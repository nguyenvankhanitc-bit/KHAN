# -*- coding: utf-8 -*-
{
    "name": "Bản đồ vị trí nhân viên & Cửa hàng",
    "version": "19.0.1.0.11",
    "category": "Human Resources",
    "summary": "Định vị vị trí nhân viên và trực quan hóa mạng lưới cửa hàng trên OpenStreetMap (OWL & geopy)",
    "description": """
Bản đồ vị trí nhân viên & Cửa hàng
===================================
* Tự động trích xuất vị trí GPS của nhân viên khi thao tác webclient Odoo.
* Lưu tọa độ gần nhất và thời gian ghi nhận trên model hr.employee.
* Tự động tính toán tọa độ (vĩ độ, kinh độ) cửa hàng theo địa chỉ bằng thư viện geopy (Nominatim), hỗ trợ admin nhập tay.
* Giao diện Bản đồ tương tác OpenStreetMap bằng OWL 2 và Leaflet.js.
* Danh sách nhân viên bên cạnh; click vào nhân viên hiển thị vị trí nhân viên và mạng lưới đường nối (network rays) đến các cửa hàng trực thuộc kèm khoảng cách thực tế (km).
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "hr",
        "hr_store",
    ],
    "data": [
        "security/hr_employee_location_security.xml",
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/hr_store_views.xml",
        "views/res_users_views.xml",
        "views/action_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_employee_location/static/src/geolocation/geolocation_service.js",
            "hr_employee_location/static/src/map_workspace/employee_store_map.scss",
            "hr_employee_location/static/src/map_workspace/employee_store_map.xml",
            "hr_employee_location/static/src/map_workspace/employee_store_map.js",
        ],
    },
    "installable": True,
    "application": True,
}
