import logging
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from numbers import Integral

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import sql
from odoo.tools.misc import format_date
from odoo.tools.translate import _

from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION

_logger = logging.getLogger(__name__)

_MULTI_STEP_RESET_CTX = "time_off_multi_step_reset_skip"

# Order for sequential HR-responsible approval: by job title (keys from hr_job_title_vn), lowest first.
# Excludes the generic employee tier so approvers map to management chain only.
_HR_RESPONSIBLE_APPROVAL_JOB_TITLE_ORDER = tuple(
    key for key, _label in JOB_TITLE_SELECTION if key != "nhân viên"
)
# Key used in hr_job_title_vn hr.version job_title selection; only this tier may approve their own leave in HR Responsibles flow.
_DIRECTOR_JOB_TITLE_KEY = "giám đốc"
# Manual / sorted-by-title flows; org-chart mode allows one row per manager level (can exceed 6).
_MAX_EMPLOYEE_HR_RESPONSIBLES = 15
# Special multi-director list can exceed the usual cap (chain + all directors).
_MAX_EMPLOYEE_HR_RESPONSIBLES_MULTI_DIRECTOR = 40
_HANDOVER_ACTIVITY_XMLID = "time_off_extra_approval.mail_act_leave_work_handover"
# Handover acknowledgement rows and activities apply while the request awaits approval.
_HANDOVER_ACTIVE_STATES = ("confirm", "validate1")
_TODO_ACTIVITY_XMLID = "mail.mail_activity_data_todo"
# Fallback values when leave type config is missing.
_HANDOVER_ESCALATION_MINUTES = 5
_HANDOVER_ESCALATION_TO_MANAGER_HOURS = 2
_DEPARTMENT_HEAD_JOB_TITLE_KEY = "trưởng bộ phận"
_DEPARTMENT_MANAGER_JOB_TITLE_KEY = "trưởng phòng"

# Advance notice (calendar days between today and first leave day) by job title (hr_job_title_vn keys).
_EMERGENCY_LEAVE_CTX = "emergency_leave_confirmed"
_SKIP_EMERGENCY_LEAVE_CHECK_CTX = "skip_emergency_leave_check"
_SKIP_SUBMIT_BOT_NOTIFY_CTX = "skip_handover_submit_bot_notify"
_SKIP_OUTCOME_BOT_NOTIFY_CTX = "skip_outcome_bot_notify"
_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX = "skip_responsible_submit_notify"
_SHORT_LEAD_JOB_KEYS = frozenset({"nhân viên", "trưởng nhóm"})
_SHORT_LEAD_DAYS = 3
_DEFAULT_LEAD_DAYS = 7


def _job_title_approval_sort_key(user, order_index):
    """Return (rank, user_id) for sorting approvers by job title."""
    title = user.employee_id.job_title if user.employee_id else False
    if title and title in order_index:
        return (order_index[title], user.id)
    # Unknown / empty title: after defined chain, stable by user id
    return (len(order_index) + 1, user.id)


def _normalize_job_title_key(title):
    normalized = (title or "").strip().casefold()
    normalized = "".join(
        ch for ch in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(ch)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    aliases = {
        "truong bp": "truong bo phan",
    }
    return aliases.get(normalized, normalized)


def _job_title_rank_map():
    """Support both selection keys and display labels stored in DB."""
    rank_map = {}
    for idx, (key, label) in enumerate(JOB_TITLE_SELECTION):
        rank_map[_normalize_job_title_key(key)] = idx
        rank_map[_normalize_job_title_key(label)] = idx
    return rank_map


class HolidaysRequest(models.Model):
    _inherit = "hr.leave"

    status_display_label = fields.Char(
        string="Status Display",
        compute="_compute_status_display_label",
    )
    last_refusal_reason = fields.Text(
        string="Last Refusal Reason",
        copy=False,
        readonly=True,
    )
    last_refuser_id = fields.Many2one(
        "res.users",
        string="Last Refuser",
        copy=False,
        readonly=True,
    )

    # Multi-step approval (demo). Used when hr.leave.type.leave_validation_type = 'multi_step_6'.
    multi_step_current = fields.Integer(
        string="Multi-step Current Step",
        default=1,
        help="Current step index (1..6) for multi-step time off approval (demo).",
    )
    multi_approval_line_ids = fields.One2many(
        comodel_name="hr.leave.multi.approval",
        inverse_name="leave_id",
        string="Multi-step Approval Log (Demo)",
        readonly=True,
    )

    can_multi_step_approve = fields.Boolean(
        string="Can Approve Current Multi-step (Demo)",
        compute="_compute_can_multi_step_approve",
    )

    extra_approver_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="hr_leave_extra_approver_user_rel",
        column1="leave_id",
        column2="user_id",
        string="Extra Time Off Approvers",
        compute="_compute_extra_approver_user_ids",
        store=True,
        readonly=True,
        help="Users who can approve/refuse this leave based on the leave type configuration.",
    )
    approval_actionable_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="hr_leave_approval_actionable_user_rel",
        column1="leave_id",
        column2="user_id",
        string="Can act on approval (technical)",
        compute="_compute_approval_actionable_user_ids",
        store=True,
        readonly=True,
        help="Users who can approve, validate, refuse, or use an extended approval action on this request.",
    )
    responsible_approval_line_ids = fields.One2many(
        comodel_name="hr.leave.responsible.approval",
        inverse_name="leave_id",
        string="Responsible Approval Log",
        readonly=True,
    )
    can_responsible_approve = fields.Boolean(
        string="Can Approve (Responsible Flow)",
        compute="_compute_can_responsible_approve",
    )
    handover_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_leave_handover_employee_rel",
        column1="leave_id",
        column2="employee_id",
        string="Work Handover To",
        help="Colleagues who receive work handover while this employee is on leave (max 5).",
    )
    unavailable_handover_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        compute="_compute_unavailable_handover_employee_ids",
        string="Unavailable handover recipients",
        help="Employees already on time off during this leave period.",
    )
    handover_acceptance_ids = fields.One2many(
        comodel_name="hr.leave.handover.acceptance",
        inverse_name="leave_id",
        string="Work Handover Details",
        copy=False,
    )
    can_respond_handover = fields.Boolean(
        string="Can respond to work handover",
        compute="_compute_can_respond_handover",
    )
    handover_waiting_label = fields.Char(
        string="Handover status",
        compute="_compute_handover_waiting_label",
    )
    handover_refused_label = fields.Char(
        string="Handover refused status",
        compute="_compute_handover_refused_label",
    )
    handover_refusal_reason_label = fields.Text(
        string="Handover refusal reasons",
        compute="_compute_handover_refusal_reason_label",
    )
    handover_requested_at = fields.Datetime(
        string="Handover requested at",
        copy=False,
        help="Timestamp when this leave was submitted with work handover recipients.",
    )
    handover_escalated = fields.Boolean(
        string="Handover escalated",
        default=False,
        copy=False,
        help="Set when no recipient accepts handover within timeout and the request is escalated.",
    )
    handover_escalated_at = fields.Datetime(
        string="Handover escalated at",
        copy=False,
    )
    handover_escalation_level = fields.Integer(
        string="Handover escalation level",
        default=0,
        copy=False,
        help="0: not escalated, 1: escalated to department head, 2: escalated to department manager.",
    )
    handover_escalation_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Handover escalation owner",
        copy=False,
        help="Department head from org chart who can assign a replacement handover recipient.",
    )
    handover_last_bot_escalation_signature = fields.Char(
        string="Handover last bot escalation signature",
        copy=False,
        help="Technical field to avoid duplicate escalation bot DMs for same leave/owner/level.",
    )
    handover_escalation_label = fields.Char(
        string="Handover escalation status",
        compute="_compute_handover_escalation_label",
    )
    handover_escalation_pick_prompt = fields.Char(
        string="Handover escalation — assign recipient instruction",
        compute="_compute_handover_escalation_pick_prompt",
    )
    handover_assigned_recipient_banner = fields.Char(
        string="Handover — assigned recipient notice",
        compute="_compute_handover_assigned_recipient_banner",
    )
    handover_recipient_list_readonly = fields.Boolean(
        string="Handover recipient cannot edit list",
        compute="_compute_handover_recipient_list_readonly",
    )
    handover_sheet_hidden_for_viewer = fields.Boolean(
        string="Hide Work Handover To table",
        compute="_compute_handover_sheet_hidden_for_viewer",
        help="Handover recipients (not the applicant) do not see the editable roster; avoids confusion after accepting.",
    )
    can_manage_handover_replacement = fields.Boolean(
        string="Can manage handover replacement",
        compute="_compute_can_manage_handover_replacement",
    )
    handover_replacement_picker_open = fields.Boolean(
        string="Handover replacement picker open",
        default=False,
        copy=False,
        help="UI only: requester chose to replace a refused handover recipient.",
    )
    handover_refused_recipient_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Refused handover recipients (technical)",
        compute="_compute_handover_refused_recipient_ids",
    )
    handover_replaceable_recipient_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Replaceable handover recipients (technical)",
        compute="_compute_handover_replaceable_recipient_ids",
    )
    handover_replacement_draft_ids = fields.One2many(
        comodel_name="hr.leave.handover.replacement.draft",
        inverse_name="leave_id",
        string="Handover replacement lines",
        copy=False,
    )
    skip_work_handover = fields.Boolean(
        string="Không cần bàn giao công việc",
        default=False,
        copy=False,
        help="Allow eligible senior employees to submit leave without handover recipients.",
    )
    can_skip_work_handover = fields.Boolean(
        string="Can skip work handover",
        compute="_compute_can_skip_work_handover",
    )
    approval_current_step_label = fields.Char(
        string="Current approval",
        compute="_compute_approval_current_step_label",
    )
    is_emergency_leave = fields.Boolean(
        string="Emergency leave (short notice)",
        default=False,
        copy=False,
        help="Set when the request is submitted with less advance notice than policy requires.",
    )
    emergency_leave_approver_notice = fields.Char(
        string="Emergency",
        compute="_compute_emergency_leave_approver_notice",
        store=True,
        help="Warning marker for approvers when this is emergency leave. "
        "Empty for employees who only have a work handover role on this request.",
    )

    def _register_hook(self):
        """Ensure DB columns exist on every registry load (not only on module -u)."""
        super()._register_hook()
        if self._name != "hr.leave":
            return
        cr = self.env.cr
        created_notice_column = False
        for column_name, column_type in (
            ("is_emergency_leave", "boolean"),
            ("emergency_leave_approver_notice", "varchar"),
            ("handover_replacement_picker_open", "boolean"),
            ("handover_requested_at", "timestamp"),
            ("handover_escalated", "boolean"),
            ("handover_escalated_at", "timestamp"),
            ("handover_escalation_level", "int4"),
            ("handover_escalation_user_id", "int4"),
            ("handover_last_bot_escalation_signature", "varchar"),
            ("skip_work_handover", "boolean"),
        ):
            cr.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                  AND table_schema = current_schema
                """,
                ("hr_leave", column_name),
            )
            if cr.fetchone():
                continue
            try:
                sql.create_column(cr, "hr_leave", column_name, column_type)
                if column_name == "emergency_leave_approver_notice":
                    created_notice_column = True
            except Exception:
                cr.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                      AND table_schema = current_schema
                    """,
                    ("hr_leave", column_name),
                )
                if not cr.fetchone():
                    raise
        if created_notice_column:
            leaves = self.env["hr.leave"].sudo().search([])
            if leaves:
                leaves._compute_emergency_leave_approver_notice()

    @api.depends(
        "employee_id",
        "employee_id.job_title",
        "employee_id.current_version_id",
        "employee_id.current_version_id.job_title",
    )
    def _compute_can_skip_work_handover(self):
        for leave in self:
            leave.can_skip_work_handover = leave._can_skip_work_handover_by_job_title(
                leave._get_effective_employee_for_skip_handover()
            )

    def _get_effective_employee_for_skip_handover(self):
        """The employee the rule applies to (the requester on the time off, not the current user)."""
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        if self.env.user.employee_id:
            return self.env.user.employee_id
        return self.env["hr.employee"]

    def _read_job_title_safely(self, employee):
        """Read `job_title` on hr.employee, falling back to current hr.version in sudo if ACL hides it.

        The Work tab in HR stores job title on the employee version model; the ORM can expose
        it as a normal field, but in some access setups it is safer to read the underlying
        `current_version_id.job_title` with elevated rights.
        """
        if not employee:
            return False
        if employee.job_title:
            return employee.job_title
        if employee.current_version_id and employee.current_version_id.job_title:
            return employee.sudo().current_version_id.job_title
        if employee.sudo().current_version_id and employee.sudo().current_version_id.job_title:
            return employee.sudo().current_version_id.job_title
        return False

    def _can_skip_workover_rank_for_employee(self, employee):
        """True when employee job title is at least `trưởng bộ phận` on the company selection scale."""
        self.ensure_one()
        threshold = _normalize_job_title_key(_DEPARTMENT_HEAD_JOB_TITLE_KEY)
        rank_map = _job_title_rank_map()
        threshold_rank = rank_map.get(threshold)
        if threshold_rank is None:
            return False
        raw = self._read_job_title_safely(employee)
        key = _normalize_job_title_key(raw)
        if not key:
            return False
        rank = rank_map.get(key)
        if rank is None:
            return False
        return rank >= threshold_rank

    def _can_skip_work_handover_by_job_title(self, employee):
        return self._can_skip_workover_rank_for_employee(employee)

    @api.constrains(
        "skip_work_handover",
        "employee_id",
        "employee_id.job_title",
        "employee_id.current_version_id",
        "employee_id.current_version_id.job_title",
    )
    def _check_skip_work_handover_permission(self):
        for leave in self.filtered("skip_work_handover"):
            target_employee = leave._get_effective_employee_for_skip_handover()
            if not leave._can_skip_workover_rank_for_employee(target_employee):
                title_raw = leave._read_job_title_safely(target_employee)
                raise ValidationError(
                    _(
                        "Chỉ nhân viên có chức danh từ Trưởng bộ phận trở lên mới được phép bỏ qua bàn giao công việc. "
                        "Nhân viên hiện tại: %(employee)s, chức danh: %(title)s."
                    )
                    % {
                        "employee": target_employee.display_name or "-",
                        "title": title_raw or "-",
                    }
                )

    # --- Advance notice vs job title (emergency leave) -----------------------------------------

    def _m2o_id(self, val):
        if val in (False, None):
            return False
        if isinstance(val, models.Model):
            return val.id
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    def _parse_date_val(self, val):
        if val in (False, None):
            return False
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            return fields.Date.from_string(val)
        return val

    def _required_lead_days_for_job_title(self, job_title):
        """Return minimum calendar days between today and leave start, or None if exempt."""
        if job_title == _DIRECTOR_JOB_TITLE_KEY:
            return None
        if job_title in _SHORT_LEAD_JOB_KEYS:
            return _SHORT_LEAD_DAYS
        return _DEFAULT_LEAD_DAYS

    def _merge_vals_for_emergency_check(self, vals, leave=None):
        """Merge write/create vals with existing leave for preview and enforcement."""
        merged = dict(vals or {})
        if leave:
            leave = leave[:1]
            for key in ("employee_id", "request_date_from", "request_date_to"):
                if key not in merged:
                    merged[key] = leave[key]
        return merged

    def _emergency_leave_violation_info(self, merged_vals, leave=None):
        """Return dict with keys: exempt, violation, required_days, delta_days, start_date."""
        if self.env.context.get(_SKIP_EMERGENCY_LEAVE_CHECK_CTX):
            return {"exempt": True, "violation": False}
        employee_id = self._m2o_id(merged_vals.get("employee_id"))
        if not employee_id and leave:
            employee_id = leave.employee_id.id
        employee = self.env["hr.employee"].sudo().browse(employee_id) if employee_id else self.env["hr.employee"]
        if not employee:
            return {"exempt": True, "violation": False}
        job_title = employee.job_title
        required = self._required_lead_days_for_job_title(job_title)
        if required is None:
            return {"exempt": True, "violation": False}
        start = self._parse_date_val(merged_vals.get("request_date_from"))
        if not start and leave:
            start = leave.request_date_from
        if not start:
            return {"exempt": True, "violation": False}
        today = fields.Date.context_today(self)
        delta = (start - today).days
        violation = delta < required
        return {
            "exempt": False,
            "violation": violation,
            "required_days": required,
            "delta_days": delta,
            "start_date": start,
        }

    def _apply_emergency_leave_on_vals(self, vals, leave=None):
        """Set is_emergency_leave on vals; raise UserError if violation without confirmation."""
        if self.env.context.get(_SKIP_EMERGENCY_LEAVE_CHECK_CTX) or self.env.context.get("leave_fast_create"):
            return
        merged = self._merge_vals_for_emergency_check(vals, leave=leave)
        info = self._emergency_leave_violation_info(merged, leave=leave)
        if info.get("exempt"):
            vals.setdefault("is_emergency_leave", False)
            return
        if not info.get("violation"):
            vals["is_emergency_leave"] = False
            return
        if self.env.context.get(_EMERGENCY_LEAVE_CTX):
            vals["is_emergency_leave"] = True
            return
        raise UserError(
            _(
                "This time off request does not meet the advance-notice rule. "
                "Confirm emergency leave in the application, or create the request with the "
                "“%(ctx)s” context key set to True.",
                ctx=_EMERGENCY_LEAVE_CTX,
            )
        )

    @api.model
    def check_emergency_leave_lead_time(self, res_id=False, vals=None):
        """Used by the UI before save. Returns needs_confirmation and translated dialog strings."""
        vals = vals or {}
        leave = self.env["hr.leave"]
        if res_id:
            leave = self.browse(res_id).exists()
            if leave:
                leave.check_access("read")
                leave.ensure_one()
        else:
            self.check_access("create")
        merged = self._merge_vals_for_emergency_check(vals, leave=leave if res_id and leave else None)
        info = self._emergency_leave_violation_info(merged, leave=leave if res_id and leave else None)
        if info.get("exempt") or not info.get("violation"):
            return {
                "needs_confirmation": False,
                "title": "",
                "message": "",
            }
        return {
            "needs_confirmation": True,
            "title": _("Xác nhận nghỉ khẩn cấp"),
            "message": _(
                "Bạn đang gửi đơn nghỉ khẩn cấp (thời gian báo trước ngắn hơn quy định). "
                "Bạn có chắc chắn muốn tiếp tục không?"
            ),
        }

    @api.depends(
        "is_emergency_leave",
        "can_approve",
        "can_validate",
        "can_refuse",
        "can_responsible_approve",
        "can_multi_step_approve",
        "approval_actionable_user_ids",
    )
    def _compute_emergency_leave_approver_notice(self):
        """Show a marker only to people who can approve/refuse this request (not handover-only)."""
        user = self.env.user
        is_manager = user.has_group("hr_holidays.group_hr_holidays_manager")
        for leave in self:
            if not leave.is_emergency_leave:
                leave.emergency_leave_approver_notice = ""
                continue
            if is_manager:
                leave.emergency_leave_approver_notice = "\u26a0"
                continue
            if (
                leave.can_approve
                or leave.can_validate
                or leave.can_refuse
                or leave.can_responsible_approve
                or leave.can_multi_step_approve
                or user in leave.approval_actionable_user_ids
            ):
                leave.emergency_leave_approver_notice = "\u26a0"
            else:
                leave.emergency_leave_approver_notice = ""

    @api.constrains("handover_employee_ids")
    def _check_handover_employee_limit(self):
        for leave in self:
            if len(leave.handover_employee_ids) > 5:
                raise ValidationError(_("Bạn chỉ có thể chọn tối đa 5 người nhận bàn giao công việc."))

    @api.constrains("handover_acceptance_ids", "handover_acceptance_ids.employee_id")
    def _check_handover_duplicate_recipients(self):
        for leave in self:
            employees = leave.handover_acceptance_ids.mapped("employee_id")
            if len(employees.ids) != len(set(employees.ids)):
                raise ValidationError(_("Mỗi người nhận bàn giao chỉ được xuất hiện một lần."))

    @api.constrains("state", "handover_acceptance_ids", "handover_acceptance_ids.handover_work_content")
    def _check_handover_content_required_on_submit(self):
        for leave in self:
            if leave.state not in ("confirm", "validate1", "validate"):
                continue
            if leave.skip_work_handover:
                continue
            missing_content = leave.handover_acceptance_ids.filtered(
                lambda line: line.employee_id and not (line.handover_work_content or "").strip()
            )
            if missing_content:
                raise ValidationError(
                    _(
                        "Vui lòng điền nội dung bàn giao công việc cho: %(names)s."
                    )
                    % {"names": ", ".join(missing_content.mapped("employee_id.name"))}
                )

    @api.constrains("state", "handover_employee_ids")
    def _check_handover_required_on_submit(self):
        for leave in self:
            if (
                leave.state in ("confirm", "validate1", "validate")
                and not leave.skip_work_handover
                and not leave.handover_employee_ids
            ):
                raise ValidationError(
                    _("Vui lòng chọn ít nhất một người nhận bàn giao công việc trước khi gửi đơn xin nghỉ phép.")
                )

    def _get_requested_interval(self):
        """Return (start_dt, end_dt) of the current leave request."""
        self.ensure_one()
        start_dt = self.date_from
        end_dt = self.date_to

        if not start_dt and self.request_date_from:
            start_dt = datetime.combine(self.request_date_from, time.min)

        if not end_dt:
            end_date = self.request_date_to or self.request_date_from
            if end_date:
                # Inclusive day range -> convert to half-open [start, end) interval.
                end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

        if start_dt and end_dt and end_dt <= start_dt:
            end_dt = start_dt + timedelta(minutes=1)
        return start_dt, end_dt

    def _get_unavailable_handover_employees(self):
        """Employees in handover list that already have overlapping time off."""
        self.ensure_one()
        if not self.handover_employee_ids:
            return self.env["hr.employee"]
        start_dt, end_dt = self._get_requested_interval()
        if not start_dt or not end_dt:
            return self.env["hr.employee"]
        overlapping = self.env["hr.leave"].sudo().search(
            [
                ("id", "!=", self.id or 0),
                ("employee_id", "in", self.handover_employee_ids.ids),
                ("state", "in", ("confirm", "validate1", "validate")),
                ("date_from", "<", end_dt),
                ("date_to", ">", start_dt),
            ]
        )
        return overlapping.mapped("employee_id")

    @api.depends(
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
        "employee_id",
        "employee_id.parent_id",
    )
    def _compute_unavailable_handover_employee_ids(self):
        Employee = self.env["hr.employee"]
        for leave in self:
            start_dt, end_dt = leave._get_requested_interval()
            if not start_dt or not end_dt:
                leave.unavailable_handover_employee_ids = Employee
                continue
            overlapping = self.env["hr.leave"].sudo().search(
                [
                    ("id", "!=", leave.id or 0),
                    ("state", "in", ("confirm", "validate1", "validate")),
                    ("date_from", "<", end_dt),
                    ("date_to", ">", start_dt),
                ]
            )
            leave.unavailable_handover_employee_ids = overlapping.mapped("employee_id")

    @api.constrains(
        "handover_employee_ids",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
        "state",
    )
    def _check_handover_employee_availability(self):
        for leave in self.filtered("handover_employee_ids"):
            unavailable = leave._get_unavailable_handover_employees()
            if unavailable:
                raise ValidationError(
                    _(
                        "Người nhận bàn giao đã chọn đang nghỉ phép trong giai đoạn này: %(names)s. "
                        "Vui lòng chọn đồng nghiệp khác."
                    )
                    % {"names": ", ".join(unavailable.mapped("name"))}
                )

    @api.onchange(
        "handover_employee_ids",
        "request_date_from",
        "request_date_to",
        "request_hour_from",
        "request_hour_to",
        "request_date_from_period",
        "request_date_to_period",
    )
    def _onchange_handover_employee_availability(self):
        for leave in self.filtered("handover_employee_ids"):
            unavailable = leave._get_unavailable_handover_employees()
            if unavailable:
                allowed = leave.handover_employee_ids - unavailable
                leave.update({"handover_employee_ids": [Command.set(allowed.ids)]})
                return {
                    "domain": {
                        "handover_employee_ids": [
                            ("id", "not in", unavailable.ids),
                            ("id", "!=", leave.employee_id.id),
                            ("user_id", "!=", False),
                        ]
                    },
                    "warning": {
                        "title": _("Cảnh báo kiểm tra dữ liệu"),
                        "message": _(
                            "Không thể phân công bàn giao cho %(names)s vì họ đang nghỉ phép trong giai đoạn này. "
                            "Những người này đã được xóa khỏi danh sách. Vui lòng chọn người khác."
                        )
                        % {"names": ", ".join(unavailable.mapped("name"))},
                    }
                }

    @api.onchange("handover_acceptance_ids", "handover_acceptance_ids.employee_id")
    def _onchange_handover_acceptance_ids(self):
        for leave in self:
            for idx, line in enumerate(leave.handover_acceptance_ids, start=1):
                line.sequence = idx
            employees = leave.handover_acceptance_ids.mapped("employee_id")
            leave.handover_employee_ids = [Command.set(employees.ids)]

    def _resequence_handover_acceptance_lines(self):
        for leave in self:
            lines = leave.handover_acceptance_ids.sudo().sorted(lambda l: (l.sequence or 0, l.id or 0))
            expected = 1
            for line in lines:
                if line.sequence != expected:
                    line.sequence = expected
                expected += 1
        return self

    def _sync_handover_employees_from_acceptance(self):
        for leave in self:
            line_employees = leave.handover_acceptance_ids.mapped("employee_id")
            if set(line_employees.ids) != set(leave.handover_employee_ids.ids):
                leave.with_context(skip_handover_line_sync=True).write(
                    {"handover_employee_ids": [Command.set(line_employees.ids)]}
                )
            leave._resequence_handover_acceptance_lines()
        return self

    @api.depends(
        "state",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_employee_ids",
    )
    def _compute_can_respond_handover(self):
        for leave in self:
            leave.can_respond_handover = False
            if leave.state != "confirm":
                continue
            emp = leave.env.user.employee_id
            if not emp or emp not in leave.handover_employee_ids:
                continue
            line = leave.handover_acceptance_ids.filtered(lambda l: l.employee_id == emp)[:1]
            leave.can_respond_handover = bool(line and line.state == "pending")

    @api.depends(
        "state",
        "handover_employee_ids",
        "handover_employee_ids.name",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.employee_id.name",
    )
    def _compute_handover_waiting_label(self):
        for leave in self:
            leave.handover_waiting_label = False
            if leave.state not in ("confirm", "validate1") or not leave.handover_employee_ids:
                continue
            waiting = leave._get_handover_blocking_employees()
            if waiting:
                leave.handover_waiting_label = _("Đang chờ bàn giao: %s") % ", ".join(waiting.mapped("name"))
            else:
                leave.handover_waiting_label = _("Tất cả người nhận bàn giao đã chấp nhận")

    @api.depends(
        "state",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.employee_id.name",
    )
    def _compute_handover_refused_label(self):
        for leave in self:
            leave.handover_refused_label = False
            if leave.state not in ("confirm", "validate1"):
                continue
            refused = leave.handover_acceptance_ids.filtered(lambda l: l.state == "refused").mapped("employee_id")
            if refused:
                leave.handover_refused_label = _("Từ chối bàn giao: %s") % ", ".join(refused.mapped("name"))

    @api.depends(
        "state",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.employee_id.name",
        "handover_acceptance_ids.refusal_reason",
    )
    def _compute_handover_refusal_reason_label(self):
        for leave in self:
            leave.handover_refusal_reason_label = False
            if leave.state not in ("confirm", "validate1"):
                continue
            refused_lines = leave.handover_acceptance_ids.filtered(lambda line: line.state == "refused")
            items = []
            for line in refused_lines:
                if line.refusal_reason:
                    items.append(_("%(name)s: %(reason)s") % {"name": line.employee_id.name, "reason": line.refusal_reason})
            leave.handover_refusal_reason_label = "\n".join(items) if items else False

    @api.depends(
        "state",
        "validation_type",
        "multi_step_current",
        "holiday_status_id",
        "holiday_status_id.multi_approval_step_ids",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
    )
    def _compute_status_display_label(self):
        selection = dict(self._fields["state"].selection)
        for leave in self:
            label = selection.get(leave.state)
            if leave.state in ("confirm", "validate1"):
                # Determine approval-flow state from underlying workflow data
                # (instead of relying on a display label compute order).
                in_approval_flow = False
                if leave.validation_type == "employee_hr_responsibles":
                    in_approval_flow = bool(
                        leave.responsible_approval_line_ids.filtered(
                            lambda line: line.state == "pending"
                        )[:1]
                    )
                elif leave.validation_type == "multi_step_6":
                    in_approval_flow = bool(leave._get_current_multi_step())
                else:
                    # Default Odoo approval states are approval flow.
                    in_approval_flow = True

                if in_approval_flow:
                    label = _("Đang chờ duyệt")
                elif leave._get_handover_blocking_employees():
                    label = _("Đang chờ bàn giao công việc")
                else:
                    label = _("Đang chờ duyệt")
            leave.status_display_label = label

    @api.depends(
        "state",
        "employee_id",
        "employee_id.user_id",
        "handover_refused_label",
        "handover_escalated",
        "handover_escalation_user_id",
    )
    def _compute_can_manage_handover_replacement(self):
        for leave in self:
            requester_can = bool(
                leave.state in ("confirm", "validate1")
                and leave.employee_id
                and leave.employee_id.user_id == leave.env.user
                and not leave.handover_escalated
            )
            escalation_owner_can = bool(
                leave.state in ("confirm", "validate1")
                and leave.handover_escalated
                and leave.handover_escalation_user_id
                and leave.handover_escalation_user_id == leave.env.user
            )
            leave.can_manage_handover_replacement = bool(
                (requester_can and leave.handover_refused_label)
                or escalation_owner_can
            )

    @api.depends(
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_handover_refused_recipient_ids(self):
        for leave in self:
            refused = leave.handover_acceptance_ids.filtered(lambda l: l.state == "refused").mapped(
                "employee_id"
            )
            leave.handover_refused_recipient_ids = refused

    @api.depends(
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_escalated",
        "handover_employee_ids",
    )
    def _compute_handover_replaceable_recipient_ids(self):
        for leave in self:
            if leave.handover_escalated:
                replaceable = leave.handover_acceptance_ids.filtered(
                    lambda l: l.state in ("pending", "refused")
                ).mapped("employee_id")
                leave.handover_replaceable_recipient_ids = replaceable
            else:
                leave.handover_replaceable_recipient_ids = leave.handover_refused_recipient_ids

    @api.depends(
        "state",
        "handover_escalated",
        "handover_escalated_at",
        "handover_escalation_user_id",
    )
    def _compute_handover_escalation_label(self):
        for leave in self:
            leave.handover_escalation_label = False
            if leave.state not in ("confirm", "validate1") or not leave.handover_escalated:
                continue
            owner_name = (
                leave.handover_escalation_user_id.display_name
                if leave.handover_escalation_user_id
                else _("Trưởng bộ phận")
            )
            leave.handover_escalation_label = _(
                "Handover timeout: escalated to %(owner)s for replacement assignment."
            ) % {"owner": owner_name}

    @api.depends(
        "state",
        "handover_employee_ids",
        "handover_escalation_user_id",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.assigned_by_user_id",
        "handover_acceptance_ids.reassigned_by_escalation_owner",
        "handover_requested_at",
        "create_date",
    )
    @api.depends_context("uid")
    def _compute_handover_escalation_pick_prompt(self):
        """Reminder for requester / manager to assign handover. Not shown to colleagues who must Accept/Refuse."""
        for leave in self:
            leave.handover_escalation_pick_prompt = False
            if leave._current_user_is_pending_handover_recipient():
                continue
            if not leave.handover_escalated:
                continue
            if not leave.handover_escalation_user_id or leave.handover_escalation_user_id != leave.env.user:
                continue
            pending_lines = leave.handover_acceptance_ids.filtered(
                lambda l: l.employee_id in leave.handover_employee_ids and l.state == "pending"
            )
            if pending_lines.filtered(
                lambda l: l.reassigned_by_escalation_owner
                or (
                    l.assigned_by_user_id
                    and leave.employee_id.user_id
                    and l.assigned_by_user_id != leave.employee_id.user_id
                )
            ):
                continue
            if not leave._handover_past_due_without_any_acceptance():
                continue
            leave.handover_escalation_pick_prompt = _(
                "Sau khoảng thời gian quy định, không ai nhận bàn giao công việc. "
                "Xin vui lòng chọn người nhận bàn giao công việc cho người nộp đơn."
            )

    @api.depends(
        "state",
        "company_id",
        "employee_id",
        "employee_id.name",
        "employee_id.user_id",
        "employee_id.job_title",
        "handover_escalated",
        "handover_escalation_user_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.assigned_by_user_id",
        "handover_acceptance_ids.reassigned_by_escalation_owner",
    )
    @api.depends_context("uid")
    def _compute_handover_assigned_recipient_banner(self):
        """Handover colleague (not the applicant): who picked them + applicant name."""
        for leave in self:
            leave.handover_assigned_recipient_banner = False
            if leave.state not in ("confirm", "validate1"):
                continue
            viewer_emp = leave.env.user.sudo().employee_id
            if (
                not viewer_emp
                or not leave.employee_id
                or viewer_emp == leave.employee_id
                or viewer_emp not in leave.handover_employee_ids
            ):
                continue
            line = leave.handover_acceptance_ids.filtered(lambda l: l.employee_id == viewer_emp)[:1]
            if not line or line.state != "pending":
                continue
            who = leave._handover_who_label_for_line(line)
            applicant = leave.employee_id.name if leave.employee_id else ""
            if applicant:
                leave.handover_assigned_recipient_banner = _(
                    "Bạn được yêu cầu bàn giao công việc khi %(name)s nghỉ."
                ) % {"name": applicant}

    @api.depends(
        "state",
        "employee_id",
        "handover_employee_ids",
        "handover_escalated",
        "handover_escalation_user_id",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.assigned_by_user_id",
    )
    @api.depends_context("uid")
    def _compute_handover_recipient_list_readonly(self):
        for leave in self:
            leave.handover_recipient_list_readonly = False
            if leave.state not in ("draft", "confirm"):
                continue
            leave.handover_recipient_list_readonly = not leave._viewer_can_manage_handover_acceptance_sheet()

    @api.depends(
        "employee_id",
        "handover_employee_ids",
        "handover_escalated",
        "handover_escalation_user_id",
    )
    @api.depends_context("uid")
    def _compute_handover_sheet_hidden_for_viewer(self):
        """Do not show the one2many roster to colleagues who were picked as handover recipients."""
        for leave in self:
            leave.handover_sheet_hidden_for_viewer = False
            user = leave.env.user
            viewer_emp = user.sudo().employee_id
            if not viewer_emp or not leave.employee_id:
                continue
            if viewer_emp == leave.employee_id:
                continue
            if (
                leave.handover_escalated
                and leave.handover_escalation_user_id
                and user == leave.handover_escalation_user_id
            ):
                continue
            if viewer_emp in leave.handover_employee_ids:
                leave.handover_sheet_hidden_for_viewer = True

    @api.depends(
        "holiday_status_id",
        "holiday_status_id.extra_responsible_user_ids",
        "holiday_status_id.extra_responsible_department_ids",
        "validation_type",
        "multi_step_current",
        "employee_id",
        "employee_id.hr_responsible_ids",
        "employee_id.hr_responsible_id",
        "holiday_status_id.multi_approval_step_ids",
        "holiday_status_id.multi_approval_step_ids.approver_user_id",
        "holiday_status_id.multi_approval_step_ids.approver_user_ids",
        "holiday_status_id.multi_approval_step_ids.approver_department_ids",
        "holiday_status_id.employee_responsible_source",
        "holiday_status_id.special_director_employee_line_ids",
        "holiday_status_id.special_director_employee_line_ids.employee_id",
        "holiday_status_id.special_director_sequential_approval",
        "holiday_status_id.special_director_order_line_ids",
        "holiday_status_id.special_director_order_line_ids.employee_id",
        "employee_id.parent_id",
        "employee_id.parent_id.parent_id",
        "employee_id.parent_id.parent_id.parent_id",
        "employee_id.parent_id.parent_id.parent_id.parent_id",
        "employee_id.parent_id.parent_id.parent_id.parent_id.parent_id",
    )
    def _compute_extra_approver_user_ids(self):
        for leave in self:
            if leave.validation_type == "multi_step_6":
                step = leave._get_current_multi_step()
                leave.extra_approver_user_ids = step and step._get_all_approver_users() or self.env["res.users"]
                continue

            if leave.validation_type == "employee_hr_responsibles":
                leave.extra_approver_user_ids = leave._get_responsible_approval_users()
                continue

            users = leave.holiday_status_id.extra_responsible_user_ids
            if leave.holiday_status_id.extra_responsible_department_ids:
                dept_users = leave.holiday_status_id.extra_responsible_department_ids.mapped("member_ids.user_id")
                dept_users = dept_users.filtered(lambda u: u and not u.share)
                users |= dept_users
            leave.extra_approver_user_ids = users

    @api.depends(
        "state",
        "employee_id",
        "employee_id.job_title",
        "employee_id.leave_manager_id",
        "holiday_status_id",
        "holiday_status_id.responsible_ids",
        "extra_approver_user_ids",
        "multi_step_current",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
        "responsible_approval_line_ids.user_id",
    )
    def _compute_approval_actionable_user_ids(self):
        """Users for whom at least one approval action would be allowed (matches Kanban/form buttons)."""
        Users = self.env["res.users"]
        group_user = self.env.ref("hr_holidays.group_hr_holidays_user")
        group_manager = self.env.ref("hr_holidays.group_hr_holidays_manager")
        # Odoo 19: res.users uses group_ids / all_group_ids — not groups_id (invalid domain field).
        base_hr = Users.sudo().search(
            [
                "&",
                ("share", "=", False),
                "|",
                ("all_group_ids", "in", [group_user.id]),
                ("all_group_ids", "in", [group_manager.id]),
            ]
        )
        manager_users = base_hr.filtered(lambda u: group_manager in u.all_group_ids)

        for leave in self:
            if not leave.id or leave.state not in ("confirm", "validate1"):
                leave.approval_actionable_user_ids = Users
                continue

            # Custom flows: compute from current workflow state directly.
            if leave.validation_type == "employee_hr_responsibles":
                pending = leave.responsible_approval_line_ids.filtered(
                    lambda l: l.state == "pending" and l.user_id and not l.user_id.share
                ).sorted(lambda l: (l.sequence, l.id))
                if not pending:
                    leave.approval_actionable_user_ids = Users
                    continue
                mode = leave.holiday_status_id.employee_responsible_approval_mode or "any"
                if mode == "sequential":
                    leave.approval_actionable_user_ids = leave._responsible_pending_current_wave().mapped("user_id")
                else:
                    leave.approval_actionable_user_ids = pending.mapped("user_id")
                continue

            if leave.validation_type == "multi_step_6":
                actionable = leave._get_multi_step_approvers().filtered(lambda u: u and not u.share)
                leave.approval_actionable_user_ids = actionable | manager_users
                continue

            candidates = base_hr | leave.extra_approver_user_ids
            if leave.employee_id.leave_manager_id:
                candidates |= leave.employee_id.leave_manager_id
            if leave.holiday_status_id.responsible_ids:
                candidates |= leave.holiday_status_id.responsible_ids
            if leave.validation_type == "multi_step_6":
                candidates |= leave._get_multi_step_approvers()

            candidates = candidates.filtered(lambda u: u and not u.share)
            actionable = Users
            for user in candidates:
                lu = leave.with_user(user)
                if (
                    lu.can_approve
                    or lu.can_validate
                    or lu.can_refuse
                    or lu.can_multi_step_approve
                    or lu.can_responsible_approve
                ):
                    actionable |= user
            leave.approval_actionable_user_ids = actionable

    def _get_current_multi_step(self):
        """Return the currently active multi-step config for this leave."""
        self.ensure_one()
        if self.validation_type != "multi_step_6":
            return self.env["hr.leave.type.approval.step"]
        steps = self.holiday_status_id.multi_approval_step_ids
        return steps.filtered(lambda s: s.sequence == self.multi_step_current)[:1]

    def activity_update(self):
        """Make pending approval activities visible immediately in Today/Late filters."""
        res = super().activity_update()
        today = fields.Date.today()
        for leave in self.filtered(lambda l: l.state in ("confirm", "validate1")):
            xmlids = (
                ["hr_holidays.mail_act_leave_approval"]
                if leave.state == "confirm"
                else ["hr_holidays.mail_act_leave_second_approval"]
            )
            activities = leave.activity_search(xmlids, only_automated=True).filtered(
                lambda a: a.date_deadline and a.date_deadline > today
            )
            if activities:
                activities.write({"date_deadline": today})
        return res

    def _get_employee_responsible_users(self):
        self.ensure_one()
        users = self.employee_id.hr_responsible_ids
        if not users and self.employee_id.hr_responsible_id:
            users = self.employee_id.hr_responsible_id
        return users

    def _get_org_chart_approver_users_ordered(self):
        """Walk reporting line (parent_id) from direct manager upward: one approver per org level.

        The previous implementation matched at most one person per *job title tier* along the chain, so
        two managers with the same title (or a middle manager without a distinct tier) were skipped.
        This matches the org chart: Tester 3 → Tester 2 → … up to the top, each with a linked user.
        """
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return self.env["res.users"]
        user_ids = []
        seen = set()
        Users = self.env["res.users"]
        cur = employee.parent_id
        while cur:
            mgr = cur.sudo()
            if mgr.user_id and not mgr.user_id.share:
                uid = mgr.user_id.id
                if uid not in seen:
                    user_ids.append(uid)
                    seen.add(uid)
            cur = mgr.parent_id
        return Users.browse(user_ids)

    def _employee_hr_responsible_users_core(self):
        """Approver users from org chart or manual HR responsible fields (no sequential sort / director expansion)."""
        self.ensure_one()
        if self.holiday_status_id.employee_responsible_source == "org_chart":
            users = self._get_org_chart_approver_users_ordered()
            # Direct manager must be able to approve first: org-chart tiers can omit them if title read failed.
            parent = self.employee_id.parent_id.sudo() if self.employee_id else self.env["hr.employee"]
            if parent and parent.user_id and not parent.user_id.share:
                pu = parent.user_id
                if pu.id not in users.ids:
                    users = pu | users
                elif users.ids and users.ids[0] != pu.id:
                    users = self.env["res.users"].browse([pu.id] + [uid for uid in users.ids if uid != pu.id])
            return users
        return self._get_employee_responsible_users()

    def _get_company_director_users(self):
        self.ensure_one()
        Employee = self.env["hr.employee"].sudo()
        domain = [
            ("job_title", "=", _DIRECTOR_JOB_TITLE_KEY),
            ("user_id", "!=", False),
        ]
        company = self.company_id or self.env.company
        if company:
            domain = ["&"] + domain + ["|", ("company_id", "=", False), ("company_id", "=", company.id)]
        employees = Employee.search(domain)
        users = employees.user_id.filtered(lambda u: u and not u.share)
        return users.sorted(key=lambda u: ((u.name or "").casefold(), u.id))

    def _get_configured_director_order_users(self):
        """Directors explicitly ordered on the leave type (STT); empty recordset when not configured."""
        self.ensure_one()
        lt = self.holiday_status_id
        if not lt or not lt.special_director_sequential_approval or not lt.special_director_order_line_ids:
            return self.env["res.users"]
        Users = self.env["res.users"]
        out_ids = []
        seen = set()
        for line in lt.special_director_order_line_ids.sorted(lambda l: (l.sequence, l.id)):
            emp = line.sudo().employee_id
            if (
                not emp
                or not emp.user_id
                or emp.user_id.share
                or (emp.job_title or "") != _DIRECTOR_JOB_TITLE_KEY
            ):
                continue
            uid = emp.user_id.id
            if uid not in seen:
                out_ids.append(uid)
                seen.add(uid)
        return Users.browse(out_ids)

    def _employee_hr_expanded_director_suffix_users(self):
        """Director users substituted at end of chain for multi-director-special employees."""
        self.ensure_one()
        lt = self.holiday_status_id
        configured = self._get_configured_director_order_users()
        if lt and lt.special_director_sequential_approval and configured:
            return configured
        return self._get_company_director_users()

    def _is_special_parallel_directors_leave(self):
        """Special employee flow: directors act in parallel (same step, simultaneous notify)."""
        self.ensure_one()
        lt = self.holiday_status_id
        return bool(lt and self._is_multi_director_special_employee() and not lt.special_director_sequential_approval)

    def _is_multi_director_special_employee(self):
        self.ensure_one()
        lt = self.holiday_status_id
        if not lt or not self.employee_id:
            return False
        specials = lt.special_director_employee_line_ids.mapped("employee_id")
        return bool(specials and self.employee_id in specials)

    def _employee_hr_maybe_expand_multi_director(self, users):
        """Sequential special list: replace from first Director in the chain with configured/all company directors."""
        self.ensure_one()
        if not self._is_multi_director_special_employee():
            return users
        directors = self._employee_hr_expanded_director_suffix_users()
        Users = self.env["res.users"]
        ordered_ids = list(users.ids)
        first_dir_idx = None
        for idx, uid in enumerate(ordered_ids):
            user = Users.browse(uid).sudo()
            emp = user.employee_id
            if emp and (emp.job_title or "") == _DIRECTOR_JOB_TITLE_KEY:
                first_dir_idx = idx
                break
        out_ids = []
        seen = set()
        if first_dir_idx is None:
            for uid in ordered_ids:
                if uid not in seen:
                    out_ids.append(uid)
                    seen.add(uid)
            for uid in directors.ids:
                if uid not in seen:
                    out_ids.append(uid)
                    seen.add(uid)
        else:
            for uid in ordered_ids[:first_dir_idx]:
                if uid not in seen:
                    out_ids.append(uid)
                    seen.add(uid)
            for uid in directors.ids:
                if uid not in seen:
                    out_ids.append(uid)
                    seen.add(uid)
        return Users.browse(out_ids)

    def _employee_hr_chain_contains_director(self, users):
        self.ensure_one()
        UsersMdl = self.env["res.users"]
        for uid in users.ids:
            u = UsersMdl.browse(uid).sudo()
            emp = u.employee_id
            if emp and (emp.job_title or "") == _DIRECTOR_JOB_TITLE_KEY:
                return True
        return False

    def _responsible_pending_current_wave(self):
        """Smallest-sequence pending line(s): one record, except parallel director wave → all directors at once."""
        self.ensure_one()
        pending = self.responsible_approval_line_ids.filtered(lambda l: l.state == "pending").sorted(
            lambda l: (l.sequence, l.id)
        )
        if not pending:
            return pending
        if not self._is_special_parallel_directors_leave():
            return pending[:1]
        wave_seq = pending[0].sequence
        return pending.filtered(lambda l: l.sequence == wave_seq)

    def _build_responsible_approval_sequences(self):
        """(user_record, sequence) after director expansion — parallel directors share same sequence."""
        self.ensure_one()
        Users = self.env["res.users"]
        users = self._get_responsible_approval_users()
        ids_order = list(users.ids)
        if not ids_order:
            return []
        if not self._is_special_parallel_directors_leave():
            return [(Users.browse(uid), idx + 1) for idx, uid in enumerate(ids_order)]
        split = None
        for i, uid in enumerate(ids_order):
            u = Users.browse(uid).sudo()
            emp = u.employee_id
            if emp and (emp.job_title or "") == _DIRECTOR_JOB_TITLE_KEY:
                split = i
                break
        if split is None:
            return [(Users.browse(uid), idx + 1) for idx, uid in enumerate(ids_order)]
        prefix = ids_order[:split]
        suffix = ids_order[split:]
        wave_seq = len(prefix) + 1
        pairs = [(Users.browse(uid), idx + 1) for idx, uid in enumerate(prefix)]
        pairs.extend((Users.browse(uid), wave_seq) for uid in suffix)
        return pairs

    def _get_responsible_approval_users(self):
        self.ensure_one()
        lt = self.holiday_status_id
        core = self._employee_hr_responsible_users_core()
        if not lt or lt.leave_validation_type != "employee_hr_responsibles":
            return core
        mode = lt.employee_responsible_approval_mode or "any"
        if mode != "sequential":
            return core
        ordered = core
        if lt.employee_responsible_source != "org_chart":
            ordered = self._sort_responsible_users_by_job_title(core)
        return self._employee_hr_maybe_expand_multi_director(ordered)

    def _sort_responsible_users_by_job_title(self, users):
        """Sequential chain order: trưởng nhóm → trưởng BP → kiểm soát → trưởng phòng HCNS → giám đốc (see hr_job_title_vn)."""
        self.ensure_one()
        order_index = {title: idx for idx, title in enumerate(_HR_RESPONSIBLE_APPROVAL_JOB_TITLE_ORDER)}
        return users.sorted(
            key=lambda u: _job_title_approval_sort_key(u, order_index)
        )

    def _employee_hr_blocks_self_approval_non_director(self, user=None):
        """In Employee HR Responsibles, only Giám đốc may approve/refuse their own request (others must not act on own leave)."""
        self.ensure_one()
        if self.validation_type != "employee_hr_responsibles":
            return False
        user = user or self.env.user
        emp = self.employee_id
        if not emp or not emp.user_id or emp.user_id != user:
            return False
        return (emp.job_title or "") != _DIRECTOR_JOB_TITLE_KEY

    def _get_multi_step_approvers(self):
        self.ensure_one()
        step = self._get_current_multi_step()
        return step and step._get_all_approver_users() or self.env["res.users"]

    def _multi_step_previous_steps_logged(self):
        """Steps 1..(current-1) must each appear in the approval log (sequential chain)."""
        self.ensure_one()
        if self.multi_step_current <= 1:
            return True
        done_seqs = set(self.multi_approval_line_ids.mapped("step_id.sequence"))
        needed = set(range(1, self.multi_step_current))
        return needed.issubset(done_seqs)

    def _bootstrap_handover_workflow(self):
        """Create handover acknowledgement rows and schedule activities (clock menu) for recipients."""
        if self.env.context.get("leave_fast_create") or self.env.context.get("mail_activity_automation_skip"):
            return self
        leaves = self.filtered(lambda l: l.state == "confirm" and l.handover_employee_ids)
        leaves._sync_handover_acceptance_lines()
        leaves._schedule_work_handover_activities()
        return self

    def _sync_handover_acceptance_lines(self):
        Acceptance = self.env["hr.leave.handover.acceptance"].sudo()
        for leave in self.filtered(lambda l: l.state in _HANDOVER_ACTIVE_STATES):
            current = leave.handover_employee_ids
            existing = leave.handover_acceptance_ids.sudo()
            to_remove = existing.filtered(lambda l: l.employee_id not in current)
            for line in to_remove:
                user = line.employee_id.user_id
                if user:
                    leave.activity_unlink(
                        [_HANDOVER_ACTIVITY_XMLID],
                        user_id=user.id,
                        only_automated=False,
                    )
            to_remove.unlink()
            existing = leave.handover_acceptance_ids.sudo()
            for emp in current:
                if not existing.filtered(lambda l: l.employee_id == emp):
                    line_vals = {
                        "leave_id": leave.id,
                        "employee_id": emp.id,
                    }
                    requester_user = leave.employee_id.user_id
                    if requester_user and not requester_user.share:
                        line_vals["assigned_by_user_id"] = requester_user.id
                    Acceptance.create(line_vals)
            leave._resequence_handover_acceptance_lines()
        return self

    def _handover_employee_for_assigner_user(self, user):
        """Resolve hr.employee for a user (company-aware; avoids wrong user.employee_id)."""
        self.ensure_one()
        if not user:
            return self.env["hr.employee"]
        Employee = self.env["hr.employee"].sudo()
        company = self.company_id or self.env.company
        if company:
            emp = Employee.search(
                [
                    ("user_id", "=", user.id),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if emp:
                return emp
        return Employee.search([("user_id", "=", user.id)], limit=1)

    def _handover_format_job_name_from_employee(self, emp):
        if not emp:
            return ""
        jt = (emp.job_title or "").strip()
        nm = (emp.name or "").strip()
        return f"{jt} {nm}".strip() if jt else nm

    def _handover_format_job_name_from_user(self, user):
        return self._handover_format_job_name_from_employee(self._handover_employee_for_assigner_user(user))

    def _handover_who_label_for_line(self, line):
        """Job title + name of the person who assigned this handover (BP, applicant, or other)."""
        self.ensure_one()
        leave = self
        assigner_user = line.assigned_by_user_id
        if line.reassigned_by_escalation_owner and leave.handover_escalation_user_id:
            return self._handover_format_job_name_from_user(leave.handover_escalation_user_id)
        if assigner_user and leave.handover_escalation_user_id and assigner_user == leave.handover_escalation_user_id:
            return self._handover_format_job_name_from_user(leave.handover_escalation_user_id)
        if (
            leave.handover_escalated
            and leave.handover_escalation_user_id
            and assigner_user
            and leave.employee_id
            and leave.employee_id.user_id
            and assigner_user == leave.employee_id.user_id
            and leave.handover_escalation_user_id != leave.employee_id.user_id
        ):
            return self._handover_format_job_name_from_user(leave.handover_escalation_user_id)
        if assigner_user and leave.employee_id and leave.employee_id.user_id and assigner_user == leave.employee_id.user_id:
            return self._handover_format_job_name_from_employee(leave.employee_id)
        if assigner_user:
            return self._handover_format_job_name_from_user(assigner_user)
        if leave.employee_id:
            return self._handover_format_job_name_from_employee(leave.employee_id)
        return ""

    def _handover_is_bp_handover_assignment(self, line):
        self.ensure_one()
        if self.handover_escalated and line.state == "pending":
            return True
        if line.reassigned_by_escalation_owner:
            return True
        if (
            self.handover_escalated
            and self.employee_id
            and self.employee_id.user_id
            and line.assigned_by_user_id
            and line.assigned_by_user_id != self.employee_id.user_id
        ):
            return True
        if self.handover_escalation_user_id and line.assigned_by_user_id == self.handover_escalation_user_id:
            return True
        if (
            self.handover_escalated
            and self.handover_escalation_user_id
            and self.employee_id
            and self.employee_id.user_id
            and line.assigned_by_user_id == self.employee_id.user_id
            and self.handover_escalation_user_id != self.employee_id.user_id
        ):
            return True
        return False

    def _handover_activity_note_for_line(self, line):
        """HTML body for clock menu handover activity (differs: requester vs trưởng BP reassignment)."""
        self.ensure_one()
        leave = self
        requester = leave.employee_id
        requester_name = requester.name if requester else leave.display_name
        applicant = requester_name
        leave_type = leave.holiday_status_id.name if leave.holiday_status_id else ""
        date_from = leave.request_date_from
        if not date_from and leave.date_from:
            date_from = leave.date_from.date()
        date_txt = format_date(self.env, date_from) if date_from else ""
        footer = _("Mở đơn và chọn Chấp nhận hoặc Từ chối bàn giao công việc.")
        who = leave._handover_who_label_for_line(line)
        if requester_name:
            first = _(
                "Bạn được yêu cầu bàn giao công việc khi %(name)s nghỉ "
                "(%(leave_type)s, %(dates)s)."
            ) % {"name": requester_name, "leave_type": leave_type, "dates": date_txt}
            return Markup("<p>%s</p><p>%s</p>") % (first, footer)
        first = _(
            "You were asked to cover work while %(name)s is away (%(leave_type)s, %(dates)s)."
        ) % {"name": requester_name, "leave_type": leave_type, "dates": date_txt}
        second = _("Mở yêu cầu này và chọn Chấp nhận bàn giao hoặc Từ chối bàn giao.")
        return Markup("<p>%s</p><p>%s</p>") % (first, second)

    def _refresh_handover_activity_notes_for_employees(self, employees):
        """After assigned_by_user_id is updated, rewrite open handover activities so the note matches."""
        self.ensure_one()
        today = fields.Date.today()
        for emp in employees:
            if not emp:
                continue
            user = emp.user_id
            if not user or user.share:
                continue
            line = self.handover_acceptance_ids.filtered(lambda l: l.employee_id == emp)[:1]
            if not line or line.state != "pending":
                continue
            note = self._handover_activity_note_for_line(line)
            acts = self.activity_search(
                [_HANDOVER_ACTIVITY_XMLID],
                user_id=user.id,
                only_automated=False,
            )
            if acts:
                acts.sudo().write({"note": note})
            else:
                self.activity_schedule(
                    _HANDOVER_ACTIVITY_XMLID,
                    date_deadline=today,
                    user_id=user.id,
                    note=note,
                )
        return self

    def _mark_pending_handover_lines_as_escalation_assigned(self):
        """When escalation owner edits recipients, keep pending lines tagged as BP-assigned."""
        self.ensure_one()
        if (
            not self.handover_escalated
            or not self.employee_id
            or not self.employee_id.user_id
            or self.env.user == self.employee_id.user_id
        ):
            return self
        pending_lines = self.handover_acceptance_ids.sudo().filtered(lambda l: l.state == "pending")
        if pending_lines:
            pending_lines.write(
                {
                    "assigned_by_user_id": self.env.user.id,
                    "reassigned_by_escalation_owner": True,
                }
            )
        return self

    def _schedule_work_handover_activities(self):
        today = fields.Date.today()
        for leave in self.filtered(
            lambda l: l.state in _HANDOVER_ACTIVE_STATES and l.handover_employee_ids
        ):
            for line in leave.handover_acceptance_ids.sudo().filtered(lambda l: l.state == "pending"):
                user = line.employee_id.user_id
                if not user or user.share:
                    continue
                open_act = leave.activity_search(
                    [_HANDOVER_ACTIVITY_XMLID],
                    user_id=user.id,
                    only_automated=False,
                )
                if open_act:
                    continue
                note = leave._handover_activity_note_for_line(line)
                leave.activity_schedule(
                    _HANDOVER_ACTIVITY_XMLID,
                    date_deadline=today,
                    user_id=user.id,
                    note=note,
                )
        return self

    def _mark_handover_requested_at(self):
        now = fields.Datetime.now()
        target = self.filtered(
            lambda l: l.state in ("confirm", "validate1")
            and l.handover_employee_ids
            and not l.handover_requested_at
        )
        if target:
            target.sudo().write({"handover_requested_at": now})
        return self

    def _get_org_chart_department_head_user(self):
        self.ensure_one()
        employee = self.employee_id
        expected = _normalize_job_title_key(_DEPARTMENT_HEAD_JOB_TITLE_KEY)
        while employee and employee.parent_id:
            manager = employee.parent_id.sudo()
            if (
                _normalize_job_title_key(manager.job_title) == expected
                and manager.user_id
                and not manager.user_id.share
            ):
                return manager.user_id
            employee = manager
        return self.env["res.users"]

    def _get_org_chart_department_manager_user_from_user(self, user):
        self.ensure_one()
        if not user:
            return self.env["res.users"]
        employee = self._handover_employee_for_assigner_user(user)
        expected = _normalize_job_title_key(_DEPARTMENT_MANAGER_JOB_TITLE_KEY)
        while employee and employee.parent_id:
            manager = employee.parent_id.sudo()
            if (
                _normalize_job_title_key(manager.job_title) == expected
                and manager.user_id
                and not manager.user_id.share
            ):
                return manager.user_id
            employee = manager
        return self.env["res.users"]

    def _get_next_manager_user_from_user(self, user):
        """Return the immediate next manager user in org chain."""
        self.ensure_one()
        if not user:
            return self.env["res.users"]
        employee = self._handover_employee_for_assigner_user(user)
        while employee and employee.parent_id:
            manager = employee.parent_id.sudo()
            if manager.user_id and not manager.user_id.share:
                return manager.user_id
            employee = manager
        return self.env["res.users"]

    def _notify_requester_handover_escalation_started_via_bot(self, hours):
        """DM from handover bot to leave requester when handover escalates to upper level."""
        self.ensure_one()
        requester_user = self.employee_id.user_id
        if not requester_user or requester_user.share or not requester_user.partner_id:
            return
        body = _(
            "Do không có ai nhận bàn giao việc cho bạn trong %(hours)s giờ nên phần này đã được chuyển lên cấp trên."
        ) % {"hours": hours}
        try:
            bot_user = (
                self.env.ref("business_discuss_bots.user_bot_handover", raise_if_not_found=False)
                or self.env.ref("base.user_root")
            )
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([requester_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send escalation-notify-requester bot chat leave_id=%s user_id=%s",
                self.id,
                requester_user.id,
            )

    def _notify_handover_timeout_escalation(self, dept_head_user, hours=None):
        self.ensure_one()
        if not dept_head_user or not dept_head_user.partner_id:
            return
        signature = "%s:%s:%s" % (self.id, dept_head_user.id, self.handover_escalation_level or 0)
        if self.handover_last_bot_escalation_signature == signature:
            return
        hours = hours if hours is not None else self._handover_escalation_after_hours()
        body = _(
            "Work handover for %(leave)s has no acceptance after %(hours)s hours. "
            "You are now assigned to choose a replacement handover recipient."
        ) % {
            "leave": self.display_name,
            "hours": hours,
        }
        self.message_post(
            body=body,
            message_type="notification",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[dept_head_user.partner_id.id],
        )
        requester_name = self.employee_id.name or self.employee_id.display_name or self.display_name
        bot_body = _(
            "Sau %(hours)s giờ, do không có ai nhận bàn giao đơn cho %(requester)s, "
            "vui lòng vào mục Time Off để quyết định."
        ) % {
            "hours": hours,
            "requester": requester_name,
        }
        try:
            bot_user = (
                self.env.ref("business_discuss_bots.user_bot_handover", raise_if_not_found=False)
                or self.env.ref("base.user_root")
            )
            chat = (
                self.env["discuss.channel"]
                .sudo()
                .with_user(dept_head_user)
                ._get_or_create_chat([bot_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=bot_body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            self.sudo().write({"handover_last_bot_escalation_signature": signature})
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send escalation bot chat leave_id=%s user_id=%s",
                self.id,
                dept_head_user.id,
            )
        self._notify_requester_handover_escalation_started_via_bot(hours=hours)
        existing_todo = self.activity_search(
            [_TODO_ACTIVITY_XMLID],
            user_id=dept_head_user.id,
            additional_domain=[("summary", "=", _("Chỉ định người thay thế bàn giao"))],
            only_automated=False,
        )
        if not existing_todo:
            self.activity_schedule(
                _TODO_ACTIVITY_XMLID,
                user_id=dept_head_user.id,
                summary=_("Chỉ định người thay thế bàn giao"),
                note=Markup("<p>%s</p><p>%s</p>") % (
                    body,
                    _("Mở yêu cầu này và chỉ định đồng nghiệp khác trong mục Người nhận bàn giao công việc."),
                ),
            )

    def _notify_handover_bot_leave_form_open_button_markup(self):
        """Purple pill link to this leave form (Discuss-safe HTML, sanitizer whitelist)."""
        self.ensure_one()
        base = (self.get_base_url() or "").rstrip("/")
        leave_url = f"{base}/web#id={self.id}&model=hr.leave&view_type=form"
        return Markup(
            '<a href="{href}" target="_blank" rel="noreferrer noopener" '
            'style="display:inline-block;padding:8px 18px;background-color:#714B67;'
            'color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600;'
            'font-size:14px;line-height:1.2;">{label}</a>'
        ).format(href=leave_url, label=_("Mở Time Off"))

    def _notify_specific_handover_recipients_via_bot(self, employees):
        """Discuss DM from handover bot: same wording as khi nộp đơn — chỉ gửi cho subset người nhận."""
        self.ensure_one()
        if not employees:
            return
        requester_name = (
            self.employee_id.name or self.employee_id.display_name or self.display_name
        )
        date_from = self.request_date_from or (self.date_from and self.date_from.date())
        date_text = date_from.strftime("%d/%m/%Y") if date_from else ""
        button_html = self._notify_handover_bot_leave_form_open_button_markup()
        bot_user = self.env.ref("business_discuss_bots.user_bot_handover", raise_if_not_found=False) or self.env.ref(
            "base.user_root"
        )
        bot_partner_id = bot_user.partner_id.id if bot_user and bot_user.partner_id else False
        channel_model = self.env["discuss.channel"].sudo()
        sent_count = 0
        for recipient in employees:
            user = recipient.user_id
            if not user or not user.partner_id:
                _logger.info(
                    "time_off_extra_approval: skip handover bot DM leave_id=%s employee_id=%s (no user or partner)",
                    self.id,
                    recipient.id,
                )
                continue
            line = self.handover_acceptance_ids.filtered(lambda l: l.employee_id == recipient)[:1]
            work_content = (line.handover_work_content or "").strip()
            content_text = work_content or _("Không có")
            # Avoid %% formatting for user/translated text (can break on % in PO strings or handover text).
            intro = Markup(
                _(
                    "Nhân viên: <b>{requester}</b> nhờ bàn giao công việc nghỉ ốm<br/>"
                    "Ngày nghỉ: <b>{date}</b><br/>"
                    "Nội dung: "
                )
            ).format(requester=requester_name, date=date_text)
            body = (
                intro
                + escape(str(content_text))
                + Markup(_("<br/>Vui lòng bấm vào Time Off để xác nhận công việc bàn giao.<br/><br/>"))
                + button_html
            )
            post_vals = {
                "body": body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
            }
            if bot_partner_id:
                post_vals["author_id"] = bot_partner_id
            try:
                chat = channel_model.with_user(bot_user)._get_or_create_chat([user.partner_id.id], pin=True)
                chat.with_user(bot_user).sudo().message_post(**post_vals)
                sent_count += 1
            except Exception:
                try:
                    bot_partner = bot_user.partner_id if bot_user else False
                    if not bot_partner:
                        raise ValueError("handover bot partner not found")
                    chat = (
                        self.env["discuss.channel"]
                        .sudo()
                        .with_user(user)
                        ._get_or_create_chat([bot_partner.id], pin=True)
                    )
                    chat.with_user(bot_user).sudo().message_post(**post_vals)
                    sent_count += 1
                except Exception:
                    _logger.exception(
                        "time_off_extra_approval: failed to send handover submit bot chat leave_id=%s recipient_id=%s",
                        self.id,
                        recipient.id,
                    )
        if not sent_count:
            _logger.warning(
                "time_off_extra_approval: handover bot DM reached no recipients leave_id=%s employee_ids=%s",
                self.id,
                employees.ids,
            )

    def _notify_handover_recipients_submit_via_bot(self):
        """Send Discuss DM from handover bot when requester submits the leave."""
        for leave in self.filtered("handover_employee_ids"):
            leave._notify_specific_handover_recipients_via_bot(leave.handover_employee_ids)

    def _handover_owner_selected_replacement(self):
        self.ensure_one()
        owner = self.handover_escalation_user_id
        if not owner:
            return False
        active_lines = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids and l.state == "pending"
        )
        return bool(active_lines.filtered(lambda l: l.assigned_by_user_id == owner))

    def _feedback_all_work_handover_activities(self):
        for leave in self:
            leave.activity_feedback(
                [_HANDOVER_ACTIVITY_XMLID],
                only_automated=False,
                feedback=_("Đơn xin nghỉ phép đã đóng."),
            )
        return self

    def _notify_requester_handover_refusal(self, refused_employee, reason=None):
        self.ensure_one()
        requester = self.employee_id
        if not requester or not requester.user_id or requester.user_id.share:
            return
        reason = (reason or "").strip()
        reason_suffix = _("\nLý do: %s") % reason if reason else ""
        body = _(
            "%(recipient)s đã từ chối yêu cầu nhận bàn giao công việc cho %(leave)s. "
            "Bạn có muốn chọn đồng nghiệp khác không?"
        ) % {
            "recipient": refused_employee.name or refused_employee.display_name,
            "leave": self.display_name,
        } + reason_suffix
        if requester.user_id.partner_id:
            self.message_notify(
                partner_ids=requester.user_id.partner_id.ids,
                subject=_("Bàn giao công việc bị từ chối"),
                body=body,
            )
        existing_todo = self.activity_search(
            [_TODO_ACTIVITY_XMLID],
            user_id=requester.user_id.id,
            additional_domain=[("summary", "=", _("Cập nhật người nhận bàn giao công việc"))],
            only_automated=False,
        )
        if not existing_todo:
            self.activity_schedule(
                _TODO_ACTIVITY_XMLID,
                user_id=requester.user_id.id,
                summary=_("Cập nhật người nhận bàn giao công việc"),
                note=Markup("<p>%s</p><p>%s</p>") % (
                    body,
                    _(
                        "Mở yêu cầu này, sau đó xóa người đã từ chối "
                        "hoặc chọn đồng nghiệp khác trong mục Người nhận bàn giao công việc."
                    ),
                ),
            )
        self._notify_requester_handover_refusal_via_bot(refused_employee, reason=reason)

    def _notify_requester_handover_refusal_via_bot(self, refused_employee, reason=None):
        """DM from handover bot to requester when a handover recipient refuses."""
        self.ensure_one()
        requester_user = self.employee_id.user_id
        if not requester_user or requester_user.share or not requester_user.partner_id:
            return
        refuser_name = refused_employee.name or refused_employee.display_name
        reason = (reason or "").strip()
        button_html = self._notify_handover_bot_leave_form_open_button_markup()
        if reason:
            bot_body = (
                Markup(
                    _(
                        "{refuser} đã từ chối nhận bàn giao công việc cho bạn với lý do "
                    )
                ).format(refuser=refuser_name)
                + escape(str(reason))
                + Markup(
                    _(
                        ", vui lòng vào mục Time Off để chọn lại người nhận bàn giao.<br/><br/>"
                    )
                )
                + button_html
            )
        else:
            bot_body = (
                Markup(
                    _(
                        "{refuser} đã từ chối nhận bàn giao công việc cho bạn, "
                        "vui lòng vào mục Time Off để chọn lại người nhận bàn giao.<br/><br/>"
                    )
                ).format(refuser=refuser_name)
                + button_html
            )
        try:
            bot_user = (
                self.env.ref("business_discuss_bots.user_bot_handover", raise_if_not_found=False)
                or self.env.ref("base.user_root")
            )
            bot_partner_id = bot_user.partner_id.id if bot_user and bot_user.partner_id else False
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([requester_user.partner_id.id], pin=True)
            )
            post_vals = {
                "body": bot_body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
            }
            if bot_partner_id:
                post_vals["author_id"] = bot_partner_id
            chat.with_user(bot_user).sudo().message_post(**post_vals)
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send handover-refusal bot chat leave_id=%s requester_user_id=%s",
                self.id,
                requester_user.id,
            )

    def _notify_requester_handover_complete_via_bot(self):
        """DM from handover bot when all handover recipients accepted; approval flow can proceed."""
        self.ensure_one()
        if not self.handover_employee_ids:
            return
        active_lines = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids
        )
        # Never notify at submit time; only notify after all current recipients explicitly accepted.
        if not active_lines or active_lines.filtered(lambda l: l.state != "accepted"):
            return
        requester_user = self.employee_id.user_id
        if not requester_user or requester_user.share or not requester_user.partner_id:
            return
        bot_body = _(
            "Công việc của bạn đã được bàn giao thành công. Bước vào quy trình duyệt đơn."
        )
        try:
            bot_user = (
                self.env.ref("business_discuss_bots.user_bot_handover", raise_if_not_found=False)
                or self.env.ref("base.user_root")
            )
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([requester_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=bot_body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send handover-complete bot chat leave_id=%s requester_user_id=%s",
                self.id,
                requester_user.id,
            )

    def _feedback_requester_handover_update_todo(self, feedback_message):
        """Mark the post-refusal 'Update work handover recipients' todo as done (if still open)."""
        self.ensure_one()
        requester_user = self.employee_id.user_id
        if not requester_user:
            return
        open_acts = self.activity_search(
            [_TODO_ACTIVITY_XMLID],
            user_id=requester_user.id,
            additional_domain=[("summary", "=", _("Cập nhật người nhận bàn giao công việc"))],
            only_automated=False,
        )
        if open_acts:
            open_acts.action_feedback(feedback=feedback_message)

    def _action_return_reload_leave_form(self):
        """call_button only forwards dict actions to the web client; booleans are dropped, so the form must reload explicitly."""
        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }

    def _get_handover_blocking_employees(self):
        """Employees who have not accepted handover yet for current approval stage."""
        self.ensure_one()
        if self.state not in ("confirm", "validate1") or not self.handover_employee_ids:
            return self.env["hr.employee"]
        active_recipients = self.handover_employee_ids
        accepted = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in active_recipients and l.state == "accepted"
        ).mapped("employee_id")
        return active_recipients - accepted

    def _handover_past_due_without_any_acceptance(self):
        """Same time/no-acceptance test as handover escalation cron (UI can show before cron sets handover_escalated)."""
        self.ensure_one()
        if self.state not in ("confirm", "validate1") or not self.handover_employee_ids:
            return False
        active_lines = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids
        )
        if not active_lines:
            return False
        if active_lines.filtered(lambda l: l.state == "accepted"):
            return False
        requested_at = self.handover_requested_at or self.create_date
        if not requested_at:
            return False
        threshold = fields.Datetime.now() - timedelta(hours=self._handover_escalation_after_hours())
        return requested_at <= threshold

    def _handover_escalation_after_hours(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_escalation_after_hours:
            return self.holiday_status_id.handover_escalation_after_hours
        return _HANDOVER_ESCALATION_MINUTES / 60.0

    def _handover_second_escalation_hours(self):
        self.ensure_one()
        # Escalation should progress level-by-level on the same cadence configured by
        # "Handover: Escalate After (hours)". This makes each timeout hop to the next
        # manager and notify them until max escalation title is reached.
        return self._handover_escalation_after_hours()

    def _handover_max_escalation_job_title(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_escalation_max_job_title:
            return self.holiday_status_id.handover_escalation_max_job_title
        return _DEPARTMENT_HEAD_JOB_TITLE_KEY

    def _handover_job_title_rank(self, title_key):
        if not title_key:
            return -1
        rank_map = _job_title_rank_map()
        return rank_map.get(_normalize_job_title_key(title_key), -1)

    def _get_handover_escalation_cap_user_for_max_title(self):
        """First manager on the requester's chain whose job title rank >= configured max (has internal user)."""
        self.ensure_one()
        max_rank = self._handover_job_title_rank(self._handover_max_escalation_job_title())
        if max_rank < 0:
            return self.env["res.users"]
        employee = self.employee_id
        while employee and employee.parent_id:
            manager = employee.parent_id.sudo()
            mgr_rank = self._handover_job_title_rank(manager.job_title)
            if mgr_rank >= max_rank and manager.user_id and not manager.user_id.share:
                return manager.user_id
            employee = manager
        return self.env["res.users"]

    def _handover_is_max_escalation_reached(self):
        self.ensure_one()
        owner = self.handover_escalation_user_id
        if not owner:
            return False
        cap_user = self._get_handover_escalation_cap_user_for_max_title()
        if cap_user and owner == cap_user:
            return True
        owner_emp = self._handover_employee_for_assigner_user(owner)
        owner_rank = self._handover_job_title_rank(owner_emp.job_title if owner_emp else False)
        max_rank = self._handover_job_title_rank(self._handover_max_escalation_job_title())
        if max_rank < 0:
            return True
        return owner_rank >= max_rank

    def _handover_should_auto_cancel_at_max_level(self):
        self.ensure_one()
        return bool(self.holiday_status_id and self.holiday_status_id.handover_cancel_if_max_unresponsive)

    def _handover_cancel_after_max_hours(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_cancel_after_max_hours:
            return self.holiday_status_id.handover_cancel_after_max_hours
        return 2.0

    def _current_user_escalation_assigned_handover_recipient_line(self):
        """Acceptance row for current user if they were designated by handover_escalation_user_id (e.g. trưởng BP)."""
        self.ensure_one()
        if not self.handover_escalation_user_id:
            return self.env["hr.leave.handover.acceptance"]
        emp = self.env.user.sudo().employee_id
        if not emp or emp not in self.handover_employee_ids:
            return self.env["hr.leave.handover.acceptance"]
        return self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id == emp
            and l.assigned_by_user_id
            and l.assigned_by_user_id == self.handover_escalation_user_id
        )[:1]

    def _current_user_is_pending_handover_recipient(self):
        """True if the logged-in user is a handover colleague who still must accept or refuse."""
        self.ensure_one()
        emp = self.env.user.sudo().employee_id
        if not emp or emp not in self.handover_employee_ids:
            return False
        line = self.handover_acceptance_ids.filtered(lambda l: l.employee_id == emp)[:1]
        return bool(line and line.state == "pending")

    def _viewer_can_manage_handover_acceptance_sheet(self):
        """Who may add/remove/edit Work Handover To lines on the Time Off request (excluding accept/refuse)."""
        self.ensure_one()
        if self.env.su:
            return True
        user = self.env.user
        viewer_emp = user.sudo().employee_id
        if viewer_emp and self.employee_id:
            if (
                self.handover_escalated
                and self.handover_escalation_user_id
                and user == self.handover_escalation_user_id
            ):
                return True
            # Colleagues on the handover list never manage the roster, even if they are Time Off Officers.
            if viewer_emp in self.handover_employee_ids and viewer_emp != self.employee_id:
                return False
        if user.has_group(
            "hr_holidays.group_hr_holidays_user"
        ) or user.has_group("hr_holidays.group_hr_holidays_manager"):
            return True
        if not viewer_emp or not self.employee_id:
            return False
        if viewer_emp == self.employee_id:
            return not self.handover_escalated
        return False

    def _handover_ready_for_approval(self):
        self.ensure_one()
        return not self._get_handover_blocking_employees()

    def _ensure_handover_ready_for_approval(self, raise_if_not_ready=True):
        blocked = self.env["hr.leave"]
        for leave in self:
            if leave._get_handover_blocking_employees():
                blocked |= leave
        if not blocked:
            return True
        if not raise_if_not_ready:
            return False
        leave = blocked[:1]
        names = ", ".join(leave._get_handover_blocking_employees().mapped("name"))
        raise UserError(
            _(
                "Duyệt đơn đang bị khóa cho đến khi tất cả người nhận bàn giao chấp nhận. "
                "Hiện vẫn đang chờ: %(names)s."
            )
            % {"names": names}
        )

    def action_handover_accept(self):
        self.ensure_one()
        emp = self.env.user.sudo().employee_id
        if not emp or emp not in self.handover_employee_ids:
            raise UserError(_("Chỉ những người nhận bàn giao đã chọn mới có thể phản hồi tại đây."))
        line = self.handover_acceptance_ids.sudo().filtered(lambda l: l.employee_id == emp)[:1]
        if not line or line.state != "pending":
            raise UserError(_("Bạn đã phản hồi yêu cầu bàn giao công việc này rồi."))
        line.write(
            {
                "state": "accepted",
                "responded_at": fields.Datetime.now(),
                "refusal_reason": False,
            }
        )
        self.activity_feedback(
            [_HANDOVER_ACTIVITY_XMLID],
            user_id=self.env.user.id,
            only_automated=False,
            feedback=_("Đã chấp nhận bàn giao công việc."),
        )
        self.message_post(
            body=_("%s đã chấp nhận bàn giao công việc.") % self.env.user.display_name,
            subtype_xmlid="mail.mt_note",
        )
        if self._handover_ready_for_approval():
            self._notify_requester_handover_complete_via_bot()
            if self.validation_type == "employee_hr_responsibles" and self.state in ("confirm", "validate1"):
                self._notify_responsible_current_turn()
        return True

    def action_handover_refuse(self):
        self.ensure_one()
        emp = self.env.user.sudo().employee_id
        if not emp or emp not in self.handover_employee_ids:
            raise UserError(_("Chỉ những người nhận bàn giao đã chọn mới có thể phản hồi tại đây."))
        line = self.handover_acceptance_ids.sudo().filtered(lambda l: l.employee_id == emp)[:1]
        if not line or line.state != "pending":
            raise UserError(_("Bạn đã phản hồi yêu cầu bàn giao công việc này rồi."))
        return {
            "name": _("Từ chối bàn giao công việc"),
            "type": "ir.actions.act_window",
            "target": "new",
            "res_model": "hr.leave.handover.refuse.wizard",
            "view_mode": "form",
            "views": [[False, "form"]],
            "context": {
                "default_leave_id": self.id,
                "dialog_size": "medium",
            },
        }

    def action_handover_refuse_with_reason(self, reason):
        self.ensure_one()
        reason = (reason or "").strip()
        emp = self.env.user.sudo().employee_id
        if not emp or emp not in self.handover_employee_ids:
            raise UserError(_("Chỉ những người nhận bàn giao đã chọn mới có thể phản hồi tại đây."))
        line = self.handover_acceptance_ids.sudo().filtered(lambda l: l.employee_id == emp)[:1]
        if not line or line.state != "pending":
            raise UserError(_("Bạn đã phản hồi yêu cầu bàn giao công việc này rồi."))
        line.write(
            {
                "state": "refused",
                "responded_at": fields.Datetime.now(),
                "refusal_reason": reason,
            }
        )
        self.activity_feedback(
            [_HANDOVER_ACTIVITY_XMLID],
            user_id=self.env.user.id,
            only_automated=False,
            feedback=_("Đã từ chối bàn giao công việc."),
        )
        reason_html = (
            Markup("<br/><strong>%s</strong> %s")
            % (_("Lý do:"), reason)
            if reason
            else Markup("")
        )
        self.message_post(
            body=Markup("%s%s")
            % (_("%s đã từ chối bàn giao công việc.") % self.env.user.display_name, reason_html),
            subtype_xmlid="mail.mt_note",
        )
        self._notify_requester_handover_refusal(emp, reason=reason)
        return True

    def action_handover_replacement_yes(self):
        """Open the picker: replace refused recipient(s) with new colleague(s) and work content per row."""
        self.ensure_one()
        if not self.can_manage_handover_replacement:
            raise UserError(
                _("Chỉ nhân viên đã tạo đơn nghỉ phép này mới có thể cập nhật người nhận bàn giao bị từ chối.")
            )
        self.handover_replacement_draft_ids.unlink()
        self.write({"handover_replacement_picker_open": True})
        return self._action_return_reload_leave_form()

    def action_handover_replacement_no(self):
        """Decline replacing refused colleagues: remove them from Work Handover To and continue the flow."""
        self.ensure_one()
        if not self.can_manage_handover_replacement:
            raise UserError(
                _("Chỉ nhân viên đã tạo đơn nghỉ phép này mới có thể cập nhật người nhận bàn giao bị từ chối.")
            )
        self.handover_replacement_draft_ids.unlink()
        refused_emps = self.handover_acceptance_ids.filtered(
            lambda line: line.state == "refused"
        ).mapped("employee_id")
        if not refused_emps:
            self.write(
                {
                    "handover_replacement_picker_open": False,
                }
            )
            return self._action_return_reload_leave_form()
        remaining = self.handover_employee_ids - refused_emps
        if not remaining:
            raise UserError(
                _(
                    "Bạn không thể xóa toàn bộ người nhận bàn giao công việc. "
                    "Hãy giữ ít nhất một người hoặc chọn Có để thay thế người nhận."
                )
            )
        self.write(
            {
                "handover_employee_ids": [Command.set(remaining.ids)],
                "handover_replacement_picker_open": False,
            }
        )
        self._feedback_requester_handover_update_todo(
            _("Đã xóa đồng nghiệp từ chối khỏi danh sách bàn giao; quy trình duyệt có thể tiếp tục.")
        )
        self.message_post(
            body=_("%s đã xóa đồng nghiệp từ chối khỏi danh sách bàn giao mà không thay thế.")
            % self.env.user.display_name,
            subtype_xmlid="mail.mt_note",
        )
        return self._action_return_reload_leave_form()

    def action_handover_apply_replacement(self):
        """Apply replacement rows: remove selected recipients and add new ones with handover content."""
        self.ensure_one()
        if not self.can_manage_handover_replacement:
            raise UserError(
                _("Chỉ nhân viên đã tạo đơn nghỉ phép này mới có thể cập nhật người nhận bàn giao bị từ chối.")
            )
        draft_lines = self.handover_replacement_draft_ids.sorted(lambda l: (l.sequence or 0, l.id or 0))
        if not draft_lines:
            raise UserError(
                _(
                    "Vui lòng thêm ít nhất một dòng (Thêm một dòng): chọn người cần thay, "
                    "người nhận bàn giao mới và nội dung công việc."
                )
            )
        replaceable = self.handover_replaceable_recipient_ids
        for line in draft_lines:
            if not line.replace_employee_id or not line.new_employee_id:
                raise UserError(_("Mỗi dòng phải có đủ người cần thay và người nhận bàn giao mới."))
            content = (line.handover_work_content or "").strip()
            if not content:
                raise UserError(_("Vui lòng điền nội dung công việc cho từng người nhận mới."))
            if line.replace_employee_id not in replaceable:
                raise UserError(
                    _(
                        "Bạn chỉ có thể thay những người nhận hiện đang cho phép thay "
                        "(đã từ chối, hoặc đang chờ sau khi quá thời gian chuyển cấp)."
                    )
                )
            if line.replace_employee_id not in self.handover_employee_ids:
                raise UserError(_("Đồng nghiệp được chọn không nằm trong danh sách bàn giao hiện tại."))
            if line.new_employee_id not in line.allowed_new_employee_ids:
                raise UserError(
                    _(
                        "Không thể thêm đồng nghiệp này: đã có trên đơn, trùng kỳ nghỉ không khả dụng, "
                        "hoặc không hợp lệ."
                    )
                )
            if line.replace_employee_id == line.new_employee_id:
                raise UserError(_("Người nhận mới phải khác người đang được thay."))
        replace_ids = draft_lines.mapped("replace_employee_id").ids
        if len(replace_ids) != len(set(replace_ids)):
            raise UserError(_("Mỗi người cần thay chỉ được chọn trên một dòng."))
        new_ids_from_lines = draft_lines.mapped("new_employee_id").ids
        if len(new_ids_from_lines) != len(set(new_ids_from_lines)):
            raise UserError(_("Người nhận bàn giao mới không được trùng nhau giữa các dòng."))
        current = list(self.handover_employee_ids.ids)
        specs = []
        for line in draft_lines:
            ro, nw = line.replace_employee_id.id, line.new_employee_id.id
            if ro not in current:
                raise UserError(
                    _("Đồng nghiệp “%s” không còn trong danh sách bàn giao.") % line.replace_employee_id.display_name
                )
            current.remove(ro)
            if nw in current:
                raise UserError(
                    _("Người nhận “%s” đã có trong danh sách bàn giao sau khi áp dụng các dòng trước.")
                    % line.new_employee_id.display_name
                )
            current.append(nw)
            specs.append((nw, (line.handover_work_content or "").strip()))
        if len(current) > 5:
            raise ValidationError(_("Bạn chỉ có thể chọn tối đa 5 người nhận bàn giao công việc."))
        draft_lines.unlink()
        self.write(
            {
                "handover_employee_ids": [Command.set(current)],
                "handover_replacement_picker_open": False,
            }
        )
        new_emps = self.env["hr.employee"]
        for emp_id, content in specs:
            new_line = self.handover_acceptance_ids.filtered(lambda l: l.employee_id.id == emp_id)[:1]
            if new_line:
                write_vals = {
                    "handover_work_content": content,
                    "assigned_by_user_id": self.env.user.id,
                }
                if (
                    self.handover_escalated
                    and self.employee_id
                    and self.employee_id.user_id
                    and self.env.user != self.employee_id.user_id
                ):
                    write_vals["reassigned_by_escalation_owner"] = True
                new_line.sudo().write(write_vals)
                new_emps |= new_line.employee_id
        self._refresh_handover_activity_notes_for_employees(new_emps)
        self._notify_specific_handover_recipients_via_bot(new_emps)
        return self._action_return_reload_leave_form()

    def _vals_trigger_emergency_leave_check(self, vals):
        if not vals:
            return False
        return bool(
            {"employee_id", "request_date_from", "request_date_to", "holiday_status_id"}.intersection(vals)
        )

    def write(self, vals):
        handover_lines_changed = bool(
            vals.get("handover_acceptance_ids") is not None and not self.env.context.get("skip_handover_line_sync")
        )
        submit_notify_target = self.env["hr.leave"]
        responsible_submit_prev_states = {}
        outcome_notify_prev_states = {}
        if (
            vals.get("state") in ("validate", "refuse", "cancel")
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_OUTCOME_BOT_NOTIFY_CTX)
        ):
            outcome_notify_prev_states = {leave.id: leave.state for leave in self}
        if (
            vals.get("state") == "confirm"
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_SUBMIT_BOT_NOTIFY_CTX)
        ):
            submit_notify_target = self.filtered(lambda l: l.state != "confirm" and l.handover_employee_ids)
        if (
            vals.get("state") == "confirm"
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX)
        ):
            responsible_submit_prev_states = {leave.id: leave.state for leave in self}
        if vals and self._vals_trigger_emergency_leave_check(vals):
            if len(self) > 1:
                raise UserError(
                    _(
                        "Please edit and save one time off request at a time when changing dates, "
                        "employee, or time off type (advance-notice check)."
                    )
                )
            self._apply_emergency_leave_on_vals(vals, leave=self)
        if (
            vals.get("handover_employee_ids") is not None
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get("skip_handover_assignee_list_lock")
        ):
            viewer_emp = self.env.user.sudo().employee_id
            for leave in self:
                if leave.handover_escalated:
                    if not leave.handover_escalation_user_id or leave.handover_escalation_user_id != self.env.user:
                        raise UserError(
                            _(
                                "Sau khi quá hạn bàn giao công việc, chỉ người được chỉ định escalate "
                                "mới có thể thay đổi người nhận bàn giao."
                            )
                        )
                if viewer_emp and leave.employee_id and viewer_emp == leave.employee_id:
                    continue
                if leave._current_user_is_pending_handover_recipient():
                    raise UserError(
                        _(
                            "Bạn không thể tự thay đổi người bàn giao. "
                            "Vui lòng dùng nút Chấp nhận hoặc Từ chối bàn giao công việc."
                        )
                    )
        reset_leaves = self.env["hr.leave"]
        if vals.get("state") == "confirm" and not self.env.context.get(_MULTI_STEP_RESET_CTX):
            reset_leaves = self.filtered(
                lambda l: l.validation_type == "multi_step_6" and l.state != "confirm"
            )
        res = super().write(vals)
        if handover_lines_changed:
            self._sync_handover_employees_from_acceptance()
        if reset_leaves:
            reset_leaves.mapped("multi_approval_line_ids").unlink()
            reset_leaves.with_context(**{_MULTI_STEP_RESET_CTX: True}).write({"multi_step_current": 1})
        self._ensure_responsible_approval_lines()
        to_timer = self.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles"
            and l.state in ("confirm", "validate1")
            and (l.holiday_status_id.employee_responsible_approval_mode or "any") == "sequential"
            and l.responsible_approval_line_ids
        )
        if to_timer:
            to_timer._responsible_backfill_pending_since_if_missing()
        if not self.env.context.get("leave_fast_create"):
            if vals.get("state") in ("confirm", "validate1"):
                self._mark_handover_requested_at()
            if vals.get("state") == "confirm" and submit_notify_target:
                submit_notify_target._notify_handover_recipients_submit_via_bot()
            if vals.get("state") == "confirm" and responsible_submit_prev_states:
                submit_responsible_leaves = self.filtered(
                    lambda l: l.validation_type == "employee_hr_responsibles"
                    and l.state == "confirm"
                    and responsible_submit_prev_states.get(l.id) != "confirm"
                )
                if submit_responsible_leaves:
                    submit_responsible_leaves._ensure_responsible_approval_lines()
                    submit_responsible_leaves._responsible_backfill_pending_since_if_missing()
                    for leave in submit_responsible_leaves:
                        leave._notify_responsible_approvers_submission()
                        leave._notify_responsible_current_turn()
            if vals.get("state") in ("validate", "refuse", "cancel"):
                self._feedback_all_work_handover_activities()
            elif "handover_employee_ids" in vals:
                self.filtered(lambda l: l.state in _HANDOVER_ACTIVE_STATES)._sync_handover_acceptance_lines()
                self.filtered(lambda l: l.state in _HANDOVER_ACTIVE_STATES)._mark_pending_handover_lines_as_escalation_assigned()
                self.filtered(lambda l: l.state in _HANDOVER_ACTIVE_STATES)._schedule_work_handover_activities()
            if outcome_notify_prev_states:
                for leave in self:
                    prev = outcome_notify_prev_states.get(leave.id)
                    if leave.state in ("validate", "refuse", "cancel") and leave.state != prev:
                        leave._notify_requester_approval_outcome_via_bot(
                            leave.state,
                            refusal_reason=self.env.context.get("refusal_reason"),
                            refuser_name=self.env.context.get("refuser_name"),
                        )
        return res

    @api.depends(
        "validation_type",
        "state",
        "multi_step_current",
        "holiday_status_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_can_multi_step_approve(self):
        for leave in self:
            can = False
            if leave.validation_type == "multi_step_6" and leave.state == "confirm":
                is_manager = leave.env.user.has_group("hr_holidays.group_hr_holidays_manager")
                if is_manager:
                    can = True
                else:
                    can = leave.env.user in leave._get_multi_step_approvers()
            if can and not leave._handover_ready_for_approval():
                can = False
            leave.can_multi_step_approve = can

    @api.depends(
        "state",
        "employee_id",
        "department_id",
        "holiday_status_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_can_approve(self):
        super()._compute_can_approve()
        for leave in self.filtered(
            lambda h: h.validation_type in ("employee_hr_responsibles", "multi_step_6")
        ):
            leave.can_approve = False
        for leave in self:
            if leave.can_approve and not leave._handover_ready_for_approval():
                leave.can_approve = False

    @api.depends(
        "state",
        "employee_id",
        "department_id",
        "holiday_status_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_can_validate(self):
        super()._compute_can_validate()
        for leave in self.filtered(
            lambda h: h.validation_type in ("employee_hr_responsibles", "multi_step_6")
        ):
            leave.can_validate = False
        for leave in self:
            if leave.can_validate and not leave._handover_ready_for_approval():
                leave.can_validate = False

    @api.depends(
        "state",
        "employee_id",
        "department_id",
        "holiday_status_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_can_refuse(self):
        super()._compute_can_refuse()
        for leave in self.filtered(
            lambda h: h.validation_type in ("employee_hr_responsibles", "multi_step_6")
        ):
            leave.can_refuse = False
        for leave in self:
            if leave.can_refuse and not leave._handover_ready_for_approval():
                leave.can_refuse = False

    def _is_extra_approver(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return user in self.extra_approver_user_ids

    def _get_responsible_for_approval(self):
        if self.validation_type == "employee_hr_responsibles":
            return self._get_responsible_approval_users()
        if self.validation_type == "multi_step_6":
            return self._get_multi_step_approvers()

        res = super()._get_responsible_for_approval()
        # Only HR-step validations use responsible_ids; for manager validations this is handled by employee leave manager.
        if self.employee_id and (
            self.validation_type == "hr" or (self.validation_type == "both" and self.state == "validate1")
        ):
            res |= self.extra_approver_user_ids
        return res

    @api.depends(
        "validation_type",
        "state",
        "holiday_status_id",
        "holiday_status_id.leave_validation_type",
        "holiday_status_id.employee_responsible_approval_mode",
        "holiday_status_id.employee_responsible_source",
        "holiday_status_id.special_director_employee_line_ids",
        "holiday_status_id.special_director_employee_line_ids.employee_id",
        "holiday_status_id.special_director_sequential_approval",
        "holiday_status_id.special_director_order_line_ids",
        "employee_id",
        "employee_id.job_title",
        "employee_id.hr_responsible_ids",
        "employee_id.hr_responsible_id",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
        "responsible_approval_line_ids.user_id",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
    )
    def _compute_can_responsible_approve(self):
        for leave in self:
            can = False
            # validate1: can appear on mixed/old data; still allow Responsible actions if approval lines exist.
            if leave.validation_type == "employee_hr_responsibles" and leave.state in ("confirm", "validate1"):
                if leave.state == "validate1" and not leave.responsible_approval_line_ids:
                    can = False
                else:
                    mode = leave.holiday_status_id.employee_responsible_approval_mode
                    approvers = leave._get_responsible_approval_users()
                    is_manager = leave.env.user.has_group("hr_holidays.group_hr_holidays_manager")
                    # Sequential: every user (including Time Off Administrators) must wait for the current
                    # pending line so "Waiting For Me" / Kanban buttons match chain order — not all admins at once.
                    if mode == "sequential":
                        if leave._employee_hr_blocks_self_approval_non_director(leave.env.user):
                            can = False
                        elif (
                            not leave.responsible_approval_line_ids
                            and approvers
                            and leave.state == "confirm"
                        ):
                            can = leave.env.user == approvers[0]
                        else:
                            user_line = leave.responsible_approval_line_ids.filtered(
                                lambda l: l.user_id == leave.env.user and l.state == "pending"
                            )[:1]
                            wave = leave._responsible_pending_current_wave()
                            can = bool(
                                user_line
                                and wave
                                and user_line in wave
                            )
                    elif is_manager:
                        can = True
                    elif leave.env.user in approvers:
                        if leave._employee_hr_blocks_self_approval_non_director(leave.env.user):
                            can = False
                        else:
                            can = bool(
                                leave.responsible_approval_line_ids.filtered(
                                    lambda l: l.user_id == leave.env.user and l.state == "pending"
                                )[:1]
                            )
            if can and not leave._handover_ready_for_approval():
                can = False
            leave.can_responsible_approve = can

    @api.depends(
        "validation_type",
        "state",
        "multi_step_current",
        "holiday_status_id.employee_responsible_approval_mode",
        "holiday_status_id.special_director_sequential_approval",
        "holiday_status_id.special_director_order_line_ids",
        "holiday_status_id.multi_approval_step_ids",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
        "responsible_approval_line_ids.sequence",
        "responsible_approval_line_ids.user_id",
    )
    def _compute_approval_current_step_label(self):
        """One-line hint for Kanban/list: who should act next (HR Responsibles / multi-step)."""
        for leave in self:
            leave.approval_current_step_label = False
            if leave.state not in ("confirm", "validate1"):
                continue
            vt = leave.validation_type
            if vt == "employee_hr_responsibles":
                pending = leave.responsible_approval_line_ids.filtered(
                    lambda line: line.state == "pending"
                ).sorted(lambda ln: (ln.sequence, ln.id))
                if not pending:
                    continue
                mode = leave.holiday_status_id.employee_responsible_approval_mode or "any"
                total = len(leave.responsible_approval_line_ids)
                if mode == "sequential":
                    wave = leave._responsible_pending_current_wave()
                    if not wave:
                        continue
                    step_num = wave[0].sequence
                    names = ", ".join(n for n in wave.mapped("user_id.name") if n)
                    leave.approval_current_step_label = _("Bước %(step)d / %(total)d · %(name)s") % {
                        "step": step_num,
                        "total": total,
                        "name": names,
                    }
                else:
                    leave.approval_current_step_label = ", ".join(
                        n for n in pending.mapped("user_id.name") if n
                    ) or False
            elif vt == "multi_step_6":
                step = leave._get_current_multi_step()
                if not step:
                    continue
                users = step._get_all_approver_users()
                names = ", ".join(n for n in users.mapped("name") if n)
                if step.name and names:
                    leave.approval_current_step_label = _("%(step)s · %(names)s") % {
                        "step": step.name,
                        "names": names,
                    }
                elif names:
                    leave.approval_current_step_label = names
                elif step.name:
                    leave.approval_current_step_label = step.name

    def _init_responsible_approval_lines(self):
        line_model = self.env["hr.leave.responsible.approval"].sudo()
        for leave in self:
            if leave.validation_type != "employee_hr_responsibles" or not leave.employee_id:
                continue
            if leave.responsible_approval_line_ids:
                continue
            lt = leave.holiday_status_id
            approvers = leave._get_responsible_approval_users()
            if leave._is_multi_director_special_employee() and (
                not leave._employee_hr_chain_contains_director(approvers)
            ):
                raise UserError(
                    _(
                        "Loại nghỉ được cấu hình nhân viên đặc biệt (chặn Giám đốc) nhưng không có người duyệt nào "
                        "mang chức danh Giám đốc (user nội bộ) trong chuỗi duyệt. Kiểm tra sơ đồ tổ chức hoặc bảng "
                        "thứ tự Giám đốc trên loại nghỉ."
                    )
                )
            if leave._is_multi_director_special_employee() and lt.special_director_sequential_approval:
                if lt.special_director_order_line_ids and not leave._get_configured_director_order_users():
                    raise UserError(
                        _(
                            "Đã bật 'Duyệt theo thứ tự Giám đốc' và có dòng trong bảng, nhưng không có Giám đốc nào "
                            "hợp lệ (chức danh Giám đốc và user nội bộ). Vui lòng sửa danh sách."
                        )
                    )
            if not approvers:
                if lt.employee_responsible_source == "org_chart":
                    raise UserError(
                        _(
                            "No approver was found from the organization chart. Set managers on the employee "
                            "and job titles (team lead → dept head → controller → HR head → director) on the hierarchy."
                        )
                    )
                raise UserError(_("Nhân viên này chưa được cấu hình người phụ trách HR."))
            slot_limit = (
                _MAX_EMPLOYEE_HR_RESPONSIBLES_MULTI_DIRECTOR
                if leave._is_multi_director_special_employee()
                else _MAX_EMPLOYEE_HR_RESPONSIBLES
            )
            if len(approvers) > slot_limit:
                raise UserError(
                    _("Luồng này hỗ trợ tối đa %(max)s người phụ trách HR cho mỗi nhân viên.")
                    % {"max": slot_limit}
                )
            now = fields.Datetime.now()
            pairs = leave._build_responsible_approval_sequences()
            seqs_present = [s for _, s in pairs]
            min_seq = min(seqs_present) if seqs_present else 1
            for user, seq in pairs:
                vals = {
                    "leave_id": leave.id,
                    "user_id": user.id,
                    "sequence": seq,
                }
                if lt.employee_responsible_approval_mode == "sequential" and seq == min_seq:
                    vals["pending_since"] = now
                line_model.create(vals)

    def _ensure_responsible_approval_lines(self):
        """Create approval log rows when a request is already To Approve but lines were never created.

        Lines are normally added in ``action_confirm``; some code paths set ``state`` to confirm via
        ``write``/import/wizards without going through that method, which left no pending step and no
        Step label until someone saved again.
        """
        to_init = self.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles"
            and l.state == "confirm"
            and l.employee_id
            and not l.responsible_approval_line_ids
        )
        if not to_init:
            return
        to_init._init_responsible_approval_lines()
        to_init.modified(
            ["responsible_approval_line_ids", "employee_id", "holiday_status_id"]
        )

    def _responsible_backfill_pending_since_if_missing(self):
        """Sequential HR Responsibles: active pending step must have pending_since or timeout never runs."""
        for leave in self:
            if leave.validation_type != "employee_hr_responsibles":
                continue
            if leave.holiday_status_id.employee_responsible_approval_mode != "sequential":
                continue
            wave = leave._responsible_pending_current_wave()
            if not wave:
                continue
            hours = leave.holiday_status_id.employee_responsible_escalation_hours or 2.0
            threshold = fields.Datetime.now() - timedelta(hours=hours)
            missing = wave.filtered(lambda ln: not ln.pending_since)
            if not missing:
                continue
            missing.write({"pending_since": threshold - timedelta(seconds=1)})

    def _notify_responsible_approvers_submission(self):
        """FYI notification to all configured approvers when a leave is submitted."""
        self.ensure_one()
        if self.validation_type != "employee_hr_responsibles":
            return
        users = self._get_responsible_approval_users().filtered(
            lambda u: u.partner_id and not u.share
        )
        if not users:
            return
        self.message_post(
            body=_(
                "New time off request from %(employee)s requires your review in the responsible approval flow."
            )
            % {"employee": self.employee_id.name or self.display_name},
            message_type="notification",
            subtype_xmlid="mail.mt_comment",
            partner_ids=users.mapped("partner_id").ids,
        )

    def _notify_responsible_current_turn(self, user=None):
        """Notify approver(s) for the active sequential wave (one user, or all parallel directors)."""
        self.ensure_one()
        if self.validation_type != "employee_hr_responsibles":
            _logger.info(
                "time_off_extra_approval: skip current-turn notify leave_id=%s reason=validation_type_%s",
                self.id,
                self.validation_type,
            )
            return
        lines = self.env["hr.leave.responsible.approval"]
        if user:
            lines = self.responsible_approval_line_ids.filtered(
                lambda l: l.state == "pending" and l.user_id == user
            )
        if not lines:
            lines = self._responsible_pending_current_wave()
        if not lines:
            _logger.info(
                "time_off_extra_approval: skip current-turn notify leave_id=%s reason=no_pending_wave user=%s",
                self.id,
                user.id if user else None,
            )
            return
        if not self._handover_ready_for_approval():
            _logger.info(
                "time_off_extra_approval: skip current-turn notify leave_id=%s reason=handover_not_ready user=%s",
                self.id,
                user.id if user else None,
            )
            return
        body_text = _(
            "It is now your turn to approve time off request %(leave)s for %(employee)s."
        ) % {
            "leave": self.display_name,
            "employee": self.employee_id.name or "",
        }
        for line in lines:
            if not line.user_id.partner_id:
                continue
            duplicate_message = self.env["mail.message"].sudo().search(
                [
                    ("model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("body", "=", body_text),
                    ("partner_ids", "in", [line.user_id.partner_id.id]),
                ],
                limit=1,
            )
            if duplicate_message:
                continue
            self.message_post(
                body=body_text,
                message_type="notification",
                subtype_xmlid="mail.mt_comment",
                partner_ids=[line.user_id.partner_id.id],
            )
            self._notify_responsible_current_turn_via_approval_bot(line.user_id)

    def _notify_responsible_current_turn_via_approval_bot(self, approver_user):
        """Send Discuss DM from approval bot to current responsible approver."""
        self.ensure_one()
        if not approver_user or approver_user.share or not approver_user.partner_id:
            _logger.info(
                "time_off_extra_approval: skip bot current-turn notify leave_id=%s reason=invalid_user share=%s has_partner=%s",
                self.id,
                bool(approver_user and approver_user.share),
                bool(approver_user and approver_user.partner_id),
            )
            return
        requester_name = self.employee_id.name or self.employee_id.display_name or self.display_name
        leave_date = self.request_date_from or (self.date_from and self.date_from.date())
        leave_date_text = leave_date.strftime("%d/%m/%Y") if leave_date else ""
        base = (self.get_base_url() or "").rstrip("/")
        leave_url = f"{base}/web#id={self.id}&model=hr.leave&view_type=form"
        intro = Markup(
            _(
                "Nhân viên: <b>{requester}</b> xin nghỉ phép<br/>"
                "Ngày nghỉ: <b>{date}</b><br/>"
                "Vui lòng bấm vào Time Off để xác nhận hoặc từ chối đơn.<br/><br/>"
            )
        ).format(
            requester=escape(str(requester_name)),
            date=escape(str(leave_date_text)),
        )
        button_html = Markup(
            '<a href="{href}" target="_blank" rel="noreferrer noopener" '
            'style="display:inline-block;padding:8px 18px;background-color:#714B67;'
            'color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600;'
            'font-size:14px;line-height:1.2;">{label}</a>'
        ).format(href=leave_url, label=_("Time Off"))
        body = intro + button_html
        try:
            # Current-turn approver notifications must come from approval bot.
            bot_user = self.env.ref("business_discuss_bots.user_bot_approval", raise_if_not_found=False)
            if not bot_user:
                bot_user = self.env.ref("base.user_root")
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([approver_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            _logger.info(
                "time_off_extra_approval: sent bot current-turn notify leave_id=%s approver_login=%s bot_user=%s",
                self.id,
                approver_user.login,
                bot_user.login,
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send approval-step bot chat leave_id=%s approver_user_id=%s",
                self.id,
                approver_user.id,
            )

    def _notify_requester_approval_outcome_via_bot(self, outcome_state, refusal_reason=None, refuser_name=None):
        """Send approval/refusal/cancel result DM from approval Discuss bot (OdooBot Duyệt đơn)."""
        self.ensure_one()
        requester_user = self.employee_id.user_id
        if not requester_user or requester_user.share or not requester_user.partner_id:
            return
        leave_date = self.request_date_from or (self.date_from and self.date_from.date())
        leave_date_text = leave_date.strftime("%d/%m/%Y") if leave_date else ""
        if outcome_state == "refuse":
            reason_text = (refusal_reason or self.last_refusal_reason or "").strip()
            by_text = refuser_name or (self.last_refuser_id and self.last_refuser_id.display_name) or _("người duyệt")
            if reason_text:
                body = _(
                    "Đơn của bạn xin nghỉ vào ngày %(date)s đã bị từ chối bởi %(refuser)s với lý do là %(reason)s."
                ) % {
                    "date": leave_date_text,
                    "refuser": by_text,
                    "reason": reason_text,
                }
            else:
                body = _(
                    "Đơn của bạn xin nghỉ vào ngày %(date)s đã bị từ chối bởi %(refuser)s."
                ) % {
                    "date": leave_date_text,
                    "refuser": by_text,
                }
        elif outcome_state == "cancel":
            body = _("Đơn xin nghỉ của bạn vào ngày %(date)s đã bị hủy.") % {
                "date": leave_date_text
            }
        else:
            body = _("Đơn xin nghỉ của bạn vào ngày %(date)s đã được phê duyệt thành công.") % {
                "date": leave_date_text
            }
        try:
            bot_user = self.env.ref("business_discuss_bots.user_bot_approval", raise_if_not_found=False)
            if not bot_user:
                bot_user = self.env.ref("base.user_root")
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([requester_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send approval-outcome bot chat leave_id=%s requester_user_id=%s state=%s",
                self.id,
                requester_user.id,
                outcome_state,
            )

    def _notify_requester_auto_cancel_via_odoo_bot(self):
        """Send specific auto-cancel timeout message via default OdooBot."""
        self.ensure_one()
        requester_user = self.employee_id.user_id
        if not requester_user or requester_user.share or not requester_user.partner_id:
            return
        leave_date = self.request_date_from or (self.date_from and self.date_from.date())
        leave_date_text = leave_date.strftime("%d/%m/%Y") if leave_date else ""
        body = _(
            "Đơn xin nghỉ của bạn vào %(date)s đã bị tự động hủy do quá thời gian chờ bàn giao công việc. "
            "Vui lòng tạo đơn mới nếu vẫn cần nghỉ."
        ) % {"date": leave_date_text}
        try:
            bot_user = self.env.ref("base.user_root")
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([requester_user.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed to send auto-cancel OdooBot chat leave_id=%s requester_user_id=%s",
                self.id,
                requester_user.id,
            )

    def _bot_status_current_step_details(self):
        """Return (step_label, approver_descriptions) for bot status replies."""
        self.ensure_one()
        step_label = self.approval_current_step_label or _("Đang chờ duyệt")
        approver_descriptions = []
        if self.validation_type == "employee_hr_responsibles":
            pending = self.responsible_approval_line_ids.filtered(
                lambda line: line.state == "pending"
            ).sorted("sequence")
            mode = self.holiday_status_id.employee_responsible_approval_mode or "any"
            current_lines = (
                self._responsible_pending_current_wave()
                if mode == "sequential"
                else pending
            )
            for line in current_lines:
                user = line.user_id
                if not user:
                    continue
                employee = user.employee_id
                job_title = employee.job_title if employee and employee.job_title else False
                if job_title:
                    approver_descriptions.append("%s (%s)" % (user.name, job_title))
                else:
                    approver_descriptions.append(user.name)
        elif self.validation_type == "multi_step_6":
            step = self._get_current_multi_step()
            if step:
                users = step._get_all_approver_users()
                if step.name:
                    step_label = step.name
                for user in users:
                    employee = user.employee_id
                    job_title = employee.job_title if employee and employee.job_title else False
                    if job_title:
                        approver_descriptions.append("%s (%s)" % (user.name, job_title))
                    else:
                        approver_descriptions.append(user.name)
        return step_label, approver_descriptions

    def action_confirm(self):
        missing_handover = self.filtered(
            lambda leave: not leave.skip_work_handover and not leave.handover_employee_ids
        )
        if missing_handover:
            raise UserError(
                _(
                    "Vui lòng chọn ít nhất một người nhận bàn giao công việc trước khi gửi đơn xin nghỉ phép."
                )
            )
        try:
            # write(state='confirm') inside super() already handles submit notifications.
            # Avoid duplicate DM sends from this action wrapper.
            res = super(
                HolidaysRequest,
                self.with_context(
                    **{
                        _SKIP_SUBMIT_BOT_NOTIFY_CTX: True,
                        _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX: True,
                    }
                ),
            ).action_confirm()
        except AttributeError:
            res = True
        subset = self.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles" and l.state == "confirm"
        )
        if subset:
            subset._ensure_responsible_approval_lines()
            subset._responsible_backfill_pending_since_if_missing()
            for leave in subset:
                leave._notify_responsible_approvers_submission()
                leave._notify_responsible_current_turn()
        self._bootstrap_handover_workflow()
        self._mark_handover_requested_at()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._apply_emergency_leave_on_vals(vals)
        records = super().create(vals_list)
        records._ensure_responsible_approval_lines()
        records._responsible_backfill_pending_since_if_missing()
        records._bootstrap_handover_workflow()
        records._mark_handover_requested_at()
        # Notify once when records are created directly in submit state.
        records.filtered(lambda l: l.state == "confirm")._notify_handover_recipients_submit_via_bot()
        submit_responsible_leaves = records.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles" and l.state == "confirm"
        )
        if submit_responsible_leaves:
            for leave in submit_responsible_leaves:
                leave._notify_responsible_approvers_submission()
                leave._notify_responsible_current_turn()
        return records

    def _check_approval_update(self, state, raise_if_not_possible=True):
        """Demo extension:
        allow extra officers / extra office-departments configured on Time Off Type to approve/refuse.
        """
        if self.env.is_superuser():
            return True

        current_employee = self.env.user.employee_id
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")
        is_manager = self.env.user.has_group("hr_holidays.group_hr_holidays_manager")

        for holiday in self:
            if state in ("validate1", "validate", "refuse"):
                blocking = holiday._get_handover_blocking_employees()
                if blocking:
                    if raise_if_not_possible:
                        raise UserError(
                            _(
                                "Duyệt đơn đang bị khóa cho đến khi tất cả người nhận bàn giao chấp nhận. "
                                "Hiện vẫn đang chờ: %(names)s."
                            )
                            % {"names": ", ".join(blocking.mapped("name"))}
                        )
                    return False
            val_type = holiday.validation_type
            is_extra_officer = self.env.user in holiday.extra_approver_user_ids
            is_officer_any = is_officer or is_extra_officer

            if val_type == "multi_step_6":
                if not is_manager:
                    approvers = holiday._get_multi_step_approvers()
                    if self.env.user not in approvers:
                        if raise_if_not_possible:
                            raise UserError(_("Bạn không được phép duyệt/từ chối bước nghỉ phép nhiều cấp này."))
                        return False
                continue

            if val_type == "employee_hr_responsibles":
                if state in ("validate", "refuse"):
                    if not is_manager and holiday._employee_hr_blocks_self_approval_non_director():
                        if raise_if_not_possible:
                            raise UserError(
                                _(
                                    "Trong luồng này, chỉ nhân viên có chức danh \"Giám đốc\" mới được duyệt hoặc từ chối "
                                    "đơn nghỉ phép của chính mình. Những người duyệt khác phải xử lý đơn của người khác."
                                )
                            )
                        return False
                    if not is_manager and self.env.user not in holiday._get_responsible_approval_users():
                        if raise_if_not_possible:
                            raise UserError(_("Bạn không được phép duyệt/từ chối đơn nghỉ phép này trong luồng phụ trách hiện tại."))
                        return False
                continue

            if not is_manager and state != "confirm":
                if state == "draft":
                    if holiday.state == "refuse":
                        raise UserError(_("Chỉ Quản lý nghỉ phép mới có thể đặt lại đơn đã bị từ chối."))
                    if holiday.date_from and holiday.date_from.date() <= fields.Date.today():
                        raise UserError(_("Chỉ Quản lý nghỉ phép mới có thể đặt lại đơn đã bắt đầu."))
                    if holiday.employee_id != current_employee:
                        raise UserError(_("Chỉ Quản lý nghỉ phép mới có thể đặt lại đơn nghỉ phép của người khác."))
                else:
                    if val_type == "no_validation" and current_employee == holiday.employee_id and (
                        is_officer_any or is_manager
                    ):
                        continue
                    # use ir.rule based first access check: department, members, ... (see security.xml)
                    holiday.check_access_rule("write")

                    # This handles states validate1 / validate / refuse
                    if (
                        holiday.employee_id == current_employee
                        and self.env.user != holiday.employee_id.leave_manager_id
                        and not is_officer_any
                    ):
                        raise UserError(
                            _("Chỉ Cán bộ nghỉ phép hoặc Quản lý nghỉ phép mới có thể duyệt/từ chối yêu cầu của chính mình.")
                        )

                    if (state == "validate1" and val_type == "both") and holiday.employee_id:
                        if not is_officer_any and self.env.user != holiday.employee_id.leave_manager_id:
                            raise UserError(
                                _("Bạn phải là quản lý của %s hoặc là Quản lý nghỉ phép để duyệt đơn này")
                                % (holiday.employee_id.name,)
                            )

                    if (
                        state == "validate"
                        and val_type == "manager"
                        and self.env.user
                        != (holiday.employee_id | holiday.sudo().employee_ids).leave_manager_id
                        and not is_officer_any
                    ):
                        if holiday.employee_id:
                            employees = holiday.employee_id
                        else:
                            employees = ", ".join(
                                holiday.employee_ids.filtered(lambda e: e.leave_manager_id != self.env.user).mapped(
                                    "name"
                                )
                            )
                        raise UserError(_("Bạn phải là quản lý của %s để duyệt đơn này", employees))

                    if (
                        not is_officer_any
                        and (state == "validate" and val_type == "hr")
                        and holiday.employee_id
                    ):
                        raise UserError(_("Bạn phải là Cán bộ nghỉ phép hoặc Quản lý nghỉ phép để duyệt đơn này"))

        return True

    def action_approve(self, check_state=True):
        self._ensure_handover_ready_for_approval()
        return super().action_approve(check_state=check_state)

    def action_multi_step_approve(self):
        """Approve one multi-step level (demo, fixed 6 steps)."""
        self.ensure_one()
        if self.validation_type != "multi_step_6":
            raise UserError(_("Đơn nghỉ phép này chưa được cấu hình duyệt nhiều cấp."))
        if self.state != "confirm":
            raise UserError(_("Đơn nghỉ phép phải ở trạng thái 'Chờ duyệt' để duyệt theo từng bước."))
        self._ensure_handover_ready_for_approval()

        approvers = self._get_multi_step_approvers()
        is_manager = self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        if not is_manager and self.env.user not in approvers:
            raise UserError(_("Bạn không có quyền duyệt bước hiện tại."))

        step = self._get_current_multi_step()
        if not step:
            raise UserError(_("Thiếu cấu hình duyệt nhiều cấp cho bước %s.") % self.multi_step_current)

        if not self._multi_step_previous_steps_logged():
            raise UserError(
                _("Thiếu log của các bước duyệt trước đó. Cần duyệt đúng thứ tự (bước 1, rồi bước 2, ...).")
            )

        self.env["hr.leave.multi.approval"].create(
            {
                "leave_id": self.id,
                "step_id": step.id,
                "approver_user_id": self.env.user.id,
            }
        )

        max_seq = max(self.holiday_status_id.multi_approval_step_ids.mapped("sequence") or [1])
        if self.multi_step_current < max_seq:
            self.write({"multi_step_current": self.multi_step_current + 1})
            self.activity_update()
            return True

        return self._action_validate(check_state=False)

    def action_cancel(self):
        """Guard cancel wizard against unsaved dashboard popup records.

        In the calendar popup, users can click "Cancel Time Off" before the leave is actually saved.
        Base wizard needs a persisted leave_id; otherwise it crashes with required field missing.
        """
        self.ensure_one()
        leave_id = self._origin.id or (self.id if isinstance(self.id, Integral) else False)
        if not leave_id:
            return {"type": "ir.actions.act_window_close"}
        return {
            "name": _("Hủy nghỉ phép"),
            "type": "ir.actions.act_window",
            "target": "new",
            "res_model": "hr.holidays.cancel.leave",
            "view_mode": "form",
            "views": [[False, "form"]],
            "context": {
                "default_leave_id": leave_id,
                "dialog_size": "medium",
            },
        }

    def action_multi_step_refuse(self, reason=False):
        """Refuse a multi-step leave at the current step."""
        self.ensure_one()
        if not (reason or "").strip():
            return self.action_open_multi_step_refuse_wizard()
        if self.validation_type != "multi_step_6":
            raise UserError(_("Đơn nghỉ phép này chưa được cấu hình duyệt nhiều cấp."))
        if self.state != "confirm":
            raise UserError(_("Đơn nghỉ phép phải ở trạng thái 'Chờ duyệt' để từ chối theo từng bước."))
        self._ensure_handover_ready_for_approval()

        approvers = self._get_multi_step_approvers()
        is_manager = self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        if not is_manager and self.env.user not in approvers:
            raise UserError(_("Bạn không có quyền từ chối bước hiện tại."))

        step = self._get_current_multi_step()
        if step:
            self.env["hr.leave.multi.approval"].create(
                {
                    "leave_id": self.id,
                    "step_id": step.id,
                    "approver_user_id": self.env.user.id,
                }
            )

        return self.action_refuse(reason=reason)

    def action_responsible_approve(self):
        self.ensure_one()
        if self.validation_type != "employee_hr_responsibles":
            raise UserError(_("Đơn nghỉ phép này chưa được cấu hình luồng Người phụ trách HR của nhân viên."))
        if self.state not in ("confirm", "validate1"):
            raise UserError(_("Đơn nghỉ phép phải ở trạng thái 'Chờ duyệt' hoặc 'Duyệt cấp 2'."))
        self._ensure_handover_ready_for_approval()

        is_manager = self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        is_responsible = self.env.user in self._get_responsible_approval_users()
        mode = self.holiday_status_id.employee_responsible_approval_mode
        if mode == "sequential":
            if not is_responsible:
                raise UserError(_("Bạn không được phép duyệt đơn nghỉ phép này."))
        elif not is_manager and not is_responsible:
            raise UserError(_("Bạn không được phép duyệt đơn nghỉ phép này."))
        if (mode == "sequential" or not is_manager) and self._employee_hr_blocks_self_approval_non_director():
            raise UserError(
                _(
                    "Only employees with job title \"Director\" may approve their own time off in this workflow. "
                    "Ask another approver in the chain."
                )
            )

        if not self.responsible_approval_line_ids:
            self._init_responsible_approval_lines()

        user_line = self.responsible_approval_line_ids.filtered(
            lambda l: l.user_id == self.env.user
        )[:1]
        if user_line and user_line.state != "pending":
            raise UserError(_("Bạn đã xử lý duyệt đơn nghỉ phép này rồi."))

        if mode == "sequential":
            wave = self._responsible_pending_current_wave()
            if not user_line or not wave or user_line not in wave:
                raise UserError(_("Đơn nghỉ phép này phải được duyệt đúng thứ tự tuần tự."))

        if is_responsible and user_line:
            user_line.write({"state": "approved", "action_date": fields.Datetime.now()})
            if mode == "sequential":
                approved_seq = user_line.sequence
                next_wave = self._responsible_pending_current_wave()
                if next_wave:
                    if next_wave[0].sequence != approved_seq:
                        next_wave.write({"pending_since": fields.Datetime.now()})
                    else:
                        missing_since = next_wave.filtered(lambda ln: not ln.pending_since)
                        if missing_since:
                            missing_since.write({"pending_since": fields.Datetime.now()})
                    self._notify_responsible_current_turn()

        if mode == "any":
            return self._action_validate(check_state=False)

        pending = self.responsible_approval_line_ids.filtered(lambda l: l.state == "pending")
        if not pending:
            return self._action_validate(check_state=False)

        self.activity_update()
        return True

    def action_responsible_refuse(self, reason=False):
        self.ensure_one()
        if not (reason or "").strip():
            return self.action_open_responsible_refuse_wizard()
        if self.validation_type != "employee_hr_responsibles":
            raise UserError(_("Đơn nghỉ phép này chưa được cấu hình luồng Người phụ trách HR của nhân viên."))
        if self.state not in ("confirm", "validate1"):
            raise UserError(_("Đơn nghỉ phép phải ở trạng thái 'Chờ duyệt' hoặc 'Duyệt cấp 2'."))
        self._ensure_handover_ready_for_approval()

        is_manager = self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        is_responsible = self.env.user in self._get_responsible_approval_users()
        mode = self.holiday_status_id.employee_responsible_approval_mode
        if mode == "sequential":
            if not is_responsible:
                raise UserError(_("Bạn không được phép từ chối đơn nghỉ phép này."))
        elif not is_manager and not is_responsible:
            raise UserError(_("Bạn không được phép từ chối đơn nghỉ phép này."))
        if (mode == "sequential" or not is_manager) and self._employee_hr_blocks_self_approval_non_director():
            raise UserError(
                _(
                    "Only employees with job title \"Director\" may refuse their own time off in this workflow. "
                    "Ask another approver in the chain."
                )
            )

        if not self.responsible_approval_line_ids:
            self._init_responsible_approval_lines()

        user_line = self.responsible_approval_line_ids.filtered(
            lambda l: l.user_id == self.env.user
        )[:1]
        if mode == "sequential":
            wave = self._responsible_pending_current_wave()
            if not user_line or not wave or user_line not in wave:
                raise UserError(_("Đơn nghỉ phép này phải được từ chối đúng thứ tự tuần tự."))

        if user_line and user_line.state == "pending":
            user_line.write({"state": "refused", "action_date": fields.Datetime.now()})

        return self.action_refuse(reason=reason)

    def action_open_refuse_wizard(self, refuse_action="standard"):
        return {
            "name": _("Từ chối duyệt đơn nghỉ phép"),
            "type": "ir.actions.act_window",
            "target": "new",
            "res_model": "hr.leave.refuse.wizard",
            "view_mode": "form",
            "views": [[False, "form"]],
            "context": {
                "default_leave_ids": self.ids,
                "default_refuse_action": refuse_action,
                "dialog_size": "medium",
            },
        }

    def action_open_multi_step_refuse_wizard(self):
        self.ensure_one()
        return self.action_open_refuse_wizard(refuse_action="multi_step")

    def action_open_responsible_refuse_wizard(self):
        self.ensure_one()
        return self.action_open_refuse_wizard(refuse_action="responsible")

    def action_refuse(self, reason=False):
        if not (reason or "").strip():
            return self.action_open_refuse_wizard()
        self._ensure_handover_ready_for_approval()
        reason_text = (reason or "").strip()
        current_employee = self.env.user.employee_id
        if any(leave.state not in ("confirm", "validate", "validate1") for leave in self):
            raise UserError(
                _("Time off request must be confirmed or validated in order to refuse it.")
            )
        if reason_text:
            self.write(
                {
                    "last_refusal_reason": reason_text,
                    "last_refuser_id": self.env.user.id,
                }
            )
        # Re-implement refusal flow to avoid base fallback message body
        # "Đơn xin nghỉ ... đã bị từ chối." and keep only custom message template.
        self._notify_manager()
        validated_holidays = self.filtered(lambda leave: leave.state == "validate1")
        if validated_holidays:
            validated_holidays.with_context(**{_SKIP_OUTCOME_BOT_NOTIFY_CTX: True}).write(
                {"state": "refuse", "first_approver_id": current_employee.id}
            )
        (self - validated_holidays).with_context(
            **{_SKIP_OUTCOME_BOT_NOTIFY_CTX: True}
        ).write(
            {"state": "refuse", "second_approver_id": current_employee.id}
        )
        self.mapped("meeting_id").write({"active": False})
        if reason_text:
            for leave in self:
                leave.message_post(
                    body=_("Lý do từ chối duyệt: %(reason)s", reason=reason_text),
                    subtype_xmlid="mail.mt_note",
                )
        self.activity_update()
        for leave in self:
            leave._notify_requester_approval_outcome_via_bot(
                "refuse",
                refusal_reason=reason_text,
                refuser_name=self.env.user.display_name,
            )
        return True

    @api.model
    def cron_escalate_responsible_approval_timeouts(self):
        """Sequential Employee HR Responsibles: skip current step after escalation delay (default 2h)."""
        leaves = self.sudo().search(
            [
                ("state", "in", ("confirm", "validate1")),
                ("validation_type", "=", "employee_hr_responsibles"),
            ]
        )
        for leave in leaves:
            try:
                leave._apply_responsible_timeout_escalation()
            except Exception:
                _logger.exception(
                    "time_off_extra_approval: responsible-timeout escalation failed for leave id=%s",
                    leave.id,
                )

    @api.model
    def cron_escalate_handover_timeouts(self):
        leaves = self.sudo().search(
            [
                ("state", "in", ("confirm", "validate1")),
                ("handover_employee_ids", "!=", False),
            ]
        )
        for leave in leaves:
            if not leave.handover_escalated:
                leave._apply_handover_timeout_escalation()
            else:
                leave._apply_handover_timeout_escalation_to_department_manager()
            leave._apply_handover_timeout_cancel_at_max_level()

    def _apply_handover_timeout_escalation(self):
        self.ensure_one()
        if self.handover_escalated:
            return
        if not self._handover_past_due_without_any_acceptance():
            return
        # First escalation is sequential: escalate to the immediate next manager.
        # Further steps are handled by _apply_handover_timeout_escalation_to_department_manager().
        dept_head_user = self._get_next_manager_user_from_user(self.employee_id.user_id)
        first_hours = self._handover_escalation_after_hours()
        if not dept_head_user:
            self.message_post(
                body=_(
                    "Handover timeout reached (%(hours)s h), but no manager user was found in org chart."
                )
                % {"hours": first_hours},
                subtype_xmlid="mail.mt_note",
            )
            return
        owner_emp = self._handover_employee_for_assigner_user(dept_head_user)
        owner_title = owner_emp.job_title if owner_emp and owner_emp.job_title else _("cấp tiếp theo")
        self.sudo().write(
            {
                "handover_escalated": True,
                "handover_escalated_at": fields.Datetime.now(),
                "handover_escalation_level": 1,
                "handover_escalation_user_id": dept_head_user.id,
            }
        )
        self.message_post(
            body=_(
                "Handover timeout reached (%(hours)s h). Escalated to %(user)s (%(title)s) to assign replacement."
            )
            % {
                "hours": first_hours,
                "user": dept_head_user.display_name,
                "title": owner_title,
            },
            subtype_xmlid="mail.mt_note",
        )
        self._notify_handover_timeout_escalation(dept_head_user, hours=first_hours)

    def _apply_handover_timeout_escalation_to_department_manager(self):
        self.ensure_one()
        if not self.handover_escalated:
            return
        if self._handover_is_max_escalation_reached():
            return
        if self._handover_owner_selected_replacement():
            return
        base_time = self.handover_escalated_at or self.handover_requested_at or self.create_date
        if not base_time:
            return
        second_hours = self._handover_second_escalation_hours()
        threshold = fields.Datetime.now() - timedelta(hours=second_hours)
        if base_time > threshold:
            return
        manager_user = self._get_next_manager_user_from_user(self.handover_escalation_user_id)
        if not manager_user or manager_user == self.handover_escalation_user_id:
            self.message_post(
                body=_(
                    "Handover escalation remained unassigned after %(hours)s hours, but no next manager user was found above %(owner)s."
                )
                % {
                    "hours": second_hours,
                    "owner": self.handover_escalation_user_id.display_name or _("trưởng bộ phận"),
                },
                subtype_xmlid="mail.mt_note",
            )
            return
        self.sudo().write(
            {
                "handover_escalated": True,
                "handover_escalated_at": fields.Datetime.now(),
                "handover_escalation_level": (self.handover_escalation_level or 1) + 1,
                "handover_escalation_user_id": manager_user.id,
            }
        )
        manager_emp = self._handover_employee_for_assigner_user(manager_user)
        manager_title = manager_emp.job_title if manager_emp and manager_emp.job_title else _("cấp tiếp theo")
        self.message_post(
            body=_(
                "Handover still had no replacement after %(hours)s hours at current level. "
                "Escalated to %(user)s (%(manager_title)s)."
            )
            % {
                "hours": second_hours,
                "user": manager_user.display_name,
                "manager_title": manager_title,
            },
            subtype_xmlid="mail.mt_note",
        )
        self._notify_handover_timeout_escalation(manager_user, hours=second_hours)

    def _apply_handover_timeout_cancel_at_max_level(self):
        self.ensure_one()
        if not self._handover_should_auto_cancel_at_max_level():
            return
        if self.state not in ("confirm", "validate1"):
            return
        active_lines = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids
        )
        if active_lines.filtered(lambda l: l.state == "accepted"):
            return
        if self._handover_owner_selected_replacement():
            return
        requested_at = self.handover_requested_at or self.create_date
        if not requested_at:
            return
        max_title = self._handover_max_escalation_job_title()
        cancel_after = self._handover_cancel_after_max_hours()
        total_hours = self._handover_escalation_after_hours() + cancel_after
        now = fields.Datetime.now()
        if requested_at > now - timedelta(hours=total_hours):
            return
        self.with_context(**{_SKIP_OUTCOME_BOT_NOTIFY_CTX: True}).sudo().write({"state": "cancel"})
        self.message_post(
            body=_(
                "Handover stayed unresolved after escalation timeout "
                "and max-level timeout (max title: %(title)s, cancel timeout: %(hours)s h). "
                "This leave request was canceled automatically; requester must create a new request."
            )
            % {"title": max_title, "hours": cancel_after},
            subtype_xmlid="mail.mt_note",
        )
        requester_user = self.employee_id.user_id
        if requester_user and requester_user.partner_id and not requester_user.share:
            self._notify_requester_auto_cancel_via_odoo_bot()
            self.message_notify(
                partner_ids=requester_user.partner_id.ids,
                subject=_("Đơn nghỉ phép đã tự động hủy"),
                body=_(
                    "Đơn nghỉ phép %(leave)s của bạn đã bị hệ thống tự động hủy vì quá thời gian chờ "
                    "nhận bàn giao/duyệt theo cấu hình."
                )
                % {"leave": self.display_name},
            )
            self.activity_schedule(
                _TODO_ACTIVITY_XMLID,
                user_id=requester_user.id,
                summary=_("Đơn nghỉ phép bị tự động hủy"),
                note=_(
                    "Đơn nghỉ phép %(leave)s đã bị tự động hủy do quá thời gian chờ bàn giao công việc. "
                    "Vui lòng tạo đơn mới nếu vẫn cần nghỉ."
                )
                % {"leave": self.display_name},
            )

    def _apply_responsible_timeout_escalation(self):
        self.ensure_one()
        if self.holiday_status_id.employee_responsible_approval_mode != "sequential":
            return
        if not self.responsible_approval_line_ids:
            return
        hours = self.holiday_status_id.employee_responsible_escalation_hours or 2.0
        threshold = fields.Datetime.now() - timedelta(hours=hours)
        wave = self._responsible_pending_current_wave()
        if not wave:
            return
        for ln in wave:
            if not ln.pending_since:
                ln.write({"pending_since": threshold - timedelta(seconds=1)})
        earliest = min(ln.pending_since for ln in wave)
        if earliest > threshold:
            return
        for first_pending in wave:
            skipped_user = first_pending.user_id
            first_pending.write(
                {
                    "state": "skipped",
                    "action_date": fields.Datetime.now(),
                }
            )
            self.message_post(
                body=_(
                    "Approval step for %(user)s was skipped due to timeout (%(hours)s h); escalated to the next level."
                )
                % {"user": skipped_user.display_name, "hours": hours},
                subtype_xmlid="mail.mt_note",
            )
        next_wave = self._responsible_pending_current_wave()
        if next_wave:
            now = fields.Datetime.now()
            next_wave.write({"pending_since": now})
            self.activity_update()
            self._notify_responsible_current_turn()
        else:
            self._action_validate(check_state=False)
