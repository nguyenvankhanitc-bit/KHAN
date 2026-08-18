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
        default=lambda self: self.env["ir.sequence"].next_by_code("phan.he.service") or "New",
    )
    name = fields.Char(string="Tiêu đề", compute="_compute_name", store=True)
    store_id = fields.Many2one(
        "phan.he.store", string="Cửa hàng", required=True,
        tracking=True, ondelete="restrict", index=True,
    )
    mien_id = fields.Many2one(related="store_id.mien_id", store=True, string="Miền")
    area_id = fields.Many2one(related="store_id.area_id", store=True, string="Khu vực")
    store_mien = fields.Selection(related="store_id.mien", store=True, string="Miền (cũ)")
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
    usage_address = fields.Text(string="Địa chỉ")
    technical_info = fields.Text(string="Thông tin kỹ thuật")
    stt = fields.Integer(string="STT", copy=False, index=True)
    date_start = fields.Date(string="Ngày bắt đầu", tracking=True)
    date_end = fields.Date(string="Ngày kết thúc", tracking=True)
    contract_amount = fields.Monetary(
        string="Cước tháng",
        currency_field="currency_id",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self._default_currency_vnd(),
    )
    duration = fields.Char(compute="_compute_duration", store=True, string="Thời hạn")
    remaining_time = fields.Char(
        compute="_compute_remaining",
        string="Thời gian còn lại",
    )
    remaining_days = fields.Integer(
        compute="_compute_remaining",
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
        tracking=True, ondelete="restrict", index=True,
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
        string="Kỳ TT gần nhất",
    )
    next_invoice_number = fields.Char(
        string="HĐ / Số hóa đơn",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
    )
    next_payment_amount = fields.Monetary(
        string="Số tiền TT",
        currency_field="currency_id",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
    )
    next_payment_date = fields.Date(
        string="Ngày TT tiếp theo",
        compute="_compute_next_payment_fields",
        inverse="_inverse_next_payment_fields",
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
        "contract_amount",
    )
    def _compute_next_payment_fields(self):
        for rec in self:
            pay = rec._get_next_payment_record()
            rec.next_invoice_number = pay.invoice_number if pay else False
            rec.next_payment_amount = pay.amount if pay else rec.contract_amount
            rec.next_payment_date = pay.date_due if pay else False

    def _inverse_next_payment_fields(self):
        """Cho phép nhập liệu trên bảng tổng → ghi vào kỳ thanh toán (tạo mới nếu chưa có).

        Cập nhật payment bằng SQL để tránh ORM modified() search theo
        next_payment_id (lỗi khi field chưa store / registry cũ).
        """
        Payment = self.env["phan.he.payment"]
        for rec in self:
            pay = rec._get_next_payment_record()
            invoice_number = rec.next_invoice_number or False
            amount = rec.next_payment_amount or rec.contract_amount or 0.0
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
                        invoice_number,
                        amount,
                        date_due,
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

    def _inverse_payment_info_text(self):
        for rec in self:
            rec.payment_info_manual = rec.payment_info_text

    @api.model_create_multi
    def create(self, vals_list):
        next_stt = self._next_stt()
        for vals in vals_list:
            if not vals.get("stt"):
                vals["stt"] = next_stt
                next_stt += 1
            if "bandwidth" in vals:
                vals["bandwidth"] = self._normalize_bandwidth(vals.get("bandwidth"))
            if vals.get("ops_status") and not vals.get("state"):
                vals["state"] = vals["ops_status"]
            elif vals.get("state") and not vals.get("ops_status"):
                vals["ops_status"] = self._map_state_to_ops(vals["state"])
            else:
                vals.setdefault("ops_status", "active")
                vals.setdefault("state", vals.get("ops_status", "active"))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if "bandwidth" in vals:
            vals["bandwidth"] = self._normalize_bandwidth(vals.get("bandwidth"))
        if "ops_status" in vals and "state" not in vals:
            vals["state"] = vals["ops_status"]
        elif "state" in vals and "ops_status" not in vals:
            vals["ops_status"] = self._map_state_to_ops(vals["state"])
        return super().write(vals)

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

            if days > 0:
                rec.remaining_time = f"Còn {days} ngày"
            elif days == 0:
                rec.remaining_time = "Hết hạn hôm nay"
            else:
                rec.remaining_time = f"Trễ {abs(days)} ngày"

            if days < 0:
                rec.alert_level = "expired"
                icon = "fa-times-circle"
                icon_css = "text-danger"
                label = rec.remaining_time
            elif days <= 7:
                rec.alert_level = "danger"
                icon = "fa-exclamation-circle"
                icon_css = "text-danger"
                label = rec.remaining_time
            elif days <= 30:
                rec.alert_level = "warn"
                icon = "fa-exclamation-triangle"
                icon_css = "text-warning"
                label = rec.remaining_time
            else:
                rec.alert_level = "ok"
                icon = "fa-check-circle"
                icon_css = "text-success"
                label = rec.remaining_time

            rec.remaining_alert = (
                f'<span class="o_phan_he_remaining_alert">'
                f'<i class="fa {icon} {icon_css}" title="Cảnh báo hết hạn"/> '
                f'<b style="color:#111827">{label}</b></span>'
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
        """Giữ tương thích: đánh dấu Thanh lý."""
        self.write({"state": "liquidated"})

    def action_liquidate(self):
        self.write({"state": "liquidated"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    @api.onchange("store_id")
    def _onchange_store_id_address(self):
        if self.store_id and self.store_id.address and not self.usage_address:
            self.usage_address = self.store_id.address

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
                "default_amount": self.contract_amount,
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
                row["amount"] += svc.contract_amount or 0.0
                totals["amount"] += svc.contract_amount or 0.0

            if svc.date_end and not is_closed:
                if svc.date_end < today:
                    row["overdue"] += 1
                    totals["overdue"] += 1
                elif today <= svc.date_end <= soon30 and svc.state == "active":
                    row["expire_soon"] += 1
                    totals["expire_soon"] += 1

        return {"by_mien": by_mien, "totals": totals}
