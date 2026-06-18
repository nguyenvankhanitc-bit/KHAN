# -*- coding: utf-8 -*-

import logging

from markupsafe import Markup

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HrLeaveOdoobotNotifyMixin(models.Model):
    _inherit = "hr.leave"

    approval_last_odoobot_remind_at = fields.Datetime(
        string="Last OdooBot approval reminder",
        copy=False,
    )
    approval_last_odoobot_remind_slot = fields.Char(
        string="Last OdooBot approval reminder slot",
        copy=False,
        help="Technical: last fired scheduled reminder slot key (date|time).",
    )
    handover_last_odoobot_remind_at = fields.Datetime(
        string="Last OdooBot handover reminder",
        copy=False,
    )
    handover_last_odoobot_remind_slot = fields.Char(
        string="Last OdooBot handover reminder slot",
        copy=False,
    )

    def _leave_request_mien(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return False
        return employee.mien or (
            employee.ma_bo_phan_id.mien if employee.ma_bo_phan_id else False
        )

    def _odoobot_notify_rule_env(self):
        """Sudo env for reading notification rules (HR config, not end-user data)."""
        return self.env["hr.leave.odoobot.notify.rule"].sudo()

    def _odoobot_notify_rule_for_employee(self, employee, bot_type):
        self.ensure_one()
        if not employee:
            return self._odoobot_notify_rule_env().browse()
        Rule = self._odoobot_notify_rule_env()
        requester_mien = self._leave_request_mien()
        for mien in self._odoobot_rule_mien_candidates(employee, requester_mien):
            rule = Rule._find_rule(
                company=self.company_id,
                mien=mien,
                job_title=employee.job_title,
                bot_type=bot_type,
            )
            if rule:
                return rule
        return Rule.browse()

    def _odoobot_rule_mien_candidates(self, employee, requester_mien):
        """Prefer requester Miền; fall back to approver Miền when no rule is configured."""
        seen = set()
        candidates = []
        for mien in (
            requester_mien,
            employee.mien if employee else False,
            employee.ma_bo_phan_id.mien if employee and employee.ma_bo_phan_id else False,
        ):
            if mien and mien not in seen:
                seen.add(mien)
                candidates.append(mien)
        return candidates

    def _odoobot_notify_rule_for_user(self, user, bot_type):
        self.ensure_one()
        employee = user.sudo().employee_id if user else False
        return self._odoobot_notify_rule_for_employee(employee, bot_type)

    def _odoobot_scheduled_remind_due(self, rule, last_slot_field):
        self.ensure_one()
        rule = rule.sudo() if rule else rule
        if not rule or not rule.remind_time_ids:
            return False
        slot_key = rule._matching_remind_slot_key()
        if not slot_key:
            return False
        if getattr(self, last_slot_field) == slot_key:
            return False
        return slot_key

    def _odoobot_mark_scheduled_remind_sent(self, bot_type, slot_key):
        self.ensure_one()
        now = fields.Datetime.now()
        if bot_type == "approval":
            self.sudo().write(
                {
                    "approval_last_odoobot_remind_at": now,
                    "approval_last_odoobot_remind_slot": slot_key,
                }
            )
        elif bot_type == "handover":
            self.sudo().write(
                {
                    "handover_last_odoobot_remind_at": now,
                    "handover_last_odoobot_remind_slot": slot_key,
                }
            )

    def _odoobot_reset_approval_remind_tracking(self):
        self.sudo().write(
            {
                "approval_last_odoobot_remind_at": False,
                "approval_last_odoobot_remind_slot": False,
            }
        )

    def _odoobot_reset_handover_remind_tracking(self):
        self.sudo().write(
            {
                "handover_last_odoobot_remind_at": False,
                "handover_last_odoobot_remind_slot": False,
            }
        )

    def _odoobot_skip_hours_for_user(self, user, bot_type):
        self.ensure_one()
        rule = self._odoobot_notify_rule_for_user(user, bot_type).sudo()
        if not rule or rule.is_final_level:
            return 0.0
        return rule.skip_level_hours or 0.0

    def _odoobot_blocks_auto_skip_for_user(self, user, bot_type):
        self.ensure_one()
        rule = self._odoobot_notify_rule_for_user(user, bot_type).sudo()
        if not rule:
            return True
        return bool(rule.is_final_level)

    def _post_odoobot_bot_discuss_message(self, bot_user_xmlid, recipient_user, body):
        """Post a Discuss DM from a configured OdooBot user."""
        return bool(
            self._post_odoobot_bot_discuss_message_returning(
                bot_user_xmlid, recipient_user, body
            )
        )

    def _post_odoobot_bot_discuss_message_returning(
        self, bot_user_xmlid, recipient_user, body
    ):
        """Post a Discuss DM and return the created mail.message (or empty recordset)."""
        self.ensure_one()
        Message = self.env["mail.message"]
        if not recipient_user or recipient_user.share or not recipient_user.partner_id:
            return Message
        bot_user = self.env.ref(bot_user_xmlid, raise_if_not_found=False)
        if not bot_user:
            bot_user = self.env.ref("base.user_root")
        bot_partner_id = bot_user.partner_id.id if bot_user and bot_user.partner_id else False
        if not bot_partner_id:
            return Message
        try:
            chat = (
                self.env["discuss.channel"]
                .sudo()
                .with_user(recipient_user)
                ._get_or_create_chat([bot_partner_id], pin=True)
            )
            post_vals = {
                "body": body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
                "author_id": bot_partner_id,
            }
            return chat.with_user(bot_user).sudo().message_post(**post_vals)
        except Exception:
            _logger.exception(
                "time_off_extra_approval: OdooBot DM failed leave_id=%s recipient_user_id=%s bot=%s",
                self.id,
                recipient_user.id,
                bot_user_xmlid,
            )
            return Message
