# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Time Off — Daily Leave Report",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Time Off",
    "summary": "Daily leave listing under Management (Ngày nghỉ theo ngày)",
    "depends": [
        "hr_holidays",
        "hr_leave_type_mien",
        "hr_employee_hrm_detail",
        "hr_job_title_vn",
        "time_off_work_handover",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_leave_daily_report_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
