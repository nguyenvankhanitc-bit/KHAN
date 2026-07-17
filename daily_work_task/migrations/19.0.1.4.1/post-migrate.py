# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Đảm bảo mọi Internal User có quyền Nhân viên của module."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    group_user = env.ref("daily_work_task.group_daily_work_user", raise_if_not_found=False)
    base_user = env.ref("base.group_user", raise_if_not_found=False)
    if not group_user or not base_user:
        return
    if group_user not in base_user.implied_ids:
        base_user.write({"implied_ids": [(4, group_user.id)]})
    # gán trực tiếp cho user nội bộ hiện có (phòng khi implied chưa sync)
    users = env["res.users"].search([("share", "=", False), ("active", "=", True)])
    for user in users:
        if group_user not in user.group_ids and base_user in user.group_ids:
            user.write({"group_ids": [(4, group_user.id)]})
