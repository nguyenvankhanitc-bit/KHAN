# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EamWarehouse(models.Model):
    _name = "eam.warehouse"
    _description = "Kho tài sản"
    _order = "sequence, name, id"

    name = fields.Char(string="Tên kho", required=True, translate=True)
    code = fields.Char(string="Mã kho", required=True, index=True)
    sequence = fields.Integer(default=10)
    is_central = fields.Boolean(
        string="Kho trung tâm",
        help="Đánh dấu kho trung tâm của công ty.",
    )
    address = fields.Char(string="Địa chỉ")
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    location_ids = fields.One2many("eam.location", "warehouse_id", string="Vị trí")
    location_count = fields.Integer(compute="_compute_counts")
    asset_count = fields.Integer(compute="_compute_counts", string="TS trong kho")
    inventory_qty = fields.Float(compute="_compute_counts", string="SL vật tư")

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã kho phải duy nhất trong cùng công ty.",
    )

    @api.depends("name", "code")
    def _compute_display_name(self):
        for wh in self:
            if wh.code:
                wh.display_name = "%s (%s)" % (wh.name or "", wh.code)
            else:
                wh.display_name = wh.name or ""

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = list(args or [])
        domain = args
        if name:
            domain = ["|", ("code", operator, name), ("name", operator, name)] + args
        records = self.search(domain, limit=limit)
        return [(rec.id, rec.display_name) for rec in records]

    @api.depends("location_ids")
    def _compute_counts(self):
        Equipment = self.env["maintenance.equipment"]
        Product = self.env["eam.inventory.product"]
        for wh in self:
            wh.location_count = len(wh.location_ids)
            wh.asset_count = Equipment.search_count(
                [("warehouse_id", "=", wh.id), ("eam_state", "=", "in_stock")]
            )
            products = Product.search([("warehouse_id", "=", wh.id)])
            wh.inventory_qty = sum(products.mapped("qty_on_hand"))

    def action_open_locations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Vị trí kho"),
            "res_model": "eam.location",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {
                "default_warehouse_id": self.id,
                "default_loc_kind": "warehouse",
            },
        }

    def action_open_assets_in_stock(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Tài sản trong kho"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id), ("eam_state", "=", "in_stock")],
            "context": {"default_warehouse_id": self.id, "default_eam_state": "in_stock"},
        }

    def action_open_inventory_products(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Vật tư trong kho"),
            "res_model": "eam.inventory.product",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {"default_warehouse_id": self.id},
        }


class EamLocation(models.Model):
    _name = "eam.location"
    _description = "Vị trí kho / nơi sử dụng"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "complete_name, id"

    name = fields.Char(string="Tên vị trí", required=True)
    code = fields.Char(string="Mã vị trí", index=True)
    parent_id = fields.Many2one(
        "eam.location",
        string="Vị trí cha",
        index=True,
        ondelete="cascade",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("eam.location", "parent_id", string="Vị trí con")
    complete_name = fields.Char(
        string="Tên đầy đủ",
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )
    loc_kind = fields.Selection(
        [
            # Nhóm kho
            ("warehouse", "Kho"),
            ("zone", "Khu"),
            ("rack", "Kệ"),
            ("shelf", "Tầng kệ"),
            ("bin", "Ô"),
            # Nhóm sử dụng
            ("site", "Cửa hàng / Chi nhánh"),
            ("building", "Tòa nhà"),
            ("floor", "Tầng"),
            ("room", "Phòng"),
            ("machine", "Vị trí máy"),
        ],
        string="Loại vị trí",
        required=True,
        default="bin",
        index=True,
    )
    loc_group = fields.Selection(
        [
            ("stock", "Kho"),
            ("usage", "Nơi sử dụng"),
        ],
        string="Nhóm",
        compute="_compute_loc_group",
        store=True,
    )
    warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    department_id = fields.Many2one("hr.department", string="Phòng ban", check_company=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")
    asset_ids = fields.One2many("maintenance.equipment", "current_location_id", string="Tài sản")
    asset_count = fields.Integer(compute="_compute_asset_count")

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã vị trí phải duy nhất trong cùng công ty.",
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for loc in self:
            if loc.parent_id:
                loc.complete_name = "%s / %s" % (loc.parent_id.complete_name, loc.name or "")
            else:
                loc.complete_name = loc.name or ""

    @api.depends("loc_kind")
    def _compute_loc_group(self):
        stock_kinds = {"warehouse", "zone", "rack", "shelf", "bin"}
        for loc in self:
            loc.loc_group = "stock" if loc.loc_kind in stock_kinds else "usage"

    @api.depends("asset_ids")
    def _compute_asset_count(self):
        for loc in self:
            loc.asset_count = len(loc.asset_ids)

    @api.constrains("parent_id")
    def _check_location_recursion(self):
        if self._has_cycle():
            raise ValidationError(self.env._("Không được tạo vòng lặp cây vị trí."))

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for loc in self:
            if loc.warehouse_id and loc.loc_kind in ("warehouse", "zone", "rack", "shelf", "bin"):
                if not loc.parent_id and loc.loc_kind != "warehouse":
                    pass

    def action_open_assets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Tài sản tại vị trí"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("current_location_id", "child_of", self.id)],
            "context": {"default_current_location_id": self.id},
        }
