# -*- coding: utf-8 -*-
"""Recompute current-year leave balances after fixing the accounting period."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env["hr.employee"].with_context(active_test=False).search([])
    if not employees:
        return
    _logger.info(
        "hr_employee_hrm_detail: recomputing current-year leave balances for %d employees",
        len(employees),
    )
    employees.with_context(
        employees_no_timeoff_write=True,
        employees_no_allowed_employee_ids=employees.ids,
    )._compute_time_off_summary()
