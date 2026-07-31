# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class EamMaintenancePart(models.Model):
    _name = "eam.maintenance.part"
    _description = "Vật tư dùng trong bảo trì"
    _order = "id"

    request_id = fields.Many2one(
        "maintenance.request",
        string="Phiếu BT",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "eam.inventory.product",
        string="Vật tư",
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    quantity = fields.Float(string="Số lượng", digits=(16, 2), required=True, default=1.0)
    uom_name = fields.Char(related="product_id.uom_name", string="Đơn vị")
    unit_cost = fields.Monetary(string="Đơn giá", currency_field="currency_id")
    currency_id = fields.Many2one(
        related="request_id.company_id.currency_id",
        store=True,
    )
    subtotal = fields.Monetary(
        string="Thành tiền",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
    )
    company_id = fields.Many2one(related="request_id.company_id", store=True)
    consumed = fields.Boolean(string="Đã trừ kho", default=False, copy=False)

    @api.depends("quantity", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.quantity or 0.0) * (line.unit_cost or 0.0)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.unit_cost = line.product_id.standard_cost or 0.0


class EamMaintenanceChecklist(models.Model):
    _name = "eam.maintenance.checklist"
    _description = "Checklist bảo trì"
    _order = "sequence, id"

    request_id = fields.Many2one(
        "maintenance.request",
        string="Phiếu BT",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Hạng mục", required=True)
    result = fields.Selection(
        [
            ("todo", "Chưa làm"),
            ("pass", "Đạt"),
            ("fail", "Không đạt"),
            ("na", "N/A"),
        ],
        string="Kết quả",
        default="todo",
        required=True,
    )
    note = fields.Char(string="Ghi chú")
    done = fields.Boolean(compute="_compute_done", store=True)

    @api.depends("result")
    def _compute_done(self):
        for line in self:
            line.done = line.result in ("pass", "fail", "na")


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    work_order_code = fields.Char(
        string="Mã Work Order",
        copy=False,
        index=True,
        tracking=True,
        help="Mã phiếu công việc, ví dụ WO000001.",
    )
    failure_symptom = fields.Text(string="Triệu chứng / Báo hỏng")
    diagnosis = fields.Text(string="Chẩn đoán")
    work_done = fields.Text(string="Công việc đã thực hiện")
    checklist_ids = fields.One2many(
        "eam.maintenance.checklist",
        "request_id",
        string="Checklist",
    )
    checklist_progress = fields.Float(
        string="% Checklist",
        compute="_compute_checklist_progress",
        store=True,
    )
    part_ids = fields.One2many("eam.maintenance.part", "request_id", string="Vật tư")
    eam_labor_cost = fields.Monetary(
        string="Chi phí nhân công",
        currency_field="currency_id",
        tracking=True,
    )
    eam_part_cost = fields.Monetary(
        string="Chi phí vật tư",
        currency_field="currency_id",
        compute="_compute_eam_costs",
        store=True,
    )
    eam_total_cost = fields.Monetary(
        string="Tổng chi phí",
        currency_field="currency_id",
        compute="_compute_eam_costs",
        store=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
    )
    asset_code = fields.Char(related="equipment_id.asset_code", string="Mã TS")
    eam_asset_state = fields.Selection(related="equipment_id.eam_state", string="TT tài sản")
    parts_consumed = fields.Boolean(string="Đã trừ vật tư", default=False, copy=False)

    _work_order_code_uniq = models.Constraint(
        "unique(work_order_code)",
        "Mã Work Order phải duy nhất.",
    )

    @api.depends("checklist_ids", "checklist_ids.result")
    def _compute_checklist_progress(self):
        for request in self:
            lines = request.checklist_ids
            if not lines:
                request.checklist_progress = 0.0
                continue
            done = len(lines.filtered(lambda l: l.result != "todo"))
            request.checklist_progress = 100.0 * done / len(lines)

    @api.depends("part_ids.subtotal", "eam_labor_cost")
    def _compute_eam_costs(self):
        for request in self:
            part_cost = sum(request.part_ids.mapped("subtotal"))
            request.eam_part_cost = part_cost
            request.eam_total_cost = part_cost + (request.eam_labor_cost or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("work_order_code"):
                vals["work_order_code"] = (
                    self.env["ir.sequence"].next_by_code("eam.work.order") or False
                )
        requests = super().create(vals_list)
        for request in requests:
            if not request.checklist_ids:
                request._eam_load_default_checklist()
            request._eam_on_request_created()
        return requests

    def write(self, vals):
        stage_before = {r.id: r.stage_id for r in self}
        done_before = {r.id: bool(r.stage_id.done) for r in self}
        res = super().write(vals)
        if "stage_id" in vals:
            for request in self:
                was_done = done_before.get(request.id)
                is_done = bool(request.stage_id.done)
                if not was_done and is_done:
                    request._eam_on_request_done()
                elif was_done and not is_done:
                    pass
                elif (
                    not is_done
                    and stage_before.get(request.id)
                    and stage_before[request.id] != request.stage_id
                    and request.equipment_id
                    and request.equipment_id.eam_state == "broken"
                ):
                    # Bắt đầu xử lý: broken → maintenance
                    request.equipment_id.with_context(eam_skip_state_check=True).write(
                        {"eam_state": "maintenance"}
                    )
                    request.equipment_id._eam_log_history(
                        "maintenance",
                        self.env._("Bắt đầu xử lý WO %s")
                        % (request.work_order_code or request.name),
                        from_state="broken",
                        to_state="maintenance",
                    )
        return res

    def _eam_load_default_checklist(self):
        defaults = [
            self.env._("Kiểm tra ngoại quan / an toàn"),
            self.env._("Xác định nguyên nhân"),
            self.env._("Thực hiện sửa chữa / bảo dưỡng"),
            self.env._("Thay thế vật tư (nếu có)"),
            self.env._("Vệ sinh / chạy thử"),
            self.env._("Nghiệm thu với người dùng"),
        ]
        for request in self:
            request.checklist_ids = [
                (0, 0, {"sequence": (i + 1) * 10, "name": name})
                for i, name in enumerate(defaults)
            ]

    def action_load_default_checklist(self):
        for request in self:
            if request.checklist_ids:
                raise UserError(self.env._("Checklist đã có hạng mục. Xóa hết trước khi tải mẫu."))
            request._eam_load_default_checklist()
        return True

    def _eam_on_request_created(self):
        """Báo hỏng / tạo phiếu → cập nhật trạng thái asset."""
        for request in self:
            asset = request.equipment_id
            if not asset:
                continue
            if request.maintenance_type == "corrective":
                if asset.eam_state in ("in_use", "in_stock", "draft"):
                    old = asset.eam_state
                    # draft/in_stock → có thể nhảy broken? ma trận: in_stock→broken OK, in_use→broken OK, draft không có broken
                    target = "broken"
                    if old == "draft":
                        # Nhập kho tạm rồi broken không hợp lý — giữ draft, chỉ log
                        asset._eam_log_history(
                            "maintenance",
                            self.env._("Tạo phiếu báo hỏng %s (asset còn nháp)")
                            % (request.work_order_code or request.name),
                            from_state=old,
                            to_state=old,
                        )
                    else:
                        asset._eam_assert_transition(target)
                        asset.with_context(eam_skip_state_check=True).write({"eam_state": target})
                        asset._eam_log_history(
                            "maintenance",
                            self.env._("Báo hỏng — WO %s")
                            % (request.work_order_code or request.name),
                            from_state=old,
                            to_state=target,
                        )
            elif request.maintenance_type == "preventive":
                if asset.eam_state == "in_use":
                    asset._eam_assert_transition("maintenance")
                    asset.with_context(eam_skip_state_check=True).write({"eam_state": "maintenance"})
                    asset._eam_log_history(
                        "maintenance",
                        self.env._("Bảo trì phòng ngừa — WO %s")
                        % (request.work_order_code or request.name),
                        from_state="in_use",
                        to_state="maintenance",
                    )

    def _eam_on_request_done(self):
        """Hoàn thành WO: trừ vật tư + đưa asset về in_use."""
        self.ensure_one()
        if not self.close_date:
            self.close_date = fields.Date.context_today(self)
        self._eam_consume_parts()
        asset = self.equipment_id
        if asset and asset.eam_state in ("broken", "maintenance"):
            old = asset.eam_state
            asset._eam_assert_transition("in_use")
            asset.with_context(eam_skip_state_check=True).write({"eam_state": "in_use"})
            asset._eam_log_history(
                "maintenance",
                self.env._("Hoàn thành WO %s — chi phí %s")
                % (self.work_order_code or self.name, self.eam_total_cost),
                from_state=old,
                to_state="in_use",
                note=self.work_done or self.diagnosis or False,
            )

    def _eam_consume_parts(self):
        """Trừ tồn kho vật tư (Inventory theo số lượng) khi hoàn thành."""
        self.ensure_one()
        if self.parts_consumed:
            return
        Move = self.env["eam.inventory.move"]
        for line in self.part_ids.filtered(lambda p: not p.consumed and p.quantity > 0):
            product = line.product_id
            if line.quantity > product.qty_on_hand:
                raise UserError(
                    self.env._(
                        "Không đủ tồn vật tư %(p)s để hoàn thành WO. Tồn: %(q)s, cần: %(n)s."
                    )
                    % {
                        "p": product.display_name,
                        "q": product.qty_on_hand,
                        "n": line.quantity,
                    }
                )
            Move.sudo().create(
                {
                    "move_type": "issue",
                    "state": "done",
                    "date": fields.Date.context_today(self),
                    "product_id": product.id,
                    "warehouse_id": product.warehouse_id.id,
                    "qty": line.quantity,
                    "reason": self.env._("Xuất cho WO %s")
                    % (self.work_order_code or self.name),
                    "company_id": self.company_id.id,
                }
            )
            line.consumed = True
        self.parts_consumed = True

    def action_start_work(self):
        """Kỹ thuật bắt đầu xử lý: broken → maintenance."""
        for request in self:
            asset = request.equipment_id
            if asset and asset.eam_state == "broken":
                asset._eam_assert_transition("maintenance")
                asset.with_context(eam_skip_state_check=True).write({"eam_state": "maintenance"})
                asset._eam_log_history(
                    "maintenance",
                    self.env._("Kỹ thuật bắt đầu xử lý WO %s")
                    % (request.work_order_code or request.name),
                    from_state="broken",
                    to_state="maintenance",
                )
        return True
