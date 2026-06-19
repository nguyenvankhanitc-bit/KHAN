# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.hr_employee_hrm_detail.hooks import _sync_mien_access_rules
from odoo.addons.hr_employee_hrm_detail.models.hr_employee import (
    MIEN_VP,
    VISIBILITY_ALL,
    VISIBILITY_OFFICE,
    VISIBILITY_STORE,
    _visibility_from_mien,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_employee' AND column_name = 'workforce_group'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE hr_employee DROP COLUMN workforce_group")
        _logger.info("hr_employee_hrm_detail: dropped hr_employee.workforce_group")

    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_mien_zone' AND column_name = 'workforce_group'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE hr_mien_zone DROP COLUMN workforce_group")

    employees = env["hr.employee"].with_context(active_test=False).search([])
    for employee in employees:
        visibility = employee.employee_visibility
        if visibility == VISIBILITY_ALL:
            continue
        expected = _visibility_from_mien(employee.mien)
        if expected and employee.employee_visibility != expected:
            employee.employee_visibility = expected

    zone_all = env.ref(
        "hr_employee_hrm_detail.mien_zone_all", raise_if_not_found=False
    )
    if not zone_all:
        zone_all = env["hr.mien.zone"].create(
            {
                "name": "Tất cả",
                "code": "all",
                "legacy_mien": "Tất cả",
                "is_assignable": True,
                "sequence": 40,
            }
        )

    users = env["res.users"].search([])
    Users = env["res.users"]
    if "hr_user_workforce_scope" in Users._fields:
        env.add_to_compute(Users._fields["hr_user_workforce_scope"], users)
        Users.flush_model(["hr_user_workforce_scope"])
    _sync_mien_access_rules(env)
    env["hr.employee.public"].init()
    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail: peer visibility by ma_bo_phan; VP without ma_bo_phan filter"
    )
