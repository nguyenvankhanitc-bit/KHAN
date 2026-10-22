# -*- coding: utf-8 -*-
"""Keep /odoo/du-an on shell; invalidate web assets after layout CSS fix."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    main = env.ref("lug_project.action_lug_project_main", raise_if_not_found=False)
    if main:
        main.write({"path": "du-an-list"})

    shell = env.ref("lug_project.action_lug_project_shell", raise_if_not_found=False)
    if shell:
        shell.write({"path": "du-an", "tag": "lug_project_shell", "name": "Dự án"})

    for xmlid in (
        "lug_project.menu_lug_project_shell",
        "project.menu_projects",
        "project.menu_main_pm",
    ):
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and shell:
            menu.action = shell

    # Force browsers to fetch rebuilt bundles after shell flex-direction fix.
    env["ir.attachment"].sudo().search(
        ["|", ("url", "=like", "%/web/assets/%"), ("name", "=like", "web.assets_%")]
    ).unlink()
