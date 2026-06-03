# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _
from odoo.exceptions import AccessError


def _privacy_is_timeoff_bypass_allowed(env, employees=None, resources=None):
    """Allow limited writes for view-only HR users during own time-off flow."""
    if not env.context.get("employees_no_timeoff_write"):
        return False
    allowed_ids = set(env.context.get("employees_no_allowed_employee_ids") or [])
    if not allowed_ids:
        return True

    if employees is not None:
        return all(emp.id in allowed_ids for emp in employees)

    if resources is not None:
        linked = resources.filtered(lambda r: r.employee_id)
        return all(res.employee_id.id in allowed_ids for res in linked)
    return False


def _privacy_can_edit_employee_profile(env):
    """HR users with Edit Employee Profile = Allowed, or HR Administrator."""
    user = env.user
    if user._is_superuser():
        return True
    if user.has_group("hr.group_hr_manager"):
        return True
    return user.has_group("hr_employee_self_only.group_hr_employee_edit_allowed")


def _privacy_is_employee_edit_forbidden(env):
    """Chỉnh sửa hồ sơ = Không for HR officers (Chuyên viên without Allowed)."""
    if not env.user.has_group("hr.group_hr_user"):
        return False
    return not _privacy_can_edit_employee_profile(env)


def _privacy_can_view_personal_information(env):
    """View Personal Information = Allowed, or HR Administrator."""
    user = env.user
    if user._is_superuser():
        return True
    if user.has_group("hr.group_hr_manager"):
        return True
    return user.has_group("hr_employee_self_only.group_hr_employee_view_personal_allowed")


def _privacy_is_personal_tab_hidden(env):
    """Hide Personal tab when View Personal Information is not allowed."""
    return not _privacy_can_view_personal_information(env)


def _privacy_raise_if_employee_no_write(env, employees):
    """Edit Employee Profile = No: no create/write/unlink on hr.employee."""
    if not _privacy_is_employee_edit_forbidden(env):
        return
    if _privacy_is_timeoff_bypass_allowed(env, employees=employees):
        return
    if employees:
        raise AccessError(_("Bạn không có quyền chỉnh sửa hồ sơ nhân viên."))


def _privacy_raise_if_hr_version_no_write(env):
    """Edit Employee Profile = No: cannot change employee versions."""
    if _privacy_is_employee_edit_forbidden(env):
        raise AccessError(_("Bạn không có quyền chỉnh sửa hồ sơ nhân viên."))


def _privacy_raise_if_hr_employee_resource_no_write(env, resources):
    """Edit Employee Profile = No: cannot change resources linked to employees."""
    if not _privacy_is_employee_edit_forbidden(env):
        return
    if _privacy_is_timeoff_bypass_allowed(env, resources=resources):
        return
    if resources.filtered(lambda r: r.employee_id):
        raise AccessError(_("Bạn không có quyền chỉnh sửa hồ sơ nhân viên."))


def _privacy_raise_if_employee_create_forbidden(env):
    if not _privacy_is_employee_edit_forbidden(env):
        return
    raise AccessError(_("Bạn không có quyền tạo nhân viên."))
