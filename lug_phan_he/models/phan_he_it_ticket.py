# -*- coding: utf-8 -*-

from odoo import fields, models


class PhanHeItTicket(models.Model):
    _name = "phan.he.it.ticket"
    _description = "Bảo trì / hỗ trợ / sự cố tài sản IT"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_reported desc, id desc"

    code = fields.Char(
        string="Mã phiếu",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("phan.he.it.ticket") or "New",
        tracking=True,
    )
    asset_id = fields.Many2one(
        "phan.he.it.asset",
        string="Tài sản",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    ticket_type = fields.Selection(
        [
            ("maintenance", "Bảo trì"),
            ("support", "Yêu cầu hỗ trợ"),
            ("incident", "Sự cố"),
        ],
        string="Loại công việc",
        required=True,
        default="maintenance",
        tracking=True,
    )
    name = fields.Char(string="Tiêu đề", required=True, tracking=True)
    description = fields.Text(string="Mô tả sự cố / yêu cầu")
    priority = fields.Selection(
        [
            ("0", "Thấp"),
            ("1", "Trung bình"),
            ("2", "Cao"),
            ("3", "Khẩn cấp"),
        ],
        string="Mức độ ưu tiên",
        default="1",
        tracking=True,
    )
    date_reported = fields.Datetime(
        string="Ngày phát sinh",
        default=fields.Datetime.now,
        tracking=True,
    )
    date_start = fields.Datetime(string="Ngày bắt đầu xử lý")
    date_done = fields.Datetime(string="Ngày hoàn thành")
    responsible_id = fields.Many2one("hr.employee", string="Người phụ trách", tracking=True)
    provider_id = fields.Many2one("phan.he.provider", string="Nhà cung cấp hỗ trợ")
    cost_amount = fields.Monetary(string="Chi phí", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref("base.VND", raise_if_not_found=False)
        or self.env.company.currency_id,
    )
    linked_cost_id = fields.Many2one(
        "phan.he.it.cost",
        string="Khoản chi phí liên quan",
        help="Tránh ghi nhận chi phí hai lần — gắn đúng chứng từ.",
    )
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("open", "Đang mở"),
            ("progress", "Đang xử lý"),
            ("done", "Hoàn thành"),
            ("cancel", "Hủy"),
        ],
        string="Trạng thái",
        default="open",
        tracking=True,
    )
    root_cause = fields.Text(string="Nguyên nhân")
    resolution = fields.Text(string="Phương án xử lý")
    note = fields.Text(string="Ghi chú")
    company_id = fields.Many2one(related="asset_id.company_id", store=True)
    active = fields.Boolean(default=True)
