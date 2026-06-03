# -*- coding: utf-8 -*-
"""Ensure Employees=No record rules exist; remove obsolete broken mien rules."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

BROKEN_RULE_XMLIDS = (
    "hr_employee_hrm_detail.hr_employee_mien_access_rule",
    "hr_employee_hrm_detail.hr_employee_public_mien_access_rule",
)

EMPLOYEES_NO_DOMAIN = (
    "['|', ('user_id', '=', user.id), ('id', '=', user.employee_id.id)]"
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    IrRule = env["ir.rule"]

    for xid in BROKEN_RULE_XMLIDS:
        rule = env.ref(xid, raise_if_not_found=False)
        if rule:
            _logger.info("Removing broken rule %s", xid)
            rule.unlink()

    for xid in (
        "hr_employee_hrm_detail.hr_employee_rule_employees_no",
        "hr_employee_hrm_detail.hr_employee_public_rule_employees_no",
    ):
        rule = env.ref(xid, raise_if_not_found=False)
        if rule and rule.domain_force != EMPLOYEES_NO_DOMAIN:
            rule.write({"domain_force": EMPLOYEES_NO_DOMAIN})
            _logger.info("Updated domain on %s", xid)

    env.registry.clear_cache()
