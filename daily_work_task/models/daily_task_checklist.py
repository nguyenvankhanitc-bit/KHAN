# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DailyTaskChecklistItem(models.Model):
    _name = "daily.task.checklist.item"
    _description = "Checklist công việc"
    _order = "sequence, id"

    task_id = fields.Many2one(
        "daily.task",
        string="Công việc",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Hạng mục", required=True)
    done = fields.Boolean(string="Hoàn thành", default=False)
    sequence = fields.Integer(string="Thứ tự", default=10)
