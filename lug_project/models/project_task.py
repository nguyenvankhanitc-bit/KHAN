# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = "project.task"

    lug_stage_id = fields.Many2one(
        "lug.project.stage",
        string="Giai đoạn",
        ondelete="cascade",
        index=True,
        copy=False,
        domain="[('project_id', '=', project_id)]",
    )
    lug_cost = fields.Float(string="Chi phí", default=0.0, digits=(16, 0))
    lug_phase = fields.Selection(
        [
            ("1", "Giai đoạn 1: CHUẨN BỊ & KHẢO SÁT"),
            ("2", "Giai đoạn 2: TRIỂN KHAI & BÁN HÀNG"),
            ("3", "Giai đoạn 3: LẮP ĐẶT & HOÀN THIỆN"),
            ("4", "Giai đoạn 4: NGHIỆM THU & BÀN GIAO"),
            ("5", "Giai đoạn 5: BẢO HÀNH & HỖ TRỢ"),
            ("6", "Giai đoạn 6: ĐÓNG DỰ ÁN"),
        ],
        string="Giai đoạn",
        index=True,
    )
    lug_pic_id = fields.Many2one(
        "res.users",
        string="Người phụ trách",
        domain="[('share', '=', False)]",
        index=True,
        tracking=True,
    )
    lug_supervisor_id = fields.Many2one(
        "res.users",
        string="Người giám sát",
        domain="[('share', '=', False)]",
        index=True,
        tracking=True,
    )
    lug_done_date = fields.Date(string="Ngày hoàn thành", copy=False)
    lug_result = fields.Char(string="Kết quả")
    lug_note = fields.Char(string="Ghi chú")
    lug_status = fields.Selection(
        [
            ("todo", "Chưa bắt đầu"),
            ("progress", "Đang thực hiện"),
            ("review", "Chờ duyệt"),
            ("done", "Hoàn thành"),
            ("cancel", "Hủy"),
        ],
        string="Trạng thái",
        default="todo",
        required=True,
        index=True,
        tracking=True,
    )
    lug_progress = fields.Integer(
        string="Tiến độ công việc",
        default=0,
        help="Phần trăm hoàn thành (0–100).",
    )
    lug_timeleft = fields.Char(
        string="Timeleft",
        compute="_compute_lug_timeleft",
    )
    lug_line_stt = fields.Char(
        string="STT",
        compute="_compute_lug_line_stt",
    )
    lug_todo_task_id = fields.Many2one(
        "project.task",
        string="Việc cần làm liên kết",
        ondelete="set null",
        copy=False,
        index=True,
    )
    lug_daily_task_id = fields.Many2one(
        "daily.task",
        string="Công việc hàng ngày liên kết",
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

    @api.depends(
        "project_id",
        "lug_stage_id",
        "lug_stage_id.code",
        "lug_stage_id.task_ids",
        "lug_stage_id.task_ids.sequence",
        "sequence",
    )
    def _compute_lug_line_stt(self):
        self.lug_line_stt = False
        staged = self.filtered("lug_stage_id")
        for stage in staged.mapped("lug_stage_id"):
            tasks = stage.task_ids.sorted(lambda task: (task.sequence or 0, task.id or 0))
            code = stage.code or "0"
            for index, task in enumerate(tasks, 1):
                if task in self:
                    task.lug_line_stt = "%s.%s" % (code, index)
        orphans = self - staged
        for project in orphans.mapped("project_id"):
            tasks = orphans.filtered(lambda task: task.project_id == project).sorted(
                lambda task: (task.sequence or 0, task.id or 0)
            )
            for index, task in enumerate(tasks, 1):
                task.lug_line_stt = str(index)

    @api.depends("date_deadline", "lug_done_date", "lug_status")
    def _compute_lug_timeleft(self):
        today = fields.Date.context_today(self)
        for rec in self:
            deadline = fields.Date.to_date(rec.date_deadline) if rec.date_deadline else False
            if not deadline:
                rec.lug_timeleft = "none|—"
                continue
            if rec.lug_status == "done" and rec.lug_done_date:
                delta = (rec.lug_done_date - deadline).days
                rec.lug_timeleft = "done|%s ngày" % delta
            elif rec.lug_status == "done":
                rec.lug_timeleft = "done|Hoàn thành"
            else:
                delta = (deadline - today).days
                if delta >= 0:
                    rec.lug_timeleft = "ok|%s ngày" % delta
                else:
                    rec.lug_timeleft = "late|%s ngày" % abs(delta)

    def _lug_apply_stage_defaults(self, vals):
        stage_id = vals.get("lug_stage_id")
        if not stage_id:
            return vals
        stage = self.env["lug.project.stage"].browse(stage_id)
        if not stage.exists():
            return vals
        if not vals.get("project_id") and stage.project_id:
            vals["project_id"] = stage.project_id.id
        codes = {key for key, _label in self._fields["lug_phase"].selection}
        if "lug_phase" not in vals and stage.code in codes:
            vals["lug_phase"] = stage.code
        return vals

    @api.onchange("lug_stage_id")
    def _onchange_lug_stage_id(self):
        if self.lug_stage_id:
            self.project_id = self.lug_stage_id.project_id
            codes = {key for key, _label in self._fields["lug_phase"].selection}
            if self.lug_stage_id.code in codes:
                self.lug_phase = self.lug_stage_id.code

    @api.onchange("lug_pic_id")
    def _onchange_lug_pic_id(self):
        if self.lug_pic_id:
            self.user_ids = self.lug_pic_id

    @api.onchange("lug_status")
    def _onchange_lug_status(self):
        if self.lug_status == "done" and not self.lug_done_date:
            self.lug_done_date = fields.Date.context_today(self)
        if self.lug_status == "progress" and not self.lug_result:
            self.lug_result = "Đang thực hiện"
        if self.lug_status == "done" and not self.lug_result:
            self.lug_result = "Hoàn thành"

    def _lug_get_or_create_daily_employee(self, user):
        if not user:
            return False
        DailyEmp = self.env.get("daily.task.employee")
        if not DailyEmp:
            return False
        hr_emp = self.env["hr.employee"].search([("user_id", "=", user.id)], limit=1)
        if hr_emp:
            return DailyEmp.get_or_create_from_hr(hr_emp.id)
        mail = (user.email or user.login or "").strip()
        domain = [("email", "=", mail)] if mail else [("name", "=ilike", user.name)]
        existing = DailyEmp.search(domain, limit=1)
        if existing:
            return existing
        return DailyEmp.create({
            "name": user.name,
            "email": mail or False,
        })

    def _lug_sync_to_todo_and_daily(self):
        for task in self:
            if not task.project_id or task.lug_origin_project_task_id:
                continue
            user = task.lug_pic_id or (task.user_ids and task.user_ids[0]) or False
            if not user:
                continue

            proj_name = task.project_id.name or "Dự án"
            sync_name = f"[{proj_name}] {task.name}"

            # 1. Sync to To-Do (project_todo: project.task with project_id = False)
            todo_state = (
                "1_done"
                if task.lug_status == "done"
                else ("1_canceled" if task.lug_status == "cancel" else "01_in_progress")
            )
            if task.lug_todo_task_id and task.lug_todo_task_id.exists():
                task.lug_todo_task_id.with_context(lug_sync_lock=True).write({
                    "name": sync_name,
                    "user_ids": [(6, 0, [user.id])],
                    "date_deadline": task.date_deadline,
                    "state": todo_state,
                })
            else:
                todo_task = task.env["project.task"].with_context(lug_sync_lock=True).create({
                    "name": sync_name,
                    "project_id": False,
                    "user_ids": [(6, 0, [user.id])],
                    "date_deadline": task.date_deadline,
                    "state": todo_state,
                    "lug_origin_project_task_id": task.id,
                })
                task.with_context(lug_sync_lock=True).write({"lug_todo_task_id": todo_task.id})

            # 2. Sync to Daily Task (daily.task in daily_work_task)
            DailyTaskModel = task.env.get("daily.task")
            if DailyTaskModel:
                daily_emp = task._lug_get_or_create_daily_employee(user)
                if daily_emp:
                    daily_state = (
                        "done"
                        if task.lug_status == "done"
                        else ("in_progress" if task.lug_status in ("progress", "review") else "not_started")
                    )
                    daily_priority = (
                        "high"
                        if task.project_id.lug_priority == "high"
                        else ("low" if task.project_id.lug_priority == "low" else "medium")
                    )
                    deadline = (
                        task.date_deadline
                        or task.project_id.lug_deadline
                        or task.project_id.date
                        or fields.Date.context_today(task)
                    )
                    daily_vals = {
                        "name": sync_name,
                        "assignee_id": daily_emp.id,
                        "deadline": deadline,
                        "state": daily_state,
                        "priority": daily_priority,
                    }
                    if daily_state == "done":
                        daily_vals["date_done"] = task.lug_done_date or fields.Date.context_today(task)

                    if task.lug_daily_task_id and task.lug_daily_task_id.exists():
                        task.lug_daily_task_id.with_context(lug_sync_lock=True).write(daily_vals)
                    else:
                        daily_vals.update({
                            "assigned_by_id": task.project_id.user_id.id or task.env.user.id,
                            "assign_date": fields.Date.context_today(task),
                            "department_id": daily_emp.department_id.id or task.project_id.lug_department_id.id or False,
                            "lug_origin_project_task_id": task.id,
                        })
                        daily_task = DailyTaskModel.with_context(lug_sync_lock=True).create(daily_vals)
                        task.with_context(lug_sync_lock=True).write({"lug_daily_task_id": daily_task.id})

    def _lug_sync_from_todo_to_project(self, vals):
        for rec in self:
            origin = rec.lug_origin_project_task_id
            if not origin or not origin.exists():
                continue
            origin_vals = {}
            if "state" in vals:
                if vals["state"] == "1_done":
                    origin_vals["lug_status"] = "done"
                    origin_vals["lug_done_date"] = fields.Date.context_today(rec)
                elif vals["state"] == "1_canceled":
                    origin_vals["lug_status"] = "cancel"
                elif vals["state"] == "01_in_progress":
                    if origin.lug_status == "done":
                        origin_vals["lug_status"] = "progress"
            if "date_deadline" in vals:
                origin_vals["date_deadline"] = vals["date_deadline"]

            if origin_vals:
                origin.with_context(lug_sync_lock=True).write(origin_vals)
                if origin.lug_daily_task_id and origin.lug_daily_task_id.exists():
                    daily_vals = {}
                    if "lug_status" in origin_vals:
                        st = origin_vals["lug_status"]
                        daily_vals["state"] = (
                            "done"
                            if st == "done"
                            else ("in_progress" if st in ("progress", "review") else "not_started")
                        )
                        if st == "done":
                            daily_vals["date_done"] = origin_vals.get("lug_done_date") or fields.Date.context_today(rec)
                    if "date_deadline" in origin_vals and origin_vals["date_deadline"]:
                        daily_vals["deadline"] = origin_vals["date_deadline"]
                    if daily_vals:
                        origin.lug_daily_task_id.with_context(lug_sync_lock=True).write(daily_vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals = self._lug_apply_stage_defaults(vals)
            if not (vals.get("name") or "").strip():
                vals["name"] = "Công việc mới"
            pic = vals.get("lug_pic_id")
            if pic and not vals.get("user_ids"):
                vals["user_ids"] = [(6, 0, [pic])]
            if vals.get("lug_status") == "done" and not vals.get("lug_done_date"):
                vals["lug_done_date"] = fields.Date.context_today(self)
        records = super().create(vals_list)
        if not self.env.context.get("lug_sync_lock"):
            for rec in records:
                if rec.project_id and not rec.lug_origin_project_task_id:
                    rec._lug_sync_to_todo_and_daily()
        return records

    def write(self, vals):
        vals = self._lug_apply_stage_defaults(vals)
        pic = vals.get("lug_pic_id")
        if pic and "user_ids" not in vals:
            vals = dict(vals, user_ids=[(6, 0, [pic])])
        res = super().write(vals)
        if vals.get("lug_status") == "done":
            to_fill = self.filtered(lambda rec: not rec.lug_done_date)
            if to_fill:
                super(ProjectTask, to_fill).write(
                    {"lug_done_date": fields.Date.context_today(self)}
                )
        if not self.env.context.get("lug_sync_lock"):
            for rec in self:
                if rec.project_id and not rec.lug_origin_project_task_id:
                    sync_fields = {"name", "date_deadline", "lug_pic_id", "user_ids", "lug_status", "project_id"}
                    if any(f in vals for f in sync_fields):
                        rec._lug_sync_to_todo_and_daily()
                elif not rec.project_id and rec.lug_origin_project_task_id:
                    rec._lug_sync_from_todo_to_project(vals)
        return res

    def unlink(self):
        for rec in self:
            if rec.lug_todo_task_id and rec.lug_todo_task_id.exists():
                try:
                    rec.lug_todo_task_id.with_context(lug_sync_lock=True).unlink()
                except Exception:
                    pass
            if rec.lug_daily_task_id and rec.lug_daily_task_id.exists():
                try:
                    rec.lug_daily_task_id.with_context(lug_sync_lock=True).unlink()
                except Exception:
                    pass
        return super().unlink()

    @api.constrains("lug_stage_id", "project_id")
    def _check_lug_stage_project(self):
        for rec in self:
            if rec.lug_stage_id and rec.project_id and rec.lug_stage_id.project_id != rec.project_id:
                raise ValidationError("Công việc phải cùng dự án với giai đoạn.")

    @api.constrains("lug_progress")
    def _check_lug_progress(self):
        for rec in self:
            if rec.lug_progress < 0 or rec.lug_progress > 100:
                raise ValidationError("Tiến độ công việc phải từ 0 đến 100.")
