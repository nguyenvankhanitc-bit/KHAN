# -*- coding: utf-8 -*-
"""Remove duplicate Edit Employee Profile 'No' group (placeholder covers Không)."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    edit_no = env.ref(
        "hr_employee_self_only.group_hr_employee_edit_no",
        raise_if_not_found=False,
    )
    if edit_no:
        users = env["res.users"].search([("group_ids", "in", edit_no.id)])
        if users:
            users.write({"group_ids": [(3, edit_no.id)]})
            _logger.info(
                "Removed group_hr_employee_edit_no from %s users",
                len(users),
            )
        edit_no.unlink()
        _logger.info("Deleted group_hr_employee_edit_no")

    edit_priv = env.ref(
        "hr_employee_self_only.res_groups_privilege_employee_edit",
        raise_if_not_found=False,
    )
    if edit_priv:
        edit_priv.write({"placeholder": "Không"})

    leave_priv = env.ref(
        "hr_leave_delete_cancel.res_groups_privilege_leave_delete",
        raise_if_not_found=False,
    )
    if leave_priv:
        leave_priv.write({"placeholder": "Không"})

    env.registry.clear_cache()
