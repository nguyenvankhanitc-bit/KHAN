# -*- coding: utf-8 -*-
"""Ensure res.users visibility columns exist BEFORE module load (Linux deploy safety)."""
import logging

from odoo.addons.hr_employee_hrm_detail.migration_schema import (
    ensure_res_users_visibility_schema,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    ensure_res_users_visibility_schema(cr)
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.88 pre-migrate: schema repair done"
    )
