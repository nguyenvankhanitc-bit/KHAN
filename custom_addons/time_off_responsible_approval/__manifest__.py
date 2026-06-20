{
    "name": "Time Off Responsible Approval",
    "version": "19.0.1.0.37",
    "category": "Human Resources",
    "summary": "Sequential HR-responsible and multi-step time off approval",
    "depends": [
        "hr_holidays",
        "hr_employee_multi_responsible",
        "hr_job_title_vn",
        "business_discuss_bots",
        "time_off_extra_approval",
    ],
    "post_init_hook": "post_init_hook",
    "data": [
        "data/ir_cron_data.xml",
        "security/hr_leave_extra_approver_rule.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
