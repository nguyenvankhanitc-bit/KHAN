# -*- coding: utf-8 -*-

from odoo import api, fields, models


LINKQ_MENU_SELECTION = [
    ("dashboard", "Dashboard"),
    ("schedule_north", "Lịch Miền Bắc"),
    ("schedule_south", "Lịch Miền Nam"),
    ("schedule_dtt", "Lịch Miền ĐTT"),
    ("schedule_main", "Lịch xếp ca"),
    ("schedule_symbol", "Ký hiệu công"),
]

LINKQ_MENU_KEYS = [key for key, _label in LINKQ_MENU_SELECTION]

# Dashboard: xem. Lịch xếp ca: xem + thêm + sửa. Lịch miền / ký hiệu công: tắt.
LINKQ_MENU_DEFAULTS = {
    "dashboard": {"can_read": True},
    "schedule_north": {},
    "schedule_south": {},
    "schedule_dtt": {},
    "schedule_main": {"can_read": True, "can_create": True, "can_write": True},
    "schedule_symbol": {},
}

OP_TO_FLAG = {
    "read": "read",
    "create": "create",
    "write": "write",
    "unlink": "unlink",
}


def _empty_menu_rights():
    return {
        key: {"read": False, "create": False, "write": False, "unlink": False}
        for key in LINKQ_MENU_KEYS
    }


def _full_menu_rights():
    return {
        key: {"read": True, "create": True, "write": True, "unlink": True}
        for key in LINKQ_MENU_KEYS
    }


class LugMenuPermissionLine(models.Model):
    _name = "lug.menu.permission.line"
    _description = "Chi tiết phân quyền Menu con LinkQ ERP"
    _order = "id"

    permission_id = fields.Many2one(
        "phan.he.module.access",
        string="Phân quyền App",
        required=True,
        ondelete="cascade",
        index=True,
    )
    menu_key = fields.Selection(
        LINKQ_MENU_SELECTION,
        string="Tên Menu",
        required=True,
    )
    can_read = fields.Boolean(string="Xem", default=True)
    can_create = fields.Boolean(string="Thêm", default=False)
    can_write = fields.Boolean(string="Sửa", default=False)
    can_unlink = fields.Boolean(string="Xóa", default=False)
    can_all = fields.Boolean(string="All", default=False)

    _menu_key_uniq = models.Constraint(
        "unique(permission_id, menu_key)",
        "Mỗi menu chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.onchange("can_all")
    def _onchange_can_all(self):
        if self.can_all:
            self.can_read = self.can_create = self.can_write = self.can_unlink = True
        else:
            self.can_create = self.can_write = self.can_unlink = False

    @api.onchange("can_read", "can_create", "can_write", "can_unlink")
    def _onchange_individual(self):
        self.can_all = bool(
            self.can_read and self.can_create and self.can_write and self.can_unlink
        )

    def write(self, vals):
        res = super().write(vals)
        if "can_all" in vals and vals["can_all"]:
            super(LugMenuPermissionLine, self).write(
                {
                    "can_read": True,
                    "can_create": True,
                    "can_write": True,
                    "can_unlink": True,
                }
            )
        elif any(
            key in vals
            for key in ("can_read", "can_create", "can_write", "can_unlink")
        ):
            for rec in self:
                all_on = rec.can_read and rec.can_create and rec.can_write and rec.can_unlink
                if rec.can_all != all_on:
                    super(LugMenuPermissionLine, rec).write({"can_all": all_on})
        return res


class PhanHeModuleAccessMenu(models.Model):
    _inherit = "phan.he.module.access"

    menu_permission_line_ids = fields.One2many(
        "lug.menu.permission.line",
        "permission_id",
        string="Chi tiết phân quyền Menu",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_menu_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_menu_lines()
        return res

    def _ensure_menu_lines(self):
        Line = self.env["lug.menu.permission.line"]
        for rec in self:
            existing = set(rec.menu_permission_line_ids.mapped("menu_key"))
            to_create = []
            for key in LINKQ_MENU_KEYS:
                if key in existing:
                    continue
                defaults = LINKQ_MENU_DEFAULTS.get(key) or {}
                to_create.append(
                    {
                        "permission_id": rec.id,
                        "menu_key": key,
                        "can_read": bool(defaults.get("can_read")),
                        "can_create": bool(defaults.get("can_create")),
                        "can_write": bool(defaults.get("can_write")),
                        "can_unlink": bool(defaults.get("can_unlink")),
                    }
                )
            if to_create:
                Line.create(to_create)

    @api.model
    def get_user_linkq_menu_rights(self, user_id=None):
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        groups = self.sudo().search(
            [
                ("user_ids", "in", user.id),
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
            ]
        )
        bypass = user.has_group("lug_phan_he.group_phan_he_admin") or user.has_group(
            "base.group_system"
        ) or user.has_group("lug_phan_he.group_phan_he_service_manager")
        if bypass:
            return _full_menu_rights()
        result = _empty_menu_rights()
        if not groups:
            return result
        groups._ensure_menu_lines()
        for line in groups.mapped("menu_permission_line_ids"):
            key = line.menu_key
            if key not in result:
                continue
            result[key]["read"] = result[key]["read"] or bool(line.can_read)
            result[key]["create"] = result[key]["create"] or bool(line.can_create)
            result[key]["write"] = result[key]["write"] or bool(line.can_write)
            result[key]["unlink"] = result[key]["unlink"] or bool(line.can_unlink)
        return result

    @api.model
    def get_user_module_rights(self, user_id=None):
        result = super().get_user_module_rights(user_id)
        result["linkq_menus"] = self.get_user_linkq_menu_rights(user_id)
        return result
