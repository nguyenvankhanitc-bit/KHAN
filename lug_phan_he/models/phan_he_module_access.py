# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
import copy
import logging


SERVICE_MODULES = [
    ("internet", "Dịch vụ Internet", "/lug_phan_he/static/description/icon_hub_internet.png"),
    ("camera", "Dịch vụ Camera", "/lug_phan_he/static/description/icon_hub_camera.png"),
    ("attendance", "Máy chấm công", "/lug_phan_he/static/description/icon_hub_attendance.png"),
    ("server", "Máy chủ", "/lug_phan_he/static/description/icon_hub_server.png"),
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
    _order = "summary_sequence, name, id"

    # Bốn mục trên màn Tổng hợp phân quyền.
    SERVICE_BUCKETS = (
        ("internet", "Dịch vụ Internet", 10),
        ("camera", "Dịch vụ Camera", 20),
        ("server", "Máy chủ", 30),
        ("linkq_nb", "LinkQ ERP", 40),
    )

    name = fields.Char(
        string="Tên nhóm",
        required=True,
        translate=True,
        default="Nhóm quyền mới",
        help="Tự lấy theo Nhóm quyền Lug Security — không cần nhập riêng.",
    )
    code = fields.Char(string="Code", index=True)
    summary_sequence = fields.Integer(default=100, index=True)
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

    @api.onchange("group_ids")
    def _onchange_group_ids_sync_name(self):
        """Bỏ lớp tên thừa — đồng bộ nhãn theo nhóm Lug Security."""
        if not self.group_ids:
            return
        main = self.group_ids[:1]
        self.name = main.name or self.name or "Nhóm quyền"
        if main.code and (not self.code or self.code in ("", "new")):
            self.code = main.code

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
    show_menu_linkq = fields.Boolean(
        string="Hiện tab Menu LinkQ",
        compute="_compute_show_menu_pages",
    )
    show_menu_server = fields.Boolean(
        string="Hiện tab Menu Máy chủ",
        compute="_compute_show_menu_pages",
    )
    show_menu_internet = fields.Boolean(
        string="Hiện tab Menu Internet",
        compute="_compute_show_menu_pages",
    )
    show_menu_store = fields.Boolean(
        string="Hiện tab Cửa hàng",
        compute="_compute_show_menu_pages",
    )

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

    @api.depends("code", "line_ids.service_code", "line_ids.perm_view", "line_ids.perm_admin")
    def _compute_show_menu_pages(self):
        """Chỉ hiện tab menu chi tiết khi nhóm thực sự dùng app đó — tránh dư thừa trên form Camera."""
        for rec in self:
            lines = {line.service_code: line for line in rec.line_ids}
            linkq_scope = rec._is_linkq_scope() if rec.id or rec.code else False
            has_linkq = linkq_scope or bool(
                lines.get("linkq_nb") and (lines["linkq_nb"].perm_view or lines["linkq_nb"].perm_admin)
            )
            has_server = bool(
                (rec.code or "").strip().lower() == "server"
                or (lines.get("server") and (lines["server"].perm_view or lines["server"].perm_admin))
            )
            has_internet = bool(
                (rec.code or "").strip().lower() == "internet"
                or (lines.get("internet") and (lines["internet"].perm_view or lines["internet"].perm_admin))
            )
            rec.show_menu_linkq = has_linkq
            rec.show_menu_server = has_server
            rec.show_menu_internet = has_internet
            rec.show_menu_store = has_linkq

    @api.depends("group_ids", "group_ids.user_ids", "custom_user_ids")
    def _compute_effective_users(self):
        for rec in self:
            lug_group_users = rec.group_ids.sudo().mapped("user_ids")
            lug_group_users = lug_group_users.filtered(lambda u: u.active and not u.share)
            rec.user_ids = lug_group_users | rec.custom_user_ids

    def _register_hook(self):
        super()._register_hook()
        # Không chạy ensure hàng loạt lúc load registry (làm chậm boot/login).
        # Dòng quyền được tạo khi create nhóm / khi mở form.

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

    def _vals_sync_name_from_groups(self, vals):
        """Khi có group_ids mà thiếu name/code → lấy từ lug.group."""
        if not vals.get("group_ids"):
            if not vals.get("name"):
                vals["name"] = "Nhóm quyền mới"
            return vals
        gids = []
        for cmd in vals.get("group_ids") or []:
            if isinstance(cmd, (list, tuple)) and cmd:
                if cmd[0] == 6:
                    gids = list(cmd[2] or [])
                elif cmd[0] == 4:
                    gids.append(cmd[1])
        if gids:
            group = self.env["lug.group"].browse(gids[0])
            if not vals.get("name") or vals.get("name") in ("Nhóm quyền mới",):
                vals["name"] = group.name or "Nhóm quyền"
            if not vals.get("code") and group.code:
                vals["code"] = group.code
        if not vals.get("name"):
            vals["name"] = "Nhóm quyền mới"
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._vals_sync_name_from_groups(vals)
            if not vals.get("line_ids"):
                vals["line_ids"] = self._default_module_line_commands()
        records = super().create(vals_list)
        records._ensure_module_lines()
        records.mapped("user_ids")._phan_he_force_logout()
        return records

    def write(self, vals):
        if "group_ids" in vals and not self.env.context.get("skip_name_sync"):
            self._vals_sync_name_from_groups(vals)
        before_users = self.mapped("user_ids")
        res = super().write(vals)
        # Chỉ seed dòng quyền khi form/nhóm mới cần — tránh rewrite nặng mỗi lần Lưu.
        if self.env.context.get("phan_he_ensure_lines"):
            self._ensure_module_lines()
        logout_keys = {
            "group_ids",
            "custom_user_ids",
            "user_ids",
            "line_ids",
            "menu_permission_line_ids",
            "internet_menu_permission_ids",
            "camera_menu_permission_ids",
            "server_menu_permission_ids",
            "store_permission_ids",
            "active",
        }
        if set(vals) & logout_keys:
            (before_users | self.mapped("user_ids"))._phan_he_force_logout()
        return res

    def _phan_he_logout_users(self):
        self.mapped("user_ids")._phan_he_force_logout()

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

    @api.model
    def _ensure_service_buckets(self):
        """Bốn dịch vụ cố định trên Tổng hợp phân quyền."""
        if self.env.context.get("skip_service_buckets"):
            return self.browse()
        Access = self.sudo().with_context(
            skip_service_buckets=True,
            phan_he_service_buckets=False,
        )
        records = Access.browse()
        for code, name, sequence in self.SERVICE_BUCKETS:
            rec = Access.search([("code", "=", code)], limit=1)
            if not rec and code == "linkq_nb":
                rec = Access.search([("name", "ilike", "LINKQ ERP")], limit=1)
            vals = {"name": name, "code": code, "summary_sequence": sequence, "active": True}
            if rec:
                to_write = {}
                for lang in ("vi_VN", "en_US"):
                    if rec.with_context(lang=lang).name != name:
                        rec.with_context(lang=lang).write({"name": name})
                for key in ("code", "summary_sequence", "active"):
                    if rec[key] != vals[key]:
                        to_write[key] = vals[key]
                if to_write:
                    rec.write(to_write)
            else:
                rec = Access.with_context(lang="vi_VN").create(vals)
                if rec.with_context(lang="en_US").name != name:
                    rec.with_context(lang="en_US").write({"name": name})
            records |= rec
        return records

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        if self.env.context.get("phan_he_service_buckets"):
            self._ensure_service_buckets()
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )

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
        """Trả về dict {service_code: {view, create, edit, delete, ...}} (có cache)."""
        try:
            uid = int(user_id or self.env.uid)
            user = self.env["res.users"].sudo().browse(uid)
            stamp = user.phan_he_access_stamp or "0"
            # deepcopy: tránh caller mutate làm bẩn ormcache
            return copy.deepcopy(self._cached_user_module_rights(uid, stamp))
        except Exception:
            # Không nuốt lỗi im lặng: ghi log để biết vì sao hub trống
            logging.getLogger(__name__).exception("lug_phan_he: get_user_module_rights lỗi (user %s)", user_id or self.env.uid)
            return self._blank_rights(view=False)

    @api.model
    @tools.ormcache("uid", "stamp")
    def _cached_user_module_rights(self, uid, stamp):
        result = self._get_user_module_rights_impl(uid)
        self._phan_he_extend_module_rights(result, uid)
        return result

    @api.model
    def _phan_he_extend_module_rights(self, result, user_id):
        """Hook cho inherit (LinkQ / Internet menu rights)."""
        return result

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

    def write(self, vals):
        res = super().write(vals)
        if set(vals) & set(PERM_FIELDS):
            self.mapped("access_id.user_ids")._phan_he_force_logout()
        return res

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
