# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProjectStageTask(models.Model):
    _name = "project.stage.task"
    _description = "Công việc chi tiết theo giai đoạn"
    _order = "sequence, id"

    daily_task_ids = fields.One2many(
        "daily.task",
        "lug_origin_stage_task_id",
        string="Công việc hàng ngày liên kết",
    )

    stage_id = fields.Many2one(
        "project.stage.line",
        string="Giai đoạn",
        required=True,
        ondelete="cascade",
        index=True,
    )
    project_id = fields.Many2one(
        "project.project",
        related="stage_id.project_id",
        store=True,
        index=True,
        readonly=True,
    )
    sequence = fields.Integer(default=10, index=True)
    stt = fields.Char(
        string="STT",
        compute="_compute_stt",
        store=False,
    )
    name = fields.Char(string="Tên công việc giai đoạn", required=True)
    user_ids = fields.Many2many(
        "res.users",
        "project_stage_task_user_rel",
        "task_id",
        "user_id",
        string="Người phụ trách",
        domain="[('share', '=', False)]",
    )
    supervisor_ids = fields.Many2many(
        "res.users",
        "project_stage_task_supervisor_rel",
        "task_id",
        "user_id",
        string="Người giám sát",
        domain="[('share', '=', False)]",
    )
    user_display = fields.Char(
        string="Người phụ trách",
        compute="_compute_assignee_display",
    )
    supervisor_display = fields.Char(
        string="Người giám sát",
        compute="_compute_assignee_display",
    )
    execution_date = fields.Date(string="Ngày thực hiện")
    deadline = fields.Date(string="Ngày hết hạn")
    state = fields.Selection(
        [
            ("draft", "Chưa bắt đầu"),
            ("in_progress", "Đang làm"),
            ("done", "Hoàn thành"),
        ],
        string="Trạng thái",
        default="draft",
        required=True,
        index=True,
    )
    timeleft = fields.Char(
        string="Timeleft",
        compute="_compute_timeleft",
    )
    notes = fields.Text(string="Ghi chú")
    cost = fields.Float(string="Chi phí", default=0.0, digits=(16, 0))

    def init(self):
        """Migrate old Many2one columns to Many2many relation tables."""
        cr = self.env.cr
        try:
            cr.execute("ALTER TABLE project_stage_task ADD COLUMN IF NOT EXISTS execution_date DATE")
        except Exception:
            pass
        cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'project_stage_task'
               AND column_name IN ('user_id', 'supervisor_id')
            """
        )
        cols = {row[0] for row in cr.fetchall()}
        if "user_id" in cols:
            cr.execute(
                """
                CREATE TABLE IF NOT EXISTS project_stage_task_user_rel (
                    task_id INTEGER NOT NULL REFERENCES project_stage_task(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, user_id)
                )
                """
            )
            cr.execute(
                """
                INSERT INTO project_stage_task_user_rel (task_id, user_id)
                SELECT t.id, t.user_id
                  FROM project_stage_task t
                 WHERE t.user_id IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1 FROM project_stage_task_user_rel r
                         WHERE r.task_id = t.id AND r.user_id = t.user_id
                   )
                """
            )
            cr.execute("ALTER TABLE project_stage_task DROP COLUMN IF EXISTS user_id")
        if "supervisor_id" in cols:
            cr.execute(
                """
                CREATE TABLE IF NOT EXISTS project_stage_task_supervisor_rel (
                    task_id INTEGER NOT NULL REFERENCES project_stage_task(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, user_id)
                )
                """
            )
            cr.execute(
                """
                INSERT INTO project_stage_task_supervisor_rel (task_id, user_id)
                SELECT t.id, t.supervisor_id
                  FROM project_stage_task t
                 WHERE t.supervisor_id IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1 FROM project_stage_task_supervisor_rel r
                         WHERE r.task_id = t.id AND r.user_id = t.supervisor_id
                   )
                """
            )
            cr.execute("ALTER TABLE project_stage_task DROP COLUMN IF EXISTS supervisor_id")

    @api.depends("user_ids", "supervisor_ids")
    def _compute_assignee_display(self):
        for rec in self:
            rec.user_display = ", ".join(rec.user_ids.mapped("name")) or False
            rec.supervisor_display = ", ".join(rec.supervisor_ids.mapped("name")) or False

    @api.depends(
        "stage_id",
        "stage_id.sequence",
        "stage_id.project_id.stage_line_ids",
        "stage_id.task_ids",
        "stage_id.task_ids.sequence",
        "sequence",
    )
    def _compute_stt(self):
        self.stt = False
        stages = self.mapped("stage_id")
        projects = stages.mapped("project_id")
        stage_no = {}
        for project in projects:
            ordered = project.stage_line_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0))
            for index, stage in enumerate(ordered, 1):
                stage_no[stage.id] = index
        for stage in stages:
            tasks = stage.task_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0))
            prefix = stage_no.get(stage.id) or 1
            for index, task in enumerate(tasks, 1):
                if task in self:
                    task.stt = "%s.%s" % (prefix, index)

    @api.depends("deadline", "state")
    def _compute_timeleft(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state == "done":
                rec.timeleft = "Hoàn thành"
                continue
            if not rec.deadline:
                rec.timeleft = False
                continue
            delta = (rec.deadline - today).days
            if delta >= 0:
                rec.timeleft = "%s ngày" % delta
            else:
                rec.timeleft = "Trễ %s ngày" % abs(delta)

    @api.constrains("user_ids")
    def _check_user_ids(self):
        for rec in self:
            if not rec.user_ids:
                raise ValidationError("Vui lòng chọn Người phụ trách cho công việc.")

    def _lug_get_or_create_daily_employee(self, user):
        if not user or "daily.task.employee" not in self.env:
            return False
        DailyEmp = self.env["daily.task.employee"]
        # Direct SQL search on hr_employee to bypass HR visibility restrictions
        self.env.cr.execute(
            """
            SELECT id FROM hr_employee
             WHERE user_id = %s AND active = TRUE
             LIMIT 1
            """,
            (user.id,),
        )
        row = self.env.cr.fetchone()
        hr_emp_id = row[0] if row else False
        mail = (user.email or user.login or "").strip()
        if not hr_emp_id and mail:
            self.env.cr.execute(
                """
                SELECT id FROM hr_employee
                 WHERE (LOWER(work_email) = LOWER(%s) OR LOWER(private_email) = LOWER(%s))
                   AND active = TRUE
                 LIMIT 1
                """,
                (mail, mail),
            )
            row = self.env.cr.fetchone()
            if row:
                hr_emp_id = row[0]
                try:
                    self.env.cr.execute(
                        "UPDATE hr_employee SET user_id = %s WHERE id = %s AND user_id IS NULL",
                        (user.id, hr_emp_id),
                    )
                except Exception:
                    pass
        if not hr_emp_id and user.name:
            self.env.cr.execute(
                """
                SELECT id FROM hr_employee
                 WHERE LOWER(name) = LOWER(%s) AND active = TRUE
                 LIMIT 1
                """,
                (user.name.strip(),),
            )
            row = self.env.cr.fetchone()
            if row:
                hr_emp_id = row[0]
                try:
                    self.env.cr.execute(
                        "UPDATE hr_employee SET user_id = %s WHERE id = %s AND user_id IS NULL",
                        (user.id, hr_emp_id),
                    )
                except Exception:
                    pass

        # If user has no hr.employee, automatically create one so that daily.task will be linked and visible
        if not hr_emp_id and "hr.employee" in self.env:
            try:
                emp_rec = self.env["hr.employee"].sudo().create({
                    "name": user.name or "Nhân viên",
                    "user_id": user.id,
                    "work_email": mail or False,
                })
                hr_emp_id = emp_rec.id
            except Exception:
                pass

        if hr_emp_id:
            return DailyEmp.sudo().get_or_create_from_hr(hr_emp_id)

        domain = [("email", "=", mail)] if mail else [("name", "=ilike", user.name)]
        existing = DailyEmp.sudo().with_context(active_test=False).search(domain, limit=1)
        if existing:
            if not existing.active:
                existing.write({"active": True})
            return existing
        return DailyEmp.sudo().create({
            "name": user.name,
            "email": mail or False,
        })

    def _lug_sync_to_daily(self):
        if "daily.task" not in self.env:
            return
        DailyTaskModel = self.env["daily.task"].sudo()
        for task in self:
            try:
                project = task.project_id or (task.stage_id and task.stage_id.project_id)
                proj_name = project.name or "Dự án" if project else "Dự án"
                sync_name = f"[{proj_name}] {task.name}"
                daily_state = (
                    "done"
                    if task.state == "done"
                    else ("in_progress" if task.state == "in_progress" else "not_started")
                )
                daily_priority = (
                    "high"
                    if project and project.lug_priority == "high"
                    else ("low" if project and project.lug_priority == "low" else "medium")
                )
                deadline = (
                    task.deadline
                    or (project and (project.lug_deadline or project.date))
                    or fields.Date.context_today(task)
                )
                assign_date = task.execution_date or fields.Date.context_today(task)
                assigned_by_id = (
                    (project and project.user_id and project.user_id.id)
                    or (project and project.lug_pic_id and project.lug_pic_id.id)
                    or task.env.user.id
                )

                active_daily_emps = {}
                for user in task.user_ids:
                    emp = task._lug_get_or_create_daily_employee(user)
                    if emp:
                        active_daily_emps[emp.id] = (user, emp)

                task_rec = task.sudo() if hasattr(task, "sudo") else task
                existing_daily_tasks = (
                    task_rec.daily_task_ids.exists()
                    if (hasattr(task_rec, "daily_task_ids") and hasattr(task_rec.daily_task_ids, "exists"))
                    else []
                )
                existing_by_emp = {dt.assignee_id.id: dt for dt in existing_daily_tasks}

                for emp_id, (user, emp) in active_daily_emps.items():
                    daily_vals = {
                        "name": sync_name,
                        "deadline": deadline,
                        "assign_date": assign_date,
                        "state": daily_state,
                        "priority": daily_priority,
                    }
                    if daily_state == "done":
                        daily_vals["date_done"] = fields.Date.context_today(task)

                    if emp_id in existing_by_emp:
                        existing_by_emp[emp_id].with_context(lug_sync_lock=True).sudo().write(daily_vals)
                    else:
                        daily_vals.update({
                            "assignee_id": emp.id,
                            "assigned_by_id": assigned_by_id,
                            "department_id": emp.department_id.id or (project and project.lug_department_id and project.lug_department_id.id) or False,
                            "lug_origin_stage_task_id": task.id,
                            "lug_origin_project_id": project.id if project else False,
                        })
                        DailyTaskModel.with_context(lug_sync_lock=True, daily_task_assigner_uid=assigned_by_id).sudo().create(daily_vals)

                for emp_id, dt in existing_by_emp.items():
                    if emp_id not in active_daily_emps:
                        try:
                            dt.with_context(lug_sync_lock=True).sudo().unlink()
                        except Exception:
                            pass
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Error syncing stage task %s to daily task: %s", task.id, e)

    @api.model_create_multi
    def create(self, vals_list):
        Stage = self.env["project.stage.line"]
        for vals in vals_list:
            if not (vals.get("name") or "").strip():
                vals["name"] = "Công việc mới"
            if not vals.get("sequence") and vals.get("stage_id"):
                siblings = Stage.browse(vals["stage_id"]).task_ids
                vals["sequence"] = (max(siblings.mapped("sequence") or [0]) + 10)
            # Compat: map old single-user keys if still sent from UI/context
            if vals.get("user_id") and not vals.get("user_ids"):
                vals["user_ids"] = [(6, 0, [vals.pop("user_id")])]
            elif "user_id" in vals:
                vals.pop("user_id")
            if vals.get("supervisor_id") and not vals.get("supervisor_ids"):
                vals["supervisor_ids"] = [(6, 0, [vals.pop("supervisor_id")])]
            elif "supervisor_id" in vals:
                vals.pop("supervisor_id")
        records = super().create(vals_list)
        if not self.env.context.get("lug_sync_lock"):
            records._lug_sync_to_daily()
        return records

    def write(self, vals):
        vals = dict(vals)
        if vals.get("user_id") and not vals.get("user_ids"):
            vals["user_ids"] = [(6, 0, [vals.pop("user_id")])]
        elif "user_id" in vals:
            vals.pop("user_id")
        if vals.get("supervisor_id") and not vals.get("supervisor_ids"):
            vals["supervisor_ids"] = [(6, 0, [vals.pop("supervisor_id")])]
        elif "supervisor_id" in vals:
            vals.pop("supervisor_id")
        res = super().write(vals)
        if not self.env.context.get("lug_sync_lock"):
            sync_fields = {"name", "user_ids", "deadline", "execution_date", "state", "stage_id"}
            if any(f in vals for f in sync_fields):
                self._lug_sync_to_daily()
        return res

    def unlink(self):
        for rec in self:
            if rec.daily_task_ids:
                try:
                    rec.daily_task_ids.with_context(lug_sync_lock=True).unlink()
                except Exception:
                    pass
        return super().unlink()

    def action_open_popup(self):
        self.ensure_one()
        view = self.env.ref("lug_project.view_project_stage_task_popup_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Công việc chi tiết",
            "res_model": "project.stage.task",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }
