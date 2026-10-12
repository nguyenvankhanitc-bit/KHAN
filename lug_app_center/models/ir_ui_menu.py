# -*- coding: utf-8 -*-

from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        """App Center là trang chủ chung: luôn hiện cho mọi user nội bộ,
        kể cả user bị áp Phân quyền ứng dụng (lug_permission chỉ cho hiện app được cấp «Xem»)."""
        res = super()._load_menus_blacklist()
        root = self.env.ref("lug_app_center.menu_lug_app_center_root", raise_if_not_found=False)
        if root and root.id in res and self.env.user._is_internal():
            res = [menu_id for menu_id in res if menu_id != root.id]
        return res
