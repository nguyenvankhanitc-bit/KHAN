# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _linkq_store_ids_from_permission_matrix(self):
        """Cửa hàng từ tab Phân quyền Cửa hàng (Lịch ca & Nhân sự)."""
        self.ensure_one()
        Store = self.env["hr.store"].sudo()
        lines = self.env["linkq.store.permission.line"].sudo().search(
            [
                ("user_id", "=", self.id),
                ("can_view", "=", True),
                ("permission_group_id.active", "=", True),
            ]
        )
        ids = set()
        for line in lines:
            if line.type_scope == "all":
                return set(Store.search([]).ids)
            if line.type_scope == "region" and line.region:
                ids.update(Store.search([("mien", "=", line.region)]).ids)
            elif line.type_scope == "custom":
                ids.update(line.store_ids.ids)
        return ids

    def _linkq_allowed_hr_store_ids(self):
        """Cửa hàng được xem: ma trận phân quyền + mã bộ phận / cửa hàng phân hệ."""
        self.ensure_one()
        Store = self.env["hr.store"].sudo()
        ids = set(self._linkq_store_ids_from_permission_matrix())
        emp = self.env["hr.employee"].sudo().search(
            [("user_id", "=", self.id)], limit=1
        )
        if emp:
            code_rec = emp.ma_bo_phan_id if "ma_bo_phan_id" in emp._fields else False
            if code_rec:
                store = getattr(code_rec, "store_id", False)
                if store:
                    ids.add(store.id)
                elif code_rec._name == "hr.store":
                    ids.add(code_rec.id)
            code = (emp.ma_bo_phan or "").strip() if "ma_bo_phan" in emp._fields else ""
            if code:
                found = Store.search([("code", "=ilike", code)], limit=1)
                if found:
                    ids.add(found.id)
            if "store_id" in emp._fields and emp.store_id:
                ids.add(emp.store_id.id)
            if "manager_id" in Store._fields:
                ids.update(Store.search([("manager_id", "=", emp.id)]).ids)
        for ph_store in self.sudo().phan_he_store_ids:
            domain = []
            if ph_store.code:
                domain = [("code", "=ilike", ph_store.code)]
            if domain:
                found = Store.search(domain, limit=1)
                if found:
                    ids.add(found.id)
        return list(ids)

    linkq_store_perm_line_ids = fields.One2many(
        "linkq.store.permission.line",
        "user_id",
        string="Phân quyền cửa hàng LinkQ",
    )

    @api.depends(
        "phan_he_store_ids",
        "linkq_store_perm_line_ids",
        "linkq_store_perm_line_ids.can_view",
        "linkq_store_perm_line_ids.type_scope",
        "linkq_store_perm_line_ids.region",
        "linkq_store_perm_line_ids.store_ids",
        "linkq_store_perm_line_ids.permission_group_id",
        "linkq_store_perm_line_ids.permission_group_id.active",
    )
    def _compute_linkq_store(self):
        for user in self:
            ids = user._linkq_allowed_hr_store_ids() if user.id else []
            stores = self.env["hr.store"].sudo().browse(ids)
            user.linkq_store_ids = stores
            user.store_id = stores[:1]
            user.branch_id = stores[:1]

    store_id = fields.Many2one(
        "hr.store",
        string="Cửa hàng",
        compute="_compute_linkq_store",
    )
    branch_id = fields.Many2one(
        "hr.store",
        string="Chi nhánh",
        compute="_compute_linkq_store",
    )
    linkq_store_ids = fields.Many2many(
        "hr.store",
        "res_users_linkq_store_rel",
        "user_id",
        "store_id",
        compute="_compute_linkq_store",
        store=True,
        compute_sudo=True,
        string="Cửa hàng được phép",
    )

    phan_he_mien_ids = fields.Many2many(
        "phan.he.mien",
        "phan_he_user_mien_rel",
        "user_id",
        "mien_id",
        string="Miền phụ trách",
    )
    phan_he_area_ids = fields.Many2many(
        "phan.he.area",
        "phan_he_user_area_rel",
        "user_id",
        "area_id",
        string="Khu vực phụ trách",
    )
    phan_he_store_ids = fields.Many2many(
        "phan.he.store",
        "phan_he_user_store_rel",
        "user_id",
        "store_id",
        string="Cửa hàng phụ trách",
        help="Nếu có thì giới hạn đúng các cửa hàng này (ưu tiên cao hơn khu vực).",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "phan_he_mien_ids", "phan_he_area_ids", "phan_he_store_ids",
            "store_id", "branch_id", "linkq_store_ids",
        ]

    def _register_hook(self):
        super()._register_hook()
        try:
            users = self.env["linkq.store.permission.line"].sudo().search([]).mapped("user_id")
            if users:
                users._compute_linkq_store()
        except Exception:
            pass

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS
