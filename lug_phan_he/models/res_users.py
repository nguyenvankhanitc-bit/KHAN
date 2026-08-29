# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _linkq_allowed_hr_store_ids(self):
        """Cửa hàng HR user phụ trách: mã bộ phận, cửa hàng phân hệ, cửa hàng đang quản lý."""
        self.ensure_one()
        Store = self.env["hr.store"].sudo()
        ids = set()
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
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS
