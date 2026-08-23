# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

_LUG_DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")


class ProjectProject(models.Model):
    _inherit = "project.project"

    lug_code = fields.Char(
        string="Mã dự án",
        copy=False,
        readonly=True,
        index=True,
        tracking=True,
    )
    lug_type_id = fields.Many2one(
        "lug.project.type",
        string="Loại dự án",
        tracking=True,
        ondelete="restrict",
        index=True,
    )
    lug_objective = fields.Html(string="Mục tiêu")
    lug_deadline = fields.Date(string="Deadline", tracking=True, index=True)
    lug_priority = fields.Selection(
        [
            ("high", "Cao"),
            ("medium", "Trung bình"),
            ("low", "Thấp"),
        ],
        string="Mức độ ưu tiên",
        default="medium",
        tracking=True,
        index=True,
    )
    lug_department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        tracking=True,
        ondelete="restrict",
        index=True,
    )
    lug_approver_id = fields.Many2one(
        "res.users",
        string="Người phê duyệt",
        tracking=True,
        domain="[('share', '=', False)]",
        index=True,
    )
    lug_deliverable_ids = fields.One2many(
        "lug.project.deliverable",
        "project_id",
        string="Deliverables",
    )
    lug_criterion_ids = fields.One2many(
        "lug.project.criterion",
        "project_id",
        string="Tiêu chí hoàn thành",
    )
    lug_stage_ids = fields.One2many(
        "lug.project.stage",
        "project_id",
        string="Danh sách giai đoạn",
    )
    stage_line_ids = fields.One2many(
        "project.stage.line",
        "project_id",
        string="Giai đoạn",
    )
    lug_attachment_ids = fields.Many2many(
        "ir.attachment",
        "lug_project_ir_attachment_rel",
        "project_id",
        "attachment_id",
        string="File đính kèm",
    )
    lug_stt = fields.Integer(string="STT", copy=False, index=True, readonly=True)
    lug_pic_id = fields.Many2one(
        "res.users",
        string="Người phụ trách",
        tracking=True,
        domain="[('share', '=', False)]",
        index=True,
    )
    lug_supply_date = fields.Date(string="Ngày cung cấp", tracking=True)
    lug_content = fields.Text(string="Nội dung dự án")
    lug_assignee_ids = fields.Many2many(
        "res.users",
        "lug_project_assignee_rel",
        "project_id",
        "user_id",
        string="Người làm",
        domain="[('share', '=', False)]",
    )
    lug_worker_label = fields.Char(
        string="Người làm",
        compute="_compute_lug_list_display",
    )
    lug_worker_ids = fields.Many2many(
        "res.users",
        string="Người làm",
        compute="_compute_lug_list_display",
    )
    lug_timeleft = fields.Char(
        string="Timeleft",
        compute="_compute_lug_list_display",
    )
    lug_pdf_id = fields.Many2one(
        "ir.attachment",
        string="PDF",
        compute="_compute_lug_list_display",
    )
    lug_workflow_state = fields.Selection(
        [
            ("todo", "Chưa bắt đầu"),
            ("progress", "Đang thực hiện"),
            ("done", "Hoàn thành"),
            ("closed", "Đóng"),
        ],
        string="Trạng thái dự án",
        default="todo",
        tracking=True,
        copy=False,
        index=True,
    )
    lug_progress_pct = fields.Integer(
        string="Tiến độ tổng thể",
        compute="_compute_lug_progress_pct",
    )
    _lug_code_uniq = models.Constraint(
        "unique(lug_code)",
        "Mã dự án phải duy nhất.",
    )

    @api.depends(
        "stage_line_ids.task_ids.state",
        "task_ids.lug_status",
        "task_ids.lug_progress",
    )
    def _compute_lug_progress_pct(self):
        for rec in self:
            tasks = rec.stage_line_ids.task_ids
            if tasks:
                done = len(tasks.filtered(lambda task: task.state == "done"))
                rec.lug_progress_pct = max(0, min(100, int(round(100.0 * done / float(len(tasks))))))
                continue
            legacy = rec.task_ids
            if not legacy:
                rec.lug_progress_pct = 0
                continue
            progresses = [int(task.lug_progress or 0) for task in legacy]
            if any(progresses):
                pct = int(round(sum(progresses) / float(len(legacy))))
            else:
                done = len(legacy.filtered(lambda task: task.lug_status == "done"))
                pct = int(round(100.0 * done / float(len(legacy))))
            rec.lug_progress_pct = max(0, min(100, pct))

    @api.onchange("lug_pic_id")
    def _onchange_lug_pic_id(self):
        if self.lug_pic_id:
            self.user_id = self.lug_pic_id

    @api.constrains("date_start", "lug_deadline")
    def _check_lug_deadline(self):
        for rec in self:
            if rec.date_start and rec.lug_deadline and rec.lug_deadline < rec.date_start:
                raise ValidationError("Deadline phải sau hoặc bằng ngày bắt đầu.")

    @api.depends(
        "lug_assignee_ids",
        "lug_deadline",
        "date",
        "last_update_status",
        "lug_attachment_ids",
        "task_ids.user_ids",
    )
    def _compute_lug_list_display(self):
        today = fields.Date.context_today(self)
        for rec in self:
            workers = rec.lug_assignee_ids or rec.task_ids.user_ids
            rec.lug_worker_ids = workers
            if not workers:
                rec.lug_worker_label = False
            else:
                first = (workers[0].name or "?").strip()
                extra = len(workers) - 1
                rec.lug_worker_label = ("%s +%s" % (first.split()[0], extra)) if extra else first
            if rec.last_update_status == "done":
                rec.lug_timeleft = "done|Hoàn thành"
            else:
                deadline = rec.lug_deadline or rec.date
                if not deadline:
                    rec.lug_timeleft = "none|Tự động tính toán"
                else:
                    delta = (deadline - today).days
                    if delta >= 0:
                        rec.lug_timeleft = "ok|%s ngày" % delta
                    else:
                        rec.lug_timeleft = "late|%s ngày" % abs(delta)
            docs = rec.lug_attachment_ids.filtered(
                lambda att: (att.name or "").lower().endswith(_LUG_DOC_EXTS)
            )
            rec.lug_pdf_id = (docs.sorted("id", reverse=True)[:1] or rec.lug_attachment_ids[:1])

    def _lug_default_stage_commands(self):
        pic = self.lug_pic_id.id if self.lug_pic_id else self.env.context.get("default_lug_pic_id")
        commands = []
        for row in self.env["lug.project.stage"]._lug_template_rows():
            vals = dict(row)
            if pic:
                vals["user_id"] = pic
            commands.append((0, 0, vals))
        return commands

    def _lug_default_stage_line_commands(self):
        rows = list(self.env["lug.project.stage"]._lug_template_rows())[:4]
        if not rows:
            rows = [{"sequence": (index + 1) * 10} for index in range(4)]
        return [
            (0, 0, {"name": False, "sequence": row.get("sequence") or (index + 1) * 10})
            for index, row in enumerate(rows)
        ]

    def _lug_ensure_stages(self):
        Stage = self.env["lug.project.stage"]
        for project in self:
            if project.lug_stage_ids:
                continue
            rows = Stage._lug_template_rows()
            pic = project.lug_pic_id.id or project.user_id.id
            Stage.create(
                [
                    dict(row, project_id=project.id, user_id=pic or False)
                    for row in rows
                ]
            )
        self._lug_map_tasks_to_stages()

    def _lug_ensure_stage_lines(self):
        Line = self.env["project.stage.line"]
        Task = self.env["project.stage.task"]
        status_map = {
            "todo": "draft",
            "progress": "in_progress",
            "review": "in_progress",
            "done": "done",
            "cancel": "draft",
        }
        for project in self:
            if project.stage_line_ids:
                continue
            if project.lug_stage_ids:
                for stage in project.lug_stage_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0)):
                    line = Line.create({
                        "project_id": project.id,
                        "name": stage.name,
                        "sequence": stage.sequence or 10,
                    })
                    task_vals = []
                    for index, task in enumerate(
                        stage.task_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0)),
                        1,
                    ):
                        due = task.date_deadline
                        if due and hasattr(due, "hour"):
                            due = due.date()
                        task_vals.append({
                            "stage_id": line.id,
                            "sequence": (task.sequence or index * 10),
                            "name": task.name or "Công việc mới",
                            "user_ids": [(6, 0, [task.lug_pic_id.id])] if task.lug_pic_id else [],
                            "supervisor_ids": [(6, 0, [task.lug_supervisor_id.id])]
                            if task.lug_supervisor_id
                            else [],
                            "deadline": due or False,
                            "state": status_map.get(task.lug_status, "draft"),
                            "notes": task.lug_note or False,
                            "cost": task.lug_cost or 0.0,
                        })
                    if task_vals:
                        Task.create(task_vals)
                continue
            rows = self.env["lug.project.stage"]._lug_template_rows()[:4]
            if not rows:
                rows = [{"sequence": (index + 1) * 10} for index in range(4)]
            Line.create(
                [
                    {
                        "project_id": project.id,
                        "name": False,
                        "sequence": row["sequence"],
                    }
                    for row in rows
                ]
            )

    def _lug_map_tasks_to_stages(self):
        for project in self:
            by_code = {stage.code: stage for stage in project.lug_stage_ids if stage.code}
            fallback = project.lug_stage_ids[:1]
            for task in project.task_ids.filtered(lambda rec: not rec.lug_stage_id):
                stage = by_code.get(task.lug_phase) or fallback
                if stage:
                    task.lug_stage_id = stage.id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "lug_stage_ids" in fields_list and not res.get("lug_stage_ids"):
            res["lug_stage_ids"] = self._lug_default_stage_commands()
        if "stage_line_ids" in fields_list and not res.get("stage_line_ids"):
            res["stage_line_ids"] = self._lug_default_stage_line_commands()
        return res

    def _lug_fill_stt(self):
        to_fill = self.filtered(lambda rec: not rec.lug_stt)
        if not to_fill:
            return
        self.env.cr.execute("SELECT COALESCE(MAX(lug_stt), 0) FROM project_project")
        number = self.env.cr.fetchone()[0] or 0
        for rec in to_fill.sorted(lambda rec: rec.id):
            number += 1
            rec.lug_stt = number

    def _lug_name_from_vals(self, vals=None, record=None):
        vals = vals or {}
        name = (vals.get("name") if "name" in vals else (record.name if record else "")) or ""
        name = str(name).strip()
        if name:
            return name[:120]
        content = vals.get("lug_content") if "lug_content" in vals else (record.lug_content if record else "")
        content = (content or "").strip()
        if content:
            return content.splitlines()[0][:120]
        return "Dự án mới"

    def _get_values_analytic_account_batch(self, project_vals_list):
        patched = []
        for project_vals in project_vals_list:
            vals = dict(project_vals)
            if not (vals.get("name") or "").strip():
                vals["name"] = self._lug_name_from_vals(vals)
            patched.append(vals)
        return super()._get_values_analytic_account_batch(patched)

    def _create_analytic_account(self):
        for project in self.filtered(lambda rec: not (rec.name or "").strip()):
            project.name = self._lug_name_from_vals(record=project)
        return super()._create_analytic_account()

    @api.model
    def _lug_generate_code(self, project_date=None):
        """Generate code: DA2026-23082026-01 (year-date-daily sequence)."""
        today = project_date or fields.Date.context_today(self)
        if hasattr(today, "date"):
            today = today.date()
        year = today.year
        date_token = today.strftime("%d%m%Y")
        prefix = "DA%s-%s-" % (year, date_token)
        lock_key = abs(hash(prefix)) % (2**31)
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        self.env.cr.execute(
            """
            SELECT COALESCE(MAX(
                NULLIF(substring(lug_code from %s), '')::INTEGER
            ), 0)
              FROM project_project
             WHERE lug_code LIKE %s
            """,
            (len(prefix) + 1, prefix + "%"),
        )
        next_seq = (self.env.cr.fetchone()[0] or 0) + 1
        return "%s%02d" % (prefix, next_seq)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("lug_code"):
                vals["lug_code"] = self._lug_generate_code() or False
            content = (vals.get("lug_content") or "").strip()
            if content and not vals.get("description"):
                vals["description"] = content
            vals["name"] = self._lug_name_from_vals(vals)
            if vals.get("lug_pic_id") and not vals.get("user_id"):
                vals["user_id"] = vals["lug_pic_id"]
            vals.setdefault("allow_milestones", True)
            vals.setdefault("lug_workflow_state", "todo")
        records = super().create(vals_list)
        records._lug_fill_stt()
        records._lug_ensure_stages()
        records._lug_ensure_stage_lines()
        return records

    def write(self, vals):
        if vals.get("lug_pic_id") and "user_id" not in vals:
            vals = dict(vals, user_id=vals["lug_pic_id"])
        if "name" in vals and not (vals.get("name") or "").strip():
            vals = dict(vals)
            if len(self) == 1:
                vals["name"] = self._lug_name_from_vals(vals, self)
            else:
                vals["name"] = self._lug_name_from_vals(vals) if (vals.get("lug_content") or "").strip() else "Dự án mới"
        return super().write(vals)

    def lug_action_open_form(self):
        self.ensure_one()
        view = self.env.ref("lug_project.view_project_intake_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Sửa dự án",
            "res_model": "project.project",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {"form_view_ref": "lug_project.view_project_intake_form"},
        }

    def lug_action_delete(self):
        self.unlink()
        return True

    def lug_action_open_pdf(self):
        self.ensure_one()
        attachment = self.lug_pdf_id
        if not attachment:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "new",
        }

    def lug_action_link_files(self, attachment_ids):
        self.ensure_one()
        if not attachment_ids:
            return False
        atts = self.env["ir.attachment"].browse(attachment_ids).exists()
        bad = atts.filtered(lambda att: not (att.name or "").lower().endswith(_LUG_DOC_EXTS))
        if bad:
            raise UserError("Chỉ nhận file Word, PDF hoặc Excel.")
        self.lug_attachment_ids = [(4, att.id) for att in atts]
        return True

    def _lug_backfill_content(self):
        recs = self.sudo().search(["|", ("lug_content", "=", False), ("lug_content", "=", "")])
        for rec in recs:
            text = (html2plaintext(rec.description or "") or "").strip()
            if text:
                rec.lug_content = text

    def _register_hook(self):
        super()._register_hook()
        try:
            empty = self.sudo().search([("lug_stt", "=", 0)], limit=1)
            if empty:
                self.sudo().search([("lug_stt", "=", 0)])._lug_fill_stt()
            self._lug_backfill_content()
            missing = self.sudo().search([("lug_stage_ids", "=", False)], limit=1)
            if missing:
                self.sudo().search([("lug_stage_ids", "=", False)])._lug_ensure_stages()
            missing_lines = self.sudo().search([("stage_line_ids", "=", False)], limit=1)
            if missing_lines:
                self.sudo().search([("stage_line_ids", "=", False)])._lug_ensure_stage_lines()
        except Exception:
            pass
