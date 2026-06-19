# -*- coding: utf-8 -*-

from .migration_schema import ensure_res_users_visibility_schema
from .models.hr_employee_mien_rule_domains import (
    HR_EMPLOYEE_MIEN_RULE_DOMAIN,
    HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN,
    HR_LEAVE_PEER_READ_DOMAIN,
    HR_VERSION_MIEN_RULE_DOMAIN,
)


def _sync_mien_access_rules(env):
    rules = (
        ("hr_employee_hrm_detail.hr_employee_officer_mien_rule", HR_EMPLOYEE_MIEN_RULE_DOMAIN),
        (
            "hr_employee_hrm_detail.hr_employee_public_officer_mien_rule",
            HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN,
        ),
        (
            "hr_employee_hrm_detail.hr_version_officer_mien_rule",
            HR_VERSION_MIEN_RULE_DOMAIN,
        ),
        (
            "hr_employee_hrm_detail.hr_leave_peer_read_rule",
            HR_LEAVE_PEER_READ_DOMAIN,
        ),
    )
    for xid, domain in rules:
        rule = env.ref(xid, raise_if_not_found=False)
        if rule and rule.domain_force != domain:
            rule.write({"domain_force": domain})


def _default_visibility_policy(user):
    """Suggested policy when none is set. Permission groups do NOT widen visibility:
    only HR Administrator implies full visibility. Staff with a region default to
    'region', everyone else to 'self'.
    """
    if user.has_group("hr.group_hr_manager"):
        return "all"
    emp = user.sudo().employee_id
    if emp and (emp.mien or (emp.ma_bo_phan_id.mien if emp.ma_bo_phan_id else False)):
        return "region"
    return "self"


def _sync_user_visibility_policy(env, users=None, force=False):
    """Populate visibility_policy for users that have none (or force reset)."""
    users = users or env["res.users"].search([("share", "=", False)])
    for user in users:
        if user.id == env.ref("base.user_root").id:
            continue
        if force or not user.visibility_policy:
            user.visibility_policy = _default_visibility_policy(user)


def post_init_hook(env):
    ensure_res_users_visibility_schema(env.cr)
    users = env["res.users"].search([])
    env.add_to_compute(env["res.users"]._fields["employee_ma_bo_phan_id"], users)
    env.add_to_compute(env["res.users"]._fields["employee_department_id"], users)
    env.add_to_compute(env["res.users"]._fields["employee_mien"], users)
    env["res.users"].flush_model(
        ["employee_ma_bo_phan_id", "employee_department_id", "employee_mien"]
    )
    _sync_user_visibility_policy(env, users)
    _sync_mien_access_rules(env)
    env["hr.employee.public"].init()
    env.registry.clear_cache()
