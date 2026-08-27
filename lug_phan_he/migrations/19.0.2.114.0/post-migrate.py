# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api

COMBINED_STORE = "AELB_ECH\nLUG_AELB_L2"
REMOVED_XML_IDS = (
    "north_lug_aelb_l2_t2t6",
    "north_lug_aelb_l2_t7cnle",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    North = env["linkq.shift.schedule.north"]
    North.search([("store_name", "=", "AELB_ECH")]).write({"store_name": COMBINED_STORE})
    North.search([("store_name", "=", "LUG_AELB_L2")]).unlink()
    env["ir.model.data"].search(
        [
            ("module", "=", "lug_phan_he"),
            ("name", "in", list(REMOVED_XML_IDS)),
        ]
    ).unlink()
