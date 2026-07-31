# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class PhanHePayment(models.Model):
    _name = "phan.he.payment"
    _description = "Thanh toán"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_due desc, code, id desc"
    _rec_names_search = ["code", "invoice_number", "period"]

    code = fields.Char(
        string="Mã thanh toán", required=True, copy=False, tracking=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("phan.he.payment") or "New",
    )
    service_id = fields.Many2one(
        "phan.he.service", string="Hợp đồng", required=True,
        tracking=True, ondelete="restrict", index=True,
    )
    store_id = fields.Many2one(related="service_id.store_id", store=True, string="Cửa hàng")
    store_name = fields.Char(related="store_id.name", string="Tên cửa hàng", readonly=True)
    mien_id = fields.Many2one(related="service_id.mien_id", store=True, string="Miền")
    area_id = fields.Many2one(related="service_id.area_id", store=True, string="Khu vực")
    provider_id = fields.Many2one(
        "phan.he.provider", string="Nhà cung cấp",
        tracking=True, ondelete="restrict", index=True,
    )
    bank_account_id = fields.Many2one(
        "phan.he.bank.account", string="Tài khoản nhận",
        domain="[('provider_id', '=', provider_id)]",
        tracking=True, ondelete="restrict",
    )
    provider_account_name = fields.Char(related="bank_account_id.account_name")
    provider_account_number = fields.Char(related="bank_account_id.account_number")
    provider_bank_name = fields.Char(related="bank_account_id.bank_name")
    provider_bank_branch = fields.Char(related="bank_account_id.bank_branch")

    period = fields.Char(string="Kỳ thanh toán", tracking=True)
    date_due = fields.Date(string="Ngày TT tiếp theo", tracking=True)
    date_paid = fields.Date(string="Ngày thanh toán thực tế", tracking=True)
    amount = fields.Monetary(string="Số tiền", currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one(
        related="service_id.currency_id", store=True, readonly=True,
    )
    payment_state = fields.Selection(
        selection=[
            ("draft", "Nháp"),
            ("not_due", "Chưa đến hạn"),
            ("due_soon", "Sắp đến hạn"),
            ("pending", "Chờ thanh toán"),
            ("overdue", "Quá hạn"),
            ("paid", "Đã thanh toán"),
            ("cancel", "Đã hủy"),
        ],
        string="Trạng thái thanh toán",
        default="pending",
        required=True,
        tracking=True,
    )
    invoice_number = fields.Char(string="Số hóa đơn", tracking=True)
    invoice_file = fields.Binary(string="File hóa đơn", attachment=True)
    invoice_filename = fields.Char(string="Tên file hóa đơn")
    invoice_ids = fields.One2many("phan.he.invoice", "payment_id", string="Hóa đơn")
    invoice_count = fields.Integer(compute="_compute_invoice_count")
    payment_content = fields.Text(string="Nội dung thanh toán", tracking=True)
    company_id = fields.Many2one(related="service_id.company_id", store=True, readonly=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã thanh toán phải duy nhất trong cùng công ty.",
    )

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.onchange("service_id")
    def _onchange_service_id(self):
        if not self.service_id:
            return
        if not self.amount:
            self.amount = self.service_id.contract_amount
        if self.service_id.provider_id and not self.provider_id:
            self.provider_id = self.service_id.provider_id
        if self.provider_id and not self.bank_account_id:
            default_acc = self.provider_id.bank_account_ids.filtered("is_default")[:1]
            self.bank_account_id = default_acc or self.provider_id.bank_account_ids[:1]

    @api.onchange("provider_id")
    def _onchange_provider_id(self):
        self.bank_account_id = False
        if self.provider_id:
            default_acc = self.provider_id.bank_account_ids.filtered("is_default")[:1]
            self.bank_account_id = default_acc or self.provider_id.bank_account_ids[:1]
            if not self.payment_content and self.bank_account_id:
                self.payment_content = self.bank_account_id.transfer_content_template

    @api.onchange("bank_account_id")
    def _onchange_bank_account_id(self):
        if self.bank_account_id and self.bank_account_id.transfer_content_template:
            if not self.payment_content:
                self.payment_content = self.bank_account_id.transfer_content_template

    @api.onchange("date_paid")
    def _onchange_date_paid(self):
        if self.date_paid and self.payment_state not in ("cancel", "draft"):
            self.payment_state = "paid"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("service_id") and not vals.get("provider_id"):
                service = self.env["phan.he.service"].browse(vals["service_id"])
                if service.provider_id:
                    vals["provider_id"] = service.provider_id.id
            if vals.get("service_id") and not vals.get("amount"):
                service = self.env["phan.he.service"].browse(vals["service_id"])
                if service.contract_amount:
                    vals["amount"] = service.contract_amount
        return super().create(vals_list)

    def action_mark_paid(self):
        for rec in self:
            rec.write({
                "payment_state": "paid",
                "date_paid": rec.date_paid or fields.Date.context_today(rec),
            })

    def action_open_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Hóa đơn",
            "res_model": "phan.he.invoice",
            "view_mode": "list,form",
            "domain": [("payment_id", "=", self.id)],
            "context": {
                "default_payment_id": self.id,
                "default_service_id": self.service_id.id,
                "default_amount": self.amount,
                "default_invoice_number": self.invoice_number,
            },
        }

    @api.depends("code", "period", "invoice_number")
    def _compute_display_name(self):
        for rec in self:
            if rec.code and rec.invoice_number:
                rec.display_name = f"[{rec.code}] HĐ {rec.invoice_number}"
            elif rec.code and rec.period:
                rec.display_name = f"[{rec.code}] {rec.period}"
            else:
                rec.display_name = rec.code or rec.period or ""

    @api.model
    def _cron_update_payment_states(self):
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=7)
        # Quá hạn
        overdue = self.search([
            ("payment_state", "in", ("pending", "not_due", "due_soon")),
            ("date_due", "!=", False),
            ("date_due", "<", today),
        ])
        overdue.write({"payment_state": "overdue"})
        for rec in overdue:
            summary = f"Thanh toán quá hạn: {rec.display_name}"
            if not self.env["mail.activity"].search_count([
                ("res_model", "=", self._name),
                ("res_id", "=", rec.id),
                ("summary", "=", summary),
            ]):
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=summary,
                    note=f"<p>Cửa hàng: {rec.store_id.name}<br/>Hạn: {rec.date_due}<br/>Số tiền: {rec.amount}</p>",
                    user_id=rec.create_uid.id or self.env.uid,
                )
        # Sắp đến hạn
        due_soon = self.search([
            ("payment_state", "in", ("pending", "not_due")),
            ("date_due", "!=", False),
            ("date_due", ">=", today),
            ("date_due", "<=", soon),
        ])
        due_soon.write({"payment_state": "due_soon"})
        # Chưa đến hạn
        not_due = self.search([
            ("payment_state", "in", ("pending", "due_soon")),
            ("date_due", "!=", False),
            ("date_due", ">", soon),
        ])
        not_due.write({"payment_state": "not_due"})
        return True
