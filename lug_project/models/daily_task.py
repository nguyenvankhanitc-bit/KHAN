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
    lug_project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        compute="_compute_lug_project_id",
        store=True,
        index=True,
    )

    @api.depends(
        "lug_origin_project_id",
        "lug_origin_stage_task_id",
        "lug_origin_stage_task_id.stage_id.project_id",
        "lug_origin_project_task_id",
        "lug_origin_project_task_id.project_id",
    )
    def _compute_lug_project_id(self):
        for rec in self:
            rec.lug_project_id = (
                rec.lug_origin_project_id
                or (rec.lug_origin_stage_task_id and rec.lug_origin_stage_task_id.project_id)
                or (rec.lug_origin_project_task_id and rec.lug_origin_project_task_id.project_id)
                or False
            )

    @api.model
    def action_open_my_project_tasks(self):
        """Mở danh sách công việc thuộc các dự án của nhân viên hiện tại, gom nhóm theo Dự án."""
        emp = self._my_hr_employee() if hasattr(self, "_my_hr_employee") else False
        project_cond = [
            "|",
            ("lug_project_id", "!=", False),
            ("lug_origin_project_id", "!=", False),
        ]
        if emp:
            user_cond = [
                "|",
                ("assignee_id.employee_id", "=", emp.id),
                "|",
                ("assignee_user_id", "=", self.env.user.id),
                ("assignee_id.employee_id.user_id", "=", self.env.user.id),
            ]
        else:
            user_cond = [
                "|",
                ("assignee_user_id", "=", self.env.user.id),
                ("assignee_id.employee_id.user_id", "=", self.env.user.id),
            ]
        domain = project_cond + user_cond

        list_view = self.env.ref("lug_project.view_daily_task_project_tree", raise_if_not_found=False)
        kanban_view = self.env.ref("lug_project.view_daily_task_project_kanban", raise_if_not_found=False)
        form_view = self.env.ref("daily_work_task.view_daily_task_form", raise_if_not_found=False)

        views = []
        if list_view:
            views.append((list_view.id, "list"))
        if kanban_view:
            views.append((kanban_view.id, "kanban"))
        if form_view:
            views.append((form_view.id, "form"))

        search_view = self.env.ref("lug_project.view_daily_task_project_search", raise_if_not_found=False)

        return {
            "name": "Dự án",
            "type": "ir.actions.act_window",
            "res_model": "daily.task",
            "view_mode": "list,kanban,form",
            "views": views or [[False, "list"], [False, "kanban"], [False, "form"]],
            "domain": domain,
            "context": {
                "default_group_by": "lug_project_id",
                "search_default_group_by_project": 1,
                "search_default_filter_open": 1,
            },
            "search_view_id": [search_view.id, "search"] if search_view else False,
            "target": "current",
        }
