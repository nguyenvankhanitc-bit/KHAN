# -*- coding: utf-8 -*-
"""Legacy workforce_group sync — superseded by visibility_policy (safe no-op)."""
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

    Users = env["res.users"]
    users = Users.search([])
    if "hr_user_workforce_scope" in Users._fields:
        env.add_to_compute(Users._fields["hr_user_workforce_scope"], users)
        Users.flush_model(["hr_user_workforce_scope"])
    _sync_mien_access_rules(env)
    try:
        env["hr.employee.public"].init()
    except Exception:
        pass
    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.72: legacy migration completed safely"
    )
