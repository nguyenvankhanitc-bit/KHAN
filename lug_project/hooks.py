# -*- coding: utf-8 -*-

from odoo import fields


def post_init_hook(env):
    """Cấp mã cho dự án đã có trước khi cài module."""
    Project = env["project.project"].with_context(active_test=False)
    used_codes = set()
    for project in Project.search([("lug_code", "in", [False, ""])]):
        code = Project._lug_generate_code(excluded_codes=used_codes) or False
        if code:
            used_codes.add(code)
            project.lug_code = code
            project.flush_recordset(["lug_code"])
    Project.search([])._lug_ensure_stages()
    Project.search([])._lug_ensure_stage_lines()
    today = fields.Date.context_today(Project)
    stale = Project.search([("active", "=", False), ("lug_archived_date", "=", False)])
    for rec in stale:
        rec.lug_archived_date = rec.write_date.date() if rec.write_date else today
