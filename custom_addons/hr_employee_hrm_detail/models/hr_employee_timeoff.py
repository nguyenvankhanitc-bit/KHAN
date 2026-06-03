import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

# Chỉ trừ phép khi đơn đã duyệt xong (Approved), không trừ khi còn chờ duyệt.
_LEAVES_DEDUCT_STATES = ("validate",)
# Đơn đang "chiếm chỗ" trong ngân sách Còn lại (chưa hủy/từ chối).
_LEAVES_BUDGET_STATES = ("confirm", "validate1", "validate")
_CON_LAI_ZERO_CONFIRMED_CTX = "con_lai_zero_confirmed"
_SKIP_CON_LAI_ZERO_CHECK_CTX = "skip_con_lai_zero_check"
_SKIP_CON_LAI_NEGATIVE_CHECK_CTX = "skip_con_lai_negative_check"
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

    @api.model
    def _get_contextual_employee(self):
        ctx = self.env.context
        for key in ("employee_id", "default_employee_id"):
            if ctx.get(key) is not None:
                employee = self._search_accessible_employee(ctx.get(key))
                if employee:
                    return employee
        return self.env.user.employee_id

    def get_mandatory_days(self, start_date, end_date):
        if self:
            self = self.env["hr.employee"].search([("id", "in", self.ids)])
        return super().get_mandatory_days(start_date, end_date)

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

    def write(self, vals):
        if "monthly_paid_leave_cap" in vals:
            if not self._monthly_paid_leave_cap_editor_allowed():
                raise AccessError(
                    _(
                        "Chỉ SALE ADMIN hoặc quản trị viên hệ thống mới được phép "
                        "thay đổi Hạn mức phép có lương / tháng."
                    )
                )
        return super().write(vals)

    def _get_leave_days_used_for_summary(self):
        """Tổng ngày nghỉ đã được phê duyệt (state = validate)."""
        self.ensure_one()
        groups = self.env["hr.leave"].sudo().read_group(
            domain=[
                ("employee_id", "=", self.id),
                ("state", "in", _LEAVES_DEDUCT_STATES),
            ],
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
        if "hr.leave.type" not in self.env:
            for employee in self:
                employee.da_su_dung = 0.0
                employee.con_lai = employee.tong_so_phep
            return
        for employee in self:
            # Chá»‰ Ä‘Æ¡n validate; khÃ´ng dÃ¹ng virtual_leaves_taken (Odoo cÃ³ thá»ƒ tÃ­nh cáº£ Ä‘Æ¡n chá» duyá»‡t).
            leave_taken = employee._get_leave_days_used_for_summary()
            employee.da_su_dung = leave_taken
            employee.con_lai = (employee.tong_so_phep or 0.0) - leave_taken

    @api.model
    def get_time_off_dashboard_data(self, target_date=None):
        """Làm mới số phép HRM trước khi dashboard đọc da_su_dung / con_lai."""
        employee = self._get_contextual_employee()
        ctx = {
            "employees_no_timeoff_write": True,
            "employees_no_allowed_employee_ids": [employee.id] if employee else [],
        }
        employee = employee.sudo().with_context(**ctx)
        if employee:
            employee._compute_time_off_summary()
        return super(HrEmployeeTimeoff, self.with_context(**ctx)).get_time_off_dashboard_data(
            target_date=target_date
        )

    @api.model
    def cron_snapshot_con_lai_prev_year(self):
        """Chạy vào 01/01 hàng năm: lưu con_lai của năm vừa kết thúc vào con_lai_nam_truoc.

        Không reset tong_so_phep hay da_su_dung — HR tự xử lý việc đó.
        """
        prev_year = date.today().year - 1
        employees = self.sudo().search([("active", "=", True)])
        if not employees:
            return

        # Refresh computed balances to make sure values reflect reality.
        employees._compute_time_off_summary()

        for emp in employees:
            emp.write({
                "con_lai_nam_truoc": emp.con_lai,
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
    def _employee_id_from_preview_vals(self, vals, leave=None):
        val = (vals or {}).get("employee_id")
        if val in (False, None) and leave:
            return leave.employee_id.id
        if isinstance(val, models.Model):
            return val.id
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    @api.model
    def check_con_lai_zero_confirmation(self, res_id=False, vals=None):
        """RPC cho UI: cáº£nh bÃ¡o khi cÃ²n láº¡i â‰¤ 0 trÆ°á»›c khi lÆ°u Ä‘Æ¡n (má»i loáº¡i nghá»‰)."""
        if self.env.context.get(_SKIP_CON_LAI_ZERO_CHECK_CTX) or self.env.context.get(
            _CON_LAI_ZERO_CONFIRMED_CTX
        ):
            return self._con_lai_zero_no_confirmation()

        vals = vals or {}
        leave = self.env["hr.leave"]
        if res_id:
            leave = self.browse(res_id).exists()
            if leave:
                leave.check_access("read")
        else:
            self.check_access("create")

        employee_id = self._employee_id_from_preview_vals(
            vals, leave if res_id and leave else None
        )
        if not employee_id:
            employee_id = self.env.user.employee_id.id
        if not employee_id:
            return self._con_lai_zero_no_confirmation()

        emp = self.env["hr.employee"].browse(employee_id)
        emp.with_context(
            employees_no_timeoff_write=True,
            employees_no_allowed_employee_ids=[employee_id],
        )._compute_time_off_summary()
        if (emp.con_lai or 0.0) > 0:
            return self._con_lai_zero_no_confirmation()

        return {
            "needs_confirmation": True,
            "title": _("Cảnh báo hết ngày phép"),
            "message": _("Bạn đang hết ngày phép, có chắc chắn muốn tiếp tục không?"),
        }

    def _recompute_employee_time_off_summary(self):
        employees = self.mapped("employee_id").filtered(lambda e: e.id)
        if employees:
            employees._compute_time_off_summary()

    @api.model
    def _con_lai_negative_check_skipped(self):
        ctx = self.env.context
        return bool(
            ctx.get(_SKIP_CON_LAI_NEGATIVE_CHECK_CTX)
            or ctx.get(_SKIP_CON_LAI_ZERO_CHECK_CTX)
            or ctx.get("leave_fast_create")
        )

    @api.model
    def _con_lai_unpaid_leave_type_ids(self):
        """ID các loại phép không tính vào ngân sách Còn lại (Unpaid Leave (O))."""
        unpaid_ids = set()
        LeaveType = self.env["hr.leave.type"]
        if hasattr(LeaveType, "search_by_code"):
            try:
                # Mọi loại phép có mã (O) — gồm «Nghỉ không lương (O)» của từng Miền.
                o_types = LeaveType.search_by_code("O", limit=None)
                if o_types:
                    unpaid_ids.update(o_types.ids)
            except Exception:  # pragma: no cover - bảo vệ khi cấu hình thiếu
                _logger.debug("con_lai: cannot resolve Unpaid Leave (O) type", exc_info=True)
        unpaid_ids.update(
            LeaveType.sudo().search([("requires_allocation", "=", False)]).ids
        )
        return list(unpaid_ids)

    @api.model
    def _con_lai_committed_days(self, employee, exclude_leave_ids=None):
        """Tổng số ngày phép tính phí (loại trừ O / unpaid) đang chiếm chỗ."""
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "in", _LEAVES_BUDGET_STATES),
        ]
        unpaid_ids = self._con_lai_unpaid_leave_type_ids()
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

    @api.model
    def _coerce_id_from_value(self, value):
        if isinstance(value, models.Model):
            return value.id
        if isinstance(value, (list, tuple)) and value:
            return value[0]
        return value

    @api.model
    def _is_unpaid_leave_type(self, leave_type_id):
        if not leave_type_id:
            return False
        return leave_type_id in self._con_lai_unpaid_leave_type_ids()

    @api.model
    def _vals_days_for_negative_check(self, vals, leave=None):
        if not vals:
            return leave.number_of_days if leave else 0.0
        days = vals.get("number_of_days")
        if days is not None:
            return days or 0.0
        return leave.number_of_days if leave else 0.0

    @api.model
    def _assert_con_lai_not_negative(self, employee, projected_days, exclude_leave_ids=None):
        """Chặn cứng khi đơn sẽ kéo Còn lại < 0 (==0 vẫn cho phép)."""
        if not employee or projected_days <= 0:
            return
        committed = self._con_lai_committed_days(
            employee, exclude_leave_ids=exclude_leave_ids
        )
        budget = employee.tong_so_phep or 0.0
        if budget - committed - projected_days < 0:
            raise ValidationError(
                _(
                    "Không thể tạo đơn nghỉ: Số phép Còn lại của %(name)s sẽ bị âm.\n"
                    "Tổng phép: %(budget).2f — Đang sử dụng: %(used).2f — Đơn này: %(new).2f"
                )
                % {
                    "name": employee.name or employee.display_name or "",
                    "budget": budget,
                    "used": committed,
                    "new": projected_days,
                }
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not self._con_lai_negative_check_skipped():
            Employee = self.env["hr.employee"]
            additions = {}
            for vals in vals_list:
                emp_id = self._coerce_id_from_value(vals.get("employee_id"))
                if not emp_id:
                    continue
                lt_id = self._coerce_id_from_value(vals.get("holiday_status_id"))
                if self._is_unpaid_leave_type(lt_id):
                    continue
                days = self._vals_days_for_negative_check(vals)
                if days <= 0:
                    continue
                additions[emp_id] = additions.get(emp_id, 0.0) + days
            for emp_id, projected in additions.items():
                employee = Employee.browse(emp_id)
                if not employee.exists():
                    continue
                self._assert_con_lai_not_negative(employee, projected)
        records = super().create(vals_list)
        if not self.env.context.get("leave_fast_create"):
            records._recompute_employee_time_off_summary()
        return records

    def write(self, vals):
        if (
            not self._con_lai_negative_check_skipped()
            and {"employee_id", "number_of_days", "holiday_status_id"}.intersection(vals)
        ):
            Employee = self.env["hr.employee"]
            for leave in self:
                emp_id = self._coerce_id_from_value(
                    vals.get("employee_id")
                ) or leave.employee_id.id
                if not emp_id:
                    continue
                lt_id = self._coerce_id_from_value(vals.get("holiday_status_id")) or (
                    leave.holiday_status_id.id if leave.holiday_status_id else False
                )
                if self._is_unpaid_leave_type(lt_id):
                    continue
                projected = self._vals_days_for_negative_check(vals, leave=leave)
                if projected <= 0:
                    continue
                employee = Employee.browse(emp_id)
                if not employee.exists():
                    continue
                self._assert_con_lai_not_negative(
                    employee, projected, exclude_leave_ids=[leave.id]
                )
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
