#!/usr/bin/env python3
"""Emergency repair: ensure res.users visibility columns exist (run via odoo shell).

Usage on Linux server:
  odoo shell -c /etc/odoo/odoo.conf -d YOUR_DB --no-http < scripts/repair_visibility_schema.py
"""
from odoo.addons.hr_employee_hrm_detail.hooks import (
    _sync_mien_access_rules,
    _sync_user_visibility_policy,
)
from odoo.addons.hr_employee_hrm_detail.migration_schema import (
    ensure_res_users_visibility_schema,
)

ensure_res_users_visibility_schema(env.cr)
env.cr.commit()

users = env["res.users"].search([("share", "=", False)])
for fname in ("employee_ma_bo_phan_id", "employee_department_id", "employee_mien"):
    env.add_to_compute(env["res.users"]._fields[fname], users)
env["res.users"].flush_model(
    ["employee_ma_bo_phan_id", "employee_department_id", "employee_mien"]
)
_sync_user_visibility_policy(env, users.filtered(lambda u: not u.visibility_policy))
_sync_mien_access_rules(env)
env.registry.clear_cache()
env.cr.commit()
print("OK: visibility schema repaired for", len(users), "users")
