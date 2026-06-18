# -*- coding: utf-8 -*-
"""Gom thông báo OdooBot + duyệt/từ chối một lần cho đơn tách P1/P2/O (split_group_id)."""

import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.time_off_responsible_approval import constants as approval_constants

_logger = logging.getLogger(__name__)

_SKIP_SPLIT_GROUP_APPROVE_CASCADE_CTX = "skip_split_group_approve_cascade"
_SKIP_SPLIT_GROUP_REFUSE_CASCADE_CTX = "skip_split_group_refuse_cascade"
_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX = approval_constants.SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX
_SKIP_SPLIT_GROUP_AFTER_CREATE_NOTIFY_CTX = "skip_split_group_after_create_notify"
_SPLIT_GROUP_NOTIFIED_CR_KEY = "hr_leave.split_group_approval_notified"
_RESPONSIBLE_SUBMIT_NOTIFIED_CR_KEY = "hr_leave.responsible_submit_notified"
_SPLIT_GROUP_OUTCOME_NOTIFIED_CR_KEY = "hr_leave.split_group_outcome_notified"


class HrLeaveSplitGroup(models.Model):
    _inherit = "hr.leave"

    # ------------------------------------------------------------------
    # Split group helpers
    # ------------------------------------------------------------------

    def _get_split_group_leaves_all(self):
        """All hr.leave records in the same split_group_id (any state)."""
        self.ensure_one()
        if not self.split_group_id:
            return self
        return self.search(
            [("split_group_id", "=", self.split_group_id)],
            order="id",
        )

    def _get_split_group_leaves(self):
        """Pending approval segments in the same split group."""
        self.ensure_one()
        if not self.split_group_id:
            return self
        return self.search(
            [
                ("split_group_id", "=", self.split_group_id),
                ("state", "in", ("confirm", "validate1")),
            ],
            order="id",
        )

    def _get_split_group_primary_leave(self):
        self.ensure_one()
        return self._get_split_group_leaves_all()[:1]

    def _is_split_group_primary_leave(self):
        self.ensure_one()
        if not self.split_group_id:
            return True
        return self == self._get_split_group_primary_leave()

    def _split_group_is_multi_segment(self):
        self.ensure_one()
        if not self.split_group_id:
            return False
        return len(self._get_split_group_leaves_all()) > 1

    def _split_group_clear_orphan_if_single(self):
        """Drop stale split_group_id when only one DB row remains (blocks OdooBot if kept)."""
        orphans = self.filtered(
            lambda l: l.split_group_id and not l._split_group_is_multi_segment()
        )
        if orphans:
            orphans.sudo().write({"split_group_id": False})

    def _split_group_dedupe_for_notify(self):
        """When notifying approvers, only handle the primary record per split group."""
        result = self.env["hr.leave"]
        seen_groups = set()
        for leave in self:
            if leave._split_group_is_multi_segment():
                gid = leave.split_group_id
                if gid in seen_groups:
                    continue
                seen_groups.add(gid)
                result |= leave._get_split_group_primary_leave()
            else:
                result |= leave
        return result

    def _format_approval_bot_period(self, date_from, date_to):
        date_from_text = self._format_approval_bot_date(date_from)
        if date_to and date_from and date_to != date_from:
            return _("%(from)s đến ngày %(to)s") % {
                "from": date_from_text,
                "to": self._format_approval_bot_date(date_to),
            }
        return date_from_text or "—"

    @api.model
    def _split_group_outcome_notified_cache(self):
        cache = self.env.cr.cache
        if _SPLIT_GROUP_OUTCOME_NOTIFIED_CR_KEY not in cache:
            cache[_SPLIT_GROUP_OUTCOME_NOTIFIED_CR_KEY] = set()
        return cache[_SPLIT_GROUP_OUTCOME_NOTIFIED_CR_KEY]

    def _outcome_bot_period_text(self, group_leaves=None):
        """Single date or 'dd/mm/yyyy đến ngày dd/mm/yyyy' for split groups."""
        leaves = group_leaves or self
        if len(leaves) == 1:
            leave = leaves[:1]
            date_from = leave.request_date_from or (
                leave.date_from and leave.date_from.date()
            )
            date_to = leave.request_date_to or (
                leave.date_to and leave.date_to.date()
            )
            return leave._format_approval_bot_period(date_from, date_to)

        dates_from = []
        dates_to = []
        for leave in leaves:
            date_from = leave.request_date_from or (
                leave.date_from and leave.date_from.date()
            )
            date_to = leave.request_date_to or (
                leave.date_to and leave.date_to.date()
            ) or date_from
            if date_from:
                dates_from.append(date_from)
            if date_to:
                dates_to.append(date_to)
        if not dates_from:
            return "—"
        primary = leaves.sorted("id")[:1]
        return primary._format_approval_bot_period(min(dates_from), max(dates_to))

    def _expand_split_group_refuse_targets(self):
        """When refusing one split segment, include all pending segments in the group."""
        expanded = self.env["hr.leave"]
        seen_groups = set()
        for leave in self:
            if leave.split_group_id and leave._split_group_is_multi_segment():
                gid = leave.split_group_id
                if gid in seen_groups:
                    continue
                seen_groups.add(gid)
                expanded |= leave._get_split_group_leaves()
            else:
                expanded |= leave
        return expanded

    def _get_approval_bot_split_group_notification_details(self, group_leaves):
        """Merged header + per-segment lines for one OdooBot message."""
        primary = group_leaves.sorted("id")[:1]
        primary.ensure_one()
        employee = primary.employee_id
        requester_name = employee.name or employee.display_name or primary.display_name
        id_hrm = (getattr(employee, "id_hrm", None) or "").strip() or "—"
        department = (employee.department_id.name or "").strip() or "—"
        reason = primary._timeoff_internal_reason_text() or "—"

        segment_lines = []
        total_days = 0.0
        for leave in group_leaves.sorted(key=lambda l: (l.request_date_from or l.id, l.id)):
            date_from = leave.request_date_from or (
                leave.date_from and leave.date_from.date()
            )
            date_to = leave.request_date_to or (leave.date_to and leave.date_to.date())
            period = leave._format_approval_bot_period(date_from, date_to)
            lt_name = (leave.holiday_status_id.name or "").strip() or "—"
            days = leave.number_of_days or 0.0
            total_days += days
            segment_lines.append(
                _("• %(type)s: %(period)s (%(days)s ngày)")
                % {
                    "type": lt_name,
                    "period": period,
                    "days": ("%g" % days) if days else "0",
                }
            )

        date_from_all = primary.request_date_from or (
            primary.date_from and primary.date_from.date()
        )
        date_to_all = max(
            (
                l.request_date_to
                or (l.date_to and l.date_to.date())
                or date_from_all
                for l in group_leaves
            ),
            default=date_from_all,
        )
        overall_period = primary._format_approval_bot_period(date_from_all, date_to_all)

        return {
            "requester": requester_name,
            "id_hrm": id_hrm,
            "department": department,
            "period": overall_period,
            "total_days": ("%g" % total_days) if total_days else "—",
            "reason": reason,
            "segment_lines": "\n".join(segment_lines),
            "segment_count": len(group_leaves),
            "primary": primary,
        }

    def _notify_approval_bot_split_group_action_buttons_markup(self, primary_leave):
        """Purple pills: approve all / refuse all (Discuss JS handles RPC)."""
        primary_leave.ensure_one()
        style = (
            "display:inline-block;padding:8px 18px;margin:4px 4px 4px 0;"
            "cursor:pointer;touch-action:manipulation;"
            "-webkit-tap-highlight-color:rgba(255,255,255,0.2);"
            "color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600;"
            "font-size:14px;line-height:1.2;"
        )
        approve_style = style + "background-color:#714B67;"
        refuse_style = style + "background-color:#6c757d;"
        pid = primary_leave.id
        split_group_id = primary_leave.split_group_id or ""
        return Markup(
            '<a class="o_timeoff_leave_pill o_timeoff_split_approve_all" href="#" '
            'data-oe-model="hr.leave" data-oe-id="{pid}" data-oe-type="approval_group" '
            'data-oe-split-group="{split_group_id}" data-oe-action="approve_all" '
            'style="{approve_style}">{approve_label}</a>'
            '<a class="o_timeoff_leave_pill o_timeoff_split_refuse_all" href="#" '
            'data-oe-model="hr.leave" data-oe-id="{pid}" data-oe-type="approval_group" '
            'data-oe-split-group="{split_group_id}" data-oe-action="refuse_all" '
            'style="{refuse_style}">{refuse_label}</a>'
        ).format(
            pid=pid,
            split_group_id=escape(split_group_id),
            approve_style=approve_style,
            refuse_style=refuse_style,
            approve_label=escape(_("Phê duyệt tất cả")),
            refuse_label=escape(_("Từ chối tất cả")),
        )

    # ------------------------------------------------------------------
    # Notifications (dedupe + grouped OdooBot body)
    # ------------------------------------------------------------------

    def _notify_responsible_approvers_submission(self):
        # Đơn tách nhiều phần: chỉ dùng 1 tin OdooBot (current_turn), không post thêm chatter.
        if any(leave._split_group_is_multi_segment() for leave in self):
            return
        if self.env.context.get(_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX):
            return super()._notify_responsible_approvers_submission()
        deduped = self._split_group_dedupe_for_notify()
        if set(deduped.ids) == set(self.ids):
            return super()._notify_responsible_approvers_submission()
        return deduped.with_context(
            **{_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX: True}
        )._notify_responsible_approvers_submission()

    def _notify_responsible_current_turn(self, user=None):
        if self.env.context.get(_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX):
            return super()._notify_responsible_current_turn(user=user)

        split_group_leaves = self.filtered("split_group_id")
        non_split = self - split_group_leaves
        if split_group_leaves:
            seen_groups = set()
            for leave in split_group_leaves:
                gid = leave.split_group_id
                if gid in seen_groups:
                    continue
                seen_groups.add(gid)
                primary = leave._get_split_group_primary_leave()
                if not primary._split_group_is_multi_segment():
                    continue
                if self._split_group_approval_notify_is_done(gid) and not user:
                    continue
                primary._notify_responsible_current_turn_split_group(user=user)
        if non_split:
            return super(
                HrLeaveSplitGroup,
                non_split.with_context(**{_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX: True}),
            )._notify_responsible_current_turn(user=user)

    def _notify_responsible_current_turn_split_group(self, user=None):
        """One grouped OdooBot message per approver — no extra chatter notifications."""
        self.ensure_one()
        if self.validation_type != "employee_hr_responsibles":
            return
        if not self._handover_ready_for_approval():
            return

        lines = self.env["hr.leave.responsible.approval"]
        if user:
            lines = self.responsible_approval_line_ids.filtered(
                lambda l: l.state == "pending" and l.user_id == user
            )
        if not lines:
            lines = self._responsible_pending_current_wave()
        if not lines:
            return

        # Also notify sale-admin users from the next pending step in parallel (FYI — approval order unchanged).
        stop_positions = self._get_org_chart_stop_positions()
        current_seq = lines[0].sequence if lines else None
        notify_lines = lines
        if current_seq is not None and not self._get_special_configured_approval_users():
            all_pending = self.responsible_approval_line_ids.filtered(
                lambda l: l.state == "pending" and l.sequence > current_seq
            ).sorted(lambda l: (l.sequence, l.id))
            for nxt in all_pending:
                job_pos = (nxt.user_id.sudo().employee_id.job_id.name or "").strip().casefold()
                if job_pos in stop_positions:
                    notify_lines = lines | nxt
                else:
                    break

        notified_users = set()
        for line in notify_lines:
            approver = line.user_id
            if not approver or not approver.partner_id or approver.id in notified_users:
                continue
            notified_users.add(approver.id)
            self._notify_responsible_current_turn_via_approval_bot(approver)
        self._notify_special_readonly_notifiers()

    def _notify_responsible_current_turn_via_approval_bot(self, approver_user):
        self.ensure_one()
        self._split_group_clear_orphan_if_single()
        if self.split_group_id and self._split_group_is_multi_segment():
            if not self._is_split_group_primary_leave():
                return
            group = self._get_split_group_leaves_all()
            return self._notify_responsible_current_turn_via_approval_bot_group(
                approver_user, group
            )
        return super()._notify_responsible_current_turn_via_approval_bot(approver_user)

    def _split_group_submission_context_key(self, split_group_id):
        return "split_group_submission_notified_%s" % (split_group_id or "")

    @api.model
    def _split_group_approval_notified_cache(self):
        cache = self.env.cr.cache
        if _SPLIT_GROUP_NOTIFIED_CR_KEY not in cache:
            cache[_SPLIT_GROUP_NOTIFIED_CR_KEY] = set()
        return cache[_SPLIT_GROUP_NOTIFIED_CR_KEY]

    @api.model
    def _responsible_submit_notified_cache(self):
        cache = self.env.cr.cache
        if _RESPONSIBLE_SUBMIT_NOTIFIED_CR_KEY not in cache:
            cache[_RESPONSIBLE_SUBMIT_NOTIFIED_CR_KEY] = set()
        return cache[_RESPONSIBLE_SUBMIT_NOTIFIED_CR_KEY]

    def _split_group_approval_notify_is_done(self, split_group_id):
        return bool(split_group_id) and split_group_id in self._split_group_approval_notified_cache()

    def _split_group_approval_notify_mark_done(self, split_group_id):
        if split_group_id:
            self._split_group_approval_notified_cache().add(split_group_id)

    def _split_group_bot_message_already_sent(self, chat, split_group_id):
        if not split_group_id or not chat:
            return False
        marker = 'data-oe-split-group="%s"' % split_group_id
        cutoff = fields.Datetime.now() - timedelta(minutes=30)
        return bool(
            self.env["mail.message"].sudo().search_count(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", chat.id),
                    ("body", "ilike", marker),
                    ("create_date", ">=", cutoff),
                ],
                limit=1,
            )
        )

    def _split_group_notify_submission_for_records(self):
        """Một lần notify / split_group_id; đơn đơn lẻ giữ hành vi cũ."""
        handled_groups = set()
        submit_cache = self._responsible_submit_notified_cache()
        for leave in self:
            if leave.validation_type != "employee_hr_responsibles" or leave.state != "confirm":
                continue
            leave._split_group_clear_orphan_if_single()
            if leave._split_group_is_multi_segment():
                gid = leave.split_group_id
                if gid in handled_groups:
                    continue
                handled_groups.add(gid)
                leave._get_split_group_primary_leave()._notify_split_group_submission_once()
            else:
                notify_key = ("leave", leave.id)
                if notify_key in submit_cache:
                    continue
                submit_cache.add(notify_key)
                if leave.handover_employee_ids and not leave._handover_ready_for_approval():
                    continue
                else:
                    leave._notify_responsible_approvers_submission()
                    leave.with_context(
                        **{_SKIP_SPLIT_GROUP_NOTIFY_DEDUP_CTX: True}
                    )._notify_responsible_current_turn()

    def _notify_split_group_submission_once(self):
        """Một lần / nhóm: hoặc bàn giao trước, hoặc duyệt đơn (không gửi cả hai cùng lúc)."""
        self.ensure_one()
        if not self._split_group_is_multi_segment():
            return
        gid = self.split_group_id
        ctx_key = self._split_group_submission_context_key(gid)
        if self.env.context.get(ctx_key):
            return
        primary = self._get_split_group_primary_leave()
        primary = primary.with_context(**{ctx_key: True})
        if primary.validation_type != "employee_hr_responsibles" or primary.state != "confirm":
            return
        group = primary._get_split_group_leaves_all()
        group._ensure_responsible_approval_lines()
        group._responsible_backfill_pending_since_if_missing()

        if primary.handover_employee_ids and not primary._handover_ready_for_approval():
            return

        if self._split_group_approval_notify_is_done(gid):
            return
        self._split_group_approval_notify_mark_done(gid)
        primary._notify_responsible_current_turn_split_group()

    def _notify_split_group_approval_after_handover_if_needed(self):
        """Sau khi bàn giao xong — gửi duyệt đơn gom một lần (tránh trùng lúc nộp đơn)."""
        self.ensure_one()
        if not self._split_group_is_multi_segment():
            return
        if self.validation_type != "employee_hr_responsibles":
            return
        if self.state not in ("confirm", "validate1"):
            return
        if not self._handover_ready_for_approval():
            return
        primary = self._get_split_group_primary_leave()
        gid = primary.split_group_id
        if self._split_group_approval_notify_is_done(gid):
            return
        self._split_group_approval_notify_mark_done(gid)
        primary._notify_responsible_current_turn_split_group()

    def _notify_responsible_current_turn_via_approval_bot_group(self, approver_user, group_leaves):
        self.ensure_one()
        if not approver_user or approver_user.share or not approver_user.partner_id:
            return
        details = self._get_approval_bot_split_group_notification_details(group_leaves)
        primary = details["primary"]
        segment_lines = details["segment_lines"].split("\n") if details["segment_lines"] else []
        segments_html = Markup("<br/>").join(
            Markup(escape(line)) for line in segment_lines if line
        )
        intro = Markup(
            _(
                "<b>ĐƠN XIN NGHỈ PHÉP</b> ({count} phần)<br/>"
                "Nhân viên: <b>{requester}</b><br/>"
                "Mã nhân viên: <b>{id_hrm}</b><br/>"
                "Bộ phận: <b>{department}</b><br/>"
                "Thời gian nghỉ: <b>{period}</b><br/>"
                "Tổng số ngày nghỉ: <b>{total_days}</b><br/>"
                "Chi tiết:<br/>{segments}<br/>"
                "Lý do: <b>{reason}</b><br/><br/>"
            )
        ).format(
            count=details["segment_count"],
            requester=escape(str(details["requester"])),
            id_hrm=escape(str(details["id_hrm"])),
            department=escape(str(details["department"])),
            period=escape(str(details["period"])),
            total_days=escape(str(details["total_days"])),
            segments=segments_html,
            reason=escape(str(details["reason"])),
        )
        button_html = primary._notify_discuss_leave_open_button_markup(
            _("Xem thông tin chi tiết ngày nghỉ phép"),
            discuss_link_type="approval",
            split_group_id=primary.split_group_id or None,
        )
        status_html = primary._approval_bot_notify_status_html(
            "pending", "unseen", approver_user, primary.split_group_id or 0
        )
        body = intro + status_html + button_html
        try:
            bot_user = self.env.ref(
                "business_discuss_bots.user_bot_approval", raise_if_not_found=False
            )
            if not bot_user:
                bot_user = self.env.ref("base.user_root")
            chat = (
                self.env["discuss.channel"]
                .with_user(bot_user)
                .sudo()
                ._get_or_create_chat([approver_user.partner_id.id], pin=True)
            )
            if self._split_group_bot_message_already_sent(chat, primary.split_group_id):
                _logger.info(
                    "time_off_extra_approval: skip duplicate grouped bot split_group=%s approver=%s",
                    primary.split_group_id,
                    approver_user.login,
                )
                return
            self._split_group_approval_notify_mark_done(primary.split_group_id)
            message = chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            primary._register_discuss_approval_notify(
                message, approver_user, primary.split_group_id or 0
            )
            _logger.info(
                "time_off_extra_approval: sent grouped bot notify split_group=%s leave_id=%s approver=%s",
                primary.split_group_id,
                primary.id,
                approver_user.login,
            )
        except Exception:
            _logger.exception(
                "time_off_extra_approval: failed grouped bot notify split_group=%s leave_id=%s",
                primary.split_group_id,
                primary.id,
            )

    def _notify_split_group_after_companion_create(self):
        """One OdooBot ping after P1/P2/O (or monthly) split — only when already submitted."""
        if self.env.context.get(_SKIP_SPLIT_GROUP_AFTER_CREATE_NOTIFY_CTX):
            return
        self.with_context(
            **{_SKIP_SPLIT_GROUP_AFTER_CREATE_NOTIFY_CTX: True}
        )._split_group_notify_submission_for_records()

    # ------------------------------------------------------------------
    # Batch approve / refuse (Discuss + form cascade)
    # ------------------------------------------------------------------

    @api.model
    def _split_group_refuse_reason(self):
        return _("Từ chối toàn bộ đơn nghỉ liên kết")

    def action_discuss_split_group_approve_all(self):
        """RPC/Discuss: phê duyệt mọi phần trong cùng split_group_id."""
        self.ensure_one()
        primary = self._get_split_group_primary_leave()
        if not primary.can_responsible_approve:
            raise UserError(_("Bạn không có quyền phê duyệt đơn nghỉ phép này."))
        # action_responsible_approve cascades to siblings in the same split group.
        return primary.action_responsible_approve()

    @api.model
    def _resolve_discuss_split_group_leave(self, leave_id, split_group_id=False):
        """Resolve a current split segment from a potentially stale bot message."""
        leave = self.browse(int(leave_id or 0)).exists()
        if split_group_id and (not leave or leave.split_group_id != split_group_id):
            leave = self.search(
                [("split_group_id", "=", split_group_id)],
                order="id",
                limit=1,
            )
        return leave

    @api.model
    def action_discuss_split_group_approve_by_reference(
        self, leave_id, split_group_id=False
    ):
        """Resolve a surviving split segment when a bot message contains a stale leave ID."""
        leave = self._resolve_discuss_split_group_leave(leave_id, split_group_id)
        if not leave:
            raise UserError(
                _("Không tìm thấy phần đơn nghỉ còn hiệu lực để phê duyệt.")
            )
        return leave.action_discuss_split_group_approve_all()

    def action_discuss_split_group_refuse_all(self):
        """RPC/Discuss: từ chối cả nhóm (P1/P2 cascade refuse đã có sẵn)."""
        self.ensure_one()
        primary = self._get_split_group_primary_leave()
        if len(primary._get_split_group_leaves_all()) <= 1:
            return primary.action_responsible_refuse(reason=self._split_group_refuse_reason())
        return primary.action_responsible_refuse(reason=self._split_group_refuse_reason())

    @api.model
    def action_discuss_split_group_refuse_by_reference(
        self, leave_id, split_group_id=False
    ):
        """Resolve a surviving split segment when a bot message contains a stale leave ID."""
        leave = self._resolve_discuss_split_group_leave(leave_id, split_group_id)
        if not leave:
            raise UserError(
                _("Không tìm thấy phần đơn nghỉ còn hiệu lực để từ chối.")
            )
        return leave.action_discuss_split_group_refuse_all()

    def action_responsible_approve(self):
        group_id = self.split_group_id if len(self) == 1 else False
        group_leave_ids = (
            self.sudo()._get_split_group_leaves().ids
            if len(self) == 1 and group_id
            else self.ids
        )
        res = super().action_responsible_approve()
        if self.env.context.get(_SKIP_SPLIT_GROUP_APPROVE_CASCADE_CTX):
            return res
        surviving = self.sudo().browse(group_leave_ids).exists()
        for leave in surviving:
            if not leave._split_group_is_multi_segment():
                continue
            siblings = leave._get_split_group_leaves().filtered(
                lambda l: l.id != leave.id and l.can_responsible_approve
            )
            ctx = {_SKIP_SPLIT_GROUP_APPROVE_CASCADE_CTX: True}
            for sibling in siblings.sorted("id"):
                try:
                    sibling.sudo().with_context(**ctx).action_responsible_approve()
                except UserError:
                    _logger.warning(
                        "split_group: could not cascade approve leave_id=%s sibling=%s",
                        leave.id,
                        sibling.id,
                        exc_info=True,
                    )
        self.sudo().browse(group_leave_ids).exists()._refresh_responsible_actionable_users()
        return res

    def action_responsible_refuse(self, reason=False):
        if not (reason or "").strip():
            return super().action_responsible_refuse(reason=reason)
        if self.env.context.get(_SKIP_SPLIT_GROUP_REFUSE_CASCADE_CTX):
            return super().action_responsible_refuse(reason=reason)

        self.ensure_one()
        targets = self.sudo()._expand_split_group_refuse_targets()
        if len(targets) <= 1:
            return super().action_responsible_refuse(reason=reason)

        reason_text = (reason or "").strip()
        ctx = {
            _SKIP_SPLIT_GROUP_REFUSE_CASCADE_CTX: True,
            "skip_outcome_bot_notify": True,
        }
        for leave in targets.sorted("id"):
            leave.sudo().with_context(**ctx).action_responsible_refuse(reason=reason_text)

        primary = self._get_split_group_primary_leave()
        primary._notify_requester_approval_outcome_via_bot(
            "refuse",
            refusal_reason=reason_text,
            refuser_name=self.env.user.display_name,
        )
        return True
