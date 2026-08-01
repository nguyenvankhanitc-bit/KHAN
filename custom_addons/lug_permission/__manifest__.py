# -*- coding: utf-8 -*-
{
    "name": "LUG Permission Center",
    "version": "19.0.1.0.33",
    "category": "Administration",
    "summary": "Centralized application permission management for Odoo",
    "description": """
LUG Permission Center
=====================
Independent permission layer: User → Group → Application → Permission → Data Scope.

- Manage app access and actions (View, Create, Edit, Delete, Approve, Export, Import, Print, Admin)
- Assign permissions to groups and users in bulk
- Hide application menus based on effective View permission
- Does not modify existing business tables (hr_employee, account_move, etc.)
    """,
    "depends": [
        "base",
        "hr",
        "hr_employee_self_only",
        "hr_employee_hrm_detail",
        "hr_holidays",
        "hr_leave_type_mien",
        "time_off_responsible_approval",
        "time_off_work_handover",
        "mail",
    ],
    "data": [
        "security/lug_permission_security.xml",
        "security/hr_leave_lug_scope_security.xml",
        "security/ir.model.access.csv",
        "data/lug_app_data.xml",
        "data/employee_edit_defaults.xml",
        "data/res_users_views_cleanup.xml",
        "views/lug_app_views.xml",
        "views/lug_group_views.xml",
        "views/res_users_views.xml",
        "views/lug_permission_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_permission/static/src/lug_systray_patch.js",
        ],
    },
    "license": "LGPL-3",
    "author": "Custom",
    "installable": True,
    "application": False,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
