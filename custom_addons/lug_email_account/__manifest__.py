# -*- coding: utf-8 -*-
{
    "name": "Quản lý tài khoản email",
    "version": "19.0.1.9.2",
    "category": "Operations/Email",
    "summary": "Đăng ký và quản lý tài khoản email theo phòng ban, chức năng, mục đích sử dụng",
    "description": """
Quản lý tài khoản email
=======================
Sổ đăng ký tài khoản email doanh nghiệp theo mẫu:
STT, Ngày tạo, Phòng ban, Chức năng, Họ tên NV, Email,
Vị trí, Mục đích sử dụng, Đối tượng sử dụng, Trạng thái, Ghi chú.
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "hr",
        "lug_permission",
    ],
    "data": [
        "security/lug_email_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/lug_email_status_data.xml",
        "data/lug_app_data.xml",
        "views/lug_email_status_views.xml",
        "views/lug_email_account_views.xml",
        "views/lug_email_dashboard_views.xml",
        "views/lug_email_menus.xml",
        "data/lug_email_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_email_account/static/src/email_account_list/lug_email_account_list.scss",
            "lug_email_account/static/src/email_account_list/lug_email_account_list.js",
            "lug_email_account/static/src/email_account_list/lug_email_account_list.xml",
            "lug_email_account/static/src/dashboard/lug_email_dashboard.scss",
            "lug_email_account/static/src/dashboard/lug_email_dashboard.xml",
            "lug_email_account/static/src/dashboard/lug_email_dashboard.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
