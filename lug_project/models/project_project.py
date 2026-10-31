# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
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
            ("high", "Gấp"),
            ("medium", "Không gấp"),
            ("low", "Không gấp"),
        ],
        string="Độ ưu tiên",
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
    lug_contract_attachment_ids = fields.Many2many(
        "ir.attachment",
        "lug_project_contract_ir_attachment_rel",
        "project_id",
        "attachment_id",
        string="File hợp đồng",
    )
    lug_stt = fields.Integer(string="STT", copy=False, index=True, readonly=True)
    lug_pic_type = fields.Selection(
        [
            ("internal", "Nội bộ"),
            ("partner", "Đối tác"),
        ],
        string="Người phụ trách",
        tracking=True,
    )
    lug_pic_id = fields.Many2one(
        "res.users",
        string="Người phụ trách",
        tracking=True,
        domain="[('share', '=', False)]",
        index=True,
    )
    lug_pic_partner_name = fields.Char(
        string="Đối tác phụ trách",
        tracking=True,
    )
    lug_supply_date = fields.Date(string="Ngày cung cấp", tracking=True)
    lug_content = fields.Text(string="Nội dung dự án")
    lug_pic_pool_ids = fields.Many2many(
        "res.users",
        "lug_project_pic_pool_rel",
        "project_id",
        "user_id",
        string="Nhóm người phụ trách",
        domain="[('share', '=', False)]",
        tracking=True,
    )
    lug_staff_pool_ids = fields.Many2many(
        "res.users",
        "lug_project_staff_pool_rel",
        "project_id",
        "user_id",
        string="Nhóm nhân sự",
        domain="[('share', '=', False)]",
        tracking=True,
    )
    lug_assignee_ids = fields.Many2many(
        "res.users",
        "lug_project_assignee_rel",
        "project_id",
        "user_id",
        string="Người làm",
        domain="[('share', '=', False)]",
    )
    lug_worker_label = fields.Char(
        string="Nhãn người làm",
        compute="_compute_lug_list_display",
    )
    lug_worker_ids = fields.Many2many(
        "res.users",
        string="Danh sách người làm",
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
            ("todo", "Đang làm"),
            ("progress", "Đang làm"),
            ("pause", "Tạm dừng"),
            ("done", "Hoàn thành"),
            ("cancel", "Hủy"),
            ("closed", "Hủy"),
        ],
        string="Trạng thái dự án",
        default="progress",
        tracking=True,
        copy=False,
        index=True,
    )
    lug_progress_pct = fields.Integer(
        string="Tiến độ tổng thể",
        compute="_compute_lug_progress_pct",
    )
    code = fields.Char(
        related="lug_code",
        string="Mã dự án (Code)",
        readonly=True,
    )
    project_type = fields.Selection(
        [
            ("event", "Sự Kiện"),
            ("maintenance", "Bảo trì"),
            ("internal", "Internal"),
            ("other", "Khác"),
        ],
        string="Phân loại dự án",
        compute="_compute_project_type",
        store=True,
    )
    deadline_status = fields.Char(
        string="Tình trạng hạn",
        compute="_compute_deadline_status",
    )
    deadline_color = fields.Char(
        string="Màu hạn",
        compute="_compute_deadline_status",
    )
    phase_num = fields.Integer(
        string="Mốc giai đoạn",
        compute="_compute_project_phase",
        store=True,
        default=1,
    )
    progress = fields.Float(
        string="Tiến độ (%)",
        compute="_compute_project_progress",
        store=True,
    )
    lug_priority_label = fields.Char(
        string="Nhãn độ ưu tiên",
        compute="_compute_lug_priority_label",
    )
    lug_archived_date = fields.Date(
        string="Ngày vào Thùng rác",
        copy=False,
        index=True,
    )
    lug_expense_ids = fields.One2many(
        "hr.expense",
        "project_id",
        string="Chi phí liên quan",
    )
    lug_total_expense = fields.Monetary(
        string="Chi phí",
        currency_field="currency_id",
        compute="_compute_lug_total_expense",
    )
    lug_expense_count = fields.Integer(
        string="Số phiếu chi phí",
        compute="_compute_lug_total_expense",
    )
    lug_daily_task_id = fields.Many2one(
        "daily.task",
        string="Công việc hàng ngày liên kết",
        ondelete="set null",
        copy=False,
        index=True,
    )
    daily_task_ids = fields.One2many(
        "daily.task",
        "lug_origin_project_id",
        string="Danh sách công việc hàng ngày liên kết",
    )
    _lug_code_uniq = models.Constraint(
        "unique(lug_code)",
        "Mã dự án phải duy nhất.",
    )

    @api.depends("lug_type_id", "lug_type_id.name", "lug_type_id.code")
    def _compute_project_type(self):
        for rec in self:
            name = (rec.lug_type_id.name or "").lower()
            type_code = (rec.lug_type_id.code or "").upper()
            if "sự kiện" in name or "su kien" in name or "event" in name or type_code == "SK":
                rec.project_type = "event"
            elif "bảo trì" in name or "bao tri" in name or type_code == "BT":
                rec.project_type = "maintenance"
            elif "nội bộ" in name or "noi bo" in name or "internal" in name or type_code == "NB":
                rec.project_type = "internal"
            else:
                rec.project_type = "other"

    @api.depends("lug_expense_ids.total_amount", "lug_expense_ids.state")
    def _compute_lug_total_expense(self):
        VALID_STATES = ("approved", "posted", "in_payment", "paid")
        if "hr.expense" not in self.env:
            for project in self:
                project.lug_total_expense = 0.0
                project.lug_expense_count = 0
            return
        Expense = self.env["hr.expense"]

        for project in self:
            expenses = project.lug_expense_ids.filtered(lambda exp: exp.state in VALID_STATES)
            if hasattr(project, "account_id") and project.account_id and hasattr(Expense, "analytic_distribution"):
                try:
                    analytic_expenses = Expense.search([
                        ("id", "not in", expenses.ids),
                        ("state", "in", VALID_STATES),
                        ("analytic_distribution", "in", project.account_id.ids),
                    ])
                    expenses = expenses | analytic_expenses
                except Exception:
                    pass
            project.lug_total_expense = sum(exp.total_amount for exp in expenses) if expenses else 0.0
            project.lug_expense_count = len(expenses)

    def action_view_lug_expenses(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_expense.hr_expense_actions_all")
        domain = [("project_id", "=", self.id)]
        if hasattr(self, "account_id") and self.account_id:
            domain = ["|", ("project_id", "=", self.id), ("analytic_distribution", "in", self.account_id.ids)]
        action["domain"] = domain
        action["context"] = {
            "default_project_id": self.id,
            "search_default_project_id": self.id,
        }
        return action

    @api.depends("date", "lug_deadline")
    def _compute_deadline_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            deadline = rec.lug_deadline or rec.date
            if not deadline:
                rec.deadline_status = "Chưa đặt hạn"
                rec.deadline_color = "muted"
                continue
            delta = (deadline - today).days
            if delta > 0:
                rec.deadline_status = "⏳ Còn %s ngày (Đúng hạn)" % delta
                rec.deadline_color = "warning" if delta <= 5 else "success"
            elif delta == 0:
                rec.deadline_status = "🔥 Đến hạn hôm nay"
                rec.deadline_color = "danger"
            else:
                rec.deadline_status = "⚠️ Quá hạn: Trễ %s ngày" % abs(delta)
                rec.deadline_color = "danger"

    def _lug_phase_from_name(self, name):
        stage_name = (name or "").lower()
        if "đóng" in stage_name or "gđ 4" in stage_name or "gd 4" in stage_name or "hoàn thành" in stage_name:
            return 4
        if "nghiệm thu" in stage_name or "gđ 3" in stage_name or "gd 3" in stage_name:
            return 3
        if "thực hiện" in stage_name or "triển khai" in stage_name or "gđ 2" in stage_name or "gd 2" in stage_name:
            return 2
        if "chuẩn bị" in stage_name or "gđ 1" in stage_name or "gd 1" in stage_name:
            return 1
        return 0

    @api.depends(
        "stage_id",
        "stage_id.name",
        "stage_line_ids.sequence",
        "stage_line_ids.name",
        "stage_line_ids.task_ids.state",
        "lug_stage_ids.sequence",
        "lug_stage_ids.name",
        "lug_stage_ids.task_ids.lug_status",
    )
    def _compute_project_phase(self):
        for rec in self:
            phase = rec._lug_phase_from_name(rec.stage_id.name)
            lines = rec.stage_line_ids.sorted(lambda line: (line.sequence or 0, line.id or 0))[:4]
            if lines:
                has_any_task = any(line.task_ids for line in lines)
                if not has_any_task:
                    rec.phase_num = 0
                    continue
                current = 1
                for index, line in enumerate(lines, 1):
                    named = rec._lug_phase_from_name(line.name)
                    tasks = line.task_ids
                    if tasks and all(task.state == "done" for task in tasks):
                        current = 4 if index >= 4 else index + 1
                    elif tasks and any(task.state in ("in_progress", "done") for task in tasks):
                        current = named or index
                        break
                    elif named:
                        current = named
                rec.phase_num = max(1, min(4, current))
                continue
            rec.phase_num = phase or 0

    @api.depends(
        "task_ids.stage_id",
        "task_ids.stage_id.fold",
        "task_ids.is_closed",
        "stage_line_ids.task_ids.state",
    )
    def _compute_project_progress(self):
        for rec in self:
            stage_tasks = rec.stage_line_ids.task_ids
            if stage_tasks:
                closed = len(stage_tasks.filtered(lambda task: task.state == "done"))
                rec.progress = round((closed / float(len(stage_tasks))) * 100, 1)
                continue
            total_tasks = len(rec.task_ids)
            if not total_tasks:
                rec.progress = 0.0
                continue
            closed_tasks = rec.task_ids.filtered(
                lambda task: task.is_closed or (task.stage_id and task.stage_id.fold)
            )
            rec.progress = round((len(closed_tasks) / float(total_tasks)) * 100, 1)

    @api.depends("lug_priority")
    def _compute_lug_priority_label(self):
        labels = dict(self._fields["lug_priority"].selection)
        for rec in self:
            rec.lug_priority_label = labels.get(rec.lug_priority) or "Bình thường"

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

    @api.onchange("lug_pic_type")
    def _onchange_lug_pic_type(self):
        if self.lug_pic_type == "partner":
            self.lug_pic_id = False
        elif self.lug_pic_type == "internal":
            self.lug_pic_partner_name = False

    @api.onchange("lug_pic_id")
    def _onchange_lug_pic_id(self):
        if self.lug_pic_id:
            self.user_id = self.lug_pic_id
            if not self.lug_pic_type:
                self.lug_pic_type = "internal"

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
                        exec_date = (
                            task.lug_execution_date
                            if hasattr(task, "lug_execution_date") and task.lug_execution_date
                            else (project.date_start or fields.Date.context_today(project))
                        )
                        task_vals.append({
                            "stage_id": line.id,
                            "sequence": (task.sequence or index * 10),
                            "name": task.name or "Công việc mới",
                            "user_ids": [(6, 0, [task.lug_pic_id.id])] if task.lug_pic_id else [],
                            "supervisor_ids": [(6, 0, [task.lug_supervisor_id.id])]
                            if task.lug_supervisor_id
                            else [],
                            "execution_date": exec_date,
                            "deadline": due or project.lug_deadline or project.date or False,
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

    def _lug_content_title(self, content):
        text = (content or "").strip()
        if not text:
            return ""
        return text.splitlines()[0][:120]

    def _lug_project_title(self):
        self.ensure_one()
        title = self._lug_content_title(self.lug_content)
        if title:
            return title
        return (self.name or "").strip() or "Dự án mới"

    def _lug_name_from_vals(self, vals=None, record=None):
        vals = vals or {}
        content = vals.get("lug_content") if "lug_content" in vals else (record.lug_content if record else "")
        title = self._lug_content_title(content)
        name = (vals.get("name") if "name" in vals else (record.name if record else "")) or ""
        name = str(name).strip()
        if title and (not name or name == "Dự án mới"):
            return title
        if name:
            return name[:120]
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
    def _lug_generate_code(self, type_id=None, project_date=None, excluded_codes=None):
        """Generate code: [Type]-[dd/mm/yyyy]-[STT in month] (e.g. NB-23/10/2026-01)."""
        self.env["project.project"].flush_model(["lug_code"])
        today = project_date or fields.Date.context_today(self)
        if isinstance(today, str):
            try:
                today = fields.Date.to_date(today)
            except Exception:
                today = fields.Date.context_today(self)
        if hasattr(today, "date"):
            today = today.date()

        type_code = "DA"
        if type_id:
            type_rec = False
            if hasattr(type_id, "code"):
                type_rec = type_id
            elif isinstance(type_id, (int, str)) and str(type_id).isdigit():
                type_rec = self.env["lug.project.type"].browse(int(type_id))
            if type_rec and hasattr(type_rec, "exists") and type_rec.exists():
                code_raw = (type_rec.code or "").strip().upper()
                if not code_raw and type_rec.name:
                    code_raw = (type_rec.name or "").strip().upper()[:4]
                if code_raw:
                    type_code = code_raw
            elif type_rec and getattr(type_rec, "code", False):
                type_code = str(type_rec.code).strip().upper()

        date_str = today.strftime("%d/%m/%Y")
        prefix = "%s-%s-" % (type_code, date_str)

        # STT counts all projects created in this month
        month_token = today.strftime("/%m/%Y-")
        month_pattern = "%" + month_token + "%"

        lock_str = "project_code_%s_%s" % (today.year, today.month)
        lock_key = abs(hash(lock_str)) % (2**31)
        if hasattr(self.env, "cr") and hasattr(self.env.cr, "execute"):
            try:
                self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            except Exception:
                pass

        max_db_seq = 0
        if hasattr(self.env, "cr") and hasattr(self.env.cr, "execute"):
            try:
                self.env.cr.execute(
                    """
                    SELECT COALESCE(MAX(
                        NULLIF(substring(lug_code from '-([0-9]+)$'), '')::INTEGER
                    ), 0)
                      FROM project_project
                     WHERE lug_code LIKE %s
                    """,
                    (month_pattern,),
                )
                row = self.env.cr.fetchone()
                max_db_seq = (row[0] if row else 0) or 0
            except Exception:
                pass

        max_batch_seq = 0
        if excluded_codes:
            for c in excluded_codes:
                if c and month_token in c:
                    parts = c.rsplit("-", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        max_batch_seq = max(max_batch_seq, int(parts[1]))

        next_seq = max(max_db_seq, max_batch_seq) + 1
        code = "%s%02d" % (prefix, next_seq)

        excluded = set(excluded_codes or ())
        while code in excluded or (hasattr(self, "search_count") and self.sudo().search_count([("lug_code", "=", code)])):
            next_seq += 1
            code = "%s%02d" % (prefix, next_seq)

        return code

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
        for project in self:
            try:
                users = []
                for u in (project.lug_assignee_ids or []):
                    if u and u not in users:
                        users.append(u)
                primary_user = project.lug_pic_id or project.user_id
                if primary_user and primary_user not in users:
                    users.append(primary_user)
                if not users:
                    continue

                proj_title = project._lug_project_title()
                sync_name = f"[Dự án] {proj_title}"
                daily_state = (
                    "done"
                    if project.lug_workflow_state == "done"
                    else ("in_progress" if project.lug_workflow_state in ("progress", "todo", "pause") else "not_started")
                )
                daily_priority = (
                    "high"
                    if project.lug_priority == "high"
                    else ("low" if project.lug_priority == "low" else "medium")
                )
                deadline = (
                    project.lug_deadline
                    or project.date
                    or fields.Date.context_today(project)
                )
                assign_date = project.date_start or fields.Date.context_today(project)
                assigned_by_id = (
                    (project.lug_approver_id and project.lug_approver_id.id)
                    or (project.user_id and project.user_id.id)
                    or project.env.user.id
                )

                active_daily_emps = {}
                for user in users:
                    emp = project._lug_get_or_create_daily_employee(user)
                    if emp:
                        active_daily_emps[emp.id] = (user, emp)

                proj_rec = project.sudo() if hasattr(project, "sudo") else project
                existing_daily_tasks = (
                    DailyTaskModel.search([
                        ("lug_origin_project_id", "=", project.id),
                        ("lug_origin_stage_task_id", "=", False),
                        ("lug_origin_project_task_id", "=", False),
                    ])
                    if hasattr(DailyTaskModel, "search")
                    else []
                )
                if not existing_daily_tasks and hasattr(proj_rec, "daily_task_ids") and proj_rec.daily_task_ids:
                    existing_daily_tasks = proj_rec.daily_task_ids.exists()
                if not existing_daily_tasks and hasattr(proj_rec, "lug_daily_task_id") and proj_rec.lug_daily_task_id and hasattr(proj_rec.lug_daily_task_id, "exists"):
                    existing_daily_tasks = proj_rec.lug_daily_task_id.exists()
                existing_by_emp = {dt.assignee_id.id: dt for dt in existing_daily_tasks if getattr(dt, "assignee_id", False)}
                existing_by_user = {}
                for dt in existing_daily_tasks:
                    uid = getattr(dt, "assignee_user_id", False) and dt.assignee_user_id.id
                    if not uid and getattr(dt, "assignee_id", False) and getattr(dt.assignee_id, "employee_id", False) and getattr(dt.assignee_id.employee_id, "user_id", False):
                        uid = dt.assignee_id.employee_id.user_id.id
                    if uid:
                        existing_by_user[uid] = dt

                created_first_dt = False
                for emp_id, (user, emp) in active_daily_emps.items():
                    daily_vals = {
                        "name": sync_name,
                        "deadline": deadline,
                        "assign_date": assign_date,
                        "state": daily_state,
                        "priority": daily_priority,
                    }
                    if daily_state == "done":
                        daily_vals["date_done"] = fields.Date.context_today(project)
                        daily_vals["completion_percent"] = 100
                    elif daily_state == "in_progress":
                        daily_vals["date_done"] = False
                        daily_vals["completion_percent"] = 50
                    else:
                        daily_vals["date_done"] = False
                        daily_vals["completion_percent"] = 0

                    matched_dt = existing_by_emp.get(emp_id) or (user and existing_by_user.get(user.id))
                    if matched_dt:
                        matched_dt.with_context(lug_sync_lock=True, daily_task_assigner_uid=assigned_by_id).sudo().write(daily_vals)
                        if not created_first_dt:
                            created_first_dt = matched_dt
                    else:
                        daily_vals.update({
                            "assignee_id": emp.id,
                            "assigned_by_id": assigned_by_id,
                            "department_id": emp.department_id.id or (project.lug_department_id and project.lug_department_id.id) or False,
                            "lug_origin_project_id": project.id,
                        })
                        new_dt = DailyTaskModel.with_context(lug_sync_lock=True, daily_task_assigner_uid=assigned_by_id).sudo().create(daily_vals)
                        if not created_first_dt:
                            created_first_dt = new_dt

                if created_first_dt and project.lug_daily_task_id != created_first_dt:
                    project.with_context(lug_sync_lock=True).sudo().write({"lug_daily_task_id": created_first_dt.id})

                for dt in existing_daily_tasks:
                    emp_id = dt.assignee_id.id if getattr(dt, "assignee_id", False) else False
                    user_id = False
                    if getattr(dt, "assignee_user_id", False):
                        user_id = dt.assignee_user_id.id
                    elif getattr(dt, "assignee_id", False) and getattr(dt.assignee_id, "employee_id", False) and getattr(dt.assignee_id.employee_id, "user_id", False):
                        user_id = dt.assignee_id.employee_id.user_id.id
                    if emp_id not in active_daily_emps and (not user_id or user_id not in {u.id for u in users}):
                        try:
                            dt.with_context(lug_sync_lock=True).sudo().unlink()
                        except Exception:
                            pass
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Error syncing project %s to daily task: %s", project.id, e)

    @api.model_create_multi
    def create(self, vals_list):
        used_codes = set()
        for vals in vals_list:
            if not vals.get("lug_code"):
                code = self._lug_generate_code(
                    type_id=vals.get("lug_type_id"),
                    excluded_codes=used_codes,
                ) or False
                vals["lug_code"] = code
                if code:
                    used_codes.add(code)
            content = (vals.get("lug_content") or "").strip()
            if content and not vals.get("description"):
                vals["description"] = content
            vals["name"] = self._lug_name_from_vals(vals)
            if vals.get("lug_pic_type") == "partner":
                vals["lug_pic_id"] = False
            elif vals.get("lug_pic_type") == "internal" and vals.get("lug_pic_id") and not vals.get("user_id"):
                vals["user_id"] = vals["lug_pic_id"]
            elif vals.get("lug_pic_id") and not vals.get("user_id"):
                vals["user_id"] = vals["lug_pic_id"]
            if vals.get("lug_pic_id") and not vals.get("lug_pic_pool_ids"):
                vals["lug_pic_pool_ids"] = [(4, vals["lug_pic_id"])]
            vals.setdefault("allow_milestones", True)
            vals.setdefault("lug_workflow_state", "todo")
        records = super().create(vals_list)
        records._lug_fill_stt()
        records._lug_ensure_stages()
        records._lug_ensure_stage_lines()
        if not self.env.context.get("lug_sync_lock"):
            records._lug_sync_to_daily()
        return records

    def write(self, vals):
        if vals.get("lug_pic_type") == "partner":
            vals = dict(vals, lug_pic_id=False)
        elif vals.get("lug_pic_type") == "internal":
            vals = dict(vals, lug_pic_partner_name=False)
            if vals.get("lug_pic_id") and "user_id" not in vals:
                vals["user_id"] = vals["lug_pic_id"]
        elif vals.get("lug_pic_id") and "user_id" not in vals:
            vals = dict(vals, user_id=vals["lug_pic_id"])
        incoming_name = str(vals.get("name") or "").strip() if "name" in vals else None
        if "lug_content" in vals or incoming_name in ("", "Dự án mới"):
            vals = dict(vals)
            content = vals.get("lug_content") if "lug_content" in vals else (
                self.lug_content if len(self) == 1 else ""
            )
            title = self._lug_content_title(content)
            if title and (incoming_name in (None, "", "Dự án mới")):
                if len(self) == 1 and (self.name or "").strip() in ("", "Dự án mới"):
                    vals["name"] = title
                elif incoming_name in ("", "Dự án mới"):
                    vals["name"] = title
        if vals.get("active") is False and "lug_archived_date" not in vals:
            vals = dict(vals, lug_archived_date=fields.Date.context_today(self))
        if vals.get("active") is True:
            vals = dict(vals, lug_archived_date=False)
        res = super().write(vals)
        if not self.env.context.get("lug_sync_lock"):
            sync_fields = {
                "name",
                "lug_content",
                "lug_pic_type",
                "lug_pic_id",
                "lug_pic_partner_name",
                "user_id",
                "lug_assignee_ids",
                "date_start",
                "lug_deadline",
                "date",
                "lug_priority",
                "lug_workflow_state",
                "lug_department_id",
            }
            if any(f in vals for f in sync_fields):
                self._lug_sync_to_daily()
        return res

    def unlink(self):
        for rec in self:
            daily_tasks = (
                rec.daily_task_ids.exists()
                if (hasattr(rec, "daily_task_ids") and hasattr(rec.daily_task_ids, "exists"))
                else []
            )
            if not daily_tasks and hasattr(rec, "lug_daily_task_id") and rec.lug_daily_task_id and hasattr(rec.lug_daily_task_id, "exists"):
                daily_tasks = rec.lug_daily_task_id.exists()
            for dt in daily_tasks:
                try:
                    dt.with_context(lug_sync_lock=True).sudo().unlink()
                except Exception:
                    pass
        return super().unlink()

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
            "context": {
                "form_view_ref": "lug_project.view_project_intake_form",
                "active_test": False,
            },
        }

    def _lug_can_delete_project(self):
        return self.env.user.has_group("base.group_system")

    def lug_action_delete(self):
        """Đưa dự án vào thùng rác. Chỉ tài khoản Administrator."""
        if not self._lug_can_delete_project():
            raise AccessError("Chỉ tài khoản Administrator mới được xóa dự án.")
        self.sudo().write({"active": False})
        return True

    def lug_action_restore(self):
        self.write({"active": True})
        return True

    @api.model
    def _lug_trash_days(self):
        raw = self.env["ir.config_parameter"].sudo().get_param("lug_project.trash_days", "30")
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 30

    def _lug_unlink_with_timesheets(self):
        AnalyticLine = self.env["account.analytic.line"].sudo()
        for project in self:
            task_ids = project.with_context(active_test=False).task_ids.ids
            domain = [("project_id", "=", project.id)]
            if task_ids:
                domain = ["|", ("task_id", "in", task_ids)] + domain
            timesheets = AnalyticLine.search(domain)
            if timesheets:
                timesheets.unlink()
        self.unlink()

    @api.model
    def _lug_purge_trashed_projects(self):
        """Xóa vĩnh viễn dự án nằm trong Thùng rác quá số ngày cấu hình (mặc định 30)."""
        days = self._lug_trash_days()
        today = fields.Date.context_today(self)
        cutoff = today - timedelta(days=days)
        Trash = self.with_context(active_test=False).sudo()
        stale = Trash.search(
            [
                ("active", "=", False),
                ("is_template", "=", False),
                ("lug_archived_date", "!=", False),
                ("lug_archived_date", "<=", cutoff),
            ]
        )
        missing_date = Trash.search(
            [
                ("active", "=", False),
                ("is_template", "=", False),
                ("lug_archived_date", "=", False),
            ]
        )
        for rec in missing_date:
            rec.lug_archived_date = rec.write_date.date() if rec.write_date else today
        extra = missing_date.filtered(
            lambda rec: rec.lug_archived_date and rec.lug_archived_date <= cutoff
        )
        (stale | extra)._lug_unlink_with_timesheets()
        return True

    def lug_toggle_priority(self):
        self.ensure_one()
        self.lug_priority = "medium" if self.lug_priority == "high" else "high"
        return self.lug_priority == "high"

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
