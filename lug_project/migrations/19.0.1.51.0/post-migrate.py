# -*- coding: utf-8 -*-
"""Move /odoo/du-an to stable act_window; shell UI uses /odoo/du-an-ui."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Old client action must leave path du-an for the new act_window.
    shell = env.ref("lug_project.action_lug_project_shell", raise_if_not_found=False)
    if shell and shell._name == "ir.actions.client":
        shell.write({"path": "du-an-ui", "name": "Tổng quan dự án"})

    main = env.ref("lug_project.action_lug_project_main", raise_if_not_found=False)
    if main:
        main.path = "du-an"

    root = env.ref("project.menu_main_pm", raise_if_not_found=False)
    if root:
        root.action = False

    projects_menu = env.ref("project.menu_projects", raise_if_not_found=False)
    if projects_menu and main:
        projects_menu.action = main
