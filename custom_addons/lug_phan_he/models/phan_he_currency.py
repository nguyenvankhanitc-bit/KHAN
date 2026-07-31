# -*- coding: utf-8 -*-

from odoo import models


class PhanHeCurrencyMixin(models.AbstractModel):
    _name = "phan.he.currency.mixin"
    _description = "Mặc định tiền tệ VNĐ"

    def _default_currency_vnd(self):
        return (
            self.env.ref("base.VND", raise_if_not_found=False)
            or self.env["res.currency"].search([("name", "=", "VND")], limit=1)
            or self.env.company.currency_id
        )
