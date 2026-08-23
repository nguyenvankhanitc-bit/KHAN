# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Cấp mã cho dự án đã có trước khi cài module."""
    Project = env["project.project"].with_context(active_test=False)
    for project in Project.search([("lug_code", "in", [False, ""])]):
        project.lug_code = Project._lug_generate_code() or False
    Project.search([])._lug_ensure_stages()
    Project.search([])._lug_ensure_stage_lines()
