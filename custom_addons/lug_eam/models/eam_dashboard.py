# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class EamDashboard(models.AbstractModel):
    """API số liệu Dashboard / Báo cáo EAM (Giai đoạn 7)."""

    _name = "eam.dashboard"
    _description = "Dashboard Quản lý tài sản"

    @api.model
    def get_dashboard_data(self):
        Equipment = self.env["maintenance.equipment"]
        Request = self.env["maintenance.request"]
        company = self.env.company
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        active_domain = [("eam_state", "!=", "disposed")]
        if company:
            active_domain.append(("company_id", "=", company.id))

        def _count(extra):
            return Equipment.search_count(active_domain + extra)

        total = _count([])
        in_use = _count([("eam_state", "=", "in_use")])
        in_stock = _count([("eam_state", "=", "in_stock")])
        maintenance = _count([("eam_state", "in", ("maintenance", "broken"))])
        broken = _count([("eam_state", "=", "broken")])
        warranty_expired = _count(
            [
                ("warranty_state", "=", "expired"),
                ("eam_state", "not in", ("disposed", "draft")),
            ]
        )
        warranty_expiring = _count(
            [
                ("warranty_state", "=", "expiring"),
                ("eam_state", "not in", ("disposed", "draft")),
            ]
        )
        draft = Equipment.search_count(
            [("eam_state", "=", "draft"), ("company_id", "=", company.id)]
        )

        req_domain = [("company_id", "=", company.id)]
        done_domain = req_domain + [("stage_id.done", "=", True)]
        open_wo = Request.search_count(
            req_domain + [("stage_id.done", "=", False), ("archive", "=", False)]
        )

        cost_month = self._sum_maint_cost(
            done_domain
            + [
                ("close_date", ">=", month_start),
                ("close_date", "<=", today),
            ]
        )
        cost_ytd = self._sum_maint_cost(
            done_domain
            + [
                ("close_date", ">=", year_start),
                ("close_date", "<=", today),
            ]
        )
        cost_total = self._sum_maint_cost(done_domain)

        by_state = self._group_count(
            Equipment,
            active_domain,
            "eam_state",
            labels=dict(Equipment._fields["eam_state"].selection),
        )
        by_site = self._group_count(
            Equipment,
            active_domain + [("eam_state", "=", "in_use")],
            "site_location_id",
            empty_label=self.env._("Chưa gán cửa hàng"),
            limit=12,
        )
        by_department = self._group_count(
            Equipment,
            active_domain + [("eam_state", "=", "in_use")],
            "department_id",
            empty_label=self.env._("Chưa gán phòng ban"),
            limit=12,
        )
        by_owner = self._group_count(
            Equipment,
            active_domain + [("eam_state", "=", "in_use")],
            "owner_employee_id",
            empty_label=self.env._("Chưa gán người dùng"),
            limit=12,
        )

        cost_by_month = self._maint_cost_by_month(company.id, months=6)

        currency = company.currency_id
        return {
            "company_name": company.name or "",
            "user_name": self.env.user.name or "",
            "currency_symbol": currency.symbol or "",
            "currency_id": currency.id,
            "as_of": fields.Date.to_string(today),
            "kpi": {
                "total": total,
                "in_use": in_use,
                "in_stock": in_stock,
                "maintenance": maintenance,
                "broken": broken,
                "warranty_expired": warranty_expired,
                "warranty_expiring": warranty_expiring,
                "draft": draft,
                "open_wo": open_wo,
                "cost_month": cost_month,
                "cost_ytd": cost_ytd,
                "cost_total": cost_total,
            },
            "charts": {
                "by_state": by_state,
                "by_site": by_site,
                "by_department": by_department,
                "by_owner": by_owner,
                "cost_by_month": cost_by_month,
            },
        }

    @api.model
    def action_open_kpi(self, kpi_key):
        """Drill-down từ thẻ KPI → list đã lọc."""
        company = self.env.company
        base = [("company_id", "=", company.id)]
        Asset = "maintenance.equipment"
        Request = "maintenance.request"

        mapping = {
            "total": {
                "name": self.env._("Tổng tài sản"),
                "res_model": Asset,
                "domain": base + [("eam_state", "!=", "disposed")],
            },
            "in_use": {
                "name": self.env._("Tài sản đang sử dụng"),
                "res_model": Asset,
                "domain": base + [("eam_state", "=", "in_use")],
            },
            "in_stock": {
                "name": self.env._("Tài sản trong kho"),
                "res_model": Asset,
                "domain": base + [("eam_state", "=", "in_stock")],
            },
            "maintenance": {
                "name": self.env._("Tài sản bảo trì / hỏng"),
                "res_model": Asset,
                "domain": base + [("eam_state", "in", ("maintenance", "broken"))],
            },
            "warranty_expired": {
                "name": self.env._("Tài sản hết bảo hành"),
                "res_model": Asset,
                "domain": base
                + [
                    ("warranty_state", "=", "expired"),
                    ("eam_state", "not in", ("disposed", "draft")),
                ],
            },
            "warranty_expiring": {
                "name": self.env._("Tài sản sắp hết bảo hành"),
                "res_model": Asset,
                "domain": base
                + [
                    ("warranty_state", "=", "expiring"),
                    ("eam_state", "not in", ("disposed", "draft")),
                ],
            },
            "open_wo": {
                "name": self.env._("Work Order đang mở"),
                "res_model": Request,
                "domain": base + [("stage_id.done", "=", False), ("archive", "=", False)],
                "view_mode": "kanban,list,form",
            },
            "cost_month": {
                "name": self.env._("WO hoàn thành tháng này"),
                "res_model": Request,
                "domain": self._cost_month_domain(company.id),
                "view_mode": "list,form",
            },
            "cost_ytd": {
                "name": self.env._("WO hoàn thành năm nay"),
                "res_model": Request,
                "domain": self._cost_ytd_domain(company.id),
                "view_mode": "list,form",
            },
            "by_site": {
                "name": self.env._("Tài sản theo cửa hàng"),
                "res_model": Asset,
                "domain": base + [("eam_state", "=", "in_use")],
                "context": {"group_by": "site_location_id"},
            },
            "by_department": {
                "name": self.env._("Tài sản theo phòng ban"),
                "res_model": Asset,
                "domain": base + [("eam_state", "=", "in_use")],
                "context": {"group_by": "department_id"},
            },
            "by_owner": {
                "name": self.env._("Tài sản theo người sử dụng"),
                "res_model": Asset,
                "domain": base + [("eam_state", "=", "in_use")],
                "context": {"group_by": "owner_employee_id"},
            },
        }
        conf = mapping.get(kpi_key) or mapping["total"]
        action = {
            "type": "ir.actions.act_window",
            "name": conf["name"],
            "res_model": conf["res_model"],
            "view_mode": conf.get("view_mode", "list,kanban,form"),
            "domain": conf["domain"],
            "context": conf.get("context", {}),
            "target": "current",
        }
        if conf["res_model"] == Asset:
            form = self.env.ref("lug_eam.view_eam_asset_form_360", raise_if_not_found=False)
            if form:
                action["views"] = [
                    (False, "list"),
                    (False, "kanban"),
                    (form.id, "form"),
                ]
        return action

    def _cost_month_domain(self, company_id):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        return [
            ("company_id", "=", company_id),
            ("stage_id.done", "=", True),
            ("close_date", ">=", month_start),
            ("close_date", "<=", today),
        ]

    def _cost_ytd_domain(self, company_id):
        today = fields.Date.context_today(self)
        year_start = today.replace(month=1, day=1)
        return [
            ("company_id", "=", company_id),
            ("stage_id.done", "=", True),
            ("close_date", ">=", year_start),
            ("close_date", "<=", today),
        ]

    def _sum_maint_cost(self, domain):
        Request = self.env["maintenance.request"]
        groups = Request.read_group(domain, ["eam_total_cost:sum"], [])
        if not groups:
            return 0.0
        return float(groups[0].get("eam_total_cost") or 0.0)

    def _group_count(self, Model, domain, field_name, labels=None, empty_label="—", limit=None):
        groups = Model.read_group(domain, [field_name], [field_name], lazy=False)
        rows = []
        for g in groups:
            key = g.get(field_name)
            count = g.get(field_name + "_count") or g.get("__count") or 0
            if isinstance(key, tuple):
                label = key[1] or empty_label
                res_id = key[0]
            elif key is False or key is None:
                label = empty_label
                res_id = False
            else:
                label = (labels or {}).get(key, str(key))
                res_id = key
            rows.append({"id": res_id, "label": label, "count": int(count)})
        rows.sort(key=lambda r: r["count"], reverse=True)
        if limit:
            rows = rows[:limit]
        return {
            "labels": [r["label"] for r in rows],
            "values": [r["count"] for r in rows],
            "rows": rows,
        }

    def _maint_cost_by_month(self, company_id, months=6):
        today = fields.Date.context_today(self)
        start = (today.replace(day=1) - relativedelta(months=months - 1))
        Request = self.env["maintenance.request"]
        domain = [
            ("company_id", "=", company_id),
            ("stage_id.done", "=", True),
            ("close_date", ">=", start),
            ("close_date", "<=", today),
        ]
        groups = Request.read_group(
            domain,
            ["eam_total_cost:sum", "close_date"],
            ["close_date:month"],
            lazy=False,
        )
        # Prefer ordered calendar months for stable axis
        labels = []
        values = []
        cursor = start
        while cursor <= today.replace(day=1):
            month_end = cursor + relativedelta(months=1, days=-1)
            month_domain = [
                ("company_id", "=", company_id),
                ("stage_id.done", "=", True),
                ("close_date", ">=", cursor),
                ("close_date", "<=", min(month_end, today)),
            ]
            labels.append("%02d/%04d" % (cursor.month, cursor.year))
            values.append(self._sum_maint_cost(month_domain))
            cursor = cursor + relativedelta(months=1)
        return {"labels": labels, "values": values}
