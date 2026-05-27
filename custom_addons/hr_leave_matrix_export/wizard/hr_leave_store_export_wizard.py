# Part of Odoo. See LICENSE file for full copyright and licensing details.

import calendar
import json
import re
from datetime import date, datetime
from io import BytesIO

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

STORE_HEADERS = [
    "MIỀN",
    "ID NHÂN VIÊN",
    "TÊN NHÂN VIÊN",
    "MÃ BỘ PHẬN",
    "CHỨC VỤ",
    "Ngày tạo đơn",
    "NGÀY NGHỈ Bắt đầu",
    "Ngày nghỉ kết thúc",
    "SỐ NGÀY NGHỈ",
    "LÝ DO NGHỈ",
    "NGƯỜI NHẬN BÀN GIAO",
    "ASM DUYỆT",
    "NGÀY ASM DUYỆT",
    "AD DUYỆT",
    "NGÀY AD DUYỆT",
    "trạng thái",
    "ký hiệu",
]

MIEN_DISPLAY = {
    "Bắc": "BẮC",
    "Nam": "NAM",
    "ĐTT": "ĐTT",
    "VP": "VP",
}

JOB_TITLE_SHORT = {
    "cửa hàng trưởng": "CHT",
    "asm": "ASM",
    "rsm": "RSM",
    "nhân viên ch": "NVCH",
    "nhân viên vp": "NVVP",
    "trưởng nhóm": "TN",
    "giám sát": "GS",
    "admin": "AD",
    "admin tổng": "AD",
}

# Khớp time_off_extra_approval._DEFAULT_LEAD_DAYS (giám đốc miễn rule nhưng vẫn có ngưỡng 7 ngày)
_DEFAULT_EMERGENCY_LEAD_DAYS = 7


class HrLeaveStoreExportMixin(models.AbstractModel):
    """Store form Excel export (used via hr.leave.matrix.export.wizard)."""

    _name = "hr.leave.store.export.mixin"
    _description = "Export store time off (FORM KẾT XUẤT NGHỈ PHÉP)"

    # Kết xuất CH: Bắc / Nam / ĐTT — Kết xuất VP (ma trận): VP
    MIEN_CH_CODES = frozenset({"Bắc", "Nam", "ĐTT"})
    MIEN_VP_CODES = frozenset({"VP"})

    @staticmethod
    def _format_date(value):
        if not value:
            return ""
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return f"{value.day}/{value.month}/{value.year}"
        return str(value)

    def _employee_mien(self, employee):
        """Miền nhân viên (trực tiếp hoặc từ mã bộ phận)."""
        if not employee:
            return None
        mien = getattr(employee, "mien", None)
        if mien:
            return mien
        dept = getattr(employee, "ma_bo_phan_id", None)
        if dept and getattr(dept, "mien", None):
            return dept.mien
        return None

    def _leave_in_mien(self, leave, allowed_miens):
        return self._employee_mien(leave.employee_id) in allowed_miens

    def _mien_label(self, employee):
        mien = getattr(employee, "mien", None) or ""
        return MIEN_DISPLAY.get(mien, (mien or "").upper())

    def _job_title_code(self, employee):
        if not employee:
            return ""
        ma = (getattr(employee, "ma_chuc_vu", None) or "").strip()
        if ma:
            return ma.upper()
        jt = employee.job_title or ""
        if jt in JOB_TITLE_SHORT:
            return JOB_TITLE_SHORT[jt]
        if "job_title" in employee._fields and employee._fields["job_title"].type == "selection":
            labels = dict(employee._fields["job_title"]._description_selection(self.env))
            label = labels.get(jt, jt)
            return (label or "").upper()
        return jt.upper()

    def _handover_recipient_names(self, leave):
        if "handover_acceptance_ids" not in leave._fields:
            return ""
        lines = leave.handover_acceptance_ids
        if not lines:
            return ""
        names = lines.mapped("employee_id.name")
        return ", ".join(n for n in names if n)

    def _approval_for_job_title(self, leave, job_title_keys):
        """Return (approver display name, approval date str) from responsible approval lines."""
        if isinstance(job_title_keys, str):
            job_title_keys = (job_title_keys,)
        if "responsible_approval_line_ids" not in leave._fields:
            return "", ""
        lines = leave.responsible_approval_line_ids.sorted("sequence")

        def _matches(line):
            emp = line.user_id.employee_id
            return emp and (emp.job_title or "") in job_title_keys

        approved = lines.filtered(lambda line: line.state == "approved" and _matches(line))
        if approved:
            line = approved[0]
            emp = line.user_id.employee_id
            name = (emp.name or line.user_id.name or "").upper()
            return name, self._format_date(line.action_date)
        pending = lines.filtered(lambda line: line.state == "pending" and _matches(line))
        if pending:
            line = pending[0]
            emp = line.user_id.employee_id
            return (emp.name or line.user_id.name or "").upper(), ""
        return "", ""

    def _leave_emergency_reference_date(self, leave):
        """Ngày đối chiếu báo trước (lần tạo / cập nhật đơn gần nhất)."""
        days = []
        if leave.create_date:
            days.append(fields.Date.to_date(leave.create_date))
        if leave.write_date:
            days.append(fields.Date.to_date(leave.write_date))
        return max(days) if days else fields.Date.context_today(self)

    def _is_emergency_leave_for_export(self, leave):
        """Khớp logic UI (kể cả giám đốc: báo trước < 7 ngày vẫn là khẩn cấp)."""
        if getattr(leave, "is_emergency_leave", False):
            return True
        hr_leave = self.env["hr.leave"]
        if hasattr(hr_leave, "_needs_emergency_leave_confirmation"):
            return hr_leave._needs_emergency_leave_confirmation(
                res_id=leave.id,
                vals={
                    "employee_id": leave.employee_id.id,
                    "request_date_from": leave.request_date_from,
                    "request_date_to": leave.request_date_to,
                    "holiday_status_id": leave.holiday_status_id.id,
                },
            )
        if not hasattr(leave, "_required_lead_days_for_job_title"):
            return False
        employee = leave.employee_id
        start = leave.request_date_from
        if not employee or not start:
            return False
        ref_day = self._leave_emergency_reference_date(leave)
        delta = (start - ref_day).days
        required = leave._required_lead_days_for_job_title(employee.job_title)
        if required is not None:
            return delta < required
        return delta < _DEFAULT_EMERGENCY_LEAD_DAYS

    def _status_text(self, leave):
        """Bình thường vs khẩn cấp (theo quy định báo trước, không phải trạng thái duyệt)."""
        if self._is_emergency_leave_for_export(leave):
            return "khẩn cấp"
        return "bình thường"

    @staticmethod
    def _normalize_leave_type_code(raw):
        """P1, P2, O — không có dấu ngoặc."""
        code = (raw or "").strip()
        code = code.replace("（", "(").replace("）", ")")
        if code.startswith("(") and code.endswith(")"):
            code = code[1:-1].strip()
        return code

    def _leave_type_symbol(self, leave):
        """Mã loại nghỉ, vd. Nghỉ Phép (P1) -> P1."""
        leave_type = leave.holiday_status_id
        if not leave_type:
            return ""
        leave_type_model = self.env["hr.leave.type"]
        if hasattr(leave_type_model, "code_from_name"):
            code = leave_type_model.code_from_name(leave_type.name)
            if code:
                return self._normalize_leave_type_code(code)
        name = (leave_type.name or "").strip().replace("（", "(").replace("）", ")")
        if not name:
            return ""
        match = re.search(r"\(([^)]+)\)", name)
        if match:
            return self._normalize_leave_type_code(match.group(1))
        return self._normalize_leave_type_code(name)

    def _leave_reason(self, leave):
        return (leave.private_name or leave.name or "").strip()

    def _row_for_leave(self, leave):
        emp = leave.employee_id
        asm_name, asm_date = self._approval_for_job_title(leave, ("asm",))
        ad_name, ad_date = self._approval_for_job_title(leave, ("admin tổng", "admin"))
        return [
            self._mien_label(emp) if emp else "",
            (getattr(emp, "id_hrm", None) or "").strip() if emp else "",
            (emp.name or "").upper() if emp else "",
            (getattr(emp, "ma_bo_phan", None) or "").strip().upper() if emp else "",
            self._job_title_code(emp),
            self._format_date(leave.create_date),
            self._format_date(leave.request_date_from),
            self._format_date(leave.request_date_to),
            leave.number_of_days or "",
            self._leave_reason(leave),
            self._handover_recipient_names(leave),
            asm_name,
            asm_date,
            ad_name,
            ad_date,
            self._status_text(leave),
            self._leave_type_symbol(leave),
        ]

    def _search_store_leaves(self, year, month, base_domain):
        last_day = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
        overlap = [
            ("request_date_from", "<=", month_end),
            ("request_date_to", ">=", month_start),
        ]
        domain = base_domain + overlap if base_domain else overlap
        leaves = self.env["hr.leave"].search(
            domain,
            order="employee_id, request_date_from, id",
        )
        return leaves.filtered(lambda leave: self._leave_in_mien(leave, self.MIEN_CH_CODES))

    def action_export_store_excel(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_allow_export"):
            raise UserError(_("You need export permissions to download this file."))

        year, month = int(self.year), int(self.month)
        leaves = self._search_store_leaves(year, month, self._parse_domain())

        buffer = BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = workbook.add_worksheet("Nghỉ phép CH")

        title_fmt = workbook.add_format(
            {"bold": True, "font_size": 12, "align": "center", "valign": "vcenter"}
        )
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#BDD7EE",
                "border": 1,
                "align": "center",
                "text_wrap": True,
                "valign": "vcenter",
            }
        )
        cell_fmt = workbook.add_format({"border": 1, "valign": "top", "text_wrap": True})

        sheet.merge_range(0, 0, 0, len(STORE_HEADERS) - 1, "FORM KẾT XUẤT NGHỈ PHÉP", title_fmt)
        for col, title in enumerate(STORE_HEADERS):
            sheet.write(1, col, title, header_fmt)

        row = 2
        for leave in leaves:
            values = self._row_for_leave(leave)
            for col, value in enumerate(values):
                sheet.write(row, col, value, cell_fmt)
            row += 1

        if row == 2:
            sheet.write_row(2, 0, [""] * len(STORE_HEADERS), cell_fmt)
            row = 3

        sheet.freeze_panes(2, 0)
        sheet.set_column(0, 0, 8)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 28)
        sheet.set_column(3, 4, 12)
        sheet.set_column(5, 8, 14)
        sheet.set_column(9, 9, 32)
        sheet.set_column(10, 10, 28)
        sheet.set_column(11, 14, 18)
        sheet.set_column(15, 15, 14)
        sheet.set_column(16, 16, 10)

        workbook.close()
        buffer.seek(0)
        filename = "form_ket_xuat_nghi_phep_ch_%s-%02d.xlsx" % (year, month)

        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "raw": buffer.read(),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
