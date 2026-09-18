# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Xóa nhân viên mẫu Minh Anh và công việc gắn với họ."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Emp = env["daily.task.employee"].with_context(active_test=False)
    demo = Emp.search([("name", "ilike", "Minh Anh")])
    xml = env.ref("daily_work_task.emp_minh_anh", raise_if_not_found=False)
    if xml:
        demo |= xml
    if not demo:
        return
    env["daily.task"].with_context(active_test=False).search(
        [("assignee_id", "in", demo.ids)]
    ).unlink()
    demo.unlink()
