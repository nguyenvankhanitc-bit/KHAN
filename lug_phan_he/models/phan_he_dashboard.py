# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


MIEN_COLORS = {
    "BAC": "#ef4444",
    "TRUNG": "#22c55e",
    "NAM": "#3b82f6",
    "DTT": "#a855f7",
    "VP": "#64748b",
}
MIEN_FALLBACK_COLORS = ["#ef4444", "#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#0d9488"]


class PhanHeDashboard(models.AbstractModel):
    _name = "phan.he.dashboard"
    _description = "Dashboard quản lý dịch vụ"

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        today = fields.Date.context_today(self)
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())

        year = today.year
        if filters.get("date_from"):
            year = fields.Date.to_date(filters["date_from"]).year
        date_from = fields.Date.to_date(filters.get("date_from") or f"{year}-01-01")
        date_to = fields.Date.to_date(filters.get("date_to") or f"{year}-12-31")
        year = date_from.year

        mien_id = int(filters["mien_id"]) if filters.get("mien_id") else False
        area_id = int(filters["area_id"]) if filters.get("area_id") else False
        emp_id = int(filters["employee_id"]) if filters.get("employee_id") else False

        Service = self.env["phan.he.service"]
        Payment = self.env["phan.he.payment"]
        Mien = self.env["phan.he.mien"]

        s_domain = [("active", "=", True)]
        if mien_id:
            s_domain.append(("mien_id", "=", mien_id))
        if area_id:
            s_domain.append(("area_id", "=", area_id))
        if emp_id:
            s_domain.append(("store_id.responsible_id", "=", emp_id))

        services = Service.search(s_domain)
        miens = Mien.search([("active", "=", True)], order="sequence, name")
        mien_meta = []
        for i, m in enumerate(miens):
            color = MIEN_COLORS.get((m.code or "").upper()) or MIEN_FALLBACK_COLORS[i % len(MIEN_FALLBACK_COLORS)]
            short = (m.name or "").replace("Miền ", "").strip() or m.code or m.name
            mien_meta.append({
                "id": m.id,
                "code": m.code or "",
                "name": m.name or "",
                "short": short,
                "color": color,
            })

        # --- Chi phí tháng theo miền (cước tháng HĐ còn hiệu lực trong tháng) ---
        def services_in_month(recs, m_start, m_end):
            return recs.filtered(
                lambda s: s.state not in ("cancel",)
                and (not s.date_start or s.date_start <= m_end)
                and (not s.date_end or s.date_end >= m_start)
            )

        def cost_by_mien(recs, m_start, m_end):
            """Chi phí tháng = tổng cước tháng các HĐ còn hiệu lực trong tháng."""
            active = services_in_month(recs, m_start, m_end)
            result = {m["id"]: 0.0 for m in mien_meta}
            for svc in active:
                mid = svc.mien_id.id
                if mid in result:
                    result[mid] += svc.contract_amount or 0.0
            return result

        cur_month_start = today.replace(day=1)
        cur_month_end = cur_month_start + relativedelta(months=1, days=-1)
        prev_month_start = cur_month_start - relativedelta(months=1)
        prev_month_end = cur_month_start - relativedelta(days=1)

        cur_map = cost_by_mien(services, cur_month_start, cur_month_end)
        prev_map = cost_by_mien(services, prev_month_start, prev_month_end)

        region_kpis = []
        for m in mien_meta:
            cur = cur_map.get(m["id"], 0.0)
            prev = prev_map.get(m["id"], 0.0)
            region_kpis.append({
                **m,
                "amount": cur,
                "delta": self._delta_pct(cur, prev),
                "title": f"CHI PHÍ {m['name'].upper()}",
            })

        # --- Cảnh báo ---
        soon30 = today + relativedelta(days=30)
        expire_soon_svcs = services.filtered(
            lambda s: s.state == "active" and s.date_end and today <= s.date_end <= soon30
        )
        expired_svcs = services.filtered(
            lambda s: s.date_end and s.date_end < today and s.state not in ("cancel", "liquidated")
        )
        due_soon_pays = Payment.search([
            ("payment_state", "in", ("due_soon", "pending", "not_due")),
            ("service_id", "in", services.ids or [0]),
            ("date_due", "!=", False),
            ("date_due", ">=", today),
            ("date_due", "<=", soon30),
        ])

        def breakdown_services(recs):
            counts = {m["id"]: 0 for m in mien_meta}
            for rec in recs:
                mid = rec.mien_id.id
                if mid in counts:
                    counts[mid] += 1
            return [
                {"id": m["id"], "short": m["short"], "count": counts[m["id"]], "color": m["color"]}
                for m in mien_meta
            ]

        def breakdown_payments(pays):
            counts = {m["id"]: 0 for m in mien_meta}
            for pay in pays:
                mid = pay.service_id.mien_id.id
                if mid in counts:
                    counts[mid] += 1
            return [
                {"id": m["id"], "short": m["short"], "count": counts[m["id"]], "color": m["color"]}
                for m in mien_meta
            ]

        alert_cards = [
            {
                "id": "expire_soon",
                "level": "warn",
                "icon": "fa-exclamation-triangle",
                "title": "SẮP HẾT HẠN (30 Ngày)",
                "count": len(expire_soon_svcs),
                "unit": "Hợp đồng",
                "breakdown": breakdown_services(expire_soon_svcs),
                "action": "lug_phan_he.action_phan_he_service_expire_soon",
            },
            {
                "id": "expired",
                "level": "danger",
                "icon": "fa-ban",
                "title": "ĐÃ HẾT HẠN / QUÁ HẠN",
                "count": len(expired_svcs),
                "unit": "Hợp đồng",
                "breakdown": breakdown_services(expired_svcs),
                "action": "lug_phan_he.action_phan_he_service_expired",
            },
            {
                "id": "pay_due_soon",
                "level": "info",
                "icon": "fa-bell",
                "title": "SẮP ĐẾN HẠN THANH TOÁN",
                "count": len(due_soon_pays),
                "unit": "Hợp đồng",
                "breakdown": breakdown_payments(due_soon_pays),
                "action": "lug_phan_he.action_phan_he_payment_due_soon",
            },
        ]

        # --- Biểu đồ 12 tháng (theo năm filter) ---
        trend_months = []
        series = {m["id"]: [] for m in mien_meta}
        totals_row = []
        year_totals = {m["id"]: 0.0 for m in mien_meta}
        grand_total = 0.0

        for month in range(1, 13):
            m_start = fields.Date.to_date(f"{year}-{month:02d}-01")
            m_end = m_start + relativedelta(months=1, days=-1)
            cmap = cost_by_mien(services, m_start, m_end)
            month_total = sum(cmap.values())
            for m in mien_meta:
                val = cmap.get(m["id"], 0.0)
                series[m["id"]].append(val)
                year_totals[m["id"]] += val
            grand_total += month_total

            if month < today.month and year == today.year:
                status = "done"
                status_label = "Hoàn tất"
            elif month == today.month and year == today.year:
                status = "current"
                status_label = "Tháng hiện tại"
            elif year < today.year:
                status = "done"
                status_label = "Hoàn tất"
            elif year > today.year:
                status = "forecast"
                status_label = "Dự kiến"
            else:
                status = "forecast"
                status_label = "Dự kiến"

            totals_row.append({
                "month": month,
                "label": f"Tháng {month:02d}",
                "is_current": status == "current",
                "amounts": [
                    {"mien_id": m["id"], "amount": cmap.get(m["id"], 0.0), "color": m["color"]}
                    for m in mien_meta
                ],
                "total": month_total,
                "status": status,
                "status_label": status_label,
            })
            trend_months.append(f"T{month:02d}")

        max_trend = max(
            (v for vals in series.values() for v in vals),
            default=1,
        ) or 1

        trend_series = [
            {
                "id": m["id"],
                "name": m["name"],
                "short": m["short"],
                "color": m["color"],
                "values": series[m["id"]],
            }
            for m in mien_meta
        ]

        # Donut: cơ cấu tháng hiện tại
        cur_total = sum(cur_map.values()) or 1.0
        cost_structure = [
            {
                "id": m["id"],
                "name": m["name"],
                "short": m["short"],
                "amount": cur_map.get(m["id"], 0.0),
                "color": m["color"],
                "pct": round((cur_map.get(m["id"], 0.0) / cur_total) * 100, 1),
            }
            for m in mien_meta
            if cur_map.get(m["id"], 0.0) > 0
        ]
        if not cost_structure:
            cost_structure = [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "short": m["short"],
                    "amount": 0.0,
                    "color": m["color"],
                    "pct": 0.0,
                }
                for m in mien_meta
            ]

        # Filter options
        miens_opts = [{"id": m["id"], "name": m["name"]} for m in mien_meta]
        area_domain = [("active", "=", True)]
        if mien_id:
            area_domain.append(("mien_id", "=", mien_id))
        areas = [
            {"id": a.id, "name": a.name, "mien_id": a.mien_id.id}
            for a in self.env["phan.he.area"].search(area_domain, order="name")
        ]
        employees = self.env["hr.employee"].search_read(
            [("id", "in", self.env["phan.he.store"].search([]).mapped("responsible_id").ids)],
            ["id", "name"],
            order="name",
        )

        return {
            "user_name": self.env.user.name,
            "role_label": self._role_label(),
            "updated_at": now.strftime("%H:%M %d/%m/%Y"),
            "year": year,
            "current_month": today.month if year == today.year else 0,
            "date_from": fields.Date.to_string(date_from),
            "date_to": fields.Date.to_string(date_to),
            "mien_id": mien_id or "",
            "area_id": area_id or "",
            "employee_id": emp_id or "",
            "miens": miens_opts,
            "areas": areas,
            "employees": employees,
            "mien_meta": mien_meta,
            "region_kpis": region_kpis,
            "alert_cards": alert_cards,
            "alert_count": (
                len(expire_soon_svcs) + len(expired_svcs) + len(due_soon_pays)
            ),
            "expire_soon": len(expire_soon_svcs),
            "overdue_contract": len(expired_svcs),
            "trend_months": trend_months,
            "trend_series": trend_series,
            "max_trend": max_trend,
            "cost_structure": cost_structure,
            "monthly_table": totals_row,
            "year_totals": [
                {"mien_id": m["id"], "amount": year_totals[m["id"]], "color": m["color"]}
                for m in mien_meta
            ],
            "year_grand_total": grand_total,
            "currency_symbol": (
                self.env.ref("base.VND", raise_if_not_found=False)
                or self.env["res.currency"].search([("name", "=", "VND")], limit=1)
                or self.env.company.currency_id
            ).symbol or "đ",
        }

    @api.model
    def _delta_pct(self, current, previous):
        if not previous:
            return 100.0 if current else 0.0
        return round(((current - previous) / abs(previous)) * 100, 1)

    @api.model
    def _role_label(self):
        user = self.env.user
        if user.has_group("lug_phan_he.group_phan_he_admin"):
            return "Administrator"
        if user.has_group("lug_phan_he.group_phan_he_service_manager"):
            return "Service Manager"
        if user.has_group("lug_phan_he.group_phan_he_regional"):
            return "Regional Manager"
        if user.has_group("lug_phan_he.group_phan_he_area"):
            return "Area Manager"
        if user.has_group("lug_phan_he.group_phan_he_staff"):
            return "Staff"
        return "Viewer"
