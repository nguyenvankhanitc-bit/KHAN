# -*- coding: utf-8 -*-

from odoo import models

SERVICE_ROOT_XMLIDS = {
    "lug_phan_he.menu_phan_he_internet_root": "internet",
    "lug_phan_he.menu_phan_he_camera_root": "camera",
    "lug_phan_he.menu_phan_he_attendance_root": "attendance",
    "lug_phan_he.menu_phan_he_server_root": "server",
    "lug_phan_he.menu_phan_he_linkq_nb_root": "linkq_nb",
    "lug_phan_he.menu_phan_he_config_root": "config",
}

INTERNET_CHILD_XMLIDS = {
    "lug_phan_he.menu_phan_he_dashboard": "overview_dashboard",
    "lug_phan_he.menu_phan_he_entry": "internet_entry",
    "lug_phan_he.menu_phan_he_internet_active": "internet_active",
    "lug_phan_he.menu_phan_he_internet_suspend": "internet_suspend",
    "lug_phan_he.menu_phan_he_internet_liquidated": "internet_liquidation",
    "lug_phan_he.menu_phan_he_payment": "payment_schedule",
    "lug_phan_he.menu_phan_he_payment_pending": "payment_confirm",
    "lug_phan_he.menu_phan_he_payment_overdue": "payment_overdue",
    "lug_phan_he.menu_phan_he_payment_forecast": "payment_forecast",
    "lug_phan_he.menu_phan_he_service_expire_soon": "payment_schedule",
    "lug_phan_he.menu_phan_he_service_expired": "payment_overdue",
}

LINKQ_CHILD_XMLIDS = {
    "lug_phan_he.menu_phan_he_linkq_nb_dashboard": "dashboard",
    "lug_phan_he.menu_linkq_shift_schedule_north": "schedule_north",
    "lug_phan_he.menu_linkq_shift_schedule_south": "schedule_south",
    "lug_phan_he.menu_linkq_shift_schedule_dtt": "schedule_dtt",
    "lug_phan_he.menu_phan_he_shift_roster": "schedule_main",
    "lug_phan_he.menu_phan_he_work_shift": "schedule_symbol",
    "lug_phan_he.menu_linkq_hr_root": "hr_group",
    "lug_phan_he.menu_linkq_employee_create": "hr_add",
    "lug_phan_he.menu_linkq_employee_list": "hr_list",
}


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        try:
            return self._phan_he_blacklist_menus(res)
        except Exception:
            return res

    def _phan_he_menu_id(self, xmlid):
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        return menu.id if menu else False

    def _phan_he_blacklist_menus(self, res):
        if self.env.su:
            return res
        user = self.env.user
        # has_group đã được cache sẵn trên user
        if user.has_group("base.group_system") or user.has_group(
            "lug_phan_he.group_phan_he_admin"
        ):
            return res

        rights = self.env["phan.he.module.access"].get_user_module_rights()
        internet_menus = rights.get("internet_menus") or {}
        linkq_menus = rights.get("linkq_menus") or {}

        for xmlid, code in SERVICE_ROOT_XMLIDS.items():
            mid = self._phan_he_menu_id(xmlid)
            if not mid:
                continue
            if code in ("config", "linkq_nb"):
                res.append(mid)
                continue
            if not (rights.get(code) or {}).get("view"):
                res.append(mid)

        for xmlid, menu_key in INTERNET_CHILD_XMLIDS.items():
            mid = self._phan_he_menu_id(xmlid)
            if mid and not (internet_menus.get(menu_key) or {}).get("read"):
                res.append(mid)

        for xmlid, menu_key in LINKQ_CHILD_XMLIDS.items():
            mid = self._phan_he_menu_id(xmlid)
            if mid and not (linkq_menus.get(menu_key) or {}).get("read"):
                res.append(mid)
        return res
