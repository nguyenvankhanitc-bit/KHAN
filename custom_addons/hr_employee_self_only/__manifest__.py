{
    "name": "HR Employee Self Only Access",
    "version": "19.0.1.2.2",
    "category": "Human Resources",
    "summary": "Employee privacy helpers for time off and managed departments",
    "depends": ["hr", "hr_holidays", "hr_employee_managed_departments"],
    "data": [
        "security/hr_employee_privilege_groups.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "assets": {
        "web.assets_backend": [
            "hr_employee_self_only/static/src/scss/hr_employee_form_privacy_readonly.scss",
            "hr_employee_self_only/static/src/js/hr_employee_form_privacy_readonly.js",
            "hr_employee_self_only/static/src/js/x2many_managed_departments_privacy.js",
            "hr_employee_self_only/static/src/js/list_renderer_no_open_row_class.js",
        ],
    },
}
