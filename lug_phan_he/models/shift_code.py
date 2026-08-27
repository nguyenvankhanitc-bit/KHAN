# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LinkqShiftCode(models.Model):
    _name = "linkq.shift.code"
    _description = "Ký hiệu công"
    _order = "sequence, code"
    _rec_name = "code"
    _rec_names_search = ["code", "name"]

    sequence = fields.Integer(string="STT", default=10)
    code = fields.Char(string="Mã ca", required=True, index=True)
    name = fields.Char(string="Tên ca")
    shift_group = fields.Selection(
        [
            ("FULL", "FULL"),
            ("GAY", "GÃY"),
            ("GAY_SANG", "GÃY SÁNG"),
            ("GAY_CHIEU", "GÃY CHIỀU"),
            ("SANG", "SÁNG"),
            ("CHIEU", "CHIỀU"),
            ("OFF", "OFF"),
        ],
        string="Nhóm ca",
        required=True,
        default="FULL",
        index=True,
    )
    time_in = fields.Float(string="Giờ vào")
    time_out = fields.Float(string="Giờ về")
    total_hours = fields.Float(
        string="Tổng giờ",
        digits=(16, 2),
        compute="_compute_total_hours",
        store=True,
    )
    note = fields.Text(string="Ghi chú")

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Mã ca phải là duy nhất."),
    ]

    @api.depends("time_in", "time_out", "shift_group")
    def _compute_total_hours(self):
        for rec in self:
            if rec.shift_group == "OFF":
                rec.total_hours = 0.0
                continue
            delta = (rec.time_out or 0.0) - (rec.time_in or 0.0)
            rec.total_hours = delta if delta >= 0 else delta + 24.0

    @api.depends("code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.code or ""

    def name_get(self):
        return [(rec.id, rec.code or "") for rec in self]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = (vals["code"] or "").strip().split()[0].split("(")[0].upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = (vals["code"] or "").strip().split()[0].split("(")[0].upper()
        return super().write(vals)
