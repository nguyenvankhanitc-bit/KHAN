# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PhanHeStore(models.Model):
    _name = "phan.he.store"
    _description = "Cửa hàng"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code, name"
    _rec_names_search = ["code", "name"]

    code = fields.Char(string="Mã cửa hàng", required=True, tracking=True, copy=False)
    name = fields.Char(string="Tên cửa hàng", required=True, tracking=True)
    mien_id = fields.Many2one(
        "phan.he.mien",
        string="Miền",
        tracking=True,
        ondelete="restrict",
        index=True,
    )
    area_id = fields.Many2one(
        "phan.he.area",
        string="Khu vực",
        tracking=True,
        ondelete="restrict",
        index=True,
        domain="[('mien_id', '=', mien_id)]",
    )
    # Giữ selection cũ để tương thích / hiển thị nhanh
    mien = fields.Selection(
        selection=[
            ("Bắc", "Miền Bắc"),
            ("Nam", "Miền Nam"),
            ("ĐTT", "Miền ĐTT"),
            ("VP", "Văn phòng"),
        ],
        string="Miền (cũ)",
        compute="_compute_mien_code",
        store=True,
        readonly=True,
    )
    address = fields.Text(string="Địa chỉ", tracking=True)
    responsible_id = fields.Many2one(
        "hr.employee",
        string="Người phụ trách",
        tracking=True,
        ondelete="set null",
    )
    state = fields.Selection(
        selection=[
            ("active", "Đang hoạt động"),
            ("inactive", "Ngừng hoạt động"),
        ],
        string="Trạng thái hoạt động",
        default="active",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    service_ids = fields.One2many("phan.he.service", "store_id", string="Hợp đồng")
    service_count = fields.Integer(compute="_compute_service_count")
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã cửa hàng phải duy nhất trong cùng công ty.",
    )

    @api.depends("mien_id", "mien_id.code")
    def _compute_mien_code(self):
        code_map = {"BAC": "Bắc", "NAM": "Nam", "DTT": "ĐTT", "VP": "VP"}
        for rec in self:
            raw = (rec.mien_id.code or "").upper()
            rec.mien = code_map.get(raw, False)

    @api.onchange("mien_id")
    def _onchange_mien_id(self):
        if self.area_id and self.area_id.mien_id != self.mien_id:
            self.area_id = False

    @api.onchange("area_id")
    def _onchange_area_id(self):
        if self.area_id:
            self.mien_id = self.area_id.mien_id

    @api.depends("service_ids")
    def _compute_service_count(self):
        for rec in self:
            rec.service_count = len(rec.service_ids)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or rec.code or ""

    def action_open_services(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Hợp đồng dịch vụ",
            "res_model": "phan.he.service",
            "view_mode": "list,form",
            "domain": [("store_id", "=", self.id)],
            "context": {"default_store_id": self.id},
        }
