# -*- coding: utf-8 -*-
"""Migrate EMP_* visibility groups -> res.users.visibility_policy.

Mapping (preserves the v83 per-user state):
- HR Administrator / EMP_ALL  -> 'all'
- EMP_OFFICE / EMP_STORE      -> 'region' (same Miền)
- otherwise                   -> 'self'
The EMP_* groups/privileges/category are removed automatically as orphan
records (their XML definitions were deleted from the module).
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.hr_employee_hrm_detail.migration_schema import (
    ensure_res_users_visibility_schema,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    ensure_res_users_visibility_schema(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.hr_employee_hrm_detail.hooks import _sync_mien_access_rules

    g_all = env.ref("hr_employee_hrm_detail.group_emp_all", raise_if_not_found=False)
    g_office = env.ref("hr_employee_hrm_detail.group_emp_office", raise_if_not_found=False)
    g_store = env.ref("hr_employee_hrm_detail.group_emp_store", raise_if_not_found=False)

    users = env["res.users"].search([("share", "=", False), ("id", "!=", SUPERUSER_ID)])

    # Recompute the stored org helper fields used by the policy domains.
    for fname in ("employee_department_id", "employee_mien", "employee_ma_bo_phan_id"):
        env.add_to_compute(env["res.users"]._fields[fname], users)
    env["res.users"].flush_model(
        ["employee_department_id", "employee_mien", "employee_ma_bo_phan_id"]
    )

    for user in users:
        groups = user.all_group_ids
        if user.has_group("hr.group_hr_manager") or (g_all and g_all in groups):
            policy = "all"
        elif (g_office and g_office in groups) or (g_store and g_store in groups):
            policy = "region"
        else:
            policy = "self"
        user.visibility_policy = policy

    _sync_mien_access_rules(env)
    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.84: migrated %s users to visibility_policy",
        len(users),
    )
