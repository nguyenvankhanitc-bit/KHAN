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

    def _can_update_task_state(self):
        """Cho phép cập nhật trạng thái khi đồng bộ từ phân hệ Dự án."""
        if self.env.su or self.env.context.get("lug_sync_lock"):
            return True
        return super()._can_update_task_state()

    def _can_edit_task(self):
        """Cho phép chỉnh sửa khi đồng bộ từ phân hệ Dự án."""
        if self.env.su or self.env.context.get("lug_sync_lock"):
            return True
        return super()._can_edit_task()

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("lug_sync_lock"):
            self._lug_sync_back_to_origin(vals)
        return res

    def _lug_sync_back_to_origin(self, vals):
        """Đồng bộ ngược 2 chiều từ Công việc hàng ngày / Công việc dự án về Dự án gốc."""
        sync_trigger_fields = {"state", "completion_percent", "deadline", "assign_date", "note"}
        if not any(f in vals for f in sync_trigger_fields):
            return

        for rec in self:
            rec_id = getattr(rec, "id", False)
            # 1. Trường hợp công việc gốc là Công việc chi tiết giai đoạn (project.stage.task)
            if rec.lug_origin_stage_task_id and rec.lug_origin_stage_task_id.exists():
                origin = rec.lug_origin_stage_task_id
                origin_vals = {}
                if "state" in vals or "completion_percent" in vals:
                    new_state = rec.state
                    sibling_domain = [("lug_origin_stage_task_id", "=", origin.id)]
                    if rec_id:
                        sibling_domain.append(("id", "!=", rec_id))
                    siblings = self.sudo().search(sibling_domain)
                    if new_state == "done":
                        if not siblings or all(s.state == "done" for s in siblings):
                            origin_vals["state"] = "done"
                        else:
                            origin_vals["state"] = "in_progress"
                    elif new_state == "in_progress":
                        origin_vals["state"] = "in_progress"
                    elif new_state == "not_started":
                        if any(s.state in ("done", "in_progress") for s in siblings):
                            origin_vals["state"] = "in_progress"
                        else:
                            origin_vals["state"] = "draft"
                if "deadline" in vals:
                    origin_vals["deadline"] = vals["deadline"]
                if "assign_date" in vals:
                    origin_vals["execution_date"] = vals["assign_date"]
                if "note" in vals and hasattr(origin, "notes"):
                    origin_vals["notes"] = vals["note"]

                if origin_vals:
                    origin.with_context(lug_sync_lock=True).sudo().write(origin_vals)
                continue

            # 2. Trường hợp công việc gốc là Công việc dự án (project.task)
            if rec.lug_origin_project_task_id and rec.lug_origin_project_task_id.exists():
                origin = rec.lug_origin_project_task_id
                origin_vals = {}
                if "state" in vals or "completion_percent" in vals:
                    new_state = rec.state
                    sibling_domain = [("lug_origin_project_task_id", "=", origin.id)]
                    if rec_id:
                        sibling_domain.append(("id", "!=", rec_id))
                    siblings = self.sudo().search(sibling_domain)
                    if new_state == "done":
                        if not siblings or all(s.state == "done" for s in siblings):
                            origin_vals["lug_status"] = "done"
                            origin_vals["lug_done_date"] = getattr(rec, "date_done", False) or fields.Date.context_today(self)
                            origin_vals["lug_progress"] = 100
                        else:
                            origin_vals["lug_status"] = "progress"
                            origin_vals["lug_progress"] = 50
                    elif new_state == "in_progress":
                        origin_vals["lug_status"] = "progress"
                        origin_vals["lug_done_date"] = False
                        pct = getattr(rec, "completion_percent", False)
                        origin_vals["lug_progress"] = (
                            pct if (isinstance(pct, (int, float)) and 0 < pct < 100) else 50
                        )
                    elif new_state == "not_started":
                        if any(s.state in ("done", "in_progress") for s in siblings):
                            origin_vals["lug_status"] = "progress"
                        else:
                            origin_vals["lug_status"] = "todo"
                            origin_vals["lug_done_date"] = False
                            origin_vals["lug_progress"] = 0
                if "deadline" in vals:
                    origin_vals["date_deadline"] = vals["deadline"]
                if "assign_date" in vals:
                    origin_vals["lug_execution_date"] = vals["assign_date"]
                if "note" in vals and hasattr(origin, "lug_note"):
                    origin_vals["lug_note"] = vals["note"]

                if origin_vals:
                    origin.with_context(lug_sync_lock=True).sudo().write(origin_vals)
                    todo = origin.lug_todo_task_id
                    if todo and todo.exists():
                        todo_vals = {}
                        if "lug_status" in origin_vals:
                            st = origin_vals["lug_status"]
                            todo_vals["state"] = (
                                "1_done"
                                if st == "done"
                                else ("1_canceled" if st == "cancel" else "01_in_progress")
                            )
                        if "date_deadline" in origin_vals:
                            todo_vals["date_deadline"] = origin_vals["date_deadline"]
                        if todo_vals:
                            todo.with_context(lug_sync_lock=True).sudo().write(todo_vals)
                continue

            # 3. Trường hợp đồng bộ cấp Dự án (project.project)
            if rec.lug_origin_project_id and rec.lug_origin_project_id.exists():
                origin = rec.lug_origin_project_id
                origin_vals = {}
                if "state" in vals or "completion_percent" in vals:
                    new_state = rec.state
                    if new_state == "done":
                        origin_vals["lug_workflow_state"] = "done"
                    elif new_state == "in_progress":
                        origin_vals["lug_workflow_state"] = "progress"
                    elif new_state == "not_started":
                        origin_vals["lug_workflow_state"] = "todo"
                if "deadline" in vals:
                    origin_vals["lug_deadline"] = vals["deadline"]
                if "assign_date" in vals:
                    origin_vals["date_start"] = vals["assign_date"]

                if origin_vals:
                    origin.with_context(lug_sync_lock=True).sudo().write(origin_vals)

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
