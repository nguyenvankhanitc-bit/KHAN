# -*- coding: utf-8 -*-
{
    "name": "Quản lý dịch vụ",
    "version": "19.0.2.75.0",
    "category": "Operations",
    "summary": "Quản lý dịch vụ: Internet, Camera, Máy chấm công, LinkQ HRM, LinkQ NB, Máy chủ",
    "description": """
Quản lý dịch vụ
===============
* 1 app trên App Center: Quản lý dịch vụ
* Bên trong gồm 6 phân hệ: Internet, Camera, Máy chấm công, LinkQ HRM, LinkQ NB, Máy chủ
* Hub chọn dịch vụ + dashboard / hợp đồng / thanh toán theo từng phân hệ
* Phân quyền theo nhóm (giống Nhóm quyền LUG): Users + Xem/Thêm/Sửa/Xóa…
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "hr",
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
        "views/phan_he_app_actions.xml",
        "views/phan_he_hub_action.xml",
        "views/phan_he_access_views.xml",
        "views/phan_he_access_action.xml",
        "data/phan_he_access_group_data.xml",
        "views/phan_he_menus.xml",
        "data/phan_he_clear_submenu_icons.xml",
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_phan_he/static/src/hub/phan_he_hub.scss",
            "lug_phan_he/static/src/hub/phan_he_hub.js",
            "lug_phan_he/static/src/hub/phan_he_hub.xml",
            "lug_phan_he/static/src/access/phan_he_access_matrix.js",
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
