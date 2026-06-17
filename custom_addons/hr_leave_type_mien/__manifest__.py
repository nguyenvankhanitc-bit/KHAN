# -*- coding: utf-8 -*-
{
    "name": "Phân chia ngày nghỉ",
    "version": "19.0.1.0.41",
    "category": "Human Resources",
    "summary": "Gán và sắp xếp loại ngày nghỉ theo từng Miền",
    "description": """
        Cấu hình loại ngày nghỉ (Time Off Types) áp dụng cho từng Miền
        (Bắc, Nam, ĐTT, VP) và thứ tự hiển thị khi nhân viên đăng ký nghỉ.
    """,
    "depends": [
        "hr_holidays",
        "hr_employee_hrm_detail",
        "time_off_responsible_approval",
    ],
    "data": [
        "data/cleanup_views.xml",
        "data/cleanup_old_model.xml",
        "security/ir.model.access.csv",
        "views/hr_leave_mien_config_views.xml",
        "views/hr_leave_type_views.xml",
        "views/hr_leave_views.xml",
        "views/hr_leave_dashboard_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
