# -*- coding: utf-8 -*-

from odoo import api, fields, models


class EamBrand(models.Model):
    _name = "eam.brand"
    _description = "Thương hiệu tài sản"
    _order = "name, id"
    _rec_name = "name"

    code = fields.Char(
        string="Mã",
        required=True,
        copy=False,
        index=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("eam.brand") or "BRD",
    )
    name = fields.Char(string="Tên thương hiệu", required=True, translate=True, index=True)
    country_id = fields.Many2one("res.country", string="Xuất xứ")
    partner_id = fields.Many2one("res.partner", string="Hãng / Đại diện")
    logo = fields.Image(string="Logo", max_width=256, max_height=256)
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        default=lambda self: self.env.company,
    )
    model_ids = fields.One2many("eam.model", "brand_id", string="Model")
    model_count = fields.Integer(compute="_compute_model_count", string="Số model")

    _code_uniq = models.Constraint(
        "unique(code)",
        "Mã thương hiệu phải duy nhất.",
    )
    _name_uniq = models.Constraint(
        "unique(name)",
        "Tên thương hiệu phải duy nhất.",
    )

    @api.depends("model_ids")
    def _compute_model_count(self):
        for brand in self:
            brand.model_count = len(brand.model_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("code") or vals.get("code") == "BRD":
                vals["code"] = sequence.next_by_code("eam.brand") or vals.get("code") or "BRD"
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
            if vals.get("name"):
                vals["name"] = vals["name"].strip()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals = dict(vals, code=vals["code"].strip().upper())
        if vals.get("name"):
            vals = dict(vals, name=vals["name"].strip())
        return super().write(vals)

    def action_open_models(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Model",
            "res_model": "eam.model",
            "view_mode": "list,form",
            "domain": [("brand_id", "=", self.id)],
            "context": {"default_brand_id": self.id},
        }
