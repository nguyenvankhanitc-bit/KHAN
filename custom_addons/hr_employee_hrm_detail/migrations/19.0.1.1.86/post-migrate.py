# -*- coding: utf-8 -*-
"""Re-sync ir.rule domain_force after switching 'assigned' policy to Mã bộ phận.

The hr.leave peer-read rule previously referenced res.users.assigned_employee_ids
(removed). Rewrite all managed rule domains from the current Python definitions
so safe_eval no longer hits the missing attribute.
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

    _sync_mien_access_rules(env)
    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.86: re-synced ir.rule domains "
        "(assigned -> ma_bo_phan)"
    )
