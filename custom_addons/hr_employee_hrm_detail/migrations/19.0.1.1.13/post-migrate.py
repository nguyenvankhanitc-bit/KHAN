# -*- coding: utf-8 -*-
"""Fix ir.rule domain_force: replace hr_employee_allowed_miens with method calls."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DOMAIN_EMPLOYEE = "user._hr_employee_mien_access_rule_domain()"
DOMAIN_PUBLIC = "user._hr_employee_public_mien_access_rule_domain()"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    updates = (
        ("hr_employee_hrm_detail.hr_employee_mien_access_rule", DOMAIN_EMPLOYEE),
        ("hr_employee_hrm_detail.hr_employee_public_mien_access_rule", DOMAIN_PUBLIC),
    )
    for xmlid, domain in updates:
        try:
            rule = env.ref(xmlid)
        except ValueError:
            _logger.warning("Rule %s not found, skipping", xmlid)
            continue
        if rule.domain_force == domain:
            continue
        _logger.info("Updating %s domain_force", xmlid)
        rule.write({"domain_force": domain})
    env.registry.clear_cache()
