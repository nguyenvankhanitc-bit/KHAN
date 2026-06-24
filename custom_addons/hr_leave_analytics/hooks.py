# Part of Odoo. See LICENSE file for full copyright and licensing details.

_STALE_BUNDLE_NAMES = [
    "web.assets_web.min.js",
    "web.assets_web.min.css",
    "web.assets_backend.min.js",
    "web.assets_backend.min.css",
]


def _invalidate_web_assets(env):
    """Drop cached asset bundles so new JS/XML from this module is picked up."""
    env.registry.clear_cache("assets")
    env["ir.attachment"].sudo().search([("name", "in", _STALE_BUNDLE_NAMES)]).unlink()


def post_init_hook(env):
    _invalidate_web_assets(env)
    env["res.users"]._hr_leave_analytics_assign_default_groups()
    env["res.users"]._hr_leave_analytics_sync_groups_from_lug_zones()
    env["res.users"].search([])._compute_hr_leave_analytics_allowed_miens()
