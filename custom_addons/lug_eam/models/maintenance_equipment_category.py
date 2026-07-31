# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MaintenanceEquipmentCategory(models.Model):
    _inherit = "maintenance.equipment.category"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "complete_name, id"

    code = fields.Char(
        string="Mã nhóm",
        copy=False,
        index=True,
        help="Mã danh mục, ví dụ CAT_AC, GRP_HVAC.",
    )
    code_token = fields.Char(
        string="Mã ngắn (trong mã TS)",
        help="Dùng sinh mã tài sản, ví dụ IT → TS-IT-2026-00001. "
             "Để trống = lấy từ mã nhóm (bỏ tiền tố GRP_/CAT_).",
    )
    parent_id = fields.Many2one(
        "maintenance.equipment.category",
        string="Nhóm cha",
        index=True,
        ondelete="cascade",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        "maintenance.equipment.category",
        "parent_id",
        string="Nhóm con",
    )
    complete_name = fields.Char(
        string="Tên đầy đủ",
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )
    require_qr = fields.Boolean(string="Bắt buộc QR", default=True)
    require_warranty = fields.Boolean(string="Bắt buộc bảo hành", default=False)
    maintenance_cycle_month = fields.Integer(
        string="Chu kỳ bảo trì (tháng)",
        default=0,
        help="0 = không tự sinh lịch phòng ngừa.",
    )
    inspection_cycle_month = fields.Integer(
        string="Chu kỳ kiểm kê / kiểm tra (tháng)",
        default=0,
    )
    asset_sequence_id = fields.Many2one(
        "ir.sequence",
        string="Sequence mã tài sản",
        help="Để trống = dùng sequence chung AS#####.",
    )
    eam_model_ids = fields.One2many("eam.model", "category_id", string="Model")
    eam_model_count = fields.Integer(compute="_compute_eam_model_count", string="Số model")

    _code_uniq = models.Constraint(
        "unique(code)",
        "Mã nhóm tài sản phải duy nhất.",
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = "%s / %s" % (
                    category.parent_id.complete_name,
                    category.name or "",
                )
            else:
                category.complete_name = category.name or ""

    @api.depends("eam_model_ids")
    def _compute_eam_model_count(self):
        for category in self:
            category.eam_model_count = len(category.eam_model_ids)

    @api.constrains("parent_id")
    def _check_category_recursion(self):
        if self._has_cycle():
            raise ValidationError("Không được tạo vòng lặp trong cây nhóm tài sản.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals = dict(vals, code=vals["code"].strip().upper())
        return super().write(vals)

    def action_open_eam_models(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Model",
            "res_model": "eam.model",
            "view_mode": "list,form",
            "domain": [("category_id", "=", self.id)],
            "context": {"default_category_id": self.id},
        }
