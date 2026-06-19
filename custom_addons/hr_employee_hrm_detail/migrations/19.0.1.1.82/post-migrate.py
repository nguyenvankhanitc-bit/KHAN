# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Chuyên viên HR thật (không phải CH/VP) — giữ EMP_ALL khi resync
HR_EMP_ALL_LOGINS = frozenset({
    "admin.lug@sangtam.com",
    "admin",
    "hr@sangtam.com",
    "anh.trinh@sangtam.com",
    "khan.nguyen@sangtam.com",
    "phuong.nguyen@sangtam.com",
    "test@sangtam.com",
})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.hr_employee_hrm_detail.hooks import _sync_user_visibility_policy

    group_all = env.ref("hr_employee_hrm_detail.group_emp_all", raise_if_not_found=False)
    supporter = env.ref("hr_employee_hrm_detail.group_hr_employees_supporter", raise_if_not_found=False)
    if group_all and supporter and group_all in supporter.implied_ids:
        supporter.write({"implied_ids": [(3, group_all.id)]})

    users = env["res.users"].search([("share", "=", False), ("id", "!=", SUPERUSER_ID)])
    _sync_user_visibility_policy(env, users)
    if group_all:
        for user in users:
            login = (user.login or "").lower()
            if login in HR_EMP_ALL_LOGINS and not user.has_group("hr.group_hr_manager"):
                user.write({"group_ids": [(4, group_all.id)]})
    env.registry.clear_cache()
    _logger.info(
        "hr_employee_hrm_detail 19.0.1.1.82: removed EMP_ALL from non-admin supporters"
    )
