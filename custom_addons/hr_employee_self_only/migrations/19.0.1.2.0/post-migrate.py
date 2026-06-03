# -*- coding: utf-8 -*-
"""Grant Edit Employee Profile = Allowed to existing HR officers."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    allowed = env.ref(
        "hr_employee_self_only.group_hr_employee_edit_allowed",
        raise_if_not_found=False,
    )
    if not allowed:
        return

    hr_user = env.ref("hr.group_hr_user")
    hr_manager = env.ref("hr.group_hr_manager")
    users = env["res.users"].search([
        "|",
        ("group_ids", "in", hr_user.id),
        ("group_ids", "in", hr_manager.id),
    ])
    users_without = users.filtered(lambda u: allowed not in u.group_ids)
    if users_without:
        users_without.write({"group_ids": [(4, allowed.id)]})
        _logger.info(
            "Granted group_hr_employee_edit_allowed to %s users",
            len(users_without),
        )
    env.registry.clear_cache()
