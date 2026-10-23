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

        cost_domain = [("active", "=", True), ("asset_id", "in", assets.ids or [0])]
        if filters.get("provider_id"):
            cost_domain.append(("provider_id", "=", int(filters["provider_id"])))

        def sum_costs(d0, d1):
            recs = Cost.search(cost_domain + [
                ("date_start", "<=", d1),
                "|", ("date_end", "=", False), ("date_end", ">=", d0),
            ])
            # Ưu tiên thực tế nếu có, không thì dự kiến
            total = 0.0
            for c in recs:
                if c.amount_untaxed_actual:
                    total += float(c.amount_untaxed_actual or 0) + float(c.amount_tax or 0)
                else:
                    total += float(c.amount_total or 0)
            return total

        month_total = sum_costs(m_start, m_end)
        prev_total = sum_costs(prev_start, prev_end)
        year_total = sum_costs(y_start, m_end)
        month_delta = 0.0
        if prev_total:
            month_delta = round((month_total - prev_total) / abs(prev_total) * 100, 1)
        elif month_total:
            month_delta = 100.0

        soon30 = today + relativedelta(days=30)
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

        # Chi phí 12 tháng
        month_series = []
        for mo in range(1, 13):
            s = fields.Date.to_date("%04d-%02d-01" % (year, mo))
            e = s + relativedelta(months=1, days=-1)
            if year == today.year and mo > today.month:
                amt = 0.0
            else:
                amt = sum_costs(s, e)
            month_series.append({"month": mo, "label": "T%s" % mo, "amount": amt})

        # Theo loại tài sản
        by_type = []
        types = self.env["phan.he.it.asset.type"].search([("active", "=", True)])
        type_total = 0.0
        for t in types:
            t_assets = assets.filtered(lambda a, tid=t.id: a.asset_type_id.id == tid)
            t_costs = Cost.search(cost_domain + [("asset_id", "in", t_assets.ids or [0])])
            amt = 0.0
            for c in t_costs:
                if c.date_start and c.date_start > m_end:
                    continue
                if c.date_end and c.date_end < m_start:
                    continue
                amt += float(c.amount_total or 0)
            if amt > 0 or t_assets:
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

        # Theo miền
        by_mien = []
        miens = self.env["phan.he.mien"].search([("active", "=", True)])
        mien_total = 0.0
        for m in miens:
            m_assets = assets.filtered(lambda a, mid=m.id: a.mien_id.id == mid)
            m_costs = Cost.search(cost_domain + [("asset_id", "in", m_assets.ids or [0])])
            amt = 0.0
            for c in m_costs:
                if c.date_end and c.date_end < m_start:
                    continue
                if c.date_start and c.date_start > m_end:
                    continue
                amt += float(c.amount_total or 0)
            by_mien.append({
                "id": m.id,
                "code": m.code or "",
                "name": m.name,
                "amount": amt,
            })
            mien_total += amt
        for row in by_mien:
            row["pct"] = round(row["amount"] * 100 / mien_total, 1) if mien_total else 0.0

        # Việc cần xử lý
        todo = []
        for c in Cost.search(cost_domain + [
            "|",
            "&", ("date_end", ">=", today), ("date_end", "<=", soon30),
            "|",
            ("date_end", "<", today),
            ("payment_state", "in", ("confirm", "pending", "overdue")),
        ], limit=50, order="date_end asc"):
            kind = "expiring"
            if c.date_end and c.date_end < today:
                kind = "overdue"
            elif c.payment_state in ("confirm", "pending"):
                kind = "payment"
            todo.append({
                "id": c.id,
                "model": "phan.he.it.cost",
                "asset": c.asset_id.name,
                "asset_code": c.asset_id.code,
                "category": c.category_id.name,
                "date": fields.Date.to_string(c.date_end) if c.date_end else "",
                "amount": c.amount_total,
                "state": c.renewal_state,
                "payment_state": c.payment_state,
                "responsible": c.responsible_id.name or "",
                "kind": kind,
            })
        for t in Ticket.search([
            ("asset_id", "in", assets.ids or [0]),
            ("state", "in", ("open", "progress")),
            ("ticket_type", "=", "incident"),
        ], limit=20):
            todo.append({
                "id": t.id,
                "model": "phan.he.it.ticket",
                "asset": t.asset_id.name,
                "asset_code": t.asset_id.code,
                "category": "Sự cố",
                "date": fields.Datetime.to_string(t.date_reported)[:10] if t.date_reported else "",
                "amount": t.cost_amount or 0,
                "state": t.state,
                "payment_state": "",
                "responsible": t.responsible_id.name or "",
                "kind": "incident",
            })

        return {
            "updated_at": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ).strftime("%H:%M %d/%m/%Y"),
            "year": year,
            "month": month,
            "kpi": {
                "asset_total": len(assets),
                "asset_active": active_n,
                "asset_inactive": retired_n,
                "month_cost": month_total,
                "month_delta": month_delta,
                "year_cost": year_total,
                "year_budget": 0.0,
                "expiring": expiring,
                "overdue": overdue,
                "confirm": confirm,
            },
            "month_series": month_series,
            "by_type": by_type,
            "by_mien": by_mien,
            "todo": todo,
            "filters": {
                "miens": [{"id": m.id, "name": m.name} for m in miens],
                "types": [{"id": t.id, "name": t.name} for t in types],
                "providers": self.env["phan.he.provider"].search_read(
                    [("active", "=", True)], ["name"], order="name", limit=200
                ),
            },
        }
