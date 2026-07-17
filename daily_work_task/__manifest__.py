# -*- coding: utf-8 -*-
{
    "name": "Quản lý công việc hàng ngày",
    "version": "19.0.1.37.6",
    "category": "Operations",
    "summary": "Kế hoạch công việc hàng ngày — Dashboard, Calendar, nhắc quá hạn",
    "description": """
Module độc lập quản lý công việc hàng ngày (theo mẫu Google Sheet / Web App).

Tính năng:
- Dashboard tổng quan: KPI, biểu đồ ưu tiên/trạng thái/quá hạn, 3 cột theo trạng thái
- Quản lý dữ liệu công việc (CRUD)
- Không gian làm việc nhân viên
- Công việc lặp lại: user khai báo mẫu, cron ~5h00 tự tạo việc mỗi ngày
- Giao việc: quản lý giao việc → hiện trong danh sách của nhân viên được giao
- Thông báo Discuss/Inbox/Activity khi được giao việc (OdooBot Giao việc)
- Phân quyền: Xem / Giao việc / Sửa / Xóa (User A xem B, User C giao cho B, User D toàn quyền)
- Tổng công việc trong tháng (bảng dạng Excel) + xuất file .xlsx
- Báo cáo tổng theo phòng ban / nhân viên + xuất Excel
- Phân quyền Báo cáo tổng theo phòng ban (tích phòng ban được xem)
- Báo cáo hiệu suất tháng (cây cấp quản lý + đánh giá) + phân quyền riêng
- Calendar To Do List (Fluent / Card UI)
- Việc quá hạn + cập nhật trạng thái trực tiếp
- Gửi mail giục quá hạn (thủ công + cron hàng ngày)
- Danh sách nhân viên (tên + email)

Không phụ thuộc / không sửa module gốc hay module custom khác.
    """,
    "depends": ["base", "mail", "hr"],
    "data": [
        "security/daily_work_security.xml",
        "security/ir.model.access.csv",
        "data/mail_template_data.xml",
        "data/assign_notify_data.xml",
        "data/cron_data.xml",
        "data/sample_data.xml",
        "wizard/send_overdue_mail_views.xml",
        "views/daily_task_views.xml",
        "views/daily_task_employee_views.xml",
        "views/daily_task_dashboard_views.xml",
        "views/daily_task_access_views.xml",
        "views/daily_task_report_access_views.xml",
        "views/daily_task_performance_access_views.xml",
        "views/daily_task_work_group_views.xml",
        "views/daily_task_recurring_views.xml",
        "views/daily_work_notebook_views.xml",
        "views/daily_task_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "daily_work_task/static/src/dashboard/daily_work_dashboard.scss",
            "daily_work_task/static/src/dashboard/daily_work_dashboard.xml",
            "daily_work_task/static/src/dashboard/daily_work_dashboard.js",
            "daily_work_task/static/src/task_manager/daily_work_task_manager.scss",
            "daily_work_task/static/src/task_manager/daily_work_task_manager.xml",
            "daily_work_task/static/src/task_manager/daily_work_task_manager.js",
            "daily_work_task/static/src/employee_ws/daily_work_employee_ws.scss",
            "daily_work_task/static/src/employee_ws/daily_work_employee_ws.xml",
            "daily_work_task/static/src/employee_ws/daily_work_employee_ws.js",
            "daily_work_task/static/src/assign_task/daily_work_assign.scss",
            "daily_work_task/static/src/assign_task/daily_work_assign.xml",
            "daily_work_task/static/src/assign_task/daily_work_assign.js",
            "daily_work_task/static/src/viewer/daily_work_viewer.scss",
            "daily_work_task/static/src/viewer/daily_work_viewer.xml",
            "daily_work_task/static/src/viewer/daily_work_viewer.js",
            "daily_work_task/static/src/summary_report/daily_work_summary_report.scss",
            "daily_work_task/static/src/summary_report/daily_work_summary_report.xml",
            "daily_work_task/static/src/summary_report/daily_work_summary_report.js",
            "daily_work_task/static/src/performance_report/daily_work_performance_report.scss",
            "daily_work_task/static/src/performance_report/daily_work_performance_report.xml",
            "daily_work_task/static/src/performance_report/daily_work_performance_report.js",
            "daily_work_task/static/lib/html2canvas.min.js",
            "daily_work_task/static/src/report_overview/daily_work_report_overview.scss",
            "daily_work_task/static/src/report_overview/daily_work_report_overview.xml",
            "daily_work_task/static/src/report_overview/daily_work_report_overview.js",
            "daily_work_task/static/src/report_access/daily_task_report_access.scss",
            "daily_work_task/static/src/calendar/daily_work_calendar.scss",
            "daily_work_task/static/src/calendar/daily_work_calendar.xml",
            "daily_work_task/static/src/calendar/daily_work_calendar.js",
            "daily_work_task/static/src/notebook/daily_work_notebook.scss",
            "daily_work_task/static/src/notebook/daily_work_notebook.xml",
            "daily_work_task/static/src/notebook/daily_work_notebook.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "author": "LUG",
    "installable": True,
    "application": True,
    "auto_install": False,
}
