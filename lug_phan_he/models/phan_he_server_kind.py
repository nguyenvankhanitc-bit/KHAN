# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import api, fields, models


class PhanHeServerKind(models.Model):
    _name = "phan.he.server.kind"
    _description = "Loại máy chủ"
    _order = "sequence, name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(string="Loại máy chủ", required=True)
    code = fields.Char(string="Mã", required=True)
    sequence = fields.Integer(default=10)
    color = fields.Char(string="Màu", help="Ma mau hex, vi du #2563eb")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "unique(code)",
        "Mã loại máy chủ phải duy nhất.",
    )

    @api.model
    def _code_from_name(self, name):
        text = unicodedata.normalize("NFKD", name or "")
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
        return text or "loai"

    @api.onchange("name")
    def _onchange_name_set_code(self):
        if self.name and not self.code:
            self.code = self._code_from_name(self.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not (vals.get("code") or "").strip():
                base = self._code_from_name(vals.get("name"))
                code = base
                index = 2
                while self.search_count([("code", "=", code)]):
                    code = "%s_%s" % (base, index)
                    index += 1
                vals["code"] = code
        return super().create(vals_list)
