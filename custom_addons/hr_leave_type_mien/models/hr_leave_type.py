# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models
from odoo.fields import Domain

from .hr_leave_mien_config import MIEN_SELECTION

# Mã loại phép = ngoặc () đầu tiên trong tên, vd. «Nghỉ phép (P1) - …» → P1.
_LEAVE_TYPE_CODE_IN_PARENS_RE = re.compile(r"\(([^)]+)\)")


def _normalize_leave_type_display_name(name):
    """Chuẩn hóa ngoặc fullwidth và khoảng trắng thừa."""
    if not name:
        return ""
    text = str(name).strip()
    return text.replace("（", "(").replace("）", ")")

# Chỉ lọc loại phép theo Miền khi tạo đơn nghỉ (holiday_status_id trên hr.leave).
MIEN_LEAVE_TYPE_FILTER_CTX = "filter_leave_types_by_employee_mien"
MIEN_LEAVE_TYPE_SKIP_CTX = "skip_mien_leave_type_filter"


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    mien_line_ids = fields.One2many(
        "hr.leave.mien.line",
        "leave_type_id",
        string="Region assignment",
    )
    mien_display = fields.Char(
        compute="_compute_mien_display",
        string="Region",
    )

    @api.model
    def code_from_name(self, display_name):
        """Trích mã loại phép từ ngoặc () đầu tiên trong tên."""
        name = _normalize_leave_type_display_name(display_name)
        if not name:
            return ""
        match = _LEAVE_TYPE_CODE_IN_PARENS_RE.search(name)
        return match.group(1).strip() if match else ""

    @api.model
    def _leave_type_name_variants(self, leave_type):
        """Các biến thể tên (mọi ngôn ngữ cài đặt) để đối chiếu mã."""
        names = set()
        field = leave_type._fields.get("name")
        if field and field.translate:
            for lang_code, _label in self.env["res.lang"].get_installed():
                names.add(
                    _normalize_leave_type_display_name(
                        leave_type.with_context(lang=lang_code).name
                    )
                )
        names.add(_normalize_leave_type_display_name(leave_type.name))
        return {n for n in names if n}

    @api.model
    def search_by_code(self, code, limit=1, allowed_ids=None):
        """Tìm loại ngày nghỉ theo mã trong () — quét toàn bộ loại phép.

        allowed_ids: nếu truyền, chỉ xét trong tập id này (vd. loại phép của Miền)
        để tránh nhập nhằng khi nhiều loại trùng mã, ví dụ (O) của
        «Làm Online (O)» và «Nghỉ không lương (O)».
        """
        code_norm = (code or "").strip().upper()
        if not code_norm:
            return self.browse()
        domain = [("id", "in", list(allowed_ids))] if allowed_ids is not None else []
        matches = self.browse()
        for leave_type in self.sudo().search(domain):
            for name in self._leave_type_name_variants(leave_type):
                if self.code_from_name(name).upper() == code_norm:
                    matches |= leave_type
                    break
            if limit and len(matches) >= limit:
                break
        return matches

    @api.model
    def leave_type_from_selection(self, leave_type, code, allowed_ids=None):
        """Ưu tiên tìm theo mã; nếu không có thì dùng bản ghi đang chọn nếu mã khớp.

        Khi truyền allowed_ids (loại phép của Miền), ưu tiên tìm trong tập đó trước
        để chọn đúng loại khi nhiều loại trùng mã.
        """
        code_norm = (code or "").strip().upper()
        if allowed_ids is not None:
            scoped = self.search_by_code(code, limit=1, allowed_ids=allowed_ids)
            if scoped:
                return scoped
        found = self.search_by_code(code, limit=1)
        if found:
            return found
        if leave_type and self.code_from_name(leave_type.name).upper() == code_norm:
            return leave_type
        return self.browse()

    @api.depends("mien_line_ids", "mien_line_ids.config_id.mien")
    def _compute_mien_display(self):
        mien_field = self.env["hr.leave.mien.config"]._fields["mien"]
        labels = dict(mien_field._description_selection(self.env))
        for leave_type in self:
            codes = leave_type.mien_line_ids.config_id.mapped("mien")
            leave_type.mien_display = ", ".join(labels.get(code, code) for code in codes) if codes else ""

    @api.model
    def _get_employee_id_for_mien_filter(self):
        ctx = self.env.context
        for key in ("employee_id", "default_employee_id"):
            employee_id = ctx.get(key)
            if not employee_id:
                continue
            if isinstance(employee_id, int):
                return employee_id
            if isinstance(employee_id, (list, tuple)):
                return employee_id[0]
            return employee_id
        if ctx.get("active_model") == "hr.leave" and ctx.get("active_id"):
            leave = self.env["hr.leave"].browse(ctx["active_id"])
            if leave.employee_id:
                return leave.employee_id.id
        return False

    @api.model
    def _should_apply_mien_leave_type_filter(self):
        ctx = self.env.context
        if ctx.get(MIEN_LEAVE_TYPE_SKIP_CTX):
            return False
        if not ctx.get(MIEN_LEAVE_TYPE_FILTER_CTX):
            return False
        return bool(self._get_employee_id_for_mien_filter())

    @api.model
    def _domain_with_employee_mien(self, domain):
        if not self._should_apply_mien_leave_type_filter():
            return domain
        employee_id = self._get_employee_id_for_mien_filter()
        employee = self.env["hr.employee"].browse(employee_id)
        if not employee.exists():
            return domain
        mien_domain = self.env["hr.leave"]._leave_type_domain_for_employee(employee)
        return Domain(domain or []) & Domain(mien_domain)

    @api.model
    @api.readonly
    def web_name_search(self, name, specification, domain=None, operator="ilike", limit=100):
        domain = self._domain_with_employee_mien(domain)
        return super().web_name_search(
            name, specification, domain=domain, operator=operator, limit=limit
        )
