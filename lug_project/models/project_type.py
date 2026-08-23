# -*- coding: utf-8 -*-

from odoo import fields, models


class LugProjectType(models.Model):
    _name = "lug.project.type"
    _description = "Loại dự án"
    _order = "sequence, name"

    name = fields.Char(string="Tên loại", required=True, translate=True)
    code = fields.Char(string="Mã", index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string="Mô tả")
