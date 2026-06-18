# -*- coding: utf-8 -*-
"""Tách đơn nghỉ theo quy tắc tháng: P1 (ngày 1) → P2 (ngày 2–3) → O (từ ngày 4)."""

import calendar
import logging
import uuid
from datetime import date, timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX = "skip_responsible_submit_notify"

_logger = logging.getLogger(__name__)

_SKIP_MONTHLY_MIEN_SPLIT_CTX = "skip_monthly_mien_split"
# Khi bật: bỏ qua việc tự cân bằng lại P1/P2/O cả tháng (tránh đệ quy khi
# chính cơ chế cân bằng đang ghi/ tạo bản ghi).
_SKIP_MONTHLY_MIEN_REBALANCE_CTX = "skip_monthly_mien_rebalance"


class HrLeaveMonthlySplit(models.Model):
    _inherit = "hr.leave"

    monthly_leave_split_preview = fields.Text(
        string="Phân tích ngày nghỉ trong đơn",
        readonly=True,
    )

    @api.model
    def _format_split_preview_date(self, value):
        d = self._coerce_to_date(value)
        return d.strftime("%d/%m/%Y") if d else ""

    def _format_split_preview_date_range(self, date_from, date_to):
        start = self._format_split_preview_date(date_from)
        end = self._format_split_preview_date(date_to)
        if not start:
            return ""
        if start == end:
            return start
        return f"{start} -> {end}"

    def _build_monthly_leave_split_preview_text(self):
        self.ensure_one()
        if (
            not self.employee_id
            or not self.request_date_from
            or not self.request_date_to
            or not self._monthly_p1p2_mien_applies(self.employee_id)
        ):
            return False
        if self.request_date_from > self.request_date_to:
            return False
        total_days = (self.request_date_to - self.request_date_from).days + 1
        if total_days <= 1:
            return False
        exclude = [self.id] if self.id else []
        plan = self._monthly_mien_split_plan(
            self.employee_id,
            self.request_date_from,
            self.request_date_to,
            exclude,
        )
        if len(plan) <= 1:
            return False
        lines = []
        for kind, seg_from, seg_to in plan:
            leave_type = self._monthly_mien_leave_type_for_kind(kind)
            label = leave_type.name if leave_type else kind.upper()
            dates = self._format_split_preview_date_range(seg_from, seg_to)
            num_days = (seg_to - seg_from).days + 1
            lines.append(f"{label} ({dates}) — {num_days} ngày")
        return "\n".join(lines)

    def _refresh_monthly_leave_split_preview(self):
        try:
            text = self._build_monthly_leave_split_preview_text()
            self.monthly_leave_split_preview = text or False
        except Exception:
            _logger.exception("monthly_leave_split_preview failed")
            self.monthly_leave_split_preview = False

    @api.model
    def _month_end_date(self, day):
        """Ngày cuối cùng của tháng chứa ``day``."""
        day = self._coerce_to_date(day)
        last = calendar.monthrange(day.year, day.month)[1]
        return date(day.year, day.month, last)

    @api.model
    def _monthly_mien_split_plan_for_month(
        self, days_before, date_from, date_to, paid_budget=None, monthly_cap=None
    ):
        """
        P1/P2/O trong một tháng lịch (date_from và date_to cùng tháng).
        days_before: số ngày nghỉ đã có trong tháng đó (không tính đơn hiện tại).
        paid_budget: ngày phép có lương còn lại của nhân viên (None = không giới hạn).
        monthly_cap: hạn mức phép có lương / tháng (None = dùng MAX_PAID_LEAVE_DAYS_PER_MONTH).
                     Trả về (segments, paid_used) — paid_used là tổng P1+P2 đã cấp.
        """
        from .hr_leave_mien_config import MAX_PAID_LEAVE_DAYS_PER_MONTH

        date_from = self._coerce_to_date(date_from)
        date_to = self._coerce_to_date(date_to)
        segments = []
        cursor = date_from
        remaining = (date_to - date_from).days + 1
        paid_used = 0
        effective_cap = (
            MAX_PAID_LEAVE_DAYS_PER_MONTH if monthly_cap is None else max(0, monthly_cap)
        )

        budget_unlimited = paid_budget is None
        budget_left = paid_budget if not budget_unlimited else None

        if (
            days_before == 0
            and remaining > 0
            and effective_cap > 0
            and (budget_unlimited or (budget_left or 0) > 0)
        ):
            segments.append(("p1", cursor, cursor))
            cursor += timedelta(days=1)
            remaining -= 1
            days_before += 1
            paid_used += 1
            if not budget_unlimited:
                budget_left -= 1

        p2_budget_month = max(0, effective_cap - days_before)
        if not budget_unlimited:
            p2_budget_month = min(p2_budget_month, max(0, budget_left or 0))
        p2_days = min(p2_budget_month, remaining)
        if p2_days > 0:
            p2_end = cursor + timedelta(days=p2_days - 1)
            segments.append(("p2", cursor, p2_end))
            cursor = p2_end + timedelta(days=1)
            remaining -= p2_days
            paid_used += p2_days

        if remaining > 0:
            segments.append(("o", cursor, date_to))

        return segments, paid_used

    @api.model
    def _monthly_mien_employee_monthly_cap(self, employee):
        """Hạn mức phép có lương / tháng của nhân viên (override > mặc định)."""
        from .hr_leave_mien_config import MAX_PAID_LEAVE_DAYS_PER_MONTH

        if employee and "monthly_paid_leave_cap" in employee._fields:
            override = employee.monthly_paid_leave_cap
            if override:
                return int(override)
        return MAX_PAID_LEAVE_DAYS_PER_MONTH

    @api.model
    def _monthly_mien_paid_budget_for_employee(
        self, employee, exclude_leave_ids=None, target_date=None
    ):
        """Ngân sách phép có lương còn lại của nhân viên (tong_so_phep − đã cam kết, không tính O).

        Trả về None khi không xác định được (không chặn theo Còn lại — chỉ áp dụng quy tắc 3 ngày/tháng).
        """
        if not employee or "tong_so_phep" not in employee._fields:
            return None
        if not hasattr(self, "_con_lai_committed_days"):
            return None
        committed = self._con_lai_committed_days(
            employee, exclude_leave_ids=exclude_leave_ids
        )
        budget = (employee.tong_so_phep or 0.0) - committed
        if budget < 0:
            budget = 0
        return int(budget)

    @api.model
    def _monthly_mien_split_plan(
        self, employee, date_from, date_to, exclude_leave_ids=None
    ):
        """
        Trả về list (kind, date_from, date_to) — áp dụng P1/P2/O riêng từng tháng
        khi đơn nghỉ trải qua nhiều tháng. Hạn mức P1/P2 còn bị giới hạn bởi Còn lại
        của nhân viên: khi hết Còn lại, các ngày tiếp theo đều thành O.
        """
        date_from = self._coerce_to_date(date_from)
        date_to = self._coerce_to_date(date_to)
        if not employee or not date_from or not date_to:
            return []
        if date_to < date_from:
            date_from, date_to = date_to, date_from

        paid_budget = self._monthly_mien_paid_budget_for_employee(
            employee, exclude_leave_ids=exclude_leave_ids, target_date=date_from
        )
        monthly_cap = self._monthly_mien_employee_monthly_cap(employee)
        segments = []
        cursor = date_from
        while cursor <= date_to:
            month_end = min(date_to, self._month_end_date(cursor))
            days_before = self._count_active_leave_days_in_month_before(
                employee,
                cursor.year,
                cursor.month,
                cursor,
                exclude_leave_ids,
            )
            month_segments, paid_used = self._monthly_mien_split_plan_for_month(
                days_before,
                cursor,
                month_end,
                paid_budget=paid_budget,
                monthly_cap=monthly_cap,
            )
            segments.extend(month_segments)
            if paid_budget is not None:
                paid_budget = max(0, paid_budget - paid_used)
            cursor = month_end + timedelta(days=1)
        return segments

    def _monthly_mien_ensure_split_before_notify(self):
        """Tách đơn (nếu cần) trước khi OdooBot gửi tin — tránh tin đơn lẻ thiếu chi tiết P1/P2/O."""
        for leave in self:
            if self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
                continue
            if (
                not leave.employee_id
                or not leave.request_date_from
                or not leave.request_date_to
            ):
                continue
            if not self._monthly_p1p2_mien_applies(leave.employee_id):
                continue
            if "split_group_id" in leave._fields and leave.split_group_id:
                if hasattr(leave, "_get_split_group_leaves_all"):
                    if len(leave._get_split_group_leaves_all()) > 1:
                        continue
            if not leave._monthly_mien_should_split(leave):
                continue
            before_from = leave.request_date_from
            before_to = leave.request_date_to
            leave._monthly_mien_do_split(leave)
            leave.invalidate_recordset(
                ["request_date_from", "request_date_to", "split_group_id"]
            )
            if hasattr(leave, "_split_group_is_multi_segment"):
                if leave._split_group_is_multi_segment():
                    continue
            _logger.warning(
                "monthly_mien_split: split expected for leave %s (%s → %s) "
                "but still single record (check P1/P2/O leave types or Miền)",
                leave.id,
                before_from,
                before_to,
            )

    def _get_monthly_plan_approval_bot_details(self):
        """Chi tiết P1/P2/O theo kế hoạch tháng (dùng khi chưa tách được DB)."""
        self.ensure_one()
        if (
            not self.employee_id
            or not self.request_date_from
            or not self.request_date_to
        ):
            return None
        if not self._monthly_p1p2_mien_applies(self.employee_id):
            return None
        exclude = [self.id] if self.id else []
        plan = self._monthly_mien_split_plan(
            self.employee_id,
            self.request_date_from,
            self.request_date_to,
            exclude,
        )
        if len(plan) <= 1:
            return None
        employee = self.employee_id
        requester_name = employee.name or employee.display_name or self.display_name
        id_hrm = (getattr(employee, "id_hrm", None) or "").strip() or "—"
        department = (employee.department_id.name or "").strip() or "—"
        reason = self._timeoff_internal_reason_text() or "—"
        segment_lines = []
        total_days = 0
        for kind, seg_from, seg_to in plan:
            lt = self._monthly_mien_leave_type_for_kind(kind)
            label = (lt.name if lt else kind.upper()).strip() or "—"
            period = self._format_approval_bot_period(seg_from, seg_to)
            days = (seg_to - seg_from).days + 1
            total_days += days
            segment_lines.append(
                _("• %(type)s: %(period)s (%(days)s ngày)")
                % {
                    "type": label,
                    "period": period,
                    "days": days,
                }
            )
        overall_period = self._format_approval_bot_period(
            self.request_date_from, self.request_date_to
        )
        return {
            "requester": requester_name,
            "id_hrm": id_hrm,
            "department": department,
            "period": overall_period,
            "total_days": "%g" % total_days,
            "reason": reason,
            "segment_lines": "\n".join(segment_lines),
            "segment_count": len(plan),
            "primary": self,
        }

    def _notify_approval_bot_monthly_plan_message(self, approver_user, details):
        """Gửi tin OdooBot dạng gom phần theo kế hoạch P1/P2/O."""
        self.ensure_one()
        primary = details["primary"]
        if not approver_user or approver_user.share or not approver_user.partner_id:
            return
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
            message = chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            primary._register_discuss_approval_notify(
                message, approver_user, primary.split_group_id or 0
            )
        except Exception:
            _logger.exception(
                "monthly_mien_split: failed plan-style bot notify leave_id=%s",
                primary.id,
            )

    def _monthly_mien_should_split(self, leave):
        if self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
            return False
        if not leave.employee_id or not leave.request_date_from or not leave.request_date_to:
            return False
        if not self._monthly_p1p2_mien_applies(leave.employee_id):
            return False
        exclude = [leave.id] if leave.id else []
        plan = self._monthly_mien_split_plan(
            leave.employee_id,
            leave.request_date_from,
            leave.request_date_to,
            exclude,
        )
        return len(plan) > 1

    def _monthly_mien_leave_type_for_kind(self, kind, selected=None, employee=None):
        if employee is None:
            employee = self.employee_id if self else False
        allowed_ids = self._mien_config_leave_type_ids(employee)
        if kind == "p1":
            return self._get_p1_leave_type(selected, allowed_ids=allowed_ids)
        if kind == "p2":
            return self._get_p2_leave_type(selected, allowed_ids=allowed_ids)
        if kind == "o":
            return self._get_o_leave_type(selected, allowed_ids=allowed_ids)
        return self.env["hr.leave.type"]

    def _monthly_mien_plan_leave_types(self, employee, plan):
        leave_types = {}
        for kind, _date_from, _date_to in plan:
            if kind in leave_types:
                continue
            leave_type = self._monthly_mien_leave_type_for_kind(
                kind, employee=employee
            )
            if not leave_type:
                raise ValidationError(
                    _(
                        "Không tìm thấy loại ngày nghỉ có mã (%(code)s) cho Miền "
                        "của nhân viên. Vui lòng liên hệ HR."
                    )
                    % {"code": kind.upper()}
                )
            leave_types[kind] = leave_type
        return leave_types

    def _monthly_mien_make_companion_vals(self, leave, leave_type, date_from, date_to, group_id):
        vals = {
            "employee_id": leave.employee_id.id,
            "holiday_status_id": leave_type.id,
            "request_date_from": date_from,
            "request_date_to": date_to,
            "name": leave.name or "",
            "state": leave.state,
        }
        if "split_group_id" in leave._fields:
            vals["split_group_id"] = group_id
        if leave.department_id:
            vals["department_id"] = leave.department_id.id
        return vals

    def _monthly_mien_do_split(self, leave):
        exclude = [leave.id] if leave.id else []
        plan = self._monthly_mien_split_plan(
            leave.employee_id,
            leave.request_date_from,
            leave.request_date_to,
            exclude,
        )
        if len(plan) <= 1:
            return

        plan_leave_types = self._monthly_mien_plan_leave_types(
            leave.employee_id, plan
        )
        group_id = (
            leave.split_group_id
            if "split_group_id" in leave._fields and leave.split_group_id
            else str(uuid.uuid4())
        )
        first_kind, first_from, first_to = plan[0]
        first_type = plan_leave_types[first_kind]

        write_vals = {
            "holiday_status_id": first_type.id,
            "request_date_from": first_from,
            "request_date_to": first_to,
        }
        if "split_group_id" in leave._fields:
            write_vals["split_group_id"] = group_id
        leave.with_context(
            leave_skip_state_check=True,
            **{_SKIP_MONTHLY_MIEN_REBALANCE_CTX: True},
        ).write(write_vals)

        companions = []
        for kind, seg_from, seg_to in plan[1:]:
            lt = plan_leave_types[kind]
            companions.append(
                self._monthly_mien_make_companion_vals(
                    leave, lt, seg_from, seg_to, group_id
                )
            )

        if companions:
            create_ctx = {
                _SKIP_MONTHLY_MIEN_SPLIT_CTX: True,
                _SKIP_MONTHLY_MIEN_REBALANCE_CTX: True,
                "leave_fast_create": True,
                "mail_activity_automation_skip": True,
                _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX: True,
            }
            Leave = self.with_context(**create_ctx)
            for companion_vals in companions:
                Leave.create([companion_vals])
        if hasattr(leave, "_notify_split_group_after_companion_create"):
            leave._notify_split_group_after_companion_create()

        _logger.info(
            "monthly_mien_split: leave %s → %s segments (%s → %s)",
            leave.id,
            len(plan),
            leave.request_date_from,
            leave.request_date_to,
        )

    # ------------------------------------------------------------------
    # Cân bằng lại P1/P2/O cả tháng theo thứ tự ngày (ngày sớm nhất = P1)
    # ------------------------------------------------------------------

    def _monthly_mien_kind_of_leave_type(self, leave_type):
        """'p1' | 'p2' | 'o' | None — suy ra loại quy tắc từ mã trong tên loại phép."""
        from .hr_leave_mien_config import (
            O_LEAVE_TYPE_CODE,
            P1_LEAVE_TYPE_CODE,
            P2_LEAVE_TYPE_CODE,
        )

        if not leave_type:
            return None
        code = (self.env["hr.leave.type"].code_from_name(leave_type.name) or "").upper()
        if code == P1_LEAVE_TYPE_CODE.upper():
            return "p1"
        if code == P2_LEAVE_TYPE_CODE.upper():
            return "p2"
        if code == O_LEAVE_TYPE_CODE.upper():
            return "o"
        return None

    @api.model
    def _monthly_mien_active_leaves_in_month(self, employee, year, month):
        month_start, month_end = self._month_date_bounds(year, month)
        return self.search(
            [
                ("employee_id", "=", employee.id),
                ("state", "not in", ("cancel", "refuse")),
                ("request_date_from", "<=", month_end),
                ("request_date_to", ">=", month_start),
            ],
            order="request_date_from, id",
        )

    @api.model
    def _monthly_mien_desired_day_kinds(self, employee, year, month):
        """{date: 'p1'|'p2'|'o'} cho mọi ngày nghỉ (chưa hủy/từ chối) trong tháng.

        Sắp xếp theo ngày: ngày sớm nhất → P1, 2 ngày kế → P2, còn lại → O,
        có giới hạn bởi hạn mức tháng và ngân sách phép có lương còn lại.
        """
        month_start, month_end = self._month_date_bounds(year, month)
        leaves = self._monthly_mien_active_leaves_in_month(employee, year, month)
        day_set = set()
        for leave in leaves:
            if not leave.request_date_from or not leave.request_date_to:
                continue
            cursor = max(leave.request_date_from, month_start)
            stop = min(leave.request_date_to, month_end)
            while cursor <= stop:
                day_set.add(cursor)
                cursor += timedelta(days=1)
        if not day_set:
            return {}
        cap = self._monthly_mien_employee_monthly_cap(employee)
        # Ngân sách phép có lương dành cho tháng này = Còn lại sau khi loại trừ
        # mọi đơn của chính tháng này (vì ta đang gán lại loại cho chúng).
        budget = self._monthly_mien_paid_budget_for_employee(
            employee, exclude_leave_ids=leaves.ids
        )
        result = {}
        paid_used = 0
        for day in sorted(day_set):
            can_paid = paid_used < cap and (budget is None or paid_used < budget)
            if can_paid:
                result[day] = "p1" if paid_used == 0 else "p2"
                paid_used += 1
            else:
                result[day] = "o"
        return result

    def _rebalance_write_ctx(self):
        return {
            _SKIP_MONTHLY_MIEN_REBALANCE_CTX: True,
            _SKIP_MONTHLY_MIEN_SPLIT_CTX: True,
            "leave_skip_state_check": True,
            "leave_skip_date_check": True,
            "leave_fast_create": True,
            # Đây là gán lại loại phép tự động trên đơn đã có — không áp dụng
            # giới hạn ngày quá khứ / nghỉ khẩn cấp như khi người dùng nhập tay.
            "skip_past_leave_limit_check": True,
            "skip_emergency_leave_check": True,
        }

    def _rebalance_create_ctx(self):
        return {
            _SKIP_MONTHLY_MIEN_REBALANCE_CTX: True,
            _SKIP_MONTHLY_MIEN_SPLIT_CTX: True,
            "leave_fast_create": True,
            "mail_activity_automation_skip": True,
            _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX: True,
            "skip_past_leave_limit_check": True,
            "skip_emergency_leave_check": True,
            "leave_skip_state_check": True,
            "leave_skip_date_check": True,
        }

    def _rebalance_record_segments(self, leave, desired):
        """List (kind, date_from, date_to) cho từng ngày của đơn theo bản đồ ``desired``.

        Trả về None nếu thiếu thông tin (an toàn, bỏ qua bản ghi).
        """
        dates = []
        cursor = leave.request_date_from
        while cursor <= leave.request_date_to:
            dates.append(cursor)
            cursor += timedelta(days=1)
        if not dates:
            return None
        kinds = []
        for day in dates:
            kind = desired.get(day)
            if not kind:
                return None
            kinds.append(kind)
        segments = []
        seg_kind = kinds[0]
        seg_from = dates[0]
        seg_prev = dates[0]
        for day, kind in zip(dates[1:], kinds[1:]):
            if kind == seg_kind:
                seg_prev = day
                continue
            segments.append((seg_kind, seg_from, seg_prev))
            seg_kind = kind
            seg_from = day
            seg_prev = day
        segments.append((seg_kind, seg_from, seg_prev))
        return segments

    def _rebalance_split_record_into_segments(self, leave, segments):
        plan_leave_types = self._monthly_mien_plan_leave_types(
            leave.employee_id, segments
        )
        group_id = (
            leave.split_group_id
            if "split_group_id" in leave._fields and leave.split_group_id
            else str(uuid.uuid4())
        )
        first_kind, first_from, first_to = segments[0]
        first_type = plan_leave_types[first_kind]
        write_vals = {
            "holiday_status_id": first_type.id,
            "request_date_from": first_from,
            "request_date_to": first_to,
        }
        if "split_group_id" in leave._fields:
            write_vals["split_group_id"] = group_id
        leave.with_context(**self._rebalance_write_ctx()).write(write_vals)

        companion_vals = []
        for kind, seg_from, seg_to in segments[1:]:
            leave_type = plan_leave_types[kind]
            vals = self._monthly_mien_make_companion_vals(
                leave, leave_type, seg_from, seg_to, group_id
            )
            # Tạo companion ở confirm rồi validate sau — tránh constraint trên
            # đơn đã duyệt khi create trực tiếp với state=validate.
            if leave.state == "validate":
                vals["state"] = "confirm"
            companion_vals.append(vals)
        companions = self.env["hr.leave"]
        if companion_vals:
            Leave = self.with_context(**self._rebalance_create_ctx())
            for vals in companion_vals:
                companions |= Leave.create([vals])
            to_validate = companions.filtered(
                lambda l: l.state == "confirm" and leave.state == "validate"
            )
            if to_validate:
                to_validate.with_context(**self._rebalance_write_ctx()).write(
                    {"state": "validate"}
                )
        return leave | companions

    def _reconcile_monthly_mien_record(self, leave, desired):
        """Đưa loại phép của ``leave`` về đúng theo ``desired``. Trả về các bản ghi đã đụng tới."""
        segments = self._rebalance_record_segments(leave, desired)
        if not segments:
            return self.env["hr.leave"]
        if len(segments) == 1:
            target_kind = segments[0][0]
            if self._monthly_mien_kind_of_leave_type(leave.holiday_status_id) == target_kind:
                return self.env["hr.leave"]
            new_type = self._monthly_mien_leave_type_for_kind(
                target_kind, employee=leave.employee_id
            )
            if not new_type:
                raise ValidationError(
                    _(
                        "Không tìm thấy loại ngày nghỉ có mã (%(code)s) cho Miền "
                        "của nhân viên. Vui lòng liên hệ HR."
                    )
                    % {"code": target_kind.upper()}
                )
            if new_type == leave.holiday_status_id:
                return self.env["hr.leave"]
            leave.with_context(**self._rebalance_write_ctx()).write(
                {"holiday_status_id": new_type.id}
            )
            return leave
        return self._rebalance_split_record_into_segments(leave, segments)

    def _rebalance_monthly_mien_month(self, employee, year, month):
        touched = self.env["hr.leave"]
        if not employee or not self._monthly_p1p2_mien_applies(employee):
            return touched
        desired = self._monthly_mien_desired_day_kinds(employee, year, month)
        if not desired:
            return touched
        for leave in self._monthly_mien_active_leaves_in_month(employee, year, month):
            if not leave.request_date_from or not leave.request_date_to:
                continue
            # Chỉ xử lý bản ghi nằm gọn trong tháng (đơn nhiều tháng đã được
            # tách theo ranh giới tháng lúc tạo).
            if (leave.request_date_from.year, leave.request_date_from.month) != (year, month):
                continue
            if (leave.request_date_to.year, leave.request_date_to.month) != (year, month):
                continue
            try:
                touched |= self._reconcile_monthly_mien_record(leave, desired)
            except ValidationError:
                raise
            except Exception:
                _logger.exception(
                    "monthly_mien_rebalance: reconcile failed leave_id=%s", leave.id
                )
        return touched

    def _collect_monthly_mien_rebalance_targets(self):
        """Tập (employee_id, year, month) cần cân bằng lại theo các đơn trong ``self``."""
        targets = set()
        for leave in self:
            employee = leave.employee_id
            if not employee or not self._monthly_p1p2_mien_applies(employee):
                continue
            date_from = leave._get_leave_start_date()
            date_to = leave._get_leave_end_date()
            if not date_from or not date_to:
                continue
            if date_to < date_from:
                date_from, date_to = date_to, date_from
            year, month = date_from.year, date_from.month
            while (year, month) <= (date_to.year, date_to.month):
                targets.add((employee.id, year, month))
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
        return targets

    def _run_monthly_mien_rebalance(self, targets):
        if not targets or self.env.context.get(_SKIP_MONTHLY_MIEN_REBALANCE_CTX):
            return self.env["hr.leave"]
        Employee = self.env["hr.employee"]
        touched = self.env["hr.leave"]
        for employee_id, year, month in targets:
            employee = Employee.browse(employee_id)
            if not employee.exists():
                continue
            touched |= self._rebalance_monthly_mien_month(employee, year, month)
        if touched and hasattr(touched, "_recompute_employee_time_off_summary"):
            try:
                touched._recompute_employee_time_off_summary()
            except Exception:
                _logger.exception(
                    "monthly_mien_rebalance: time-off summary recompute failed"
                )
        return touched
