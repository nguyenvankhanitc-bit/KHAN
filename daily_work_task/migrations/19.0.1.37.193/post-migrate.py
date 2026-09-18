# -*- coding: utf-8 -*-

DEMO_NAMES = (
    "Lê Hoài An",
    "Minh Anh",
    "Dương Thu",
    "Quốc Bảo",
    "Ánh Dương",
    "Dũng IT",
)


def migrate(cr, version):
    """Xóa nhân viên/công việc mẫu (sample_data)."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Emp = env["daily.task.employee"].with_context(active_test=False)
    demo = Emp.search(
        [
            "|",
            ("email", "=", "emailcuanhanvien@gmail.com"),
            ("name", "in", list(DEMO_NAMES)),
        ]
    )
    if not demo:
        return
    tasks = env["daily.task"].with_context(active_test=False).search(
        [("assignee_id", "in", demo.ids)]
    )
    tasks.unlink()
    demo.unlink()
