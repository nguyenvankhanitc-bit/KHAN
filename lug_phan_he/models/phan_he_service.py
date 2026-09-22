# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class PhanHeService(models.Model):
    _name = "phan.he.service"
    _description = "Hợp đồng dịch vụ"
    _inherit = ["mail.thread", "mail.activity.mixin", "phan.he.currency.mixin", "phan.he.access.mixin"]
    _order = "date_end desc, code, id desc"
    _rec_names_search = ["code", "customer_code", "name"]

    code = fields.Char(
        string="Mã hợp đồng",
        required=True,
        copy=False,
        tracking=True,
    )
    name = fields.Char(string="Tiêu đề", compute="_compute_name", store=True)
    store_id = fields.Many2one(
        "phan.he.store", string="Cửa hàng", required=True,
        tracking=True, ondelete="restrict", index=True,
    )
    mien_id = fields.Many2one(related="store_id.mien_id", store=True, string="Miền")
    area_id = fields.Many2one(related="store_id.area_id", store=True, string="Khu vực")
    store_mien = fields.Selection(related="store_id.mien", store=True, string="Miền (cũ)")
    store_name_sort = fields.Char(
        string="Tên cửa hàng (sắp xếp)",
        related="store_id.name",
        store=True,
        index=True,
    )
    store_mien_rank = fields.Integer(
        string="Thứ tự miền",
        compute="_compute_store_mien_rank",
        store=True,
        index=True,
    )
    customer_code = fields.Char(string="Mã khách hàng", tracking=True)
    service_type_id = fields.Many2one(
        "phan.he.service.type", string="Loại dịch vụ", required=True,
        tracking=True, ondelete="restrict", index=True,
        default=lambda self: self._default_service_type_id(),
    )
    service_type_name = fields.Char(related="service_type_id.name", store=True)
    category = fields.Selection(
        selection=[
            ("internet", "INTERNET"),
            ("camera", "CAMERA"),
            ("attendance", "MÁY CHẤM CÔNG"),
            ("linkq_hrm", "LINKQ HRM"),
            ("linkq_nb", "LINKQ NB"),
            ("server", "MÁY CHỦ"),
            ("software", "SOFTWARE"),
            ("phone", "PHONE"),
            ("other", "OTHER"),
        ],
        compute="_compute_category", store=True, readonly=True,
    )
    package_name = fields.Char(string="Loại thanh toán")
    service_content = fields.Text(string="Nội dung / gói dịch vụ")
    bandwidth = fields.Char(
        string="Băng thông",
        tracking=True,
        help="VD: 100Mbps, 200Mbps, Fiber 1Gbps",
    )
    bandwidth_display = fields.Char(
        string="Băng thông",
        compute="_compute_bandwidth_display",
    )
    usage_address = fields.Text(string="Địa chỉ lắp đặt")
    payment_type = fields.Selection(
        selection=[
            ("monthly", "Trả sau hàng tháng"),
            ("prepaid_6", "Trả trước / 6 tháng"),
            ("prepaid_12", "Trả trước / 12 tháng"),
        ],
        string="Loại thanh toán",
        default="prepaid_12",
        tracking=True,
    )
    bank_account_holder = fields.Char(string="Tên tài khoản")
    bank_account_number = fields.Char(string="Số tài khoản")
    bank_name = fields.Char(string="Ngân hàng")
    bank_branch = fields.Char(string="Chi nhánh")
    bank_display = fields.Char(
        string="Ngân hàng",
        compute="_compute_bank_display",
        inverse="_inverse_bank_display",
    )
    invoice_attachment_ids = fields.Many2many(
        "ir.attachment",
        "phan_he_service_invoice_attachment_rel",
        "service_id",
        "attachment_id",
        string="File hóa đơn đính kèm",
    )
    invoice_file = fields.Binary(string="File hóa đơn đính kèm", attachment=True)
    invoice_filename = fields.Char(string="Tên file hóa đơn")
    technical_info = fields.Text(string="Thông tin kỹ thuật")
    stt = fields.Integer(string="STT", copy=False, index=True)
    date_start = fields.Date(string="Ngày bắt đầu", tracking=True)
    date_end = fields.Date(string="Ngày kết thúc", tracking=True)
    contract_amount = fields.Monetary(
        string="Cước tháng",
        currency_field="currency_id",
        tracking=True,
        required=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self._default_currency_vnd() or self.env.company.currency_id,
        required=True,
    )
    duration = fields.Char(compute="_compute_duration", store=True, string="Thời hạn")
    remaining_time = fields.Char(
        compute="_compute_remaining",
        store=True,
        string="Thời gian còn lại",
    )
    remaining_days = fields.Integer(
        compute="_compute_remaining",
        store=True,
        string="Số ngày còn lại",
    )
    alert_level = fields.Selection(
        selection=[
            ("ok", "Bình thường"),
            ("warn", "Sắp hết hạn (≤30 ngày)"),
            ("danger", "Sắp hết hạn (≤7 ngày)"),
            ("expired", "Đã hết hạn"),
        ],
        compute="_compute_remaining",
        store=True,
        string="Mức cảnh báo",
    )
    remaining_alert = fields.Html(
        compute="_compute_remaining",
        string="Còn lại (cảnh báo)",
        sanitize=False,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Nháp"),
            ("waiting", "Chờ duyệt"),
            ("active", "Đang hoạt động"),
            ("suspend", "Tạm ngưng"),
            ("liquidated", "Thanh lý"),
            ("expired", "Đã hết hạn"),
            ("cancel", "Đã hủy"),
        ],
        string="Trạng thái (nội bộ)",
        default="active",
        required=True,
        tracking=True,
    )
    # Cột TRẠNG THÁI bảng theo dõi: chỉ 3 giá trị
    ops_status = fields.Selection(
        selection=[
            ("active", "Đang hoạt động"),
            ("suspend", "Tạm ngưng"),
            ("liquidated", "Thanh lý"),
        ],
        string="Trạng thái",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )

    @api.model
    def _map_state_to_ops(self, state):
        if state == "suspend":
            return "suspend"
        if state in ("liquidated", "expired", "cancel"):
            return "liquidated"
        return "active"

    provider_id = fields.Many2one(
        "phan.he.provider", string="Nhà cung cấp",
        tracking=True, ondelete="set null", index=True,
    )
    company_id = fields.Many2one(related="store_id.company_id", store=True, readonly=True)
    payment_ids = fields.One2many("phan.he.payment", "service_id", string="Lịch thanh toán")
    payment_count = fields.Integer(compute="_compute_counts")
    invoice_ids = fields.One2many("phan.he.invoice", "service_id", string="Hóa đơn")
    invoice_count = fields.Integer(compute="_compute_counts")
    document_ids = fields.One2many("phan.he.document", "service_id", string="Chứng từ")
    document_count = fields.Integer(compute="_compute_counts")
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

    # --- Cột bảng theo dõi (giống Excel) ---
    store_address = fields.Text(
        related="store_id.address",
        string="Địa chỉ CH",
        readonly=True,
    )
    next_payment_id = fields.Many2one(
        "phan.he.payment",
        compute="_compute_next_payment",
        store=True,
        ondelete="set null",
        string="Kỳ TT gần nhất",
    )
    next_invoice_number = fields.Char(
        string="HĐ / Số hóa đơn",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
        readonly=False,
    )
    next_payment_amount = fields.Monetary(
        string="Số tiền thanh toán",
        currency_field="currency_id",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
        store=True,
        readonly=False,
    )
    next_payment_date = fields.Date(
        string="Ngày TT tiếp theo",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
        store=True,
        readonly=False,
    )
    payment_info_text = fields.Text(
        string="Thông tin thanh toán",
        compute="_compute_payment_info_text",
        inverse="_inverse_payment_info_text",
        store=True,
        readonly=False,
    )
    payment_info_manual = fields.Text(
        string="Thông tin thanh toán (nhập tay)",
    )
    store_card_html = fields.Html(
        string="Cửa hàng",
        compute="_compute_tracking_cards",
        sanitize=False,
    )
    remaining_card_html = fields.Html(
        string="Thời gian còn lại",
        compute="_compute_tracking_cards",
        sanitize=False,
    )

    MIEN_LIST_RANK = {
        "Nam": 1,
        "ĐTT": 2,
        "Bắc": 3,
        "VP": 4,
    }
    INTERNET_LIST_ORDER = "store_mien_rank asc, store_name_sort asc, id asc"

    @api.depends("store_mien")
    def _compute_store_mien_rank(self):
        """Nam → ĐTT → Bắc → Văn phòng; trong miền sắp A→Z theo tên CH."""
        for rec in self:
            rec.store_mien_rank = self.MIEN_LIST_RANK.get(rec.store_mien, 99)

    @api.depends(
        "store_id", "store_id.name", "customer_code", "code",
        "date_end", "remaining_days", "alert_level", "remaining_time",
    )
    def _compute_tracking_cards(self):
        from markupsafe import Markup, escape

        for rec in self:
            store_name = escape(rec.store_id.name or "—")
            code = escape((rec.customer_code or rec.code or "").strip())
            code_html = (
                f'<div class="o_phan_he_store_code">{code}</div>'
                if code else
                '<div class="o_phan_he_store_code is-empty">—</div>'
            )
            rec.store_card_html = Markup(
                f'<div class="o_phan_he_store_card">'
                f'<div class="o_phan_he_store_name">{store_name}</div>'
                f"{code_html}"
                f"</div>"
            )
            label = escape(rec.remaining_time or "—")
            level = rec.alert_level or "ok"
            css = {
                "ok": "is-ok",
                "warn": "is-warn",
                "danger": "is-danger",
                "expired": "is-danger",
            }.get(level, "is-ok")
            rec.remaining_card_html = Markup(
                f'<span class="o_phan_he_remaining_card {css}">{label}</span>'
            )

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã hợp đồng phải duy nhất trong cùng công ty.",
    )

    @api.model
    def _default_service_type_id(self):
        return self.env.ref("lug_phan_he.service_type_internet", raise_if_not_found=False)

    def _phan_he_service_code(self):
        self.ensure_one()
        return (self.service_type_id.code or self.category or "").lower() or False

    @api.model
    def _phan_he_service_code_from_vals(self, vals):
        stype_id = vals.get("service_type_id")
        if stype_id:
            stype = self.env["phan.he.service.type"].browse(stype_id)
            return (stype.code or "").lower() or False
        ctx_code = (self.env.context.get("phan_he_service_type_code") or "").lower()
        if ctx_code:
            return ctx_code
        default = self._default_service_type_id()
        return (default.code or "").lower() if default else False

    def _phan_he_internet_menu_code(self):
        if self and self.id:
            status = (self.ops_status or "active")
            from .internet_menu_permission import STATUS_TO_MENU
            return STATUS_TO_MENU.get(status, "internet_active")
        return self.env.context.get("phan_he_internet_menu") or "internet_entry"

    def _phan_he_internet_menu_codes(self, operation):
        from .internet_menu_permission import SERVICE_READ_MENUS, STATUS_TO_MENU
        if self and self.id:
            if (self.service_type_id.code or self.category or "").lower() != "internet":
                return []
        else:
            ctx_type = (self.env.context.get("phan_he_service_type_code") or "").lower()
            if ctx_type and ctx_type != "internet":
                return []
        if operation == "read":
            return list(SERVICE_READ_MENUS)
        if operation == "create":
            return [self.env.context.get("phan_he_internet_menu") or "internet_entry"]
        status = "active"
        if self and self.id:
            status = self.ops_status or "active"
        return [STATUS_TO_MENU.get(status, "internet_active")]


    @api.depends("service_type_id", "store_id")
    def _compute_name(self):
        for rec in self:
            stype = rec.service_type_id.name or ""
            store = rec.store_id.name or ""
            rec.name = f"{stype} - {store}" if stype and store else (stype or store or rec.code or "")

    @api.depends("service_type_id", "service_type_id.code")
    def _compute_category(self):
        valid = {
            "internet",
            "camera",
            "attendance",
            "linkq_hrm",
            "linkq_nb",
            "server",
            "software",
            "phone",
            "other",
        }
        for rec in self:
            code = (rec.service_type_id.code or "").lower()
            rec.category = code if code in valid else "other"

    @api.depends("payment_ids", "invoice_ids", "document_ids")
    def _compute_counts(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)
            rec.invoice_count = len(rec.invoice_ids)
            rec.document_count = len(rec.document_ids)

    def _get_next_payment_record(self):
        """Kỳ TT gần nhất: chưa thanh toán theo date_due, fallback kỳ đầu."""
        self.ensure_one()
        unpaid = self.payment_ids.filtered(
            lambda p: p.payment_state not in ("paid", "cancel")
        ).sorted(key=lambda p: p.date_due or fields.Date.today())
        return unpaid[:1] or self.payment_ids[:1]

    @api.depends(
        "payment_ids",
        "payment_ids.date_due",
        "payment_ids.payment_state",
        "payment_ids.invoice_number",
        "payment_ids.amount",
    )
    def _compute_next_payment(self):
        for rec in self:
            rec.next_payment_id = rec._get_next_payment_record()

    @api.depends(
        "payment_ids",
        "payment_ids.invoice_number",
        "payment_ids.amount",
        "payment_ids.date_due",
        "payment_ids.payment_state",
    )
    def _compute_next_payment_fields(self):
        for rec in self:
            pay = rec._get_next_payment_record()
            rec.next_invoice_number = pay.invoice_number if pay else False
            rec.next_payment_date = pay.date_due if pay else False
            # Cước tháng ≠ số tiền thanh toán (chu kỳ 6/12 tháng): không copy contract_amount.
            if pay:
                rec.next_payment_amount = pay.amount
            else:
                rec.next_payment_amount = rec.next_payment_amount or 0.0

    def _inverse_next_payment_fields(self):
        """Cho phép nhập liệu trên bảng tổng → ghi vào kỳ thanh toán (tạo mới nếu chưa có).

        Cập nhật payment bằng SQL để tránh ORM modified() search theo
        next_payment_id (lỗi khi field chưa store / registry cũ).
        """
        Payment = self.env["phan.he.payment"]
        for rec in self:
            pay = rec._get_next_payment_record()
            invoice_number = rec.next_invoice_number or False
            amount = rec.next_payment_amount or 0.0
            date_due = rec.next_payment_date or False
            if pay:
                self.env.cr.execute(
                    """
                    UPDATE phan_he_payment
                       SET invoice_number = %s,
                           amount = %s,
                           date_due = %s,
                           write_date = (now() at time zone 'UTC'),
                           write_uid = %s
                     WHERE id = %s
                    """,
                    (
                        invoice_number or None,
                        amount,
                        date_due or None,
                        self.env.uid,
                        pay.id,
                    ),
                )
                pay.invalidate_recordset(["invoice_number", "amount", "date_due", "write_date", "write_uid"])
                rec.invalidate_recordset([
                    "next_payment_id",
                    "next_invoice_number",
                    "next_payment_amount",
                    "next_payment_date",
                    "payment_info_text",
                ])
            elif invoice_number or date_due or rec.next_payment_amount:
                Payment.create({
                    "service_id": rec.id,
                    "provider_id": rec.provider_id.id or False,
                    "period": "HĐ 001",
                    "payment_state": "pending",
                    "invoice_number": invoice_number,
                    "amount": amount,
                    "date_due": date_due,
                })

    @api.depends(
        "payment_info_manual",
        "provider_id",
        "provider_id.bank_account_ids",
        "provider_id.bank_account_ids.is_default",
        "provider_id.bank_account_ids.account_name",
        "provider_id.bank_account_ids.account_number",
        "provider_id.bank_account_ids.bank_name",
        "provider_id.bank_account_ids.bank_branch",
        "payment_ids",
        "payment_ids.bank_account_id",
        "payment_ids.payment_content",
        "payment_ids.payment_state",
        "payment_ids.date_due",
    )
    def _compute_payment_info_text(self):
        for rec in self:
            if rec.payment_info_manual:
                rec.payment_info_text = rec.payment_info_manual
                continue
            pay = rec._get_next_payment_record()
            bank = pay.bank_account_id if pay else False
            if not bank and rec.provider_id:
                bank = rec.provider_id.bank_account_ids.filtered("is_default")[:1] \
                    or rec.provider_id.bank_account_ids[:1]
            if bank:
                rec.payment_info_text = (
                    f"{bank.account_name or rec.provider_id.name or ''}\n"
                    f"- STK: {bank.account_number or ''}\n"
                    f"- NGÂN HÀNG: {bank.bank_name or ''}"
                    + (f" - {bank.bank_branch}" if bank.bank_branch else "")
                ).strip()
            elif pay and pay.payment_content:
                rec.payment_info_text = pay.payment_content
            elif rec.provider_id:
                rec.payment_info_text = rec.provider_id.name
            else:
                rec.payment_info_text = False

    @api.depends("bank_name", "bank_branch")
    def _compute_bank_display(self):
        for rec in self:
            name = (rec.bank_name or "").strip()
            branch = (rec.bank_branch or "").strip()
            if branch and name and branch.lower() not in name.lower():
                rec.bank_display = f"{name} - {branch}"
            else:
                rec.bank_display = name or branch

    def _inverse_bank_display(self):
        for rec in self:
            rec.bank_name = (rec.bank_display or "").strip() or False
            rec.bank_branch = False

    def _inverse_payment_info_text(self):
        for rec in self:
            rec.payment_info_manual = rec.payment_info_text

    @api.model_create_multi
    def create(self, vals_list):
        next_stt = self._next_stt()
        Seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("stt"):
                vals["stt"] = next_stt
                next_stt += 1
            code = (vals.get("code") or "").strip() if vals.get("code") else ""
            if code:
                vals["code"] = code
            else:
                vals["code"] = Seq.next_by_code("phan.he.service") or "New"
            if "bandwidth" in vals:
                vals["bandwidth"] = self._normalize_bandwidth(vals.get("bandwidth"))
            if vals.get("ops_status") and not vals.get("state"):
                vals["state"] = vals["ops_status"]
            elif vals.get("state") and not vals.get("ops_status"):
                vals["ops_status"] = self._map_state_to_ops(vals["state"])
            else:
                vals.setdefault("ops_status", "active")
                vals.setdefault("state", vals.get("ops_status", "active"))
        records = super().create(vals_list)
        records._bind_invoice_attachments()
        return records

    def write(self, vals):
        vals = dict(vals)
        if "bandwidth" in vals:
            vals["bandwidth"] = self._normalize_bandwidth(vals.get("bandwidth"))
        if "ops_status" in vals and "state" not in vals:
            vals["state"] = vals["ops_status"]
        elif "state" in vals and "ops_status" not in vals:
            vals["ops_status"] = self._map_state_to_ops(vals["state"])
        # Thanh lý / hủy (hoặc HĐ đã đóng): không cho ghi đè trống NCC / ngày / băng thông.
        _keep = (
            "provider_id",
            "date_start",
            "date_end",
            "bandwidth",
            "contract_amount",
            "package_name",
            "customer_code",
            "usage_address",
        )
        new_ops = vals.get("ops_status") or vals.get("state")
        closing = new_ops in ("liquidated", "cancel", "expired")
        already_closed = any(
            (r.ops_status in ("liquidated", "cancel") or r.state in ("liquidated", "cancel", "expired"))
            for r in self
        )
        if closing or (already_closed and new_ops not in ("active", "suspend", "waiting", "draft")):
            for fname in _keep:
                if fname in vals and not vals.get(fname):
                    vals.pop(fname)
        res = super().write(vals)
        if "invoice_attachment_ids" in vals:
            self._bind_invoice_attachments()
        return res

    def _bind_invoice_attachments(self):
        for rec in self:
            atts = rec.invoice_attachment_ids.filtered(lambda a: not a.res_id or a.res_model != rec._name)
            if atts:
                atts.sudo().write({"res_model": rec._name, "res_id": rec.id})

    def unlink(self):
        Payment = self.env["phan.he.payment"].sudo()
        Invoice = self.env["phan.he.invoice"].sudo()
        self.sudo().write({"next_payment_id": False})
        invoices = Invoice.search([("service_id", "in", self.ids)])
        if invoices:
            invoices.unlink()
        payments = Payment.search([("service_id", "in", self.ids)])
        if payments:
            payments.unlink()
        return super().unlink()

    @api.model
    def _normalize_bandwidth(self, value):
        import re

        text = (value or "").strip()
        if not text:
            return text or False
        if re.search(r"mbps|gbps|kbps|bps", text, flags=re.I):
            return re.sub(r"\s*mbps\b", " Mbps", text, flags=re.I).strip()
        return f"{text} Mbps"

    @api.model
    def _next_stt(self):
        self.env.cr.execute("SELECT COALESCE(MAX(stt), 0) FROM phan_he_service")
        return (self.env.cr.fetchone() or (0,))[0] + 1

    @api.model
    def action_renumber_stt_desc(self):
        """Đánh STT từ lớn → nhỏ theo id (mới nhất = STT lớn nhất)."""
        records = self.with_context(active_test=False).search([], order="id asc")
        total = len(records)
        for idx, rec in enumerate(records):
            # id cũ nhất = 1, id mới nhất = total → list sort stt desc = lớn → nhỏ
            stt_val = idx + 1
            if rec.stt != stt_val:
                rec.stt = stt_val
        return total

    @api.depends("bandwidth")
    def _compute_bandwidth_display(self):
        import re

        for rec in self:
            value = (rec.bandwidth or "").strip()
            if not value:
                rec.bandwidth_display = False
            elif re.search(r"mbps|gbps|kbps|bps", value, flags=re.I):
                rec.bandwidth_display = re.sub(r"\s*mbps\b", " Mbps", value, flags=re.I).strip()
            else:
                rec.bandwidth_display = f"{value} Mbps"

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end >= rec.date_start:
                delta = relativedelta(rec.date_end, rec.date_start)
                parts = []
                if delta.years:
                    parts.append(f"{delta.years} năm")
                if delta.months:
                    parts.append(f"{delta.months} tháng")
                if delta.days or not parts:
                    parts.append(f"{delta.days} ngày")
                rec.duration = " ".join(parts)
            else:
                rec.duration = False

    @api.depends("date_end", "state")
    def _compute_remaining(self):
        """Thời gian còn lại = ngày hết hạn − hôm nay; ≤30 ngày → cảnh báo."""
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_end:
                rec.remaining_days = 0
                rec.remaining_time = False
                rec.alert_level = "ok"
                rec.remaining_alert = False
                continue

            days = (rec.date_end - today).days
            rec.remaining_days = days

            if days >= 0:
                rec.remaining_time = f"Còn {days} ngày"
            else:
                rec.remaining_time = f"Quá hạn {abs(days)} ngày"

            if days < 0:
                rec.alert_level = "expired"
            elif days <= 7:
                rec.alert_level = "danger"
            elif days <= 30:
                rec.alert_level = "warn"
            else:
                rec.alert_level = "ok"
            label = rec.remaining_time

            rec.remaining_alert = (
                f'<span class="o_phan_he_remaining_alert is-{rec.alert_level}">'
                f'<i class="fa fa-clock-o"/> {label}</span>'
            )

    @api.depends("name", "code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or rec.code or ""

    def action_submit(self):
        self.write({"state": "waiting"})

    def action_approve(self):
        self.write({"state": "active"})

    def action_suspend(self):
        self.write({"state": "suspend"})

    def action_reactivate(self):
        self.write({"state": "active"})

    def action_expire(self):
        """Giữ tương thích: đánh dấu Thanh lý (không xóa nội dung HĐ)."""
        self.write({"state": "liquidated"})

    def action_liquidate(self):
        """Chỉ đánh dấu thanh lý — giữ NCC / ngày bắt đầu / ngày kết thúc."""
        self.write({"state": "liquidated"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    @api.onchange("store_id")
    def _onchange_store_id_address(self):
        if self.store_id and self.store_id.address:
            self.usage_address = self.store_id.address

    @api.onchange("payment_type")
    def _onchange_payment_type(self):
        labels = dict(self._fields["payment_type"].selection or [])
        if self.payment_type:
            self.package_name = labels.get(self.payment_type)

    def action_save_internet_form(self):
        return True

    def action_open_payments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Lịch thanh toán",
            "res_model": "phan.he.payment",
            "view_mode": "list,form",
            "domain": [("service_id", "=", self.id)],
            "context": {
                "default_service_id": self.id,
                "default_amount": self.next_payment_amount,
                "default_provider_id": self.provider_id.id,
            },
        }

    def action_open_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Hóa đơn",
            "res_model": "phan.he.invoice",
            "view_mode": "list,form",
            "domain": [("service_id", "=", self.id)],
            "context": {"default_service_id": self.id},
        }

    def action_open_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Chứng từ",
            "res_model": "phan.he.document",
            "view_mode": "list,form",
            "domain": [("service_id", "=", self.id)],
            "context": {"default_service_id": self.id},
        }

    @api.model
    def _cron_update_alerts(self):
        """Cron hàng ngày: tạo activity cảnh báo sắp hết hạn (không đổi trạng thái)."""
        today = fields.Date.context_today(self)
        soon30 = today + relativedelta(days=30)
        for rec in self.search([
            ("state", "in", ("active", "suspend")),
            ("date_end", "!=", False),
            ("date_end", ">=", today),
            ("date_end", "<=", soon30),
        ]):
            days = (rec.date_end - today).days
            summary = f"Hợp đồng sắp hết hạn: {rec.name}"
            note = (
                f"<p><b>{rec.store_id.name}</b><br/>"
                f"Dịch vụ: {rec.service_type_id.name}<br/>"
                f"Ngày hết hạn: {rec.date_end}<br/>"
                f"Còn lại: {days} ngày</p>"
            )
            existing = self.env["mail.activity"].search([
                ("res_model", "=", self._name),
                ("res_id", "=", rec.id),
                ("summary", "=", summary),
                ("activity_type_id", "=", self.env.ref("mail.mail_activity_data_todo").id),
            ], limit=1)
            if not existing:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=summary,
                    note=note,
                    user_id=rec.create_uid.id or self.env.uid,
                )
        return True

    @api.model
    def get_tracking_mien_stats(self, domain=None):
        """Thống kê theo miền cho header nhóm bảng theo dõi."""
        domain = list(domain or [])
        today = fields.Date.context_today(self)
        soon30 = today + relativedelta(days=30)
        color_map = {
            "BAC": "#ef4444",
            "NAM": "#3b82f6",
            "DTT": "#f59e0b",
            "TRUNG": "#22c55e",
            "VP": "#64748b",
        }
        by_mien = {}
        totals = {
            "count": 0,
            "amount": 0.0,
            "expire_soon": 0,
            "overdue": 0,
        }
        for svc in self.search(domain):
            mid = svc.mien_id.id or 0
            key = str(mid)
            if key not in by_mien:
                mien = svc.mien_id
                code = (mien.code or "").upper() if mien else ""
                by_mien[key] = {
                    "id": mid,
                    "name": (mien.name or "Chưa gán miền").upper() if mid else "CHƯA GÁN MIỀN",
                    "display_name": mien.name or "Chưa gán miền",
                    "code": code,
                    "color": color_map.get(code, "#64748b"),
                    "count": 0,
                    "amount": 0.0,
                    "expire_soon": 0,
                    "overdue": 0,
                }
            row = by_mien[key]
            row["count"] += 1
            totals["count"] += 1

            # Chi phí tháng: cộng mọi HĐ chưa hủy / chưa thanh lý
            is_closed = svc.state in ("cancel", "liquidated")
            if not is_closed:
                pay = float(svc.next_payment_amount or 0.0)
                row["amount"] += pay
                totals["amount"] += pay

            if svc.date_end and not is_closed:
                if svc.date_end < today:
                    row["overdue"] += 1
                    totals["overdue"] += 1
                elif today <= svc.date_end <= soon30 and svc.state == "active":
                    row["expire_soon"] += 1
                    totals["expire_soon"] += 1

        return {"by_mien": by_mien, "totals": totals}

    REGION_COLORS = {
        "NAM": "#2f80ed",
        "DTT": "#f2994a",
        "TRUNG": "#f2994a",
        "BAC": "#27ae60",
        "VP": "#9b51e0",
    }
    REGION_ORDER = ("NAM", "DTT", "BAC", "VP", "TRUNG")

    @api.model
    def _internet_payment_period_bounds(self, year=None, month=None):
        """Tháng Lịch TT / Xác nhận TT. Không truyền → tháng kế tiếp."""
        today = fields.Date.context_today(self)
        try:
            y = int(year) if year not in (None, False, "") else 0
            m = int(month) if month not in (None, False, "") else 0
        except (TypeError, ValueError):
            y, m = 0, 0
        if y and 1 <= m <= 12:
            period_start = fields.Date.to_date(f"{y}-{m:02d}-01")
        else:
            period_start = today.replace(day=1) + relativedelta(months=1)
        period_end = (period_start + relativedelta(months=1)) - relativedelta(days=1)
        return period_start, period_end, today

    @api.model
    def _internet_payment_schedule_domain(self, year=None, month=None):
        """Cùng domain Lịch TT: HĐ active trong tháng + quá hạn."""
        period_start, period_end, today = self._internet_payment_period_bounds(year, month)
        return [
            ("active", "=", True),
            ("service_type_id.code", "=", "internet"),
            ("state", "=", "active"),
            "|", "|",
            "&", ("date_end", ">=", period_start), ("date_end", "<=", period_end),
            "&", ("next_payment_date", ">=", period_start), ("next_payment_date", "<=", period_end),
            "&", ("date_end", "!=", False), ("date_end", "<", today),
        ], period_start, period_end, today

    @api.model
    def _ensure_open_payment_for_service(self, service, period_start, period_end, today):
        """Lấy / tạo 1 phiếu chưa TT cho HĐ thuộc Lịch TT (không đụng state HĐ)."""
        Payment = self.env["phan.he.payment"]
        unpaid = service.payment_ids.filtered(
            lambda p: p.active and p.payment_state not in ("paid", "cancel")
        ).sorted(key=lambda p: (p.date_due or today, p.id))
        if unpaid:
            return unpaid[0]
        due = service.next_payment_date or service.date_end or period_end or today
        if due < today:
            pay_state = "overdue"
        elif due <= today + relativedelta(days=7):
            pay_state = "due_soon"
        else:
            pay_state = "pending"
        amount = service.next_payment_amount or service.contract_amount or 0.0
        period_label = (
            (service.package_name or "").strip()
            or f"{period_start.month:02d}/{period_start.year}"
        )
        return Payment.create({
            "service_id": service.id,
            "provider_id": service.provider_id.id if service.provider_id else False,
            "date_due": due,
            "amount": amount,
            "payment_state": pay_state,
            "period": period_label,
        })

    @api.model
    def get_payment_confirm_board(self, year=None, month=None, search=""):
        """Xác nhận TT = map 1:1 từ Lịch thanh toán (tháng + quá hạn).

        Mỗi HĐ trên Lịch TT → đúng 1 phiếu chưa TT (tạo nếu thiếu).
        Không đổi state/ops_status hợp đồng.
        """
        domain, period_start, period_end, today = self._internet_payment_schedule_domain(
            year, month
        )
        q = (search or "").strip()
        if q:
            domain = domain + [
                "|", "|", "|",
                ("name", "ilike", q),
                ("code", "ilike", q),
                ("customer_code", "ilike", q),
                ("store_id.name", "ilike", q),
            ]
        services = self.search(domain, order="date_end asc, id desc")
        payments = self.env["phan.he.payment"]
        for svc in services:
            payments |= self._ensure_open_payment_for_service(
                svc, period_start, period_end, today
            )
        fields_list = [
            "code", "service_id", "store_id", "store_name", "provider_id",
            "period", "date_due", "date_paid", "amount", "payment_state",
        ]
        rows = payments.read(fields_list)
        rows.sort(key=lambda r: (str(r.get("date_due") or ""), r.get("id") or 0))
        return {
            "records": rows,
            "total": len(rows),
            "year": period_start.year,
            "month": period_start.month,
        }

    @api.model
    def get_internet_alert_counts(self, year=None, month=None):
        """Số HĐ / phiếu thanh toán hiển thị badge sidebar Internet.

        year/month: tháng đang chọn trên Lịch TT / Dự kiến.
        Không truyền → tháng kế tiếp (mặc định mở danh sách).
        """
        today = fields.Date.context_today(self)
        soon30 = today + relativedelta(days=30)
        inet_base = [
            ("active", "=", True),
            ("service_type_id.code", "=", "internet"),
        ]
        list_active = self.search_count(inet_base + [("state", "=", "active")])
        list_suspend = self.search_count(inet_base + [
            "|",
            ("state", "=", "suspend"),
            ("ops_status", "=", "suspend"),
        ])
        list_liquidated = self.search_count(inet_base + [
            "|",
            ("state", "in", ["liquidated", "cancel"]),
            ("ops_status", "=", "liquidated"),
        ])
        expire_soon = self.search_count(inet_base + [
            ("state", "=", "active"),
            ("date_end", "!=", False),
            ("date_end", ">=", today),
            ("date_end", "<=", soon30),
        ])
        overdue = self.search_count(inet_base + [
            ("state", "=", "active"),
            ("date_end", "!=", False),
            ("date_end", "<", today),
        ])
        domain, period_start, _period_end, _today = self._internet_payment_schedule_domain(
            year, month
        )
        payment_period = self.search_count(domain)
        # Xác nhận TT map cùng Lịch TT — cùng số HĐ tháng + quá hạn
        return {
            "list_active": list_active,
            "list_suspend": list_suspend,
            "list_liquidated": list_liquidated,
            "expire_soon": expire_soon,
            "overdue_contract": overdue,
            "payment_schedule": payment_period,
            "payment_confirm": payment_period,
            "payment_forecast": payment_period,
            "alert_count": expire_soon + overdue,
            "payment_period_year": period_start.year,
            "payment_period_month": period_start.month,
        }

    @api.model
    def get_dashboard_data(self, month=None, year=None, region_id=None, store_id=None):
        """Dashboard Internet: read_group, lọc tháng/năm + miền + cửa hàng."""
        today = fields.Date.context_today(self)
        # Gọi cũ: get_dashboard_data("2026-09", region)
        if isinstance(month, str):
            extra_region = year
            year, month = self._parse_dash_month(month, today)
            if region_id in (None, False, "", "all") and extra_region not in (None, False):
                if not isinstance(extra_region, int) or extra_region < 1000:
                    region_id = extra_region
        else:
            if not year:
                year = today.year
            if not month:
                month = today.month
            year = int(year)
            month = int(month)

        region_id = self._dash_int(region_id)
        store_id = self._dash_int(store_id)

        m_start = fields.Date.to_date(f"{year}-{month:02d}-01")
        m_end = m_start + relativedelta(months=1, days=-1)
        prev_start = m_start - relativedelta(months=1)
        prev_end = m_start - relativedelta(days=1)

        base = self._dash_base_domain(region_id, store_id)
        miens = self.env["phan.he.mien"].search([("active", "=", True)])
        mien_meta = self._dash_mien_meta(miens)

        # Tổng quan tháng = cùng Kỳ/Tổng với Báo cáo → Chi phí tháng
        month_recs = self.search_month_cost_ky(year, month, extra_domain=base)
        by_rows, due_sum = self._dash_group_due_stores(month_recs)
        month_total = sum(self._month_ky_period_amount(r) for r in month_recs)

        prev_recs = self.search_month_cost_ky(prev_start.year, prev_start.month, extra_domain=base)
        month_delta = self._dash_delta(
            month_total,
            sum(self._month_ky_period_amount(r) for r in prev_recs),
        )

        # Sparkline: phân bổ các kỳ tháng N theo tuần (cùng nguồn Chi phí tháng)
        month_weeks = []
        day = m_start
        w = 1
        week_slots = []
        while day <= m_end:
            week_end = min(day + relativedelta(days=6), m_end)
            week_slots.append((w, day, week_end))
            day = week_end + relativedelta(days=1)
            w += 1
        week_amts = [0.0] * len(week_slots)
        last_i = len(week_slots) - 1
        for rec in month_recs:
            amt = self._month_ky_period_amount(rec)
            de = rec.date_end
            placed = False
            if de:
                for i, (_wn, d0, d1) in enumerate(week_slots):
                    if d0 <= de <= d1:
                        week_amts[i] += amt
                        placed = True
                        break
                if not placed and de < m_start and last_i >= 0:
                    week_amts[0] += amt
                    placed = True
            if not placed and last_i >= 0:
                week_amts[last_i] += amt
        for i, (wn, d0, _d1) in enumerate(week_slots):
            month_weeks.append({
                "key": f"W{wn}",
                "label": f"Tuần {wn}",
                "full": f"{d0.day:02d}/{d0.month:02d}",
                "amount": week_amts[i],
            })

        # Xu hướng 6 tháng — mỗi tháng = Tổng chi phí tháng (Báo cáo)
        trend = []
        for i in range(5, -1, -1):
            ts = m_start - relativedelta(months=i)
            trend.append({
                "key": f"{ts.year}-{ts.month:02d}",
                "label": f"Th{ts.month}",
                "full": f"{ts.month:02d}/{ts.year}",
                "amount": self.sum_month_cost_ky(ts.year, ts.month, extra_domain=base),
            })

        region_rows = []
        ky_sum = {}
        for rec in month_recs:
            mid = rec.mien_id.id or 0
            ky_sum[mid] = ky_sum.get(mid, 0.0) + self._month_ky_period_amount(rec)
        for m in mien_meta:
            mid = m["id"]
            amt = float(ky_sum.get(mid, 0.0) or 0.0)
            prev_amt = sum(
                self._month_ky_period_amount(r)
                for r in prev_recs
                if (r.mien_id.id or 0) == mid
            )
            cnt = len([r for r in month_recs if (r.mien_id.id or 0) == mid])
            pct = round((amt / month_total) * 100, 1) if month_total else 0.0
            region_rows.append({
                **m,
                "amount": amt,
                "pct": pct,
                "count": cnt,
                "delta": self._dash_delta(amt, prev_amt),
            })
        if month_total and region_rows:
            drift = round(100.0 - sum(r["pct"] for r in region_rows), 1)
            if drift:
                region_rows[0]["pct"] = round(region_rows[0]["pct"] + drift, 1)

        year_history = {}
        year_rows_by_year = {}
        year_bars = []
        for y in range(year - 3, year + 1):
            ys = fields.Date.to_date(f"{y}-01-01")
            ye = fields.Date.to_date(f"{y}-12-31")
            y_recs = self.search(base + self._dash_cost_domain(ys, ye), order="id desc")
            y_rows, y_sum = self._dash_group_due_stores(y_recs)
            year_history[y] = y_sum
            year_rows_by_year[y] = y_rows
            year_bars.append({
                "year": y,
                "amount": self._dash_mien_total(y_sum, mien_meta),
                "is_current": y == year,
            })
        cur_year = year_bars[-1]["amount"] if year_bars else 0.0
        prev_year_amt = year_bars[-2]["amount"] if len(year_bars) > 1 else 0.0
        year_delta = self._dash_delta(cur_year, prev_year_amt)
        year_by_rows = year_rows_by_year.get(year, {})
        year_sum = year_history.get(year, {})

        usage_rows = self.read_group(
            base, ["id:count"], ["ops_status"]
        )
        usage_map = {r.get("ops_status") or "": r.get("ops_status_count") or r.get("id_count") or 0 for r in usage_rows}
        # Odoo read_group count key is typically ops_status_count
        def _cnt(key):
            for row in usage_rows:
                if (row.get("ops_status") or "") == key:
                    for k, v in row.items():
                        if k.endswith("_count") and k != "__count":
                            return int(v or 0)
                    return int(row.get("__count") or 0)
            return 0

        n_active = _cnt("active")
        n_suspend = _cnt("suspend")
        n_liq = _cnt("liquidated")
        total_cnt = sum(_cnt(k) for k in ("active", "suspend", "liquidated", "expired")) or (
            n_active + n_suspend + n_liq
        )
        if not total_cnt:
            total_cnt = n_active + n_suspend + n_liq
        active_pct = round((n_active / total_cnt) * 100) if total_cnt else 0

        # Widget 6: T1 → tháng đang chọn — mỗi cột = Chi phí tháng
        month_bars = []
        for mo in range(1, month + 1):
            month_bars.append({
                "month": mo,
                "label": f"T{mo}",
                "amount": self.sum_month_cost_ky(year, mo, extra_domain=base),
            })

        detail_tables = []
        for m in mien_meta:
            rows = by_rows.get(m["id"], [])
            spark = []
            for i in range(3, -1, -1):
                ts = m_start - relativedelta(months=i)
                spark.append({
                    "key": f"{ts.year}-{ts.month:02d}",
                    "amount": self.sum_month_cost_ky(
                        ts.year,
                        ts.month,
                        extra_domain=self._dash_base_domain(m["id"], store_id),
                    ),
                })
            spark_max = max((s["amount"] for s in spark), default=1) or 1
            for item in spark:
                item["pct"] = max(8, round((item["amount"] / spark_max) * 100)) if item["amount"] else 8
            y_amt = float(year_sum.get(m["id"], 0.0) or 0.0)
            py_amt = float(year_history.get(year - 1, {}).get(m["id"], 0.0) or 0.0)
            year_spark = []
            for y in range(year - 3, year + 1):
                year_spark.append({
                    "key": str(y),
                    "amount": float(year_history.get(y, {}).get(m["id"], 0.0) or 0.0),
                })
            ys_max = max((s["amount"] for s in year_spark), default=1) or 1
            for item in year_spark:
                item["pct"] = max(8, round((item["amount"] / ys_max) * 100)) if item["amount"] else 8
            detail_tables.append({
                **m,
                "amount": ky_sum.get(m["id"], 0.0),
                "delta": 0.0,
                "count": len(rows),
                "rows": rows,
                "spark": spark,
                "year_amount": y_amt,
                "year_delta": self._dash_delta(y_amt, py_amt),
                "year_count": len(year_by_rows.get(m["id"], [])),
                "year_spark": year_spark,
                "year_rows": rows[:8],
            })

        Store = self.env["phan.he.store"]
        store_dom = []
        if "active" in Store._fields:
            store_dom.append(("active", "=", True))
        if region_id:
            store_dom.append(("mien_id", "=", region_id))
        stores = Store.search(store_dom, limit=500, order="name")
        store_options = [{"id": "all", "name": "Tất cả cửa hàng"}] + [
            {"id": s.id, "name": s.name} for s in stores
        ]

        month_options = []
        for i in range(0, 18):
            dt = today.replace(day=1) - relativedelta(months=i)
            month_options.append({
                "value": f"{dt.year}-{dt.month:02d}",
                "label": f"Tháng {dt.month}/{dt.year}",
            })

        return {
            "user_name": self.env.user.name or "Admin",
            "selected_month": f"{year}-{month:02d}",
            "selected_month_label": f"Tháng {month}/{year}",
            "selected_year": year,
            "selected_region": region_id or "all",
            "selected_store": store_id or "all",
            "month_total": month_total,
            "month_delta": month_delta,
            "month_weeks": month_weeks,
            "trend": trend,
            "regions": region_rows,
            "region_options": [{"id": "all", "name": "Tất cả khu vực"}] + [
                {"id": m["id"], "name": m["name"]} for m in mien_meta
            ],
            "store_options": store_options,
            "year_total": cur_year,
            "year_delta": year_delta,
            "year_bars": year_bars,
            "month_bars": month_bars,
            "usage": {
                "active_pct": active_pct,
                "active": n_active,
                "suspend": n_suspend,
                "liquidated": n_liq,
                "total": total_cnt,
            },
            "kpis": region_rows,
            "detail_tables": detail_tables,
            "month_options": month_options,
            "updated_at": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ).strftime("%H:%M %d/%m/%Y"),
            **self.get_internet_alert_counts(),
        }

    @api.model
    def _dash_int(self, value):
        if value in (None, False, "", "all", "0", 0, "false"):
            return False
        try:
            return int(value)
        except (TypeError, ValueError):
            mien = self.env["phan.he.mien"].search(
                [("code", "=", str(value).upper())], limit=1
            )
            return mien.id or False

    @api.model
    def _internet_period_bounds(self, period):
        today = fields.Date.context_today(self)
        year = today.year
        month = today.month
        if period in ("month", "report_month"):
            start = today.replace(day=1)
            end = (start + relativedelta(months=1)) - relativedelta(days=1)
            return start, end
        if period in ("quarter", "report_quarter"):
            q_start_month = ((month - 1) // 3) * 3 + 1
            start = today.replace(month=q_start_month, day=1)
            end = (start + relativedelta(months=3)) - relativedelta(days=1)
            return start, end
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        return start, end

    @api.model
    def internet_board_domain(self, filter_code="all"):
        """Domain OWL danh sách Internet — không đổi action xmlid."""
        today = fields.Date.context_today(self)
        soon30 = today + relativedelta(days=30)
        domain = [
            ("active", "=", True),
            ("service_type_id.code", "=", "internet"),
        ]
        code = filter_code or "all"
        if code == "active":
            domain.append(("state", "=", "active"))
        elif code in ("suspend", "paused"):
            domain.append(("state", "=", "suspend"))
        elif code == "liquidated":
            domain.append(("state", "in", ("liquidated", "cancel")))
        elif code == "expire_soon":
            domain += [
                ("state", "=", "active"),
                ("date_end", ">=", today),
                ("date_end", "<=", soon30),
            ]
        elif code == "expired":
            domain += [
                ("state", "=", "active"),
                ("date_end", "<", today),
            ]
        elif code in ("payment_due", "payment_schedule", "payment_forecast"):
            # Cùng domain Lịch TT / Dự kiến / Xác nhận (tháng + quá hạn)
            pay_domain, _ps, _pe, _td = self._internet_payment_schedule_domain()
            # _internet_payment_schedule_domain đã có active + type + state
            return pay_domain
        elif code in ("month", "quarter", "year", "report_month", "report_quarter", "report_year"):
            start, end = self._internet_period_bounds(code)
            domain += self._dash_overlap(start, end)
        return domain

    @api.model
    def search_internet_payment_period(self, year=None, month=None, search="", region=False):
        """API danh sách Lịch TT / Dự kiến — cùng domain badge sidebar."""
        domain, period_start, period_end, _today = self._internet_payment_schedule_domain(
            year, month
        )
        if region:
            domain = list(domain) + [("store_mien", "=", region)]
        q = (search or "").strip()
        if q:
            domain = list(domain) + [
                "|", "|", "|",
                ("name", "ilike", q),
                ("code", "ilike", q),
                ("customer_code", "ilike", q),
                ("store_id.name", "ilike", q),
            ]
        fields_list = [
            "name", "code", "customer_code", "store_id", "provider_id",
            "date_start", "date_end", "bandwidth", "contract_amount",
            "ops_status", "state", "store_mien", "next_payment_amount",
            "next_payment_date", "note", "invoice_filename",
        ]
        rows = self.search_read(
            domain,
            fields_list,
            order="date_end asc, id desc",
            limit=2000,
        )
        return {
            "records": rows,
            "total": len(rows),
            "year": period_start.year,
            "month": period_start.month,
            "period_start": str(period_start),
            "period_end": str(period_end),
        }

    @api.model
    def search_internet_board(self, filter_code="all", limit=300, offset=0):
        domain = self.internet_board_domain(filter_code)
        fields_list = [
            "name", "code", "customer_code", "store_id", "provider_id",
            "date_start", "date_end", "bandwidth", "contract_amount",
            "next_payment_amount", "ops_status", "state",
            "remaining_days", "remaining_time", "alert_level", "store_mien",
        ]
        return self.search_read(
            domain,
            fields_list,
            offset=offset,
            limit=limit,
            order=self.INTERNET_LIST_ORDER,
        )

    @api.model
    def _excel_dmy(self, val):
        if not val:
            return ""
        try:
            y, m, d = str(val)[:10].split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            return str(val)

    def _excel_payment_content(self, rec, month, year):
        pay = rec._get_next_payment_record()
        if pay and (pay.payment_content or "").strip():
            return pay.payment_content.strip()
        pkg = (rec.package_name or rec.duration or "").strip()
        start = self._excel_dmy(rec.date_start)
        end = self._excel_dmy(rec.date_end)
        store = rec.store_id.name or rec.name or ""
        if pkg and start and end:
            return f"Thanh toán {pkg} từ: {start} - {end}"
        if start and end:
            return f"Thanh toán cước internet {store} từ: {start} - {end}"
        return f"Thanh toán cước internet {store} Tháng {month}/{year}"

    def _excel_account_block(self, rec):
        pay = rec._get_next_payment_record()
        bank = pay.bank_account_id if pay else False
        if not bank and rec.provider_id:
            bank = rec.provider_id.bank_account_ids.filtered("is_default")[:1] \
                or rec.provider_id.bank_account_ids[:1]
        name = ""
        stk = ""
        bank_name = ""
        ndung = ""
        if bank:
            name = bank.account_name or rec.provider_id.name or ""
            stk = bank.account_number or ""
            bank_name = " - ".join(
                p for p in [(bank.bank_name or "").strip(), (bank.bank_branch or "").strip()] if p
            )
            ndung = (bank.transfer_content_template or "").strip()
        elif rec.payment_info_text:
            return rec.payment_info_text.strip()
        if pay and (pay.payment_content or "").strip():
            ndung = pay.payment_content.strip()
        lines = [
            f"- TÊN TK: {name}",
            f"- STK: {stk}",
            f"- NGÂN HÀNG: {bank_name}",
        ]
        if ndung:
            lines.append(f"- Nội dung: {ndung}")
        return "\n".join(lines)

    @api.model
    def export_internet_list_excel(self, filter_code="payment_due", region=None, search=""):
        """Xuất Excel mẫu thanh toán internet (STT, CÔNG TY, CỬA HÀNG, MÃ KH, NỘI DUNG, SỐ TIỀN, TK)."""
        import base64
        import io
        import os

        try:
            import openpyxl
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        except ImportError as exc:
            from odoo.exceptions import UserError

            raise UserError("Thiếu thư viện openpyxl trên server.") from exc

        domain = self.internet_board_domain(filter_code or "payment_due")
        if region:
            domain.append(("store_mien", "=", region))
        q = (search or "").strip()
        if q:
            domain += [
                "|", "|", "|",
                ("name", "ilike", q),
                ("code", "ilike", q),
                ("customer_code", "ilike", q),
                ("store_id.name", "ilike", q),
            ]
        recs = self.search(domain, order="remaining_days asc, date_end asc, id desc")
        today = fields.Date.context_today(self)
        month, year = today.month, today.year

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"T{month} {year}"[:31]

        font_title = Font(name="Times New Roman", size=18, bold=True)
        font_header = Font(name="Times New Roman", size=10, bold=True)
        font_cell = Font(name="Times New Roman", size=10)
        font_cell_bold = Font(name="Times New Roman", size=10, bold=True)
        fill_peach = PatternFill("solid", fgColor="FBE4D5")
        thin = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        num_fmt = '_-* #,##0\\ _₫_-;\\-* #,##0\\ _₫_-;_-* "-"??\\ _₫_-;_-@'

        ws.merge_cells("A1:G1")
        ws.row_dimensions[1].height = 36
        ws["A1"].value = f"DANH SÁCH THANH TOÁN INTERNET THÁNG T{month}/{year} "
        ws["A1"].font = font_title
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 18
        ws.row_dimensions[3].height = 30.75

        headers = ["STT", "CÔNG TY", "CỬA HÀNG", "MÃ KH", "NỘI DUNG", "SỐ TIỀN", "TÊN TÀI KHOẢN"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(3, col, h)
            cell.font = font_header
            cell.fill = fill_peach
            cell.border = thin
            cell.alignment = align_center
            if col == 6:
                cell.number_format = num_fmt

        data_start = 4
        row_i = data_start
        for idx, rec in enumerate(recs, 1):
            acct = self._excel_account_block(rec)
            content = self._excel_payment_content(rec, month, year)
            ws.row_dimensions[row_i].height = max(45, 18 * (acct.count("\n") + 2))
            values = [
                idx,
                "ST",
                rec.store_id.name or rec.name or "",
                rec.customer_code or "",
                content,
                float(rec.next_payment_amount or 0.0),
                acct,
            ]
            for col, val in enumerate(values, 1):
                cell = ws.cell(row_i, col, val)
                cell.border = thin
                if col in (1, 2):
                    cell.font = font_cell_bold
                    cell.alignment = align_center
                elif col == 6:
                    cell.font = font_cell
                    cell.alignment = align_center
                    cell.number_format = num_fmt
                elif col == 7:
                    cell.font = font_cell
                    cell.alignment = align_left
                    cell.number_format = "@"
                else:
                    cell.font = font_cell
                    cell.alignment = align_center if col in (3, 4) else align_left
            row_i += 1

        data_end = row_i - 1 if recs else data_start - 1
        total_row = row_i
        ws.row_dimensions[total_row].height = 31.5
        ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
        for col in range(1, 8):
            cell = ws.cell(total_row, col)
            cell.border = thin
            if col <= 6:
                cell.fill = fill_peach
            cell.font = font_header if col in (1, 6) else font_cell
            cell.alignment = align_center
        ws.cell(total_row, 1).value = "TỔNG THANH TOÁN"
        ws.cell(total_row, 6).value = f"=SUM(F{data_start}:F{data_end})" if recs else 0
        ws.cell(total_row, 6).number_format = num_fmt
        ws.cell(total_row, 6).font = font_header

        sig_row = total_row + 2
        ws.merge_cells(start_row=sig_row, start_column=2, end_row=sig_row, end_column=4)
        ws.merge_cells(start_row=sig_row, start_column=5, end_row=sig_row, end_column=6)
        for col, label in ((2, "NGƯỜI ĐỀ NGHỊ"), (5, "KẾ TOÁN"), (7, "NGƯỜI DUYỆT")):
            cell = ws.cell(sig_row, col, label)
            cell.font = font_header
            cell.alignment = Alignment(horizontal="center", vertical="center")

        name_row = sig_row + 6
        ws.merge_cells(start_row=name_row, start_column=2, end_row=name_row, end_column=4)
        ws.merge_cells(start_row=name_row, start_column=6, end_row=name_row, end_column=7)
        proposer = (self.env.user.name or "").upper()
        ws.cell(name_row, 2).value = proposer
        ws.cell(name_row, 2).font = font_cell_bold
        ws.cell(name_row, 2).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(name_row, 7).font = font_cell_bold
        ws.cell(name_row, 7).alignment = Alignment(horizontal="center", vertical="center")

        for letter, width in {
            "A": 6.29, "B": 10.86, "C": 17.71, "D": 21.71, "E": 39.66, "F": 13.43, "G": 68.0,
        }.items():
            ws.column_dimensions[letter].width = width

        try:
            from openpyxl.drawing.image import Image as XLImage
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "description")
            logo0 = os.path.join(static_dir, "payment_logo_0.png")
            if os.path.isfile(logo0):
                img0 = XLImage(logo0)
                img0.width = 228
                img0.height = 77
                ws.add_image(img0, "A1")
        except Exception:
            pass

        buf = io.BytesIO()
        wb.save(buf)
        fname = f"Thanh toan internet T{month} {year}.xlsx"
        return {
            "file_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "filename": fname,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

    @api.model
    def _dash_base_domain(self, region_id=None, store_id=None):
        domain = [
            ("active", "=", True),
            ("state", "not in", ("cancel", "draft")),
        ]
        stype = self.env["phan.he.service.type"].search(
            [("code", "=", "internet")], limit=1
        )
        if stype:
            domain.append(("service_type_id", "=", stype.id))
        else:
            domain.append(("category", "=", "internet"))
        if store_id:
            domain.append(("store_id", "=", store_id))
        elif region_id:
            domain.append(("mien_id", "=", region_id))
        return domain

    @api.model
    def _dash_overlap(self, start, end):
        return [
            "|", ("date_start", "=", False), ("date_start", "<=", end),
            "|", ("date_end", "=", False), ("date_end", ">=", start),
        ]

    @api.model
    def _dash_group_due_stores(self, recs):
        """Gộp 1 cửa hàng / miền; bỏ Tạm ngưng / Thanh lý."""
        blocked_dom = [
            ("active", "=", True),
            "|", ("ops_status", "in", ("suspend", "liquidated")),
            ("state", "in", ("suspend", "liquidated", "cancel")),
        ]
        stype = self.env["phan.he.service.type"].search([("code", "=", "internet")], limit=1)
        if stype:
            blocked_dom.append(("service_type_id", "=", stype.id))
        else:
            blocked_dom.append(("category", "=", "internet"))
        blocked = set(self.search(blocked_dom).mapped("store_id").ids)
        by_best = {}
        for svc in recs:
            if (svc.ops_status or "") in ("suspend", "liquidated"):
                continue
            if (svc.state or "") in ("suspend", "liquidated", "cancel", "expired"):
                continue
            if svc.store_id.id and svc.store_id.id in blocked:
                continue
            mid = svc.mien_id.id or 0
            store_key = svc.store_id.id or (svc.store_id.name or svc.name or svc.id)
            key = (mid, store_key)
            amt = float(svc.next_payment_amount or 0.0)
            days = int(svc.remaining_days or 0)
            row = by_best.get(key)
            if not row:
                by_best[key] = {
                    "id": svc.id,
                    "store": svc.store_id.name or "—",
                    "provider": svc.provider_id.name or "—",
                    "bandwidth": svc.bandwidth or "—",
                    "amount": amt,
                    "remaining_days": days,
                    "remaining_time": svc.remaining_time or "",
                }
                continue
            row["amount"] += amt
            if days < row["remaining_days"]:
                row["id"] = svc.id
                row["provider"] = svc.provider_id.name or row["provider"]
                row["bandwidth"] = svc.bandwidth or row["bandwidth"]
                row["remaining_days"] = days
                row["remaining_time"] = svc.remaining_time or row["remaining_time"]
        by_rows = {}
        due_sum = {}
        for (mid, _sk), row in by_best.items():
            by_rows.setdefault(mid, []).append(row)
            due_sum[mid] = due_sum.get(mid, 0.0) + row["amount"]
        for mid, rows in by_rows.items():
            rows.sort(key=lambda r: (r["remaining_days"], r["store"]))
            for i, row in enumerate(rows, 1):
                row["stt"] = i
        return by_rows, due_sum

    @api.model
    def _dash_mien_total(self, due_sum, mien_meta):
        return sum(float(due_sum.get(m["id"], 0.0) or 0.0) for m in mien_meta)

    @api.model
    def _dash_cost_domain(self, start, end):
        """HĐ Đang sử dụng còn hiệu lực trong kỳ — cộng Số tiền thanh toán."""
        if not start or not end or start > end:
            return [("id", "=", 0)]
        return [
            ("ops_status", "=", "active"),
        ] + self._dash_overlap(start, end)

    @api.model
    def _month_ky_bounds(self, year, month):
        """Thời điểm lập kỳ tháng N → (start, end, as_of, soon)."""
        today = fields.Date.context_today(self)
        year = int(year)
        month = min(12, max(1, int(month)))
        start = fields.Date.from_string(f"{year:04d}-{month:02d}-01")
        end = (start + relativedelta(months=1)) - relativedelta(days=1)
        if start <= today <= end:
            as_of = today
        elif end < today:
            as_of = end
        else:
            as_of = start
        soon = as_of + relativedelta(days=30)
        return start, end, as_of, soon

    @api.model
    def _month_ky_period_amount(self, rec):
        """Số tiền kỳ = Lịch thanh toán (next_payment_amount)."""
        return float(rec.next_payment_amount or rec.contract_amount or 0.0)

    @api.model
    def _month_ky_paid_amount(self, rec, start, end, as_of, soon):
        """Đã TT = xác nhận thanh toán (paid) gắn kỳ."""
        paid_pays = rec.payment_ids.filtered(
            lambda p: p.active and p.payment_state == "paid"
        )
        in_month = paid_pays.filtered(
            lambda p: p.date_paid and start <= p.date_paid <= end
        )
        if in_month:
            return sum(float(p.amount or 0.0) for p in in_month)
        window_start = as_of - relativedelta(days=365)
        in_ky = paid_pays.filtered(
            lambda p: p.date_due and window_start <= p.date_due <= soon
        )
        return sum(float(p.amount or 0.0) for p in in_ky)

    @api.model
    def search_month_cost_ky(self, year, month, extra_domain=None):
        """Kỳ TT tháng N (cùng Báo cáo / Chi phí tháng):

        - Đến hạn trong vòng 30 ngày kể từ thời điểm lập kỳ
        - + Quá hạn chưa hoàn tất thanh toán
        """
        start, end, as_of, soon = self._month_ky_bounds(year, month)
        domain = [
            ("active", "=", True),
            ("service_type_id.code", "=", "internet"),
            ("state", "=", "active"),
            ("ops_status", "=", "active"),
            ("date_end", "!=", False),
            ("date_end", "<=", soon),
        ]
        if extra_domain:
            domain = domain + list(extra_domain)
        candidates = self.search(domain, order="date_end asc, id asc")
        result = self.browse()
        for rec in candidates:
            amt = self._month_ky_period_amount(rec)
            paid_sum = self._month_ky_paid_amount(rec, start, end, as_of, soon)
            remain = max(amt - paid_sum, 0.0)
            overdue = bool(rec.date_end and rec.date_end < as_of)
            if overdue and remain <= 0 and amt > 0:
                continue
            result |= rec
        return result

    @api.model
    def sum_month_cost_ky(self, year, month, extra_domain=None):
        """Tổng chi phí tháng N = tổng tiền các kỳ đưa vào tháng N."""
        recs = self.search_month_cost_ky(year, month, extra_domain=extra_domain)
        return sum(self._month_ky_period_amount(r) for r in recs)

    @api.model
    def _dash_due_soon_domain(self, start, end, soon_days=30):
        """HĐ đang dùng, thời gian còn lại ≤ 30 ngày (kể cả quá hạn).

        Dùng as_of theo kỳ (giống Chi phí tháng): tháng chứa tại → hôm nay;
        tháng quá khứ → cuối tháng; tương lai → đầu tháng.
        """
        if not start or not end or start > end:
            return [("id", "=", 0)]
        today = fields.Date.context_today(self)
        if start <= today <= end:
            as_of = today
        elif end < today:
            as_of = end
        else:
            as_of = start
        soon = as_of + relativedelta(days=int(soon_days or 30))
        return [
            ("ops_status", "=", "active"),
            ("state", "=", "active"),
            ("ops_status", "not in", ("suspend", "liquidated")),
            ("state", "not in", ("suspend", "liquidated", "cancel", "expired")),
            ("date_end", "!=", False),
            ("date_end", "<=", soon),
        ]

    @api.model
    def _dash_pay_due_domain(self, start, end, soon_days=30):
        """API cũ: cần thanh toán ≤ 30 ngày trong kỳ."""
        return self._dash_due_soon_domain(start, end, soon_days=soon_days)

    @api.model
    def _dash_sum(self, domain):
        """Tổng chi phí dashboard = Số tiền thanh toán (không dùng cước tháng)."""
        groups = self.read_group(domain, ["next_payment_amount:sum"], [])
        if not groups:
            return 0.0
        return float(groups[0].get("next_payment_amount") or 0.0)

    @api.model
    def _parse_dash_month(self, selected_month, today):
        raw = str(selected_month or "").strip()
        if raw:
            if "-" in raw and len(raw) >= 7:
                parts = raw.split("-")
                try:
                    return int(parts[0]), int(parts[1])
                except (TypeError, ValueError):
                    pass
            if "/" in raw:
                parts = raw.split("/")
                try:
                    if len(parts[0]) == 4:
                        return int(parts[0]), int(parts[1])
                    return int(parts[1]), int(parts[0])
                except (TypeError, ValueError, IndexError):
                    pass
        return today.year, today.month

    @api.model
    def _dash_mien_meta(self, miens):
        ordered = []
        used = set()
        by_code = {(m.code or "").upper(): m for m in miens}
        for code in self.REGION_ORDER:
            m = by_code.get(code)
            if m:
                ordered.append(m)
                used.add(m.id)
        for m in miens:
            if m.id not in used:
                ordered.append(m)
        rows = []
        fallback = ["#2f80ed", "#f2994a", "#27ae60", "#9b51e0"]
        for i, m in enumerate(ordered):
            code = (m.code or "").upper()
            rows.append({
                "id": m.id,
                "code": code,
                "name": m.name or code,
                "short": (m.name or "").replace("Miền ", "").strip() or code,
                "color": self.REGION_COLORS.get(code) or fallback[i % len(fallback)],
            })
        return rows

    @api.model
    def _dash_delta(self, current, previous):
        if not previous:
            return 0.0 if not current else 100.0
        return round(((current - previous) / previous) * 100.0, 1)
