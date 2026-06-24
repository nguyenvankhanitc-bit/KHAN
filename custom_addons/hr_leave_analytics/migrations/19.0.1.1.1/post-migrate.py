from odoo import api, SUPERUSER_ID

from odoo.addons.hr_leave_analytics.hooks import _invalidate_web_assets


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.users"]._hr_leave_analytics_assign_default_groups()
    env["res.users"]._hr_leave_analytics_sync_groups_from_lug_zones()
    env["res.users"].search([])._compute_hr_leave_analytics_allowed_miens()
    _invalidate_web_assets(env)
