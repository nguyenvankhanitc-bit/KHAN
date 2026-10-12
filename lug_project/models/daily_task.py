# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DailyTask(models.Model):
    _inherit = "daily.task"

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

    def _register_hook(self):
        super()._register_hook()
        try:
            self.env.cr.execute("ALTER TABLE daily_task ADD COLUMN IF NOT EXISTS lug_origin_project_task_id INTEGER")
            self.env.cr.execute("ALTER TABLE daily_task ADD COLUMN IF NOT EXISTS lug_origin_stage_task_id INTEGER")
        except Exception:
            pass
