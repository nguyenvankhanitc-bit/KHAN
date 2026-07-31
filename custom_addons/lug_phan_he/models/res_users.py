# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    phan_he_mien_ids = fields.Many2many(
        "phan.he.mien",
        "phan_he_user_mien_rel",
        "user_id",
        "mien_id",
        string="Miền phụ trách",
    )
    phan_he_area_ids = fields.Many2many(
        "phan.he.area",
        "phan_he_user_area_rel",
        "user_id",
        "area_id",
        string="Khu vực phụ trách",
    )
    phan_he_store_ids = fields.Many2many(
        "phan.he.store",
        "phan_he_user_store_rel",
        "user_id",
        "store_id",
        string="Cửa hàng phụ trách",
        help="Nếu có thì giới hạn đúng các cửa hàng này (ưu tiên cao hơn khu vực).",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "phan_he_mien_ids", "phan_he_area_ids", "phan_he_store_ids",
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS
