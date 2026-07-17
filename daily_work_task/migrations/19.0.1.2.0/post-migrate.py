# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.daily_work_task.hooks import _link_employees_to_hr

    _link_employees_to_hr(env)
