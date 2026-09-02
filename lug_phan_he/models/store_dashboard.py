# -*- coding: utf-8 -*-

from calendar import monthrange
from datetime import datetime

from odoo import api, fields, models

from .monthly_matrix_schedule import _hours_for, _norm_code
from .shift_summary_report import _fmt_pct, _shift_bucket


PAGE_SIZE = 5
PLANNED_HOURS = 160.0
WORK_STATUS_LABEL = {
    "working": "Đang công tác",
    "resigned": "Nghỉ việc",
    "transferred": "Điều chuyển",
}


def _fmt_hour_num(n):
    n = round(float(n or 0), 1)
    if abs(n - int(round(n))) < 0.05:
        return str(int(round(n)))
    return "%.1f" % n


def _fmt_hours(n):
    return _fmt_hour_num(n) + " giờ"


def _fmt_clock(value):
    raw = float(value or 0.0)
    hours = int(raw)
    minutes = int(round((raw - hours) * 60))
    if minutes >= 60:
        hours += 1
        minutes = 0
    return "%02d:%02d" % (hours % 24, minutes)


class LinkqStoreDashboard(models.Model):
    _inherit = "linkq.monthly.roster"

    def _store_dash_catalog(self):
        catalog = {}
        if "linkq.shift.code" in self.env:
            for rec in self.env["linkq.shift.code"].sudo().search([]):
                if rec.code:
                    catalog[_norm_code(rec.code)] = rec.total_hours or 0.0
        return catalog

    def _store_dash_shift_meta(self):
        meta = {}
        if "linkq.shift.code" not in self.env:
            return meta
        for rec in self.env["linkq.shift.code"].sudo().search([]):
            if not rec.code:
                continue
            time_label = "—"
            if rec.shift_group != "OFF":
                time_label = "%s - %s" % (_fmt_clock(rec.time_in), _fmt_clock(rec.time_out))
            meta[_norm_code(rec.code)] = {
                "code": rec.code,
                "time": time_label,
            }
        return meta

    def _store_dash_code(self, line, day):
        actual = line._code_map(line.actual_codes)
        plan = line._code_map(line.plan_codes)
        key = str(day)
        return actual.get(key) or plan.get(key) or ""

    def _user_store_ids(self):
        user = self.env.user
        bypass = bool(
            self.env.su
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_linkq_manager")
        )
        ids = list(user._linkq_allowed_hr_store_ids() or [])
        store = getattr(user, "store_id", False) or getattr(user, "branch_id", False)
        if store and store.id and store.id not in ids:
            ids.append(store.id)
        return ids, bypass

    def _store_base_domain(self, store=None):
        if store:
            return [("store_id", "=", store.id)]
        ids, bypass = self._user_store_ids()
        if ids:
            return [("store_id", "in", ids)] if len(ids) > 1 else [("store_id", "=", ids[0])]
        if bypass:
            return []
        return [("id", "=", False)]

    def _pick_store(self, store_id=None):
        Store = self.env["hr.store"].sudo()
        allowed, bypass = self._user_store_ids()
        if store_id:
            rec = Store.browse(int(store_id))
            if rec.exists() and (bypass or rec.id in allowed):
                return rec
        user = self.env.user
        primary = getattr(user, "store_id", False) or getattr(user, "branch_id", False)
        if primary and primary.id and (bypass or primary.id in allowed):
            return primary
        if allowed:
            return Store.browse(allowed[0])
        if bypass:
            return Store.search([("company_id", "=", self.env.company.id)], order="name", limit=1)
        return Store.browse()

    def _best_roster(self, store, year, month):
        rosters = self.search([
            ("store_id", "=", store.id),
            ("year", "=", year),
            ("month", "=", str(month)),
        ], order="id desc")
        if not rosters:
            return self.browse()
        best = rosters[0]
        best_score = -1
        for rec in rosters:
            score = sum((line.actual_hours or line.hour_total or 0.0) for line in rec.sudo().line_ids)
            score = score * 1000 + len(rec.sudo().line_ids)
            if score > best_score:
                best_score = score
                best = rec
        return best

    @api.model
    def get_dashboard_warnings(self, month=None, year=None, store_id=None):
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        if month < 1 or month > 12:
            month = today.month
        store = self._pick_store(store_id)
        if not store:
            return []
        base_domain = [("store_id", "=", store.id)]
        month_label = "Tháng %02d/%s" % (month, year)
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        next_label = "Tháng %02d/%s" % (next_month, next_year)
        roster = self._best_roster(store, year, month)
        warnings = []

        missing = 0
        short_staff = 0
        if roster:
            n = roster.days_in_month or monthrange(year, month)[1]
            morning = roster.lack_morning or []
            evening = roster.lack_evening or []
            limit = min(n, len(morning), len(evening))
            missing = sum(1 for i in range(limit) if morning[i]) + sum(
                1 for i in range(limit) if evening[i]
            )
            for line in roster.sudo().line_ids:
                hours = line.actual_hours or line.hour_total or 0.0
                planned = line.plan_hours or PLANNED_HOURS
                if hours + 0.01 < planned * 0.9:
                    short_staff += 1

        if missing:
            warnings.append({
                "key": "missing",
                "tone": "danger",
                "icon": "fa-exclamation-triangle",
                "text": "Cửa hàng đang thiếu %s ca trong %s" % (missing, month_label.lower()),
                "res_model": "linkq.monthly.roster",
                "res_id": roster.id if roster else 0,
                "action_domain": base_domain + [("year", "=", year), ("month", "=", str(month))],
            })
        if short_staff:
            warnings.append({
                "key": "hours",
                "tone": "warning",
                "icon": "fa-info-circle",
                "text": "%s nhân viên chưa đủ số giờ theo kế hoạch" % short_staff,
                "res_model": "linkq.monthly.roster",
                "res_id": roster.id if roster else 0,
                "action_domain": base_domain + [("year", "=", year), ("month", "=", str(month))],
            })

        next_roster = self._best_roster(store, next_year, next_month)
        next_has = bool(next_roster and next_roster.line_ids)
        if not next_has:
            warnings.append({
                "key": "next",
                "tone": "caution",
                "icon": "fa-clock-o",
                "text": "Lịch ca %s chưa được xếp" % next_label.lower(),
                "res_model": "linkq.monthly.roster",
                "res_id": 0,
                "action_domain": base_domain + [
                    ("year", "=", next_year),
                    ("month", "=", str(next_month)),
                ],
            })

        if roster and roster.lock_datetime and not roster.is_locked:
            lock_local = fields.Datetime.context_timestamp(self, roster.lock_datetime)
            lock_days_left = (
                lock_local.replace(tzinfo=None) - datetime.combine(today, datetime.min.time())
            ).days
            if lock_days_left is not None and lock_days_left >= 0:
                warnings.append({
                    "key": "lock",
                    "tone": "info",
                    "icon": "fa-lock",
                    "text": "Lịch ca %s sẽ khóa sau %s ngày (%s)" % (
                        month_label.lower(),
                        lock_days_left,
                        lock_local.strftime("%d/%m/%Y"),
                    ),
                    "res_model": "linkq.monthly.roster",
                    "res_id": roster.id,
                    "action_domain": base_domain + [("year", "=", year), ("month", "=", str(month))],
                })
        return warnings

    @api.model
    def get_store_dashboard_data(self, month=None, year=None, store_id=None):
        today = fields.Date.context_today(self)
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        year = int(year or today.year)
        month = int(month or today.month)
        if month < 1 or month > 12:
            month = today.month
        store = self._pick_store(store_id)
        days_n = monthrange(year, month)[1]
        catalog = self._store_dash_catalog()
        shift_meta = self._store_dash_shift_meta()
        roster = self._best_roster(store, year, month) if store else self.browse()
        today_day = today.day if year == today.year and month == today.month else 0

        emp_rows = []
        hours_by_day = [0.0] * days_n
        bucket_counts = {"s": 0, "c": 0, "t": 0, "off": 0}
        hours_total = 0.0
        working = 0
        left = 0
        paused = 0
        missing = 0
        filled = 0
        slots = days_n * 2

        for line in (roster.sudo().line_ids if roster else []):
            emp = line.employee_id.sudo() if line.employee_id else False
            name = (line.employee_name or (emp.name if emp else "") or "—").strip()
            job = (line.job_title or (emp.job_id.name if emp and emp.job_id else "") or "NV").strip()
            work_status = "working"
            if emp and "work_status" in emp._fields:
                work_status = emp.work_status or "working"
            if work_status == "resigned":
                left += 1
            elif work_status == "transferred":
                paused += 1
            else:
                working += 1
            line_hours = 0.0
            for day in range(1, days_n + 1):
                code = self._store_dash_code(line, day)
                hours = _hours_for(code, catalog)
                line_hours += hours
                hours_by_day[day - 1] += hours
                bucket_counts[_shift_bucket(code)] = bucket_counts.get(_shift_bucket(code), 0) + 1
            stored = line.actual_hours or line.hour_total or 0.0
            use_hours = stored if stored else line_hours
            hours_total += use_hours
            planned = line.plan_hours or PLANNED_HOURS
            emp_rows.append({
                "name": name,
                "job": job,
                "hours": round(use_hours, 1),
                "status": work_status,
                "active": work_status == "working",
                "shift_code": "",
                "shift_time": "—",
            })
            if today_day:
                today_code = self._store_dash_code(line, today_day)
                meta = shift_meta.get(_norm_code(today_code)) or {}
                emp_rows[-1]["shift_code"] = meta.get("code") or today_code or ""
                emp_rows[-1]["shift_time"] = meta.get("time") or ("—" if not today_code else "")

        if roster:
            morning = roster.lack_morning or []
            evening = roster.lack_evening or []
            limit = min(days_n, len(morning), len(evening))
            missing = sum(1 for i in range(limit) if morning[i]) + sum(
                1 for i in range(limit) if evening[i]
            )
            filled = max(slots - missing, 0)

        staff_total = working + left + paused
        fill_pct = round(filled * 100.0 / slots, 1) if slots else 0.0
        emp_rows.sort(key=lambda r: -r["hours"])
        top5 = emp_rows[:5]

        month_label = "Tháng %02d/%s" % (month, year)
        alerts = self.get_dashboard_warnings(
            month=month, year=year, store_id=store.id if store else False
        )

        shift_total = sum(bucket_counts.values()) or 1
        shifts = [
            {
                "key": "s",
                "label": "Ca sáng",
                "count": bucket_counts["s"],
                "pct": round(bucket_counts["s"] * 100.0 / shift_total, 0),
                "color": "#3b82f6",
            },
            {
                "key": "c",
                "label": "Ca chiều",
                "count": bucket_counts["c"],
                "pct": round(bucket_counts["c"] * 100.0 / shift_total, 0),
                "color": "#f59e0b",
            },
            {
                "key": "t",
                "label": "Ca tối",
                "count": bucket_counts["t"],
                "pct": round(bucket_counts["t"] * 100.0 / shift_total, 0),
                "color": "#22c55e",
            },
            {
                "key": "off",
                "label": "Nghỉ",
                "count": bucket_counts["off"],
                "pct": round(bucket_counts["off"] * 100.0 / shift_total, 0),
                "color": "#94a3b8",
            },
        ]

        staff_slices = [
            {"key": "working", "label": "Đang công tác", "count": working, "color": "#22c55e"},
            {"key": "left", "label": "Nghỉ việc", "count": left, "color": "#ef4444"},
            {"key": "paused", "label": "Điều chuyển", "count": paused, "color": "#f59e0b"},
        ]
        for item in staff_slices:
            item["pct"] = round(item["count"] * 100.0 / staff_total, 1) if staff_total else 0.0

        stores = []
        allowed, bypass = self._user_store_ids()
        Store = self.env["hr.store"].sudo()
        sdomain = [] if bypass else [("id", "in", allowed or [0])]
        for rec in Store.search(sdomain, order="name", limit=80):
            stores.append({"id": rec.id, "name": rec.name or ""})
        can_switch = bypass or len(stores) > 1

        return {
            "store_id": store.id if store else 0,
            "store_name": (store.name or "—").upper() if store else "—",
            "month": month,
            "year": year,
            "month_label": month_label,
            "days_in_month": days_n,
            "updated_at": now.strftime("%H:%M %d/%m/%Y") if now else "",
            "roster_id": roster.id if roster else 0,
            "can_switch_store": can_switch,
            "stores": stores,
            "kpis": {
                "staff_total": staff_total,
                "staff_total_label": "%s nhân viên" % staff_total,
                "staff_sub": "Đang công tác: %s | Nghỉ việc: %s" % (working, left),
                "hours_total": round(hours_total, 1),
                "hours_label": _fmt_hours(hours_total),
                "shifts_total": filled + missing if roster else 0,
                "shifts_label": "%s ca" % (filled + missing if roster else 0),
                "fill_pct": fill_pct,
                "fill_label": _fmt_pct(fill_pct),
                "fill_sub": "%s / %s ca" % (filled, filled + missing if roster else 0),
                "missing": missing,
                "missing_label": "%s ca" % missing,
            },
            "staff_chart": {
                "total": staff_total,
                "slices": staff_slices,
            },
            "top_employees": [
                {"name": r["name"], "hours": round(r["hours"], 1)} for r in top5
            ],
            "hours_by_day": [round(v, 1) for v in hours_by_day],
            "shift_chart": shifts,
            "alerts": alerts,
            "employees": [
                {
                    "name": r["name"],
                    "job": r["job"],
                    "hours": round(r["hours"], 1),
                    "hours_label": _fmt_hour_num(r["hours"]),
                    "status": r["status"],
                    "status_label": WORK_STATUS_LABEL.get(r["status"], r["status"]),
                    "shift_code": r.get("shift_code") or "",
                    "shift_time": r.get("shift_time") or "—",
                }
                for r in emp_rows
            ],
            "page_size": PAGE_SIZE,
        }
