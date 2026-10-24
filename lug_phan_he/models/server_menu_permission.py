# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError

# (menu_key, label, is_group, parent_key) — đúng cây sidebar Máy chủ.
SERVER_MENU_TREE = [
    ("overview", "TỔNG QUAN", True, False),
    ("overview_dashboard", "Tổng quan Dashboard", False, "overview"),
    ("manage", "QUẢN LÝ TÀI SẢN", True, False),
    ("it_asset_all", "Danh sách máy chủ", False, "manage"),
    ("it_asset_physical", "Máy chủ vật lý", False, "manage"),
    ("it_asset_virtual", "Máy chủ ảo", False, "manage"),
    ("it_asset_network", "Thiết bị mạng & bảo mật", False, "manage"),
    ("it_asset_new", "Thêm mới", False, "manage"),
    ("payment", "CHI PHÍ & GIA HẠN", True, False),
    ("it_cost_new", "Thêm mới", False, "payment"),
    ("it_cost_list", "Danh sách chi phí", False, "payment"),
    ("it_cost_confirm", "Chờ xác nhận thanh toán", False, "payment"),
    ("it_cost_overdue", "Quá hạn", False, "payment"),
    ("it_cost_schedule", "Lịch gia hạn", False, "payment"),
    ("it_cost_estimate", "Dự toán chi phí", False, "payment"),
    ("support", "BẢO TRÌ & HỖ TRỢ", True, False),
    ("it_ticket_maint", "Lịch sử bảo trì", False, "support"),
    ("it_ticket_support", "Yêu cầu hỗ trợ", False, "support"),
    ("it_ticket_incident", "Nhật ký sự cố", False, "support"),
    ("reports", "BÁO CÁO", True, False),
    ("it_report_month", "Chi phí tháng", False, "reports"),
    ("it_report_quarter", "Chi phí quý", False, "reports"),
    ("it_report_year", "Chi phí năm", False, "reports"),
    ("it_report_by_asset", "Chi phí theo tài sản", False, "reports"),
    ("it_report_by_provider", "Chi phí theo nhà cung cấp", False, "reports"),
    ("settings", "CÀI ĐẶT", True, False),
    ("it_settings_type", "Danh mục loại tài sản", False, "settings"),
    ("it_settings_category", "Danh mục hạng mục chi phí", False, "settings"),
    ("settings_provider", "Nhà cung cấp", False, "settings"),
    ("it_settings_cycle", "Chu kỳ gia hạn", False, "settings"),
    ("it_settings_remind", "Cấu hình nhắc hạn", False, "settings"),
]

SERVER_MENU_LABEL = {key: label for key, label, _g, _p in SERVER_MENU_TREE}
SERVER_MENU_IS_GROUP = {key: is_group for key, _l, is_group, _p in SERVER_MENU_TREE}
SERVER_MENU_PARENT = {key: parent or False for key, _l, _g, parent in SERVER_MENU_TREE}
SERVER_MENU_KEYS = [key for key, _l, _g, _p in SERVER_MENU_TREE]

PARENT_CHILD = {}
for _key, _label, _is_group, _parent in SERVER_MENU_TREE:
    if _parent:
        PARENT_CHILD.setdefault(_parent, []).append(_key)
PARENT_CHILD = {k: tuple(v) for k, v in PARENT_CHILD.items()}

PERM_BOOLS = ("can_read", "can_create", "can_write", "can_unlink")
OP_LABEL = {"read": "Xem", "create": "Thêm", "write": "Sửa", "unlink": "Xóa"}
OP_TO_FLAG = {"read": "read", "create": "create", "write": "write", "unlink": "unlink"}

ASSET_MENUS = (
    "it_asset_all",
    "it_asset_physical",
    "it_asset_virtual",
    "it_asset_network",
    "it_asset_new",
    "manage",
)
COST_MENUS = (
    "it_cost_new",
    "it_cost_list",
    "it_cost_confirm",
    "it_cost_overdue",
    "it_cost_schedule",
    "it_cost_estimate",
    "payment",
)
REPORT_MENUS = (
    "it_report_month",
    "it_report_quarter",
    "it_report_year",
    "it_report_by_asset",
    "it_report_by_provider",
    "reports",
)
TICKET_MENUS = (
    "it_ticket_maint",
    "it_ticket_support",
    "it_ticket_incident",
    "support",
)


_RIGHT_OPS = ("read", "create", "write", "unlink", "admin")


def _empty_server_menu_rights():
    return {
        key: {"read": False, "create": False, "write": False, "unlink": False, "admin": False}
        for key in SERVER_MENU_KEYS
    }


def _full_server_menu_rights():
    return {
        key: {"read": True, "create": True, "write": True, "unlink": True, "admin": True}
        for key in SERVER_MENU_KEYS
    }


def _fold_parent_rights(result):
    """Đẩy quyền từ mục con lên thư mục cha. Không lan sang mục anh em."""
    for parent, children in PARENT_CHILD.items():
        if parent not in result:
            continue
        for child in children:
            row = result.get(child) or {}
            for op in _RIGHT_OPS:
                result[parent][op] = result[parent][op] or bool(row.get(op))
    return result


def menu_op_allowed(menus, menu_code, operation):
    row = (menus or {}).get(menu_code) or {}
    if row.get("admin"):
        return True
    flag = OP_TO_FLAG.get(operation)
    return bool(flag and row.get(flag))


def _inherit_overview_dashboard(result, explicit_dashboard=True):
    """Dashboard mới kế thừa folder Tổng quan khi chưa có dòng quyền riêng."""
    if explicit_dashboard or "overview_dashboard" not in result or "overview" not in result:
        return result
    src = result.get("overview") or {}
    for op in _RIGHT_OPS:
        result["overview_dashboard"][op] = bool(src.get(op))
    return result


def _apply_app_gate_to_server_menus(menus, app):
    """Bảng 2 chỉ cần mở app Máy chủ. Không AND từng cờ app với từng menu."""
    app = app or {}
    if app.get("admin"):
        return menus
    app_open = bool(
        app.get("view")
        or app.get("create")
        or app.get("edit")
        or app.get("delete")
        or app.get("admin")
    )
    if app_open:
        return menus
    for _code, flags in (menus or {}).items():
        if not isinstance(flags, dict):
            continue
        for key in _RIGHT_OPS:
            flags[key] = False
    return menus


def _guard_server_menus(records, operation, codes):
    if records.env.su:
        return None
    user = records.env.user
    if (
        user.has_group("base.group_system")
        or user.has_group("lug_phan_he.group_phan_he_admin")
        or user.has_group("lug_phan_he.group_phan_he_service_manager")
    ):
        return None
    if records.env["phan.he.module.access"].server_operation_allowed(codes, operation):
        return None

    def _raise():
        raise AccessError(
            "Bạn không có quyền %s trên menu Máy chủ."
            % OP_LABEL.get(operation, operation)
        )

    return records, _raise


class SecurityServerMenuPermission(models.Model):
    _name = "security.server.menu.permission"
    _description = "Chi tiết phân quyền Menu Máy chủ"
    _order = "sequence, id"

    role_id = fields.Many2one(
        "phan.he.module.access",
        string="Nhóm quyền",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    menu_key = fields.Char(string="Mã menu", required=True, index=True)
    parent_key = fields.Char(string="Mã menu cha")
    name = fields.Char(string="Menu", compute="_compute_name", store=True, readonly=False)
    parent_id = fields.Many2one(
        "security.server.menu.permission",
        string="Menu cha",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many(
        "security.server.menu.permission",
        "parent_id",
        string="Menu con",
    )
    is_group = fields.Boolean(string="Thư mục", default=False)
    can_read = fields.Boolean(string="XEM", default=False)
    can_create = fields.Boolean(string="THÊM", default=False)
    can_write = fields.Boolean(string="SỬA", default=False)
    can_unlink = fields.Boolean(string="XÓA", default=False)
    can_all = fields.Boolean(string="QUẢN TRỊ", default=False)
    is_custom = fields.Boolean(string="Tùy chỉnh riêng", default=False)

    _menu_key_uniq = models.Constraint(
        "unique(role_id, menu_key)",
        "Mỗi menu Máy chủ chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.depends("menu_key", "is_group")
    def _compute_name(self):
        for rec in self:
            label = SERVER_MENU_LABEL.get(rec.menu_key) or rec.menu_key or ""
            rec.name = ("📁  %s" % label) if rec.is_group else ("    └─  %s" % label)

    @api.onchange("can_all")
    def _onchange_can_all(self):
        if self.can_all:
            self.can_read = self.can_create = self.can_write = self.can_unlink = True
            for child in self.child_ids:
                child.can_all = True
                child.can_read = child.can_create = child.can_write = child.can_unlink = True

    def write(self, vals):
        vals = dict(vals)
        if any(vals.get(fname) for fname in ("can_create", "can_write", "can_unlink", "can_all")):
            vals["can_read"] = True
        if vals.get("can_all") and not self.env.context.get("skip_server_menu_cascade"):
            for fname in PERM_BOOLS:
                vals.setdefault(fname, True)
        res = super().write(vals)
        if self.env.context.get("skip_server_menu_cascade"):
            return res
        perm_keys = [
            key
            for key in ("can_read", "can_create", "can_write", "can_unlink", "can_all")
            if key in vals
        ]
        if perm_keys:
            for rec in self.filtered("is_group"):
                child_vals = {key: bool(rec[key]) for key in perm_keys}
                if child_vals:
                    rec.child_ids.with_context(skip_server_menu_cascade=True).write(child_vals)
        if vals.get("can_all"):
            for rec in self:
                child_vals = {fname: True for fname in PERM_BOOLS}
                child_vals["can_all"] = True
                rec.child_ids.with_context(skip_server_menu_cascade=True).write(child_vals)
        roles = self.mapped("role_id")
        if roles and not self.env.context.get("skip_server_app_sync"):
            roles._sync_server_app_line_from_menus()
        return res


class PhanHeModuleAccessServerMenu(models.Model):
    _inherit = "phan.he.module.access"

    server_menu_permission_ids = fields.One2many(
        "security.server.menu.permission",
        "role_id",
        string="Phân quyền Menu Máy chủ",
    )

    def _sync_server_app_line_from_menus(self):
        """Bảng 2 Máy chủ = OR các quyền bảng 3."""
        for rec in self:
            menus = rec.server_menu_permission_ids
            line = rec.line_ids.filtered(lambda item: item.service_code == "server")[:1]
            if not line:
                continue
            vals = {
                "perm_view": any(
                    item.can_read
                    or item.can_create
                    or item.can_write
                    or item.can_unlink
                    or item.can_all
                    for item in menus
                ),
                "perm_create": any(item.can_create or item.can_all for item in menus),
                "perm_edit": any(item.can_write or item.can_all for item in menus),
                "perm_delete": any(item.can_unlink or item.can_all for item in menus),
                "perm_admin": any(item.can_all for item in menus),
            }
            to_write = {key: value for key, value in vals.items() if line[key] != value}
            if to_write:
                line.with_context(skip_server_app_sync=True).write(to_write)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "server_menu_permission_ids" in fields_list and not res.get("server_menu_permission_ids"):
            res["server_menu_permission_ids"] = self._default_server_menu_commands()
        return res

    @api.model
    def _default_server_menu_commands(self):
        commands = []
        for seq, (key, _label, is_group, parent) in enumerate(SERVER_MENU_TREE, start=1):
            commands.append((0, 0, {
                "sequence": seq * 10,
                "menu_key": key,
                "parent_key": parent or False,
                "is_group": is_group,
            }))
        return commands

    def _server_menu_seed_flags(self):
        """Nhóm đang có quyền Máy chủ trên tab ứng dụng thì giữ quyền đó khi sinh dòng menu."""
        self.ensure_one()
        flags = {fname: False for fname in PERM_BOOLS}
        flags["can_all"] = False
        line = self.line_ids.filtered(lambda item: item.service_code == "server")[:1]
        code = (self.code or "").strip().lower()
        if line and line.perm_admin:
            flags = {fname: True for fname in PERM_BOOLS}
            flags["can_all"] = True
            return flags
        if line:
            flags["can_read"] = bool(line.perm_view) or code == "server"
            flags["can_create"] = bool(line.perm_create)
            flags["can_write"] = bool(line.perm_edit)
            flags["can_unlink"] = bool(line.perm_delete)
        elif code == "server":
            flags["can_read"] = True
        flags["can_all"] = bool(line and line.perm_admin)
        return flags

    def _apply_server_menu_template(self):
        """Nhóm Máy chủ mới: bật đủ XEM/THÊM/SỬA/XÓA/QUẢN TRỊ, trừ Cài đặt."""
        self._ensure_server_menu_lines()
        for rec in self:
            if (rec.code or "").strip().lower() != "server":
                continue
            for line in rec.server_menu_permission_ids:
                parent = SERVER_MENU_PARENT.get(line.menu_key)
                granted = line.menu_key != "settings" and parent != "settings"
                vals = {
                    "can_read": granted,
                    "can_create": granted,
                    "can_write": granted,
                    "can_unlink": granted,
                    "can_all": granted,
                }
                if any(line[key] != value for key, value in vals.items()):
                    line.with_context(skip_server_menu_cascade=True).write(vals)
            rec._sync_server_app_line_from_menus()

    @api.model_create_multi
    def create(self, vals_list):
        template_idx = {
            index
            for index, vals in enumerate(vals_list)
            if not vals.get("server_menu_permission_ids")
            and str(vals.get("code") or "").strip().lower() == "server"
        }
        records = super().create(vals_list)
        templated = self.browse()
        plain = self.browse()
        for index, rec in enumerate(records):
            if index in template_idx:
                templated |= rec
            else:
                plain |= rec
        if plain:
            plain._ensure_server_menu_lines()
        if templated:
            templated._apply_server_menu_template()
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("phan_he_ensure_lines"):
            self._ensure_server_menu_lines()
        return res

    def web_read(self, specification):
        if self.ids and specification and "server_menu_permission_ids" in specification:
            self._ensure_server_menu_lines()
            self.invalidate_recordset(["server_menu_permission_ids"])
        return super().web_read(specification)

    def _ensure_server_menu_lines(self):
        Line = self.env["security.server.menu.permission"].sudo()
        for rec in self:
            if not rec.id:
                continue
            existing = {line.menu_key: line for line in rec.server_menu_permission_ids}
            seed = rec._server_menu_seed_flags()
            to_create = []
            for seq, (key, _label, is_group, parent) in enumerate(SERVER_MENU_TREE, start=1):
                meta = {
                    "sequence": seq * 10,
                    "is_group": is_group,
                    "parent_key": parent or False,
                }
                if key in existing:
                    line = existing[key]
                    updates = {}
                    if line.sequence != meta["sequence"]:
                        updates["sequence"] = meta["sequence"]
                    if line.is_group != is_group:
                        updates["is_group"] = is_group
                    if (line.parent_key or False) != meta["parent_key"]:
                        updates["parent_key"] = meta["parent_key"]
                    if updates:
                        line.with_context(skip_server_menu_cascade=True).write(updates)
                    continue
                vals = dict(
                    meta,
                    role_id=rec.id,
                    menu_key=key,
                    can_read=bool(seed.get("can_read")),
                    can_create=bool(seed.get("can_create")),
                    can_write=bool(seed.get("can_write")),
                    can_unlink=bool(seed.get("can_unlink")),
                    can_all=bool(seed.get("can_all")),
                )
                if key == "overview_dashboard":
                    src = existing.get("overview")
                    if src:
                        vals.update({
                            "can_read": bool(src.can_read),
                            "can_create": bool(src.can_create),
                            "can_write": bool(src.can_write),
                            "can_unlink": bool(src.can_unlink),
                            "can_all": bool(src.can_all),
                        })
                to_create.append(vals)
            if to_create:
                Line.with_context(skip_server_menu_cascade=True).create(to_create)
            for line in rec.server_menu_permission_ids:
                label = SERVER_MENU_LABEL.get(line.menu_key) or line.menu_key or ""
                expected = ("📁  %s" % label) if line.is_group else ("    └─  %s" % label)
                if line.name != expected:
                    line.with_context(skip_server_menu_cascade=True).write({"name": expected})
            rec._link_server_menu_parents()

    def _link_server_menu_parents(self):
        self.ensure_one()
        by_key = {line.menu_key: line for line in self.server_menu_permission_ids}
        for key, parent_key in SERVER_MENU_PARENT.items():
            line = by_key.get(key)
            if not line:
                continue
            parent = by_key.get(parent_key) if parent_key else False
            parent_id = parent.id if parent else False
            if line.parent_id.id != parent_id:
                line.with_context(skip_server_menu_cascade=True).write({"parent_id": parent_id})

    @api.model
    def get_user_server_menu_rights(self, user_id=None):
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        groups = self.sudo().search([
            ("user_ids", "in", user.id),
            ("active", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", user.company_ids.ids),
        ])
        bypass = (
            user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
        )
        if bypass:
            return _full_server_menu_rights()
        result = _empty_server_menu_rights()
        if not groups:
            return result
        seen = set()
        for line in groups.mapped("server_menu_permission_ids"):
            key = line.menu_key
            if key not in result:
                continue
            seen.add(key)
            result[key]["read"] = result[key]["read"] or bool(line.can_read)
            result[key]["create"] = result[key]["create"] or bool(line.can_create)
            result[key]["write"] = result[key]["write"] or bool(line.can_write)
            result[key]["unlink"] = result[key]["unlink"] or bool(line.can_unlink)
            result[key]["admin"] = result[key]["admin"] or bool(line.can_all)
        result = _inherit_overview_dashboard(result, "overview_dashboard" in seen)
        result = _fold_parent_rights(result)
        app = (self._get_user_module_rights_impl(user.id).get("server") or {})
        return _apply_app_gate_to_server_menus(result, app)

    @api.model
    def server_operation_allowed(self, menu_codes, operation, user_id=None):
        menus = self.get_user_server_menu_rights(user_id)
        codes = menu_codes if isinstance(menu_codes, (list, tuple, set)) else [menu_codes]
        return any(menu_op_allowed(menus, code, operation) for code in codes if code)

    @api.model
    def _phan_he_extend_module_rights(self, result, user_id):
        super()._phan_he_extend_module_rights(result, user_id)
        result["server_menus"] = self.get_user_server_menu_rights(user_id)
        return result


def _server_ops(read_codes, write_codes=None):
    write_codes = write_codes or read_codes
    return {
        "read": read_codes,
        "create": write_codes,
        "write": write_codes,
        "unlink": write_codes,
    }


class PhanHeItAssetServerMenu(models.Model):
    _inherit = "phan.he.it.asset"
    _server_menu_ops = _server_ops(ASSET_MENUS + ("overview",), ASSET_MENUS)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItAssetTypeServerMenu(models.Model):
    _inherit = "phan.he.it.asset.type"
    _server_menu_ops = _server_ops(
        ASSET_MENUS + ("overview", "it_settings_type"),
        ("it_settings_type",),
    )

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItCostServerMenu(models.Model):
    _inherit = "phan.he.it.cost"
    _server_menu_ops = _server_ops(COST_MENUS + REPORT_MENUS + ("overview",), COST_MENUS)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItCostPeriodServerMenu(models.Model):
    _inherit = "phan.he.it.cost.period"
    _server_menu_ops = _server_ops(COST_MENUS + REPORT_MENUS + ("overview",), COST_MENUS)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItCostCategoryServerMenu(models.Model):
    _inherit = "phan.he.it.cost.category"
    _server_menu_ops = _server_ops(
        COST_MENUS + ("overview", "it_settings_category"),
        ("it_settings_category",),
    )

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItRenewalCycleServerMenu(models.Model):
    _inherit = "phan.he.it.renewal.cycle"
    _server_menu_ops = _server_ops(
        COST_MENUS + ("overview", "it_settings_cycle"),
        ("it_settings_cycle",),
    )

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItTicketServerMenu(models.Model):
    _inherit = "phan.he.it.ticket"
    _server_menu_ops = _server_ops(TICKET_MENUS + ("overview",), TICKET_MENUS)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)


class PhanHeItReminderServerMenu(models.Model):
    _inherit = "phan.he.it.reminder.config"
    _server_menu_ops = _server_ops(("it_settings_remind", "settings"))

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        codes = self._server_menu_ops.get(operation)
        if not codes:
            return None
        return _guard_server_menus(self, operation, codes)
