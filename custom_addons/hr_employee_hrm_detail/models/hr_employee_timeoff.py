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
_SKIP_DEPARTURE_MONTHLY_LEAVE_CUTOFF_CTX = (
    "skip_departure_monthly_leave_cutoff"
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
        return super()._has_field_access(field, operation)

    def _employee_for_timeoff_calendar(self):
        """Sudo + self-service context for calendar helpers (mandatory/unusual days)."""
        if self.env.user.has_group("hr.group_hr_user"):
            return self
        return self._sudo_for_timeoff_access().with_context(
            **self._timeoff_self_service_context()
        )

    def _get_mandatory_days(self, start_date, end_date):
        return super(
            HrEmployeeTimeoff, self._employee_for_timeoff_calendar()
        )._get_mandatory_days(start_date, end_date)

    def _get_unusual_days(self, date_from, date_to=None):
        if self.env.user.has_group("hr.group_hr_user"):
            return super()._get_unusual_days(date_from, date_to)
        self = self._employee_for_timeoff_calendar().sudo()
        date_from_date = datetime.strptime(date_from, "%Y-%m-%d %H:%M:%S").date()
        date_to_date = (
            datetime.strptime(date_to, "%Y-%m-%d %H:%M:%S").date() if date_to else None
        )
        employee_versions = self.env["hr.version"].search(
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
        """Read version-linked employee fields for permitted time-off UI without HR officer."""
        if self.env.user.has_group("hr.group_hr_user"):
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
                and employee._blocks_departure_monthly_leave_bonus(bonus_date)
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
                    "Skipped monthly leave bonus for employees %s: departure "
                    "before day %s in %s-%02d",
                    blocked.ids,
                    _DEPARTURE_MONTHLY_LEAVE_CUTOFF_DAY,
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
        return super().write(vals)

    @api.model
    def _summary_paid_leave_type_ids(self):
        """ID các loại phép có lương làm giảm quỹ: chỉ P1 và P2."""
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
        groups = self.env["hr.leave"].sudo().read_group(
            domain=domain,
            fields=["number_of_days:sum"],
            groupby=[],
        )
        if not groups:
            return 0.0
        row = groups[0]
        # Odoo 19 read_group tráº£ vá» key number_of_days (khÃ´ng cÃ²n number_of_days_sum).
        return row.get("number_of_days_sum") or row.get("number_of_days") or 0.0

    @api.depends("tong_so_phep")
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
            # Dùng cùng tập đơn đang chiếm quỹ với bộ chia P1/P2/O.
            leave_taken = employee._get_leave_days_used_for_summary()
            raw_remaining = (employee.tong_so_phep or 0.0) - leave_taken
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
        """Chạy vào 01/01 hàng năm: lưu con_lai của năm vừa kết thúc vào con_lai_nam_truoc.

        Không reset tong_so_phep hay da_su_dung — HR tự xử lý việc đó.
        """
        today = fields.Date.context_today(self)
        prev_year = today.year - 1
        previous_year_date = date(prev_year, 12, 31)
        employees = self.sudo().search([("active", "=", True)])
        if not employees:
            return

        for emp in employees:
            leave_taken = emp._get_leave_days_used_for_summary(previous_year_date)
            emp.write({
                "con_lai_nam_truoc": max(
                    0.0, (emp.tong_so_phep or 0.0) - leave_taken
                ),
                "nam_chot_con_lai": prev_year,
            })
        _logger.info(
            "hr_employee_hrm_detail: snapshotted con_lai for %d employees (year=%d)",
            len(employees),
            prev_year,
        )


class HrLeaveTimeOffSummary(models.Model):
    _inherit = "hr.leave"

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
        groups = self.sudo().read_group(
            domain=domain,
            fields=["number_of_days:sum"],
            groupby=[],
        )
        if not groups:
            return 0.0
        row = groups[0]
        return row.get("number_of_days_sum") or row.get("number_of_days") or 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("leave_fast_create"):
            records._recompute_employee_time_off_summary()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("leave_fast_create") and {
            "employee_id",
            "holiday_status_id",
            "number_of_days",
            "request_date_from",
            "request_date_to",
            "state",
        }.intersection(vals):
            self._recompute_employee_time_off_summary()
        return res

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
