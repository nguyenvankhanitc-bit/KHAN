# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.lug_eam.hooks import _ensure_asset_sequence, _ensure_category_tokens

    _ensure_asset_sequence(env)
    _ensure_category_tokens(env)
