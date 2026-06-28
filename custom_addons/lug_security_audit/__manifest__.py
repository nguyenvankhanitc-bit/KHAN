# -*- coding: utf-8 -*-
{
    "name": "Lug Security",
    "version": "19.0.1.0.17",
    "post_init_hook": "post_init_hook",
    "category": "Administration",
    "summary": "Security Audit — phiên đăng nhập, thiết bị, tổng hợp và báo cáo",
    "description": """
Lug Security Audit — module độc lập theo dõi phiên đăng nhập,
thiết bị, tổng hợp ngày/tháng và báo cáo. Menu: Cài đặt → Lug Security.
    """,
    "depends": [
        "base",
        "web",
        "hr",
    ],
    "data": [
        "security/lug_security_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/lug_device_views.xml",
        "views/lug_user_session_views.xml",
        "views/lug_user_daily_summary_views.xml",
        "views/lug_user_month_summary_views.xml",
        "views/lug_security_dashboard_views.xml",
        "views/lug_security_session_list_views.xml",
        "views/lug_security_month_report_views.xml",
        "views/lug_security_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_security_audit/static/src/lug_security_heartbeat.js",
            "lug_security_audit/static/src/dashboard/lug_security_dashboard.scss",
            "lug_security_audit/static/src/dashboard/lug_donut_card.js",
            "lug_security_audit/static/src/dashboard/lug_security_dashboard.xml",
            "lug_security_audit/static/src/dashboard/lug_security_dashboard.js",
            "lug_security_audit/static/src/session_list/lug_session_list.xml",
            "lug_security_audit/static/src/session_list/lug_session_list.js",
            "lug_security_audit/static/src/month_report/lug_month_report.xml",
            "lug_security_audit/static/src/month_report/lug_month_report.js",
        ],
    },
    "license": "LGPL-3",
    "author": "LUG",
    "installable": True,
    "application": False,
    "auto_install": False,
}
