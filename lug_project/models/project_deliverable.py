# -*- coding: utf-8 -*-

from odoo import fields, models


class LugProjectDeliverable(models.Model):
    _name = "lug.project.deliverable"
    _description = "Sản phẩm bàn giao"
    _order = "sequence, id"

    project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Deliverable", required=True)
    description = fields.Text(string="Mô tả")
    deadline = fields.Date(string="Hạn")
    user_id = fields.Many2one(
        "res.users",
        string="Người nhận",
        domain="[('share', '=', False)]",
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        [
            ("todo", "Chưa giao"),
            ("progress", "Đang làm"),
            ("done", "Hoàn thành"),
        ],
        string="Trạng thái",
        default="todo",
        required=True,
    )
