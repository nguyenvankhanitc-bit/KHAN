# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .eam_amount_vn import amount_to_vietnamese

TXN_TYPES = [
    ("in", "Nhập mua / Nhập kho"),
    ("out", "Xuất kho"),
    ("transfer", "Điều chuyển"),
    ("recall", "Thu hồi"),
    ("disposal", "Thanh lý"),
]

TXN_STATES = [
    ("draft", "Nháp"),
    ("done", "Hoàn thành"),
    ("cancel", "Hủy"),
]

EAM_STATE_TRANSITIONS = {
    "draft": {"in_stock"},
    "in_stock": {"in_use", "maintenance", "broken", "disposed"},
    "in_use": {"in_stock", "maintenance", "broken", "disposed"},
    "maintenance": {"in_stock", "in_use", "broken", "disposed"},
    "broken": {"in_stock", "maintenance", "disposed"},
    "disposed": set(),
}

SEQ_BY_TYPE = {
    "in": "eam.txn.in",
    "out": "eam.txn.out",
    "transfer": "eam.txn.transfer",
    "recall": "eam.txn.recall",
    "disposal": "eam.txn.disposal",
}


class EamTransaction(models.Model):
    _name = "eam.transaction"
    _description = "Phiếu nghiệp vụ tài sản"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Số phiếu",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env._("Mới"),
        tracking=True,
    )
    txn_type = fields.Selection(
        TXN_TYPES,
        string="Loại phiếu",
        required=True,
        index=True,
        tracking=True,
    )
    doc_type_code = fields.Char(
        string="Mã CT",
        default="NM",
        help="Mã chứng từ in trên phiếu (mẫu NM).",
    )
    state = fields.Selection(
        TXN_STATES,
        string="Trạng thái",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    date = fields.Date(
        string="Ngày",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Người tạo",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many("eam.transaction.line", "header_id", string="Dòng hàng")
    line_count = fields.Integer(compute="_compute_line_count", string="Số dòng")

    partner_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp (liên kết)",
        tracking=True,
        check_company=True,
    )
    partner_name = fields.Char(
        string="Nhà cung cấp",
        tracking=True,
        help="Nhập tay tên nhà cung cấp.",
    )
    eam_model_id = fields.Many2one(
        "eam.model",
        string="Danh mục (Model)",
        ondelete="restrict",
        check_company=True,
        tracking=True,
        help="Áp dụng cho các dòng hàng khi xác nhận (nếu dòng không chọn model riêng).",
    )
    deliverer_name = fields.Char(string="Họ tên người giao hàng", tracking=True)
    receiver_name = fields.Char(string="Họ tên người nhận hàng", tracking=True)
    receiver_phone = fields.Char(string="Điện thoại người nhận")
    content = fields.Text(string="Nội dung")
    contract_ref = fields.Char(string="Số hợp đồng", tracking=True)
    contract_date = fields.Date(string="Ngày hợp đồng")
    po_ref = fields.Char(string="Số PO / Đơn mua")
    invoice_ref = fields.Char(string="Số hóa đơn")
    funding_source = fields.Char(string="Nguồn vốn")
    warranty_month = fields.Integer(string="Bảo hành (tháng)", default=12)
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self._eam_default_vnd_currency(),
    )
    amount_total = fields.Monetary(
        string="Tổng giá trị",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    qty_total = fields.Float(
        string="Cộng SL",
        digits=(16, 2),
        compute="_compute_totals",
        store=True,
    )
    amount_goods = fields.Monetary(
        string="Cộng tiền hàng",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    tax_import = fields.Monetary(string="Thuế nhập khẩu", currency_field="currency_id", default=0.0)
    tax_vat = fields.Monetary(string="Thuế GTGT", currency_field="currency_id", default=0.0)
    amount_grand = fields.Monetary(
        string="Tổng tiền",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    amount_in_words = fields.Char(
        string="Tổng số tiền (bằng chữ)",
        compute="_compute_amount_in_words",
    )
    attached_docs = fields.Char(string="Số chứng từ gốc kèm theo")
    debit_account = fields.Char(string="Nợ (TK)")
    credit_account = fields.Char(string="Có (TK)")
    debit_amount = fields.Monetary(string="Nợ (số tiền)", currency_field="currency_id")
    credit_amount = fields.Monetary(string="Có (số tiền)", currency_field="currency_id")
    prepared_by_id = fields.Many2one(
        "res.users",
        string="Người lập phiếu",
        default=lambda self: self.env.user,
    )
    receiver_id = fields.Many2one("hr.employee", string="Người nhận hàng", check_company=True)
    warehouse_keeper_id = fields.Many2one("hr.employee", string="Thủ kho", check_company=True)
    controller_id = fields.Many2one("hr.employee", string="Người kiểm soát", check_company=True)

    warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho",
        index=True,
        check_company=True,
        tracking=True,
        help="Nhập mua: kho nhập. Xuất kho: kho xuất.",
    )
    dest_warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Nhập tại kho",
        index=True,
        check_company=True,
        tracking=True,
        help="Kho đích trên PHIẾU XUẤT KHO.",
    )
    src_location_id = fields.Many2one("eam.location", string="Vị trí nguồn", check_company=True)
    dest_location_id = fields.Many2one("eam.location", string="Vị trí đích", check_company=True)
    src_location_note = fields.Char(string="Vị trí nguồn (text)")
    dest_location_note = fields.Char(string="Vị trí đích (text)")
    department_id = fields.Many2one("hr.department", string="Phòng ban", check_company=True)
    owner_employee_id = fields.Many2one("hr.employee", string="Người nhận / giữ", check_company=True)
    reason = fields.Text(string="Lý do / Ghi chú")
    amount_recovery = fields.Monetary(
        string="Giá trị thu hồi",
        currency_field="currency_id",
        help="Dùng khi thanh lý.",
    )

    _name_uniq = models.Constraint(
        "unique(name)",
        "Số phiếu phải duy nhất.",
    )

    @api.model
    def _eam_default_vnd_currency(self):
        Currency = self.env["res.currency"].sudo()
        vnd = Currency.search([("name", "=", "VND")], limit=1)
        if not vnd:
            vnd = self.env.ref("base.VND", raise_if_not_found=False)
        if vnd:
            vals = {}
            if vnd.symbol != "VNĐ":
                vals["symbol"] = "VNĐ"
            if vnd.position != "after":
                vals["position"] = "after"
            if not vnd.active:
                vals["active"] = True
            if vals:
                vnd.write(vals)
            return vnd
        return self.env.company.currency_id

    def _eam_resolve_partner(self):
        """Ưu tiên partner_id; nếu chỉ có tên nhập tay thì tìm / tạo partner."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        name = (self.partner_name or "").strip()
        if not name:
            return self.env["res.partner"]
        Partner = self.env["res.partner"]
        partner = Partner.search([("name", "=ilike", name)], limit=1)
        if not partner:
            partner = Partner.create({"name": name})
        if not self.partner_id:
            self.partner_id = partner
        return partner

    @api.onchange("partner_id")
    def _onchange_partner_id_name(self):
        for txn in self:
            if txn.partner_id and not txn.partner_name:
                txn.partner_name = txn.partner_id.name

    @api.onchange("eam_model_id")
    def _onchange_header_eam_model_id(self):
        """Điền nhanh mặt hàng trống theo model trên phiếu."""
        for txn in self:
            model = txn.eam_model_id
            if not model:
                continue
            for line in txn.line_ids:
                if not line.product_name:
                    line.product_name = model.display_name or model.name
                if not line.product_code and model.code:
                    line.product_code = model.code
                if model.uom_note and (not line.uom_name or line.uom_name == "Cái"):
                    line.uom_name = model.uom_note
                if model.default_cost and not line.unit_cost:
                    line.unit_cost = model.default_cost
                if not line.eam_model_id:
                    line.eam_model_id = model

    @api.onchange("txn_type")
    def _onchange_txn_type_doc_code(self):
        mapping = {"in": "NM", "out": "PX", "transfer": "DC", "recall": "TH", "disposal": "TL"}
        for txn in self:
            if txn.txn_type:
                txn.doc_type_code = mapping.get(txn.txn_type, "NM")
            if txn.txn_type in ("in", "out", "transfer"):
                txn.currency_id = self._eam_default_vnd_currency()

    @api.onchange("owner_employee_id")
    def _onchange_owner_employee_receiver(self):
        for txn in self:
            emp = txn.owner_employee_id
            if not emp:
                continue
            if not txn.receiver_name:
                txn.receiver_name = emp.name
            if not txn.receiver_phone and emp.work_phone:
                txn.receiver_phone = emp.work_phone
            elif not txn.receiver_phone and emp.mobile_phone:
                txn.receiver_phone = emp.mobile_phone

    @api.onchange("dest_warehouse_id")
    def _onchange_dest_warehouse_id(self):
        for txn in self:
            if txn.dest_warehouse_id and not txn.dest_location_note:
                txn.dest_location_note = txn.dest_warehouse_id.name

    @api.onchange("dest_location_id")
    def _onchange_dest_location_id(self):
        for txn in self:
            if txn.dest_location_id:
                txn.dest_location_note = txn.dest_location_id.complete_name
                if txn.dest_location_id.warehouse_id:
                    txn.warehouse_id = txn.dest_location_id.warehouse_id

    @api.onchange("src_location_id")
    def _onchange_src_location_id(self):
        for txn in self:
            if txn.src_location_id:
                txn.src_location_note = txn.src_location_id.complete_name

    @api.onchange("amount_grand", "tax_import", "tax_vat", "line_ids")
    def _onchange_amount_grand_accounts(self):
        for txn in self:
            if txn.txn_type == "in" and txn.amount_grand:
                if not txn.debit_amount:
                    txn.debit_amount = txn.amount_grand
                if not txn.credit_amount:
                    txn.credit_amount = txn.amount_grand

    def _eam_dest_label(self):
        self.ensure_one()
        if self.dest_location_id:
            return self.dest_location_id.complete_name
        if self.dest_warehouse_id:
            return self.dest_warehouse_id.name
        if self.warehouse_id:
            return self.warehouse_id.name
        return self.dest_location_note

    @api.depends("line_ids")
    def _compute_line_count(self):
        for txn in self:
            txn.line_count = len(txn.line_ids)

    @api.depends(
        "line_ids.subtotal",
        "line_ids.qty_received",
        "line_ids.unit_cost",
        "tax_import",
        "tax_vat",
    )
    def _compute_totals(self):
        for txn in self:
            goods = sum(txn.line_ids.mapped("subtotal"))
            qty = sum(txn.line_ids.mapped("qty_received"))
            txn.amount_goods = goods
            txn.qty_total = qty
            txn.amount_total = goods
            txn.amount_grand = goods + (txn.tax_import or 0.0) + (txn.tax_vat or 0.0)

    @api.depends(
        "amount_grand",
        "line_ids.subtotal",
        "line_ids.unit_cost",
        "line_ids.qty_received",
        "tax_import",
        "tax_vat",
    )
    def _compute_amount_in_words(self):
        for txn in self:
            txn.amount_in_words = amount_to_vietnamese(txn.amount_grand)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("doc_type_code"):
                vals["doc_type_code"] = {
                    "in": "NM",
                    "out": "PX",
                    "transfer": "DC",
                    "recall": "TH",
                    "disposal": "TL",
                }.get(vals.get("txn_type"), "NM")
            if vals.get("name", self.env._("Mới")) in (self.env._("Mới"), "Mới", "/", False):
                seq_code = SEQ_BY_TYPE.get(vals.get("txn_type"), "eam.txn.in")
                vals["name"] = self.env["ir.sequence"].next_by_code(seq_code) or self.env._("Mới")
            if not vals.get("currency_id"):
                vals["currency_id"] = self._eam_default_vnd_currency().id
            if vals.get("partner_name") and not vals.get("partner_id"):
                # giữ tên nhập tay; resolve khi xác nhận
                pass
        return super().create(vals_list)

    def unlink(self):
        if any(txn.state == "done" for txn in self):
            raise UserError(self.env._("Không được xóa phiếu đã hoàn thành."))
        return super().unlink()

    def action_cancel(self):
        for txn in self:
            if txn.state == "done":
                raise UserError(self.env._("Không hủy phiếu đã hoàn thành. Hãy tạo phiếu ngược."))
            txn.state = "cancel"
        return True

    def action_draft(self):
        self.filtered(lambda t: t.state == "cancel").write({"state": "draft"})
        return True

    def action_confirm(self):
        for txn in self:
            txn._eam_confirm()
        return True

    def action_print_purchase_receipt(self):
        self.ensure_one()
        return self.env.ref("lug_eam.action_report_eam_purchase_receipt").report_action(self)

    def action_print_stock_issue(self):
        self.ensure_one()
        return self.env.ref("lug_eam.action_report_eam_stock_issue").report_action(self)

    def action_open_lines(self):
        """Smart button: giữ trên form, tab Chi tiết hàng."""
        self.ensure_one()
        return True

    def action_open_form(self):
        """Mở form đúng loại phiếu (NM / PX / khác)."""
        self.ensure_one()
        view_xmlid = {
            "in": "lug_eam.view_eam_transaction_form_in",
            "out": "lug_eam.view_eam_transaction_form_out",
            "transfer": "lug_eam.view_eam_transaction_form_out",
        }.get(self.txn_type)
        views = [(False, "form")]
        if view_xmlid:
            views = [(self.env.ref(view_xmlid).id, "form")]
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "eam.transaction",
            "res_id": self.id,
            "view_mode": "form",
            "views": views,
            "target": "current",
            "context": dict(self.env.context),
        }

    def action_delete_record(self):
        """Xóa từ list (chỉ nháp / hủy)."""
        self.unlink()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _eam_confirm(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(self.env._("Chỉ xác nhận phiếu ở trạng thái Nháp."))
        if not self.line_ids:
            raise UserError(self.env._("Phiếu phải có ít nhất một dòng."))
        method = {
            "in": self._apply_in,
            "out": self._apply_out,
            "transfer": self._apply_transfer,
            "recall": self._apply_recall,
            "disposal": self._apply_disposal,
        }.get(self.txn_type)
        if not method:
            raise UserError(self.env._("Loại phiếu không hợp lệ."))
        method()
        self.state = "done"
        self.message_post(body=self.env._("Đã xác nhận phiếu %s.") % self.name)

    def _apply_in(self):
        """Nhập mua theo mẫu giấy: nhập Mặt hàng + SL → tạo TS vào kho."""
        self.ensure_one()
        dest_label = self._eam_dest_label()
        if not self.warehouse_id and not self.dest_location_id and not dest_label:
            raise UserError(self.env._("Chọn «Nhập tại kho» trước khi xác nhận."))
        if self.dest_location_id and self.dest_location_id.loc_group != "stock":
            raise UserError(self.env._("Vị trí nhập kho phải thuộc nhóm Kho."))

        partner = self._eam_resolve_partner()
        Equipment = self.env["maintenance.equipment"]
        for line in self.line_ids:
            line_model = line.eam_model_id or self.eam_model_id
            if line.asset_id and not line.product_name and not line_model:
                self._eam_receive_existing_asset(line, dest_label)
                continue

            if not (line.product_name or line_model or line.asset_id):
                raise UserError(self.env._("Mỗi dòng cần nhập Mặt hàng."))

            qty = int(line.qty_received or line.qty_document or 0)
            if qty < 1:
                raise UserError(
                    self.env._("Dòng '%s' cần Số lượng thực nhập ≥ 1.")
                    % (line.product_name or line.product_code or "?")
                )
            if line.asset_id and qty == 1 and not line_model:
                self._eam_receive_existing_asset(line, dest_label)
                continue

            created = Equipment
            for _i in range(qty):
                created |= self._eam_create_asset_from_line(line, dest_label, partner=partner)
            line.write(
                {
                    "asset_id": created[0].id,
                    "qty_received": qty,
                    "to_state": "in_stock",
                    "to_location_note": dest_label,
                    "note": (
                        (line.note + " | " if line.note else "")
                        + self.env._("Đã tạo %s TS: %s")
                        % (len(created), ", ".join(created.mapped("asset_code")))
                    ),
                }
            )

    def _eam_default_category(self):
        Category = self.env["maintenance.equipment.category"]
        return (
            Category.search([("code", "=", "CAT_OTHER")], limit=1)
            or Category.search([("code", "=", "GRP_OTHER")], limit=1)
            or Category.search([], limit=1)
        )

    def _eam_create_asset_from_line(self, line, dest_label, partner=False):
        model = line.eam_model_id or self.eam_model_id
        name = line.product_name or (model.display_name if model else False) or line.product_code
        if not name:
            raise UserError(self.env._("Thiếu tên mặt hàng trên dòng."))
        category = model.category_id if model else self._eam_default_category()
        if not category:
            raise UserError(self.env._("Chưa có Nhóm tài sản mặc định (OTHER)."))
        if partner is False:
            partner = self._eam_resolve_partner()
        vals = {
            "name": name,
            "eam_model_id": model.id if model else False,
            "category_id": category.id,
            "eam_state": "in_stock",
            "company_id": self.company_id.id,
            "cost": line.unit_cost or (model.default_cost if model else 0.0) or 0.0,
            "location_note": dest_label or (self.warehouse_id.name if self.warehouse_id else False),
            "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
            "warehouse_id": (
                self.warehouse_id.id
                or (self.dest_location_id.warehouse_id.id if self.dest_location_id else False)
            ),
            "purchase_date": self.date,
            "partner_id": partner.id if partner else False,
            "po_ref": self.po_ref or False,
            "invoice_ref": self.invoice_ref or False,
            "funding_source": self.funding_source or False,
            "contract_ref": self.contract_ref or False,
            "contract_date": self.contract_date or False,
        }
        if line.product_code and not model:
            vals["barcode"] = line.product_code
        if self.warranty_month and self.date:
            vals["warranty_start"] = self.date
            vals["warranty_date"] = self.date + relativedelta(months=self.warranty_month)
        asset = self.env["maintenance.equipment"].create(vals)
        if not asset.asset_code:
            asset.write(asset._eam_prepare_identity_vals({}))
        asset._eam_log_history(
            "in",
            self.env._("Nhập mua theo phiếu %s") % self.name,
            transaction_id=self.id,
            from_state="draft",
            to_state="in_stock",
            location_note=vals["location_note"],
        )
        return asset

    def _eam_receive_existing_asset(self, line, dest_label):
        asset = line.asset_id
        asset._eam_assert_transition("in_stock")
        partner = self._eam_resolve_partner()
        vals = {
            "eam_state": "in_stock",
            "location_note": dest_label or (self.warehouse_id.name if self.warehouse_id else False),
            "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
            "warehouse_id": (
                self.warehouse_id.id
                or (self.dest_location_id.warehouse_id.id if self.dest_location_id else False)
            ),
            "owner_employee_id": False,
            "owner_user_id": False,
            "department_id": False,
        }
        if partner:
            vals["partner_id"] = partner.id
        if self.po_ref:
            vals["po_ref"] = self.po_ref
        if self.invoice_ref:
            vals["invoice_ref"] = self.invoice_ref
        if self.funding_source:
            vals["funding_source"] = self.funding_source
        if self.contract_ref:
            vals["contract_ref"] = self.contract_ref
        if self.contract_date:
            vals["contract_date"] = self.contract_date
        if self.date and not asset.purchase_date:
            vals["purchase_date"] = self.date
        if line.unit_cost:
            vals["cost"] = line.unit_cost
        if self.warranty_month and self.date:
            vals["warranty_start"] = self.date
            vals["warranty_date"] = self.date + relativedelta(months=self.warranty_month)
        if not asset.asset_code:
            vals.update(asset._eam_prepare_identity_vals({}))
        line.write(
            {
                "from_state": asset.eam_state,
                "to_state": "in_stock",
                "from_location_note": asset.location_note,
                "to_location_note": vals["location_note"],
            }
        )
        asset.with_context(eam_skip_state_check=True).write(vals)
        asset._eam_log_history(
            "in",
            self.env._("Nhập kho theo phiếu %s") % self.name,
            transaction_id=self.id,
            from_state=line.from_state,
            to_state="in_stock",
            location_note=vals["location_note"],
        )

    def _apply_out(self):
        """PHIẾU XUẤT KHO: xuất từ kho → kho đích hoặc người nhận / nơi sử dụng."""
        self.ensure_one()
        if not self.warehouse_id and not self.src_location_id:
            raise UserError(self.env._("Chọn «Xuất tại kho» trước khi xác nhận."))
        dest_wh = self.dest_warehouse_id
        dest_label = self._eam_dest_label()
        if not dest_wh and not self.dest_location_id and not dest_label and not self.owner_employee_id:
            raise UserError(
                self.env._("Chọn «Nhập tại kho» hoặc Người nhận / Vị trí đích trước khi xác nhận.")
            )

        for line in self.line_ids:
            asset = line.asset_id
            if not asset:
                raise UserError(self.env._("Mỗi dòng cần chọn Tài sản để xuất kho."))
            if asset.eam_state != "in_stock":
                raise UserError(
                    self.env._("Tài sản %s phải đang Trong kho để xuất.")
                    % (asset.asset_code or asset.display_name)
                )

            # Ưu tiên xuất sang kho đích (theo mẫu PX)
            if dest_wh:
                asset._eam_assert_transition("in_stock")
                loc_note = dest_wh.name
                vals = {
                    "eam_state": "in_stock",
                    "warehouse_id": dest_wh.id,
                    "location_note": loc_note,
                    "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
                    "owner_employee_id": False,
                    "owner_user_id": False,
                    "department_id": False,
                }
                if self.dest_location_id and self.dest_location_id.warehouse_id == dest_wh:
                    vals["location_note"] = self.dest_location_id.complete_name
                line.write(
                    {
                        "from_state": asset.eam_state,
                        "to_state": "in_stock",
                        "from_location_note": asset.location_note,
                        "to_location_note": vals["location_note"],
                        "product_name": line.product_name or asset.name,
                        "product_code": line.product_code or asset.asset_code,
                        "unit_cost": line.unit_cost or asset.cost or 0.0,
                        "qty_document": line.qty_document or 1.0,
                        "qty_received": line.qty_received or 1.0,
                    }
                )
                asset.with_context(eam_skip_state_check=True).write(vals)
                asset._eam_log_history(
                    "out",
                    self.env._("Xuất kho theo phiếu %s → %s") % (self.name, dest_wh.name),
                    transaction_id=self.id,
                    from_state="in_stock",
                    to_state="in_stock",
                    location_note=vals["location_note"],
                    employee_id=self.owner_employee_id.id if self.owner_employee_id else False,
                )
                continue

            # Cấp phát cho người dùng / vị trí sử dụng
            if not self.dest_location_id and not dest_label:
                raise UserError(self.env._("Cấp phát cần chọn Vị trí đích (nơi sử dụng)."))
            if self.dest_location_id and self.dest_location_id.loc_group not in ("usage", "stock"):
                raise UserError(self.env._("Vị trí đích không hợp lệ."))
            asset._eam_assert_transition("in_use")
            line.write(
                {
                    "from_state": asset.eam_state,
                    "to_state": "in_use",
                    "from_location_note": asset.location_note,
                    "to_location_note": dest_label,
                    "product_name": line.product_name or asset.name,
                    "product_code": line.product_code or asset.asset_code,
                    "unit_cost": line.unit_cost or asset.cost or 0.0,
                    "qty_document": line.qty_document or 1.0,
                    "qty_received": line.qty_received or 1.0,
                }
            )
            vals = {
                "eam_state": "in_use",
                "location_note": dest_label,
                "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
                "assign_date": self.date,
            }
            if self.department_id:
                vals["department_id"] = self.department_id.id
            if self.owner_employee_id:
                vals["owner_employee_id"] = self.owner_employee_id.id
                if self.owner_employee_id.user_id:
                    vals["owner_user_id"] = self.owner_employee_id.user_id.id
            asset.with_context(eam_skip_state_check=True).write(vals)
            asset._eam_log_history(
                "out",
                self.env._("Xuất kho / cấp phát theo phiếu %s") % self.name,
                transaction_id=self.id,
                from_state="in_stock",
                to_state="in_use",
                location_note=dest_label,
                employee_id=self.owner_employee_id.id if self.owner_employee_id else False,
                department_id=self.department_id.id if self.department_id else False,
            )

    def _apply_transfer(self):
        """Điều chuyển TS: trừ tồn kho nguồn (đổi warehouse) → cộng tồn kho đích."""
        self.ensure_one()
        src_wh = self.warehouse_id
        dest_wh = self.dest_warehouse_id
        dest_label = self._eam_dest_label()
        if not dest_wh and not self.dest_location_id and not dest_label:
            raise UserError(self.env._("Điều chuyển cần chọn «Nhập tại kho» / Vị trí đích."))
        if dest_wh and src_wh and dest_wh == src_wh and not self.dest_location_id:
            raise UserError(self.env._("Kho đích phải khác kho xuất."))

        for line in self.line_ids:
            asset = line.asset_id
            if not asset:
                raise UserError(self.env._("Điều chuyển yêu cầu chọn Tài sản trên mỗi dòng."))
            if asset.eam_state in ("draft", "disposed"):
                raise UserError(
                    self.env._("Không điều chuyển tài sản %s (trạng thái %s).")
                    % (asset.asset_code or asset.name, asset.eam_state)
                )
            # Tài sản phải đang thuộc kho xuất (nếu đã chọn kho xuất)
            if src_wh and asset.warehouse_id and asset.warehouse_id != src_wh:
                raise UserError(
                    self.env._(
                        "Tài sản %(code)s đang ở kho %(wh)s, không khớp kho xuất %(src)s."
                    )
                    % {
                        "code": asset.asset_code or asset.name,
                        "wh": asset.warehouse_id.display_name,
                        "src": src_wh.display_name,
                    }
                )

            from_state = asset.eam_state
            new_state = from_state
            loc_note = dest_label
            if dest_wh:
                loc_note = dest_wh.name
            if self.dest_location_id:
                loc_note = self.dest_location_id.complete_name

            vals = {
                "location_note": loc_note,
                "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
            }

            # Ưu tiên chuyển sang kho đích → tồn nguồn giảm / tồn đích tăng
            if dest_wh:
                new_state = "in_stock"
                if from_state != "in_stock":
                    asset._eam_assert_transition("in_stock")
                vals.update(
                    {
                        "eam_state": "in_stock",
                        "warehouse_id": dest_wh.id,
                        "owner_employee_id": False,
                        "owner_user_id": False,
                        "department_id": False,
                    }
                )
            elif self.dest_location_id:
                if self.dest_location_id.loc_group == "stock":
                    new_state = "in_stock"
                    vals.update(
                        {
                            "eam_state": "in_stock",
                            "warehouse_id": (
                                self.dest_location_id.warehouse_id.id
                                or (dest_wh.id if dest_wh else False)
                                or asset.warehouse_id.id
                            ),
                            "owner_employee_id": False,
                            "owner_user_id": False,
                            "department_id": False,
                        }
                    )
                    if from_state != "in_stock":
                        asset._eam_assert_transition("in_stock")
                elif self.dest_location_id.loc_group == "usage":
                    new_state = "in_use"
                    if from_state == "in_stock":
                        asset._eam_assert_transition("in_use")
                    vals["eam_state"] = "in_use"
                    # Xuất khỏi kho nguồn → tồn nguồn giảm
                    if self.dest_location_id.warehouse_id:
                        vals["warehouse_id"] = self.dest_location_id.warehouse_id.id
            elif dest_wh:
                pass  # already handled
            else:
                # Chỉ có text dest — vẫn chuyển note, giữ kho nếu không có dest_wh
                if src_wh and not dest_wh:
                    raise UserError(
                        self.env._("Chọn kho đích để trừ tồn kho nguồn khi điều chuyển.")
                    )

            if self.department_id and new_state == "in_use":
                vals["department_id"] = self.department_id.id
            if self.owner_employee_id and new_state == "in_use":
                vals["owner_employee_id"] = self.owner_employee_id.id
                if self.owner_employee_id.user_id:
                    vals["owner_user_id"] = self.owner_employee_id.user_id.id

            qty = line.qty_received or line.qty_document or 1.0
            line.write(
                {
                    "from_state": from_state,
                    "to_state": new_state,
                    "from_location_note": asset.location_note,
                    "to_location_note": loc_note,
                    "product_name": line.product_name or asset.name,
                    "product_code": line.product_code or asset.asset_code,
                    "unit_cost": line.unit_cost or asset.cost or 0.0,
                    "qty_document": line.qty_document or qty,
                    "qty_received": qty,
                }
            )
            asset.with_context(eam_skip_state_check=True).write(vals)
            asset._eam_log_history(
                "transfer",
                self.env._("Điều chuyển theo phiếu %s (trừ tồn kho nguồn)") % self.name,
                transaction_id=self.id,
                from_state=from_state,
                to_state=new_state,
                location_note=loc_note,
                employee_id=self.owner_employee_id.id if self.owner_employee_id else False,
                department_id=self.department_id.id if self.department_id else False,
            )

    def _apply_recall(self):
        self.ensure_one()
        dest_label = self._eam_dest_label()
        if not self.dest_location_id and not dest_label and not self.warehouse_id:
            raise UserError(self.env._("Thu hồi cần chọn Kho / Vị trí kho đích."))
        if self.dest_location_id and self.dest_location_id.loc_group != "stock":
            raise UserError(self.env._("Vị trí thu hồi phải thuộc nhóm Kho."))
        for line in self.line_ids:
            asset = line.asset_id
            if not asset:
                raise UserError(self.env._("Thu hồi yêu cầu chọn Tài sản trên mỗi dòng."))
            if asset.eam_state not in ("in_use", "maintenance", "broken"):
                raise UserError(
                    self.env._("Tài sản %s không thể thu hồi từ trạng thái hiện tại.")
                    % (asset.asset_code or asset.name)
                )
            asset._eam_assert_transition("in_stock")
            loc_note = dest_label or (self.warehouse_id.name if self.warehouse_id else False)
            line.write(
                {
                    "from_state": asset.eam_state,
                    "to_state": "in_stock",
                    "from_location_note": asset.location_note,
                    "to_location_note": loc_note,
                }
            )
            asset.with_context(eam_skip_state_check=True).write(
                {
                    "eam_state": "in_stock",
                    "location_note": loc_note,
                    "current_location_id": self.dest_location_id.id if self.dest_location_id else False,
                    "warehouse_id": (
                        self.warehouse_id.id
                        or (self.dest_location_id.warehouse_id.id if self.dest_location_id else False)
                        or asset.warehouse_id.id
                    ),
                    "owner_employee_id": False,
                    "owner_user_id": False,
                    "department_id": False,
                }
            )
            asset._eam_log_history(
                "recall",
                self.env._("Thu hồi về kho theo phiếu %s") % self.name,
                transaction_id=self.id,
                from_state=line.from_state,
                to_state="in_stock",
                location_note=loc_note,
            )

    def _apply_disposal(self):
        self.ensure_one()
        if not self.reason:
            raise UserError(self.env._("Thanh lý cần nhập lý do."))
        for line in self.line_ids:
            asset = line.asset_id
            if not asset:
                raise UserError(self.env._("Thanh lý yêu cầu chọn Tài sản trên mỗi dòng."))
            open_req = asset.maintenance_ids.filtered(lambda r: not r.stage_id.done and not r.archive)
            if open_req:
                raise UserError(
                    self.env._("Không thanh lý %s khi còn phiếu bảo trì mở.")
                    % (asset.asset_code or asset.name)
                )
            asset._eam_assert_transition("disposed")
            line.write(
                {
                    "from_state": asset.eam_state,
                    "to_state": "disposed",
                    "from_location_note": asset.location_note,
                    "to_location_note": asset.location_note,
                }
            )
            asset.with_context(eam_skip_state_check=True).write(
                {
                    "eam_state": "disposed",
                    "scrap_date": self.date,
                    "active": False,
                }
            )
            asset._eam_log_history(
                "disposal",
                self.env._("Thanh lý theo phiếu %s — %s") % (self.name, self.reason),
                transaction_id=self.id,
                from_state=line.from_state,
                to_state="disposed",
            )


class EamTransactionLine(models.Model):
    _name = "eam.transaction.line"
    _description = "Dòng phiếu nghiệp vụ tài sản"
    _order = "sequence, id"

    header_id = fields.Many2one(
        "eam.transaction",
        string="Phiếu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="STT", default=10)
    # Nhập mua theo mẫu: mặt hàng / mã / ĐVT / SL
    eam_model_id = fields.Many2one(
        "eam.model",
        string="Danh mục (Model)",
        ondelete="restrict",
        check_company=True,
    )
    product_name = fields.Char(string="Mặt hàng")
    product_code = fields.Char(string="Mã số")
    uom_name = fields.Char(string="Đvt", default="Cái")
    qty_document = fields.Float(string="SL theo chứng từ", digits=(16, 2), default=1.0)
    qty_received = fields.Float(string="SL thực nhập", digits=(16, 2), default=1.0)
    subtotal = fields.Monetary(
        string="Thành tiền",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
    )
    # Các loại phiếu khác: chọn tài sản có sẵn
    asset_id = fields.Many2one(
        "maintenance.equipment",
        string="Tài sản",
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(related="header_id.company_id", store=True)
    asset_code = fields.Char(related="asset_id.asset_code", string="Mã TS")
    eam_state = fields.Selection(related="asset_id.eam_state", string="TT hiện tại")
    unit_cost = fields.Monetary(string="Đơn giá", currency_field="currency_id")
    currency_id = fields.Many2one(related="header_id.currency_id")
    from_state = fields.Char(string="Từ TT")
    to_state = fields.Char(string="Sang TT")
    from_location_note = fields.Char(string="Từ vị trí")
    to_location_note = fields.Char(string="Đến vị trí")
    note = fields.Char(string="Ghi chú")
    txn_type = fields.Selection(related="header_id.txn_type", store=True)

    @api.depends("qty_received", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.qty_received or 0.0) * (line.unit_cost or 0.0)

    @api.onchange("eam_model_id")
    def _onchange_eam_model_id(self):
        for line in self:
            model = line.eam_model_id
            if not model:
                continue
            line.product_name = model.display_name or model.name
            line.product_code = model.code
            if model.uom_note:
                line.uom_name = model.uom_note
            if model.default_cost and not line.unit_cost:
                line.unit_cost = model.default_cost
            if not line.qty_document:
                line.qty_document = 1.0
            if not line.qty_received:
                line.qty_received = line.qty_document or 1.0

    @api.onchange("qty_document")
    def _onchange_qty_document(self):
        for line in self:
            if line.header_id.txn_type == "in":
                # Giống mẫu giấy: thực nhập mặc định = theo chứng từ
                line.qty_received = line.qty_document

    @api.onchange("asset_id")
    def _onchange_asset_id(self):
        for line in self:
            asset = line.asset_id
            if not asset:
                continue
            if asset.cost and not line.unit_cost:
                line.unit_cost = asset.cost
            line.product_name = asset.name
            line.product_code = asset.asset_code or asset.barcode
            line.uom_name = line.uom_name or "Cái"
            line.qty_document = line.qty_document or 1.0
            line.qty_received = line.qty_received or 1.0
            if asset.eam_model_id and not line.eam_model_id:
                line.eam_model_id = asset.eam_model_id
