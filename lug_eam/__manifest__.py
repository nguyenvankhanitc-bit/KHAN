# -*- coding: utf-8 -*-
{
    "name": "Quản lý tài sản",
    "version": "19.0.3.11.0",
    "category": "Operations/Maintenance",
    "summary": "EAM + CMMS — tài sản, phiếu nhập/xuất kho, bảo trì, dashboard",
    "description": """
Quản lý tài sản (EAM / CMMS)
============================
- PHIẾU NHẬP MUA (NM)
- PHIẾU XUẤT KHO (PX): xuất kho → nhập kho, người nhận, lý do, in PDF
    """,
    "author": "LUG",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "maintenance",
        "hr",
    ],
    "data": [
        "security/eam_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/eam_category_seed.xml",
        "data/eam_warehouse_seed.xml",
        "data/lug_app_data.xml",
        "views/eam_brand_views.xml",
        "views/eam_model_views.xml",
        "views/maintenance_equipment_category_views.xml",
        "views/maintenance_equipment_views.xml",
        "views/eam_asset_history_views.xml",
        "views/eam_transaction_views.xml",
        "views/eam_warehouse_views.xml",
        "views/eam_inventory_views.xml",
        "views/eam_maintenance_views.xml",
        "views/eam_dashboard_views.xml",
        "report/eam_label_report.xml",
        "report/eam_purchase_receipt_report.xml",
        "report/eam_stock_issue_report.xml",
        "views/eam_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_eam/static/src/scss/eam_asset_form.scss",
            "lug_eam/static/src/dashboard/eam_dashboard.js",
            "lug_eam/static/src/dashboard/eam_dashboard.xml",
            "lug_eam/static/src/dashboard/eam_dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
