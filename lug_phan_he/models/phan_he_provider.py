# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PhanHeProvider(models.Model):
    _name = "phan.he.provider"
    _description = "Nhà cung cấp"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"
    _rec_names_search = ["name"]

    name = fields.Char(string="Nhà cung cấp", required=True, tracking=True)
    phone = fields.Char(string="Điện thoại")
    email = fields.Char(string="Email")
    website = fields.Char(string="Website")
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    bank_account_ids = fields.One2many(
        "phan.he.bank.account",
        "provider_id",
        string="Tài khoản ngân hàng",
    )
    bank_account_count = fields.Integer(compute="_compute_bank_account_count")
    # Giữ field cũ để tương thích dữ liệu demo/cũ
    account_name = fields.Char(string="Tên tài khoản (mặc định)")
    account_number = fields.Char(string="Số tài khoản (mặc định)")
    bank_name = fields.Char(string="Ngân hàng (mặc định)")
    bank_branch = fields.Char(string="Chi nhánh (mặc định)")
    transfer_content_template = fields.Char(string="Nội dung CK mẫu")
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")
    service_ids = fields.One2many("phan.he.service", "provider_id", string="Hợp đồng")

    def _compute_bank_account_count(self):
        for rec in self:
            rec.bank_account_count = len(rec.bank_account_ids)

    def action_open_bank_accounts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tài khoản ngân hàng",
            "res_model": "phan.he.bank.account",
            "view_mode": "list,form",
            "domain": [("provider_id", "=", self.id)],
            "context": {"default_provider_id": self.id},
        }


class PhanHeBankAccount(models.Model):
    _name = "phan.he.bank.account"
    _description = "Tài khoản ngân hàng nhận"
    _order = "provider_id, name"
    _rec_names_search = ["name", "account_number", "bank_name"]

    name = fields.Char(string="Tên hiển thị", compute="_compute_name", store=True)
    provider_id = fields.Many2one(
        "phan.he.provider",
        string="Nhà cung cấp",
        required=True,
        ondelete="cascade",
        index=True,
    )
    account_name = fields.Char(string="Tên tài khoản", required=True)
    account_number = fields.Char(string="Số tài khoản", required=True)
    bank_name = fields.Char(string="Ngân hàng", required=True)
    bank_branch = fields.Char(string="Chi nhánh")
    transfer_content_template = fields.Char(string="Nội dung chuyển khoản mẫu")
    is_default = fields.Boolean(string="Mặc định")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        related="provider_id.company_id",
        store=True,
        readonly=True,
    )
    note = fields.Text(string="Ghi chú")

    @api.depends("provider_id", "bank_name", "account_number")
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.provider_id:
                parts.append(rec.provider_id.name)
            if rec.bank_name:
                parts.append(rec.bank_name)
            if rec.account_number:
                parts.append(rec.account_number)
            rec.name = " — ".join(parts) if parts else "Tài khoản"
