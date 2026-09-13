# -*- coding: utf-8 -*-

from odoo import api, fields, models
from markupsafe import Markup, escape

# (menu_key, label, is_group, parent_key)
MENU_TREE = [
    ("dashboard", "Dashboard", True, False),
    ("schedule_main", "Lịch xếp ca", True, False),
    ("schedule_add", "Thêm lịch ca", False, "schedule_main"),
    ("schedule_list", "Danh sách lịch ca", False, "schedule_main"),
    ("schedule_copy", "Sao chép lịch ca", False, "schedule_main"),
    ("schedule_lock", "Khóa lịch ca", False, "schedule_main"),
    ("schedule_unlock", "Mở khóa lịch ca", False, "schedule_main"),
    ("schedule_symbol", "Ký hiệu công", True, False),
    ("schedule_symbol_list", "Danh sách ký hiệu", False, "schedule_symbol"),
    ("schedule_symbol_add", "Thêm ký hiệu", False, "schedule_symbol"),
    ("region_group", "Lịch theo vùng miền", True, False),
    ("schedule_north", "Lịch Miền Bắc", False, "region_group"),
    ("schedule_south", "Lịch Miền Nam", False, "region_group"),
    ("schedule_dtt", "Lịch Miền ĐTT", False, "region_group"),
    ("notify_group", "Thông báo", True, False),
    ("notify_expiring", "Sắp khóa", False, "notify_group"),
    ("notify_reminder", "Nhắc nhở", False, "notify_group"),
    ("notify_locked", "Đã khóa", False, "notify_group"),
    ("notify_info", "Thông tin", False, "notify_group"),
    ("hr_group", "Nhân sự", True, False),
    ("hr_add", "Thêm nhân sự", False, "hr_group"),
    ("hr_list", "Danh sách nhân sự", False, "hr_group"),
    ("guide_docs", "Tài liệu hướng dẫn", True, False),
    ("report_group", "Báo cáo & Giám sát", True, False),
    ("report_summary", "Báo cáo tổng hợp", False, "report_group"),
    ("report_missing", "Cửa hàng thiếu ca", False, "report_group"),
    ("system_group", "Cấu hình hệ thống", True, False),
    ("system_lock", "Cài đặt khóa lịch ca", False, "system_group"),
    ("system_access", "Nhật ký hệ thống (Audit Log)", False, "system_group"),
]

MENU_LABEL = {key: label for key, label, _g, _p in MENU_TREE}
MENU_IS_GROUP = {key: is_group for key, _l, is_group, _p in MENU_TREE}
MENU_PARENT = {key: parent or False for key, _l, _g, parent in MENU_TREE}

LINKQ_MENU_SELECTION = [
    (key, (("" if is_group else "↳ ") + label))
    for key, label, is_group, _p in MENU_TREE
]
LINKQ_MENU_KEYS = [key for key, _l, _g, _p in MENU_TREE]

PARENT_CHILD = {}
for key, _label, _is_group, parent in MENU_TREE:
    if parent:
        PARENT_CHILD.setdefault(parent, []).append(key)
PARENT_CHILD = {k: tuple(v) for k, v in PARENT_CHILD.items()}

# Mẫu Nhân viên ca — khớp ma trận CÔNG VIỆC (không Xóa).
LINKQ_MENU_DEFAULTS = {
    "dashboard": {"can_read": True},
    "schedule_main": {"can_read": True, "can_create": True, "can_write": True},
    "schedule_add": {"can_read": True, "can_create": True},
    "schedule_list": {"can_read": True, "can_write": True},
    "schedule_copy": {"can_read": True, "can_create": True},
    "schedule_lock": {"can_read": True},
    "schedule_unlock": {"can_read": True},
    "schedule_symbol": {"can_read": True, "can_create": True, "can_write": True},
    "schedule_symbol_list": {"can_read": True, "can_write": True},
    "schedule_symbol_add": {"can_read": True, "can_create": True, "can_write": True},
    "region_group": {},
    "schedule_north": {},
    "schedule_south": {},
    "schedule_dtt": {},
    "notify_group": {"can_read": True},
    "notify_expiring": {"can_read": True},
    "notify_reminder": {"can_read": True},
    "notify_locked": {"can_read": True},
    "notify_info": {"can_read": True},
    "hr_group": {"can_read": True, "can_create": True, "can_write": True},
    "hr_add": {"can_read": True, "can_create": True},
    "hr_list": {"can_read": True, "can_write": True},
    "guide_docs": {"can_read": True},
    "report_group": {},
    "report_summary": {},
    "report_missing": {},
    "system_group": {},
    "system_lock": {},
    "system_access": {},
}

PRESET_MENU = {
    "preset_view": {
        "dashboard": {"can_read": True},
        "schedule_main": {"can_read": True},
        "schedule_list": {"can_read": True},
        "schedule_symbol": {"can_read": True},
        "schedule_symbol_list": {"can_read": True},
        "notify_group": {"can_read": True},
        "notify_expiring": {"can_read": True},
        "notify_reminder": {"can_read": True},
        "notify_locked": {"can_read": True},
        "notify_info": {"can_read": True},
        "hr_group": {"can_read": True},
        "hr_list": {"can_read": True},
        "guide_docs": {"can_read": True},
    },
    "preset_staff": LINKQ_MENU_DEFAULTS,
    "preset_store_mgr": {
        **LINKQ_MENU_DEFAULTS,
        "region_group": {"can_read": True},
        "schedule_north": {"can_read": True},
        "schedule_south": {"can_read": True},
        "schedule_dtt": {"can_read": True},
        "report_missing": {"can_read": True},
        "schedule_lock": {"can_read": True, "can_write": True},
    },
    "preset_region_mgr": {
        **LINKQ_MENU_DEFAULTS,
        "region_group": {"can_read": True, "can_write": True},
        "schedule_north": {"can_read": True, "can_write": True},
        "schedule_south": {"can_read": True, "can_write": True},
        "schedule_dtt": {"can_read": True, "can_write": True},
        "report_group": {"can_read": True},
        "report_summary": {"can_read": True},
        "report_missing": {"can_read": True},
        "schedule_lock": {"can_read": True, "can_write": True},
        "schedule_unlock": {"can_read": True, "can_write": True},
    },
    "preset_admin": {
        key: {"can_read": True, "can_create": True, "can_write": True, "can_unlink": True}
        for key in LINKQ_MENU_KEYS
    },
}

OP_TO_FLAG = {
    "read": "read",
    "create": "create",
    "write": "write",
    "unlink": "unlink",
}

PERM_BOOLS = ("can_read", "can_create", "can_write", "can_unlink")


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


def _fold_parent_rights(result):
    for parent, children in PARENT_CHILD.items():
        if parent not in result:
            continue
        for child in children:
            row = result.get(child) or {}
            for op in ("read", "create", "write", "unlink"):
                result[parent][op] = result[parent][op] or bool(row.get(op))
                result[child][op] = bool(row.get(op)) or bool(result[parent].get(op))
    return result


class LugMenuPermissionLine(models.Model):
    _name = "lug.menu.permission.line"
    _description = "Chi tiết phân quyền Menu con LinkQ ERP"
    _order = "sequence, id"

    permission_id = fields.Many2one(
        "phan.he.module.access",
        string="Phân quyền App",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    menu_key = fields.Selection(
        LINKQ_MENU_SELECTION,
        string="Công việc",
        required=True,
    )
    name = fields.Char(string="Công việc / Menu", compute="_compute_name", store=True)
    name_html = fields.Html(
        string="Công việc / Menu",
        compute="_compute_name_html",
        sanitize=False,
    )
    parent_id = fields.Many2one(
        "lug.menu.permission.line",
        string="Nhóm cha",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many(
        "lug.menu.permission.line",
        "parent_id",
        string="Menu con",
    )
    is_group = fields.Boolean(string="Là nhóm thư mục", default=False)
    can_read = fields.Boolean(string="Xem", default=False)
    can_create = fields.Boolean(string="Thêm", default=False)
    can_write = fields.Boolean(string="Sửa", default=False)
    can_unlink = fields.Boolean(string="Xóa", default=False)
    can_all = fields.Boolean(
        string="ALL",
        compute="_compute_can_all",
        inverse="_inverse_can_all",
        store=True,
    )
    is_custom = fields.Boolean(string="Tùy chỉnh riêng", default=False)

    _menu_key_uniq = models.Constraint(
        "unique(permission_id, menu_key)",
        "Mỗi menu chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.depends("menu_key", "is_group")
    def _compute_name(self):
        for rec in self:
            label = MENU_LABEL.get(rec.menu_key) or rec.menu_key or ""
            rec.name = ("📁  %s" % label) if rec.is_group else ("    ↳  %s" % label)

    @api.depends("menu_key", "is_group")
    def _compute_name_html(self):
        for rec in self:
            label = escape(MENU_LABEL.get(rec.menu_key) or rec.menu_key or "")
            if rec.is_group:
                rec.name_html = Markup(
                    '<span class="o_linkq_menu_group"><i class="fa fa-folder"></i> %s</span>'
                ) % label
            else:
                rec.name_html = Markup(
                    '<span class="o_linkq_menu_child">↳ %s</span>'
                ) % label

    @api.depends(*PERM_BOOLS)
    def _compute_can_all(self):
        for rec in self:
            rec.can_all = all(rec[fname] for fname in PERM_BOOLS)

    def _inverse_can_all(self):
        for rec in self:
            val = bool(rec.can_all)
            rec.with_context(skip_menu_cascade=True).write(
                {fname: val for fname in PERM_BOOLS}
            )
            rec._cascade_permissions_to_children()

    @api.onchange("can_all")
    def _onchange_can_all(self):
        val = bool(self.can_all)
        self.can_read = self.can_create = self.can_write = self.can_unlink = val
        for child in self.child_ids:
            child.can_read = child.can_create = child.can_write = child.can_unlink = val
            child.can_all = val

    @api.onchange("can_read", "can_create", "can_write", "can_unlink")
    def _onchange_permissions(self):
        self.can_all = all(self[fname] for fname in PERM_BOOLS)
        for child in self.child_ids:
            child.can_read = self.can_read
            child.can_create = self.can_create
            child.can_write = self.can_write
            child.can_unlink = self.can_unlink
            child.can_all = self.can_all

    def _cascade_permissions_to_children(self):
        self.ensure_one()
        if not self.child_ids:
            return
        vals = {fname: self[fname] for fname in PERM_BOOLS}
        self.child_ids.with_context(skip_menu_cascade=True).write(vals)

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_menu_cascade"):
            return res
        if set(vals) & set(PERM_BOOLS):
            for rec in self:
                rec._cascade_permissions_to_children()
            self.mapped("permission_id.user_ids")._phan_he_force_logout()
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
        if self.env.context.get("phan_he_ensure_lines"):
            self._ensure_menu_lines()
        return res

    def _menu_defaults_map(self):
        self.ensure_one()
        return PRESET_MENU.get(self.code) or LINKQ_MENU_DEFAULTS

    def _ensure_menu_lines(self):
        Line = self.env["lug.menu.permission.line"]
        for rec in self:
            existing = {line.menu_key: line for line in rec.menu_permission_line_ids}
            defaults_map = rec._menu_defaults_map()
            to_create = []
            for seq, (key, _label, is_group, _parent) in enumerate(MENU_TREE, start=1):
                defaults = defaults_map.get(key) or LINKQ_MENU_DEFAULTS.get(key) or {}
                meta = {
                    "sequence": seq * 10,
                    "is_group": is_group,
                }
                if key in existing:
                    line = existing[key]
                    updates = {}
                    if line.sequence != meta["sequence"]:
                        updates["sequence"] = meta["sequence"]
                    if line.is_group != is_group:
                        updates["is_group"] = is_group
                    if updates:
                        line.with_context(skip_menu_cascade=True).write(updates)
                    continue
                vals = dict(
                    meta,
                    permission_id=rec.id,
                    menu_key=key,
                    can_read=bool(defaults.get("can_read")),
                    can_create=bool(defaults.get("can_create")),
                    can_write=bool(defaults.get("can_write")),
                    can_unlink=bool(defaults.get("can_unlink")),
                )
                to_create.append(vals)
            if to_create:
                Line.create(to_create)
            rec._link_menu_line_parents()

    def _link_menu_line_parents(self):
        self.ensure_one()
        by_key = {line.menu_key: line for line in self.menu_permission_line_ids}
        for key, parent_key in MENU_PARENT.items():
            line = by_key.get(key)
            if not line:
                continue
            parent = by_key.get(parent_key) if parent_key else False
            parent_id = parent.id if parent else False
            if line.parent_id.id != parent_id:
                line.with_context(skip_menu_cascade=True).write({"parent_id": parent_id})

    INSTANT_PERM_MAP = {
        "perm_read": "can_read",
        "perm_create": "can_create",
        "perm_write": "can_write",
        "perm_unlink": "can_unlink",
        "perm_admin": "can_all",
        "can_read": "can_read",
        "can_create": "can_create",
        "can_write": "can_write",
        "can_unlink": "can_unlink",
        "can_all": "can_all",
    }

    @api.model
    def get_permission_matrix(self, group_id=None, user_id=None, access_id=None):
        Group = self.env["lug.group"].sudo()
        groups = Group.search([("active", "=", True)], order="name")
        group = Group.browse(int(group_id or 0))
        if not group.exists():
            group = groups[:1]
        users = group.user_ids.filtered(lambda u: u.active and not u.share) if group else self.env["res.users"]
        user = self.env["res.users"].sudo().browse(int(user_id or 0))
        if user.exists() and user not in users and not group:
            users = user
        elif user.exists() and users and user not in users:
            user = users[:1]
        elif not user.exists():
            user = users[:1]

        access = self.browse()
        if access_id:
            access = self.sudo().browse(int(access_id)).exists()
        if not access and group:
            access = self.sudo().search([("group_ids", "in", group.id), ("active", "=", True)], limit=1)
        if not access and user:
            access = self.sudo().search([("user_ids", "in", user.id), ("active", "=", True)], limit=1)
        if not access:
            access = self.sudo().search([("active", "=", True)], limit=1)
        if not access:
            access = self.sudo().create({
                "name": group.name if group else "Nhóm quyền LinkQ",
                "code": (group.code or "linkq_matrix") if group else "linkq_matrix",
                "group_ids": [(6, 0, group.ids)] if group else False,
            })
        access._ensure_menu_lines()

        by_key = {line.menu_key: line for line in access.menu_permission_line_ids}
        rows = []
        for key, label, is_group, parent_key in MENU_TREE:
            line = by_key.get(key)
            if not line:
                continue
            parent = by_key.get(parent_key) if parent_key else False
            inherited = {}
            for fname in PERM_BOOLS:
                inherited[fname] = bool(parent and parent[fname] and not line.is_custom)
            inherited["can_all"] = bool(parent and parent.can_all and not line.is_custom)
            rows.append({
                "id": line.id,
                "menu_key": key,
                "name": label,
                "is_group": bool(is_group),
                "parent_key": parent_key or False,
                "depth": 1 if parent_key else 0,
                "can_read": bool(line.can_read),
                "can_create": bool(line.can_create),
                "can_write": bool(line.can_write),
                "can_unlink": bool(line.can_unlink),
                "can_all": bool(line.can_all),
                "is_custom": bool(line.is_custom),
                "inherited": inherited,
            })
        return {
            "access_id": access.id,
            "group_id": group.id if group else 0,
            "user_id": user.id if user else 0,
            "groups": [{"id": g.id, "name": g.name or ""} for g in groups],
            "users": [{"id": u.id, "name": u.name or u.login} for u in users],
            "rows": rows,
        }

    @api.model
    def update_permission_instant(self, line_id, perm_type, value):
        Line = self.env["lug.menu.permission.line"].sudo()
        line = Line.browse(int(line_id))
        fname = self.INSTANT_PERM_MAP.get(perm_type)
        if not line.exists() or not fname:
            return {"status": "error", "message": "Dòng quyền không hợp lệ"}
        value = bool(value)
        vals = {}
        if line.parent_id:
            vals["is_custom"] = True
        else:
            vals["is_custom"] = False
        if fname == "can_all":
            vals.update({name: value for name in PERM_BOOLS})
        else:
            vals[fname] = value
        ctx = {"skip_menu_cascade": bool(line.parent_id)}
        line.with_context(**ctx).write(vals)
        if line.is_group and not line.parent_id:
            child_vals = dict(vals)
            child_vals["is_custom"] = False
            line.child_ids.with_context(skip_menu_cascade=True).write(child_vals)
        return {"status": "success"}

    @api.model
    def get_user_linkq_menu_rights(self, user_id=None):
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        groups = self.sudo().search(
            [
                ("user_ids", "in", user.id),
                ("active", "=", True),
                "|",
                ("company_id", "=", False),
                ("company_id", "in", user.company_ids.ids),
            ]
        )
        bypass = user.has_group("lug_phan_he.group_phan_he_admin") or user.has_group(
            "base.group_system"
        ) or user.has_group("lug_phan_he.group_phan_he_service_manager") or user.has_group(
            "lug_phan_he.group_linkq_manager"
        )
        if bypass:
            return _full_menu_rights()
        result = _empty_menu_rights()
        if not groups:
            return result
        for line in groups.mapped("menu_permission_line_ids"):
            key = line.menu_key
            if key not in result:
                continue
            result[key]["read"] = result[key]["read"] or bool(line.can_read)
            result[key]["create"] = result[key]["create"] or bool(line.can_create)
            result[key]["write"] = result[key]["write"] or bool(line.can_write)
            result[key]["unlink"] = result[key]["unlink"] or bool(line.can_unlink)
        return _fold_parent_rights(result)

    @api.model
    def _phan_he_extend_module_rights(self, result, user_id):
        super()._phan_he_extend_module_rights(result, user_id)
        result["linkq_menus"] = self.get_user_linkq_menu_rights(user_id)
        return result
