{
    "name": "Time Off Dashboard — Department on Popup",
    "version": "19.0.1.0.14",
    "category": "Human Resources",
    "summary": "HRM ID, department code, and leave reason on time-off popups (dashboard and overview)",
    "depends": ["hr_holidays", "hr_employee_hrm_detail", "time_off_extra_approval"],
    "data": [
        "views/hr_leave_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_leave_dashboard_department/static/src/scss/hr_leave_employee_row.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
