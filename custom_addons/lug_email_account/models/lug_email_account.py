# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

POSITION_SELECTION = [
    ("director", "Giám đốc"),
    ("deputy_director", "Phó Giám đốc"),
    ("dept_head", "Trưởng phòng"),
    ("deputy_head", "Phó phòng"),
    ("team_lead", "Trưởng nhóm"),
    ("staff", "Nhân viên"),
    ("warehouse_keeper", "Thủ kho"),
    ("accountant", "Kế toán"),
    ("hr", "HCNS"),
    ("marketing", "Marketing"),
    ("it", "IT"),
    ("other", "Khác"),
]

POSITION_IMPORT_MAP = {
    label.lower(): key for key, label in POSITION_SELECTION
}

STATE_IMPORT_MAP = {
    "đang sử dụng": "active",
    "tam khoa": "lock",
    "tạm khóa": "lock",
    "hủy": "cancel",
    "huy": "cancel",
}



class LugEmailAccount(models.Model):
    _name = "lug.email.account"
    _description = "Tài khoản email"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "stt asc, id asc"
    _rec_name = "email"

    stt = fields.Integer(
        string="STT",
        copy=False,
        index=True,
    )
    date_created = fields.Char(
        string="Ngày tạo",
        tracking=True,
        help="Nhập dạng text, ví dụ: 06/07/2026",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        tracking=True,
        ondelete="set null",
    )
    department = fields.Char(
        string="Phòng ban (text)",
        tracking=True,
        help="Tên phòng ban hiển thị trên danh sách, tự đồng bộ khi chọn phòng ban HR.",
    )
    function_name = fields.Char(
        string="Chức năng",
        tracking=True,
    )
    employee_name = fields.Char(
        string="Họ và tên nhân viên",
        required=True,
        tracking=True,
        help="Tên hiển thị trên danh mục email, không bắt buộc liên kết hồ sơ nhân sự.",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Liên kết nhân viên",
        tracking=True,
        ondelete="set null",
        help="Tùy chọn — chỉ dùng khi cần liên kết với hồ sơ nhân sự.",
    )
    email = fields.Char(
        string="Email",
        required=True,
        tracking=True,
    )
    position = fields.Selection(
        selection=POSITION_SELECTION,
        string="Vị trí",
        default="other",
        tracking=True,
    )
    purpose = fields.Text(
        string="Mục đích sử dụng",
    )
    usage_target = fields.Text(
        string="Đối tượng sử dụng",
        default="Nội bộ",
        tracking=True,
        help="Nhập tự do, ví dụ: Cá nhân, Nội bộ, Đối tác, Nhà cung cấp...",
    )
    status_id = fields.Many2one(
        "lug.email.account.status",
        string="Trạng thái",
        tracking=True,
        ondelete="restrict",
    )
    status_code = fields.Char(
        related="status_id.code",
        string="Mã trạng thái",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        default=lambda self: self.env.company,
        required=True,
    )
    active = fields.Boolean(default=True)

    _email_unique = models.Constraint(
        "unique(email, company_id)",
        "Email đã tồn tại trong hệ thống.",
    )

    @api.model
    def _default_date_created(self):
        today = fields.Date.context_today(self)
        if hasattr(today, "strftime"):
            return today.strftime("%d/%m/%Y")
        return fields.Date.to_string(today)

    @api.model
    def _default_status_id(self):
        status = self.env.ref(
            "lug_email_account.status_active",
            raise_if_not_found=False,
        )
        return status.id if status else False

    @api.model
    def _resolve_status_id(self, value):
        Status = self.env["lug.email.account.status"]
        default = self._default_status_id()
        if not value:
            return default
        if isinstance(value, int):
            return Status.browse(value).exists().id or default
        text = str(value).strip()
        if not text:
            return default
        mapped_code = STATE_IMPORT_MAP.get(text.lower(), text)
        status = Status.search(
            ["|", ("code", "=", mapped_code), ("name", "ilike", text)],
            limit=1,
        )
        return status.id or default

    @api.model
    def _apply_import_defaults(self, vals, from_import=False):
        email = (vals.get("email") or "").strip()
        employee = (vals.get("employee_name") or "").strip()
        email_label = email.split("@")[0] if email and "@" in email else email

        if not (vals.get("date_created") or "").strip():
            vals["date_created"] = self._default_date_created()

        if not employee and email_label:
            vals["employee_name"] = email_label
            employee = email_label

        if not (vals.get("function_name") or "").strip():
            vals["function_name"] = "-"

        if not (vals.get("department") or "").strip() and not vals.get("department_id"):
            vals["department"] = "Chưa phân loại"
        else:
            vals = self._sync_department_fields(vals)

        if not (vals.get("purpose") or "").strip():
            vals["purpose"] = "-"

        if not (vals.get("usage_target") or "").strip():
            vals["usage_target"] = "Nội bộ"

        vals["position"] = self._normalize_position(vals.get("position"))

        if vals.get("status_id"):
            vals["status_id"] = self._resolve_status_id(vals["status_id"])
        elif vals.get("state"):
            vals["status_id"] = self._resolve_status_id(vals.pop("state"))
        elif from_import:
            vals["status_id"] = self._resolve_status_id(None)

        if not vals.get("stt"):
            vals["stt"] = int(
                self.env["ir.sequence"].next_by_code("lug.email.account") or 0
            )

        return vals

    @api.model_create_multi
    def create(self, vals_list):
        from_import = bool(self.env.context.get("import_file"))
        prepared = []
        for vals in vals_list:
            prepared.append(
                self._apply_import_defaults(dict(vals), from_import=from_import)
            )
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if "position" in vals:
            vals["position"] = self._normalize_position(vals.get("position"))
        if "status_id" in vals:
            vals["status_id"] = self._resolve_status_id(vals.get("status_id"))
        if vals.get("state"):
            vals["status_id"] = self._resolve_status_id(vals.pop("state"))
        if vals.get("department_id") or vals.get("department"):
            vals = self._sync_department_fields(vals)
        return super().write(vals)

    @api.model
    def _sync_department_fields(self, vals):
        Department = self.env["hr.department"]
        if vals.get("department_id"):
            dept = Department.browse(vals["department_id"])
            if dept.exists():
                vals["department"] = dept.name
        elif vals.get("department"):
            dept_name = str(vals["department"]).strip()
            if dept_name and dept_name != "Chưa phân loại":
                dept = Department.search([("name", "=ilike", dept_name)], limit=1)
                if dept:
                    vals["department_id"] = dept.id
                    vals["department"] = dept.name
        return vals

    @api.model
    def _normalize_position(self, value):
        if not value:
            return "other"
        valid = dict(POSITION_SELECTION)
        if value in valid:
            return value
        return POSITION_IMPORT_MAP.get(str(value).strip().lower(), "other")

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for record in self:
            if not record.employee_id:
                continue
            employee = record.employee_id
            if not record.employee_name:
                record.employee_name = employee.name
            if employee.department_id and not record.department_id:
                record.department_id = employee.department_id
            if employee.department_id and not record.department:
                record.department = employee.department_id.name
            if not record.email and employee.work_email:
                record.email = employee.work_email

    @api.onchange("department_id")
    def _onchange_department_id(self):
        for record in self:
            if record.department_id:
                record.department = record.department_id.name

    @api.model
    def get_list_filter_options(self):
        departments = self.env["hr.department"].search([], order="name")
        statuses = self.env["lug.email.account.status"].search(
            [("active", "=", True)],
            order="sequence, name",
        )
        return {
            "departments": [
                {"id": dept.id, "name": dept.name} for dept in departments
            ],
            "states": [
                {"value": status.id, "label": status.name}
                for status in statuses
            ],
        }

    @api.constrains("email", "employee_name", "status_id")
    def _check_required_fields(self):
        for record in self:
            if not record.email or "@" not in record.email:
                raise ValidationError("Email không hợp lệ.")
            if not (record.employee_name or "").strip():
                raise ValidationError("Họ và tên nhân viên không được để trống.")
            if not record.status_id:
                raise ValidationError("Trạng thái không được để trống.")
