# -*- coding: utf-8 -*-
"""Full visibility_policy data repair after schema is guaranteed."""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.hr_employee_hrm_detail.migration_schema import (
    ensure_res_users_visibility_schema,
)

_logger = logging.getLogger(__name__)

_ORG_FIELDS = (
    "employee_ma_bo_phan_id",
    "employee_department_id",
    "employee_mien",
)


def migrate(cr, version):
    ensure_res_users_visibility_schema(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.hr_employee_hrm_detail.hooks import (
        _sync_mien_access_rules,
        _sync_user_visibility_policy,
    )

    users = env["res.users"].search([("share", "=", False)])
    Users = env["res.users"]
    for fname in _ORG_FIELDS:
        if fname in Users._fields:
            env.add_to_compute(Users._fields[fname], users)
    env["res.users"].flush_model(list(_ORG_FIELDS))

    # Default policy for users still NULL after partial deploys.
    null_policy = users.filtered(lambda u: not u.visibility_policy)
    if null_policy:
        _sync_user_visibility_policy(env, null_policy)

    _sync_mien_access_rules(env)

    # Fix stale hr.leave rule still referencing removed fields.
    stale = env["ir.rule"].search([
        "|",
        ("domain_force", "ilike", "assigned_employee_ids"),
        ("domain_force", "ilike", "hr_user_workforce_scope"),
    ])
    if stale:
        _sync_mien_access_rules(env)
        _logger.warning(
            "hr_employee_hrm_detail 19.0.1.1.88: re-synced %s stale ir.rule(s)",
            len(stale),
        )

    try:
        env["hr.employee.public"].init()
    except Exception:
        _logger.exception(
            "hr_employee_hrm_detail 19.0.1.1.88: hr.employee.public.init skipped"
        )

    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.88: visibility schema + data repair OK "
        "(%s users)",
        len(users),
    )
