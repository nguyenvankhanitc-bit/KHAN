# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools.translate import _

from odoo.addons.time_off_responsible_approval import constants as approval_constants

from .hr_leave import _normalize_job_title_key

_logger = logging.getLogger(__name__)
_SKIP_OUTCOME_BOT_NOTIFY_CTX = "skip_outcome_bot_notify"
_DEFAULT_MAX_TITLE = "trưởng bộ phận"
_DEFAULT_ESCALATION_MINUTES = 5


class HrLeaveApprovalEscalation(models.Model):
    _inherit = "hr.leave"

    approval_escalated = fields.Boolean(
        string="Approval escalated",
        default=False,
        copy=False,
        help="Set when no approver acts within timeout and the request is escalated.",
    )
    approval_escalated_at = fields.Datetime(
        string="Approval escalated at",
        copy=False,
    )
    approval_escalation_level = fields.Integer(
        string="Approval escalation level",
        default=0,
        copy=False,
    )
    approval_escalation_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Approval escalation owner",
        copy=False,
        index=True,
    )
    approval_last_bot_escalation_signature = fields.Char(
        string="Approval last bot escalation signature",
        copy=False,
    )

    # --- Leave type config readers ---

    def _approval_escalation_after_hours(self):
        self.ensure_one()
        leave_type = self.holiday_status_id
        if leave_type and leave_type.approval_escalation_after_hours:
            return leave_type.approval_escalation_after_hours
        return _DEFAULT_ESCALATION_MINUTES / 60.0

    def _approval_escalation_mode(self):
        self.ensure_one()
        leave_type = self.holiday_status_id
        if leave_type and leave_type.approval_escalation_mode:
            return leave_type.approval_escalation_mode
        return "sequential"

    def _approval_escalation_is_direct(self):
        self.ensure_one()
        return self._approval_escalation_mode() == "direct"

    def _approval_max_escalation_job_title(self):
        self.ensure_one()
        leave_type = self.holiday_status_id
        if leave_type and leave_type.approval_escalation_max_job_title:
            return leave_type.approval_escalation_max_job_title
        return _DEFAULT_MAX_TITLE

    def _approval_should_auto_cancel_at_max_level(self):
        self.ensure_one()
        leave_type = self.holiday_status_id
        return bool(leave_type and leave_type.approval_cancel_if_max_unresponsive)

    def _approval_cancel_after_max_hours(self):
        self.ensure_one()
        leave_type = self.holiday_status_id
        if leave_type and leave_type.approval_cancel_after_max_hours:
            return leave_type.approval_cancel_after_max_hours
        return 2.0

    def _approval_second_escalation_hours(self):
        self.ensure_one()
        return self._approval_escalation_after_hours()

    # --- Org-chart helpers (reuse work-handover rank helpers when installed) ---

    def _approval_job_title_rank(self, title_key):
        rank_fn = getattr(super(), "_handover_job_title_rank", None)
        if rank_fn:
            return rank_fn(title_key)
        return -1

    def _get_approval_org_chart_user_for_exact_job_title(self, title_key):
        """First manager on the requester's chain with an exact job title match (internal user)."""
        self.ensure_one()
        exact_fn = getattr(super(), "_get_org_chart_user_for_exact_job_title", None)
        if exact_fn:
            return exact_fn(title_key)
        if not title_key:
            return self.env["res.users"]
        expected = _normalize_job_title_key(title_key)
        employee = self.employee_id
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

    def _get_approval_escalation_cap_user_for_max_title(self):
        """Exact match for configured approval max job title on the requester's org chart."""
        self.ensure_one()
        return self._get_approval_org_chart_user_for_exact_job_title(
            self._approval_max_escalation_job_title()
        )

    def _get_next_approval_manager_user_from_user(self, user):
        next_fn = getattr(super(), "_get_next_manager_user_from_user", None)
        if next_fn:
            return next_fn(user)
        self.ensure_one()
        if not user:
            return self.env["res.users"]
        employee_fn = getattr(super(), "_handover_employee_for_assigner_user", None)
        employee = employee_fn(user) if employee_fn else user.sudo().employee_id
        while employee and employee.parent_id:
            manager = employee.parent_id.sudo()
            if manager.user_id and not manager.user_id.share:
                return manager.user_id
            employee = manager
        return self.env["res.users"]

    def _approval_is_max_escalation_reached(self):
        self.ensure_one()
        owner = self.approval_escalation_user_id
        if not owner:
            return False
        cap_user = self._get_approval_escalation_cap_user_for_max_title()
        if cap_user and owner == cap_user:
            return True
        employee_fn = getattr(super(), "_handover_employee_for_assigner_user", None)
        owner_emp = employee_fn(owner) if employee_fn else owner.sudo().employee_id
        owner_title = _normalize_job_title_key(owner_emp.job_title if owner_emp else False)
        if owner_title == _normalize_job_title_key(self._approval_max_escalation_job_title()):
            return True
        return False

    def _approval_escalation_owner_acted(self):
        self.ensure_one()
        owner = self.approval_escalation_user_id
        if not owner:
            return False
        if self._is_responsible_approval_validation():
            line = self.responsible_approval_line_ids.filtered(
                lambda ln: ln.user_id == owner
                and ln.state in ("approved", "refused")
                and ln.action_date
                and (
                    not self.approval_escalated_at
                    or ln.action_date >= self.approval_escalated_at
                )
            )[:1]
            if line:
                return True
        return False

    def _approval_applies_to_leave(self):
        self.ensure_one()
        if self.state not in ("confirm", "validate1"):
            return False
        if getattr(self, "_should_skip_work_handover", None) and self._should_skip_work_handover():
            pass
        elif getattr(self, "_handover_ready_for_approval", None):
            if not self._handover_ready_for_approval():
                return False
        if self.validation_type in approval_constants.RESPONSIBLE_APPROVAL_VALIDATION_TYPES:
            return bool(
                self.responsible_approval_line_ids.filtered(lambda ln: ln.state == "pending")
            )
        if self.validation_type == "multi_step_6":
            return self.state == "confirm"
        return self.state == "confirm"

    def _approval_pending_since_base(self):
        self.ensure_one()
        if self.approval_escalated:
            return self.approval_escalated_at
        if self.validation_type in approval_constants.RESPONSIBLE_APPROVAL_VALIDATION_TYPES:
            wave = self._responsible_pending_current_wave()
            if wave:
                times = [ln.pending_since for ln in wave if ln.pending_since]
                if times:
                    return min(times)
                for ln in wave:
                    if not ln.pending_since:
                        ln.write({"pending_since": fields.Datetime.now()})
                return fields.Datetime.now()
        return self.create_date

    def _approval_past_due_without_action(self):
        self.ensure_one()
        if not self._approval_applies_to_leave():
            return False
        if self.approval_escalated:
            return False
        base_time = self._approval_pending_since_base()
        if not base_time:
            return False
        threshold = fields.Datetime.now() - timedelta(hours=self._approval_escalation_after_hours())
        return base_time <= threshold

    def _approval_past_due_at_escalation_level(self):
        self.ensure_one()
        if not self.approval_escalated or not self.approval_escalation_user_id:
            return False
        if self._approval_escalation_owner_acted():
            return False
        base_time = self.approval_escalated_at or self.create_date
        if not base_time:
            return False
        threshold = fields.Datetime.now() - timedelta(
            hours=self._approval_second_escalation_hours()
        )
        return base_time <= threshold

    # --- Escalation actions ---

    def _apply_approval_timeout_cancel_at_max_level(self):
        self.ensure_one()
        if not self._approval_should_auto_cancel_at_max_level():
            return
        if self.state not in ("confirm", "validate1"):
            return
        if not self.approval_escalated or not self._approval_is_max_escalation_reached():
            return
        if self._approval_escalation_owner_acted():
            return
        base_time = self.approval_escalated_at or self.create_date
        if not base_time:
            return
        cancel_after = self._approval_cancel_after_max_hours()
        total_hours = self._approval_escalation_after_hours() + cancel_after
        if base_time > fields.Datetime.now() - timedelta(hours=total_hours):
            return
        self.with_context(**{_SKIP_OUTCOME_BOT_NOTIFY_CTX: True}).sudo().write({"state": "cancel"})
        self.message_post(
            body=_(
                "Approval stayed unresolved after escalation timeout "
                "and max-level timeout (max title: %(title)s, cancel timeout: %(hours)s h). "
                "This leave request was canceled automatically; requester must create a new request."
            )
            % {
                "title": self._approval_max_escalation_job_title(),
                "hours": cancel_after,
            },
            subtype_xmlid="mail.mt_note",
        )

    def _apply_approval_timeout_escalation(self):
        self.ensure_one()
        if self.approval_escalated:
            return
        if not self._approval_past_due_without_action():
            return
        if self._approval_escalation_is_direct():
            escalation_user = self._get_approval_escalation_cap_user_for_max_title()
        else:
            requester_user = self.employee_id.user_id
            escalation_user = self._get_next_approval_manager_user_from_user(requester_user)
        first_hours = self._approval_escalation_after_hours()
        if not escalation_user:
            self.message_post(
                body=_(
                    "Approval timeout reached (%(hours)s h), but no manager user was found in org chart."
                )
                % {"hours": first_hours},
                subtype_xmlid="mail.mt_note",
            )
            return
        employee_fn = getattr(super(), "_handover_employee_for_assigner_user", None)
        owner_emp = employee_fn(escalation_user) if employee_fn else escalation_user.sudo().employee_id
        owner_title = owner_emp.job_title if owner_emp and owner_emp.job_title else _("cấp tiếp theo")
        self.sudo().write(
            {
                "approval_escalated": True,
                "approval_escalated_at": fields.Datetime.now(),
                "approval_escalation_level": 1,
                "approval_escalation_user_id": escalation_user.id,
            }
        )
        self.message_post(
            body=_(
                "Approval timeout reached (%(hours)s h). Escalated to %(user)s (%(title)s) to approve."
            )
            % {
                "hours": first_hours,
                "user": escalation_user.display_name,
                "title": owner_title,
            },
            subtype_xmlid="mail.mt_note",
        )
        self._notify_approval_timeout_escalation(escalation_user, hours=first_hours)
        self._refresh_responsible_actionable_users()

    def _apply_approval_timeout_escalation_to_next_level(self):
        self.ensure_one()
        if not self.approval_escalated:
            return
        if self._approval_escalation_is_direct():
            return
        if self._approval_is_max_escalation_reached():
            return
        if self._approval_escalation_owner_acted():
            return
        if not self._approval_past_due_at_escalation_level():
            return
        second_hours = self._approval_second_escalation_hours()
        manager_user = self._get_next_approval_manager_user_from_user(self.approval_escalation_user_id)
        if not manager_user or manager_user == self.approval_escalation_user_id:
            self.message_post(
                body=_(
                    "Approval escalation remained unresolved after %(hours)s hours, but no next manager user was found above %(owner)s."
                )
                % {
                    "hours": second_hours,
                    "owner": self.approval_escalation_user_id.display_name or _("trưởng bộ phận"),
                },
                subtype_xmlid="mail.mt_note",
            )
            return
        employee_fn = getattr(super(), "_handover_employee_for_assigner_user", None)
        manager_emp = employee_fn(manager_user) if employee_fn else manager_user.sudo().employee_id
        manager_title = manager_emp.job_title if manager_emp and manager_emp.job_title else _("cấp tiếp theo")
        self.sudo().write(
            {
                "approval_escalated": True,
                "approval_escalated_at": fields.Datetime.now(),
                "approval_escalation_level": (self.approval_escalation_level or 1) + 1,
                "approval_escalation_user_id": manager_user.id,
            }
        )
        self.message_post(
            body=_(
                "Approval still had no action after %(hours)s hours at current level. "
                "Escalated to %(user)s (%(manager_title)s)."
            )
            % {
                "hours": second_hours,
                "user": manager_user.display_name,
                "manager_title": manager_title,
            },
            subtype_xmlid="mail.mt_note",
        )
        self._notify_approval_timeout_escalation(manager_user, hours=second_hours)
        self._refresh_responsible_actionable_users()

    def _notify_approval_timeout_escalation(self, escalation_user, hours=None):
        self.ensure_one()
        if not escalation_user or not escalation_user.partner_id:
            return
        signature = "%s:%s:%s" % (
            self.id,
            escalation_user.id,
            self.approval_escalation_level or 0,
        )
        if self.approval_last_bot_escalation_signature == signature:
            return
        hours = hours if hours is not None else self._approval_escalation_after_hours()
        body = _(
            "Approval for %(leave)s has no action after %(hours)s hours. "
            "You are now assigned to approve or refuse this request."
        ) % {
            "leave": self.display_name,
            "hours": hours,
        }
        self.message_post(
            body=body,
            message_type="notification",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[escalation_user.partner_id.id],
        )
        requester_name = self.employee_id.name or self.employee_id.display_name or self.display_name
        period_fn = getattr(self, "_get_handover_bot_period_text", None)
        date_text = period_fn() if period_fn else self.display_name
        button_fn = getattr(self, "_notify_discuss_approval_pending_list_button_markup", None)
        if button_fn:
            button_html = button_fn(_("Duyệt đơn"))
        else:
            button_html = Markup("")
        bot_body = (
            Markup(
                _(
                    "Đơn nghỉ phép ngày <b>{date}</b> của nhân viên <b>{requester}</b> chưa được duyệt "
                    "sau thời gian chờ. Bạn được chỉ định duyệt hoặc từ chối đơn này.<br/><br/>"
                )
            ).format(date=date_text, requester=requester_name)
            + button_html
        )
        try:
            self._post_odoobot_bot_discuss_message(
                "business_discuss_bots.user_bot_approval",
                escalation_user,
                bot_body,
            )
            self.sudo().write({"approval_last_bot_escalation_signature": signature})
        except Exception:
            _logger.exception(
                "time_off_responsible_approval: failed approval escalation bot leave_id=%s user_id=%s",
                self.id,
                escalation_user.id,
            )

    def _clear_approval_escalation_state(self):
        self.sudo().write(
            {
                "approval_escalated": False,
                "approval_escalated_at": False,
                "approval_escalation_level": 0,
                "approval_escalation_user_id": False,
            }
        )

    def _action_approval_escalation_owner_approve(self):
        self.ensure_one()
        now = fields.Datetime.now()
        if self._is_responsible_approval_validation():
            wave = self._responsible_pending_current_wave()
            if wave:
                wave.sudo().write({"state": "skipped", "action_date": now})
        self.message_post(
            body=_("%(user)s approved after approval escalation timeout.")
            % {"user": self.env.user.display_name},
            subtype_xmlid="mail.mt_note",
        )
        self._clear_approval_escalation_state()
        if self._is_responsible_approval_validation():
            pending = self.responsible_approval_line_ids.filtered(lambda ln: ln.state == "pending")
            if pending and self._responsible_approval_mode() == "sequential":
                next_wave = self._responsible_pending_current_wave()
                if next_wave:
                    next_wave.sudo().write({"pending_since": now})
                    self._refresh_responsible_actionable_users()
                    self._notify_responsible_current_turn()
                    self.sudo().activity_update()
                    return True
            if not pending:
                return self.sudo()._action_validate(check_state=False)
            self.sudo().activity_update()
            return True
        return self.sudo()._action_validate(check_state=False)

    def _action_approval_escalation_owner_refuse(self, reason):
        self.ensure_one()
        now = fields.Datetime.now()
        if self._is_responsible_approval_validation():
            wave = self._responsible_pending_current_wave()
            if wave:
                wave.sudo().write({"state": "skipped", "action_date": now})
        self._clear_approval_escalation_state()
        return self.sudo().action_refuse(reason=reason)

    @api.model
    def cron_escalate_approval_org_timeouts(self):
        domain = [("state", "in", ("confirm", "validate1"))]
        leaves = self.sudo().search(domain)
        leaves._ensure_responsible_approval_lines()
        for leave in leaves:
            try:
                if not leave.approval_escalated:
                    leave._apply_approval_timeout_escalation()
                else:
                    leave._apply_approval_timeout_escalation_to_next_level()
                leave._apply_approval_timeout_cancel_at_max_level()
            except Exception:
                _logger.exception(
                    "time_off_responsible_approval: approval org escalation failed leave_id=%s",
                    leave.id,
                )

    @api.depends(
        "validation_type",
        "state",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
        "responsible_approval_line_ids.sequence",
        "responsible_approval_line_ids.user_id",
        "employee_id",
        "department_id",
        "holiday_status_id",
        "approval_escalated",
        "approval_escalation_user_id",
    )
    def _compute_can_responsible_approve(self):
        super()._compute_can_responsible_approve()
        for leave in self:
            if not (
                leave.approval_escalated
                and leave.approval_escalation_user_id
                and leave.state in ("confirm", "validate1")
            ):
                continue
            ready_fn = getattr(leave, "_handover_ready_for_approval", None)
            if ready_fn and not leave._handover_ready_for_approval():
                leave.can_responsible_approve = False
                continue
            leave.can_responsible_approve = leave.env.user == leave.approval_escalation_user_id

    @api.depends(
        "state",
        "validation_type",
        "responsible_approval_line_ids",
        "responsible_approval_line_ids.state",
        "responsible_approval_line_ids.sequence",
        "responsible_approval_line_ids.user_id",
        "approval_escalated",
        "approval_escalation_user_id",
    )
    def _compute_approval_actionable_user_ids(self):
        super()._compute_approval_actionable_user_ids()
        for leave in self:
            if (
                leave.approval_escalated
                and leave.approval_escalation_user_id
                and leave.state in ("confirm", "validate1")
            ):
                leave.approval_actionable_user_ids = leave.approval_escalation_user_id

    def action_responsible_approve(self):
        self.ensure_one()
        if (
            self.approval_escalated
            and self.approval_escalation_user_id == self.env.user
        ):
            return self._action_approval_escalation_owner_approve()
        return super().action_responsible_approve()

    def action_responsible_refuse(self, reason=False):
        self.ensure_one()
        if (
            self.approval_escalated
            and self.approval_escalation_user_id == self.env.user
        ):
            if not (reason or "").strip():
                return self.action_open_responsible_refuse_wizard()
            return self._action_approval_escalation_owner_refuse(reason)
        return super().action_responsible_refuse(reason=reason)
