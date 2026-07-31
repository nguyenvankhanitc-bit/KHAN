# -*- coding: utf-8 -*-
{
    "name": "LUG Enterprise Application Center",
    "version": "19.0.1.3.7",
    "category": "Productivity",
    "summary": "Cổng truy cập tập trung toàn bộ ứng dụng doanh nghiệp",
    "description": """
Enterprise Application Center
=============================
Một cổng truy cập — toàn bộ ứng dụng doanh nghiệp.

- Header thương hiệu + tìm kiếm ứng dụng
- Lưới ứng dụng theo nhóm chức năng
- Ứng dụng yêu thích và thông báo nội bộ
    """,
    "depends": [
        "web",
        "mail",
        "lug_permission",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/lug_app_center_announcement_data.xml",
        "views/lug_app_center_views.xml",
        "views/lug_app_center_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_app_center/static/src/app_center/lug_app_center.scss",
            "lug_app_center/static/src/app_center/lug_app_center.xml",
            "lug_app_center/static/src/app_center/lug_app_center.js",
            "lug_app_center/static/src/app_center/lug_app_center_home_patch.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "author": "LUG",
    "installable": True,
    "application": True,
    "auto_install": False,
}
