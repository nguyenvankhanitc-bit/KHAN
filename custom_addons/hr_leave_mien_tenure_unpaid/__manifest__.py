# -*- coding: utf-8 -*-
{
    "name": "Time Off — Miền tenure unpaid (O)",
    "version": "19.0.1.0.16",
    "category": "Human Resources",
    "summary": "Bắt buộc (O) khi chưa đủ 4 năm hoặc nghỉ trùng ngày lễ (Bắc, Nam, ĐTT)",
    "description": """
        Nhân viên có Miền thuộc Bắc, Nam hoặc ĐTT (hr_employee_hrm_detail):

        * Từ **Ngày vào làm** tới ngày hiện tại **đủ 4 năm** → tạo đơn Time Off bình thường
          (trừ khi chọn ngày trùng **Public Holiday**).
        * **Chưa đủ 4 năm** (hoặc chưa có ngày vào làm) → mọi đơn Time Off bắt buộc loại
          **Nghỉ không lương (O)**.
        * **Đủ 4 năm** nhưng khoảng nghỉ có ngày trùng **Public Holiday** → bắt buộc
          **Nghỉ không lương (O)**.
        * Cộng **+1 Tổng số phép** mỗi tháng (miền **Bắc / Nam / ĐTT**):
          **Ngày bổ nhiệm** phải là **ngày 1**; **Nhóm trưởng** thêm điều kiện đủ
          **4 năm** từ **Ngày vào làm**; chức danh khác không xét thâm niên.
        * Quy tắc bắt buộc **(O)** khi chưa đủ 4 năm hoặc nghỉ trùng ngày lễ vẫn chỉ
          áp dụng cho chức danh **Nhóm trưởng**.
    """,
    "depends": [
        "hr_holidays",
        "hr_employee_hrm_detail",
        "hr_leave_type_mien",
    ],
    "data": [
        "data/ir_cron.xml",
        "views/hr_leave_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
