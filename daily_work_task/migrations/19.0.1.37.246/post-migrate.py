# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đổ user M2O cũ sang M2M tags trên daily.task.assign."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Assign = env["daily.task.assign"].sudo()
    if "assignee_user_ids" not in Assign._fields:
        return
    Assign.search([])._migrate_m2o_into_m2m()
