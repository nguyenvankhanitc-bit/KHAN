# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    stype = env.ref("lug_phan_he.service_type_linkq_hrm", raise_if_not_found=False)
    if stype and stype.active:
        stype.active = False
    menu = env.ref("lug_phan_he.menu_phan_he_linkq_hrm_root", raise_if_not_found=False)
    if menu and menu.active:
        menu.active = False
    env["phan.he.module.access"].search([])._ensure_module_lines()
