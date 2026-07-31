# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PhanHeInvoice(models.Model):
    _name = "phan.he.invoice"
    _description = "Hóa đơn dịch vụ"
    _inherit = ["mail.thread", "mail.activity.mixin", "phan.he.currency.mixin"]
    _order = "invoice_date desc, id desc"
    _rec_names_search = ["name", "invoice_number"]

    name = fields.Char(string="Mã hóa đơn nội bộ", required=True, copy=False, default="New")
    invoice_number = fields.Char(string="Số hóa đơn", tracking=True, required=True)
    payment_id = fields.Many2one(
        "phan.he.payment",
        string="Thanh toán",
        ondelete="set null",
        index=True,
    )
    service_id = fields.Many2one(
        "phan.he.service",
        string="Hợp đồng",
        required=True,
        tracking=True,
        ondelete="restrict",
        index=True,
    )
    store_id = fields.Many2one(related="service_id.store_id", store=True, string="Cửa hàng")
    provider_id = fields.Many2one(related="service_id.provider_id", store=True, string="Nhà cung cấp")
    invoice_date = fields.Date(string="Ngày hóa đơn", tracking=True)
    amount = fields.Monetary(string="Số tiền", currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self._default_currency_vnd(),
    )
    file = fields.Binary(string="File hóa đơn", attachment=True)
    filename = fields.Char(string="Tên file")
    reconcile_state = fields.Selection(
        selection=[
            ("draft", "Nháp"),
            ("matched", "Đã đối soát"),
            ("mismatch", "Lệch"),
        ],
        string="Đối soát",
        default="draft",
        tracking=True,
    )
    reconcile_note = fields.Text(string="Ghi chú đối soát")
    company_id = fields.Many2one(related="service_id.company_id", store=True, readonly=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("phan.he.invoice") or "New"
            if vals.get("payment_id") and not vals.get("service_id"):
                payment = self.env["phan.he.payment"].browse(vals["payment_id"])
                vals["service_id"] = payment.service_id.id
                if not vals.get("amount"):
                    vals["amount"] = payment.amount
        return super().create(vals_list)

    @api.onchange("payment_id")
    def _onchange_payment_id(self):
        if self.payment_id:
            self.service_id = self.payment_id.service_id
            self.amount = self.payment_id.amount
            if self.payment_id.invoice_number and not self.invoice_number:
                self.invoice_number = self.payment_id.invoice_number
