# -*- coding: utf-8 -*-
import logging
import hashlib
import hmac
from datetime import date, datetime, time, timedelta
from numbers import Integral

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import sql
from odoo.tools.misc import format_date
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

_EMERGENCY_LEAVE_CTX = "emergency_leave_confirmed"
_SKIP_EMERGENCY_LEAVE_CHECK_CTX = "skip_emergency_leave_check"
_SKIP_PAST_LEAVE_LIMIT_CTX = "skip_past_leave_limit_check"
_SKIP_SUBMIT_BOT_NOTIFY_CTX = "skip_handover_submit_bot_notify"
_SKIP_OUTCOME_BOT_NOTIFY_CTX = "skip_outcome_bot_notify"
_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX = "skip_responsible_submit_notify"
# Job titles that require only 3 calendar days advance notice
_SHORT_LEAD_JOB_KEYS = frozenset({"trưởng nhóm", "nhóm trưởng", "cửa hàng trưởng"})
_SHORT_LEAD_DAYS = 3
_DEFAULT_LEAD_DAYS = 7
_MAX_BACKDATE_DAYS = 3
# Must match time_off_responsible_approval.constants.DIRECTOR_JOB_TITLE_KEY
_DIRECTOR_JOB_TITLE_KEY = "giám đốc"


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

    def _action_return_reload_leave_form(self):
        """call_button only forwards dict actions to the web client; booleans are dropped, so the form must reload explicitly."""
        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
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

    def _check_past_leave_limit_on_vals(self, vals, leave=None):
        """Block creating/moving leave requests more than 3 calendar days in the past."""
        if self.env.context.get(_SKIP_PAST_LEAVE_LIMIT_CTX):
            return
        start = self._past_leave_limit_violation_start(vals=vals, leave=leave)
        if start:
            raise ValidationError(self._past_leave_limit_error_message(start))

    def _past_leave_limit_error_message(self, start):
        min_start = fields.Date.context_today(self) - timedelta(days=_MAX_BACKDATE_DAYS)
        return _(
            "Cannot create or move a time off request more than %(days)s days in the past. "
            "The earliest allowed start date is %(min_date)s (selected: %(start_date)s).",
            days=_MAX_BACKDATE_DAYS,
            min_date=format_date(self.env, min_start),
            start_date=format_date(self.env, start),
        )

    def _past_leave_limit_violation_start(self, vals=None, leave=None):
        vals = vals or {}
        start = self._parse_date_val(vals.get("request_date_from"))
        if not start:
            start = self._parse_date_val(vals.get("date_from"))
        if not start and leave:
            leave = leave[:1]
            start = leave.request_date_from or self._parse_date_val(leave.date_from)
        if not start:
            return False
        min_start = fields.Date.context_today(self) - timedelta(days=_MAX_BACKDATE_DAYS)
        return start if start < min_start else False

    @api.constrains("request_date_from", "date_from")
    def _check_past_leave_limit_constraint(self):
        if self.env.context.get(_SKIP_PAST_LEAVE_LIMIT_CTX):
            return
        for leave in self:
            start = self._past_leave_limit_violation_start(leave=leave)
            if start:
                raise ValidationError(self._past_leave_limit_error_message(start))

    @api.onchange("request_date_from", "date_from")
    def _onchange_past_leave_limit(self):
        start = self._past_leave_limit_violation_start(leave=self)
        if start:
            return {
                "warning": {
                    "title": _("Backdated time off is too old"),
                    "message": self._past_leave_limit_error_message(start),
                }
            }

    @api.model
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
        if not start:
            start = self._parse_date_val(merged_vals.get("date_from"))
        if not start and leave:
            start = leave.request_date_from or (
                leave.date_from.date() if leave.date_from else False
            )
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

    def _leave_discuss_hmac_secret_key(self):
        icp = self.env["ir.config_parameter"].sudo()
        secret = icp.get_param("database.secret") or icp.get_param("database.uuid") or ""
        return secret.encode("utf-8")

    def _leave_discuss_link_token(self):
        self.ensure_one()
        key = self._leave_discuss_hmac_secret_key()
        if not key:
            _logger.warning(
                "time_off_extra_approval: database.secret/database.uuid missing — Discuss leave links disabled"
            )
            return ""
        msg = ("v1|hr.leave.discuss_open|%s" % (self.id,)).encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest()

    def _leave_discuss_link_verify_token(self, token):
        self.ensure_one()
        expected = self._leave_discuss_link_token()
        if not expected or not token or len(token) != len(expected):
            return False
        try:
            return hmac.compare_digest(expected, token)
        except Exception:  # noqa: BLE001
            return False

    def _leave_discuss_open_client_fragment(self):
        self.ensure_one()
        return "#id=%s&model=hr.leave&view_type=form" % self.id

    def _leave_discuss_open_http_path(self):
        """Signed HTTP route for old messages / bookmarks; Discuss pills use SPA path."""
        self.ensure_one()
        tok = self._leave_discuss_link_token()
        if not tok:
            return self._leave_discuss_open_spa_path()
        return "/time_off_extra_approval/discuss_leave/%s/%s" % (self.id, tok)

    def _leave_discuss_open_spa_path(self):
        """Canonical in-app URL (Odoo 19 path router). Used in Discuss bot pills."""
        self.ensure_one()
        return "/odoo/hr.leave/%s" % self.id

    def _m2o_id(self, val):
        if val in (False, None):
            return False
        if isinstance(val, models.Model):
            return val.id
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    def _merge_vals_for_emergency_check(self, vals, leave=None):
        """Merge write/create vals with existing leave for preview and enforcement."""
        merged = dict(vals or {})
        if leave:
            leave = leave[:1]
            for key in (
                "employee_id",
                "request_date_from",
                "request_date_to",
                "date_from",
                "date_to",
                "holiday_status_id",
            ):
                if key not in merged or merged[key] in (False, None):
                    merged[key] = leave[key]
        if not merged.get("employee_id"):
            default_emp = self.env.context.get("default_employee_id")
            if default_emp:
                merged["employee_id"] = default_emp
            elif self.env.user.employee_id:
                merged["employee_id"] = self.env.user.employee_id.id
        return merged

    def _notify_approval_bot_leave_form_open_button_markup(self):
        """OdooBot Duyệt đơn."""
        self.ensure_one()
        return self._notify_discuss_leave_open_button_markup(
            _("Time Off"),
            discuss_link_type="approval",
        )


    def _notify_discuss_leave_open_button_markup(self, button_label, *, discuss_link_type):
        """Purple pill for Discuss bots (handover + approval).

        Uses ``data-oe-*`` attributes (survive mail HTML sanitization; ``class`` does not).
        """
        self.ensure_one()
        path_esc = escape(self._leave_discuss_open_spa_path())
        return Markup(
            '<a class="o_timeoff_leave_pill" href="{href}" target="_self" '
            'data-oe-model="hr.leave" data-oe-id="{res_id}" data-oe-type="{link_type}" '
            'style="display:inline-block;padding:8px 18px;background-color:#714B67;cursor:pointer;'
            'touch-action:manipulation;-webkit-tap-highlight-color:rgba(255,255,255,0.2);'
            'color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600;'
            'font-size:14px;line-height:1.2;">{label}</a>'
        ).format(
            href=path_esc,
            res_id=self.id,
            link_type=escape(discuss_link_type),
            label=escape(button_label),
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
            if sql.column_exists(cr, "hr_leave", column_name):
                continue
            sql.create_column(cr, "hr_leave", column_name, column_type)
            if column_name == "emergency_leave_approver_notice":
                created_notice_column = True
        if created_notice_column:
            leaves = self.env["hr.leave"].sudo().search([])
            if leaves:
                leaves._compute_emergency_leave_approver_notice()

    def _required_lead_days_for_job_title(self, job_title):
        """Return minimum calendar days between today and leave start, or None if exempt."""
        if job_title == _DIRECTOR_JOB_TITLE_KEY:
            return None
        if job_title in _SHORT_LEAD_JOB_KEYS:
            return _SHORT_LEAD_DAYS
        return _DEFAULT_LEAD_DAYS

    def _vals_trigger_emergency_leave_check(self, vals):
        if not vals:
            return False
        return bool(
            {"employee_id", "request_date_from", "request_date_to", "holiday_status_id"}.intersection(vals)
        )

    def action_approve(self, check_state=True):
        self._ensure_handover_ready_for_approval()
        return super().action_approve(check_state=check_state)

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

    def action_refuse(self, reason=False):
        if not (reason or "").strip():
            return self.action_open_refuse_wizard()
        if not self.env.context.get("skip_split_group_refuse_cascade") and hasattr(
            self, "_expand_split_group_refuse_targets"
        ):
            self = self._expand_split_group_refuse_targets()
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
        if not self.env.context.get(_SKIP_OUTCOME_BOT_NOTIFY_CTX):
            for leave in self:
                leave._notify_requester_approval_outcome_via_bot(
                    "refuse",
                    refusal_reason=reason_text,
                    refuser_name=self.env.user.display_name,
                )
        return True

    @api.model
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

    @api.model
    def _needs_emergency_leave_confirmation(self, res_id=False, vals=None):
        """Cần cảnh báo nghỉ khẩn cấp trên UI (kể cả Giám đốc nếu báo trước ngắn)."""
        vals = vals or {}
        leave = self.env["hr.leave"]
        if res_id:
            leave = self.browse(res_id).exists()
        merged = self._merge_vals_for_emergency_check(
            vals, leave=leave if res_id and leave else None
        )
        info = self._emergency_leave_violation_info(
            merged, leave=leave if res_id and leave else None
        )
        if info.get("violation"):
            return True
        if not info.get("exempt"):
            return False
        employee_id = self._m2o_id(merged.get("employee_id"))
        if not employee_id and leave:
            employee_id = leave.employee_id.id
        employee = (
            self.env["hr.employee"].sudo().browse(employee_id)
            if employee_id
            else self.env["hr.employee"]
        )
        if not employee or self._required_lead_days_for_job_title(employee.job_title) is not None:
            return False
        start = self._parse_date_val(merged.get("request_date_from"))
        if not start:
            start = self._parse_date_val(merged.get("date_from"))
        if not start and leave:
            start = leave.request_date_from or (
                leave.date_from.date() if leave.date_from else False
            )
        if not start:
            return False
        today = fields.Date.context_today(self)
        return (start - today).days < _DEFAULT_LEAD_DAYS

    @api.model
    def check_leave_form_save_confirmations(self, res_id=False, vals=None):
        """Một hộp thoại trước khi lưu: nghỉ khẩn cấp, hết phép, hoặc cả hai."""
        vals = vals or {}
        leave = self.env["hr.leave"]
        if res_id:
            leave = self.browse(res_id).exists()
        past_start = self._past_leave_limit_violation_start(
            vals=vals, leave=leave if res_id and leave else None
        )
        if past_start:
            return {
                "blocked": True,
                "needs_confirmation": False,
                "set_emergency_confirmed": False,
                "set_con_lai_zero_confirmed": False,
                "title": _("Backdated time off is too old"),
                "message": self._past_leave_limit_error_message(past_start),
            }
        emergency_preview = self.check_emergency_leave_lead_time(res_id=res_id, vals=vals)
        con_lai_preview = self.check_con_lai_zero_confirmation(res_id=res_id, vals=vals)
        need_emergency = self._needs_emergency_leave_confirmation(
            res_id=res_id, vals=vals
        )
        need_con_lai = con_lai_preview.get("needs_confirmation")
        if need_emergency and need_con_lai:
            return {
                "needs_confirmation": True,
                "set_emergency_confirmed": True,
                "set_con_lai_zero_confirmed": True,
                "title": _("Xác nhận nghỉ khẩn cấp"),
                "message": _(
                    "Bạn đang xin nghỉ khẩn cấp, đồng thời số phép của bạn hiện đang là 0. "
                    "Bạn có muốn tiếp tục không?"
                ),
            }
        if need_emergency:
            if emergency_preview.get("needs_confirmation"):
                return {
                    **emergency_preview,
                    "set_emergency_confirmed": True,
                    "set_con_lai_zero_confirmed": False,
                }
            return {
                "needs_confirmation": True,
                "set_emergency_confirmed": True,
                "set_con_lai_zero_confirmed": False,
                "title": _("Xác nhận nghỉ khẩn cấp"),
                "message": _(
                    "Bạn đang gửi đơn nghỉ khẩn cấp (thời gian báo trước ngắn hơn quy định). "
                    "Bạn có chắc chắn muốn tiếp tục không?"
                ),
            }
        if need_con_lai:
            return {
                **con_lai_preview,
                "set_emergency_confirmed": False,
                "set_con_lai_zero_confirmed": True,
            }
        return {
            "needs_confirmation": False,
            "title": "",
            "message": "",
            "set_emergency_confirmed": False,
            "set_con_lai_zero_confirmed": False,
        }

    def write(self, vals):
        check_past_limit = {"request_date_from", "date_from"} & set(vals)
        if check_past_limit:
            for leave in self:
                self._check_past_leave_limit_on_vals(vals, leave=leave)
        if vals and self._vals_trigger_emergency_leave_check(vals):
            if len(self) > 1:
                raise UserError(
                    _(
                        "Please edit and save one time off request at a time when changing dates, "
                        "employee, or time off type (advance-notice check)."
                    )
                )
            self._apply_emergency_leave_on_vals(vals, leave=self)
        res = super().write(vals)
        if check_past_limit:
            self._check_past_leave_limit_constraint()
        return res

    def action_confirm(self):
        try:
            return super(
                HolidaysRequest,
                self.with_context(
                    **{
                        _SKIP_SUBMIT_BOT_NOTIFY_CTX: True,
                        _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX: True,
                    }
                ),
            ).action_confirm()
        except AttributeError:
            return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_past_leave_limit_on_vals(vals)
            self._apply_emergency_leave_on_vals(vals)
        records = super().create(vals_list)
        records._check_past_leave_limit_constraint()
        return records
