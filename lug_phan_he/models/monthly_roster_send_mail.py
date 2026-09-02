# -*- coding: utf-8 -*-

import base64
import io
import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import UserError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ADMIN_TITLES = {"admin", "admin tong"}
_CHT_TITLES = {"cua hang truong", "cht"}


def _valid_email(value):
    return bool(value and _EMAIL_RE.match(value.strip()))


def _split_emails(value):
    parts = re.split(r"[;,]+", value or "")
    return [p.strip() for p in parts if p.strip()]


def _fold_title(value):
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().split())


def _employee_email(employee):
    if not employee:
        return ""
    user = employee.user_id
    for val in (
        employee.work_email,
        user.email if user else "",
        user.login if user else "",
        employee.work_contact_id.email if employee.work_contact_id else "",
    ):
        mail = (val or "").strip()
        if _valid_email(mail):
            return mail
    return ""


def _employee_job_title(employee):
    if not employee:
        return ""
    title = employee.job_title or ""
    if not title and employee.version_id:
        title = employee.version_id.job_title or ""
    return title


def _is_admin_title(employee):
    return _fold_title(_employee_job_title(employee)) in _ADMIN_TITLES


def _is_cht_title(employee):
    title = _fold_title(_employee_job_title(employee))
    return title in _CHT_TITLES or title.startswith("cua hang truong")


def _employee_manager(employee):
    if not employee:
        return employee
    return employee.parent_id


class LinkqMonthlyRosterSendMail(models.Model):
    _inherit = "linkq.monthly.roster"

    sender_email = fields.Char(string="Người gửi", compute="_compute_sender_email")
    asm_email = fields.Char(string="Gửi đến ASM", compute="_compute_email_setup", inverse="_inverse_email_recipients", readonly=False)
    admin_email = fields.Char(string="Gửi đến Admin", compute="_compute_email_setup", inverse="_inverse_email_recipients", readonly=False)
    email_subject = fields.Char(
        string="Tiêu đề Email",
        compute="_compute_email_setup",
        store=True,
        readonly=False,
    )
    attachment_name = fields.Char(string="Tên tệp đính kèm", compute="_compute_email_setup", store=True)
    attachment_file = fields.Binary(string="File đính kèm")
    asm_email_valid = fields.Boolean(compute="_compute_email_valid")
    admin_email_valid = fields.Boolean(compute="_compute_email_valid")

    def _current_user_email(self):
        user = self.env.user
        for val in (user.email, user.partner_id.email, user.login):
            mail = (val or "").strip()
            if _valid_email(mail):
                return mail
        return (user.login or "").strip()

    @api.depends_context("uid")
    def _compute_sender_email(self):
        mail = self._current_user_email()
        for rec in self:
            rec.sender_email = mail

    def _store_employees(self):
        self.ensure_one()
        Employee = self.env["hr.employee"].sudo()
        employees = self.line_ids.mapped("employee_id")
        if self.store_id:
            employees |= Employee.search([("store_id", "=", self.store_id.id), ("active", "=", True)])
        return employees

    def _lookup_asm_emails(self):
        """ASM = email Quản lý (parent_id) của Cửa hàng trưởng tại cửa hàng."""
        self.ensure_one()
        employees = self._store_employees()
        cht = employees.filtered(_is_cht_title)
        if not cht and self.store_id and self.store_id.manager_id:
            cht = self.store_id.manager_id
        sources = cht or employees
        emails = []
        seen = set()
        for emp in sources:
            manager = _employee_manager(emp)
            mail = _employee_email(manager)
            key = mail.lower()
            if mail and key not in seen:
                seen.add(key)
                emails.append(mail)
        return emails

    def _lookup_admin_emails(self):
        """Chỉ lấy Chức danh (job_title) = Admin hoặc Admin Tổng, không dùng Job Position."""
        emails = []
        seen = set()
        employees = self.env["hr.employee"].sudo().with_context(active_test=True).search([])
        for emp in employees:
            if not _is_admin_title(emp):
                continue
            mail = _employee_email(emp)
            key = mail.lower()
            if mail and key not in seen:
                seen.add(key)
                emails.append(mail)
        if not emails:
            versions = self.env["hr.version"].sudo().search([("job_title", "ilike", "admin")])
            for version in versions:
                emp = version.employee_id
                if not emp or not emp.active or not _is_admin_title(emp):
                    continue
                mail = _employee_email(emp)
                key = mail.lower()
                if mail and key not in seen:
                    seen.add(key)
                    emails.append(mail)
        return emails

    @api.depends(
        "store_id",
        "store_id.code",
        "store_id.manager_id",
        "store_id.manager_id.work_email",
        "name",
        "month",
        "year",
        "period_label",
        "line_ids.employee_id",
        "line_ids.employee_id.parent_id",
        "line_ids.employee_id.parent_id.work_email",
        "line_ids.employee_id.job_title",
    )
    def _compute_email_setup(self):
        admin_emails = None
        for rec in self:
            store_code = (rec.store_id.code or rec.store_id.name or "STORE").strip() or "STORE"
            rec.asm_email = ", ".join(rec._lookup_asm_emails())
            if admin_emails is None:
                admin_emails = rec._lookup_admin_emails()
            rec.admin_email = ", ".join(admin_emails)
            month_label = rec.period_label or rec.name or ""
            rec.email_subject = f"Lịch ca {month_label} - {store_code}".strip(" -")
            safe_name = re.sub(r"[^\w.-]+", "_", rec.name or "lich_ca")
            rec.attachment_name = f"Lich_ca_{store_code}_{safe_name}.pdf"

    def _inverse_email_recipients(self):
        """Cho phép sửa tay trên form; giá trị không-store nên không ghi DB."""
        return

    @api.depends("asm_email", "admin_email")
    def _compute_email_valid(self):
        for rec in self:
            asm_parts = _split_emails(rec.asm_email)
            admin_parts = _split_emails(rec.admin_email)
            rec.asm_email_valid = bool(asm_parts) and all(_valid_email(p) for p in asm_parts)
            rec.admin_email_valid = bool(admin_parts) and all(_valid_email(p) for p in admin_parts)

    def _roster_mail_template(self):
        return self.env.ref("lug_phan_he.email_template_weekly_roster", raise_if_not_found=False)

    def _ensure_roster_pdf(self):
        self.ensure_one()
        if self.attachment_file:
            return
        pdf_b64 = self._render_roster_pdf()
        self.sudo().write({"attachment_file": pdf_b64})

    def _render_roster_pdf(self):
        self.ensure_one()
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
        except ImportError:
            return self._render_minimal_pdf()

        buf = io.BytesIO()
        page = landscape(A4)
        c = canvas.Canvas(buf, pagesize=page)
        width, height = page
        y = height - 18 * mm
        c.setFont("Helvetica-Bold", 14)
        c.drawString(16 * mm, y, (self.name or "Bang xep ca")[:90])
        y -= 8 * mm
        c.setFont("Helvetica", 10)
        c.drawString(16 * mm, y, f"{self.sender_email or ''}  |  {self.period_label or ''}")
        y -= 10 * mm
        c.setFont("Helvetica", 8)
        for line in self.line_ids:
            if y < 14 * mm:
                c.showPage()
                y = height - 16 * mm
                c.setFont("Helvetica", 8)
            name = line.employee_name or (line.employee_id.name if line.employee_id else "")
            c.drawString(16 * mm, y, f"{name}  |  {line.job_title or ''}  |  {line.employee_code or ''}")
            y -= 5 * mm
        c.save()
        return base64.b64encode(buf.getvalue())

    def _render_minimal_pdf(self):
        title = (self.name or "Lich ca").replace("\\", " ")[:80]
        stream = f"BT /F1 12 Tf 50 750 Td ({title}) Tj ET"
        pdf = (
            "%PDF-1.1\n"
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
            "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            "xref\n0 6\n0000000000 65535 f \n"
            "trailer << /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
        )
        return base64.b64encode(pdf.encode("latin-1", errors="ignore"))

    def _recipient_emails(self):
        self.ensure_one()
        emails = _split_emails(self.admin_email) + _split_emails(self.asm_email)
        for line in self.line_ids:
            emp = line.employee_id
            if emp:
                emails.append(_employee_email(emp))
        seen = set()
        out = []
        for raw in emails:
            mail = (raw or "").strip()
            if mail and mail.lower() not in seen and _valid_email(mail):
                seen.add(mail.lower())
                out.append(mail)
        return out

    def action_preview_email(self):
        self.ensure_one()
        self._ensure_roster_pdf()
        template = self._roster_mail_template()
        ctx = {
            "default_model": self._name,
            "default_res_ids": [self.id],
            "default_composition_mode": "comment",
            "default_subject": self.email_subject or "",
        }
        if template:
            ctx["default_template_id"] = template.id
        return {
            "type": "ir.actions.act_window",
            "name": "Xem trước email",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_send_email_now(self):
        self.ensure_one()
        template = self._roster_mail_template()
        if not template:
            raise UserError("Không tìm thấy mẫu email lịch ca. Cập nhật module lug_phan_he rồi thử lại.")
        recipients = self._recipient_emails()
        if not recipients:
            raise UserError("Chưa có địa chỉ email hợp lệ để gửi.")
        self._ensure_roster_pdf()
        attachment = False
        if self.attachment_file:
            attachment = self.env["ir.attachment"].create({
                "name": self.attachment_name or "lich_ca.pdf",
                "datas": self.attachment_file,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/pdf",
            })
        email_values = {
            "email_from": self.sender_email or self.env.user.email_formatted,
            "email_to": ",".join(recipients),
            "subject": self.email_subject or template.subject,
        }
        if attachment:
            email_values["attachment_ids"] = [(4, attachment.id)]
        template.send_mail(self.id, force_send=True, email_values=email_values)
        self.message_post(
            body=(
                "Đã gửi email lịch ca đến Admin (%s) và ASM (%s)."
                % (self.admin_email or "—", self.asm_email or "—")
            ),
            message_type="notification",
        )
        return True
