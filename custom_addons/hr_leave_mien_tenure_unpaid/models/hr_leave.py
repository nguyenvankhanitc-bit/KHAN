# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

O_LEAVE_TYPE_CODE = "O"


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _get_tenure_unpaid_o_leave_type(self, selected=None, employee=None):
        if employee is None:
            employee = self.employee_id if self else False
        allowed_ids = self._mien_config_leave_type_ids(employee)
        return self.env["hr.leave.type"].leave_type_from_selection(
            selected, O_LEAVE_TYPE_CODE, allowed_ids=allowed_ids
        )

    def _employee_requires_mien_unpaid_o(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return False
        start = self._get_leave_start_date()
        end = self._get_leave_end_date() or start
        return employee._mien_unpaid_o_required(date_from=start, date_to=end)

    @api.depends(
        "employee_id",
        "employee_id.mien",
        "employee_id.ma_bo_phan_id.mien",
        "employee_id.ngay_vao_lam",
        "employee_id.job_id",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _compute_holiday_status_id_month_leave_type_locked(self):
        super()._compute_holiday_status_id_month_leave_type_locked()
        for leave in self:
            if leave._employee_requires_mien_unpaid_o():
                leave.holiday_status_id_month_leave_type_locked = True

    @api.model
    def _leave_type_domain_for_employee(
        self, employee, start_date=None, end_date=None, leave=None
    ):
        end_date = end_date or start_date
        if employee and employee._mien_unpaid_o_required(
            date_from=start_date, date_to=end_date
        ):
            o_type = self._get_tenure_unpaid_o_leave_type(employee=employee)
            base = list(self._leave_type_base_domain())
            if o_type:
                return ["&"] + base + [("id", "=", o_type.id)]
            return ["&"] + base + [("id", "in", [])]
        return super()._leave_type_domain_for_employee(
            employee,
            start_date=start_date,
            end_date=end_date,
            leave=leave,
        )

    @api.model
    def _monthly_leave_rule_kind(self, employee, start_date, leave=None, end_date=None):
        end_date = end_date or start_date
        if employee and employee._mien_unpaid_o_required(
            date_from=start_date, date_to=end_date
        ):
            return "o"
        return super()._monthly_leave_rule_kind(
            employee, start_date, leave=leave, end_date=end_date
        )

    def _monthly_mien_should_split(self, leave):
        if leave._employee_requires_mien_unpaid_o():
            return False
        return super()._monthly_mien_should_split(leave)

    @api.depends(
        "employee_id",
        "employee_id.mien",
        "employee_id.ma_bo_phan_id.mien",
        "employee_id.ngay_vao_lam",
        "employee_id.job_id",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _compute_mien_allowed_leave_type_ids(self):
        return super()._compute_mien_allowed_leave_type_ids()

    @api.constrains(
        "employee_id",
        "holiday_status_id",
        "request_date_from",
        "request_date_to",
        "date_from",
        "date_to",
    )
    def _check_mien_unpaid_leave_type(self):
        for leave in self:
            employee = leave.employee_id
            if not employee or not leave.holiday_status_id:
                continue
            if not leave._employee_requires_mien_unpaid_o():
                continue
            o_type = leave._get_tenure_unpaid_o_leave_type(leave.holiday_status_id)
            if not o_type:
                raise ValidationError(
                    _(
                        "Không tìm thấy loại ngày nghỉ có mã (O) trong tên "
                        "(ví dụ: «Nghỉ không lương (O)»). Vui lòng liên hệ HR."
                    )
                )
            if leave.holiday_status_id.id != o_type.id:
                mien = employee._get_leave_mien_for_rules()
                start = leave._get_leave_start_date()
                end = leave._get_leave_end_date() or start
                if employee._mien_tenure_unpaid_required():
                    join = employee.ngay_vao_lam
                    join_label = (
                        fields.Date.to_string(join) if join else _("chưa khai báo")
                    )
                    raise ValidationError(
                        _(
                            "Nhân viên miền %(mien)s chưa đủ 4 năm làm việc "
                            "(ngày vào làm: %(join)s). Chỉ được đăng ký loại "
                            "«%(required)s»."
                        )
                        % {
                            "mien": mien or "",
                            "join": join_label,
                            "required": o_type.display_name,
                        }
                    )
                if employee._mien_public_holiday_unpaid_required(start, end):
                    raise ValidationError(
                        _(
                            "Nhân viên miền %(mien)s: khoảng nghỉ có ngày trùng "
                            "ngày lễ (Public Holiday). Chỉ được đăng ký loại "
                            "«%(required)s»."
                        )
                        % {
                            "mien": mien or "",
                            "required": o_type.display_name,
                        }
                    )
