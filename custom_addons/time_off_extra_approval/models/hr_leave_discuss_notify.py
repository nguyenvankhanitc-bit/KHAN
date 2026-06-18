# -*- coding: utf-8 -*-

import logging
import re

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

_STATUS_DIV_RE = re.compile(
    r'(<div class="o_timeoff_discuss_notify_status"[^>]*data-oe-notify-key="(?P<key>[^"]+)"[^>]*>)'
    r".*?"
    r"(</div>)",
    re.DOTALL | re.IGNORECASE,
)


class HrLeaveDiscussNotify(models.Model):
    _name = "hr.leave.discuss.notify"
    _description = "Discuss leave approval notification tracking"
    _rec_name = "leave_id"

    leave_id = fields.Many2one(
        "hr.leave",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
    )
    split_group_id = fields.Integer(default=0, index=True)
    message_id = fields.Many2one("mail.message", ondelete="set null")
    approval_status = fields.Selection(
        [
            ("pending", "Chưa duyệt"),
            ("approved", "Đã duyệt"),
        ],
        default="pending",
        required=True,
    )
    view_status = fields.Selection(
        [
            ("unseen", "Chưa xem"),
            ("seen", "Đã xem"),
        ],
        default="unseen",
        required=True,
    )
    viewed_at = fields.Datetime(copy=False)

    _leave_user_group_unique = models.Constraint(
        "unique(leave_id, user_id, split_group_id)",
        "Each approver can only have one tracked Discuss notification per leave group.",
    )

    def _sync_message_body(self):
        for tracker in self.filtered("message_id"):
            leave = tracker.leave_id
            notify_key = leave._discuss_notify_tracking_key(
                tracker.user_id, tracker.split_group_id or None
            )
            status_markup = leave._approval_bot_notify_status_markup(
                tracker.approval_status,
                tracker.view_status,
                notify_key,
            )
            tracker._patch_message_status(status_markup, notify_key)

    def _patch_message_status(self, new_status_markup, notify_key):
        self.ensure_one()
        message = self.message_id.sudo()
        if not message or not message.body:
            return
        body = str(message.body)
        replacement = str(new_status_markup)

        def _replacer(match):
            if match.group("key") != notify_key:
                return match.group(0)
            return replacement

        new_body, count = _STATUS_DIV_RE.subn(_replacer, body, count=1)
        if not count:
            return
        message.write({"body": html_sanitize(new_body, sanitize_tags=False)})


class HrLeaveDiscussNotifyMixin(models.Model):
    _inherit = "hr.leave"

    def _discuss_notify_tracking_key(self, user, split_group_id=None):
        self.ensure_one()
        gid = split_group_id
        if gid is None:
            gid = self.split_group_id or 0
        return "%s|%s|%s" % (self.id, user.id, gid or 0)

    def _approval_bot_notify_status_markup(self, approval_status, view_status, notify_key):
        approval_label = (
            _("Chưa duyệt") if approval_status == "pending" else _("Đã duyệt")
        )
        view_label = _("Chưa xem") if view_status == "unseen" else _("Đã xem")
        return Markup(
            '<div class="o_timeoff_discuss_notify_status" '
            'data-oe-notify-key="{key}">'
            "Trạng thái: <b>{approval}</b><br/>"
            "<b>{view}</b>"
            "</div><br/>"
        ).format(
            key=escape(notify_key),
            approval=escape(approval_label),
            view=escape(view_label),
        )

    def _approval_bot_notify_status_html(
        self,
        approval_status="pending",
        view_status="unseen",
        recipient_user=None,
        split_group_id=None,
    ):
        self.ensure_one()
        notify_key = None
        if recipient_user:
            notify_key = self._discuss_notify_tracking_key(recipient_user, split_group_id)
        return self._approval_bot_notify_status_markup(
            approval_status, view_status, notify_key or ""
        )

    def _register_discuss_approval_notify(self, message, recipient_user, split_group_id=None):
        self.ensure_one()
        if not message or not recipient_user:
            return
        gid = split_group_id if split_group_id is not None else (self.split_group_id or 0)
        Notify = self.env["hr.leave.discuss.notify"].sudo()
        existing = Notify.search(
            [
                ("leave_id", "=", self.id),
                ("user_id", "=", recipient_user.id),
                ("split_group_id", "=", gid),
            ],
            limit=1,
        )
        vals = {
            "message_id": message.id,
            "approval_status": "pending",
            "view_status": "unseen",
            "viewed_at": False,
        }
        if existing:
            existing.write(vals)
        else:
            Notify.create(
                {
                    **vals,
                    "leave_id": self.id,
                    "user_id": recipient_user.id,
                    "split_group_id": gid,
                }
            )

    def _post_discuss_approval_bot_message(
        self,
        recipient_user,
        intro_body,
        *,
        split_group_id=None,
        button_label=None,
        bot_user_xmlid="business_discuss_bots.user_bot_approval",
    ):
        """Post approval-bot DM with Trạng thái / Đã xem footer and register tracker."""
        self.ensure_one()
        primary = self
        if hasattr(self, "_get_split_group_primary_leave"):
            primary = self._get_split_group_primary_leave() or self
        gid = split_group_id if split_group_id is not None else (primary.split_group_id or 0)
        status_html = primary._approval_bot_notify_status_html(
            "pending", "unseen", recipient_user, gid
        )
        button_html = primary._notify_discuss_leave_open_button_markup(
            button_label or _("Xem thông tin chi tiết ngày nghỉ phép"),
            discuss_link_type="approval",
            split_group_id=gid or None,
        )
        body = intro_body + status_html + button_html
        message = primary._post_odoobot_bot_discuss_message_returning(
            bot_user_xmlid, recipient_user, body
        )
        if message:
            primary._register_discuss_approval_notify(message, recipient_user, gid)
        return message

    def _discuss_notify_find_trackers(self, user, split_group_id=0):
        self.ensure_one()
        Notify = self.env["hr.leave.discuss.notify"].sudo()
        gid = int(split_group_id or 0)
        domain = [("leave_id", "=", self.id), ("user_id", "=", user.id)]
        if gid:
            trackers = Notify.search(domain + [("split_group_id", "=", gid)])
            if trackers:
                return trackers
        return Notify.search(domain + [("split_group_id", "=", gid)])

    def _discuss_notify_update_status(
        self,
        user,
        *,
        split_group_id=0,
        view_status=None,
        approval_status=None,
    ):
        self.ensure_one()
        trackers = self._discuss_notify_find_trackers(user, split_group_id)
        if not trackers:
            return
        for tracker in trackers:
            vals = {}
            if view_status:
                vals["view_status"] = view_status
                if view_status == "seen":
                    vals["viewed_at"] = fields.Datetime.now()
            if approval_status:
                vals["approval_status"] = approval_status
            if vals:
                tracker.write(vals)
                tracker._sync_message_body()

    def _discuss_notify_mark_approved_for_user(self, user, split_group_id=None):
        self.ensure_one()
        gid = split_group_id if split_group_id is not None else (self.split_group_id or 0)
        self._discuss_notify_update_status(
            user,
            split_group_id=gid,
            view_status="seen",
            approval_status="approved",
        )

    @api.model
    def action_discuss_mark_leave_notification_viewed(self, leave_id, split_group_id=False):
        """Mark Discuss approval notification as viewed when approver opens the leave."""
        leave = self.browse(int(leave_id)).exists()
        if not leave:
            return False
        leave.check_access("read")
        gid = int(split_group_id or 0)
        leave._discuss_notify_update_status(
            self.env.user,
            split_group_id=gid,
            view_status="seen",
        )
        return True
