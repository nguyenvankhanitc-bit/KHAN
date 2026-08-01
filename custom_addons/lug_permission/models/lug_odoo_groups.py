# -*- coding: utf-8 -*-
"""Map LUG application permissions to Odoo security groups."""

LUG_APP_ODOO_GROUPS = {
    "discuss": {},
    "calendar": {},
    "todo": {},
    "dashboards": {
        "view": ["spreadsheet_dashboard.group_dashboard_manager"],
    },
    "daily_work": {
        "view": ["daily_work_task.group_daily_work_user"],
        "create": ["daily_work_task.group_daily_work_assigner"],
        "edit": ["daily_work_task.group_daily_work_assigner"],
        "delete": ["daily_work_task.group_daily_work_manager"],
        "admin": ["daily_work_task.group_daily_work_manager"],
    },
    "ctkm": {
        "view": ["ctkm_core.group_ctkm_user"],
        "create": ["ctkm_core.group_ctkm_user"],
        "edit": ["ctkm_core.group_ctkm_user"],
        "admin": ["ctkm_core.group_ctkm_manager"],
    },
    "project": {
        "view": ["project.group_project_user"],
        "edit": ["project.group_project_user"],
        "create": ["project.group_project_user"],
        "delete": ["project.group_project_manager"],
        "admin": ["project.group_project_manager"],
    },
    "timesheets": {
        "view": ["hr_timesheet.group_hr_timesheet_user"],
        "create": ["hr_timesheet.group_hr_timesheet_user"],
        "edit": ["hr_timesheet.group_hr_timesheet_user"],
    },
    "hr": {
        "view": ["hr.group_hr_user"],
        "create": ["hr.group_hr_user"],
        "edit": ["hr.group_hr_user"],
        "delete": ["hr.group_hr_manager"],
        "admin": ["hr.group_hr_manager"],
    },
    "leave": {
        "view": ["hr_holidays.group_hr_holidays_user"],
        "create": ["hr_holidays.group_hr_holidays_user"],
        "edit": ["hr_holidays.group_hr_holidays_user"],
        "delete": ["hr_holidays.group_hr_holidays_manager"],
        "approve": ["hr_holidays.group_hr_holidays_responsible"],
        # Time Off Administrator: manage all requests, public holidays,
        # leave types, allocations (Configuration menu).
        "admin": ["hr_holidays.group_hr_holidays_manager"],
    },
    "attendance": {
        "view": ["hr_attendance.group_hr_attendance_user"],
        "create": ["hr_attendance.group_hr_attendance_officer"],
        "edit": ["hr_attendance.group_hr_attendance_officer"],
        "delete": ["hr_attendance.group_hr_attendance_manager"],
        "admin": ["hr_attendance.group_hr_attendance_manager"],
    },
    "gatepass": {
        "view": ["base.group_user"],
        "create": ["base.group_user"],
        "edit": ["base.group_user"],
        "approve": ["hr_attendance.group_hr_attendance_user"],
    },
    "fleet": {
        "view": ["fleet.fleet_group_user"],
        "edit": ["fleet.fleet_group_manager"],
        "admin": ["fleet.fleet_group_manager"],
    },
    "expense": {
        "view": ["hr_expense.group_hr_expense_user"],
        "create": ["hr_expense.group_hr_expense_user"],
        "edit": ["hr_expense.group_hr_expense_user"],
        "approve": ["hr_expense.group_hr_expense_team_approver"],
        "admin": ["hr_expense.group_hr_expense_manager"],
    },
    "invoice": {
        "view": ["account.group_account_readonly"],
        "create": ["account.group_account_invoice"],
        "edit": ["account.group_account_user"],
        "delete": ["account.group_account_manager"],
        "approve": ["account.group_account_manager"],
        "admin": ["account.group_account_manager"],
    },
    "event": {
        "view": ["event.group_event_user"],
        "edit": ["event.group_event_manager"],
        "admin": ["event.group_event_manager"],
    },
    "recruitment": {
        "view": ["hr_recruitment.group_hr_recruitment_user"],
        "edit": ["hr_recruitment.group_hr_recruitment_manager"],
        "admin": ["hr_recruitment.group_hr_recruitment_manager"],
    },
    "warehouse": {
        "view": ["stock.group_stock_user"],
        "edit": ["stock.group_stock_manager"],
        "admin": ["stock.group_stock_manager"],
    },
    "crm": {
        "view": ["sales_team.group_sale_salesman"],
        "edit": ["sales_team.group_sale_salesman_all_leads"],
        "approve": ["sales_team.group_sale_manager"],
        "admin": ["sales_team.group_sale_manager"],
    },
    "pos": {
        "view": ["point_of_sale.group_pos_user"],
        "edit": ["point_of_sale.group_pos_manager"],
        "admin": ["point_of_sale.group_pos_manager"],
    },
}

# Groups that hr_employee_hrm_detail may grant via user_role / app access.
ROLE_MANAGED_GROUP_XMLIDS = [
    "base.group_user",
    "hr.group_hr_user",
    "hr.group_hr_manager",
    "hr_holidays.group_hr_holidays_user",
    "hr_holidays.group_hr_holidays_responsible",
    "hr_holidays.group_hr_holidays_manager",
    "hr_attendance.group_hr_attendance_user",
    "hr_attendance.group_hr_attendance_officer",
    "hr_attendance.group_hr_attendance_manager",
    "hr_expense.group_hr_expense_user",
    "hr_expense.group_hr_expense_team_approver",
    "hr_expense.group_hr_expense_manager",
    "sales_team.group_sale_salesman",
    "sales_team.group_sale_salesman_all_leads",
    "sales_team.group_sale_manager",
    "point_of_sale.group_pos_user",
    "point_of_sale.group_pos_manager",
    "account.group_account_user",
    "account.group_account_manager",
    "account.group_account_readonly",
    "account.group_account_invoice",
    "hr_employee_hrm_detail.group_hr_employees_staff",
    "hr_employee_hrm_detail.group_hr_employees_supporter",
]

# Root menus always hidden for users under LUG enforcement (unless system).
LUG_ALWAYS_HIDDEN_MENU_XMLIDS = [
    "base.menu_administration",
    "base.menu_management",
    "lug_permission.menu_lug_permission_root",
]
