# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class EamInventoryProduct(models.Model):
    """Vật tư / hàng hóa quản lý THEO SỐ LƯỢNG (khác Asset theo mã riêng)."""

    _name = "eam.inventory.product"
    _description = "Vật tư kho (theo số lượng)"
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(string="Tên vật tư", required=True, translate=True)
    code = fields.Char(string="Mã vật tư", required=True, index=True, copy=False)
    barcode = fields.Char(string="Barcode", index=True, copy=False)
    uom_name = fields.Char(string="Đơn vị", default="Cái", required=True)
    warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    category_note = fields.Char(string="Nhóm / loại")
    qty_on_hand = fields.Float(
        string="Tồn kho",
        digits=(16, 2),
        compute="_compute_qty_on_hand",
        store=True,
    )
    qty_min = fields.Float(string="Tồn tối thiểu", digits=(16, 2), default=0.0)
    standard_cost = fields.Monetary(string="Đơn giá", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Ghi chú")
    move_ids = fields.One2many("eam.inventory.move", "product_id", string="Phiếu kho")
    is_below_min = fields.Boolean(compute="_compute_is_below_min", store=True)

    _code_wh_company_uniq = models.Constraint(
        "unique(code, warehouse_id, company_id)",
        "Mã vật tư phải duy nhất trong cùng kho.",
    )

    @api.depends("move_ids.state", "move_ids.qty", "move_ids.move_type", "move_ids.product_id")
    def _compute_qty_on_hand(self):
        for product in self:
            qty = 0.0
            for move in product.move_ids.filtered(lambda m: m.state == "done"):
                if move.move_type == "in":
                    qty += move.qty
                elif move.move_type in ("out", "issue"):
                    qty -= move.qty
                elif move.move_type == "transfer":
                    # Phiếu transfer gắn product kho nguồn → trừ tồn nguồn.
                    # Kho đích nhận phiếu in riêng.
                    qty -= move.qty
                elif move.move_type == "adjust":
                    qty += move.qty  # can be negative
            product.qty_on_hand = qty

    @api.depends("qty_on_hand", "qty_min")
    def _compute_is_below_min(self):
        for product in self:
            product.is_below_min = product.qty_min > 0 and product.qty_on_hand < product.qty_min

    def action_open_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Phiếu vật tư"),
            "res_model": "eam.inventory.move",
            "view_mode": "list,form",
            "domain": [("product_id", "=", self.id)],
            "context": {
                "default_product_id": self.id,
                "default_warehouse_id": self.warehouse_id.id,
            },
        }


class EamInventoryMove(models.Model):
    """Phiếu nhập / xuất / điều chuyển / điều chỉnh số lượng vật tư."""

    _name = "eam.inventory.move"
    _description = "Phiếu kho vật tư (số lượng)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Số phiếu",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env._("Mới"),
    )
    move_type = fields.Selection(
        [
            ("in", "Nhập kho"),
            ("out", "Xuất kho"),
            ("issue", "Xuất cấp phát"),
            ("transfer", "Điều chuyển"),
            ("adjust", "Điều chỉnh"),
        ],
        string="Loại",
        required=True,
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [("draft", "Nháp"), ("done", "Hoàn thành"), ("cancel", "Hủy")],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    product_id = fields.Many2one(
        "eam.inventory.product",
        string="Vật tư",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho nguồn",
        required=True,
        index=True,
        check_company=True,
    )
    dest_warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho đích",
        check_company=True,
    )
    qty = fields.Float(string="Số lượng", digits=(16, 2), required=True, default=1.0)
    uom_name = fields.Char(related="product_id.uom_name", string="Đơn vị")
    partner_id = fields.Many2one("res.partner", string="Đối tác")
    employee_id = fields.Many2one("hr.employee", string="Người nhận")
    department_id = fields.Many2one("hr.department", string="Phòng ban")
    reason = fields.Char(string="Lý do / Ghi chú")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for move in self:
            if move.product_id:
                move.warehouse_id = move.product_id.warehouse_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", self.env._("Mới")) in (self.env._("Mới"), "Mới", "/", False):
                vals["name"] = self.env["ir.sequence"].next_by_code("eam.inventory.move") or self.env._(
                    "Mới"
                )
        return super().create(vals_list)

    def unlink(self):
        if any(m.state == "done" for m in self):
            raise UserError(self.env._("Không xóa phiếu vật tư đã hoàn thành."))
        return super().unlink()

    def action_cancel(self):
        for move in self:
            if move.state == "done":
                raise UserError(self.env._("Không hủy phiếu đã hoàn thành."))
            move.state = "cancel"
        return True

    def action_draft(self):
        self.filtered(lambda m: m.state == "cancel").write({"state": "draft"})
        return True

    def action_confirm(self):
        for move in self:
            move._confirm()
        return True

    def _confirm(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(self.env._("Chỉ xác nhận phiếu nháp."))
        if self.qty == 0:
            raise UserError(self.env._("Số lượng phải khác 0."))
        if self.move_type == "transfer" and not self.dest_warehouse_id:
            raise UserError(self.env._("Điều chuyển cần chọn kho đích."))
        if self.move_type == "transfer" and self.dest_warehouse_id == self.warehouse_id:
            raise UserError(self.env._("Kho đích phải khác kho nguồn."))
        if self.move_type in ("out", "issue", "transfer") and self.qty < 0:
            raise ValidationError(self.env._("Số lượng xuất phải > 0."))

        # Kiểm tra tồn khi xuất
        if self.move_type in ("out", "issue", "transfer"):
            available = self.product_id.qty_on_hand
            if self.qty > available:
                raise UserError(
                    self.env._(
                        "Không đủ tồn kho vật tư %(name)s. Tồn: %(qty)s, cần: %(need)s."
                    )
                    % {
                        "name": self.product_id.display_name,
                        "qty": available,
                        "need": self.qty,
                    }
                )

        # Điều chuyển: đảm bảo có bản ghi product ở kho đích
        if self.move_type == "transfer":
            dest_product = self.env["eam.inventory.product"].search(
                [
                    ("code", "=", self.product_id.code),
                    ("warehouse_id", "=", self.dest_warehouse_id.id),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
            if not dest_product:
                dest_product = self.product_id.copy(
                    {
                        "warehouse_id": self.dest_warehouse_id.id,
                        "name": self.product_id.name,
                        "code": self.product_id.code,
                    }
                )
            # Tạo phiếu nhập tương ứng ở kho đích (đã done) để qty cộng đúng
            self.env["eam.inventory.move"].create(
                {
                    "name": "%s-IN" % self.name,
                    "move_type": "in",
                    "state": "done",
                    "date": self.date,
                    "product_id": dest_product.id,
                    "warehouse_id": self.dest_warehouse_id.id,
                    "qty": self.qty,
                    "reason": self.env._("Nhập từ điều chuyển %s") % self.name,
                    "company_id": self.company_id.id,
                }
            )

        self.state = "done"
        # Force recompute qty (invalidate cache rồi tính lại)
        products = self.product_id
        if self.move_type == "transfer" and self.dest_warehouse_id:
            dest = self.env["eam.inventory.product"].search(
                [
                    ("code", "=", self.product_id.code),
                    ("warehouse_id", "=", self.dest_warehouse_id.id),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
            if dest:
                products |= dest
        products.invalidate_recordset(["qty_on_hand"])
        products._compute_qty_on_hand()
