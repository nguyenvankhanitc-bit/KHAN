# -*- coding: utf-8 -*-

import calendar
from datetime import date, datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .hr_leave_mien_config import (
    FIRST_MONTH_LEAVE_P1_MIEN_CODES,
    MAX_PAID_LEAVE_DAYS_PER_MONTH,
    O_LEAVE_TYPE_CODE,
    P1_LEAVE_TYPE_CODE,
    P2_LEAVE_TYPE_CODE,
)
from .hr_leave_monthly_split import (
    _SKIP_MONTHLY_MIEN_REBALANCE_CTX,
    _SKIP_MONTHLY_MIEN_SPLIT_CTX,
    _SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX,
)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    mien_allowed_leave_type_ids = fields.Many2many(
        comodel_name="hr.leave.type",
        relation="hr_leave_mien_allowed_leave_type_rel",
        column1="leave_id",
        column2="leave_type_id",
        string="Loại phép theo Miền",
        compute="_compute_mien_allowed_leave_type_ids",
        store=True,
        readonly=True,
    )
    holiday_status_id_month_leave_type_locked = fields.Boolean(
        string="Khóa loại phép P1/P2/O theo tháng",
        compute="_compute_holiday_status_id_month_leave_type_locked",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _mien_config_leave_type_ids(self, employee):
        """ID loại phép cấu hình cho Miền của nhân viên (để chọn đúng loại khi trùng mã)."""
        if not employee:
            return None
        mien = employee._get_leave_mien()
        if not mien:
            return None
        MienConfig = self.env["hr.leave.mien.config"]
        if not MienConfig._is_mien_configured(mien):
            return None
        return MienConfig._get_leave_type_ids_for_mien(mien)

    @api.model
    def _get_p1_leave_type(self, selected=None, allowed_ids=None):
        return self.env["hr.leave.type"].leave_type_from_selection(
            selected, P1_LEAVE_TYPE_CODE, allowed_ids=allowed_ids
        )

    @api.model
    def _get_p2_leave_type(self, selected=None, allowed_ids=None):
        return self.env["hr.leave.type"].leave_type_from_selection(
            selected, P2_LEAVE_TYPE_CODE, allowed_ids=allowed_ids
        )

    @api.model
    def _get_o_leave_type(self, selected=None, allowed_ids=None):
        return self.env["hr.leave.type"].leave_type_from_selection(
            selected, O_LEAVE_TYPE_CODE, allowed_ids=allowed_ids
        )

    def _get_leave_start_date(self):
        self.ensure_one()
        if self.request_date_from:
            return self.request_date_from
        if self.date_from:
            return self.date_from.date()
        return False

    def _get_leave_end_date(self):
        self.ensure_one()
        if self.request_date_to:
            return self.request_date_to
        if self.date_to:
            return self.date_to.date()
        return self._get_leave_start_date()

    @api.model
    def _coerce_to_date(self, value):
        if not value:
            return False
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return fields.Date.to_date(value)

    @api.model
    def _parse_start_date_from_vals(self, vals, leave=None):
        start_date = False
        if vals:
            if vals.get("request_date_from"):
                start_date = self._coerce_to_date(vals["request_date_from"])
            elif vals.get("date_from"):
                start_date = self._coerce_to_date(vals["date_from"])
        if not start_date and leave:
            start_date = leave._get_leave_start_date()
        return start_date

    @api.model
    def _parse_end_date_from_vals(self, vals, leave=None):
        end_date = False
        if vals:
            if vals.get("request_date_to"):
                end_date = self._coerce_to_date(vals["request_date_to"])
            elif vals.get("date_to"):
                end_date = self._coerce_to_date(vals["date_to"])
        if not end_date and leave:
            end_date = leave._get_leave_end_date()
        if not end_date:
            end_date = self._parse_start_date_from_vals(vals, leave=leave)
        return end_date

    @api.model
    def _monthly_p1p2_mien_applies(self, employee):
        return bool(
            employee and employee._get_leave_mien() in FIRST_MONTH_LEAVE_P1_MIEN_CODES
        )

    @api.model
    def _month_date_bounds(self, year, month):
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    @api.model
    def _leave_days_overlapping_month(self, leave, year, month):
        if not leave.request_date_from or not leave.request_date_to:
            return 0
        month_start, month_end = self._month_date_bounds(year, month)
        start = max(leave.request_date_from, month_start)
        end = min(leave.request_date_to, month_end)
        if start > end:
            return 0
        return (end - start).days + 1

    @api.model
    def _count_leave_days_in_calendar_month(
        self, employee, year, month, exclude_leave_ids=None
    ):
        """Tổng số ngày nghỉ (đơn không hủy/từ chối) giao với tháng."""
        month_start, month_end = self._month_date_bounds(year, month)
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "not in", ("cancel", "refuse")),
            ("request_date_from", "<=", month_end),
            ("request_date_to", ">=", month_start),
        ]
        if exclude_leave_ids:
            domain.append(("id", "not in", list(exclude_leave_ids)))
        total = 0
        for leave in self.search(domain):
            total += self._leave_days_overlapping_month(leave, year, month)
        return total

    @api.model
    def _leave_days_overlapping_range(self, leave, start, end):
        if not leave.request_date_from or not leave.request_date_to:
            return 0
        a = max(leave.request_date_from, start)
        b = min(leave.request_date_to, end)
        if a > b:
            return 0
        return (b - a).days + 1

    @api.model
    def _count_active_leave_days_in_month_before(
        self, employee, year, month, before_date, exclude_leave_ids=None
    ):
        """Số ngày nghỉ (đơn không hủy/từ chối) trong tháng có ngày *sớm hơn* ``before_date``.

        Dùng để gán P1/P2/O theo thứ tự ngày: ngày nghỉ sớm nhất trong tháng → P1.
        """
        before_date = self._coerce_to_date(before_date)
        if not before_date:
            return 0
        month_start, month_end = self._month_date_bounds(year, month)
        window_end = min(before_date - timedelta(days=1), month_end)
        if window_end < month_start:
            return 0
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "not in", ("cancel", "refuse")),
            ("request_date_from", "<=", window_end),
            ("request_date_to", ">=", month_start),
        ]
        if exclude_leave_ids:
            domain.append(("id", "not in", list(exclude_leave_ids)))
        total = 0
        for leave in self.search(domain):
            total += self._leave_days_overlapping_range(leave, month_start, window_end)
        return total

    @api.model
    def _employee_has_leave_in_calendar_month(
        self, employee, year, month, exclude_leave_ids=None
    ):
        return self._count_leave_days_in_calendar_month(
            employee, year, month, exclude_leave_ids
        ) > 0

    @api.model
    def _employee_has_p1_leave_in_calendar_month(
        self, employee, year, month, exclude_leave_ids=None
    ):
        p1_type = self._get_p1_leave_type()
        if not p1_type:
            return False
        month_start, month_end = self._month_date_bounds(year, month)
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "not in", ("cancel", "refuse")),
            ("holiday_status_id", "=", p1_type.id),
            ("request_date_from", "<=", month_end),
            ("request_date_to", ">=", month_start),
        ]
        if exclude_leave_ids:
            domain.append(("id", "not in", list(exclude_leave_ids)))
        return bool(self.search(domain, limit=1))

    @api.model
    def _monthly_o_rule_applies(self, employee, start_date, leave=None):
        """Từ ngày nghỉ vượt hạn mức tháng trở đi → O."""
        start_date = self._coerce_to_date(start_date)
        if not self._monthly_p1p2_mien_applies(employee) or not start_date:
            return False
        exclude = [leave.id] if leave and leave.id else []
        days_before = self._count_leave_days_in_calendar_month(
            employee, start_date.year, start_date.month, exclude
        )
        cap = self._monthly_mien_employee_monthly_cap(employee)
        return days_before >= cap

    @api.model
    def _first_leave_in_month_p1_rule_applies(self, employee, start_date, leave=None):
        start_date = self._coerce_to_date(start_date)
        if not self._monthly_p1p2_mien_applies(employee) or not start_date:
            return False
        if self._monthly_o_rule_applies(employee, start_date, leave):
            return False
        exclude = [leave.id] if leave and leave.id else []
        return not self._employee_has_leave_in_calendar_month(
            employee, start_date.year, start_date.month, exclude
        )

    @api.model
    def _subsequent_month_leave_p2_rule_applies(self, employee, start_date, leave=None):
        start_date = self._coerce_to_date(start_date)
        if not self._monthly_p1p2_mien_applies(employee) or not start_date:
            return False
        if self._monthly_o_rule_applies(employee, start_date, leave):
            return False
        exclude = [leave.id] if leave and leave.id else []
        if not self._employee_has_p1_leave_in_calendar_month(
            employee, start_date.year, start_date.month, exclude
        ):
            return False
        days_before = self._count_leave_days_in_calendar_month(
            employee, start_date.year, start_date.month, exclude
        )
        cap = self._monthly_mien_employee_monthly_cap(employee)
        return days_before < cap

    @api.model
    def _monthly_leave_rule_kind(self, employee, start_date, leave=None, end_date=None):
        """'p1' | 'p2' | 'o' | None — loại áp dụng cho đoạn đầu của đơn."""
        start_date = self._coerce_to_date(start_date)
        end_date = self._coerce_to_date(end_date) or start_date
        if not self._monthly_p1p2_mien_applies(employee) or not start_date:
            return None
        exclude = [leave.id] if leave and leave.id else []
        days_before = self._count_active_leave_days_in_month_before(
            employee, start_date.year, start_date.month, start_date, exclude
        )
        cap = self._monthly_mien_employee_monthly_cap(employee)
        if days_before >= cap:
            return "o"
        plan = self._monthly_mien_split_plan(
            employee, start_date, end_date, exclude
        )
        if plan:
            return plan[0][0]
        return None

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends(
        "employee_id",
        "employee_id.mien",
        "employee_id.ma_bo_phan_id.mien",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _compute_holiday_status_id_month_leave_type_locked(self):
        for leave in self:
            leave.holiday_status_id_month_leave_type_locked = bool(
                leave._monthly_leave_rule_kind(
                    leave.employee_id,
                    leave._get_leave_start_date(),
                    leave=leave,
                    end_date=leave._get_leave_end_date(),
                )
            )

    @api.depends(
        "employee_id",
        "employee_id.mien",
        "employee_id.ma_bo_phan_id.mien",
        "request_date_from",
        "request_date_to",
        "date_from",
    )
    def _compute_mien_allowed_leave_type_ids(self):
        LeaveType = self.env["hr.leave.type"]
        for leave in self:
            employee = leave.employee_id
            if not employee:
                leave.mien_allowed_leave_type_ids = LeaveType
                continue
            domain = leave._leave_type_domain_for_employee(
                employee,
                start_date=leave._get_leave_start_date(),
                end_date=leave._get_leave_end_date(),
                leave=leave,
            )
            leave.mien_allowed_leave_type_ids = LeaveType.with_context(
                employee_id=employee.id
            ).search(domain)

    def onchange(self, values, field_names, fields_spec):
        if values and "employee_id" in fields_spec:
            Employee = self.env["hr.employee"]
            employee = Employee._search_accessible_employee(values.get("employee_id"))
            if not employee:
                employee = self._safe_timeoff_context_employee()
            if employee:
                self = self.with_context(
                    employee_id=employee.id,
                    default_employee_id=employee.id,
                )
        return super().onchange(values, field_names, fields_spec)

    @api.model
    def _leave_type_base_domain(self):
        return [
            "|",
            ("requires_allocation", "=", False),
            "&",
            ("has_valid_allocation", "=", True),
            "|",
            ("allows_negative", "=", True),
            "&",
            ("virtual_remaining_leaves", ">", 0),
            ("allows_negative", "=", False),
        ]

    @api.model
    def _leave_type_domain_for_employee(
        self, employee, start_date=None, end_date=None, leave=None
    ):
        domain = list(self._leave_type_base_domain())
        if not employee:
            return domain
        config_ids = self._mien_config_leave_type_ids(employee)
        if config_ids is not None:
            domain = ["&"] + domain + [("id", "in", config_ids or [0])]
        rule = self._monthly_leave_rule_kind(
            employee, start_date, leave=leave, end_date=end_date
        )
        rule_type = self._leave_type_for_rule(rule, employee=employee)
        if rule_type:
            domain = ["&"] + domain + [("id", "=", rule_type.id)]
        return domain

    def _search_allowed_leave_types(
        self, employee, start_date=None, end_date=None, leave=None
    ):
        if not employee:
            return self.env["hr.leave.type"]
        domain = self._leave_type_domain_for_employee(
            employee, start_date=start_date, end_date=end_date, leave=leave
        )
        return self.env["hr.leave.type"].with_context(employee_id=employee.id).search(
            domain
        )

    def _leave_type_for_rule(self, rule, selected=None, employee=None):
        if employee is None:
            employee = self.employee_id if self else False
        allowed_ids = self._mien_config_leave_type_ids(employee)
        if rule == "p1":
            return self._get_p1_leave_type(selected, allowed_ids=allowed_ids)
        if rule == "p2":
            return self._get_p2_leave_type(selected, allowed_ids=allowed_ids)
        if rule == "o":
            return self._get_o_leave_type(selected, allowed_ids=allowed_ids)
        return self.env["hr.leave.type"]

    def _apply_monthly_leave_rule_to_vals(self, vals, employee, start_date, leave=None):
        vals = dict(vals)
        end_date = self._parse_end_date_from_vals(vals, leave=leave) or start_date
        selected = (
            self.env["hr.leave.type"].browse(vals["holiday_status_id"])
            if vals.get("holiday_status_id")
            else (leave.holiday_status_id if leave else False)
        )
        rule = self._monthly_leave_rule_kind(
            employee, start_date, leave=leave, end_date=end_date
        )
        leave_type = self._leave_type_for_rule(rule, selected, employee=employee)
        if leave_type:
            vals["holiday_status_id"] = leave_type.id
        elif rule:
            raise ValidationError(
                _(
                    "Không tìm thấy loại ngày nghỉ có mã (%(code)s) cho Miền của "
                    "nhân viên. Vui lòng liên hệ HR."
                )
                % {"code": rule.upper()}
            )
        return vals

    def _monthly_leave_warning_missing_type(self, code):
        return {
            "warning": {
                "title": _("Thiếu cấu hình loại phép"),
                "message": _(
                    "Không tìm thấy loại ngày nghỉ có mã (%(code)s) trong tên "
                    "(ví dụ: Nghỉ phép (%(code)s)). Vui lòng liên hệ HR."
                )
                % {"code": code},
            }
        }

    def _default_get_split_preview(self, res, fields_list):
        if "monthly_leave_split_preview" not in fields_list:
            return res
        employee = (
            self.env["hr.employee"].browse(res["employee_id"])
            if res.get("employee_id")
            else self.env.user.employee_id
        )
        leave = self.new(
            {
                "employee_id": employee.id if employee else False,
                "request_date_from": res.get("request_date_from"),
                "request_date_to": res.get("request_date_to"),
            }
        )
        try:
            res["monthly_leave_split_preview"] = (
                leave._build_monthly_leave_split_preview_text() or False
            )
        except Exception:
            res["monthly_leave_split_preview"] = False
        return res

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res = self._default_get_split_preview(res, fields_list)
        if not self.env.context.get("holiday_status_display_name", True) or "holiday_status_id" not in fields_list:
            return res
        employee = (
            self.env["hr.employee"].browse(res["employee_id"])
            if res.get("employee_id")
            else self.env.user.employee_id
        )
        start_date = self._coerce_to_date(res.get("request_date_from"))
        if not start_date:
            start_date = self._coerce_to_date(res.get("date_from"))
        if not start_date:
            for ctx_key in ("default_request_date_from", "default_date_from"):
                ctx_val = self.env.context.get(ctx_key)
                if ctx_val:
                    start_date = self._coerce_to_date(ctx_val)
                    break
        end_date = self._coerce_to_date(res.get("request_date_to")) or start_date
        rule = self._monthly_leave_rule_kind(
            employee, start_date, end_date=end_date
        )
        leave_type = self._leave_type_for_rule(rule, employee=employee)
        if leave_type:
            res["holiday_status_id"] = leave_type.id
            res["request_unit_hours"] = leave_type.request_unit == "hour"
            return res
        domain = self._leave_type_domain_for_employee(
            employee, start_date=start_date, end_date=end_date
        )
        leave_types = self.env["hr.leave.type"].search(domain, order="sequence")
        selected = next(
            (
                lt
                for lt in leave_types
                if (res.get("request_unit_hours") and lt.request_unit == "hour")
                or (not res.get("request_unit_hours"))
            ),
            leave_types[:1],
        )
        if selected:
            res["holiday_status_id"] = selected.id
            res["request_unit_hours"] = selected.request_unit == "hour"
        else:
            res["holiday_status_id"] = False
        return res

    @api.onchange("employee_id", "request_date_from", "request_date_to")
    def _onchange_employee_id_mien_leave_type(self):
        employee = self.employee_id
        start_date = self.request_date_from
        end_date = self.request_date_to or start_date
        self._refresh_monthly_leave_split_preview()
        if not employee:
            return {}
        rule = self._monthly_leave_rule_kind(
            employee, start_date, leave=self, end_date=end_date
        )
        if rule:
            leave_type = self._leave_type_for_rule(rule, self.holiday_status_id)
            code_map = {
                "p1": P1_LEAVE_TYPE_CODE,
                "p2": P2_LEAVE_TYPE_CODE,
                "o": O_LEAVE_TYPE_CODE,
            }
            if not leave_type:
                return self._monthly_leave_warning_missing_type(code_map[rule])
            self.holiday_status_id = leave_type
            return {"domain": {"holiday_status_id": [("id", "=", leave_type.id)]}}
        allowed = self._search_allowed_leave_types(
            employee, start_date=start_date, end_date=end_date, leave=self
        )
        allowed_ids = allowed.ids
        mien = employee._get_leave_mien()
        if (
            self.holiday_status_id
            and mien
            and self.env["hr.leave.mien.config"]._is_mien_configured(mien)
            and self.holiday_status_id.id not in allowed_ids
        ):
            self.holiday_status_id = False
        return {"domain": {"holiday_status_id": [("id", "in", allowed_ids)]}}

    @api.constrains("employee_id", "holiday_status_id")
    def _check_holiday_status_mien(self):
        MienConfig = self.env["hr.leave.mien.config"]
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            mien = leave.employee_id._get_leave_mien()
            if not mien:
                continue
            if not MienConfig._is_mien_configured(mien):
                continue
            allowed_ids = MienConfig._get_leave_type_ids_for_mien(mien)
            if leave.holiday_status_id.id not in allowed_ids:
                raise ValidationError(
                    _("Loại ngày nghỉ «%s» không áp dụng cho Miền %s của nhân viên.")
                    % (leave.holiday_status_id.name, mien)
                )

    @api.constrains(
        "employee_id",
        "holiday_status_id",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _check_monthly_p1p2o_leave_type(self):
        for leave in self:
            if self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
                continue
            start = leave._get_leave_start_date()
            end = leave._get_leave_end_date()
            if not start or not end:
                continue
            exclude = [leave.id] if leave.id else []
            plan = leave._monthly_mien_split_plan(
                leave.employee_id, start, end, exclude
            )
            if len(plan) > 1:
                continue
            rule = leave._monthly_leave_rule_kind(
                leave.employee_id, start, leave=leave, end_date=end
            )
            if not rule:
                continue
            mien = leave.employee_id._get_leave_mien()
            expected = leave._leave_type_for_rule(rule, leave.holiday_status_id)
            code_map = {
                "p1": P1_LEAVE_TYPE_CODE,
                "p2": P2_LEAVE_TYPE_CODE,
                "o": O_LEAVE_TYPE_CODE,
            }
            if not expected:
                raise ValidationError(
                    _(
                        "Không tìm thấy loại ngày nghỉ có mã (%(code)s) trong tên. "
                        "Vui lòng liên hệ HR."
                    )
                    % {"code": code_map[rule]}
                )
            if leave.holiday_status_id != expected:
                messages = {
                    "p1": _(
                        "Nhân viên miền %(mien)s: đơn nghỉ đầu tiên trong tháng "
                        "bắt buộc loại (%(code)s)."
                    ),
                    "p2": _(
                        "Nhân viên miền %(mien)s: sau phép (%(p1)s) trong tháng, "
                        "ngày nghỉ tiếp theo bắt buộc loại (%(p2)s)."
                    ),
                    "o": _(
                        "Nhân viên miền %(mien)s: đã nghỉ %(max)s ngày phép trong tháng, "
                        "từ ngày thứ %(day)s trở đi bắt buộc loại (%(o)s)."
                    ),
                }
                cap = leave._monthly_mien_employee_monthly_cap(leave.employee_id)
                params = {
                    "mien": mien,
                    "code": code_map[rule],
                    "p1": P1_LEAVE_TYPE_CODE,
                    "p2": P2_LEAVE_TYPE_CODE,
                    "o": O_LEAVE_TYPE_CODE,
                    "max": cap,
                    "day": cap + 1,
                }
                raise ValidationError(messages[rule] % params)

    def _monthly_mien_any_will_split_vals_list(self, vals_list):
        if self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
            return False
        Leave = self.env["hr.leave"]
        for vals in vals_list:
            if Leave._monthly_mien_should_split(Leave.new(dict(vals))):
                return True
        return False

    @api.model_create_multi
    def create(self, vals_list):
        rebalance_skip = self.env.context.get(_SKIP_MONTHLY_MIEN_REBALANCE_CTX)
        new_vals_list = []
        for vals in vals_list:
            if rebalance_skip:
                new_vals_list.append(vals)
                continue
            employee = (
                self.env["hr.employee"].browse(vals["employee_id"])
                if vals.get("employee_id")
                else False
            )
            start_date = self._parse_start_date_from_vals(vals)
            if employee and start_date:
                vals = self._apply_monthly_leave_rule_to_vals(
                    vals, employee, start_date
                )
            new_vals_list.append(vals)
        ctx = dict(self.env.context)
        if not rebalance_skip and self._monthly_mien_any_will_split_vals_list(
            new_vals_list
        ):
            ctx[_SKIP_RESPONSIBLE_SUBMIT_NOTIFY_CTX] = True
        records = super(HrLeave, self.with_context(ctx)).create(new_vals_list)
        if not self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
            for leave in records:
                if leave._monthly_mien_should_split(leave):
                    leave._monthly_mien_do_split(leave)
            records._run_monthly_mien_rebalance(
                records._collect_monthly_mien_rebalance_targets()
            )
        return records

    def write(self, vals):
        if self.env.context.get(_SKIP_MONTHLY_MIEN_REBALANCE_CTX):
            return super().write(vals)
        date_emp_change = bool(
            {
                "employee_id",
                "request_date_from",
                "request_date_to",
                "date_from",
                "date_to",
            }
            & set(vals)
        )
        # Hủy/từ chối (đổi state) cũng phải kích hoạt cân bằng lại để ngày nghỉ
        # sớm nhất còn lại trong tháng được gán P1. Chỉ quan tâm khi đơn vào/ra
        # khỏi trạng thái cancel/refuse (các bước duyệt confirm→validate không
        # đổi tập đơn đang hiệu lực nên bỏ qua cho nhẹ).
        state_change = "state" in vals and (
            vals.get("state") in ("cancel", "refuse")
            or any(leave.state in ("cancel", "refuse") for leave in self)
        )
        if not date_emp_change and not state_change:
            return super().write(vals)

        targets = self._collect_monthly_mien_rebalance_targets()

        if not date_emp_change:
            res = super().write(vals)
        elif len(self) == 1:
            leave = self
            employee = (
                self.env["hr.employee"].browse(vals["employee_id"])
                if "employee_id" in vals
                else leave.employee_id
            )
            start_date = self._parse_start_date_from_vals(vals, leave=leave)
            vals = self._apply_monthly_leave_rule_to_vals(
                vals, employee, start_date, leave=leave
            )
            res = super().write(vals)
            if not self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
                if leave._monthly_mien_should_split(leave):
                    leave._monthly_mien_do_split(leave)
        else:
            for leave in self:
                row_vals = dict(vals)
                employee = (
                    self.env["hr.employee"].browse(row_vals["employee_id"])
                    if "employee_id" in row_vals
                    else leave.employee_id
                )
                start_date = self._parse_start_date_from_vals(row_vals, leave=leave)
                row_vals = self._apply_monthly_leave_rule_to_vals(
                    row_vals, employee, start_date, leave=leave
                )
                super(HrLeave, leave).write(row_vals)
            res = True

        if not self.env.context.get(_SKIP_MONTHLY_MIEN_SPLIT_CTX):
            targets |= self._collect_monthly_mien_rebalance_targets()
            self._run_monthly_mien_rebalance(targets)
        return res

    def unlink(self):
        targets = set()
        if not self.env.context.get(_SKIP_MONTHLY_MIEN_REBALANCE_CTX):
            targets = self._collect_monthly_mien_rebalance_targets()
        res = super().unlink()
        if targets:
            self.env["hr.leave"]._run_monthly_mien_rebalance(targets)
        return res

    def _split_group_notify_submission_for_records(self):
        self._monthly_mien_ensure_split_before_notify()
        orphans = self.filtered(
            lambda l: l.split_group_id
            and hasattr(l, "_split_group_is_multi_segment")
            and not l._split_group_is_multi_segment()
        )
        if orphans:
            orphans.sudo().write({"split_group_id": False})
        return super()._split_group_notify_submission_for_records()

    def _notify_responsible_current_turn_via_approval_bot(self, approver_user):
        self.ensure_one()
        self._monthly_mien_ensure_split_before_notify()
        if (
            self.split_group_id
            and hasattr(self, "_split_group_is_multi_segment")
            and self._split_group_is_multi_segment()
        ):
            if hasattr(self, "_is_split_group_primary_leave") and not self._is_split_group_primary_leave():
                return
            group = self._get_split_group_leaves_all()
            return self._notify_responsible_current_turn_via_approval_bot_group(
                approver_user, group
            )
        plan_details = self._get_monthly_plan_approval_bot_details()
        if plan_details:
            return self._notify_approval_bot_monthly_plan_message(
                approver_user, plan_details
            )
        return super()._notify_responsible_current_turn_via_approval_bot(approver_user)
