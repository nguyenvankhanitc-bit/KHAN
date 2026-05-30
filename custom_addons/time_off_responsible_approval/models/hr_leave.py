# -*- coding: utf-8 -*-
import logging
import re
import unicodedata
from datetime import date, datetime, time, timedelta

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.translate import _

from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION
from odoo.addons.time_off_responsible_approval import constants as approval_constants

_logger = logging.getLogger(__name__)

_MULTI_STEP_RESET_CTX = approval_constants.MULTI_STEP_RESET_CTX
_SKIP_OUTCOME_BOT_NOTIFY_CTX = approval_constants.SKIP_OUTCOME_BOT_NOTIFY_CTX
_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX = approval_constants.SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX
_HR_RESPONSIBLE_APPROVAL_JOB_TITLE_ORDER = tuple(
    key for key, _label in JOB_TITLE_SELECTION if key != "nhân viên"
)
_DIRECTOR_JOB_TITLE_KEY = approval_constants.DIRECTOR_JOB_TITLE_KEY
_MAX_EMPLOYEE_HR_RESPONSIBLES = approval_constants.MAX_EMPLOYEE_HR_RESPONSIBLES
_MAX_EMPLOYEE_HR_RESPONSIBLES_MULTI_DIRECTOR = approval_constants.MAX_EMPLOYEE_HR_RESPONSIBLES_MULTI_DIRECTOR
# Org-chart walk stops after including the first approver whose Job Position (job_id.name, case-insensitive)
# matches any value in the applicable stop set.
_ORG_CHART_STOP_JOB_POSITIONS = frozenset({"sale admin"})
_ORG_CHART_STOP_JOB_POSITIONS_GIAM_SAT = frozenset({"human resources manager"})

# Job Position + Job Title of the single observer who receives FYI bot DMs but cannot approve.
_OBSERVER_JOB_POSITION = "tiền lương"
_OBSERVER_JOB_TITLE = "trưởng bộ phận"

# Job titles whose org-chart flow triggers observer notification (all miền).
_OBSERVER_JOB_TITLES = frozenset({"asm", "rsm"})
# Job titles whose org-chart flow triggers observer only when Miền = "Bắc".
_OBSERVER_JOB_TITLES_BAC = frozenset({"asm", "cửa hàng trưởng", "nhóm trưởng"})


def _job_title_approval_sort_key(user, order_index):
    title = user.employee_id.job_title if user.employee_id else False
    if title and title in order_index:
        return (order_index[title], user.id)
    return (len(order_index) + 1, user.id)


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


class HrLeaveResponsibleApproval(models.Model):
    _inherit = "hr.leave"

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
    approval_current_step_label = fields.Char(
        string="Current approval",
        compute="_compute_approval_current_step_label",
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

    def _compute_can_multi_step_approve(self):
        for leave in self:
            can = False
            if leave.validation_type == "multi_step_6" and leave.state == "confirm":
                is_manager = leave.env.user.has_group("hr_holidays.group_hr_holidays_manager")
                if is_manager:
                    can = True
                else:
                    can = leave.env.user in leave._get_multi_step_approvers()
            leave.can_multi_step_approve = can

    @api.depends(
        "state",
        "employee_id",
        "department_id",
        "holiday_status_id",
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

    def _employee_hr_chain_contains_director(self, users):
        self.ensure_one()
        UsersMdl = self.env["res.users"]
        for uid in users.ids:
            u = UsersMdl.browse(uid).sudo()
            emp = u.employee_id
            if emp and (emp.job_title or "") == _DIRECTOR_JOB_TITLE_KEY:
                return True
        return False

    def _employee_hr_expanded_director_suffix_users(self):
        """Director users substituted at end of chain for multi-director-special employees."""
        self.ensure_one()
        lt = self.holiday_status_id
        configured = self._get_configured_director_order_users()
        if lt and lt.special_director_sequential_approval and configured:
            return configured
        return self._get_company_director_users()

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

    def _employee_hr_substitute_final_director_with_department_manager(self, users):
        """Org-chart sequential flow: director wave uses department manager, not reporting-line director tier.

        Skipped when the leave targets the special \"all directors\" employee list — that flow keeps replacing
        the chain suffix with configured/company directors.
        """
        self.ensure_one()
        if self._is_multi_director_special_employee():
            return users
        lt = self.holiday_status_id
        if (
            not lt
            or lt.leave_validation_type != "employee_hr_responsibles"
            or lt.employee_responsible_source != "org_chart"
            or (lt.employee_responsible_approval_mode or "any") != "sequential"
        ):
            return users
        dept_user = self._get_leave_department_manager_user()
        if not dept_user:
            return users
        Users = self.env["res.users"]
        ids = list(users.ids)
        first_director_idx = None
        for idx, uid in enumerate(ids):
            u = Users.browse(uid).sudo()
            emp = u.employee_id
            if emp and (emp.job_title or "") == _DIRECTOR_JOB_TITLE_KEY:
                first_director_idx = idx
                break

        prefix_ids = ids[:first_director_idx] if first_director_idx is not None else ids
        if dept_user.id in prefix_ids:
            # Already in chain before director tier — avoid reordering ambiguous cases.
            return users
        if first_director_idx is None:
            if dept_user.id in ids:
                return users
            return Users.browse(ids + [dept_user.id])
        return Users.browse(prefix_ids + [dept_user.id])

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

    def _format_approval_bot_date(self, value):
        """Format a date as DD/MM/YYYY for approval-bot notifications."""
        if not value:
            return ""
        if isinstance(value, datetime):
            value = value.date()
        return value.strftime("%d/%m/%Y")

    def _get_approval_bot_leave_notification_details(self):
        """Display values for the OdooBot Duyệt đơn leave-request DM."""
        self.ensure_one()
        employee = self.employee_id
        requester_name = employee.name or employee.display_name or self.display_name
        id_hrm = (getattr(employee, "id_hrm", None) or "").strip() or "—"
        department = (employee.department_id.name or "").strip() or "—"
        date_from = self.request_date_from or (self.date_from and self.date_from.date())
        date_to = self.request_date_to or (self.date_to and self.date_to.date())
        date_from_text = self._format_approval_bot_date(date_from)
        if date_to and date_from and date_to != date_from:
            period_text = _("%(from)s đến ngày %(to)s") % {
                "from": date_from_text,
                "to": self._format_approval_bot_date(date_to),
            }
        else:
            period_text = date_from_text or "—"
        total_days = (self.duration_display or "").strip()
        if not total_days and self.number_of_days:
            total_days = "%g" % self.number_of_days
        reason = (self.notes or self.private_name or self.name or "").strip() or "—"
        return {
            "requester": requester_name,
            "id_hrm": id_hrm,
            "department": department,
            "period": period_text,
            "total_days": total_days or "—",
            "reason": reason,
        }

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

    def _get_current_multi_step(self):
        """Return the currently active multi-step config for this leave."""
        self.ensure_one()
        if self.validation_type != "multi_step_6":
            return self.env["hr.leave.type.approval.step"]
        steps = self.holiday_status_id.multi_approval_step_ids
        return steps.filtered(lambda s: s.sequence == self.multi_step_current)[:1]

    def _get_employee_responsible_users(self):
        self.ensure_one()
        users = self.employee_id.hr_responsible_ids
        if not users and self.employee_id.hr_responsible_id:
            users = self.employee_id.hr_responsible_id
        return users

    def _get_leave_department_manager_user(self):
        """User linked to ``hr.department.manager_id`` for the employee's department (internal users only)."""
        self.ensure_one()
        dept = self._get_leave_employee_department_for_approval()
        if not dept:
            return self.env["res.users"]
        mgr = dept.manager_id.sudo()
        if not mgr or not mgr.user_id or mgr.user_id.share:
            return self.env["res.users"]
        return mgr.user_id

    def _get_leave_employee_department_for_approval(self):
        """Department the request belongs to (same source as computed ``department_id`` on leave)."""
        self.ensure_one()
        dept = self.sudo().department_id or (
            self.employee_id.sudo().department_id if self.employee_id else self.env["hr.department"]
        )
        return dept

    def _get_multi_step_approvers(self):
        self.ensure_one()
        step = self._get_current_multi_step()
        return step and step._get_all_approver_users() or self.env["res.users"]

    def _get_org_chart_stop_positions(self):
        """Return the set of Job Position names (casefolded) at which the org-chart walk stops (inclusive).

        Priority:
          1. Special employee line with an explicit org_chart_stop_position set.
          2. Job-title-based default (giám sát → HR Manager, everyone else → SALE ADMIN).
        """
        self.ensure_one()
        special_line = self._get_special_employee_line()
        if special_line and special_line.org_chart_stop_position:
            return frozenset({special_line.org_chart_stop_position})
        emp = self.employee_id.sudo()
        if (emp.job_title or "").strip().lower() == "giám sát":
            return _ORG_CHART_STOP_JOB_POSITIONS_GIAM_SAT
        return _ORG_CHART_STOP_JOB_POSITIONS

    def _get_org_chart_approver_users_ordered(self):
        """Walk reporting line (parent_id) from direct manager upward: one approver per org level.

        Stops after including the first approver whose Job Position (job_id.name, casefolded)
        is in the stop set returned by _get_org_chart_stop_positions(). Higher levels are not added.
        """
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return self.env["res.users"]
        stop_positions = self._get_org_chart_stop_positions()
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
                if (mgr.job_id.name or "").strip().casefold() in stop_positions:
                    break
            cur = mgr.parent_id
        return Users.browse(user_ids)

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
        ordered = self._employee_hr_maybe_expand_multi_director(ordered)
        ordered = self._employee_hr_substitute_final_director_with_department_manager(ordered)
        return ordered

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
    )
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

    def _is_extra_approver(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return user in self.extra_approver_user_ids

    def _get_observer_user(self):
        """Return the single observer res.users (job_id.name == 'TIỀN LƯƠNG' and job_title == 'Trưởng bộ phận'), or empty."""
        emp = self.env["hr.employee"].sudo().search(
            [
                ("job_id.name", "ilike", _OBSERVER_JOB_POSITION),
                ("job_title", "ilike", _OBSERVER_JOB_TITLE),
                ("user_id", "!=", False),
            ],
            limit=1,
        )
        if not emp or not emp.user_id or emp.user_id.share:
            return self.env["res.users"]
        return emp.user_id

    def _leave_needs_observer_notify(self):
        """Return True when this leave's flow should send FYI bot DMs to the observer."""
        self.ensure_one()
        emp = self.employee_id.sudo()
        title = (emp.job_title or "").strip().lower()
        mien = (emp.mien or "").strip()

        # Special employee list (Dũng/Tuấn/Huy/Trà Phú/Long/Thế Anh/Vinh)
        if self._get_special_employee_line():
            return True
        # ASM/RSM → Admin chain (all Miền)
        if title in _OBSERVER_JOB_TITLES:
            return True
        # ASM others / CHT / NT in Miền Bắc
        if title in _OBSERVER_JOB_TITLES_BAC and mien == "Bắc":
            return True
        return False

    def _get_special_employee_line(self):
        """Return the special employee line for this leave's employee, or empty recordset."""
        self.ensure_one()
        lt = self.holiday_status_id
        if not lt or not self.employee_id:
            return self.env["hr.leave.type.special.employee.line"]
        return lt.special_director_employee_line_ids.filtered(
            lambda l: l.employee_id == self.employee_id
        )[:1]

    def _is_multi_director_special_employee(self):
        self.ensure_one()
        return bool(self._get_special_employee_line())

    def _is_special_parallel_directors_leave(self):
        """Special employee flow: directors act in parallel (same step, simultaneous notify)."""
        self.ensure_one()
        lt = self.holiday_status_id
        return bool(lt and self._is_multi_director_special_employee() and not lt.special_director_sequential_approval)

    def _multi_step_previous_steps_logged(self):
        """Steps 1..(current-1) must each appear in the approval log (sequential chain)."""
        self.ensure_one()
        if self.multi_step_current <= 1:
            return True
        done_seqs = set(self.multi_approval_line_ids.mapped("step_id.sequence"))
        needed = set(range(1, self.multi_step_current))
        return needed.issubset(done_seqs)

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
        if self._leave_needs_observer_notify():
            observer = self._get_observer_user()
            if observer:
                self._notify_responsible_current_turn_via_approval_bot(observer)

    def _notify_responsible_current_turn(self, user=None):
        """Notify approver(s) for the active sequential wave (one user, or all parallel directors)."""
        self.ensure_one()
        if (
            self.split_group_id
            and self._split_group_is_multi_segment()
            and not self._is_split_group_primary_leave()
        ):
            return
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
        # Also notify sale-admin users from the next pending step in parallel (FYI only — approval order unchanged).
        stop_positions = self._get_org_chart_stop_positions()
        current_seq = lines[0].sequence if lines else None
        notify_lines = lines
        if current_seq is not None:
            all_pending = self.responsible_approval_line_ids.filtered(
                lambda l: l.state == "pending" and l.sequence > current_seq
            ).sorted(lambda l: (l.sequence, l.id))
            for nxt in all_pending:
                job_pos = (nxt.user_id.sudo().employee_id.job_id.name or "").strip().casefold()
                if job_pos in stop_positions:
                    notify_lines = lines | nxt
                else:
                    break
        for line in notify_lines:
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
        if self._leave_needs_observer_notify():
            observer = self._get_observer_user()
            if observer and observer not in lines.mapped("user_id"):
                self._notify_responsible_current_turn_via_approval_bot(observer)

    @api.model
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
        details = self._get_approval_bot_leave_notification_details()
        lt_name = (self.holiday_status_id.name or "").strip() or "—"
        days_value = self.number_of_days or 0.0
        segment_line = _("• %(type)s: %(period)s (%(days)s ngày)") % {
            "type": lt_name,
            "period": details["period"],
            "days": ("%g" % days_value) if days_value else "0",
        }
        plan_details = {
            "requester": details["requester"],
            "id_hrm": details["id_hrm"],
            "department": details["department"],
            "period": details["period"],
            "total_days": details["total_days"],
            "reason": details["reason"],
            "segment_lines": segment_line,
            "segment_count": 1,
            "primary": self,
        }
        if hasattr(self, "_notify_approval_bot_monthly_plan_message"):
            return self._notify_approval_bot_monthly_plan_message(
                approver_user, plan_details
            )
        segments_html = Markup(escape(segment_line))
        intro = Markup(
            _(
                "<b>ĐƠN XIN NGHỈ PHÉP</b> ({count} phần)<br/>"
                "Nhân viên: <b>{requester}</b><br/>"
                "Mã nhân viên: <b>{id_hrm}</b><br/>"
                "Bộ phận: <b>{department}</b><br/>"
                "Thời gian nghỉ: <b>{period}</b><br/>"
                "Tổng số ngày nghỉ: <b>{total_days}</b><br/>"
                "Chi tiết:<br/>{segments}<br/>"
                "Lý do: <b>{reason}</b><br/>"
                "Vui lòng bấm <b>Phê duyệt tất cả</b> hoặc <b>Từ chối tất cả</b><br/><br/>"
            )
        ).format(
            count=1,
            requester=escape(str(details["requester"])),
            id_hrm=escape(str(details["id_hrm"])),
            department=escape(str(details["department"])),
            period=escape(str(details["period"])),
            total_days=escape(str(details["total_days"])),
            segments=segments_html,
            reason=escape(str(details["reason"])),
        )
        button_html = self._notify_approval_bot_split_group_action_buttons_markup(self)
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

    def _sort_responsible_users_by_job_title(self, users):
        """Sequential chain order: trưởng nhóm → trưởng BP → kiểm soát → trưởng phòng HCNS → giám đốc (see hr_job_title_vn)."""
        self.ensure_one()
        order_index = {title: idx for idx, title in enumerate(_HR_RESPONSIBLE_APPROVAL_JOB_TITLE_ORDER)}
        return users.sorted(
            key=lambda u: _job_title_approval_sort_key(u, order_index)
        )

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

    def action_open_multi_step_refuse_wizard(self):
        self.ensure_one()
        return self.action_open_refuse_wizard(refuse_action="multi_step")

    def action_open_responsible_refuse_wizard(self):
        self.ensure_one()
        return self.action_open_refuse_wizard(refuse_action="responsible")

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

    def _approval_write_before(self, vals):
        ctx = {}
        if (
            vals.get("state") in ("validate", "refuse", "cancel")
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_OUTCOME_BOT_NOTIFY_CTX)
        ):
            ctx["outcome_notify_prev_states"] = {leave.id: leave.state for leave in self}
        if (
            vals.get("state") == "confirm"
            and not self.env.context.get("leave_fast_create")
            and not self.env.context.get(_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX)
        ):
            ctx["responsible_submit_prev_states"] = {leave.id: leave.state for leave in self}
        reset_leaves = self.env["hr.leave"]
        if vals.get("state") == "confirm" and not self.env.context.get(_MULTI_STEP_RESET_CTX):
            reset_leaves = self.filtered(
                lambda l: l.validation_type == "multi_step_6" and l.state != "confirm"
            )
        ctx["reset_leaves"] = reset_leaves
        return ctx

    def _approval_write_after(self, vals, ctx):
        reset_leaves = ctx.get("reset_leaves") or self.env["hr.leave"]
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
        responsible_submit_prev_states = ctx.get("responsible_submit_prev_states") or {}
        if not self.env.context.get("leave_fast_create"):
            if vals.get("state") == "confirm" and responsible_submit_prev_states:
                submit_responsible_leaves = self.filtered(
                    lambda l: l.validation_type == "employee_hr_responsibles"
                    and l.state == "confirm"
                    and responsible_submit_prev_states.get(l.id) != "confirm"
                )
                if submit_responsible_leaves and not self.env.context.get(
                    _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX
                ):
                    submit_responsible_leaves._ensure_responsible_approval_lines()
                    submit_responsible_leaves._responsible_backfill_pending_since_if_missing()
                    submit_responsible_leaves._split_group_notify_submission_for_records()
            outcome_notify_prev_states = ctx.get("outcome_notify_prev_states") or {}
            if outcome_notify_prev_states:
                for leave in self:
                    prev = outcome_notify_prev_states.get(leave.id)
                    if leave.state in ("validate", "refuse", "cancel") and leave.state != prev:
                        leave._notify_requester_approval_outcome_via_bot(
                            leave.state,
                            refusal_reason=self.env.context.get("refusal_reason"),
                            refuser_name=self.env.context.get("refuser_name"),
                        )

    def write(self, vals):
        ctx = self._approval_write_before(vals)
        res = super().write(vals)
        self._approval_write_after(vals, ctx)
        return res

    def action_confirm(self):
        res = super().action_confirm()
        if self.env.context.get(_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX):
            return res
        subset = self.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles" and l.state == "confirm"
        )
        if subset:
            subset._ensure_responsible_approval_lines()
            subset._responsible_backfill_pending_since_if_missing()
            subset._split_group_notify_submission_for_records()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_responsible_approval_lines()
        records._responsible_backfill_pending_since_if_missing()
        submit_responsible_leaves = records.filtered(
            lambda l: l.validation_type == "employee_hr_responsibles" and l.state == "confirm"
        )
        if (
            submit_responsible_leaves
            and not self.env.context.get(_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX)
            and not self.env.context.get("leave_fast_create")
        ):
            submit_responsible_leaves._split_group_notify_submission_for_records()
        return records
