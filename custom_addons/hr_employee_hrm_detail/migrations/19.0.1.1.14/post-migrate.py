# -*- coding: utf-8 -*-
"""Fix ir.rule domain_force still referencing removed hr_employee_allowed_miens field."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DOMAIN_EMPLOYEE = "user._hr_employee_mien_access_rule_domain()"
DOMAIN_PUBLIC = "user._hr_employee_public_mien_access_rule_domain()"
OLD_MARKER = "hr_employee_allowed_miens"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Rule = env["ir.rule"]
    for xmlid, domain in (
        ("hr_employee_hrm_detail.hr_employee_mien_access_rule", DOMAIN_EMPLOYEE),
        ("hr_employee_hrm_detail.hr_employee_public_mien_access_rule", DOMAIN_PUBLIC),
    ):
        try:
            rule = env.ref(xmlid)
        except ValueError:
            continue
        if OLD_MARKER in (rule.domain_force or "") or rule.domain_force != domain:
            _logger.info("Fixing domain_force on %s", xmlid)
            rule.write({"domain_force": domain})
    env.registry.clear_cache()
