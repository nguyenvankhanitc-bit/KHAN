# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO phan_he_module_access_custom_user_rel (access_id, user_id)
        SELECT b.access_id, b.user_id
          FROM phan_he_access_user_backup b
         WHERE NOT EXISTS (
            SELECT 1 FROM phan_he_module_access_custom_user_rel c
             WHERE c.access_id = b.access_id AND c.user_id = b.user_id
         )
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    Access = env["phan.he.module.access"]
    Access._ensure_linkq_presets()
    Access.search([])._compute_effective_users()
