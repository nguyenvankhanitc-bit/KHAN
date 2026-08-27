# -*- coding: utf-8 -*-
{
    "name": "Nhập dự án (custom Project)",
    "version": "19.0.1.40.2",
    "category": "Services/Project",
    "summary": "Bổ sung form nhập dự án trên app Project chuẩn Odoo",
    "description": """
Inherit app Project native — không tạo model dự án mới.

- Popup Tạo dự án: mã, loại, khách hàng, thời gian, quản lý, kế hoạch, tài liệu
- Form dự án đầy đủ: notebook A–E
- Tái dùng partner, PM, ngày, milestone, stage, chatter
    """,
    "author": "LUG",
    "license": "LGPL-3",
    "depends": [
        "project",
        "hr",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/project_stage_access.xml",
        "data/ir_sequence_data.xml",
        "data/project_type_data.xml",
        "data/project_phase_data.xml",
        "data/ir_cron_data.xml",
        "views/project_type_views.xml",
        "views/project_phase_views.xml",
        "views/project_stage_views.xml",
        "views/project_stage_line_views.xml",
        "views/project_project_views.xml",
        "views/project_shell_views.xml",
        "views/project_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lug_project/static/src/scss/lug_project.scss",
            "lug_project/static/src/list/lug_project_list.scss",
            "lug_project/static/src/list/lug_project_list.xml",
            "lug_project/static/src/list/lug_project_list.js",
            "lug_project/static/src/list/lug_project_list_fields.js",
            "lug_project/static/src/phases/lug_task_phases.scss",
            "lug_project/static/src/phases/lug_task_phases.xml",
            "lug_project/static/src/phases/lug_task_phases.js",
            "lug_project/static/src/scss/custom_fullwidth.scss",
            "lug_project/static/src/stages/lug_stage_cards.scss",
            "lug_project/static/src/stages/lug_stage_cards.xml",
            "lug_project/static/src/stages/lug_stage_cards.js",
            "lug_project/static/src/shell/lug_project_shell.scss",
            "lug_project/static/src/shell/lug_project_shell.xml",
            "lug_project/static/src/shell/lug_project_shell_boot.js",
            "lug_project/static/src/shell/lug_project_shell.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
