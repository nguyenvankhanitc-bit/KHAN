# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Time Off Matrix Excel Export",
    "version": "19.0.1.2.9",
    "category": "Human Resources/Time Off",
    "summary": "Export time off matrix and store leave form (Excel)",
    "depends": [
        "hr_holidays",
        "web",
        "hr_employee_hrm_detail",
        "hr_job_title_vn",
        "time_off_responsible_approval",
        "time_off_work_handover",
        "time_off_extra_approval",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/hr_leave_matrix_export_wizard_views.xml",
        "wizard/hr_leave_store_export_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_leave_matrix_export/static/src/matrix_export/export_all_matrix_patch.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
