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

    @api.readonly
    def web_read(self, specification: dict[str, dict]) -> list[dict]:
        try:
            return super().web_read(specification)
        except KeyError:
            # Fallback 1: If a related record (e.g. manager_id of another mien/dept)
            # is restricted by ir.rule, read as sudo so display_name/avatar is retrieved safely
            if not self.env.su:
                try:
                    return self.sudo().web_read(specification)
                except KeyError:
                    pass
            # Fallback 2: If a comodel record was deleted from DB (orphaned foreign key),
            # sanitize specification to avoid resolving missing foreign keys:
            clean_spec = dict(specification)
            for fname, fspec in list(clean_spec.items()):
                f = self._fields.get(fname)
                if f and f.type == "many2one" and isinstance(fspec, dict) and "fields" in fspec:
                    clean_spec[fname] = {}
            return super(HrStore, self.sudo()).web_read(clean_spec)

