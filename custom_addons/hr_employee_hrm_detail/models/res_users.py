# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .hr_employee_access import MIEN_BND


class ResUsers(models.Model):
    _inherit = "res.users"

    hr_officer_mien_scope = fields.Selection(
        selection=[
            ("vp", "VP"),
            ("bnd", "Bắc/Nam/ĐTT"),
            ("self", "Self only"),
        ],
        compute="_compute_hr_officer_mien_scope",
        store=True,
    )

    @api.depends(
        "employee_id.mien",
        "employee_id.ma_bo_phan_id.mien",
        "group_ids",
    )
    def _compute_hr_officer_mien_scope(self):
        for user in self:
            if user._is_superuser() or user.has_group("hr.group_hr_manager"):
                user.hr_officer_mien_scope = False
                continue
            if not user.has_group("hr.group_hr_user"):
                user.hr_officer_mien_scope = False
                continue
            emp = user.employee_id
            mien = False
            if emp:
                mien = emp.mien or (emp.ma_bo_phan_id.mien if emp.ma_bo_phan_id else False)
            if mien == "VP":
                user.hr_officer_mien_scope = "vp"
            elif mien in MIEN_BND:
                user.hr_officer_mien_scope = "bnd"
            else:
                user.hr_officer_mien_scope = "self"

    def write(self, vals):
        res = super().write(vals)
        if "group_ids" in vals:
            self.env.registry.clear_cache()
        return res
