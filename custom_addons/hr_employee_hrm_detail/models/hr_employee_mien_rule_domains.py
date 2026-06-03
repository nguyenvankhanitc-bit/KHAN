# -*- coding: utf-8 -*-
"""domain_force strings for ir.rule (safe_eval, no custom methods)."""

MIEN_BND = ("Bắc", "Nam", "ĐTT")

SELF_DOMAIN = "['|', ('user_id', '=', user.id), ('id', '=', user.employee_id.id)]"


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
        "[(1, '=', 1)] if user.has_group('hr.group_hr_manager') "
        "or not user.has_group('hr.group_hr_user') "
        f"else ({vp} if user.hr_officer_mien_scope == 'vp' "
        f"else ({bnd} if user.hr_officer_mien_scope == 'bnd' "
        f"else {SELF_DOMAIN}))"
    )


HR_EMPLOYEE_MIEN_RULE_DOMAIN = officer_mien_rule_domain("mien", "ma_bo_phan_id.mien")
HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN = officer_mien_rule_domain(
    "employee_id.mien", "employee_id.ma_bo_phan_id.mien"
)
