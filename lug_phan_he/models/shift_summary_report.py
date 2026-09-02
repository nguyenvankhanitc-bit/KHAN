# -*- coding: utf-8 -*-

from calendar import monthrange

from odoo import api, fields, models

from .monthly_matrix_schedule import _hours_for, _norm_code

REGION_LABEL = {
    "Bắc": "Miền Bắc",
    "north": "Miền Bắc",
    "Nam": "Miền Nam",
    "south": "Miền Nam",
    "ĐTT": "Miền ĐTT",
    "dtt": "Miền ĐTT",
    "VP": "VP",
}
REGION_KEY = {
    "Miền Bắc": "north",
    "Miền Nam": "south",
    "Miền ĐTT": "dtt",
}
REGION_COLOR = {
    "north": "#2563eb",
    "south": "#f97316",
    "dtt": "#22c55e",
}


def _fmt_int(n):
    return f"{int(round(n or 0)):,}".replace(",", ".")


def _fmt_pct(n):
    return f"{n:.1f}".replace(".", ",") + "%"


def _fmt_cost_kpi(n):
    n = float(n or 0)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}".replace(".", ",") + " tỷ"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}".replace(".", ",") + " triệu"
    return _fmt_int(n) + " ₫"


def _shift_bucket(code):
    c = _norm_code(code)
    if not c or c in ("OFF", "NVM", "TV1", "LE", "LỄ"):
        return "off"
    if c.startswith("GS") or c.startswith("GC"):
        return "t"
    if c.startswith("S") or c.startswith("F"):
        return "s"
    if c.startswith("C"):
        return "c"
    return "off"


def _region_name(raw):
    if not raw:
        return "Khác"
    return REGION_LABEL.get(raw, raw if str(raw).startswith("Miền") else str(raw))


class LinkqMonthlyRosterSummary(models.Model):
    _inherit = "linkq.monthly.roster"

    def _summary_catalog(self):
        catalog = {}
        if "linkq.shift.code" in self.env:
            for rec in self.env["linkq.shift.code"].sudo().search([]):
                if rec.code:
                    catalog[_norm_code(rec.code)] = rec.total_hours or 0.0
        return catalog

    def _summary_hourly_rate(self, employee):
        """Báo cáo tổng hợp không đọc lương HR (wage bị chặn với user thường)."""
        return 25000.0

    def _summary_store_code(self, store):
        if not store:
            return ""
        for fname in ("code", "store_code", "barcode"):
            if fname in store._fields and store[fname]:
                return str(store[fname])
        return (store.name or "")[:12]

    def _code_for_day(self, line, day):
        actual = line._code_map(line.actual_codes)
        plan = line._code_map(line.plan_codes)
        key = str(day)
        return actual.get(key) or plan.get(key) or ""

    def _roster_has_codes(self, roster):
        for line in roster.line_ids:
            for day in range(1, 32):
                if self._code_for_day(line, day):
                    return True
        return False

    def _aggregate_one(self, roster, catalog):
        store = roster.store_id
        hours_s = hours_c = hours_t = hours_off = hours_total = cost = 0.0
        staff_ids = set()
        left_ids = set()
        n = roster.days_in_month or 0
        has_codes = False
        for line in roster.line_ids:
            emp = line.employee_id.sudo() if line.employee_id else False
            if emp:
                staff_ids.add(emp.id)
                if not emp.active:
                    left_ids.add(emp.id)
            elif line.employee_name:
                staff_ids.add("n:%s" % line.employee_name)
            rate = self._summary_hourly_rate(emp)
            line_hours = 0.0
            for day in range(1, (n or 31) + 1):
                code = self._code_for_day(line, day)
                if code:
                    has_codes = True
                hours = _hours_for(code, catalog)
                line_hours += hours
                bucket = _shift_bucket(code)
                if bucket == "s":
                    hours_s += hours
                elif bucket == "c":
                    hours_c += hours
                elif bucket == "t":
                    hours_t += hours
                elif _norm_code(code) in ("OFF", "LE", "LỄ"):
                    hours_off += 1
            stored = line.actual_hours or line.hour_total or 0.0
            if stored and line_hours < stored:
                hours_total += stored
                cost += stored * rate
            else:
                hours_total += line_hours
                cost += line_hours * rate
        if hours_s + hours_c + hours_t <= 0 and hours_total:
            hours_s = hours_total
        missing = 0
        slots = n * 2
        if has_codes:
            morning = roster.lack_morning or []
            evening = roster.lack_evening or []
            limit = min(n, len(morning), len(evening)) if n else 0
            missing = sum(1 for i in range(limit) if morning[i]) + sum(
                1 for i in range(limit) if evening[i]
            )
        fill = round(max(0.0, (slots - missing) * 100.0 / slots), 1) if slots and has_codes else 0.0
        total = len(staff_ids)
        left = len(left_ids)
        return {
            "roster_id": roster.id,
            "store_id": store.id if store else 0,
            "code": self._summary_store_code(store) or "—",
            "name": (store.name if store else "") or roster.name or "—",
            "region": _region_name(roster.region or (store.mien if store else "")),
            "staff_total": total,
            "staff_working": max(total - left, 0),
            "staff_left": left,
            "hours_s": int(round(hours_s)),
            "hours_c": int(round(hours_c)),
            "hours_t": int(round(hours_t)),
            "hours_off": int(round(hours_off)),
            "hours_total": int(round(hours_total)),
            "fill_rate": fill,
            "missing_shifts": missing,
            "cost": int(round(cost)),
        }

    def _aggregate_rosters(self, rosters):
        catalog = self._summary_catalog()
        rows = [self._aggregate_one(rec, catalog) for rec in rosters]
        rows.sort(key=lambda r: (r["region"], r["code"], r["roster_id"]))
        for i, row in enumerate(rows, start=1):
            row["stt"] = i
        return rows

    def _best_roster_per_store(self, rosters):
        """Mỗi cửa hàng chỉ lấy bảng xếp ca mới nhất (write_date, rồi id)."""
        best = {}
        for rec in rosters:
            key = rec.store_id.id or rec.id
            prev = best.get(key)
            if not prev:
                best[key] = rec
                continue
            rec_dt = rec.write_date or rec.create_date
            prev_dt = prev.write_date or prev.create_date
            if rec_dt > prev_dt or (rec_dt == prev_dt and rec.id > prev.id):
                best[key] = rec
        if not best:
            return rosters.browse()
        return self.browse([rec.id for rec in best.values()])

    def _kpi_delta(self, cur, prev, suffix, invert=False):
        diff = (cur or 0) - (prev or 0)
        better = diff <= 0 if invert else diff >= 0
        sign = "+" if diff > 0 else ""
        return f"{sign}{_fmt_int(diff)} {suffix}", better

    @api.model
    def get_shift_summary_dashboard(self, filters=None):
        filters = filters or {}
        today = fields.Date.context_today(self)
        year = int(filters.get("year") or today.year)
        month = int(filters.get("month") or today.month)
        month = month if 1 <= month <= 12 else today.month

        domain = [("year", "=", year), ("month", "=", str(month))]
        all_rosters = self.search(domain, order="id")
        if not all_rosters:
            last = self.search([], order="year desc, month desc", limit=1)
            if last:
                year, month = last.year, int(last.month)
                all_rosters = self.search(
                    [("year", "=", year), ("month", "=", str(month))],
                    order="id",
                )
        chart_rosters = self._best_roster_per_store(all_rosters)

        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year -= 1
        prev_rosters = self._best_roster_per_store(
            self.search([("year", "=", prev_year), ("month", "=", str(prev_month))])
        )

        stores = self._aggregate_rosters(chart_rosters)
        prev_stores = self._aggregate_rosters(prev_rosters)
        chart_rows = self._aggregate_rosters(chart_rosters)

        def totals(rows):
            return {
                "stores": len(rows),
                "staff": sum(r["staff_total"] for r in rows),
                "hours": sum(r["hours_total"] for r in rows),
                "missing": sum(r["missing_shifts"] for r in rows),
                "cost": sum(r["cost"] for r in rows),
                "fill": (
                    round(sum(r["fill_rate"] for r in rows) / len(rows), 1) if rows else 0.0
                ),
                "hours_s": sum(r["hours_s"] for r in rows),
                "hours_c": sum(r["hours_c"] for r in rows),
                "hours_t": sum(r["hours_t"] for r in rows),
            }

        cur_t = totals(chart_rows)
        prev_t = totals(prev_stores)

        d_store, up_s = self._kpi_delta(cur_t["stores"], prev_t["stores"], "cửa hàng")
        d_staff, up_st = self._kpi_delta(cur_t["staff"], prev_t["staff"], "nhân sự")
        d_hours, up_h = self._kpi_delta(cur_t["hours"], prev_t["hours"], "giờ")
        fill_diff = round((cur_t["fill"] or 0) - (prev_t["fill"] or 0), 1)
        d_fill = ("+" if fill_diff > 0 else "") + f"{fill_diff}".replace(".", ",") + "%"
        d_miss, up_m = self._kpi_delta(
            cur_t["missing"], prev_t["missing"], "ca", invert=True
        )
        cost_diff = (cur_t["cost"] or 0) - (prev_t["cost"] or 0)
        d_cost = ("+" if cost_diff > 0 else "") + _fmt_cost_kpi(abs(cost_diff))

        last_day = monthrange(year, month)[1]
        period_label = f"01/{month:02d}/{year} - {last_day:02d}/{month:02d}/{year}"

        by_region = {}
        for row in chart_rows:
            key = REGION_KEY.get(row["region"], "other")
            bucket = by_region.setdefault(
                key,
                {
                    "key": key,
                    "name": row["region"],
                    "color": REGION_COLOR.get(key, "#64748b"),
                    "staff": 0,
                    "missing": 0,
                    "hours_s": 0,
                    "hours_c": 0,
                    "hours_t": 0,
                    "fill_sum": 0.0,
                    "n": 0,
                },
            )
            bucket["staff"] += row["staff_total"]
            bucket["missing"] += row["missing_shifts"]
            bucket["hours_s"] += row["hours_s"]
            bucket["hours_c"] += row["hours_c"]
            bucket["hours_t"] += row["hours_t"]
            bucket["fill_sum"] += row["fill_rate"]
            bucket["n"] += 1

        staff_total = cur_t["staff"] or 1
        prev_by_region = {}
        for row in prev_stores:
            key = REGION_KEY.get(row["region"], "other")
            prev_by_region[key] = prev_by_region.get(key, 0) + row["staff_total"]

        regions = []
        for key in ("north", "south", "dtt"):
            b = by_region.get(
                key,
                {
                    "key": key,
                    "name": {"north": "Miền Bắc", "south": "Miền Nam", "dtt": "Miền ĐTT"}[key],
                    "color": REGION_COLOR[key],
                    "staff": 0,
                    "missing": 0,
                    "hours_s": 0,
                    "hours_c": 0,
                    "hours_t": 0,
                    "fill_sum": 0.0,
                    "n": 0,
                },
            )
            prev_staff = prev_by_region.get(key, 0)
            delta = b["staff"] - prev_staff
            delta_pct = round((delta * 100.0 / prev_staff), 1) if prev_staff else 0.0
            regions.append(
                {
                    "key": key,
                    "name": b["name"],
                    "color": b["color"],
                    "staff": b["staff"],
                    "pct": round(b["staff"] * 100.0 / staff_total, 1) if staff_total else 0.0,
                    "delta": delta,
                    "delta_pct": delta_pct,
                    "fill": round(b["fill_sum"] / b["n"], 1) if b["n"] else 0.0,
                    "missing": b["missing"],
                    "hours_s": b["hours_s"],
                    "hours_c": b["hours_c"],
                    "hours_t": b["hours_t"],
                }
            )

        low_fill = [r for r in chart_rows if r["fill_rate"] < 90]
        miss_week = [r for r in chart_rows if r["missing_shifts"] > 5]
        left_n = sum(r["staff_left"] for r in chart_rows)
        alerts = []
        if low_fill:
            alerts.append(
                {
                    "id": "low_fill",
                    "text": f"{len(low_fill)} cửa hàng tỷ lệ đủ ca < 90%",
                    "href": "fill",
                }
            )
        if miss_week:
            alerts.append(
                {
                    "id": "missing_week",
                    "text": f"{len(miss_week)} cửa hàng thiếu > 5 ca trong tuần",
                    "href": "missing",
                }
            )
        if left_n:
            alerts.append(
                {
                    "id": "headcount",
                    "text": f"{left_n} vị trí nghỉ việc / không còn active",
                    "href": "staff",
                }
            )

        mid = f"{month:02d}"
        trend_staff = {r["key"]: r["staff"] for r in regions}
        return {
            "period": {
                "from": f"{year}-{month:02d}-01",
                "to": f"{year}-{month:02d}-{last_day:02d}",
                "label": period_label,
                "compare": filters.get("compare") or "prev_month",
                "year": year,
                "month": month,
            },
            "kpis": [
                {
                    "key": "stores",
                    "label": "TỔNG CỬA HÀNG",
                    "value": _fmt_int(cur_t["stores"]),
                    "icon": "fa-building",
                    "tone": "purple",
                    "delta": d_store,
                    "up": up_s,
                },
                {
                    "key": "staff",
                    "label": "TỔNG NHÂN SỰ",
                    "value": _fmt_int(cur_t["staff"]),
                    "icon": "fa-users",
                    "tone": "green",
                    "delta": d_staff,
                    "up": up_st,
                },
                {
                    "key": "hours",
                    "label": "TỔNG GIỜ THEO CA",
                    "value": _fmt_int(cur_t["hours"]),
                    "icon": "fa-clock-o",
                    "tone": "blue",
                    "delta": d_hours,
                    "up": up_h,
                },
                {
                    "key": "fill",
                    "label": "TỶ LỆ ĐỦ CA",
                    "value": _fmt_pct(cur_t["fill"]),
                    "icon": "fa-check-circle",
                    "tone": "mint",
                    "delta": d_fill,
                    "up": fill_diff >= 0,
                },
                {
                    "key": "missing",
                    "label": "SỐ CA THIẾU",
                    "value": _fmt_int(cur_t["missing"]),
                    "icon": "fa-exclamation-triangle",
                    "tone": "red",
                    "delta": d_miss,
                    "up": up_m,
                },
            ],
            "regions": regions,
            "staff_total": cur_t["staff"],
            "staff_working": sum(r.get("staff_working", 0) for r in chart_rows),
            "staff_delta": cur_t["staff"] - prev_t["staff"],
            "staff_delta_pct": (
                round((cur_t["staff"] - prev_t["staff"]) * 100.0 / prev_t["staff"], 1)
                if prev_t["staff"]
                else 0.0
            ),
            "trend": {
                "labels": [
                    f"01/{mid}",
                    f"08/{mid}",
                    f"15/{mid}",
                    f"22/{mid}",
                    f"{last_day:02d}/{mid}",
                ],
                "north": [trend_staff.get("north", 0)] * 5,
                "south": [trend_staff.get("south", 0)] * 5,
                "dtt": [trend_staff.get("dtt", 0)] * 5,
            },
            "alerts": alerts,
            "stores": stores,
            "store_total": len(stores),
        }
