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

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("lug_sync_lock"):
            for rec in self:
                origin = rec.lug_origin_project_task_id
                if not origin or not origin.exists():
                    continue

                origin_vals = {}
                if "state" in vals:
                    new_state = vals["state"]
                    if new_state == "done":
                        origin_vals["lug_status"] = "done"
                        origin_vals["lug_done_date"] = rec.date_done or fields.Date.context_today(rec)
                    elif new_state == "in_progress":
                        origin_vals["lug_status"] = "progress"
                    elif new_state == "not_started":
                        origin_vals["lug_status"] = "todo"

                if "deadline" in vals and vals["deadline"]:
                    origin_vals["date_deadline"] = vals["deadline"]

                if origin_vals:
                    origin.with_context(lug_sync_lock=True).write(origin_vals)
                    # Sync to linked To-Do task if present
                    todo = origin.lug_todo_task_id
                    if todo and todo.exists():
                        todo_vals = {}
                        if "lug_status" in origin_vals:
                            todo_vals["state"] = (
                                "1_done" if origin_vals["lug_status"] == "done" else "01_in_progress"
                            )
                        if "date_deadline" in origin_vals:
                            todo_vals["date_deadline"] = origin_vals["date_deadline"]
                        if todo_vals:
                            todo.with_context(lug_sync_lock=True).write(todo_vals)
        return res
