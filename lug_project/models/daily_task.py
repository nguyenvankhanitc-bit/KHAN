# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DailyTask(models.Model):
    _inherit = "daily.task"

    lug_origin_project_id = fields.Many2one(
        "project.project",
        string="Dự án gốc",
        ondelete="set null",
        copy=False,
        index=True,
    )
    lug_origin_project_task_id = fields.Many2one(
        "project.task",
        string="Công việc dự án gốc",
        ondelete="set null",
        copy=False,
        index=True,
    )
    lug_origin_stage_task_id = fields.Many2one(
        "project.stage.task",
        string="Công việc giai đoạn gốc",
        ondelete="set null",
        copy=False,
        index=True,
    )
