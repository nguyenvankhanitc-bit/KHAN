# -*- coding: utf-8 -*-
"""Remove Employees privilege 'No' group and related record rules."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

EMPLOYEES_NO_RULE_XMLIDS = (
    "hr_employee_hrm_detail.hr_employee_rule_employees_no",
    "hr_employee_hrm_detail.hr_employee_public_rule_employees_no",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    no = env.ref("hr_employee_self_only.group_hr_employees_no", raise_if_not_found=False)
    if not no:
        return

    for xid in EMPLOYEES_NO_RULE_XMLIDS:
        rule = env.ref(xid, raise_if_not_found=False)
        if rule:
            rule.unlink()
            _logger.info("Deleted ir.rule %s", xid)

    env["ir.rule"].search([("groups", "in", no.id)]).unlink()

    users = env["res.users"].search([("group_ids", "in", no.id)])
    if users:
        users.write({"group_ids": [(3, no.id)]})
        _logger.info("Removed group_hr_employees_no from %s users", len(users))

    no.unlink()
    _logger.info("Deleted group_hr_employees_no")
    env.registry.clear_cache()
