# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProjectStageTask(models.Model):
    _name = "project.stage.task"
    _description = "Công việc chi tiết theo giai đoạn"
    _order = "sequence, id"

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
        return super().create(vals_list)

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
        return super().write(vals)

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
