# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


SERVICE_MODULES = [
    ("internet", "Dịch vụ Internet", "/lug_phan_he/static/description/icon_hub_internet.png"),
    ("camera", "Dịch vụ Camera", "/lug_phan_he/static/description/icon_hub_camera.png"),
    ("attendance", "Máy chấm công", "/lug_phan_he/static/description/icon_hub_attendance.png"),
    ("server", "Máy chủ & Cloud", "/lug_phan_he/static/description/icon_hub_server.png"),
    ("linkq_nb", "LinkQ ERP", "/lug_phan_he/static/description/icon_hub_erp.png"),
    ("linkq_hrm", "LinkQ HRM", "/lug_phan_he/static/description/icon_hub_hrm.png"),
]

SERVICE_SELECTION = [(code, name) for code, name, _icon in SERVICE_MODULES]
SERVICE_ICON_MAP = {code: icon for code, _name, icon in SERVICE_MODULES}
SERVICE_NAME_MAP = {code: name for code, name, _icon in SERVICE_MODULES}

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
    user_ids = fields.Many2many(
        "res.users",
        "phan_he_module_access_users_rel",
        "access_id",
        "user_id",
        string="Người dùng",
    )
    line_ids = fields.One2many(
        "phan.he.module.access.line",
        "access_id",
        string="Phân quyền dịch vụ",
        copy=True,
    )
    user_count = fields.Integer(compute="_compute_user_count", string="Users")

    @api.depends("user_ids")
    def _compute_user_count(self):
        for rec in self:
            rec.user_count = len(rec.user_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_module_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "line_ids" in vals:
            self._ensure_module_lines()
        return res

    def _ensure_module_lines(self):
        Line = self.env["phan.he.module.access.line"]
        for rec in self:
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

    @api.model
    def get_user_module_rights(self, user_id=None):
        """Trả về dict {service_code: {view, create, edit, delete, ...}}."""
        user = self.env["res.users"].browse(user_id or self.env.user.id)
        if user.has_group("lug_phan_he.group_phan_he_admin") or user.has_group("base.group_system"):
            return {
                code: {
                    "view": True,
                    "create": True,
                    "edit": True,
                    "delete": True,
                    "approve": True,
                    "export": True,
                    "import": True,
                    "print": True,
                    "admin": True,
                    "name": name,
                    "icon": icon,
                }
                for code, name, icon in SERVICE_MODULES
            }

        result = {
            code: {
                "view": False,
                "create": False,
                "edit": False,
                "delete": False,
                "approve": False,
                "export": False,
                "import": False,
                "print": False,
                "admin": False,
                "name": name,
                "icon": icon,
            }
            for code, name, icon in SERVICE_MODULES
        }

        groups = self.sudo().search([
            ("user_ids", "in", user.id),
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ])
        if not groups:
            # Chưa cấu hình: cho xem tất cả để không khóa hệ thống
            for code in result:
                result[code]["view"] = True
            return result

        for line in groups.mapped("line_ids"):
            code = line.service_code
            if code not in result:
                continue
            result[code]["view"] = result[code]["view"] or bool(line.perm_view)
            result[code]["create"] = result[code]["create"] or bool(line.perm_create)
            result[code]["edit"] = result[code]["edit"] or bool(line.perm_edit)
            result[code]["delete"] = result[code]["delete"] or bool(line.perm_delete)
            result[code]["approve"] = result[code]["approve"] or bool(line.perm_approve)
            result[code]["export"] = result[code]["export"] or bool(line.perm_export)
            result[code]["import"] = result[code]["import"] or bool(line.perm_import)
            result[code]["print"] = result[code]["print"] or bool(line.perm_print)
            result[code]["admin"] = result[code]["admin"] or bool(line.perm_admin)
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
