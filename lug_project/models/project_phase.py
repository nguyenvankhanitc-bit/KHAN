# -*- coding: utf-8 -*-

from odoo import fields, models


class LugProjectPhase(models.Model):
    _name = "lug.project.phase"
    _description = "Giai doan du an"
    _order = "sequence, code, id"

    name = fields.Char(string="Tên giai đoạn", required=True, translate=True)
    code = fields.Char(string="Mã", required=True, index=True)
    sequence = fields.Integer(default=10)
    color = fields.Char(string="Màu", default="#7c3aed")
    active = fields.Boolean(default=True)
    _lug_phase_code_uniq = models.Constraint(
        "unique(code)",
        "Mã giai đoạn phải duy nhất.",
    )
