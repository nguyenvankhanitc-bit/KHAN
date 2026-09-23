# -*- coding: utf-8 -*-

from odoo import api, fields, models

# (menu_code, menu_name, is_folder, parent_code)
INTERNET_MENU_TREE = [
    ("menu_overview", "TỔNG QUAN", True, False),
    ("overview_dashboard", "Tổng quan Dashboard", False, "menu_overview"),
    ("group_manage_internet", "QUẢN LÝ INTERNET", True, False),
    ("internet_active", "Đang sử dụng", False, "group_manage_internet"),
    ("internet_suspend", "Tạm ngưng", False, "group_manage_internet"),
    ("internet_liquidation", "Thanh lý", False, "group_manage_internet"),
    ("internet_entry", "Nhập thông tin", False, "group_manage_internet"),
    ("group_cost_payment", "CHI PHÍ & THANH TOÁN", True, False),
    ("payment_schedule", "Danh sách thanh toán", False, "group_cost_payment"),
    ("payment_confirm", "Xác nhận TT", False, "group_cost_payment"),
    ("payment_overdue", "Quá hạn", False, "group_cost_payment"),
    ("payment_forecast", "Dự kiến thanh toán", False, "group_cost_payment"),
    ("group_reports", "BÁO CÁO", True, False),
    ("report_month", "Chi phí tháng", False, "group_reports"),
    ("report_quarter", "Chi phí quý", False, "group_reports"),
    ("report_year", "Chi phí năm", False, "group_reports"),
    ("group_settings", "CÀI ĐẶT", True, False),
    ("setting_store", "Cửa hàng", False, "group_settings"),
    ("setting_area", "Khu vực / Chi nhánh", False, "group_settings"),
    ("setting_region", "Miền", False, "group_settings"),
    ("setting_provider", "Nhà cung cấp", False, "group_settings"),
    ("setting_bank", "Tài khoản ngân hàng", False, "group_settings"),
]

INTERNET_MENU_LABEL = {code: name for code, name, _f, _p in INTERNET_MENU_TREE}
INTERNET_MENU_IS_FOLDER = {code: is_folder for code, _n, is_folder, _p in INTERNET_MENU_TREE}
INTERNET_MENU_PARENT = {code: parent or False for code, _n, _f, parent in INTERNET_MENU_TREE}
INTERNET_MENU_CODES = [code for code, _n, _f, _p in INTERNET_MENU_TREE]

PARENT_CHILD = {}
for code, _name, _is_folder, parent in INTERNET_MENU_TREE:
    if parent:
        PARENT_CHILD.setdefault(parent, []).append(code)
PARENT_CHILD = {k: tuple(v) for k, v in PARENT_CHILD.items()}

# Menu cũ → menu mới (giữ quyền khi gom sidebar Chi phí & thanh toán).
LEGACY_INTERNET_MENU_MAP = {
    "payment_tracking": "payment_confirm",
    "payment_track": "payment_confirm",
    "alert_overdue": "payment_overdue",
    "alert_due_soon": "payment_schedule",
    "expire_soon": "payment_schedule",
    "expired": "payment_overdue",
}
OBSOLETE_INTERNET_MENU_CODES = frozenset(
    {
        "group_alerts",
        "payment_tracking",
        "payment_track",
        "alert_overdue",
        "alert_due_soon",
        "expire_soon",
        "expired",
    }
)

PERM_BOOLS = ("can_read", "can_create", "can_write", "can_unlink")
OP_TO_MENU_FLAG = {
    "read": "read",
    "create": "create",
    "write": "write",
    "unlink": "unlink",
}
STATUS_TO_MENU = {
    "active": "internet_active",
    "suspend": "internet_suspend",
    "liquidated": "internet_liquidation",
}
SERVICE_READ_MENUS = (
    "internet_active",
    "internet_suspend",
    "internet_liquidation",
    "internet_entry",
    "report_month",
    "report_quarter",
    "report_year",
    "payment_schedule",
    "payment_confirm",
    "payment_overdue",
    "payment_forecast",
    "overview_dashboard",
)


def menu_op_allowed(menus, menu_code, operation):
    row = (menus or {}).get(menu_code) or {}
    if row.get("admin"):
        return True
    flag = OP_TO_MENU_FLAG.get(operation)
    return bool(flag and row.get(flag))



def _empty_internet_menu_rights():
    return {
        code: {"read": False, "create": False, "write": False, "unlink": False, "admin": False}
        for code in INTERNET_MENU_CODES
    }


def _full_internet_menu_rights():
    return {
        code: {"read": True, "create": True, "write": True, "unlink": True, "admin": True}
        for code in INTERNET_MENU_CODES
    }


def _fold_parent_rights(result):
    """Chỉ đẩy quyền lên folder cha. Không lan từ 1 menu con sang các anh em."""
    for parent, children in PARENT_CHILD.items():
        if parent not in result:
            continue
        for child in children:
            row = result.get(child) or {}
            for op in ("read", "create", "write", "unlink", "admin"):
                result[parent][op] = result[parent][op] or bool(row.get(op))
    return result


class SecurityInternetMenuPermission(models.Model):
    _name = "security.internet.menu.permission"
    _description = "Chi tiết phân quyền Menu Internet"
    _order = "sequence, id"

    role_id = fields.Many2one(
        "phan.he.module.access",
        string="Nhóm quyền",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    menu_name = fields.Char(string="Tên menu", compute="_compute_menu_name", store=True, readonly=False)
    menu_code = fields.Char(string="Mã menu", required=True, index=True)
    parent_id = fields.Many2one(
        "security.internet.menu.permission",
        string="Menu cha",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many(
        "security.internet.menu.permission",
        "parent_id",
        string="Menu con",
    )
    is_folder = fields.Boolean(string="Thư mục nhóm", default=False)
    can_read = fields.Boolean(string="XEM", default=False)
    can_create = fields.Boolean(string="THÊM", default=False)
    can_write = fields.Boolean(string="SỬA", default=False)
    can_unlink = fields.Boolean(string="XÓA", default=False)
    can_admin = fields.Boolean(string="QUẢN TRỊ", default=False)

    _menu_code_uniq = models.Constraint(
        "unique(role_id, menu_code)",
        "Mỗi menu Internet chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.depends("menu_code", "is_folder")
    def _compute_menu_name(self):
        for rec in self:
            label = INTERNET_MENU_LABEL.get(rec.menu_code) or rec.menu_code or ""
            if rec.is_folder:
                rec.menu_name = "📁  %s" % label
            else:
                rec.menu_name = "    └─  %s" % label

    @api.onchange("can_admin")
    def _onchange_can_admin(self):
        if self.can_admin:
            self.can_read = self.can_create = self.can_write = self.can_unlink = True
            for child in self.child_ids:
                child.can_admin = True
                child.can_read = child.can_create = child.can_write = child.can_unlink = True

    def write(self, vals):
        vals = dict(vals)
        if any(vals.get(fname) for fname in ("can_create", "can_write", "can_unlink", "can_admin")):
            vals["can_read"] = True
        if vals.get("can_admin") and not self.env.context.get("skip_internet_menu_cascade"):
            for fname in PERM_BOOLS:
                vals.setdefault(fname, True)
        res = super().write(vals)
        if self.env.context.get("skip_internet_menu_cascade"):
            return res
        if vals.get("can_admin"):
            for rec in self:
                child_vals = {fname: True for fname in PERM_BOOLS}
                child_vals["can_admin"] = True
                rec.child_ids.with_context(skip_internet_menu_cascade=True).write(child_vals)
        # Không ép logout tại đây — chỉ áp dụng khi form nhóm bấm Lưu
        # (xem phan.he.module.access.write + internet_menu_permission_ids).
        return res


class PhanHeModuleAccessInternetMenu(models.Model):
    _inherit = "phan.he.module.access"

    internet_menu_permission_ids = fields.One2many(
        "security.internet.menu.permission",
        "role_id",
        string="Phân quyền Menu Internet",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "internet_menu_permission_ids" in fields_list and not res.get("internet_menu_permission_ids"):
            res["internet_menu_permission_ids"] = self._default_internet_menu_commands()
        return res

    @api.model
    def _default_internet_menu_commands(self):
        commands = []
        for seq, (code, _name, is_folder, _parent) in enumerate(INTERNET_MENU_TREE, start=1):
            commands.append((0, 0, {
                "sequence": seq * 10,
                "menu_code": code,
                "is_folder": is_folder,
            }))
        return commands

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_internet_menu_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("phan_he_ensure_lines"):
            self._ensure_internet_menu_lines()
        return res

    def _register_hook(self):
        super()._register_hook()
        # Bỏ ensure toàn bộ nhóm lúc boot — tránh làm chậm khởi động/login.

    @api.model
    def _phan_he_extend_module_rights(self, result, user_id):
        super()._phan_he_extend_module_rights(result, user_id)
        result["internet_menus"] = self.get_user_internet_menu_rights(user_id)
        return result

    def _migrate_legacy_internet_menu_lines(self):
        """Gộp quyền menu cũ (Theo dõi / Cảnh báo) sang 4 mục thanh toán mới."""
        Line = self.env["security.internet.menu.permission"].sudo()
        for rec in self:
            if not rec.id:
                continue
            by_code = {line.menu_code: line for line in rec.internet_menu_permission_ids}
            for old_code, new_code in LEGACY_INTERNET_MENU_MAP.items():
                old = by_code.get(old_code)
                if not old or not new_code:
                    continue
                target = by_code.get(new_code)
                flags = {
                    "can_read": bool(old.can_read),
                    "can_create": bool(old.can_create),
                    "can_write": bool(old.can_write),
                    "can_unlink": bool(old.can_unlink),
                    "can_admin": bool(old.can_admin),
                }
                if target:
                    updates = {}
                    for fname, val in flags.items():
                        if val and not target[fname]:
                            updates[fname] = True
                    if updates:
                        target.with_context(skip_internet_menu_cascade=True).write(updates)
                    old.with_context(skip_internet_menu_cascade=True).unlink()
                else:
                    old.with_context(skip_internet_menu_cascade=True).write(
                        {"menu_code": new_code}
                    )
                    by_code[new_code] = old
                by_code.pop(old_code, None)
            obsolete = rec.internet_menu_permission_ids.filtered(
                lambda l: l.menu_code in OBSOLETE_INTERNET_MENU_CODES
                or l.menu_code not in INTERNET_MENU_CODES
            )
            if obsolete:
                obsolete.with_context(skip_internet_menu_cascade=True).unlink()

    def _ensure_internet_menu_lines(self):
        Line = self.env["security.internet.menu.permission"]
        self._migrate_legacy_internet_menu_lines()
        for rec in self:
            if not rec.id:
                continue
            existing = {line.menu_code: line for line in rec.internet_menu_permission_ids}
            to_create = []
            for seq, (code, _name, is_folder, _parent) in enumerate(INTERNET_MENU_TREE, start=1):
                meta = {"sequence": seq * 10, "is_folder": is_folder}
                if code in existing:
                    line = existing[code]
                    updates = {}
                    if line.sequence != meta["sequence"]:
                        updates["sequence"] = meta["sequence"]
                    if line.is_folder != is_folder:
                        updates["is_folder"] = is_folder
                    if updates:
                        line.with_context(skip_internet_menu_cascade=True).write(updates)
                    continue
                to_create.append(dict(
                    meta,
                    role_id=rec.id,
                    menu_code=code,
                ))
            if to_create:
                Line.create(to_create)
            # Đổi tên hiển thị theo cây menu mới (stored compute).
            for line in rec.internet_menu_permission_ids:
                label = INTERNET_MENU_LABEL.get(line.menu_code) or line.menu_code or ""
                expected = ("📁  %s" % label) if line.is_folder else ("    └─  %s" % label)
                if line.menu_name != expected:
                    line.with_context(skip_internet_menu_cascade=True).write({"menu_name": expected})
            rec._link_internet_menu_parents()

    def _link_internet_menu_parents(self):
        self.ensure_one()
        by_code = {line.menu_code: line for line in self.internet_menu_permission_ids}
        for code, parent_code in INTERNET_MENU_PARENT.items():
            line = by_code.get(code)
            if not line:
                continue
            parent = by_code.get(parent_code) if parent_code else False
            parent_id = parent.id if parent else False
            if line.parent_id.id != parent_id:
                line.with_context(skip_internet_menu_cascade=True).write({"parent_id": parent_id})

    @api.model
    def get_user_internet_menu_rights(self, user_id=None):
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
        )
        if bypass:
            return _full_internet_menu_rights()
        result = _empty_internet_menu_rights()
        if not groups:
            return result
        for line in groups.mapped("internet_menu_permission_ids"):
            code = LEGACY_INTERNET_MENU_MAP.get(line.menu_code, line.menu_code)
            if code not in result:
                continue
            result[code]["read"] = result[code]["read"] or bool(line.can_read)
            result[code]["create"] = result[code]["create"] or bool(line.can_create)
            result[code]["write"] = result[code]["write"] or bool(line.can_write)
            result[code]["unlink"] = result[code]["unlink"] or bool(line.can_unlink)
            result[code]["admin"] = result[code]["admin"] or bool(line.can_admin)
        return _fold_parent_rights(result)

    @api.model
    def internet_operation_allowed(self, menu_codes, operation, user_id=None):
        menus = self.get_user_internet_menu_rights(user_id)
        codes = menu_codes if isinstance(menu_codes, (list, tuple, set)) else [menu_codes]
        return any(menu_op_allowed(menus, code, operation) for code in codes if code)
