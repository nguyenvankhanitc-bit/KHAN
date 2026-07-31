# -*- coding: utf-8 -*-

from odoo import fields, models


class PhanHeDocument(models.Model):
    _name = "phan.he.document"
    _description = "Hồ sơ / Chứng từ hợp đồng"
    _order = "date desc, id desc"

    name = fields.Char(string="Tên chứng từ", required=True)
    service_id = fields.Many2one(
        "phan.he.service", string="Hợp đồng", required=True,
        ondelete="cascade", index=True,
    )
    store_id = fields.Many2one(related="service_id.store_id", store=True, string="Cửa hàng")
    date = fields.Date(string="Ngày", default=fields.Date.context_today)
    doc_type = fields.Selection(
        selection=[
            ("contract", "Hồ sơ hợp đồng"),
            ("invoice", "Hóa đơn"),
            ("appendix", "Phụ lục"),
            ("other", "Khác"),
        ],
        string="Loại",
        default="contract",
    )
    file = fields.Binary(string="File", attachment=True, required=True)
    filename = fields.Char(string="Tên file")
    note = fields.Char(string="Ghi chú")
    company_id = fields.Many2one(related="service_id.company_id", store=True, readonly=True)
