# -*- coding: utf-8 -*-

from odoo import fields, models


class LugProjectCriterion(models.Model):
    _name = "lug.project.criterion"
    _description = "Tiêu chí hoàn thành dự án"
    _order = "sequence, id"

    project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Tiêu chí", required=True)
    is_required = fields.Boolean(string="Bắt buộc", default=True)
    is_done = fields.Boolean(string="Đã đạt", default=False)
