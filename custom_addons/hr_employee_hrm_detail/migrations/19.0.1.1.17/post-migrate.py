# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xid in (
        "hr_employee_hrm_detail.hr_employee_rule_employees_no",
        "hr_employee_hrm_detail.hr_employee_public_rule_employees_no",
    ):
        rule = env.ref(xid, raise_if_not_found=False)
        if rule:
            rule.unlink()
            _logger.info("Deleted ir.rule %s", xid)
