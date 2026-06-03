# -*- coding: utf-8 -*-
"""Remove broken ir.rule records; Miền access is enforced in ir.rule._compute_domain."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

RULE_XMLIDS = (
    "hr_employee_hrm_detail.hr_employee_mien_access_rule",
    "hr_employee_hrm_detail.hr_employee_public_mien_access_rule",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in RULE_XMLIDS:
        try:
            rule = env.ref(xmlid)
        except ValueError:
            continue
        _logger.info("Removing obsolete ir.rule %s", xmlid)
        rule.unlink()
    env.registry.clear_cache()
