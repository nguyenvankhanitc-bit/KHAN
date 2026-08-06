# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Gỡ nhóm Người giao / Người xem còn sót khi không còn dòng phân quyền."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["daily.task.access"].repair_stale_security_groups()
