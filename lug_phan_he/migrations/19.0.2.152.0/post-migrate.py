# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["phan.he.module.access"].search([])._ensure_menu_lines()
    user = env["res.users"].search([("login", "=", "phuc.bui@sangtam.com")], limit=1)
    group = env.ref("lug_phan_he.group_linkq_schedule_user", raise_if_not_found=False)
    if user and group and group not in user.group_ids:
        user.write({"group_ids": [(4, group.id)]})
