# -*- coding: utf-8 -*-

def _sync_lug_leave_access_rules(env):
    from odoo.addons.hr_employee_hrm_detail.hooks import _sync_mien_access_rules
    from .models.lug_constants import lug_leave_lug_scope_rule_domain

    _sync_mien_access_rules(env)
    rule = env.ref("lug_permission.hr_leave_lug_scope_rule", raise_if_not_found=False)
    domain = lug_leave_lug_scope_rule_domain()
    if rule and rule.domain_force != domain:
        rule.write({"domain_force": domain})


def post_init_hook(env):
    Users = env["res.users"]
    Users._lug_cleanup_legacy_visibility_views()
    Users._lug_backfill_data_scope_from_visibility()
    Users._lug_backfill_time_off_role_from_groups()
    _sync_lug_leave_access_rules(env)
    users = Users.search([]).filtered(lambda user: user._lug_permission_is_enforced())
    if users:
        users._sync_lug_odoo_groups()
        Users._lug_clear_menu_cache_global(env)
    Users._lug_set_default_employee_edit_scopes()
    _sync_lug_leave_access_rules(env)
