# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.hr_employee_hrm_detail.models.hr_employee_mien_rule_domains import (
    HR_EMPLOYEE_MIEN_RULE_DOMAIN,
    HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.add_to_compute(env["res.users"]._fields["hr_officer_mien_scope"], env["res.users"].search([]))
    env["res.users"].flush_model(["hr_officer_mien_scope"])

    for xid, domain in (
        ("hr_employee_hrm_detail.hr_employee_officer_mien_rule", HR_EMPLOYEE_MIEN_RULE_DOMAIN),
        ("hr_employee_hrm_detail.hr_employee_public_officer_mien_rule", HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN),
    ):
        rule = env.ref(xid, raise_if_not_found=False)
        if rule:
            rule.write({"domain_force": domain})
            _logger.info("Updated domain on %s", xid)

    env.registry.clear_cache()
