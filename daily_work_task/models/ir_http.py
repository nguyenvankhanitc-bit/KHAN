# -*- coding: utf-8 -*-

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        info["daily_work_single_app"] = bool(
            user
            and user.id
            and not user._is_public()
            and not user._is_system()
            and user.sudo().daily_work_single_app
        )
        return info
