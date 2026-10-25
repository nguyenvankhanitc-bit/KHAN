# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class PhanHeItDashboard(models.AbstractModel):
    _name = "phan.he.it.dashboard"
    _description = "Dashboard Máy chủ"

    @api.model
    def get_it_dashboard_data(self, filters=None):
        filters = filters or {}
        today = fields.Date.context_today(self)
        Asset = self.env["phan.he.it.asset"]
        Cost = self.env["phan.he.it.cost"]
        Ticket = self.env["phan.he.it.ticket"]

        domain = [("active", "=", True)]
        if filters.get("mien_id"):
            domain.append(("mien_id", "=", int(filters["mien_id"])))
        if filters.get("asset_type_id"):
            domain.append(("asset_type_id", "=", int(filters["asset_type_id"])))
        if filters.get("state"):
            domain.append(("state", "=", filters["state"]))
        if filters.get("provider_id"):
            domain.append(("provider_id", "=", int(filters["provider_id"])))

        assets = Asset.search(domain)
        active_n = len(assets.filtered(lambda a: a.state == "active"))
        retired_n = len(assets.filtered(lambda a: a.state in ("retired", "suspended")))

        year = int(filters.get("year") or today.year)
        month = int(filters.get("month") or today.month)
        m_start = fields.Date.to_date("%04d-%02d-01" % (year, month))
        m_end = m_start + relativedelta(months=1, days=-1)
        prev_start = m_start - relativedelta(months=1)
        prev_end = m_start - relativedelta(days=1)
        y_start = fields.Date.to_date("%04d-01-01" % year)
        # Xu hướng số tài sản: so với tài sản tạo trước đầu tháng hiện tại.
        prev_asset_n = Asset.search_count(domain + [("create_date", "<", fields.Datetime.to_datetime(m_start))])
        asset_delta = 0.0
        if prev_asset_n:
            asset_delta = round((len(assets) - prev_asset_n) / abs(prev_asset_n) * 100, 1)
        elif assets:
            asset_delta = 100.0

        cost_domain = [("active", "=", True), ("asset_id", "in", assets.ids or [0])]
        if filters.get("provider_id"):
            cost_domain.append(("provider_id", "=", int(filters["provider_id"])))

        def cost_in_period(rec, d0, d1, mode="overlap"):
            """overlap: còn hiệu lực giao kỳ; anchor: ngày bắt đầu nằm trong kỳ."""
            ds = rec.date_start or rec.date_end
            de = rec.date_end or rec.date_start
            if not ds:
                return False
            if mode == "anchor":
                return d0 <= ds <= d1
            return ds <= d1 and (not de or de >= d0)

        def cost_amount(rec):
            if rec.amount_untaxed_actual:
                return float(rec.amount_untaxed_actual or 0) + float(rec.amount_tax or 0)
            return float(rec.amount_total or 0)

        def cost_budget(rec):
            """Ngân sách / kế hoạch: ưu tiên cước tháng (amount_untaxed)."""
            planned = float(rec.amount_untaxed or 0)
            if planned > 0:
                return planned
            return cost_amount(rec)

        def sum_costs(d0, d1, mode="overlap", budget=False):
            # Theo tháng trên tổng quan / nhóm tài sản: lấy khoản chi còn hiệu lực trong kỳ.
            recs = Cost.search(cost_domain).filtered(
                lambda c, s=d0, e=d1, m=mode: cost_in_period(c, s, e, m)
            )
            fn = cost_budget if budget else cost_amount
            return sum(fn(c) for c in recs)

        month_total = sum_costs(m_start, m_end, "overlap")
        prev_total = sum_costs(prev_start, prev_end, "overlap")
        year_total = sum_costs(y_start, m_end, "overlap")
        year_budget_ytd = sum_costs(y_start, m_end, "overlap", budget=True)
        prev_ytd = sum_costs(y_start, prev_end, "overlap") if prev_end >= y_start else 0.0
        month_delta = 0.0
        if prev_total:
            month_delta = round((month_total - prev_total) / abs(prev_total) * 100, 1)
        elif month_total:
            month_delta = 100.0
        year_delta = 0.0
        if prev_ytd:
            year_delta = round((year_total - prev_ytd) / abs(prev_ytd) * 100, 1)
        elif year_total:
            year_delta = 100.0

        soon30 = today + relativedelta(days=30)
        soon180 = today + relativedelta(days=180)
        expiring = Cost.search_count(cost_domain + [
            ("date_end", ">=", today),
            ("date_end", "<=", soon30),
            ("renewal_state", "in", ("active", "expiring")),
        ])
        overdue = Cost.search_count(cost_domain + [
            ("date_end", "<", today),
            ("renewal_state", "in", ("active", "expiring", "overdue")),
        ])
        confirm = Cost.search_count(cost_domain + [
            ("payment_state", "=", "confirm"),
        ])
        maintain_need = Cost.search_count(cost_domain + [
            "|",
            "&", ("date_end", "<", today),
            ("renewal_state", "in", ("active", "expiring", "overdue")),
            "&", ("date_end", ">=", today), ("date_end", "<=", soon180),
            ("renewal_state", "in", ("active", "expiring", "overdue", "quote")),
        ])

        # Chi phí 12 tháng + ngân sách tháng + dự báo các tháng còn lại
        month_series = []
        actual_vals = []
        for mo in range(1, 13):
            s = fields.Date.to_date("%04d-%02d-01" % (year, mo))
            e = s + relativedelta(months=1, days=-1)
            is_future = (year > today.year) or (year == today.year and mo > today.month)
            amt = 0.0 if is_future else sum_costs(s, e)
            bud = 0.0 if is_future else sum_costs(s, e, "overlap", budget=True)
            if not is_future:
                actual_vals.append(amt)
            month_series.append({
                "month": mo,
                "label": "T%s" % mo,
                "amount": amt,
                "budget": bud,
                "forecast": False,
            })
        avg_actual = (sum(actual_vals) / len(actual_vals)) if actual_vals else 0.0
        last_actual = actual_vals[-1] if actual_vals else 0.0
        for row in month_series:
            mo = row["month"]
            is_future = (year > today.year) or (year == today.year and mo > today.month)
            if is_future:
                base = last_actual or avg_actual
                row["forecast"] = round(base * 1.05, 0) if base else 0.0
                row["budget"] = round(base * 1.15, 0) if base else 0.0
            else:
                row["forecast"] = row["amount"]
                if not row["budget"]:
                    row["budget"] = round(row["amount"] * 1.15, 0) if row["amount"] else 0.0

        # Ngân sách cả năm = tổng budget tháng; dự báo cuối năm = actual đã có + forecast tương lai
        year_budget = sum(float(r["budget"] or 0) for r in month_series)
        if year_budget_ytd > year_budget:
            year_budget = year_budget_ytd
        if year_total > year_budget:
            year_budget = round(year_total / 0.62, 0) if year_total else year_budget
        year_end_forecast = sum(
            float(r["amount"] or 0) if not (
                (year > today.year) or (year == today.year and r["month"] > today.month)
            ) else float(r["forecast"] or 0)
            for r in month_series
        )
        budget_usage_pct = round(year_total * 100.0 / year_budget, 1) if year_budget else 0.0
        next_year_budget = round((year_end_forecast or year_total) * 1.08, 0)

        # So sánh quý
        quarter_series = []
        for q in range(1, 5):
            qs = fields.Date.to_date("%04d-%02d-01" % (year, (q - 1) * 3 + 1))
            qe = qs + relativedelta(months=3, days=-1)
            q_actual = sum_costs(qs, qe, "overlap")
            q_budget = sum_costs(qs, qe, "overlap", budget=True) or round(q_actual * 1.15, 0)
            quarter_series.append({
                "quarter": q,
                "label": "Q%s" % q,
                "actual": round(q_actual, 0),
                "budget": round(q_budget, 0),
                "usage_pct": round(q_actual * 100.0 / q_budget, 1) if q_budget else 0.0,
            })

        # Chi phí theo hạng mục
        by_category = []
        cat_total = 0.0
        cats = self.env["phan.he.it.cost.category"].search([("active", "=", True)])
        for cat in cats:
            cat_costs = Cost.search(cost_domain + [("category_id", "=", cat.id)])
            amt = 0.0
            for c in cat_costs:
                if cost_in_period(c, m_start, m_end, "overlap"):
                    amt += cost_amount(c)
            if amt:
                by_category.append({
                    "id": cat.id,
                    "name": cat.name,
                    "amount": round(amt, 0),
                })
                cat_total += amt
        by_category.sort(key=lambda r: r["amount"], reverse=True)
        for row in by_category:
            row["pct"] = round(row["amount"] * 100.0 / cat_total, 1) if cat_total else 0.0

        # OPEX / CAPEX (heuristic theo tên hạng mục)
        opex = 0.0
        capex = 0.0
        for c in Cost.search(cost_domain).filtered(
            lambda rec: cost_in_period(rec, y_start, m_end, "overlap")
        ):
            name_l = ((c.category_id.name or "") + " " + (c.category_id.code or "")).lower()
            amt = cost_amount(c)
            if any(k in name_l for k in ("mua", "capex", "đầu tư", "dau tu", "thiết bị mới")):
                capex += amt
            else:
                opex += amt
        oc_total = opex + capex or 1.0
        opex_capex = [
            {
                "id": "opex",
                "label": "OPEX",
                "amount": round(opex, 0),
                "pct": round(opex * 100.0 / oc_total, 1),
                "color": "#3b82f6",
            },
            {
                "id": "capex",
                "label": "CAPEX",
                "amount": round(capex, 0),
                "pct": round(capex * 100.0 / oc_total, 1),
                "color": "#22c55e",
            },
        ]

        # Xu hướng nhiều năm
        year_trend = []
        for y in range(year - 2, year + 2):
            ys = fields.Date.to_date("%04d-01-01" % y)
            ye = fields.Date.to_date("%04d-12-31" % y)
            if y > today.year:
                base = year_end_forecast or year_total
                year_trend.append({
                    "year": y,
                    "label": str(y),
                    "amount": 0.0,
                    "forecast": round(base * (1.08 ** (y - year)), 0) if base else 0.0,
                })
            else:
                amt = sum_costs(ys, min(ye, m_end) if y == year else ye, "overlap")
                year_trend.append({
                    "year": y,
                    "label": str(y),
                    "amount": round(amt, 0),
                    "forecast": round(amt, 0),
                })

        # Theo nhóm tài sản — chi phí của tháng đang chọn (overlap kỳ)
        by_type = []
        types = self.env["phan.he.it.asset.type"].search([("active", "=", True)])
        type_total = 0.0
        for t in types:
            t_assets = assets.filtered(lambda a, tid=t.id: a.asset_type_id.id == tid)
            t_costs = Cost.search(cost_domain + [("asset_id", "in", t_assets.ids or [0])])
            amt = 0.0
            for c in t_costs:
                if not cost_in_period(c, m_start, m_end, "overlap"):
                    continue
                amt += cost_amount(c)
            name_l = (t.name or "").lower()
            is_main = any(k in name_l for k in ("vật lý", "ảo", "mạng", "bảo mật", "virtual", "network"))
            if amt or t_assets or is_main:
                by_type.append({
                    "id": t.id,
                    "code": t.code,
                    "name": t.name,
                    "color": t.color or "#64748b",
                    "amount": amt,
                    "count": len(t_assets),
                })
                type_total += amt
        for row in by_type:
            row["pct"] = round(row["amount"] * 100 / type_total, 1) if type_total else 0.0

        # Theo miền — cùng tháng đang chọn
        by_mien = []
        miens = self.env["phan.he.mien"].search([("active", "=", True)])
        mien_total = 0.0
        for m in miens:
            m_assets = assets.filtered(lambda a, mid=m.id: a.mien_id.id == mid)
            m_costs = Cost.search(cost_domain + [("asset_id", "in", m_assets.ids or [0])])
            amt = 0.0
            for c in m_costs:
                if not cost_in_period(c, m_start, m_end, "overlap"):
                    continue
                amt += cost_amount(c)
            by_mien.append({
                "id": m.id,
                "code": m.code or "",
                "name": m.name,
                "amount": amt,
            })
            mien_total += amt
        for row in by_mien:
            row["pct"] = round(row["amount"] * 100 / mien_total, 1) if mien_total else 0.0

        renewal_labels = {
            "active": "Đang hiệu lực",
            "expiring": "Sắp hết hạn",
            "overdue": "Quá hạn",
            "quote": "Chờ báo giá",
            "approval": "Chờ phê duyệt",
            "processing": "Đang xử lý",
            "renewed": "Đã gia hạn",
            "cancel": "Đã hủy",
        }

        # Việc cần xử lý (bảng dưới)
        todo = []
        for c in Cost.search(cost_domain + [
            "|",
            "&", ("date_end", ">=", today), ("date_end", "<=", soon30),
            "|",
            ("date_end", "<", today),
            ("payment_state", "in", ("confirm", "pending", "overdue")),
        ], limit=50, order="date_end asc"):
            kind = "expiring"
            status_label = renewal_labels.get(c.renewal_state, c.renewal_state or "")
            if c.date_end and c.date_end < today:
                kind = "overdue"
                status_label = "Quá hạn"
            elif c.renewal_state == "expiring" or (
                c.date_end and today <= c.date_end <= soon30
            ):
                kind = "expiring"
                status_label = "Sắp hết hạn"
            elif c.payment_state in ("confirm", "pending"):
                kind = "payment"
            elif c.renewal_state in ("active", "renewed"):
                kind = "active"
                status_label = "Đang hiệu lực"
            asset = c.asset_id
            brand = " ".join(
                p for p in [(asset.manufacturer or "").strip(), (asset.model_name or "").strip()] if p
            ) or "—"
            todo.append({
                "id": c.id,
                "model": "phan.he.it.cost",
                "asset": asset.name,
                "asset_code": asset.code,
                "brand": brand,
                "asset_type": asset.asset_type_id.name or "",
                "category": c.category_id.name,
                "date_start": fields.Date.to_string(c.date_start) if c.date_start else "",
                "date_end": fields.Date.to_string(c.date_end) if c.date_end else "",
                "date": fields.Date.to_string(c.date_end) if c.date_end else "",
                "amount": c.amount_total,
                "state": c.renewal_state,
                "status_label": status_label,
                "payment_state": c.payment_state,
                "responsible": c.responsible_id.name or "",
                "kind": kind,
            })

        # Lịch gia hạn sắp tới
        renewal_schedule = []
        for c in Cost.search(cost_domain + [
            ("date_end", "!=", False),
            ("renewal_state", "not in", ("cancel",)),
        ], limit=8, order="date_end asc"):
            kind = "active"
            label = renewal_labels.get(c.renewal_state, "Đang hiệu lực")
            if c.date_end < today:
                kind = "overdue"
                label = "Quá hạn"
            elif c.date_end <= soon30:
                kind = "expiring"
                label = "Sắp hết hạn"
            renewal_schedule.append({
                "id": c.id,
                "date": fields.Date.to_string(c.date_end),
                "day": c.date_end.day,
                "month_label": "Th%s" % c.date_end.month,
                "name": c.asset_id.name or c.asset_name or "—",
                "category": c.category_id.name or "",
                "status_label": label,
                "kind": kind,
            })

        # Donut tình trạng gia hạn (ưu tiên số tài sản đang hoạt động như mockup)
        renew_stopped = retired_n
        renewal_status = [
            {"id": "active", "label": "Đang hoạt động", "count": active_n, "color": "#22c55e"},
            {"id": "expiring", "label": "Sắp hết hạn", "count": expiring, "color": "#f59e0b"},
            {"id": "overdue", "label": "Quá hạn", "count": overdue, "color": "#ef4444"},
            {"id": "stopped", "label": "Ngừng hoạt động", "count": renew_stopped, "color": "#94a3b8"},
        ]
        renew_base = float(len(assets) or sum(r["count"] for r in renewal_status) or 1)
        for row in renewal_status:
            row["pct"] = round(row["count"] * 100.0 / renew_base, 1)

        # Treemap phân bổ theo loại tài sản (đã có by_type)
        allocate = []
        for row in by_type:
            allocate.append({
                "id": row["id"],
                "name": row["name"],
                "color": row["color"],
                "amount": row["amount"],
                "count": row["count"],
                "pct": row["pct"],
            })

        # Vòng đời / kế hoạch thay thế theo nhóm tài sản
        lifecycle = []
        for t in types:
            t_assets = assets.filtered(lambda a, tid=t.id: a.asset_type_id.id == tid)
            if not t_assets and not any(
                k in (t.name or "").lower()
                for k in ("vật lý", "ảo", "mạng", "bảo mật", "virtual", "network")
            ):
                continue
            t_costs = Cost.search(cost_domain + [("asset_id", "in", t_assets.ids or [0])])
            n_ok = 0
            n_soon = 0
            n_over = 0
            seen = set()
            for c in t_costs:
                aid = c.asset_id.id
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                if not c.date_end:
                    n_ok += 1
                elif c.date_end < today:
                    n_over += 1
                elif c.date_end <= soon180:
                    n_soon += 1
                else:
                    n_ok += 1
            # Tài sản chưa gắn chi phí → đang hiệu lực
            n_ok += max(0, len(t_assets) - len(seen))
            lifecycle.append({
                "id": t.id,
                "name": t.name,
                "active": n_ok,
                "expiring": n_soon,
                "overdue": n_over,
            })

        asset_total = len(assets) or 1
        return {
            "updated_at": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ).strftime("%H:%M %d/%m/%Y"),
            "year": year,
            "month": month,
            "selected_month": "%04d-%02d" % (year, month),
            "kpi": {
                "asset_total": len(assets),
                "asset_active": active_n,
                "asset_inactive": retired_n,
                "asset_delta": asset_delta,
                "asset_active_pct": round(active_n * 100.0 / asset_total, 1),
                "expiring_pct": round(expiring * 100.0 / asset_total, 1),
                "month_cost": month_total,
                "month_delta": month_delta,
                "year_cost": year_total,
                "year_delta": year_delta,
                "year_budget": round(year_budget, 0),
                "budget_usage_pct": budget_usage_pct,
                "year_end_forecast": round(year_end_forecast, 0),
                "budget_remain": round(max(year_budget - year_total, 0), 0),
                "expiring": expiring,
                "overdue": overdue,
                "confirm": confirm,
                "maintain_need": maintain_need,
                "next_year_budget": next_year_budget,
            },
            "month_series": month_series,
            "quarter_series": quarter_series,
            "by_type": by_type,
            "by_mien": by_mien,
            "by_category": by_category,
            "opex_capex": opex_capex,
            "lifecycle": lifecycle,
            "year_trend": year_trend,
            "renewal_status": renewal_status,
            "renewal_schedule": renewal_schedule,
            "allocate": allocate,
            "todo": todo,
            "filters": {
                "miens": [{"id": m.id, "name": m.name} for m in miens],
                "types": [{"id": t.id, "name": t.name} for t in types],
                "providers": self.env["phan.he.provider"].search_read(
                    [("active", "=", True)], ["name"], order="name", limit=200
                ),
            },
        }

    @api.model
    def get_it_month_cost_board(self, params=None):
        """Chi phí tháng Máy chủ — cùng layout board Internet.

        Tập khoản: date_end trong tháng chọn, hoặc quá hạn từ các tháng trước.
        """
        params = params or {}
        today = fields.Date.context_today(self)
        year = int(params.get("year") or today.year)
        month = int(params.get("month") or today.month)
        month = min(12, max(1, month))
        region = (params.get("region") or "all") or "all"
        provider_id = int(params["provider_id"]) if params.get("provider_id") else False
        pay_filter = (params.get("pay_status") or "all") or "all"

        start = fields.Date.from_string("%04d-%02d-01" % (year, month))
        end = start + relativedelta(months=1, days=-1)
        if start <= today <= end:
            as_of = today
        elif end < today:
            as_of = end
        else:
            as_of = start

        Cost = self.env["phan.he.it.cost"]
        domain = [
            ("active", "=", True),
            ("renewal_state", "!=", "cancel"),
            ("payment_state", "!=", "cancel"),
            "|",
            "&", ("date_end", ">=", start), ("date_end", "<=", end),
            "&", ("date_end", "!=", False), ("date_end", "<", start),
        ]
        if provider_id:
            domain.append(("provider_id", "=", provider_id))
        costs = Cost.search(domain, order="date_end asc, id asc")
        if region and region != "all":
            costs = costs.filtered(
                lambda c, rg=region: (c.asset_id.mien_id.name or "") == rg
            )

        def period_amount(rec):
            return float(rec.amount_total or rec.amount_untaxed or 0.0)

        def paid_amount(rec):
            if rec.payment_state == "paid":
                return period_amount(rec)
            return 0.0

        def pay_status_of(rec, monthly, paid_cap, remain_amt):
            if monthly <= 0 and paid_cap <= 0:
                return "none"
            if rec.payment_state == "paid" or (remain_amt <= 0 and (monthly > 0 or paid_cap > 0)):
                return "paid"
            if paid_cap > 0:
                return "partial"
            return "unpaid"

        def week_ranges():
            last = end.day
            cuts = [(1, min(5, last)), (6, min(12, last)), (13, min(19, last)), (20, last)]
            out = []
            for i, (a, b) in enumerate(cuts, 1):
                if a > last:
                    break
                b = max(a, b)
                out.append({
                    "key": "w%s" % i,
                    "label": "Tuần %s" % i,
                    "sub": "%02d-%02d/%02d" % (a, b, month),
                    "d0": start.replace(day=a),
                    "d1": start.replace(day=b),
                })
            return out

        weeks = week_ranges()
        week_total = [0.0] * len(weeks)
        week_paid = [0.0] * len(weeks)
        week_remain = [0.0] * len(weeks)

        def week_index(day):
            if not day:
                return None
            for i, w in enumerate(weeks):
                if w["d0"] <= day <= w["d1"]:
                    return i
            return None

        rows = []
        due_buckets = {"lt7": 0, "d7_15": 0, "d16_30": 0, "overdue": 0}
        status_counts = {"paid": 0, "partial": 0, "unpaid": 0, "none": 0}
        kpi = {
            "total_amount": 0.0,
            "total_count": 0,
            "paid_amount": 0.0,
            "paid_count": 0,
            "unpaid_amount": 0.0,
            "unpaid_count": 0,
        }

        for rec in costs:
            monthly = period_amount(rec)
            paid_sum = paid_amount(rec)
            paid_cap = min(paid_sum, monthly) if monthly > 0 else paid_sum
            remain_amt = max(monthly - paid_cap, 0.0)
            pay_status = pay_status_of(rec, monthly, paid_cap, remain_amt)
            if pay_filter not in ("all", "", False) and pay_status != pay_filter:
                continue

            days = (rec.date_end - as_of).days if rec.date_end else 0
            due_key = ""
            if days < 0:
                due_key = "overdue"
                due_buckets["overdue"] += 1
                due_buckets["lt7"] += 1
            elif 0 <= days < 7:
                due_key = "lt7"
                due_buckets["lt7"] += 1
            elif 7 <= days <= 15:
                due_key = "d7_15"
                due_buckets["d7_15"] += 1
            elif 16 <= days <= 30:
                due_key = "d16_30"
                due_buckets["d16_30"] += 1

            status_counts[pay_status] = status_counts.get(pay_status, 0) + 1
            kpi["total_amount"] += monthly
            kpi["total_count"] += 1
            kpi["paid_amount"] += paid_cap
            if pay_status == "paid":
                kpi["paid_count"] += 1
            elif pay_status in ("unpaid", "partial"):
                kpi["unpaid_count"] += 1

            wi = week_index(rec.date_end) if rec.date_end and start <= rec.date_end <= end else None
            if wi is None and rec.date_end and rec.date_end < start:
                wi = 0
            if wi is None:
                wi = len(weeks) - 1
            week_total[wi] += monthly
            week_paid[wi] += paid_cap
            week_remain[wi] += remain_amt

            asset = rec.asset_id
            provider = rec.provider_id or asset.provider_id
            rows.append({
                "id": rec.id,
                "store": asset.name or rec.asset_name or "—",
                "code": asset.code or rec.code or "",
                "provider": provider.name if provider else "—",
                "provider_id": provider.id if provider else False,
                "region": asset.mien_id.name or "",
                "date_start": fields.Date.to_string(rec.date_start) if rec.date_start else False,
                "date_end": fields.Date.to_string(rec.date_end) if rec.date_end else False,
                "remaining_days": days,
                "due_key": "lt7" if due_key == "overdue" else due_key,
                "monthly": monthly,
                "paid": paid_cap,
                "remain": remain_amt,
                "pay_status": pay_status,
            })

        kpi["unpaid_amount"] = max(kpi["total_amount"] - kpi["paid_amount"], 0.0)
        kpi["paid_count"] = status_counts["paid"]
        kpi["unpaid_count"] = status_counts["unpaid"] + status_counts["partial"]

        total_n = kpi["total_count"] or 1
        donut = [
            {
                "id": "paid",
                "label": "Đã thanh toán",
                "count": status_counts["paid"],
                "pct": round(status_counts["paid"] * 100 / total_n),
                "color": "#22c55e",
            },
            {
                "id": "partial",
                "label": "Thanh toán 1 phần",
                "count": status_counts["partial"],
                "pct": round(status_counts["partial"] * 100 / total_n),
                "color": "#f59e0b",
            },
            {
                "id": "unpaid",
                "label": "Chưa thanh toán",
                "count": status_counts["unpaid"],
                "pct": round(status_counts["unpaid"] * 100 / total_n),
                "color": "#ef4444",
            },
        ]
        providers = self.env["phan.he.provider"].search_read(
            [("active", "=", True)], ["name"], order="name asc"
        )
        regions = sorted({
            m.name for m in self.env["phan.he.mien"].search([("active", "=", True)]) if m.name
        })
        return {
            "year": year,
            "month": month,
            "month_label": "Tháng %02d/%s" % (month, year),
            "as_of": fields.Date.to_string(as_of),
            "entity_label": "thiết bị",
            "kpi": kpi,
            "weeks": [
                {
                    "label": w["label"],
                    "sub": w["sub"],
                    "total": week_total[i],
                    "paid": week_paid[i],
                    "remain": week_remain[i],
                }
                for i, w in enumerate(weeks)
            ],
            "due_bars": [
                {"id": "lt7", "label": "< 7 ngày", "count": due_buckets["lt7"], "color": "#ef4444"},
                {"id": "d7_15", "label": "7 - 15 ngày", "count": due_buckets["d7_15"], "color": "#f97316"},
                {"id": "d16_30", "label": "16 - 30 ngày", "count": due_buckets["d16_30"], "color": "#facc15"},
            ],
            "donut": donut,
            "rows": rows,
            "providers": providers,
            "regions": regions,
        }

    @api.model
    def _it_month_cost_records(self, year, month, region="all", provider_id=False):
        """Khoản chi phí thuộc tháng (date_end trong tháng hoặc quá hạn trước tháng)."""
        year = int(year)
        month = min(12, max(1, int(month)))
        start = fields.Date.from_string("%04d-%02d-01" % (year, month))
        end = start + relativedelta(months=1, days=-1)
        domain = [
            ("active", "=", True),
            ("renewal_state", "!=", "cancel"),
            ("payment_state", "!=", "cancel"),
            "|",
            "&", ("date_end", ">=", start), ("date_end", "<=", end),
            "&", ("date_end", "!=", False), ("date_end", "<", start),
        ]
        if provider_id:
            domain.append(("provider_id", "=", int(provider_id)))
        costs = self.env["phan.he.it.cost"].search(domain, order="date_end asc, id asc")
        if region and region != "all":
            costs = costs.filtered(
                lambda c, rg=region: (c.asset_id.mien_id.name or "") == rg
            )
        return costs

    @api.model
    def _it_cost_period_amount(self, rec):
        return float(rec.amount_total or rec.amount_untaxed or 0.0)

    @api.model
    def _it_cost_pay_status(self, rec):
        monthly = self._it_cost_period_amount(rec)
        paid = monthly if rec.payment_state == "paid" else 0.0
        remain = max(monthly - paid, 0.0)
        if monthly <= 0 and paid <= 0:
            return "none", monthly, paid, remain
        if rec.payment_state == "paid" or (remain <= 0 and monthly > 0):
            return "paid", monthly, paid, remain
        if paid > 0:
            return "partial", monthly, paid, remain
        return "unpaid", monthly, paid, remain

    @api.model
    def get_it_quarter_cost_board(self, params=None):
        """Chi phí quý Máy chủ — cùng layout board Internet."""
        params = params or {}
        today = fields.Date.context_today(self)
        year = int(params.get("year") or today.year)
        quarter = int(params.get("quarter") or ((today.month - 1) // 3 + 1))
        quarter = min(4, max(1, quarter))
        region = (params.get("region") or "all") or "all"
        provider_id = int(params["provider_id"]) if params.get("provider_id") else False
        pay_filter = (params.get("pay_status") or "all") or "all"

        month_names = {
            1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
            7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12",
        }
        region_color = {
            "Miền Bắc": "#3b82f6",
            "Miền Trung": "#22c55e",
            "Miền Nam": "#f59e0b",
            "Miền ĐTT": "#f97316",
            "Văn phòng": "#94a3b8",
            "Khác": "#94a3b8",
        }

        def provider_color(name):
            u = (name or "").upper()
            if "VIETTEL" in u:
                return "#4f7cff"
            if "FPT" in u:
                return "#3b82f6"
            if "VNPT" in u:
                return "#22c55e"
            if "CMC" in u:
                return "#7c3aed"
            return "#f59e0b"

        def quarter_months(q):
            sm = (q - 1) * 3 + 1
            return (sm, sm + 1, sm + 2)

        def iter_quarter_costs(q):
            for m in quarter_months(q):
                for rec in self._it_month_cost_records(year, m, region=region, provider_id=provider_id):
                    amt = self._it_cost_period_amount(rec)
                    if amt <= 0:
                        continue
                    yield m, rec, amt

        def ops_of(rec):
            if rec.renewal_state == "overdue" or (rec.remaining_days is not False and rec.remaining_days < 0):
                return "active", "danger"
            if rec.renewal_state == "expiring" or (rec.remaining_days is not False and 0 <= rec.remaining_days <= 30):
                return "active", "warn"
            return "active", "ok"

        quarter_kpis = []
        for q in (1, 2, 3, 4):
            providers = set()
            seen = set()
            total = 0.0
            for _m, rec, amt in iter_quarter_costs(q):
                status, _mo, _paid, _remain = self._it_cost_pay_status(rec)
                if pay_filter not in ("all", "", False) and status != pay_filter:
                    continue
                total += amt
                seen.add(rec.id)
                provider = rec.provider_id or rec.asset_id.provider_id
                if provider:
                    providers.add(provider.id)
            sm = (q - 1) * 3 + 1
            quarter_kpis.append({
                "quarter": q,
                "year": year,
                "month_range": "Tháng %s – %s/%s" % (month_names[sm], month_names[sm + 2], year),
                "total_amount": total,
                "contract_count": len(seen),
                "provider_count": len(providers),
            })

        rows_by_id = {}
        monthly_map = {m: 0.0 for m in quarter_months(quarter)}
        provider_map = {}
        region_map = {}
        kpi = {
            "total_amount": 0.0,
            "paid_amount": 0.0,
            "unpaid_amount": 0.0,
            "total_count": 0,
        }
        paid_once = set()
        for m, rec, amt in iter_quarter_costs(quarter):
            status, monthly, paid_sum, remain_amt = self._it_cost_pay_status(rec)
            if pay_filter not in ("all", "", False) and status != pay_filter:
                continue
            kpi["total_amount"] += amt
            monthly_map[m] = monthly_map.get(m, 0.0) + amt
            provider = rec.provider_id or rec.asset_id.provider_id
            pname = provider.name if provider else "Khác"
            provider_map[pname] = provider_map.get(pname, 0.0) + amt
            rkey = rec.asset_id.mien_id.name or "Khác"
            region_map[rkey] = region_map.get(rkey, 0.0) + amt
            if rec.id not in paid_once:
                paid_cap = min(paid_sum, amt) if amt else paid_sum
                kpi["paid_amount"] += paid_cap
                paid_once.add(rec.id)
            row = rows_by_id.get(rec.id)
            if not row:
                ops_status, alert = ops_of(rec)
                asset = rec.asset_id
                row = {
                    "id": rec.id,
                    "store": asset.name or rec.asset_name or "—",
                    "code": asset.code or rec.code or "",
                    "customer_code": asset.code or "",
                    "contract_code": rec.code or "",
                    "provider": pname,
                    "provider_id": provider.id if provider else False,
                    "bandwidth": rec.bandwidth or "—",
                    "region": rkey if rkey != "Khác" else "",
                    "date_start": fields.Date.to_string(rec.date_start) if rec.date_start else False,
                    "date_end": fields.Date.to_string(rec.date_end) if rec.date_end else False,
                    "monthly": 0.0,
                    "paid": paid_sum,
                    "next_payment_amount": amt,
                    "remain": 0.0,
                    "pay_status": status,
                    "ops_status": ops_status,
                    "remaining_days": rec.remaining_days if rec.remaining_days is not False else 0,
                    "remaining_time": rec.remaining_label or "",
                    "alert_level": alert,
                }
                rows_by_id[rec.id] = row
            row["monthly"] += amt
            row["next_payment_amount"] = row["monthly"]
            row["remain"] = max(row["monthly"] - min(paid_sum, row["monthly"]), 0.0)
        rows = list(rows_by_id.values())
        kpi["total_count"] = len(rows)
        kpi["unpaid_amount"] = max(kpi["total_amount"] - kpi["paid_amount"], 0.0)

        months_in_q = [(quarter - 1) * 3 + i for i in (1, 2, 3)]
        monthly_trend = [
            {"label": "Tháng %s/%s" % (m, year), "value": monthly_map.get(m, 0.0)}
            for m in months_in_q
        ]
        by_provider = [
            {"label": name, "value": amt, "color": provider_color(name)}
            for name, amt in sorted(provider_map.items(), key=lambda x: -x[1])
        ]
        region_total = sum(region_map.values()) or 1.0
        by_region = [
            {
                "label": name,
                "value": amt,
                "percent": round(amt * 100 / region_total),
                "color": region_color.get(name, "#94a3b8"),
            }
            for name, amt in sorted(region_map.items(), key=lambda x: -x[1])
        ]
        providers = self.env["phan.he.provider"].search_read(
            [("active", "=", True)], ["name"], order="name asc"
        )
        regions = sorted({
            m.name for m in self.env["phan.he.mien"].search([("active", "=", True)]) if m.name
        })
        sm = (quarter - 1) * 3 + 1
        return {
            "year": year,
            "quarter": quarter,
            "quarter_label": "Quý %s/%s (Tháng %s - %s/%s)" % (
                quarter, year, month_names[sm], month_names[sm + 2], year
            ),
            "entity_label": "thiết bị",
            "kpi": kpi,
            "quarter_kpis": quarter_kpis,
            "monthly_trend": monthly_trend,
            "by_provider": by_provider,
            "by_region": by_region,
            "rows": rows,
            "providers": providers,
            "regions": regions,
        }

    @api.model
    def get_it_year_cost_board(self, params=None):
        """Chi phí năm Máy chủ — so sánh năm / tháng, NCC, cơ cấu, bảng chi tiết."""
        params = params or {}
        today = fields.Date.context_today(self)
        year = int(params.get("year") or today.year)
        prev_year = year - 1
        region = (params.get("region") or "all") or "all"
        provider_id = int(params["provider_id"]) if params.get("provider_id") else False

        Cost = self.env["phan.he.it.cost"]
        domain = [
            ("active", "=", True),
            ("renewal_state", "!=", "cancel"),
            ("payment_state", "!=", "cancel"),
        ]
        if provider_id:
            domain.append(("provider_id", "=", provider_id))
        costs = Cost.search(domain)
        if region and region != "all":
            costs = costs.filtered(
                lambda c, rg=region: (c.asset_id.mien_id.name or "") == rg
            )

        def amount_of(rec):
            return self._it_cost_period_amount(rec)

        def anchor(rec):
            return rec.date_start or rec.date_end

        def collect_year(y):
            month_map = {m: 0.0 for m in range(1, 13)}
            provider_map = {}
            category_map = {}
            asset_map = {}
            total = 0.0
            for rec in costs:
                a = anchor(rec)
                if not a or a.year != y:
                    continue
                amt = amount_of(rec)
                if amt <= 0:
                    continue
                total += amt
                month_map[a.month] = month_map.get(a.month, 0.0) + amt
                provider = rec.provider_id or rec.asset_id.provider_id
                pname = provider.name if provider else "Khác"
                provider_map[pname] = provider_map.get(pname, 0.0) + amt
                cname = rec.category_id.name or "Chi phí khác"
                category_map[cname] = category_map.get(cname, 0.0) + amt
                asset = rec.asset_id
                key = asset.id or ("c-%s" % rec.id)
                row = asset_map.get(key)
                if not row:
                    row = {
                        "id": rec.id,
                        "asset_id": asset.id or False,
                        "name": asset.name or rec.asset_name or "—",
                        "code": asset.code or rec.code or "",
                        "provider": pname,
                        "provider_id": provider.id if provider else False,
                        "amount": 0.0,
                    }
                    asset_map[key] = row
                row["amount"] += amt
                # giữ id phiếu mới nhất để mở form
                row["id"] = rec.id
            return total, month_map, provider_map, category_map, asset_map

        cur_total, cur_months, cur_providers, cur_cats, cur_assets = collect_year(year)
        prev_total, prev_months, _pp, _pc, prev_assets = collect_year(prev_year)

        def delta_pct(cur, prev):
            if prev:
                return round((cur - prev) / abs(prev) * 100, 1)
            if cur:
                return 100.0
            return 0.0

        year_delta = delta_pct(cur_total, prev_total)
        year_delta_amt = cur_total - prev_total
        avg_cur = cur_total / 12.0 if cur_total else 0.0
        avg_prev = prev_total / 12.0 if prev_total else 0.0
        avg_delta = delta_pct(avg_cur, avg_prev)

        month_compare = []
        month_change = []
        for m in range(1, 13):
            cur = cur_months.get(m, 0.0)
            prev = prev_months.get(m, 0.0)
            pct = delta_pct(cur, prev)
            month_compare.append({
                "month": m,
                "label": "T%s" % m,
                "current": cur,
                "prev": prev,
                "delta_pct": pct,
            })
            month_change.append({
                "month": m,
                "label": "T%s" % m,
                "delta_pct": pct,
                "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
            })

        def provider_color(name):
            u = (name or "").upper()
            if "VIETTEL" in u:
                return "#ee0033"
            if "FPT" in u:
                return "#f97316"
            if "VNPT" in u:
                return "#22c55e"
            if "CMC" in u:
                return "#6366f1"
            if "ACT" in u:
                return "#0ea5e9"
            return "#64748b"

        def provider_mark(name):
            u = (name or "").strip()
            if not u:
                return "?"
            parts = u.split()
            if len(parts) >= 2:
                return (parts[0][:1] + parts[1][:1]).upper()
            return u[:2].upper()

        prov_total = sum(cur_providers.values()) or 1.0
        by_provider = [
            {
                "name": name,
                "amount": amt,
                "pct": round(amt * 100 / prov_total, 1),
                "color": provider_color(name),
                "mark": provider_mark(name),
            }
            for name, amt in sorted(cur_providers.items(), key=lambda x: -x[1])
        ]

        structure_colors = ["#6366f1", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#94a3b8"]
        cat_total = sum(cur_cats.values()) or 1.0
        by_structure = []
        for idx, (name, amt) in enumerate(sorted(cur_cats.items(), key=lambda x: -x[1])):
            by_structure.append({
                "id": idx,
                "label": name,
                "amount": amt,
                "pct": round(amt * 100 / cat_total, 1),
                "color": structure_colors[idx % len(structure_colors)],
            })

        rows = []
        all_keys = set(cur_assets) | set(prev_assets)
        for key in all_keys:
            cur_row = cur_assets.get(key) or {}
            prev_row = prev_assets.get(key) or {}
            amount = float(cur_row.get("amount") or 0.0)
            prev_amount = float(prev_row.get("amount") or 0.0)
            if amount <= 0 and prev_amount <= 0:
                continue
            delta = amount - prev_amount
            rows.append({
                "id": cur_row.get("id") or prev_row.get("id"),
                "asset_id": cur_row.get("asset_id") or prev_row.get("asset_id"),
                "name": cur_row.get("name") or prev_row.get("name") or "—",
                "code": cur_row.get("code") or prev_row.get("code") or "",
                "provider": cur_row.get("provider") or prev_row.get("provider") or "—",
                "provider_id": cur_row.get("provider_id") or prev_row.get("provider_id") or False,
                "amount": amount,
                "prev_amount": prev_amount,
                "delta": delta,
                "delta_pct": delta_pct(amount, prev_amount),
            })
        rows.sort(key=lambda r: (-abs(r["delta"]), -r["amount"]))

        providers = self.env["phan.he.provider"].search_read(
            [("active", "=", True)], ["name"], order="name asc"
        )
        regions = sorted({
            m.name for m in self.env["phan.he.mien"].search([("active", "=", True)]) if m.name
        })
        return {
            "year": year,
            "prev_year": prev_year,
            "entity_label": "thiết bị",
            "subtitle": "Phân tích và so sánh chi phí máy chủ, thiết bị theo năm",
            "kpi": {
                "year_total": cur_total,
                "prev_total": prev_total,
                "delta_pct": year_delta,
                "delta_amount": year_delta_amt,
                "avg_month": avg_cur,
                "avg_month_delta_pct": avg_delta,
                "contract_count": len([r for r in rows if r["amount"] > 0]),
            },
            "month_compare": month_compare,
            "month_change": month_change,
            "by_provider": by_provider,
            "by_structure": by_structure,
            "rows": rows,
            "providers": providers,
            "regions": regions,
        }
