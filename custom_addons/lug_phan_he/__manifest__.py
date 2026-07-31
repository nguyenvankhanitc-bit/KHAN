# -*- coding: utf-8 -*-
{
    "name": "Quản lý dịch vụ",
    "version": "19.0.2.48.0",
    "category": "Operations",
    "summary": "Quản lý dịch vụ enterprise: miền/khu vực, hợp đồng, thanh toán, chứng từ, dashboard, phân quyền",
    "description": """
Quản lý dịch vụ
===============
* Dashboard 8 KPI + cảnh báo
* Vận hành: Miền / Khu vực / Cửa hàng
* Hợp đồng & loại dịch vụ (Internet, Phần mềm, Điện thoại, Khác)
* Thanh toán + File thanh toán tháng + Hóa đơn + Đối soát
* Nhà cung cấp / Tài khoản ngân hàng
* Phân quyền theo tổ chức + cron cảnh báo
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "hr",
        "lug_permission",
    ],
    "data": [
        "security/phan_he_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/phan_he_service_type_data.xml",
        "data/lug_app_data.xml",
        "data/phan_he_demo.xml",
        "data/phan_he_lang_date.xml",
        "views/phan_he_views.xml",
        "views/phan_he_payment_file_views.xml",
        "views/phan_he_menus.xml",
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_phan_he/static/src/dashboard/phan_he_dashboard.scss",
            "lug_phan_he/static/src/dashboard/phan_he_dashboard.js",
            "lug_phan_he/static/src/dashboard/phan_he_dashboard.xml",
            "lug_phan_he/static/src/fields/ops_status_field.js",
            "lug_phan_he/static/src/fields/ops_status_field.xml",
            "lug_phan_he/static/src/tracking/phan_he_tracking.scss",
            "lug_phan_he/static/src/tracking/phan_he_tracking_list.js",
            "lug_phan_he/static/src/tracking/phan_he_tracking_list.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
