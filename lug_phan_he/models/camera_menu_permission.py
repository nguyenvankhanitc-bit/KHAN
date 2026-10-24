# -*- coding: utf-8 -*-

from odoo import api, fields, models

# (menu_code, menu_name, is_folder, parent_code) — menu thực tế của Dịch vụ Camera.
CAMERA_MENU_TREE = [
    ("overview", "TỔNG QUAN", True, False),
    ("camera_dashboard", "Dashboard", False, "overview"),
    ("manage", "QUẢN LÝ CAMERA", True, False),
    ("camera_list", "Danh sách điểm Camera", False, "manage"),
    ("camera_entry", "Nhập liệu", False, "manage"),
    ("payment", "CHI PHÍ", True, False),
    ("camera_payment", "Chi phí bảo trì", False, "payment"),
]

CAMERA_MENU_LABEL = {code: name for code, name, _f, _p in CAMERA_MENU_TREE}
CAMERA_MENU_PARENT = {code: parent or False for code, _n, _f, parent in CAMERA_MENU_TREE}
PERM_BOOLS = ("can_read", "can_create", "can_write", "can_unlink")


class SecurityCameraMenuPermission(models.Model):
    _name = "security.camera.menu.permission"
    _description = "Chi tiết phân quyền Menu Camera"
    _order = "sequence, id"

    role_id = fields.Many2one(
        "phan.he.module.access",
        string="Nhóm quyền",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    menu_code = fields.Char(string="Mã menu", required=True, index=True)
    menu_name = fields.Char(string="Tên menu", compute="_compute_menu_name", store=True, readonly=False)
    parent_id = fields.Many2one(
        "security.camera.menu.permission",
        string="Menu cha",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many("security.camera.menu.permission", "parent_id", string="Menu con")
    is_folder = fields.Boolean(string="Thư mục nhóm", default=False)
    can_read = fields.Boolean(string="XEM", default=False)
    can_create = fields.Boolean(string="THÊM", default=False)
    can_write = fields.Boolean(string="SỬA", default=False)
    can_unlink = fields.Boolean(string="XÓA", default=False)
    can_admin = fields.Boolean(string="QUẢN TRỊ", default=False)

    _menu_code_uniq = models.Constraint(
        "unique(role_id, menu_code)",
        "Mỗi menu Camera chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.depends("menu_code", "is_folder")
    def _compute_menu_name(self):
        for rec in self:
            label = CAMERA_MENU_LABEL.get(rec.menu_code) or rec.menu_code or ""
            rec.menu_name = ("📁  %s" % label) if rec.is_folder else ("    └─  %s" % label)

    def write(self, vals):
        vals = dict(vals)
        if any(vals.get(fname) for fname in ("can_create", "can_write", "can_unlink", "can_admin")):
            vals["can_read"] = True
        if vals.get("can_admin") and not self.env.context.get("skip_camera_menu_cascade"):
            for fname in PERM_BOOLS:
                vals.setdefault(fname, True)
        res = super().write(vals)
        if self.env.context.get("skip_camera_menu_cascade"):
            return res
        perm_keys = [key for key in ("can_read", "can_create", "can_write", "can_unlink", "can_admin") if key in vals]
        if perm_keys:
            for rec in self.filtered("is_folder"):
                child_vals = {key: bool(rec[key]) for key in perm_keys}
                if child_vals:
                    rec.child_ids.with_context(skip_camera_menu_cascade=True).write(child_vals)
        roles = self.mapped("role_id")
        if roles and not self.env.context.get("skip_camera_app_sync"):
            roles._sync_camera_app_line_from_menus()
        return res


class PhanHeModuleAccessCameraMenu(models.Model):
    _inherit = "phan.he.module.access"

    camera_menu_permission_ids = fields.One2many(
        "security.camera.menu.permission",
        "role_id",
        string="Phân quyền Menu Camera",
    )

    def _sync_camera_app_line_from_menus(self):
        for rec in self:
            menus = rec.camera_menu_permission_ids
            line = rec.line_ids.filtered(lambda item: item.service_code == "camera")[:1]
            if not line:
                continue
            vals = {
                "perm_view": any(
                    item.can_read or item.can_create or item.can_write or item.can_unlink or item.can_admin
                    for item in menus
                ),
                "perm_create": any(item.can_create or item.can_admin for item in menus),
                "perm_edit": any(item.can_write or item.can_admin for item in menus),
                "perm_delete": any(item.can_unlink or item.can_admin for item in menus),
                "perm_admin": any(item.can_admin for item in menus),
            }
            to_write = {key: value for key, value in vals.items() if line[key] != value}
            if to_write:
                line.with_context(skip_camera_app_sync=True).write(to_write)

    def web_read(self, specification):
        if self.ids and specification and "camera_menu_permission_ids" in specification:
            self._ensure_camera_menu_lines()
            self.invalidate_recordset(["camera_menu_permission_ids"])
        return super().web_read(specification)

    def _ensure_camera_menu_lines(self):
        Line = self.env["security.camera.menu.permission"].sudo()
        for rec in self:
            if not rec.id:
                continue
            existing = {line.menu_code: line for line in rec.camera_menu_permission_ids}
            fresh = not existing and (rec.code or "").strip().lower() == "camera"
            to_create = []
            for seq, (code, _name, is_folder, _parent) in enumerate(CAMERA_MENU_TREE, start=1):
                meta = {"sequence": seq * 10, "is_folder": is_folder}
                if code in existing:
                    line = existing[code]
                    updates = {}
                    if line.sequence != meta["sequence"]:
                        updates["sequence"] = meta["sequence"]
                    if line.is_folder != is_folder:
                        updates["is_folder"] = is_folder
                    if updates:
                        line.with_context(skip_camera_menu_cascade=True).write(updates)
                    continue
                to_create.append({
                    "role_id": rec.id,
                    "menu_code": code,
                    "sequence": meta["sequence"],
                    "is_folder": is_folder,
                    "can_read": fresh,
                    "can_create": fresh,
                    "can_write": fresh,
                    "can_unlink": fresh,
                    "can_admin": fresh,
                })
            if to_create:
                Line.with_context(skip_camera_menu_cascade=True).create(to_create)
            for line in rec.camera_menu_permission_ids:
                label = CAMERA_MENU_LABEL.get(line.menu_code) or line.menu_code or ""
                expected = ("📁  %s" % label) if line.is_folder else ("    └─  %s" % label)
                if line.menu_name != expected:
                    line.with_context(skip_camera_menu_cascade=True).write({"menu_name": expected})
            rec._link_camera_menu_parents()

    def _link_camera_menu_parents(self):
        self.ensure_one()
        by_code = {line.menu_code: line for line in self.camera_menu_permission_ids}
        for code, parent_code in CAMERA_MENU_PARENT.items():
            line = by_code.get(code)
            if not line:
                continue
            parent = by_code.get(parent_code) if parent_code else False
            parent_id = parent.id if parent else False
            if line.parent_id.id != parent_id:
                line.with_context(skip_camera_menu_cascade=True).write({"parent_id": parent_id})
