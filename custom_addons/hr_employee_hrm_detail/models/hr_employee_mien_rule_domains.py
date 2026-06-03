# -*- coding: utf-8 -*-
"""domain_force strings for ir.rule (safe_eval, no custom methods)."""

MIEN_BND = ("Bắc", "Nam", "ĐTT")

SELF_DOMAIN = "['|', ('user_id', '=', user.id), ('id', '=', user.employee_id.id)]"


def staff_department_rule_domain(ma_bo_phan_field):
    return (
        f"({SELF_DOMAIN} if not user.employee_id.ma_bo_phan_id "
        f"else ['|', '|', ('{ma_bo_phan_field}', '=', user.employee_id.ma_bo_phan_id.id), "
        f"('user_id', '=', user.id), ('id', '=', user.employee_id.id)])"
    )


def officer_mien_rule_domain(mien_field, dept_field):
    vp = (
        "['|', '|', "
        f"('{mien_field}', 'in', ['VP']), "
        f"'&', ('{mien_field}', '=', False), ('{dept_field}', 'in', ['VP']), "
        "'|', ('user_id', '=', user.id), ('id', '=', user.employee_id.id)]"
    )
    bnd = (
        "['|', '|', "
        f"('{mien_field}', 'in', {list(MIEN_BND)!r}), "
        f"'&', ('{mien_field}', '=', False), ('{dept_field}', 'in', {list(MIEN_BND)!r}), "
        "'|', ('user_id', '=', user.id), ('id', '=', user.employee_id.id)]"
    )
    return (
        f"({vp} if user.hr_officer_mien_scope == 'vp' "
        f"else ({bnd} if user.hr_officer_mien_scope == 'bnd' "
        f"else {SELF_DOMAIN}))"
    )


def employee_access_rule_domain(mien_field, dept_mien_field, ma_bo_phan_field):
    staff = staff_department_rule_domain(ma_bo_phan_field)
    officer = officer_mien_rule_domain(mien_field, dept_mien_field)
    return (
        "[(1, '=', 1)] if user.has_group('hr.group_hr_manager') "
        "else "
        f"({staff}) if user.has_group('hr_employee_hrm_detail.group_hr_employees_staff') "
        "else "
        f"({officer}) if user.has_group('hr.group_hr_user') "
        "else [(1, '=', 1)]"
    )


HR_EMPLOYEE_MIEN_RULE_DOMAIN = employee_access_rule_domain(
    "mien", "ma_bo_phan_id.mien", "ma_bo_phan_id"
)
HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN = employee_access_rule_domain(
    "employee_id.mien",
    "employee_id.ma_bo_phan_id.mien",
    "employee_id.ma_bo_phan_id",
)
