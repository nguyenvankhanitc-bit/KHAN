# -*- coding: utf-8 -*-
"""Restore Project menus after blank-screen fix.

Earlier versions pointed project.menu_main_pm / menu_projects at the custom
client action, which could leave the native Project navbar with an empty pane.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Root Project app: no direct action (first child "Tổng quan" opens shell).
    root = env.ref("project.menu_main_pm", raise_if_not_found=False)
    if root:
        root.action = False

    # Native "Dự án" list menu → standard act_window again.
    projects_menu = env.ref("project.menu_projects", raise_if_not_found=False)
    projects_action = env.ref("project.open_view_project_all", raise_if_not_found=False)
    if projects_menu and projects_action:
        projects_menu.action = projects_action

    shell = env.ref("lug_project.action_lug_project_shell", raise_if_not_found=False)
    if shell and "path" in shell._fields:
        shell.path = "du-an"
