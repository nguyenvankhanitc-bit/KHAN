# -*- coding: utf-8 -*-

from .models.hr_employee_mien_rule_domains import (
    HR_EMPLOYEE_MIEN_RULE_DOMAIN,
    HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN,
)


def _sync_mien_access_rules(env):
    rules = (
        ("hr_employee_hrm_detail.hr_employee_officer_mien_rule", HR_EMPLOYEE_MIEN_RULE_DOMAIN),
        (
            "hr_employee_hrm_detail.hr_employee_public_officer_mien_rule",
            HR_EMPLOYEE_PUBLIC_MIEN_RULE_DOMAIN,
        ),
    )
    for xid, domain in rules:
        rule = env.ref(xid, raise_if_not_found=False)
        if rule and rule.domain_force != domain:
            rule.write({"domain_force": domain})


def post_init_hook(env):
    env.add_to_compute(env["res.users"]._fields["hr_officer_mien_scope"], env["res.users"].search([]))
    env["res.users"].flush_model(["hr_officer_mien_scope"])
    _sync_mien_access_rules(env)
    env.registry.clear_cache()
