# -*- coding: utf-8 -*-
"""Ma trận phân quyền người dùng theo menu cha–con.

Tận dụng cây menu Internet / Máy chủ / LinkQ đã có; Camera & Máy chấm công
dùng mục cấu hình map sang action thực tế (không tạo trang nghiệp vụ giả).

User đã có dòng trong phan.he.user.menu.perm → dùng ma trận user.
User chưa cấu hình → giữ quyền nhóm (phan.he.module.access) như trước.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .internet_menu_permission import INTERNET_MENU_TREE
from .lug_menu_permission import MENU_TREE as LINKQ_MENU_TREE
from .server_menu_permission import SERVER_MENU_TREE

# (code, name, app_code, parent_code, is_folder)
# parent_code False = gốc app; thư mục cấp 1 gắn vào gốc app.
def _build_unified_tree():
    rows = [
        ("app_internet", "DỊCH VỤ INTERNET", "internet", False, True),
        ("app_attendance", "MÁY CHẤM CÔNG", "attendance", False, True),
        ("app_camera", "DỊCH VỤ CAMERA", "camera", False, True),
        ("app_server", "MÁY CHỦ", "server", False, True),
        ("app_linkq", "LINKQ ERP", "linkq_nb", False, True),
    ]
    # Internet: gắn thư mục gốc vào app_internet
    for code, name, is_folder, parent in INTERNET_MENU_TREE:
        rows.append((
            code,
            name,
            "internet",
            parent or "app_internet",
            bool(is_folder),
        ))
    # Camera — menu thực tế trên hệ thống
    for code, name, parent in (
        ("camera_overview", "Tổng quan", "app_camera"),
        ("camera_list", "Danh sách", "app_camera"),
        ("camera_entry", "Nhập liệu", "app_camera"),
        ("camera_payment", "Thanh toán", "app_camera"),
    ):
        rows.append((code, name, "camera", parent, False))
    # Máy chấm công — menu thực tế
    for code, name, parent in (
        ("attendance_overview", "Tổng quan", "app_attendance"),
        ("attendance_list", "Danh sách máy", "app_attendance"),
        ("attendance_entry", "Nhập liệu", "app_attendance"),
        ("attendance_payment", "Thanh toán", "app_attendance"),
    ):
        rows.append((code, name, "attendance", parent, False))
    # Máy chủ — cây sidebar IT thực tế. "overview" đổi mã để khỏi trùng catalog khác.
    def _server_catalog_code(code):
        return "server_overview" if code == "overview" else code

    for code, name, is_group, parent in SERVER_MENU_TREE:
        rows.append((
            _server_catalog_code(code),
            name,
            "server",
            _server_catalog_code(parent) if parent else "app_server",
            bool(is_group),
        ))
    # LinkQ ERP — cây menu lịch ca thực tế
    for key, label, is_group, parent in LINKQ_MENU_TREE:
        rows.append((
            "lq_%s" % key,
            label,
            "linkq_nb",
            ("lq_%s" % parent) if parent else "app_linkq",
            bool(is_group),
        ))
    return rows


UNIFIED_MENU_TREE = _build_unified_tree()
APP_LABELS = {
    "internet": "Dịch vụ Internet",
    "camera": "Dịch vụ Camera",
    "attendance": "Máy chấm công",
    "server": "Máy chủ",
    "linkq_nb": "LinkQ ERP",
}
# Cột tổng hợp theo mẫu Excel (User × quyền truy cập ứng dụng)
SUMMARY_APPS = (
    ("internet", "Internet", "app_internet"),
    ("attendance", "Máy chấm", "app_attendance"),
    ("server", "Máy chủ", "app_server"),
    ("linkq_nb", "LinkQERP", "app_linkq"),
)
SUMMARY_APP_CODES = tuple(code for code, _l, _root in SUMMARY_APPS)
SUMMARY_APP_ROOT = {code: root for code, _l, root in SUMMARY_APPS}
PERM_FIELDS = ("can_view", "can_create", "can_edit", "can_delete", "can_admin")
# Map mã catalog → mã quyền runtime (internet / server / linkq)
RUNTIME_CODE_MAP = {
    "server_overview": "overview",
}
for key, _l, _g, _p in LINKQ_MENU_TREE:
    RUNTIME_CODE_MAP["lq_%s" % key] = key


class PhanHePermMenu(models.Model):
    _name = "phan.he.perm.menu"
    _description = "Danh mục menu phân quyền"
    _order = "sequence, id"
    _parent_store = True
    _rec_name = "name"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    app_code = fields.Selection(
        [(k, v) for k, v in APP_LABELS.items()],
        string="Ứng dụng",
        required=True,
        index=True,
    )
    parent_id = fields.Many2one(
        "phan.he.perm.menu",
        string="Menu cha",
        ondelete="cascade",
        index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("phan.he.perm.menu", "parent_id", string="Menu con")
    is_folder = fields.Boolean(default=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("unique(code)", "Mã menu phân quyền phải duy nhất.")

    @api.model
    def _ensure_catalog(self):
        """Đồng bộ danh mục từ UNIFIED_MENU_TREE (idempotent)."""
        Menu = self.sudo()
        existing = {m.code: m for m in Menu.search([])}
        created = {}
        seq = 0
        # Pass 1: create / update meta (parent later)
        for code, name, app_code, _parent, is_folder in UNIFIED_MENU_TREE:
            seq += 10
            vals = {
                "name": name,
                "app_code": app_code,
                "is_folder": is_folder,
                "sequence": seq,
                "active": True,
            }
            if code in existing:
                line = existing[code]
                updates = {k: v for k, v in vals.items() if line[k] != v}
                if updates:
                    line.write(updates)
                created[code] = line
            else:
                created[code] = Menu.create(dict(vals, code=code))
        # Pass 2: link parents
        for code, _name, _app, parent_code, _folder in UNIFIED_MENU_TREE:
            line = created.get(code)
            if not line:
                continue
            parent = created.get(parent_code) if parent_code else False
            parent_id = parent.id if parent else False
            if line.parent_id.id != parent_id:
                line.write({"parent_id": parent_id})
        return True


class PhanHeUserMenuPerm(models.Model):
    _name = "phan.he.user.menu.perm"
    _description = "Phân quyền menu theo người dùng"
    _order = "user_id, menu_id"

    user_id = fields.Many2one(
        "res.users",
        string="Người dùng",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('share', '=', False)]",
    )
    menu_id = fields.Many2one(
        "phan.he.perm.menu",
        string="Menu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    menu_code = fields.Char(related="menu_id.code", store=True, index=True)
    app_code = fields.Selection(related="menu_id.app_code", store=True, index=True)
    can_view = fields.Boolean(string="Xem", default=False)
    can_create = fields.Boolean(string="Thêm", default=False)
    can_edit = fields.Boolean(string="Sửa", default=False)
    can_delete = fields.Boolean(string="Xóa", default=False)
    can_admin = fields.Boolean(string="Quản trị", default=False)

    _user_menu_uniq = models.Constraint(
        "unique(user_id, menu_id)",
        "Mỗi người dùng chỉ có một dòng quyền cho mỗi menu.",
    )

    @api.constrains("can_view", "can_create", "can_edit", "can_delete", "can_admin")
    def _check_view_required(self):
        for rec in self:
            if rec.can_view:
                continue
            if any(rec[f] for f in ("can_create", "can_edit", "can_delete", "can_admin")):
                raise ValidationError(
                    "Menu «%s»: cần bật Xem trước khi cấp quyền khác."
                    % (rec.menu_id.name or rec.menu_code)
                )

    def write(self, vals):
        vals = dict(vals)
        if any(vals.get(f) for f in ("can_create", "can_edit", "can_delete", "can_admin")):
            vals["can_view"] = True
        if vals.get("can_admin"):
            for f in ("can_view", "can_create", "can_edit", "can_delete"):
                vals.setdefault(f, True)
        return super().write(vals)


class PhanHeModuleAccessUserMatrix(models.Model):
    _inherit = "phan.he.module.access"

    def _user_matrix_guard(self):
        user = self.env.user
        if self.env.su or user.has_group("base.group_system") or user.has_group(
            "lug_phan_he.group_phan_he_admin"
        ):
            return
        raise AccessError("Chỉ Quản trị viên mới được cấu hình ma trận phân quyền người dùng.")

    def _is_protected_admin_user(self, target):
        return bool(
            target.has_group("base.group_system")
            or target.has_group("lug_phan_he.group_phan_he_admin")
        )

    @api.model
    def get_user_app_summary(self, user_ids=None):
        """Tổng hợp User × quyền truy cập ứng dụng (+ trạng thái menu chi tiết)."""
        self._user_matrix_guard()
        self.env["phan.he.perm.menu"]._ensure_catalog()
        Users = self.env["res.users"].sudo()
        users = Users.search([("share", "=", False), ("active", "=", True)], order="name")
        if user_ids:
            wanted = {int(i) for i in user_ids if i}
            users = users.filtered(lambda u: u.id in wanted) or users
        rows = []
        Perm = self.env["phan.he.user.menu.perm"].sudo()
        for user in users:
            rights = self.get_user_module_rights(user.id)
            configured = self.user_has_matrix_config(user.id)
            menu_count = Perm.search_count([
                ("user_id", "=", user.id),
                ("can_view", "=", True),
                ("menu_id.code", "not in", list(SUMMARY_APP_ROOT.values())),
            ]) if configured else 0
            apps = {}
            for code, _label, _root in SUMMARY_APPS:
                row = rights.get(code) or {}
                apps[code] = bool(row.get("view"))
            rows.append({
                "user_id": user.id,
                "name": user.name or user.login,
                "login": user.login or "",
                "is_admin": self._is_protected_admin_user(user),
                "configured": configured,
                "apps": apps,
                "menu_count": menu_count,
            })
        return {
            "apps": [
                {"code": code, "label": label, "root": root}
                for code, label, root in SUMMARY_APPS
            ],
            "rows": rows,
        }

    def _seed_user_matrix_from_effective(self, user):
        """Lần đầu bật ma trận: giữ quyền app đang có (nhóm) rồi mới chỉnh tay."""
        self.env["phan.he.perm.menu"]._ensure_catalog()
        rights = self.get_user_module_rights(user.id)
        # Tránh đệ quy seed: chỉ đọc cờ view từ nhóm nếu chưa có matrix
        # get_user_module_rights đã gộp matrix; nếu chưa configured thì là quyền nhóm.
        Menu = self.env["phan.he.perm.menu"].sudo()
        Perm = self.env["phan.he.user.menu.perm"].sudo()
        for code, _label, root_code in SUMMARY_APPS:
            if not (rights.get(code) or {}).get("view"):
                continue
            root = Menu.search([("code", "=", root_code)], limit=1)
            if not root:
                continue
            existing = Perm.search([
                ("user_id", "=", user.id),
                ("menu_id", "=", root.id),
            ], limit=1)
            if existing:
                if not existing.can_view:
                    existing.write({"can_view": True})
            else:
                Perm.create({
                    "user_id": user.id,
                    "menu_id": root.id,
                    "can_view": True,
                })

    def _set_user_app_access(self, user, app_code, enabled):
        root_code = SUMMARY_APP_ROOT.get(app_code)
        if not root_code:
            raise UserError("Ứng dụng không hợp lệ: %s" % app_code)
        self.env["phan.he.perm.menu"]._ensure_catalog()
        Menu = self.env["phan.he.perm.menu"].sudo()
        Perm = self.env["phan.he.user.menu.perm"].sudo()
        root = Menu.search([("code", "=", root_code)], limit=1)
        if not root:
            raise UserError("Thiếu menu gốc «%s»." % root_code)
        app_menus = Menu.search([("app_code", "=", app_code), ("active", "=", True)])
        if enabled:
            line = Perm.search([
                ("user_id", "=", user.id),
                ("menu_id", "=", root.id),
            ], limit=1)
            if line:
                line.write({"can_view": True})
            else:
                Perm.create({
                    "user_id": user.id,
                    "menu_id": root.id,
                    "can_view": True,
                })
        else:
            # Thu hồi toàn bộ quyền menu thuộc app
            lines = Perm.search([
                ("user_id", "=", user.id),
                ("menu_id", "in", app_menus.ids),
            ])
            if lines:
                lines.unlink()

    @api.model
    def save_user_app_summary(self, changes):
        """changes: [{user_id, apps: {internet: bool, attendance: bool, ...}}, ...]"""
        self._user_matrix_guard()
        touched = self.env["res.users"]
        for raw in changes or []:
            user = self.env["res.users"].sudo().browse(int(raw.get("user_id") or 0))
            if not user.exists() or user.share:
                continue
            if self._is_protected_admin_user(user) and not self.env.user.has_group("base.group_system"):
                raise AccessError(
                    "Không được sửa quyền của tài khoản Quản trị: %s" % (user.name or user.login)
                )
            if not self.user_has_matrix_config(user.id):
                self._seed_user_matrix_from_effective(user)
            apps = raw.get("apps") or {}
            for code in SUMMARY_APP_CODES:
                if code not in apps:
                    continue
                self._set_user_app_access(user, code, bool(apps.get(code)))
            touched |= user
        if touched:
            touched._phan_he_force_logout()
        return {"status": "ok", "user_ids": touched.ids}

    @api.model
    def get_user_perm_matrix(self, user_id=None, app_code=None):
        """Payload cho UI ma trận."""
        self._user_matrix_guard()
        self.env["phan.he.perm.menu"]._ensure_catalog()
        Users = self.env["res.users"].sudo()
        users = Users.search([("share", "=", False), ("active", "=", True)], order="name")
        target = Users.browse(int(user_id or 0))
        if not target.exists():
            target = users.filtered(lambda u: not self._is_protected_admin_user(u))[:1] or users[:1]
        Menu = self.env["phan.he.perm.menu"].sudo()
        domain = [("active", "=", True)]
        if app_code and app_code != "all":
            domain.append(("app_code", "=", app_code))
        menus = Menu.search(domain, order="sequence, id")
        by_id = {m.id: m for m in menus}
        perm_map = {
            p.menu_id.id: p
            for p in self.env["phan.he.user.menu.perm"].sudo().search([
                ("user_id", "=", target.id),
            ])
        }
        rows = []
        for menu in menus:
            depth = 0
            walk = menu
            while walk.parent_id and walk.parent_id.id in by_id:
                depth += 1
                walk = walk.parent_id
                if depth > 8:
                    break
            p = perm_map.get(menu.id)
            rows.append({
                "menu_id": menu.id,
                "code": menu.code,
                "name": menu.name,
                "app_code": menu.app_code,
                "parent_id": menu.parent_id.id if menu.parent_id else False,
                "is_folder": bool(menu.is_folder),
                "depth": depth,
                "can_view": bool(p.can_view) if p else False,
                "can_create": bool(p.can_create) if p else False,
                "can_edit": bool(p.can_edit) if p else False,
                "can_delete": bool(p.can_delete) if p else False,
                "can_admin": bool(p.can_admin) if p else False,
            })
        return {
            "user_id": target.id,
            "user_name": target.name or target.login,
            "users": [
                {
                    "id": u.id,
                    "name": u.name or u.login,
                    "login": u.login or "",
                    "is_admin": self._is_protected_admin_user(u),
                }
                for u in users
            ],
            "apps": [{"code": "all", "name": "Tất cả ứng dụng"}]
            + [{"code": k, "name": v} for k, v in APP_LABELS.items()],
            "rows": rows,
            "configured": bool(perm_map),
        }

    @api.model
    def save_user_perm_matrix(self, user_id, rows):
        """Lưu ma trận. rows: [{menu_id, can_view, ...}, ...]."""
        self._user_matrix_guard()
        target = self.env["res.users"].sudo().browse(int(user_id or 0))
        if not target.exists() or target.share:
            raise UserError("Người dùng không hợp lệ.")
        if self._is_protected_admin_user(target) and not self.env.user.has_group("base.group_system"):
            raise AccessError("Không được sửa quyền của tài khoản Quản trị hệ thống.")
        if target == self.env.user and not self.env.user.has_group("base.group_system"):
            # Admin phan_he vẫn được sửa user khác; không tự nâng mình qua API này nếu không phải system
            pass

        Perm = self.env["phan.he.user.menu.perm"].sudo()
        existing = {
            p.menu_id.id: p
            for p in Perm.search([("user_id", "=", target.id)])
        }
        seen = set()
        for raw in rows or []:
            mid = int(raw.get("menu_id") or 0)
            if not mid:
                continue
            seen.add(mid)
            vals = {
                "can_view": bool(raw.get("can_view")),
                "can_create": bool(raw.get("can_create")),
                "can_edit": bool(raw.get("can_edit")),
                "can_delete": bool(raw.get("can_delete")),
                "can_admin": bool(raw.get("can_admin")),
            }
            if vals["can_admin"]:
                vals.update({f: True for f in PERM_FIELDS})
            elif any(vals[f] for f in ("can_create", "can_edit", "can_delete")):
                vals["can_view"] = True
            if mid in existing:
                line = existing[mid]
                if any(line[f] != vals[f] for f in PERM_FIELDS):
                    line.write(vals)
            else:
                if any(vals.values()):
                    Perm.create(dict(vals, user_id=target.id, menu_id=mid))
        # Xóa dòng không còn quyền nào và không còn trong payload (khi lọc app chỉ cập nhật subset)
        # Chỉ xóa các menu thuộc các menu_id gửi lên nếu có can_* = false hết
        for mid in seen:
            line = existing.get(mid)
            if not line:
                continue
            if not any(line[f] for f in PERM_FIELDS):
                line.unlink()

        target._phan_he_force_logout()
        return {"status": "ok", "user_id": target.id}

    @api.model
    def user_has_matrix_config(self, user_id=None):
        uid = int(user_id or self.env.uid)
        return bool(
            self.env["phan.he.user.menu.perm"].sudo().search_count([("user_id", "=", uid)], limit=1)
        )

    @api.model
    def get_user_matrix_rights(self, user_id=None):
        """Trả {configured, apps, internet_menus, server_menus, linkq_menus}."""
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        if (
            user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
        ):
            return {"configured": False, "bypass": True}

        lines = self.env["phan.he.user.menu.perm"].sudo().search([("user_id", "=", user.id)])
        if not lines:
            return {"configured": False, "bypass": False}

        apps = {
            code: {
                "view": False,
                "create": False,
                "edit": False,
                "delete": False,
                "admin": False,
            }
            for code in APP_LABELS
        }
        internet_menus = {}
        server_menus = {}
        linkq_menus = {}

        for line in lines:
            app = line.app_code
            if app in apps:
                apps[app]["view"] = apps[app]["view"] or bool(line.can_view)
                apps[app]["create"] = apps[app]["create"] or bool(line.can_create)
                apps[app]["edit"] = apps[app]["edit"] or bool(line.can_edit)
                apps[app]["delete"] = apps[app]["delete"] or bool(line.can_delete)
                apps[app]["admin"] = apps[app]["admin"] or bool(line.can_admin)

            code = line.menu_code or ""
            if code.startswith("app_"):
                continue
            runtime = RUNTIME_CODE_MAP.get(code, code)
            flags = {
                "read": bool(line.can_view or line.can_admin),
                "create": bool(line.can_create or line.can_admin),
                "write": bool(line.can_edit or line.can_admin),
                "unlink": bool(line.can_delete or line.can_admin),
                "admin": bool(line.can_admin),
            }
            if app == "internet":
                internet_menus[runtime] = flags
            elif app == "server":
                server_menus[runtime] = flags
            elif app == "linkq_nb":
                linkq_menus[runtime] = {
                    "read": flags["read"],
                    "create": flags["create"],
                    "write": flags["write"],
                    "unlink": flags["unlink"],
                }

        return {
            "configured": True,
            "bypass": False,
            "apps": apps,
            "internet_menus": internet_menus,
            "server_menus": server_menus,
            "linkq_menus": linkq_menus,
        }

    @api.model
    def get_user_internet_menu_rights(self, user_id=None):
        matrix = self.get_user_matrix_rights(user_id)
        if matrix.get("configured"):
            from .internet_menu_permission import (
                _apply_app_gate_to_internet_menus,
                _empty_internet_menu_rights,
                _fold_parent_rights,
            )
            result = _empty_internet_menu_rights()
            for code, flags in (matrix.get("internet_menus") or {}).items():
                if code not in result:
                    continue
                result[code]["read"] = bool(flags.get("read"))
                result[code]["create"] = bool(flags.get("create"))
                result[code]["write"] = bool(flags.get("write"))
                result[code]["unlink"] = bool(flags.get("unlink"))
                result[code]["admin"] = bool(flags.get("admin"))
            result = _fold_parent_rights(result)
            app = (matrix.get("apps") or {}).get("internet") or {}
            return _apply_app_gate_to_internet_menus(result, app)
        return super().get_user_internet_menu_rights(user_id)

    @api.model
    def get_user_server_menu_rights(self, user_id=None):
        matrix = self.get_user_matrix_rights(user_id)
        if matrix.get("configured"):
            from .server_menu_permission import (
                _apply_app_gate_to_server_menus,
                _empty_server_menu_rights,
                _fold_parent_rights,
                _inherit_overview_dashboard,
            )
            result = _empty_server_menu_rights()
            raw = matrix.get("server_menus") or {}
            for code, flags in raw.items():
                if code not in result:
                    continue
                result[code]["read"] = bool(flags.get("read"))
                result[code]["create"] = bool(flags.get("create"))
                result[code]["write"] = bool(flags.get("write"))
                result[code]["unlink"] = bool(flags.get("unlink"))
                result[code]["admin"] = bool(flags.get("admin"))
            result = _inherit_overview_dashboard(result, "overview_dashboard" in raw)
            result = _fold_parent_rights(result)
            app = (matrix.get("apps") or {}).get("server") or {}
            return _apply_app_gate_to_server_menus(result, app)
        return super().get_user_server_menu_rights(user_id)

    @api.model
    def get_user_linkq_menu_rights(self, user_id=None):
        matrix = self.get_user_matrix_rights(user_id)
        if matrix.get("configured"):
            from .lug_menu_permission import _empty_menu_rights, _fold_parent_rights
            result = _empty_menu_rights()
            for code, flags in (matrix.get("linkq_menus") or {}).items():
                if code not in result:
                    continue
                result[code]["read"] = bool(flags.get("read"))
                result[code]["create"] = bool(flags.get("create"))
                result[code]["write"] = bool(flags.get("write"))
                result[code]["unlink"] = bool(flags.get("unlink"))
            return _fold_parent_rights(result)
        return super().get_user_linkq_menu_rights(user_id)

    @api.model
    def _phan_he_extend_module_rights(self, result, user_id):
        result = super()._phan_he_extend_module_rights(result, user_id)
        matrix = self.get_user_matrix_rights(user_id)
        if not matrix.get("configured"):
            return result
        for code, flags in (matrix.get("apps") or {}).items():
            if code not in result:
                continue
            result[code]["view"] = bool(flags.get("view"))
            result[code]["create"] = bool(flags.get("create"))
            result[code]["edit"] = bool(flags.get("edit"))
            result[code]["delete"] = bool(flags.get("delete"))
            result[code]["admin"] = bool(flags.get("admin"))
        # Đồng bộ lại menu từ helper (đã ưu tiên ma trận user) + gate app
        from .internet_menu_permission import _apply_app_gate_to_internet_menus

        result["internet_menus"] = _apply_app_gate_to_internet_menus(
            self.get_user_internet_menu_rights(user_id),
            result.get("internet") or {},
        )
        result["server_menus"] = self.get_user_server_menu_rights(user_id)
        result["linkq_menus"] = self.get_user_linkq_menu_rights(user_id)
        result["user_matrix"] = True
        return result
