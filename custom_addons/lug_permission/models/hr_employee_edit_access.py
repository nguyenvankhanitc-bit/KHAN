# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _lug_employee_legacy_mien(self):
        self.ensure_one()
        emp = self.sudo()
        if emp.mien_zone_id and (emp.mien_zone_id.legacy_mien or "").strip():
            return (emp.mien_zone_id.legacy_mien or "").strip()
        if emp.mien:
            return (emp.mien or "").strip()
        if emp.ma_bo_phan_id and emp.ma_bo_phan_id.mien:
            return (emp.ma_bo_phan_id.mien or "").strip()
        if emp.employee_visibility == "office":
            return "VP"
        return ""

    def _lug_is_employee_profile_edit_allowed(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if self.env.su or user.has_group("base.group_system") or user.has_group(
            "hr.group_hr_manager"
        ):
            return True
        allowed = user.lug_allowed_employee_edit_legacy_miens()
        if allowed is None:
            return True
        own_emp_id = user.sudo().employee_id.id if user.sudo().employee_id else False
        if self.id == own_emp_id:
            return True
        return self._lug_employee_legacy_mien() in allowed

    def _lug_check_employee_profile_edit_access(self):
        user = self.env.user
        if self.env.su or self.env.context.get("skip_lug_employee_profile_edit_check"):
            return
        forbidden = self.filtered(
            lambda e: not e._lug_is_employee_profile_edit_allowed(user)
        )
        if forbidden:
            raise AccessError(
                "Bạn không có quyền chỉnh sửa hồ sơ nhân viên ở Miền này."
            )

    @api.depends_context("uid")
    def _compute_employee_form_force_readonly_ui(self):
        super()._compute_employee_form_force_readonly_ui()
        user = self.env.user
        if user.has_group("base.group_system") or user.has_group("hr.group_hr_manager"):
            return
        if user.lug_allowed_employee_edit_legacy_miens() is None:
            return
        for employee in self:
            if employee.employee_form_force_readonly_ui:
                continue
            if not employee._lug_is_employee_profile_edit_allowed(user):
                employee.employee_form_force_readonly_ui = True

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._lug_check_employee_profile_edit_access()
        return employees

    def write(self, vals):
        self._lug_check_employee_profile_edit_access()
        return super().write(vals)


class HrVersion(models.Model):
    _inherit = "hr.version"

    def _lug_related_employees_for_profile_check(self):
        employee_ids = []
        for version in self.sudo():
            if version.employee_id:
                employee_ids.append(version.employee_id.id)
        if not employee_ids:
            employee_ids = self.env["hr.employee"].sudo().search(
                [("version_id", "in", self.ids)]
            ).ids
        # Use the real user env for access checks (not sudo).
        return self.env["hr.employee"].browse(employee_ids)

    def _lug_check_version_profile_edit_access(self):
        employees = self._lug_related_employees_for_profile_check()
        if employees:
            employees._lug_check_employee_profile_edit_access()

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._lug_check_version_profile_edit_access()
        return versions

    def write(self, vals):
        self._lug_check_version_profile_edit_access()
        return super().write(vals)

