# Part of Odoo. See LICENSE file for full copyright and licensing details.

{

    "name": "HR Leave Analytics",

    "version": "19.0.1.1.2",

    "post_init_hook": "post_init_hook",

    "category": "Human Resources/Time Off",

    "summary": "Dashboard nghỉ phép theo miền, cửa hàng và cảnh báo HR cho Sáng Tâm",

    "depends": [

        "hr_holidays",

        "hr_employee_hrm_detail",

        "hr_store",

        "hr_leave_type_mien",

        "hr_job_title_vn",

        "lug_permission",

        "spreadsheet_dashboard",

    ],

    "data": [

        "security/hr_leave_analytics_groups.xml",

        "security/hr_leave_analytics_manager_implied.xml",

        "security/hr_leave_analytics_security.xml",

        "security/ir.model.access.csv",

        "data/hr_leave_analytics_user_groups.xml",

        "data/dashboards.xml",

        "views/hr_leave_analytics_report_views.xml",

        "views/hr_leave_analytics_summary_views.xml",

        "views/hr_leave_analytics_menus.xml",

        "views/res_users_views.xml",

    ],

    "assets": {

        "web.assets_backend": [

            "hr_leave_analytics/static/src/dashboard/leave_analytics_dashboard.scss",

            "hr_leave_analytics/static/src/dashboard/leave_analytics_dashboard.xml",

            "hr_leave_analytics/static/src/dashboard/leave_analytics_dashboard.js",

        ],

    },

    "license": "LGPL-3",

    "installable": True,

    "application": False,

}

