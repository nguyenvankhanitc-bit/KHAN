# -*- coding: utf-8 -*-

from odoo import fields, models


class LugAppAnnouncement(models.Model):
    _name = "lug.app.announcement"
    _description = "Thông báo nội bộ App Center"
    _order = "sequence, id desc"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    body = fields.Text(translate=True)
    announce_date = fields.Date(string="Ngày", default=fields.Date.context_today)
    tag = fields.Char(string="Nhãn", translate=True)
    tag_type = fields.Selection(
        [
            ("important", "Quan trọng"),
            ("warning", "Cảnh báo"),
            ("info", "Thông tin"),
            ("event", "Sự kiện"),
        ],
        default="info",
        required=True,
    )
