# -*- coding: utf-8 -*-

from odoo import models


SERVICE_ROOT_XMLIDS = {
    "lug_phan_he.menu_phan_he_internet_root": "internet",
    "lug_phan_he.menu_phan_he_camera_root": "camera",
    "lug_phan_he.menu_phan_he_attendance_root": "attendance",
    "lug_phan_he.menu_phan_he_server_root": "server",
    "lug_phan_he.menu_phan_he_linkq_nb_root": "linkq_nb",
    "lug_phan_he.menu_phan_he_linkq_hrm_root": "linkq_hrm",
    "lug_phan_he.menu_phan_he_config_root": "config",
}

LINKQ_CHILD_XMLIDS = {
    "lug_phan_he.menu_phan_he_linkq_nb_dashboard": "dashboard",
    "lug_phan_he.menu_linkq_shift_schedule_north": "schedule_north",
    "lug_phan_he.menu_linkq_shift_schedule_south": "schedule_south",
    "lug_phan_he.menu_linkq_shift_schedule_dtt": "schedule_dtt",
    "lug_phan_he.menu_phan_he_shift_roster": "schedule_main",
    "lug_phan_he.menu_phan_he_work_shift": "schedule_symbol",
}


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        if self.env.su:
            return res
        user = self.env.user
        if user.has_group("base.group_system") or user.has_group(
            "lug_phan_he.group_phan_he_admin"
        ):
            return res
        rights = self.env["phan.he.module.access"].get_user_module_rights()
        for xmlid, code in SERVICE_ROOT_XMLIDS.items():
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            if code in ("config", "linkq_nb"):
                res.append(menu.id)
                continue
            if not (rights.get(code) or {}).get("view"):
                res.append(menu.id)
        menus = rights.get("linkq_menus") or {}
        for xmlid, menu_key in LINKQ_CHILD_XMLIDS.items():
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            if not (menus.get(menu_key) or {}).get("read"):
                res.append(menu.id)
        return res
