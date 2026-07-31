# -*- coding: utf-8 -*-

from odoo import api, fields, models


class EamModel(models.Model):
    _name = "eam.model"
    _description = "Danh mục tài sản (Model)"
    _order = "category_id, brand_id, name, id"
    _check_company_auto = True

    code = fields.Char(
        string="Mã",
        required=True,
        copy=False,
        index=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("eam.model") or "MDL",
    )
    name = fields.Char(
        string="Model",
        required=True,
        index=True,
        help="Tên / số model, ví dụ FTKB25, Latitude 5520.",
    )
    category_id = fields.Many2one(
        "maintenance.equipment.category",
        string="Nhóm tài sản",
        required=True,
        index=True,
        ondelete="restrict",
    )
    brand_id = fields.Many2one(
        "eam.brand",
        string="Thương hiệu",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)
    specification = fields.Text(string="Thông số kỹ thuật")
    default_warranty_month = fields.Integer(string="Bảo hành mặc định (tháng)", default=12)
    default_cost = fields.Monetary(string="Giá tham chiếu", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self.env.company.currency_id,
    )
    uom_note = fields.Char(string="Đơn vị / Ghi chú")
    image = fields.Image(string="Ảnh", max_width=1024, max_height=1024)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        default=lambda self: self.env.company,
        index=True,
    )
    equipment_ids = fields.One2many(
        "maintenance.equipment",
        "eam_model_id",
        string="Tài sản",
    )
    equipment_count = fields.Integer(compute="_compute_equipment_count", string="Số tài sản")

    _code_uniq = models.Constraint(
        "unique(code)",
        "Mã model phải duy nhất.",
    )
    _category_brand_name_uniq = models.Constraint(
        "unique(category_id, brand_id, name)",
        "Model đã tồn tại trong cùng nhóm và thương hiệu.",
    )

    @api.depends("category_id.name", "brand_id.name", "name")
    def _compute_display_name(self):
        for record in self:
            parts = [
                record.category_id.name,
                " ".join(p for p in [record.brand_id.name, record.name] if p).strip(),
            ]
            record.display_name = " / ".join(p for p in parts if p) or record.name or ""

    @api.depends("equipment_ids")
    def _compute_equipment_count(self):
        for record in self:
            record.equipment_count = len(record.equipment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("code") or vals.get("code") == "MDL":
                vals["code"] = sequence.next_by_code("eam.model") or vals.get("code") or "MDL"
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

    def action_open_equipment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tài sản",
            "res_model": "maintenance.equipment",
            "view_mode": "list,form,kanban",
            "domain": [("eam_model_id", "=", self.id)],
            "context": {
                "default_eam_model_id": self.id,
                "default_category_id": self.category_id.id,
            },
        }
