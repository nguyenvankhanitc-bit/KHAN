import logging
from datetime import date, datetime, time

import pytz

from odoo import api, fields, models
from odoo.addons.hr.models.hr_employee import _ALLOW_READ_HR_EMPLOYEE
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

# Đơn đang trừ/chiếm chỗ trong ngân sách Còn lại (chưa hủy/từ chối).
_LEAVES_BUDGET_STATES = ("confirm", "validate1", "validate")
_TIMEOFF_SELF_SERVICE_CTX = "hr_employee_timeoff_self_service"
_MONTHLY_LEAVE_BONUS_DATE_CTX = "monthly_leave_bonus_date"
_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX = "skip_previous_year_balance_sync"
_SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX = (
    "skip_departure_monthly_leave_cutoff"
)
_SKIP_DEPARTURE_MONTHLY_LEAVE_REVERSAL_CTX = (
    "skip_departure_monthly_leave_reversal"
)
_DEPARTURE_MONTHLY_LEAVE_CUTOFF_DAY = 20
# HR-only fields that time-off logic must read on the user's own employee record.
_TIMEOFF_SELF_READ_FIELDS = frozenset({"version_id", "mien", "ma_bo_phan_id"})
# Tên Job Position được phép chỉnh `monthly_paid_leave_cap`.
_MONTHLY_CAP_EDITOR_JOB_POSITION = "sale admin"


class HrEmployeeTimeoff(models.Model):
    _inherit = "hr.employee"

    @api.model
    def _coerce_context_employee_id(self, emp_id):
        if emp_id in (None, False):
            return False
        if isinstance(emp_id, dict):
            emp_id = emp_id.get("id")
        if isinstance(emp_id, (list, tuple)):
            emp_id = emp_id[0] if emp_id else False
        return emp_id or False

    @api.model
    def _search_accessible_employee(self, emp_id):
        """Resolve employee id from context only when visible to current user."""
        emp_id = self._coerce_context_employee_id(emp_id)
        if not emp_id:
            return self.env["hr.employee"]
        return self.search([("id", "=", emp_id)], limit=1)

    def _timeoff_summary_privacy_context(self):
        """Allow stored compute writes for time-off counters (hr_employee_self_only)."""
        return {
            "employees_no_timeoff_write": True,
            "employees_no_allowed_employee_ids": self.ids,
        }

    def _employees_for_timeoff_summary_compute(self):
        """Only employees visible to the current user (skips OdooBot / out-of-scope rows)."""
        if not self:
            return self.env["hr.employee"]
        return self.env["hr.employee"].search([("id", "in", self.ids)])

    @api.model
    def _timeoff_self_service_context(self):
        return {_TIMEOFF_SELF_SERVICE_CTX: True}

    def _check_access(self, operation):
        if (
            operation == "read"
            and not self.env.su
            and self.env.context.get("_allow_read_hr_employee") is _ALLOW_READ_HR_EMPLOYEE
        ):
            return None
        return super()._check_access(operation)

    @api.model
    def _has_field_access(self, field, operation):
        if (
            operation == "read"
            and not self.env.su
            and self.env.context.get("_allow_read_hr_employee") is _ALLOW_READ_HR_EMPLOYEE
        ):
            return True
        if (
            field.name in _TIMEOFF_SELF_READ_FIELDS
            and operation == "read"
            and not self.env.su
            and not self.env.user.has_group("hr.group_hr_user")
        ):
            own = self.env.user.employee_id
            if own and self.ids and set(self.ids) <= set(own.ids):
                return True
            if self.env.context.get(_TIMEOFF_SELF_SERVICE_CTX):
                return True
            if self.env.user.has_group("hr_holidays.group_hr_holidays_responsible"):
                accessible = self.env["hr.employee"].search([("id", "in", self.ids)])
                if self.ids and set(accessible.ids) == set(self.ids):
                    return True
        return super()._has_field_access(field, operation)

    def _employee_for_timeoff_calendar(self):
        """Sudo + self-service context for calendar helpers (mandatory/unusual days)."""
        if self.env.user.has_group("hr.group_hr_manager"):
            return self
        return self._sudo_for_timeoff_access().with_context(
            **self._timeoff_self_service_context()
        )

    def _get_mandatory_days(self, start_date, end_date):
        return super(
            HrEmployeeTimeoff, self._employee_for_timeoff_calendar()
        )._get_mandatory_days(start_date, end_date)

    def _get_unusual_days(self, date_from, date_to=None):
        if self.env.user.has_group("hr.group_hr_manager"):
            return super()._get_unusual_days(date_from, date_to)
        self = self._employee_for_timeoff_calendar().sudo()
        date_from_date = datetime.strptime(date_from, "%Y-%m-%d %H:%M:%S").date()
        date_to_date = (
            datetime.strptime(date_to, "%Y-%m-%d %H:%M:%S").date() if date_to else None
        )
        employee_versions = self.env["hr.version"].sudo().search(
            [("employee_id", "=", self.id)]
        ).filtered(lambda version: version._is_overlapping_period(date_from_date, date_to_date))
        if not employee_versions:
            calendar = self.resource_calendar_id or self.env.company.resource_calendar_id
            return calendar._get_unusual_days(
                datetime.combine(fields.Date.from_string(date_from), time.min).replace(
                    tzinfo=pytz.UTC
                ),
                datetime.combine(fields.Date.from_string(date_to), time.max).replace(
                    tzinfo=pytz.UTC
                ),
                self.company_id,
            )
        unusual_days = {}
        for version in employee_versions:
            tmp_date_from = max(date_from_date, version.date_start)
            tmp_date_to = (
                min(date_to_date, version.date_end) if version.date_end else date_to_date
            )
            calendar = version.resource_calendar_id
            if not calendar:
                continue
            unusual_days.update(
                calendar._get_unusual_days(
                    datetime.combine(
                        fields.Date.from_string(tmp_date_from), time.min
                    ).replace(tzinfo=pytz.UTC),
                    datetime.combine(
                        fields.Date.from_string(tmp_date_to), time.max
                    ).replace(tzinfo=pytz.UTC),
                    self.company_id,
                )
            )
        return unusual_days

    def _get_public_holidays(self, date_start, date_end):
        return super(
            HrEmployeeTimeoff, self._employee_for_timeoff_calendar()
        )._get_public_holidays(date_start, date_end)

    @api.model
    def _get_contextual_employee(self):
        ctx = self.env.context
        employee = self.env["hr.employee"]
        for key in ("employee_id", "default_employee_id"):
            if ctx.get(key) is not None:
                found = self._search_accessible_employee(ctx.get(key))
                if found:
                    employee = found
                    break
        if not employee:
            employee = self.env.user.employee_id
        if employee:
            employee = employee.with_context(**self._timeoff_self_service_context())
        return employee._sudo_for_timeoff_access() if employee else employee

    def _sudo_for_timeoff_access(self):
        """Read version-linked employee fields for permitted time-off UI without HR administrator."""
        if self.env.user.has_group("hr.group_hr_manager"):
            return self
        if not self:
            return self
        own = self.env.user.employee_id
        if own and set(self.ids) <= set(own.ids):
            return self.sudo()
        accessible = self.env["hr.employee"].search([("id", "in", self.ids)])
        if set(accessible.ids) != set(self.ids):
            return self
        return accessible.sudo()

    def get_mandatory_days(self, start_date, end_date):
        self = self.with_context(**self._timeoff_self_service_context())
        if self:
            self = self.env["hr.employee"].search([("id", "in", self.ids)])
        if not self:
            self = self._get_contextual_employee()
        return super(HrEmployeeTimeoff, self).get_mandatory_days(start_date, end_date)

    phep_chuan = fields.Float(string="Phép chuẩn")
    tong_so_phep = fields.Float(string="Tổng số phép")
    last_monthly_leave_bonus_date = fields.Date(
        string="Tháng cộng phép gần nhất",
        readonly=True,
        copy=False,
    )
    departure_monthly_leave_reversal_date = fields.Date(
        string="Tháng đã trừ phép do nghỉ việc",
        readonly=True,
        copy=False,
    )
    da_su_dung = fields.Float(
        string="Số phép đã sử dụng",
        compute="_compute_time_off_summary",
        store=True,
    )
    con_lai = fields.Float(
        string="Số phép còn lại",
        compute="_compute_time_off_summary",
        store=True,
    )
    ngay_het_han = fields.Date(string="Ngày hết hạn")
    con_lai_nam_truoc = fields.Float(
        string="Số phép còn lại năm trước",
        readonly=True,
        help="Số ngày phép còn lại vào cuối năm trước, được hệ thống tự động lưu vào ngày 01/01 hàng năm.",
    )
    nam_chot_con_lai = fields.Integer(
        string="Năm chốt",
        readonly=True,
        help="Năm tương ứng với giá trị Số phép còn lại năm trước.",
    )
    monthly_paid_leave_cap = fields.Integer(
        string="Hạn mức phép có lương / tháng",
        help=(
            "Số ngày phép có lương tối đa trong một tháng dành riêng cho nhân viên này. "
            "Bỏ trống để dùng mặc định toàn hệ thống (3 ngày). "
            "Chỉ SALE ADMIN (Job Position) và quản trị hệ thống được phép chỉnh."
        ),
        tracking=True,
    )
    can_edit_monthly_paid_leave_cap = fields.Boolean(
        compute="_compute_can_edit_monthly_paid_leave_cap",
    )

    @api.depends_context("uid")
    def _compute_can_edit_monthly_paid_leave_cap(self):
        allowed = self.env["hr.employee"]._monthly_paid_leave_cap_editor_allowed()
        for emp in self:
            emp.can_edit_monthly_paid_leave_cap = allowed

    @api.model
    def _monthly_paid_leave_cap_editor_allowed(self):
        """True khi user hiện tại có quyền chỉnh `monthly_paid_leave_cap`."""
        user = self.env.user
        if user._is_superuser() or user.has_group("base.group_system"):
            return True
        emp = user.sudo().employee_id
        job_name = (emp.job_id.name or "").strip().casefold() if emp else ""
        return job_name == _MONTHLY_CAP_EDITOR_JOB_POSITION

    @api.constrains("monthly_paid_leave_cap")
    def _check_monthly_paid_leave_cap_positive(self):
        for emp in self:
            if emp.monthly_paid_leave_cap and emp.monthly_paid_leave_cap < 0:
                raise ValidationError(
                    _("Hạn mức phép có lương / tháng không được là số âm.")
                )

    @api.model
    def _monthly_leave_bonus_date(self):
        value = self.env.context.get(_MONTHLY_LEAVE_BONUS_DATE_CTX)
        return fields.Date.to_date(value) if value else fields.Date.context_today(self)

    def _blocks_departure_monthly_leave_bonus(self, bonus_date):
        self.ensure_one()
        departure_date = self.sudo().ngay_nghi_viec
        return bool(
            departure_date
            and departure_date.day < _DEPARTURE_MONTHLY_LEAVE_CUTOFF_DAY
            and (departure_date.year, departure_date.month)
            == (bonus_date.year, bonus_date.month)
        )

    def _blocks_monthly_leave_bonus(self, bonus_date):
        """Return True when a +1 monthly bonus must be skipped for ``bonus_date``."""
        self.ensure_one()
        return self._blocks_departure_monthly_leave_bonus(bonus_date)

    def _monthly_leave_bonus_eligible(self, bonus_date=None):
        """Whether this employee may receive a +1 monthly leave accrual."""
        self.ensure_one()
        bonus_date = bonus_date or self._monthly_leave_bonus_date()
        return not self._blocks_monthly_leave_bonus(bonus_date)

    def _apply_monthly_leave_bonus(self, bonus_date=None):
        """Add one paid-leave day to ``tong_so_phep`` when eligible."""
        bonus_date = bonus_date or self._monthly_leave_bonus_date()
        bonus_month = bonus_date.replace(day=1)
        ctx = {
            _MONTHLY_LEAVE_BONUS_DATE_CTX: bonus_date,
            _SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX: True,
            _SKIP_DEPARTURE_MONTHLY_LEAVE_REVERSAL_CTX: True,
        }
        for employee in self:
            if not employee._monthly_leave_bonus_eligible(bonus_date):
                continue
            new_total = (employee.tong_so_phep or 0.0) + 1.0
            employee.with_context(**ctx).write(
                {
                    "tong_so_phep": new_total,
                    "last_monthly_leave_bonus_date": bonus_month,
                }
            )

    def _reverse_departure_monthly_leave_bonus(self, bonus_date):
        """Remove a granted monthly +1 when departure is before day 20."""
        bonus_month = bonus_date.replace(day=1)
        for employee in self.sudo():
            departure_date = employee.ngay_nghi_viec
            if (
                not departure_date
                or departure_date.day >= _DEPARTURE_MONTHLY_LEAVE_CUTOFF_DAY
                or departure_date.replace(day=1) != bonus_month
                or employee.departure_monthly_leave_reversal_date == bonus_month
            ):
                continue

            employee.with_context(
                **{
                    _SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX: True,
                    _SKIP_DEPARTURE_MONTHLY_LEAVE_REVERSAL_CTX: True,
                }
            ).write(
                {
                    "tong_so_phep": (employee.tong_so_phep or 0.0) - 1.0,
                    "departure_monthly_leave_reversal_date": bonus_month,
                }
            )
            _logger.info(
                "Reversed monthly leave bonus for employee %s on %s-%02d",
                employee.id,
                bonus_month.year,
                bonus_month.month,
            )

    def _restore_departure_monthly_leave_reversal(self):
        """Undo the previous departure deduction before recalculating it."""
        for employee in self.sudo().filtered(
            "departure_monthly_leave_reversal_date"
        ):
            reversed_month = employee.departure_monthly_leave_reversal_date
            employee.with_context(
                **{
                    _SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX: True,
                    _SKIP_DEPARTURE_MONTHLY_LEAVE_REVERSAL_CTX: True,
                }
            ).write(
                {
                    "tong_so_phep": (employee.tong_so_phep or 0.0) + 1.0,
                    "departure_monthly_leave_reversal_date": False,
                }
            )
            _logger.info(
                "Restored departure leave deduction for employee %s from %s-%02d",
                employee.id,
                reversed_month.year,
                reversed_month.month,
            )

    def _sync_departure_monthly_leave_reversal(self, bonus_date):
        """Recalculate the departure deduction after its date is corrected."""
        self._restore_departure_monthly_leave_reversal()
        self._reverse_departure_monthly_leave_bonus(bonus_date)

    def _is_single_day_monthly_leave_bonus(self, new_total):
        self.ensure_one()
        return isinstance(new_total, (int, float)) and abs(
            new_total - (self.tong_so_phep or 0.0) - 1.0
        ) < 0.000001

    def write(self, vals):
        if (
            "tong_so_phep" in vals
            and not self.env.context.get(_SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX)
        ):
            bonus_date = self._monthly_leave_bonus_date()
            blocked_ids = self.sudo().filtered(
                lambda employee: employee._is_single_day_monthly_leave_bonus(
                    vals["tong_so_phep"]
                )
                and (
                    employee._blocks_monthly_leave_bonus(bonus_date)
                    or not employee._monthly_leave_bonus_eligible(bonus_date)
                )
            ).ids
            if blocked_ids:
                blocked = self.browse(blocked_ids)
                allowed = self - blocked
                result = True
                if allowed:
                    result = allowed.with_context(
                        **{_SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX: True}
                    ).write(vals)
                remaining_vals = dict(vals)
                remaining_vals.pop("tong_so_phep")
                if remaining_vals:
                    result = (
                        blocked.with_context(
                            **{_SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX: True}
                        ).write(remaining_vals)
                        and result
                    )
                _logger.info(
                    "Skipped monthly leave bonus for employees %s on %s-%02d",
                    blocked.ids,
                    bonus_date.year,
                    bonus_date.month,
                )
                return result

        if "monthly_paid_leave_cap" in vals:
            if not self._monthly_paid_leave_cap_editor_allowed():
                raise AccessError(
                    _(
                        "Chỉ SALE ADMIN hoặc quản trị viên hệ thống mới được phép "
                        "thay đổi Hạn mức phép có lương / tháng."
                    )
                )
        result = super().write(vals)
        if (
            "ngay_nghi_viec" in vals
            and not self.env.context.get(
                _SKIP_DEPARTURE_MONTHLY_LEAVE_REVERSAL_CTX
            )
        ):
            self._sync_departure_monthly_leave_reversal(
                self._monthly_leave_bonus_date()
            )
        return result

    @api.model
    def _summary_paid_leave_type_ids(self):
        """ID các loại phép có lương làm giảm quỹ: P1 và P2."""
        LeaveType = self.env["hr.leave.type"]
        if hasattr(LeaveType, "search_by_code"):
            try:
                paid_types = LeaveType
                for code in ("P1", "P2"):
                    paid_types |= LeaveType.search_by_code(code, limit=None)
                if paid_types:
                    return paid_types.ids
            except Exception:  # pragma: no cover
                _logger.debug(
                    "summary: cannot resolve paid leave types P1/P2", exc_info=True
                )
        return []

    @api.model
    def _summary_unpaid_leave_type_ids(self):
        """Compatibility fallback when P1/P2 code lookup is unavailable."""
        LeaveType = self.env["hr.leave.type"]
        if hasattr(LeaveType, "search_by_code"):
            try:
                o_types = LeaveType.search_by_code("O", limit=None)
                if o_types:
                    return o_types.ids
            except Exception:  # pragma: no cover
                _logger.debug(
                    "summary: cannot resolve Unpaid Leave (O) type", exc_info=True
                )
        return []

    @api.model
    def _time_off_summary_period_bounds(self, target_date=None):
        target_date = fields.Date.to_date(target_date) or fields.Date.context_today(self)
        return date(target_date.year, 1, 1), date(target_date.year, 12, 31)

    def _get_leave_days_used_for_summary(self, target_date=None):
        """Tổng ngày P1/P2 đang hiệu lực trong năm của ``target_date``.

        Tính cả đơn đang chờ duyệt; không tính O, đơn hủy hoặc đơn bị từ chối.
        """
        self.ensure_one()
        period_start, period_end = self._time_off_summary_period_bounds(target_date)
        domain = [
            ("employee_id", "=", self.id),
            ("state", "in", _LEAVES_BUDGET_STATES),
            ("request_date_from", ">=", period_start),
            ("request_date_from", "<=", period_end),
        ]
        paid_ids = self._summary_paid_leave_type_ids()
        if paid_ids:
            domain.append(("holiday_status_id", "in", paid_ids))
        else:
            unpaid_ids = self._summary_unpaid_leave_type_ids()
            if unpaid_ids:
                domain.append(("holiday_status_id", "not in", unpaid_ids))
        groups = self.env["hr.leave"].sudo()._read_group(
            domain=domain,
            aggregates=["number_of_days:sum"],
        )
        return groups[0][0] if groups else 0.0

    def _maternity_first_day_balance_bonus(self, target_date=None):
        self.ensure_one()
        license_date = getattr(self.sudo(), "thai_san_ngay_cap_phep", False)
        license_date = fields.Date.to_date(license_date) if license_date else False
        if not license_date or license_date.day != 1:
            return 0.0
        period_start, period_end = self._time_off_summary_period_bounds(target_date)
        return 1.0 if period_start <= license_date <= period_end else 0.0

    @api.depends("tong_so_phep", "thai_san_ngay_cap_phep")
    def _compute_time_off_summary(self):
        employees = self._employees_for_timeoff_summary_compute()
        if not employees:
            return
        employees = employees.with_context(**employees._timeoff_summary_privacy_context())
        if "hr.leave.type" not in self.env:
            for employee in employees:
                employee.da_su_dung = 0.0
                employee.con_lai = employee.tong_so_phep
            return
        for employee in employees:
            # Dùng cùng tập đơn đang chiếm quỹ với bộ chia P/P1/P2/O.
            leave_taken = employee._get_leave_days_used_for_summary()
            maternity_bonus = employee._maternity_first_day_balance_bonus()
            raw_remaining = (
                (employee.tong_so_phep or 0.0) + maternity_bonus - leave_taken
            )
            employee.da_su_dung = leave_taken
            employee.con_lai = max(0.0, raw_remaining)
            if raw_remaining < 0:
                _logger.warning(
                    "Employee %s has historical negative leave balance: "
                    "budget=%s, paid_committed=%s",
                    employee.id,
                    employee.tong_so_phep or 0.0,
                    leave_taken,
                )

    @api.model
    def get_time_off_dashboard_data(self, target_date=None):
        """Làm mới số phép HRM trước khi dashboard đọc da_su_dung / con_lai."""
        employee = self._get_contextual_employee()
        if employee:
            employee.with_context(**employee._timeoff_summary_privacy_context())._compute_time_off_summary()
        ctx = employee._timeoff_summary_privacy_context() if employee else {
            "employees_no_timeoff_write": True,
            "employees_no_allowed_employee_ids": [],
        }
        ctx.update(self._timeoff_self_service_context())
        return super(HrEmployeeTimeoff, self.with_context(**ctx)).get_time_off_dashboard_data(
            target_date=target_date
        )

    @api.model
    def cron_snapshot_con_lai_prev_year(self):
        """Chốt phép năm trước rồi đưa quỹ phép của năm mới về 0."""
        today = fields.Date.context_today(self)
        prev_year = today.year - 1
        previous_year_date = date(prev_year, 12, 31)
        employees = self.sudo().search(
            [
                ("active", "=", True),
                ("nam_chot_con_lai", "!=", prev_year),
            ]
        )
        if not employees:
            return

        for emp in employees:
            leave_taken = emp._get_leave_days_used_for_summary(previous_year_date)
            emp.write(
                {
                    "con_lai_nam_truoc": max(
                        0.0, (emp.tong_so_phep or 0.0) - leave_taken
                    ),
                    "nam_chot_con_lai": prev_year,
                    "tong_so_phep": 0.0,
                }
            )
        tracked_leaves = self.env["hr.leave"].sudo().search(
            [
                "|",
                ("previous_year_balance_deduction", ">", 0),
                ("previous_year_balance_synced", "=", True),
            ]
        )
        if tracked_leaves:
            tracked_leaves.with_context(
                **{_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX: True}
            ).write(
                {
                    "previous_year_balance_deduction": 0.0,
                    "previous_year_balance_synced": False,
                }
            )
        _logger.info(
            "hr_employee_hrm_detail: rolled over leave balances for %d employees "
            "(previous year=%d)",
            len(employees),
            prev_year,
        )


class HrLeaveTimeOffSummary(models.Model):
    _inherit = "hr.leave"

    previous_year_balance_deduction = fields.Float(
        string="Khấu trừ phép năm trước",
        readonly=True,
        copy=False,
        help=(
            "Số ngày đơn này đã khấu trừ khỏi Số phép còn lại năm trước. "
            "Trường kỹ thuật được hệ thống tự động cập nhật."
        ),
    )
    previous_year_balance_synced = fields.Boolean(
        string="Đã đồng bộ phép năm trước",
        readonly=True,
        copy=False,
        help=(
            "Đánh dấu kỹ thuật cho đơn phát sinh sau khi đã chốt phép năm trước."
        ),
    )

    @api.model
    def _con_lai_zero_no_confirmation(self):
        return {
            "needs_confirmation": False,
            "title": "",
            "message": "",
        }

    @api.model
    def check_con_lai_zero_confirmation(self, res_id=False, vals=None):
        """Compatibility RPC: zero balance is converted to unpaid leave (O)."""
        return self._con_lai_zero_no_confirmation()

    def _recompute_employee_time_off_summary(self):
        employees = self.mapped("employee_id").filtered(lambda e: e.id)
        employees = employees.env["hr.employee"].search([("id", "in", employees.ids)])
        if employees:
            employees = employees._sudo_for_timeoff_access()
            employees.with_context(
                **employees._timeoff_summary_privacy_context()
            )._compute_time_off_summary()

    @api.model
    def _previous_year_balance_today(self):
        return fields.Date.context_today(self)

    def _is_previous_year_balance_leave(self):
        self.ensure_one()
        today = self._previous_year_balance_today()
        request_date = self.request_date_from
        employee = self.employee_id
        paid_type_ids = employee._summary_paid_leave_type_ids() if employee else []
        if paid_type_ids:
            is_paid_type = self.holiday_status_id.id in paid_type_ids
        else:
            unpaid_type_ids = (
                employee._summary_unpaid_leave_type_ids() if employee else []
            )
            is_paid_type = self.holiday_status_id.id not in unpaid_type_ids
        return bool(
            employee
            and request_date
            and request_date.year == today.year - 1
            and employee.nam_chot_con_lai == request_date.year
            and self.state in _LEAVES_BUDGET_STATES
            and is_paid_type
        )

    def _lock_previous_year_balance_employees(self):
        employee_ids = sorted(self.mapped("employee_id").ids)
        if employee_ids:
            self.env.cr.execute(
                "SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(employee_ids)],
            )
            self.env["hr.employee"].browse(employee_ids).invalidate_recordset(
                ["con_lai_nam_truoc"]
            )

    def _restore_previous_year_balance_deduction(self):
        leaves = self.sudo().filtered("previous_year_balance_deduction")
        if not leaves:
            return
        leaves._lock_previous_year_balance_employees()
        for leave in leaves.sorted("id"):
            deduction = max(0.0, leave.previous_year_balance_deduction)
            if deduction and leave.employee_id:
                employee = leave.employee_id
                employee.write(
                    {
                        "con_lai_nam_truoc": (
                            employee.con_lai_nam_truoc or 0.0
                        )
                        + deduction
                    }
                )
            leave.with_context(
                **{_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX: True}
            ).write({"previous_year_balance_deduction": 0.0})

    def _apply_previous_year_balance_deduction(self):
        leaves = self.sudo().filtered(
            lambda leave: leave._is_previous_year_balance_leave()
            and not leave.previous_year_balance_deduction
        )
        if not leaves:
            return
        leaves._lock_previous_year_balance_employees()
        for leave in leaves.sorted("id"):
            employee = leave.employee_id
            available = max(0.0, employee.con_lai_nam_truoc or 0.0)
            deduction = min(max(0.0, leave.number_of_days or 0.0), available)
            if not deduction:
                continue
            employee.write(
                {"con_lai_nam_truoc": available - deduction}
            )
            leave.with_context(
                **{_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX: True}
            ).write({"previous_year_balance_deduction": deduction})

    def _register_previous_year_balance_leaves(self):
        leaves = self.sudo().filtered(
            lambda leave: not leave.previous_year_balance_synced
            and leave._is_previous_year_balance_leave()
        )
        if leaves:
            leaves.with_context(
                **{_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX: True}
            ).write({"previous_year_balance_synced": True})
        return leaves

    @api.model
    def _rebalance_previous_year_balance(self, employee_ids):
        employee_ids = list(set(employee_ids))
        if not employee_ids:
            return
        tracked_leaves = self.sudo().search(
            [
                ("employee_id", "in", employee_ids),
                ("previous_year_balance_synced", "=", True),
            ],
            order="id",
        )
        tracked_leaves._restore_previous_year_balance_deduction()
        tracked_leaves._apply_previous_year_balance_deduction()

    @api.model
    def _con_lai_committed_days(
        self, employee, exclude_leave_ids=None, target_date=None
    ):
        """Ngày phép có lương đang chiếm quỹ trong năm của ``target_date``."""
        period_start, period_end = self.env[
            "hr.employee"
        ]._time_off_summary_period_bounds(target_date)
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "in", _LEAVES_BUDGET_STATES),
            ("request_date_from", ">=", period_start),
            ("request_date_from", "<=", period_end),
        ]
        paid_ids = employee._summary_paid_leave_type_ids()
        if paid_ids:
            domain.append(("holiday_status_id", "in", paid_ids))
        else:
            unpaid_ids = employee._summary_unpaid_leave_type_ids()
            if unpaid_ids:
                domain.append(("holiday_status_id", "not in", unpaid_ids))
        if exclude_leave_ids:
            domain.append(("id", "not in", list(exclude_leave_ids)))
        groups = self.sudo()._read_group(
            domain=domain,
            aggregates=["number_of_days:sum"],
        )
        return groups[0][0] if groups else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        registered = records._register_previous_year_balance_leaves()
        self._rebalance_previous_year_balance(registered.mapped("employee_id").ids)
        if not self.env.context.get("leave_fast_create"):
            records._recompute_employee_time_off_summary()
        return records

    def write(self, vals):
        previous_year_fields_changed = bool(
            {
                "employee_id",
                "holiday_status_id",
                "number_of_days",
                "request_date_from",
                "request_date_to",
                "date_from",
                "date_to",
                "state",
            }.intersection(vals)
        )
        sync_previous_year_balance = (
            previous_year_fields_changed
            and not self.env.context.get(_SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX)
        )
        previous_year_employee_ids = self.mapped("employee_id").ids
        if sync_previous_year_balance:
            self._restore_previous_year_balance_deduction()
        res = super().write(vals)
        summary_fields_changed = bool({
            "employee_id",
            "holiday_status_id",
            "number_of_days",
            "request_date_from",
            "request_date_to",
            "state",
        }.intersection(vals))
        terminal_state_change = vals.get("state") in ("refuse", "cancel")
        if summary_fields_changed and (
            terminal_state_change or not self.env.context.get("leave_fast_create")
        ):
            self._recompute_employee_time_off_summary()
        if sync_previous_year_balance:
            self._register_previous_year_balance_leaves()
            self._rebalance_previous_year_balance(
                previous_year_employee_ids + self.mapped("employee_id").ids
            )
        return res

    def unlink(self):
        sync_previous_year_balance = not self.env.context.get(
            _SKIP_PREVIOUS_YEAR_BALANCE_SYNC_CTX
        )
        employee_ids = self.mapped("employee_id").ids
        if sync_previous_year_balance:
            self._restore_previous_year_balance_deduction()
        result = super().unlink()
        if sync_previous_year_balance:
            self._rebalance_previous_year_balance(employee_ids)
        return result

    def action_confirm(self):
        res = super().action_confirm()
        self._recompute_employee_time_off_summary()
        return res

    def action_validate(self):
        res = super().action_validate()
        self._recompute_employee_time_off_summary()
        return res

    def action_refuse(self):
        res = super().action_refuse()
        self._recompute_employee_time_off_summary()
        return res

    def action_draft(self):
        res = super().action_draft()
        self._recompute_employee_time_off_summary()
        return res


class HrLeaveTypeTimeoff(models.Model):
    _inherit = "hr.leave.type"

    @api.model
    def get_allocation_data_request(self, target_date=None, hidden_allocations=True):
        ctx = self.env["hr.employee"]._timeoff_self_service_context()
        return super(HrLeaveTypeTimeoff, self.with_context(**ctx)).get_allocation_data_request(
            target_date=target_date,
            hidden_allocations=hidden_allocations,
        )
