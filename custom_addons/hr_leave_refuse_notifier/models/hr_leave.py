# -*- coding: utf-8 -*-
import logging

from markupsafe import Markup

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

    def _notify_refuse_ticket_notifier(self):
        refuser = self.env.user.display_name
        odoobot_partner = self.env.ref("base.partner_root", raise_if_not_found=False)
        if not odoobot_partner:
            return
        for leave in self:
            user_ids = set()
            for line in leave.sudo().responsible_approval_line_ids:
                if line.user_id and not line.user_id.share and line.user_id.active:
                    user_ids.add(line.user_id.id)
            if leave.employee_id.leave_manager_id and not leave.employee_id.leave_manager_id.share:
                user_ids.add(leave.employee_id.leave_manager_id.id)
            _logger.info(
                "hr_leave_refuse_notifier: leave_id=%s notifying %d user(s): %s",
                leave.id,
                len(user_ids),
                list(user_ids),
            )
            if not user_ids:
                continue
            # Use Odoo's canonical full leave label (employee, type, duration,
            # and date).  Explicitly clear compact/grouped display contexts so
            # refusal notifications never collapse this to only the leave type.
            leave_name = leave.with_context(
                short_name=False,
                hide_employee_name=False,
                group_by=[],
            ).display_name or leave.holiday_status_id.display_name
            reason = (leave.last_refusal_reason or "").strip()
            if reason:
                body = Markup(
                    "%s đã bị từ chối bởi %s với lý do: <b>%s</b>"
                ) % (leave_name, refuser, reason)
            else:
                body = _(
                    "%(leave_name)s đã bị từ chối bởi %(refuser)s.",
                    leave_name=leave_name,
                    refuser=refuser,
                )
            for uid in user_ids:
                try:
                    user = self.env["res.users"].sudo().browse(uid)
                    if not user.exists() or user.share or not user.partner_id:
                        continue
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
                        "hr_leave_refuse_notifier: DM failed leave_id=%s user_id=%s",
                        leave.id,
                        uid,
                    )
