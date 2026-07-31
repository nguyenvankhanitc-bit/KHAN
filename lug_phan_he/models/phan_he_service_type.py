# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PhanHeServiceType(models.Model):
    _name = "phan.he.service.type"
    _description = "Loại dịch vụ"
    _order = "sequence, name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(string="Tên loại dịch vụ", required=True)
    code = fields.Char(string="Mã", required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Màu")
    active = fields.Boolean(default=True)
    description = fields.Text(string="Mô tả")
    service_count = fields.Integer(compute="_compute_service_count")

    _code_uniq = models.Constraint("unique(code)", "Mã loại dịch vụ phải duy nhất.")

    def _compute_service_count(self):
        Service = self.env["phan.he.service"]
        for rec in self:
            rec.service_count = Service.search_count([("service_type_id", "=", rec.id)])

    @api.depends("name", "code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or rec.code or ""
