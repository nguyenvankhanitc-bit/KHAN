# -*- coding: utf-8 -*-


def _set_app_center_as_home(env):
    """Đặt Enterprise Application Center làm trang chủ cho mọi user nội bộ."""
    action = env.ref("lug_app_center.action_lug_app_center", raise_if_not_found=False)
    if not action:
        return
    users = env["res.users"].sudo().search([
        ("share", "=", False),
        ("active", "=", True),
    ])
    users.write({"action_id": action.id})


def post_init_hook(env):
    _set_app_center_as_home(env)
