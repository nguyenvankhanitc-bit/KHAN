# -*- coding: utf-8 -*-
"""Restore /odoo/du-an to OWL shell (workspace-compatible left sidebar)."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Free path du-an from act_window first.
    main = env.ref("lug_project.action_lug_project_main", raise_if_not_found=False)
    if main:
        main.write({"path": "du-an-list", "name": "Dự án (danh sách)"})

    shell = env.ref("lug_project.action_lug_project_shell", raise_if_not_found=False)
    if shell:
        shell.write({"path": "du-an", "name": "Dự án", "tag": "lug_project_shell"})

    # Default menus open the shell.
    for xmlid in ("lug_project.menu_lug_project_shell", "project.menu_projects"):
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and shell:
            menu.action = shell
