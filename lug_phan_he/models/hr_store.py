# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrStore(models.Model):
    _inherit = "hr.store"

    asm_email = fields.Char(string="Email ASM")

    def _linkq_employee_group_label(self):
        self.ensure_one()
        code = (self.code or self.name or "").strip()
        extra = ""
        if self.manager_id:
            extra = (self.manager_id.name or "").strip()
        elif self.name and code and self.name.strip() != code:
            extra = self.name.strip()
        if extra and extra != code:
            return f"{code} - {extra}"
        return code or "Cửa hàng"
