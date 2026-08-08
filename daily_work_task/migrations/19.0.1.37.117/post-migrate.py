# -*- coding: utf-8 -*-
"""Gán web_icon an toàn (tránh ParseError khi XML đọc file icon trên lab)."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    menu = env.ref("daily_work_task.menu_daily_work_root", raise_if_not_found=False)
    if not menu:
        return

    icon = "daily_work_task,static/description/icon.png"
    # Chỉ SQL cho web_icon — tránh ir.ui.menu.write() đọc lại file (PermissionError trên lab)
    cr.execute(
        "UPDATE ir_ui_menu SET web_icon = %s WHERE id = %s",
        (icon, menu.id),
    )

    try:
        data = menu._compute_web_icon_data(icon)
    except Exception:
        data = False
    if data:
        try:
            menu.write({"web_icon_data": data})
        except Exception:
            pass
