# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrLeave(models.Model):
    _inherit = "hr.leave"

    employee_id_hrm = fields.Char(
        string="ID HRM",
        compute="_compute_employee_hrm_display",
        readonly=True,
    )
    employee_ma_bo_phan = fields.Char(
        string="Mã bộ phận",
        compute="_compute_employee_hrm_display",
        readonly=True,
    )

    @api.depends("employee_id")
    def _compute_employee_hrm_display(self):
        for leave in self:
            employee = leave.employee_id.sudo()
            id_hrm = (getattr(employee, "id_hrm", None) or "").strip()
            leave.employee_id_hrm = f"ID {id_hrm}" if id_hrm else ""
            leave.employee_ma_bo_phan = (getattr(employee, "ma_bo_phan", None) or "").strip()

    def _leave_reason_from_vals(self, vals):
        return (vals.get("name") or vals.get("private_name") or "").strip()

    def _leave_reason_text(self, vals=None):
        self.ensure_one()
        if vals:
            reason = self._leave_reason_from_vals(vals)
            if reason:
                return reason
        reason = (self.sudo().private_name or "").strip()
        if not reason:
            reason = (self.name or "").strip()
        return reason

    def _can_persist_leave_reason(self):
        self.ensure_one()
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")
        employee_user = self.employee_id.user_id
        return bool(
            is_officer
            or self.user_id == self.env.user
            or employee_user == self.env.user
            or self.employee_id.leave_manager_id == self.env.user
        )

    def _inverse_description(self):
        for leave in self:
            if not leave._can_persist_leave_reason():
                continue
            reason = (leave.name or "").strip()
            if reason:
                leave.sudo().private_name = reason

    def _ensure_leave_reason_persisted(self, vals_list=None):
        for idx, leave in enumerate(self):
            vals = vals_list[idx] if vals_list and idx < len(vals_list) else {}
            reason = leave._leave_reason_text(vals)
            if not reason or not leave._can_persist_leave_reason():
                continue
            if reason != (leave.sudo().private_name or "").strip():
                leave.sudo().private_name = reason

    def _validate_leave_reason_required(self, vals_list=None):
        for idx, leave in enumerate(self):
            if leave.state != "confirm":
                continue
            vals = vals_list[idx] if vals_list and idx < len(vals_list) else {}
            if not leave._leave_reason_text(vals):
                raise ValidationError(_("Vui lòng nhập lý do nghỉ phép trước khi gửi đơn."))

    def _should_check_leave_reason(self, vals):
        if not vals:
            return False
        # Public-holiday create/write re-evaluates overlapping hr.leave rows via
        # sudo().write({'state': 'confirm'}) — not a user submit action.
        if self.env.su and set(vals.keys()) <= {"state"}:
            return False
        if self.env.context.get("skip_handover_constraints_on_leave_sync"):
            return False
        tracked = {
            "name",
            "private_name",
            "state",
            "holiday_status_id",
            "request_date_from",
            "request_date_to",
            "request_unit_half",
            "request_unit_hours",
            "handover_acceptance_ids",
            "skip_work_handover",
        }
        return bool(tracked & set(vals))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("leave_fast_create") and not self.env.context.get("import_file"):
            records._ensure_leave_reason_persisted(vals_list)
            records._validate_leave_reason_required(vals_list)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("leave_fast_create") or not self._should_check_leave_reason(vals):
            return res
        vals_list = [vals] * len(self)
        self._ensure_leave_reason_persisted(vals_list)
        self._validate_leave_reason_required(vals_list)
        return res
