# -*- coding: utf-8 -*-
import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _notify_manager(self):
        result = super()._notify_manager()
        try:
            self._notify_refuse_ticket_notifier()
        except Exception:
            _logger.exception("hr_leave_refuse_notifier: failed to notify refuse ticket notifier")
        return result

    def _get_refuse_notifier_users(self):
        self.ensure_one()
        users = self.env["res.users"]
        if self.validation_type == "employee_hr_responsibles":
            users |= self.sudo().responsible_approval_line_ids.mapped("user_id")
        if self.validation_type == "multi_step_6":
            step = self.sudo()._get_current_multi_step()
            if step:
                users |= step._get_all_approver_users()
        users |= self.sudo().extra_approver_user_ids
        users |= self.sudo().holiday_status_id.sudo().responsible_ids
        if self.employee_id.leave_manager_id:
            users |= self.employee_id.leave_manager_id
        users = users.filtered(lambda u: u and not u.share and u.active)
        return users

    def _notify_refuse_ticket_notifier(self):
        refuser = self.env.user.display_name
        odoobot_partner = self.env.ref("base.partner_root", raise_if_not_found=False)
        if not odoobot_partner:
            _logger.warning("hr_leave_refuse_notifier: base.partner_root not found")
            return
        for leave in self:
            notifier_users = leave._get_refuse_notifier_users()
            if not notifier_users:
                _logger.info(
                    "hr_leave_refuse_notifier: no approvers to notify for leave_id=%s",
                    leave.id,
                )
                continue
            _logger.info(
                "hr_leave_refuse_notifier: leave_id=%s notifying %d approver(s): %s",
                leave.id,
                len(notifier_users),
                [u.login for u in notifier_users],
            )
            body = _(
                "%(leave_name)s has been refused by %(refuser)s.",
                leave_name=leave.display_name,
                refuser=refuser,
            )
            for user in notifier_users:
                try:
                    chat = (
                        self.env["discuss.channel"]
                        .sudo()
                        .with_user(user)
                        ._get_or_create_chat([odoobot_partner.id], pin=True)
                    )
                    chat.with_user(user).sudo().message_post(
                        body=body,
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        author_id=odoobot_partner.id,
                    )
                except Exception:
                    _logger.exception(
                        "hr_leave_refuse_notifier: OdooBot DM failed leave_id=%s user_id=%s",
                        leave.id,
                        user.id,
                    )
