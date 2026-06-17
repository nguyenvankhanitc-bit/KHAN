# -*- coding: utf-8 -*-
import logging
import re
import unicodedata
from datetime import date, datetime, time, timedelta

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import MissingError, UserError, ValidationError
from odoo.tools import sql
from odoo.tools.float_utils import float_round
from odoo.tools.misc import format_date
from odoo.tools.translate import _

from odoo.addons.hr.models.hr_employee import _ALLOW_READ_HR_EMPLOYEE
from odoo.addons.time_off_extra_approval.models.hr_leave_type import (
    _ALLOW_WRITE_HR_LEAVE_TYPE,
)
from odoo.addons.time_off_work_handover import constants as handover_constants
from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION

_logger = logging.getLogger(__name__)

_HANDOVER_ACTIVITY_XMLID = handover_constants.HANDOVER_ACTIVITY_XMLID
_HANDOVER_ACTIVE_STATES = handover_constants.HANDOVER_ACTIVE_STATES
_TODO_ACTIVITY_XMLID = "mail.mail_activity_data_todo"
_HANDOVER_ESCALATION_MINUTES = handover_constants.HANDOVER_ESCALATION_MINUTES
_HANDOVER_ESCALATION_TO_MANAGER_HOURS = handover_constants.HANDOVER_ESCALATION_TO_MANAGER_HOURS
_DEPARTMENT_HEAD_JOB_TITLE_KEY = handover_constants.DEPARTMENT_HEAD_JOB_TITLE_KEY
_DEPARTMENT_MANAGER_JOB_TITLE_KEY = handover_constants.DEPARTMENT_MANAGER_JOB_TITLE_KEY
_SKIP_SUBMIT_BOT_NOTIFY_CTX = handover_constants.SKIP_SUBMIT_BOT_NOTIFY_CTX
_SKIP_OUTCOME_BOT_NOTIFY_CTX = handover_constants.SKIP_OUTCOME_BOT_NOTIFY_CTX
_STORE_REGION_HANDOVER_MIEN_CODES = handover_constants.STORE_REGION_HANDOVER_MIEN_CODES
_STORE_LEADER_HANDOVER_REQUIRED_JOB_TITLE_KEYS = (
    handover_constants.STORE_LEADER_HANDOVER_REQUIRED_JOB_TITLE_KEYS
)
_HANDOVER_EXEMPT_JOB_TITLE_KEYS = {"asm", "rsm"}


def _normalize_job_title_key(title):
    normalized = (title or "").strip().casefold()
    normalized = "".join(
        ch for ch in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(ch)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    aliases = {"truong bp": "truong bo phan"}
    return aliases.get(normalized, normalized)


def _job_title_rank_map():
    rank_map = {}
    for idx, (key, label) in enumerate(JOB_TITLE_SELECTION):
        rank_map[_normalize_job_title_key(key)] = idx
        rank_map[_normalize_job_title_key(label)] = idx
    return rank_map


_HANDOVER_ONCHANGE_TRIGGER_FIELDS = frozenset(
    {
        "handover_acceptance_ids",
        "handover_employee_ids",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
        "request_hour_from",
        "request_hour_to",
        "request_date_from_period",
        "request_date_to_period",
    }
)
_HANDOVER_ONCHANGE_SPEC_FIELDS = frozenset(
    {
        "handover_employee_ids",
        "unavailable_handover_employee_ids",
        "handover_refused_recipient_ids",
        "handover_replaceable_recipient_ids",
        "handover_acceptance_ids",
    }
)


class HrLeaveHandover(models.Model):
    _inherit = "hr.leave"

    def _with_handover_employee_read_context(self):
        """Allow internal relational reads while processing handover data."""
        return self.with_context(_allow_read_hr_employee=_ALLOW_READ_HR_EMPLOYEE)

    def _handover_employee_browse(self, employee_ids):
        """Browse colleagues for handover logic without tripping HR employee ACL."""
        Employee = self._with_handover_employee_read_context().env["hr.employee"]
        return Employee.sudo().browse(employee_ids)

    def _with_timeoff_self_service_write_context(self):
        """Handover M2M + leave-type stored computes during employee self-service."""
        ctx = {"_allow_read_hr_employee": _ALLOW_READ_HR_EMPLOYEE}
        if not self.env.user.has_group("hr_holidays.group_hr_holidays_user"):
            ctx["_allow_write_hr_leave_type"] = _ALLOW_WRITE_HR_LEAVE_TYPE
        return self.with_context(**ctx)

    @api.model
    def _is_handover_onchange(self, field_names):
        handover_fields = {"handover_acceptance_ids", "handover_employee_ids"}
        return any(
            (field_name or "").split(".", 1)[0] in handover_fields
            for field_name in (field_names or ())
        )

    @api.model
    def _needs_handover_read_context(self, field_names, fields_spec):
        """True when onchange may read colleague hr.employee rows for handover."""
        if any(
            (field_name or "").split(".", 1)[0] in _HANDOVER_ONCHANGE_TRIGGER_FIELDS
            for field_name in (field_names or ())
        ):
            return True
        if fields_spec and _HANDOVER_ONCHANGE_SPEC_FIELDS & set(fields_spec):
            return True
        return False

    @api.model
    def _handover_onchange_fields_spec(self, fields_spec):
        """Preserve trusted employee reads in nested onchange serialization."""
        result = {name: dict(spec) for name, spec in fields_spec.items()}
        for field_name in _HANDOVER_ONCHANGE_SPEC_FIELDS & result.keys():
            field_spec = result[field_name]
            field_spec["context"] = {
                **field_spec.get("context", {}),
                "_allow_read_hr_employee": _ALLOW_READ_HR_EMPLOYEE,
            }

        acceptance_spec = result.get("handover_acceptance_ids")
        if acceptance_spec is not None:
            acceptance_spec["context"] = {
                **acceptance_spec.get("context", {}),
                "_allow_read_hr_employee": _ALLOW_READ_HR_EMPLOYEE,
            }
            line_fields = {
                name: dict(spec)
                for name, spec in acceptance_spec.get("fields", {}).items()
            }
            employee_spec = line_fields.get("employee_id")
            if employee_spec is not None:
                employee_spec["context"] = {
                    **employee_spec.get("context", {}),
                    "_allow_read_hr_employee": _ALLOW_READ_HR_EMPLOYEE,
                }
            acceptance_spec["fields"] = line_fields
        return result

    def onchange(self, values, field_names, fields_spec):
        needs_handover = self._needs_handover_read_context(field_names, fields_spec)
        target = (
            self._with_handover_employee_read_context() if needs_handover else self
        )
        if needs_handover and fields_spec:
            fields_spec = self._handover_onchange_fields_spec(fields_spec)
        return super(HrLeaveHandover, target).onchange(
            values, field_names, fields_spec
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
    handover_waiting_label = fields.Char(
        string="Handover status",
        compute="_compute_handover_waiting_label",
    )
    handover_recipient_display = fields.Char(
        string="Work handover recipients",
        compute="_compute_handover_recipient_display",
    )
    handover_work_content_display = fields.Text(
        string="Work handover content",
        compute="_compute_handover_work_content_display",
    )
    leave_reason_display = fields.Char(
        string="Leave reason",
        compute="_compute_leave_reason_display",
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
        string="No work handover required",
        default=False,
        copy=False,
        help="Allow eligible senior employees to submit leave without handover recipients.",
    )
    can_skip_work_handover = fields.Boolean(
        string="Can skip work handover",
        compute="_compute_can_skip_work_handover",
    )
    can_respond_handover = fields.Boolean(
        string="Can respond to work handover",
        compute="_compute_can_respond_handover",
    )
    can_manage_handover_replacement = fields.Boolean(
        string="Can manage handover replacement",
        compute="_compute_can_manage_handover_replacement",
    )

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

    def _bootstrap_handover_workflow(self):
        """Create handover acknowledgement rows and schedule activities (clock menu) for recipients."""
        if self.env.context.get("leave_fast_create") or self.env.context.get("mail_activity_automation_skip"):
            return self
        leaves = self.filtered(
            lambda l: l.state == "confirm"
            and not l._should_skip_work_handover()
            and l.handover_employee_ids
        )
        leaves._sync_handover_acceptance_lines()
        leaves._schedule_work_handover_activities()
        return self

    def _get_employee_leave_mien(self, employee):
        if not employee:
            return False
        if hasattr(employee, "_get_leave_mien"):
            return employee._get_leave_mien()
        return employee.mien or False

    def _uses_store_region_handover_rules(self, employee):
        return self._get_employee_leave_mien(employee) in _STORE_REGION_HANDOVER_MIEN_CODES

    def _is_store_leader_handover_required_title(self, employee):
        """True when NT/CHT in Bắc/Nam/ĐTT must assign a handover recipient."""
        self.ensure_one()
        raw = self._read_job_title_safely(employee)
        return (
            _normalize_job_title_key(raw) in _STORE_LEADER_HANDOVER_REQUIRED_JOB_TITLE_KEYS
        )

    def _can_skip_work_handover_by_job_title(self, employee):
        if self._uses_store_region_handover_rules(employee):
            return not self._is_store_leader_handover_required_title(employee)
        return self._is_work_handover_exempt_job_title(
            employee
        ) or self._can_skip_workover_rank_for_employee(employee)

    def _is_work_handover_exempt_job_title(self, employee):
        """True for job titles that never require work handover on leave requests."""
        self.ensure_one()
        if self._uses_store_region_handover_rules(employee):
            return not self._is_store_leader_handover_required_title(employee)
        raw = self._read_job_title_safely(employee)
        return _normalize_job_title_key(raw) in _HANDOVER_EXEMPT_JOB_TITLE_KEYS

    def _should_skip_work_handover(self):
        self.ensure_one()
        employee = self._get_effective_employee_for_skip_handover()
        return bool(
            self.skip_work_handover
            or self._is_work_handover_exempt_job_title(employee)
        )

    def _apply_job_title_work_handover_exemption(self):
        exempt_leaves = self.filtered(
            lambda leave: not leave.skip_work_handover
            and leave._is_work_handover_exempt_job_title(
                leave._get_effective_employee_for_skip_handover()
            )
        )
        if exempt_leaves:
            exempt_leaves.write({"skip_work_handover": True})
        return self

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

    def _check_handover_content_required_on_submit(self):
        for leave in self:
            if leave.state not in ("confirm", "validate1", "validate"):
                continue
            if leave._should_skip_work_handover():
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
    def _check_handover_duplicate_recipients(self):
        for leave in self:
            employees = leave.handover_acceptance_ids.mapped("employee_id")
            if len(employees.ids) != len(set(employees.ids)):
                raise ValidationError(_("Mỗi người nhận bàn giao chỉ được xuất hiện một lần."))

    @api.constrains("state", "handover_acceptance_ids")
    def _check_handover_employee_availability(self):
        for leave in self.filtered("handover_employee_ids"):
            unavailable = leave._get_unavailable_handover_employees()
            if unavailable:
                raise ValidationError(
                    _(
                        "Selected handover recipients are on leave during this period: %(names)s. "
                        "Please choose other colleagues."
                    )
                    % {"names": ", ".join(unavailable.mapped("name"))}
                )

    @api.constrains("handover_employee_ids")
    def _check_handover_employee_limit(self):
        for leave in self:
            if len(leave.handover_employee_ids) > 5:
                raise ValidationError(_("Bạn chỉ có thể chọn tối đa 5 người nhận bàn giao công việc."))

    def _handover_recipient_employees(self):
        self.ensure_one()
        recipients = self.handover_employee_ids
        if not recipients:
            recipients = self.handover_acceptance_ids.mapped("employee_id")
        return recipients

    @api.constrains("handover_acceptance_ids")
    def _check_handover_required_on_submit(self):
        if self.env.context.get("import_file"):
            return
        for leave in self:
            if (
                leave.state in ("confirm", "validate1", "validate")
                and not leave._should_skip_work_handover()
                and not leave._handover_recipient_employees()
            ):
                raise ValidationError(
                    _("Vui lòng chọn ít nhất một người nhận bàn giao công việc trước khi gửi đơn xin nghỉ phép.")
                )

    @api.constrains(
        "skip_work_handover",
        "employee_id",
    )
    def _check_skip_work_handover_permission(self):
        for leave in self.filtered("skip_work_handover"):
            target_employee = leave._get_effective_employee_for_skip_handover()
            if not leave._can_skip_work_handover_by_job_title(target_employee):
                title_raw = leave._read_job_title_safely(target_employee)
                if leave._uses_store_region_handover_rules(target_employee):
                    message = _(
                        "Nhân viên có chức danh Nhóm trưởng hoặc Cửa hàng trưởng ở miền "
                        "%(mien)s phải bàn giao công việc khi xin nghỉ phép. "
                        "Nhân viên hiện tại: %(employee)s, chức danh: %(title)s."
                    )
                    params = {
                        "mien": leave._get_employee_leave_mien(target_employee) or "-",
                        "employee": target_employee.display_name or "-",
                        "title": title_raw or "-",
                    }
                else:
                    message = _(
                        "Chỉ nhân viên có chức danh ASM, RSM, hoặc từ Trưởng bộ phận trở lên "
                        "mới được phép bỏ qua bàn giao công việc. "
                        "Nhân viên hiện tại: %(employee)s, chức danh: %(title)s."
                    )
                    params = {
                        "employee": target_employee.display_name or "-",
                        "title": title_raw or "-",
                    }
                raise ValidationError(message % params)

    # --- Advance notice vs job title (emergency leave) -----------------------------------------

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
        "employee_id",
        "employee_id.job_title",
        "employee_id.mien",
        "employee_id.ma_bo_phan_id",
        "employee_id.ma_bo_phan_id.mien",
        "handover_employee_ids",
        "handover_employee_ids.name",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
        "handover_acceptance_ids.employee_id.name",
    )
    def _compute_can_skip_work_handover(self):
        for leave in self:
            leave.can_skip_work_handover = leave._can_skip_work_handover_by_job_title(
                leave._get_effective_employee_for_skip_handover()
            )

    @api.onchange("employee_id")
    def _onchange_employee_id_apply_handover_exemption(self):
        for leave in self:
            target_employee = leave._get_effective_employee_for_skip_handover()
            if leave._is_work_handover_exempt_job_title(target_employee):
                leave.skip_work_handover = True
            elif leave.skip_work_handover and not leave._can_skip_work_handover_by_job_title(
                target_employee
            ):
                leave.skip_work_handover = False

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
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
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
        "state",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "handover_acceptance_ids.employee_id",
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

    @api.depends("handover_employee_ids", "handover_employee_ids.name")
    def _compute_handover_recipient_display(self):
        for leave in self:
            names = leave.handover_employee_ids.mapped("name")
            leave.handover_recipient_display = ", ".join(name for name in names if name)

    @api.depends(
        "handover_acceptance_ids.handover_work_content",
        "handover_acceptance_ids.sequence",
    )
    def _compute_handover_work_content_display(self):
        Acceptance = self.env["hr.leave.handover.acceptance"].sudo()
        for leave in self:
            lines = Acceptance.search(
                [("leave_id", "=", leave.id)],
                order="sequence, id",
            )
            parts = [
                (line.handover_work_content or "").strip()
                for line in lines
                if (line.handover_work_content or "").strip()
            ]
            leave.handover_work_content_display = "\n".join(parts)

    @api.depends("name", "private_name", "employee_id", "user_id")
    def _compute_leave_reason_display(self):
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")
        for leave in self:
            if (
                is_officer
                or leave.user_id == self.env.user
                or leave.employee_id.leave_manager_id == self.env.user
            ):
                leave.leave_reason_display = (
                    leave.sudo().private_name or leave.name or ""
                ).strip()
            else:
                reason = (leave.name or "").strip()
                leave.leave_reason_display = "" if reason == "*****" else reason

    @api.depends(
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _compute_unavailable_handover_employee_ids(self):
        Employee = self._with_handover_employee_read_context().env["hr.employee"]
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
            unavailable_ids = overlapping.mapped("employee_id").ids
            leave.unavailable_handover_employee_ids = leave._handover_employee_browse(
                unavailable_ids
            )

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

    def _feedback_all_work_handover_activities(self):
        for leave in self:
            leave.activity_feedback(
                [_HANDOVER_ACTIVITY_XMLID],
                only_automated=False,
                feedback=_("Đơn xin nghỉ phép đã đóng."),
            )
        return self

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

    def _get_effective_employee_for_skip_handover(self):
        """The employee the rule applies to (the requester on the time off, not the current user)."""
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        if self.env.user.employee_id:
            return self.env.user.employee_id
        return self.env["hr.employee"]

    def _get_handover_blocking_employees(self):
        """Employees who have not accepted handover yet for current approval stage.

        Read the acceptance state with ``sudo()`` (via an explicit search rather
        than the ``handover_acceptance_ids`` o2m) so that the result is identical
        for every viewer. Approvers further up the chain (e.g. ASM → admin → admin
        tổng) are usually neither the requester nor a handover recipient, so the
        record rules on ``hr.leave.handover.acceptance`` would otherwise hide the
        accepted rows from them — making the leave look "still waiting for handover"
        and wrongly disabling their Approve button. A direct sudo search also
        bypasses any o2m field cache that record-rule filtering may have populated
        as empty for the current (non-privileged) user.
        """
        self.ensure_one()
        leave_su = self.sudo()
        if leave_su.state not in ("confirm", "validate1") or leave_su._should_skip_work_handover():
            return self.env["hr.employee"]
        active_recipients = leave_su.handover_employee_ids
        if not active_recipients:
            return self.env["hr.employee"]
        accepted = self.env["hr.leave.handover.acceptance"].sudo().search([
            ("leave_id", "=", leave_su.id),
            ("employee_id", "in", active_recipients.ids),
            ("state", "=", "accepted"),
        ]).mapped("employee_id")
        return active_recipients - accepted

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
        return self._handover_employee_browse(overlapping.mapped("employee_id").ids)

    @api.depends(
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
        "employee_id",
        "employee_id.parent_id",
    )
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
        button_html = leave._notify_handover_bot_leave_form_open_button_markup()
        who = leave._handover_who_label_for_line(line)
        if requester_name:
            first = _(
                "Bạn được yêu cầu bàn giao công việc khi %(name)s nghỉ "
                "(%(leave_type)s, %(dates)s)."
            ) % {"name": requester_name, "leave_type": leave_type, "dates": date_txt}
            return Markup("<p>%s</p><p>%s</p><p>%s</p>") % (first, footer, button_html)
        first = _(
            "You were asked to cover work while %(name)s is away (%(leave_type)s, %(dates)s)."
        ) % {"name": requester_name, "leave_type": leave_type, "dates": date_txt}
        second = _("Mở yêu cầu này và chọn Chấp nhận bàn giao hoặc Từ chối bàn giao.")
        return Markup("<p>%s</p><p>%s</p><p>%s</p>") % (first, second, button_html)

    def _handover_cancel_after_max_hours(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_cancel_after_max_hours:
            return self.holiday_status_id.handover_cancel_after_max_hours
        return 2.0

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

    def _handover_escalation_after_hours(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_escalation_after_hours:
            return self.holiday_status_id.handover_escalation_after_hours
        return _HANDOVER_ESCALATION_MINUTES / 60.0

    def _handover_format_job_name_from_employee(self, emp):
        if not emp:
            return ""
        jt = (emp.job_title or "").strip()
        nm = (emp.name or "").strip()
        return f"{jt} {nm}".strip() if jt else nm

    def _handover_format_job_name_from_user(self, user):
        return self._handover_format_job_name_from_employee(self._handover_employee_for_assigner_user(user))

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

    def _handover_job_title_rank(self, title_key):
        if not title_key:
            return -1
        rank_map = _job_title_rank_map()
        return rank_map.get(_normalize_job_title_key(title_key), -1)

    def _handover_max_escalation_job_title(self):
        self.ensure_one()
        if self.holiday_status_id and self.holiday_status_id.handover_escalation_max_job_title:
            return self.holiday_status_id.handover_escalation_max_job_title
        return _DEPARTMENT_HEAD_JOB_TITLE_KEY

    def _handover_owner_selected_replacement(self):
        self.ensure_one()
        owner = self.handover_escalation_user_id
        if not owner:
            return False
        active_lines = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids and l.state == "pending"
        )
        return bool(active_lines.filtered(lambda l: l.assigned_by_user_id == owner))

    def _handover_past_due_without_any_acceptance(self):
        """Same time/no-acceptance test as handover escalation cron (UI can show before cron sets handover_escalated)."""
        self.ensure_one()
        if (
            self.state not in ("confirm", "validate1")
            or self._should_skip_work_handover()
            or not self.handover_employee_ids
        ):
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

    def _handover_ready_for_approval(self):
        self.ensure_one()
        return not self._get_handover_blocking_employees()

    def _handover_second_escalation_hours(self):
        self.ensure_one()
        # Escalation should progress level-by-level on the same cadence configured by
        # "Handover: Escalate After (hours)". This makes each timeout hop to the next
        # manager and notify them until max escalation title is reached.
        return self._handover_escalation_after_hours()

    def _handover_should_auto_cancel_at_max_level(self):
        self.ensure_one()
        return bool(self.holiday_status_id and self.holiday_status_id.handover_cancel_if_max_unresponsive)

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

    def _mark_handover_requested_at(self):
        now = fields.Datetime.now()
        target = self.filtered(
            lambda l: l.state in ("confirm", "validate1")
            and not l._should_skip_work_handover()
            and l.handover_employee_ids
            and not l.handover_requested_at
        )
        if target:
            target.sudo().write({"handover_requested_at": now})
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

    def _notify_handover_bot_leave_form_open_button_markup(self):
        """OdooBot Bàn giao việc — same mobile-safe link as approval bot."""
        self.ensure_one()
        return self._notify_discuss_leave_open_button_markup(
            _("Mở Time Off"),
            discuss_link_type="handover",
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
        pending_recipients = self.handover_acceptance_ids.filtered(
            lambda l: l.employee_id in self.handover_employee_ids and l.state == "pending"
        ).mapped("employee_id")
        if pending_recipients:
            recipient_names = ", ".join(pending_recipients.mapped("name"))
        else:
            blocking = self._get_handover_blocking_employees()
            recipient_names = ", ".join(blocking.mapped("name")) if blocking else _("người được chỉ định")
        date_text = self._get_handover_bot_period_text()
        button_html = self._notify_handover_bot_leave_form_open_button_markup()
        bot_body = (
            Markup(
                _(
                    "Nhân viên <b>{recipient}</b> chưa xác nhận nhận bàn giao công việc cho đơn nghỉ phép ngày "
                    "<b>{date}</b> của nhân viên <b>{requester}</b>. Trưởng bộ phận vào ngày nghỉ "
                    "xem xét và quyết định duyệt hoặc từ chối ngày nghỉ phép.<br/><br/>"
                )
            ).format(recipient=recipient_names, date=date_text, requester=requester_name)
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
                .sudo()
                .with_user(dept_head_user)
                ._get_or_create_chat([bot_user.partner_id.id], pin=True)
            )
            post_vals = {
                "body": bot_body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
            }
            if bot_partner_id:
                post_vals["author_id"] = bot_partner_id
            chat.with_user(bot_user).sudo().message_post(**post_vals)
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
                    _("Open this request and assign another colleague in Work Handover To."),
                ),
            )

    # --- Discuss bot: plain-HTTP opener (mobile browsers handle this reliably) ---

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
                        "Open this request, then remove the declined recipient "
                        "or select another colleague in Work Handover To."
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

    @api.onchange("handover_acceptance_ids")
    def _onchange_handover_acceptance_ids(self):
        for leave in self:
            for idx, line in enumerate(leave.handover_acceptance_ids, start=1):
                line.sequence = idx
            employee_ids = leave.handover_acceptance_ids.sudo().mapped("employee_id").ids
            leave.handover_employee_ids = [Command.set(employee_ids)]

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

    def _read_job_title_safely(self, employee):
        """Read job_title without tripping hr.version wage field ACL for HR officers."""
        if not employee:
            return False
        if employee.job_title:
            return employee.job_title
        version = employee.sudo().current_version_id
        return version.job_title if version else False

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

    def _resequence_handover_acceptance_lines(self):
        for leave in self:
            lines = leave.handover_acceptance_ids.sudo().sorted(lambda l: (l.sequence or 0, l.id or 0))
            expected = 1
            for line in lines:
                if line.sequence != expected:
                    line.sequence = expected
                expected += 1
        return self

    def _schedule_work_handover_activities(self):
        today = fields.Date.today()
        for leave in self.filtered(
            lambda l: l.state in _HANDOVER_ACTIVE_STATES
            and not l._should_skip_work_handover()
            and l.handover_employee_ids
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
                if getattr(self, "_split_group_is_multi_segment", None) and self._split_group_is_multi_segment():
                    self._get_split_group_primary_leave()._notify_split_group_approval_after_handover_if_needed()
                else:
                    self._notify_responsible_current_turn()
        return True

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
            raise UserError(_("New handover recipients must be unique across lines."))
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

    def cron_escalate_handover_timeouts(self):
        leaves = self.sudo().search(
            [
                ("state", "in", ("confirm", "validate1")),
                ("skip_work_handover", "=", False),
                ("handover_employee_ids", "!=", False),
            ]
        )
        for leave in leaves.filtered(lambda l: not l._should_skip_work_handover()):
            if not leave.handover_escalated:
                leave._apply_handover_timeout_escalation()
            else:
                leave._apply_handover_timeout_escalation_to_department_manager()
            leave._apply_handover_timeout_cancel_at_max_level()


    @api.depends(
        "state",
        "validation_type",
        "responsible_approval_line_ids.state",
        "multi_step_current",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
    )
    @api.depends(
        "state",
        "is_emergency_leave",
        "employee_id",
        "department_id",
        "holiday_status_id",
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

    @api.depends(
        "state",
        "validation_type",
        "handover_employee_ids",
        "handover_acceptance_ids.state",
        "responsible_approval_line_ids.state",
        "multi_step_current",
    )
    def _compute_status_display_label(self):
        selection = dict(self._fields["state"].selection)
        for leave in self:
            label = selection.get(leave.state)
            if leave.state == "validate":
                label = _("Được duyệt")
            elif leave.state in ("confirm", "validate1"):
                if leave._get_handover_blocking_employees():
                    label = _("Đang chờ bàn giao công việc")
                elif leave.validation_type == "employee_hr_responsibles" and leave.responsible_approval_line_ids.filtered(
                    lambda line: line.state == "pending"
                )[:1]:
                    label = _("Đang chờ duyệt")
                elif leave.validation_type == "multi_step_6" and leave._get_current_multi_step():
                    label = _("Đang chờ duyệt")
                elif leave.validation_type not in ("employee_hr_responsibles", "multi_step_6"):
                    label = _("Đang chờ duyệt")
            leave.status_display_label = label

    @api.depends("number_of_hours", "number_of_days", "leave_type_request_unit")
    def _compute_duration_display(self):
        for leave in self:
            if leave.leave_type_request_unit == "hour":
                hours, minutes = divmod(abs(leave.number_of_hours) * 60, 60)
                minutes = round(minutes)
                if minutes == 60:
                    minutes = 0
                    hours += 1
                leave.duration_display = _("%d:%02d giờ") % (hours, minutes)
            else:
                duration = float_round(leave.number_of_days, precision_digits=2)
                if duration == int(duration):
                    duration = int(duration)
                leave.duration_display = _("%g ngày") % duration

    def _compute_can_multi_step_approve(self):
        super()._compute_can_multi_step_approve()
        for leave in self:
            if leave.can_multi_step_approve and not leave._handover_ready_for_approval():
                leave.can_multi_step_approve = False

    def _compute_can_responsible_approve(self):
        super()._compute_can_responsible_approve()
        for leave in self:
            if leave.can_responsible_approve and not leave._handover_ready_for_approval():
                leave.can_responsible_approve = False

    @api.model
    def _check_approval_update(self, state, raise_if_not_possible=True):
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
        return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

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
    def _compute_can_refuse(self):
        super()._compute_can_refuse()
        for leave in self.filtered(
            lambda h: h.validation_type in ("employee_hr_responsibles", "multi_step_6")
        ):
            leave.can_refuse = False
        for leave in self:
            if leave.can_refuse and not leave._handover_ready_for_approval():
                leave.can_refuse = False

    def _compute_can_validate(self):
        super()._compute_can_validate()
        for leave in self.filtered(
            lambda h: h.validation_type in ("employee_hr_responsibles", "multi_step_6")
        ):
            leave.can_validate = False
        for leave in self:
            if leave.can_validate and not leave._handover_ready_for_approval():
                leave.can_validate = False

    def _handover_write_before(self, vals):
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

    def _handover_write_after(self, vals, handover_lines_changed, submit_notify_target):
        if handover_lines_changed:
            self._sync_handover_employees_from_acceptance()
        if not self.env.context.get("leave_fast_create"):
            if vals.get("state") in ("confirm", "validate1"):
                self._mark_handover_requested_at()
            if vals.get("state") == "confirm" and submit_notify_target:
                submit_notify_target._notify_handover_recipients_submit_via_bot()
            if vals.get("state") in ("validate", "refuse", "cancel"):
                self._feedback_all_work_handover_activities()
            elif "handover_employee_ids" in vals:
                active_handover = self.filtered(
                    lambda l: l.state in _HANDOVER_ACTIVE_STATES
                    and not l._should_skip_work_handover()
                )
                active_handover._sync_handover_acceptance_lines()
                active_handover._mark_pending_handover_lines_as_escalation_assigned()
                active_handover._schedule_work_handover_activities()

    def write(self, vals):
        handover_lines_changed = bool(
            vals.get("handover_acceptance_ids") is not None and not self.env.context.get("skip_handover_line_sync")
        )
        submit_notify_target = self.env["hr.leave"]
        if (
            vals.get("state") == "confirm"
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_SUBMIT_BOT_NOTIFY_CTX)
        ):
            submit_notify_target = self.filtered(
                lambda l: l.state != "confirm"
                and not l._should_skip_work_handover()
                and l.handover_employee_ids
                and not l.split_group_id
            )
        self._handover_write_before(vals)
        res = super(HrLeaveHandover, self._with_timeoff_self_service_write_context()).write(vals)
        self._handover_write_after(vals, handover_lines_changed, submit_notify_target)
        return res

    def _collect_handover_submit_notify_primaries(self):
        """Resolve primary confirm leaves that still need a handover bot ping (post-split)."""
        if hasattr(self, "_monthly_mien_ensure_split_before_notify"):
            self._monthly_mien_ensure_split_before_notify()
        group_ids = [gid for gid in self.mapped("split_group_id") if gid]
        if group_ids:
            candidates = self.env["hr.leave"].search([("split_group_id", "in", group_ids)])
        else:
            candidates = self.env["hr.leave"].browse(self.ids)
        primaries = self.env["hr.leave"]
        seen = set()
        for leave in candidates.filtered(
            lambda l: l.state == "confirm" and not l._should_skip_work_handover()
        ):
            if not leave.handover_employee_ids or leave._handover_ready_for_approval():
                continue
            if leave.split_group_id:
                if not leave._split_group_is_multi_segment():
                    continue
                if not leave._is_split_group_primary_leave():
                    continue
                key = leave.split_group_id
            else:
                key = ("leave", leave.id)
            if key in seen:
                continue
            seen.add(key)
            notify_leave = (
                leave._get_handover_bot_notify_leave()
                if hasattr(leave, "_get_handover_bot_notify_leave")
                else leave
            )
            primaries |= notify_leave
        return primaries

    def _dispatch_handover_submit_bot_after_confirm(self):
        """Send OdooBot Bàn giao việc once after confirm + monthly/P1P2 split."""
        if self.env.context.get("leave_fast_create"):
            return
        primaries = self._collect_handover_submit_notify_primaries()
        for primary in primaries:
            ctx_key = primary._handover_split_submission_context_key(
                primary.split_group_id
            )
            if self.env.context.get(ctx_key):
                continue
            primary._notify_handover_recipients_submit_via_bot()

    def action_confirm(self):
        self.sudo()._apply_job_title_work_handover_exemption()
        missing_handover = self.filtered(
            lambda leave: not leave._should_skip_work_handover()
            and not leave._handover_recipient_employees()
        )
        if missing_handover:
            raise UserError(
                _("Vui lòng chọn ít nhất một người nhận bàn giao công việc trước khi gửi đơn xin nghỉ phép.")
            )
        res = super().action_confirm()
        self._bootstrap_handover_workflow()
        self._mark_handover_requested_at()
        self.with_context(**{_SKIP_SUBMIT_BOT_NOTIFY_CTX: False})._dispatch_handover_submit_bot_after_confirm()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        try:
            records = super(
                HrLeaveHandover, self._with_timeoff_self_service_write_context()
            ).create(vals_list)
        except MissingError:
            _logger.exception(
                "time_off_work_handover: MissingError during hr.leave create "
                "uid=%s employee_ids=%s handover_employee_ids=%s "
                "handover_acceptance_ids=%s",
                self.env.uid,
                [vals.get("employee_id") for vals in vals_list],
                [vals.get("handover_employee_ids") for vals in vals_list],
                [vals.get("handover_acceptance_ids") for vals in vals_list],
            )
            raise
        workflow_records = records.sudo()
        workflow_records._apply_job_title_work_handover_exemption()
        workflow_records.filtered(
            lambda l: l.handover_acceptance_ids and not l.handover_employee_ids
        )._sync_handover_employees_from_acceptance()
        workflow_records._bootstrap_handover_workflow()
        workflow_records._mark_handover_requested_at()
        if not self.env.context.get("leave_fast_create"):
            workflow_records.filtered(lambda l: l.state == "confirm").with_context(
                **{_SKIP_SUBMIT_BOT_NOTIFY_CTX: False}
            )._dispatch_handover_submit_bot_after_confirm()
        return records

    def web_save(self, vals, specification, next_id=None):
        """Keep the create/read boundary visible when relational reads fail."""
        try:
            if self:
                self.write(vals)
            else:
                self = self.create(vals)
            # Odoo flushes immediately after the RPC method returns. Flush here
            # so deferred stored computes remain inside this diagnostic boundary.
            self.env.flush_all()
        except MissingError:
            _logger.exception(
                "time_off_work_handover: MissingError during hr.leave web_save "
                "write/create/flush uid=%s leave_ids=%s employee_id=%s "
                "handover_employee_ids=%s acceptance_employee_ids=%s",
                self.env.uid,
                self.ids,
                vals.get("employee_id"),
                vals.get("handover_employee_ids"),
                [
                    command[2].get("employee_id")
                    for command in vals.get("handover_acceptance_ids", [])
                    if isinstance(command, (list, tuple))
                    and len(command) > 2
                    and isinstance(command[2], dict)
                ],
            )
            raise

        if next_id:
            self = self.browse(next_id)

        try:
            return self.with_context(bin_size=True).web_read(specification)
        except MissingError:
            _logger.exception(
                "time_off_work_handover: MissingError during hr.leave web_save "
                "serialization uid=%s leave_ids=%s specification_fields=%s",
                self.env.uid,
                self.ids,
                sorted(specification),
            )
            raise

    def web_read(self, specification):
        needs_handover = self._needs_handover_read_context((), specification)
        target = (
            self._with_handover_employee_read_context() if needs_handover else self
        )
        if needs_handover and specification:
            specification = self._handover_onchange_fields_spec(specification)
        try:
            return super(HrLeaveHandover, target).web_read(specification)
        except MissingError:
            _logger.exception(
                "time_off_work_handover: MissingError during hr.leave web_read "
                "uid=%s leave_ids=%s specification_fields=%s",
                self.env.uid,
                self.ids,
                sorted(specification),
            )
            raise
