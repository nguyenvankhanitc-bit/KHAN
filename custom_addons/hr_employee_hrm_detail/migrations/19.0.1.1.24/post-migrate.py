# -*- coding: utf-8 -*-
"""Sync employee access ir.rules after adding Employees = Staff level."""

from odoo import SUPERUSER_ID, api

from odoo.addons.hr_employee_hrm_detail.hooks import _sync_mien_access_rules


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _sync_mien_access_rules(env)
    env.registry.clear_cache()
