# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "HR Leave Analytics",
    "version": "19.0.1.0.1",
    "category": "Human Resources/Time Off",
    "summary": "Executive leave dashboard with KPIs, charts, and HR alerts for Sáng Tâm",
    "depends": [
        "hr_holidays",
        "hr_employee_hrm_detail",
        "hr_store",
        "hr_leave_type_mien",
        "spreadsheet_dashboard",
    ],
    "data": [
        "security/hr_leave_analytics_security.xml",
        "security/ir.model.access.csv",
        "data/dashboards.xml",
        "views/hr_leave_analytics_report_views.xml",
        "views/hr_leave_analytics_menus.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
