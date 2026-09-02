# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


SERVICE_MODULES = [
    ("internet", "Dịch vụ Internet", "/lug_phan_he/static/description/icon_hub_internet.png"),
    ("camera", "Dịch vụ Camera", "/lug_phan_he/static/description/icon_hub_camera.png"),
    ("attendance", "Máy chấm công", "/lug_phan_he/static/description/icon_hub_attendance.png"),
    ("server", "Máy chủ & Cloud", "/lug_phan_he/static/description/icon_hub_server.png"),
    ("linkq_nb", "LinkQ ERP", "/lug_phan_he/static/description/icon_hub_erp.png"),
]

SERVICE_SELECTION = [(code, name) for code, name, _icon in SERVICE_MODULES]
SERVICE_ICON_MAP = {code: icon for code, _name, icon in SERVICE_MODULES}
SERVICE_NAME_MAP = {code: name for code, name, _icon in SERVICE_MODULES}

NON_LINKQ_SERVICES = ("internet", "camera", "attendance", "server")
LINKQ_SCOPE_CODES = frozenset(
    {
        "preset_view",
        "preset_staff",
        "preset_store_mgr",
        "preset_region_mgr",
        "preset_admin",
        "linkq_nb",
        "linkq",
        "linkq_erp",
    }
)

PERM_FIELDS = (
    "perm_view",
    "perm_create",
    "perm_edit",
    "perm_delete",
    "perm_approve",
    "perm_export",
    "perm_import",
    "perm_print",
    "perm_admin",
)


class PhanHeModuleAccess(models.Model):
    """Nhóm quyền phân hệ dịch vụ — UI giống lug.group."""

    _name = "phan.he.module.access"
    _description = "Nhóm quyền phân hệ dịch vụ"
    _order = "name"

    name = fields.Char(string="Tên nhóm", required=True, translate=True)
    code = fields.Char(string="Code", index=True)
    active = fields.Boolean(default=True)
    description = fields.Text(string="Mô tả")
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        default=lambda self: self.env.company,
        required=True,
    )
    group_ids = fields.Many2many(
        "lug.group",
        "phan_he_module_access_lug_group_rel",
        "access_id",
        "group_id",
        string="Nhóm quyền",
        help="Nhóm quyền Lug Security (lug.group). Toàn bộ user trong nhóm được áp dụng quyền.",
    )
    custom_user_ids = fields.Many2many(
        "res.users",
        "phan_he_module_access_custom_user_rel",
        "access_id",
        "user_id",
        string="Người dùng ngoại lệ",
        help="User lẻ ngoài các nhóm đã chọn.",
    )
    user_ids = fields.Many2many(
        "res.users",
        "phan_he_module_access_users_rel",
        "access_id",
        "user_id",
        string="Người dùng",
        compute="_compute_effective_users",
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "phan.he.module.access.line",
        "access_id",
        string="Phân quyền dịch vụ",
        copy=True,
    )
    user_count = fields.Integer(compute="_compute_user_count", string="Users")

    LINKQ_PRESET_DEFS = (
        ("preset_view", "Chỉ xem", ()),
        ("preset_staff", "Nhân viên ca", ()),
        ("preset_store_mgr", "Quản lý cửa hàng", ()),
        ("preset_region_mgr", "Quản lý miền", ()),
        ("preset_admin", "Toàn quyền (Admin)", ()),
    )

    def _is_linkq_scope(self):
        """Nhóm preset / LinkQ ERP: chỉ điều khiển lịch ca, không mở Internet/Camera/..."""
        self.ensure_one()
        try:
            code = str(self.code or "").strip().lower()
            name = str(self.name or "").casefold()
            if code.startswith("preset_") or code in LINKQ_SCOPE_CODES:
                return True
            if "linkq" in name or "erp" in name:
                return True
            return False
        except Exception:
            return True

    @api.depends("user_ids")
    def _compute_user_count(self):
        for rec in self:
            rec.user_count = len(rec.user_ids)

    @api.depends("group_ids", "group_ids.user_ids", "custom_user_ids")
    def _compute_effective_users(self):
        for rec in self:
            lug_group_users = rec.group_ids.sudo().mapped("user_ids")
            lug_group_users = lug_group_users.filtered(lambda u: u.active and not u.share)
            rec.user_ids = lug_group_users | rec.custom_user_ids

    def _register_hook(self):
        super()._register_hook()
        try:
            self.sudo()._ensure_linkq_presets()
            all_groups = self.sudo().search([])
            all_groups._ensure_module_lines()
            if hasattr(self, "_ensure_menu_lines"):
                all_groups._ensure_menu_lines()
        except Exception:
            pass

    @api.model
    def _ensure_linkq_presets(self):
        company = self.env.company or self.env.ref("base.main_company", raise_if_not_found=False)
        company_id = company.id if company else False
        for code, name, _xmlids in self.LINKQ_PRESET_DEFS:
            rec = self.search([("code", "=", code)], limit=1)
            vals = {"name": name, "code": code, "active": True}
            if company_id and not rec:
                vals["company_id"] = company_id
            if rec:
                if rec.name != name:
                    rec.write({"name": name})
            else:
                self.create(vals)

    @api.model
    def _default_module_line_commands(self):
        return [
            (0, 0, {
                "service_code": code,
                "sequence": (idx + 1) * 10,
            })
            for idx, (code, _name, _icon) in enumerate(SERVICE_MODULES)
        ]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "line_ids" in fields_list and not res.get("line_ids"):
            res["line_ids"] = self._default_module_line_commands()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("line_ids"):
                vals["line_ids"] = self._default_module_line_commands()
        records = super().create(vals_list)
        records._ensure_module_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_module_lines()
        return res

    def _ensure_module_lines(self):
        Line = self.env["phan.he.module.access.line"].sudo()
        for rec in self:
            if not rec.id:
                continue
            existing = set(rec.line_ids.mapped("service_code"))
            to_create = []
            for idx, (code, _name, _icon) in enumerate(SERVICE_MODULES):
                if code in existing:
                    continue
                to_create.append({
                    "access_id": rec.id,
                    "service_code": code,
                    "sequence": (idx + 1) * 10,
                })
            if to_create:
                Line.create(to_create)

    def action_open_users(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "res.users",
            "view_mode": "list,form",
            "domain": [("id", "in", self.user_ids.ids)],
        }

    def _blank_rights(self, view=False, full=False):
        flag = bool(full)
        return {
            code: {
                "view": True if full else bool(view),
                "create": flag,
                "edit": flag,
                "delete": flag,
                "approve": flag,
                "export": flag,
                "import": flag,
                "print": flag,
                "admin": flag,
                "name": name,
                "icon": icon,
            }
            for code, name, icon in SERVICE_MODULES
        }

    @api.model
    def get_user_module_rights(self, user_id=None):
        """Trả về dict {service_code: {view, create, edit, delete, ...}}."""
        try:
            return self._get_user_module_rights_impl(user_id)
        except Exception:
            return self._blank_rights(view=False)

    @api.model
    def _get_user_module_rights_impl(self, user_id=None):
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        groups = self.sudo().search([
            ("user_ids", "in", user.id),
            ("active", "=", True),
        ])
        is_full_admin = (
            user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
        )
        if is_full_admin:
            return self._blank_rights(full=True)

        result = self._blank_rights(view=False)

        if not groups:
            return result

        def _merge_line(line):
            code = line.service_code
            if code not in result:
                return
            result[code]["view"] = result[code]["view"] or bool(line.perm_view)
            result[code]["create"] = result[code]["create"] or bool(line.perm_create)
            result[code]["edit"] = result[code]["edit"] or bool(line.perm_edit)
            result[code]["delete"] = result[code]["delete"] or bool(line.perm_delete)
            result[code]["approve"] = result[code]["approve"] or bool(line.perm_approve)
            result[code]["export"] = result[code]["export"] or bool(line.perm_export)
            result[code]["import"] = result[code]["import"] or bool(line.perm_import)
            result[code]["print"] = result[code]["print"] or bool(line.perm_print)
            result[code]["admin"] = result[code]["admin"] or bool(line.perm_admin)

        for rec in groups:
            group_code = (rec.code or "").strip().lower()
            if rec._is_linkq_scope():
                result["linkq_nb"]["view"] = True
                for line in rec.line_ids:
                    if line.service_code == "linkq_nb":
                        _merge_line(line)
                continue
            if group_code in result:
                result[group_code]["view"] = True
            for line in rec.line_ids:
                _merge_line(line)
        return result


class PhanHeModuleAccessLine(models.Model):
    _name = "phan.he.module.access.line"
    _description = "Chi tiết quyền phân hệ dịch vụ"
    _order = "sequence, id"

    access_id = fields.Many2one(
        "phan.he.module.access",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    service_code = fields.Selection(
        selection=SERVICE_SELECTION,
        string="App",
        required=True,
    )
    service_name = fields.Char(
        string="Dịch vụ con",
        compute="_compute_service_meta",
        store=True,
    )
    icon_url = fields.Char(
        string="Icon",
        compute="_compute_service_meta",
        store=True,
    )
    perm_view = fields.Boolean(string="Xem", default=False)
    perm_create = fields.Boolean(string="Thêm", default=False)
    perm_edit = fields.Boolean(string="Sửa", default=False)
    perm_delete = fields.Boolean(string="Xóa", default=False)
    perm_approve = fields.Boolean(string="Duyệt", default=False)
    perm_export = fields.Boolean(string="Xuất", default=False)
    perm_import = fields.Boolean(string="Nhập", default=False)
    perm_print = fields.Boolean(string="In", default=False)
    perm_admin = fields.Boolean(string="Quản trị", default=False)

    _access_service_uniq = models.Constraint(
        "unique(access_id, service_code)",
        "Mỗi phân hệ chỉ xuất hiện một lần trong nhóm quyền.",
    )

    @api.depends("service_code")
    def _compute_service_meta(self):
        for rec in self:
            code = rec.service_code or ""
            rec.service_name = SERVICE_NAME_MAP.get(code, code)
            rec.icon_url = SERVICE_ICON_MAP.get(code, "")

    @api.constrains(*PERM_FIELDS)
    def _check_view_required(self):
        for rec in self:
            if rec.perm_view:
                continue
            if any(rec[fname] for fname in PERM_FIELDS if fname != "perm_view"):
                raise ValidationError(
                    "Phân hệ '%s': cần bật Xem trước khi cấp quyền khác."
                    % (rec.service_name or rec.service_code)
                )
