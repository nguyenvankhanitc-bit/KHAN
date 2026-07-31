# -*- coding: utf-8 -*-

import base64
import logging
import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .eam_transaction import EAM_STATE_TRANSITIONS

_logger = logging.getLogger(__name__)

EAM_STATE_SELECTION = [
    ("draft", "Nháp"),
    ("in_stock", "Trong kho"),
    ("in_use", "Đang sử dụng"),
    ("maintenance", "Đang bảo trì"),
    ("broken", "Hỏng"),
    ("disposed", "Đã thanh lý"),
]


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    asset_code = fields.Char(
        string="Mã tài sản",
        copy=False,
        index=True,
        tracking=True,
        help="Mã duy nhất tự sinh, ví dụ TS-IT-2026-00001.",
    )
    eam_model_id = fields.Many2one(
        "eam.model",
        string="Danh mục (Model)",
        tracking=True,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    eam_brand_id = fields.Many2one(
        related="eam_model_id.brand_id",
        string="Thương hiệu",
        store=True,
        index=True,
    )
    barcode = fields.Char(
        string="Barcode",
        copy=False,
        index=True,
        help="Mặc định = mã tài sản. Có thể dùng để quét.",
    )
    qr_code = fields.Char(
        string="Nội dung QR",
        copy=False,
        index=True,
        help="Nội dung mã QR, mặc định = mã tài sản.",
    )
    qr_image = fields.Binary(
        string="Ảnh QR",
        compute="_compute_qr_image",
        store=True,
        attachment=True,
    )
    eam_state = fields.Selection(
        EAM_STATE_SELECTION,
        string="Trạng thái",
        default="draft",
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )
    eam_state_color = fields.Integer(
        string="Màu trạng thái",
        compute="_compute_eam_state_color",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban sử dụng",
        tracking=True,
        index=True,
        check_company=True,
    )
    owner_employee_id = fields.Many2one(
        "hr.employee",
        string="Người giữ tài sản",
        tracking=True,
        index=True,
        check_company=True,
    )
    purchase_date = fields.Date(string="Ngày mua", tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self.env.company.currency_id,
    )
    po_ref = fields.Char(string="Số PO / Hóa đơn")
    funding_source = fields.Char(string="Nguồn vốn")
    invoice_ref = fields.Char(string="Số hóa đơn")
    contract_ref = fields.Char(string="Số hợp đồng", tracking=True)
    contract_date = fields.Date(string="Ngày hợp đồng")
    warranty_start = fields.Date(string="Bắt đầu bảo hành")
    warranty_state = fields.Selection(
        [
            ("none", "Không BH"),
            ("valid", "Còn hạn"),
            ("expiring", "Sắp hết"),
            ("expired", "Hết hạn"),
        ],
        string="Trạng thái bảo hành",
        compute="_compute_warranty_state",
        store=True,
    )
    image_1920 = fields.Image(string="Ảnh tài sản", max_width=1920, max_height=1920)
    warehouse_id = fields.Many2one(
        "eam.warehouse",
        string="Kho",
        tracking=True,
        index=True,
        check_company=True,
        ondelete="restrict",
    )
    current_location_id = fields.Many2one(
        "eam.location",
        string="Vị trí hiện tại",
        tracking=True,
        index=True,
        check_company=True,
        ondelete="restrict",
    )
    site_location_id = fields.Many2one(
        "eam.location",
        string="Cửa hàng / Chi nhánh",
        compute="_compute_site_location_id",
        store=True,
        index=True,
        help="Vị trí loại Cửa hàng/Chi nhánh (leo cây từ vị trí hiện tại).",
    )
    location_note = fields.Char(
        string="Vị trí (text)",
        help="Hiển thị / ghi chú vị trí. Ưu tiên chọn Vị trí hiện tại ở trên.",
    )
    next_maintenance_date = fields.Date(
        string="Ngày BT kế tiếp",
        compute="_compute_next_maintenance_date",
        store=True,
    )
    maintenance_cycle_month = fields.Integer(
        related="category_id.maintenance_cycle_month",
        string="Chu kỳ BT (tháng)",
    )
    transaction_line_ids = fields.One2many(
        "eam.transaction.line",
        "asset_id",
        string="Dòng phiếu",
    )
    transaction_count = fields.Integer(compute="_compute_eam_counts")
    history_ids = fields.One2many("eam.asset.history", "asset_id", string="Lịch sử")
    history_count = fields.Integer(compute="_compute_eam_counts")

    _asset_code_uniq = models.Constraint(
        "unique(asset_code)",
        "Mã tài sản phải duy nhất.",
    )
    _qr_code_uniq = models.Constraint(
        "unique(qr_code)",
        "Nội dung QR phải duy nhất.",
    )
    _barcode_uniq = models.Constraint(
        "unique(barcode)",
        "Barcode phải duy nhất.",
    )

    @api.depends("transaction_line_ids", "history_ids")
    def _compute_eam_counts(self):
        for equipment in self:
            equipment.transaction_count = len(equipment.transaction_line_ids)
            equipment.history_count = len(equipment.history_ids)

    @api.onchange("current_location_id")
    def _onchange_current_location_id(self):
        for equipment in self:
            loc = equipment.current_location_id
            if loc:
                equipment.location_note = loc.complete_name
                if loc.warehouse_id:
                    equipment.warehouse_id = loc.warehouse_id
                if loc.loc_group == "usage" and loc.department_id and not equipment.department_id:
                    equipment.department_id = loc.department_id

    @api.depends(
        "current_location_id",
        "current_location_id.loc_kind",
        "current_location_id.parent_id",
        "current_location_id.parent_path",
    )
    def _compute_site_location_id(self):
        for equipment in self:
            loc = equipment.current_location_id
            site = self.env["eam.location"]
            cursor = loc
            while cursor:
                if cursor.loc_kind == "site":
                    site = cursor
                    break
                cursor = cursor.parent_id
            if not site and loc and loc.loc_group == "usage":
                # Fallback: nút gốc của nhánh usage (thường là cửa hàng)
                cursor = loc
                while cursor.parent_id and cursor.parent_id.loc_group == "usage":
                    cursor = cursor.parent_id
                site = cursor
            equipment.site_location_id = site

    @api.depends("eam_state")
    def _compute_eam_state_color(self):
        mapping = {
            "draft": 0,
            "in_stock": 4,
            "in_use": 10,
            "maintenance": 2,
            "broken": 1,
            "disposed": 3,
        }
        for equipment in self:
            equipment.eam_state_color = mapping.get(equipment.eam_state, 0)

    @api.depends("qr_code")
    def _compute_qr_image(self):
        report = self.env["ir.actions.report"]
        for equipment in self:
            if not equipment.qr_code:
                equipment.qr_image = False
                continue
            try:
                png = report.barcode(
                    "QR",
                    equipment.qr_code,
                    width=200,
                    height=200,
                    humanreadable=0,
                    quiet=1,
                )
                equipment.qr_image = base64.b64encode(png) if png else False
            except Exception:
                _logger.exception(
                    "Không tạo được QR cho tài sản %s", equipment.asset_code or equipment.id
                )
                equipment.qr_image = False

    @api.depends("warranty_date", "warranty_start")
    def _compute_warranty_state(self):
        today = fields.Date.context_today(self)
        for equipment in self:
            if not equipment.warranty_date:
                equipment.warranty_state = "none"
                continue
            days_left = (equipment.warranty_date - today).days
            if days_left < 0:
                equipment.warranty_state = "expired"
            elif days_left <= 30:
                equipment.warranty_state = "expiring"
            else:
                equipment.warranty_state = "valid"

    @api.depends(
        "category_id.maintenance_cycle_month",
        "purchase_date",
        "effective_date",
        "maintenance_ids.close_date",
        "maintenance_ids.stage_id.done",
        "maintenance_ids.request_date",
    )
    def _compute_next_maintenance_date(self):
        for equipment in self:
            months = equipment.category_id.maintenance_cycle_month or 0
            if months <= 0:
                equipment.next_maintenance_date = False
                continue
            done = equipment.maintenance_ids.filtered(
                lambda r: r.stage_id.done and (r.close_date or r.request_date)
            )
            if done:
                last = max(done.mapped(lambda r: r.close_date or r.request_date))
            else:
                last = equipment.purchase_date or equipment.effective_date
            equipment.next_maintenance_date = (
                last + relativedelta(months=months) if last else False
            )

    @api.onchange("eam_model_id")
    def _onchange_eam_model_id(self):
        for equipment in self:
            model = equipment.eam_model_id
            if not model:
                continue
            equipment.category_id = model.category_id
            if model.name and not equipment.model:
                equipment.model = "%s %s" % (model.brand_id.name or "", model.name).strip()
            if model.default_cost and not equipment.cost:
                equipment.cost = model.default_cost
            if model.image and not equipment.image_1920:
                equipment.image_1920 = model.image
            if model.default_warranty_month and equipment.purchase_date and not equipment.warranty_date:
                equipment.warranty_start = equipment.warranty_start or equipment.purchase_date
                equipment.warranty_date = equipment.purchase_date + relativedelta(
                    months=model.default_warranty_month
                )
            if not equipment.name:
                brand = model.brand_id.name or ""
                equipment.name = ("%s %s" % (brand, model.name)).strip() or model.display_name

    @api.onchange("purchase_date", "eam_model_id")
    def _onchange_purchase_warranty(self):
        for equipment in self:
            model = equipment.eam_model_id
            if not equipment.purchase_date or not model or not model.default_warranty_month:
                continue
            if not equipment.warranty_start:
                equipment.warranty_start = equipment.purchase_date
            if not equipment.warranty_date:
                equipment.warranty_date = equipment.purchase_date + relativedelta(
                    months=model.default_warranty_month
                )

    @api.onchange("owner_employee_id")
    def _onchange_owner_employee_id(self):
        for equipment in self:
            employee = equipment.owner_employee_id
            if employee:
                if employee.user_id:
                    equipment.owner_user_id = employee.user_id
                if employee.department_id and not equipment.department_id:
                    equipment.department_id = employee.department_id

    @api.constrains("eam_model_id", "category_id")
    def _check_model_category(self):
        for equipment in self:
            if (
                equipment.eam_model_id
                and equipment.category_id
                and equipment.eam_model_id.category_id != equipment.category_id
            ):
                raise ValidationError(
                    "Nhóm tài sản phải khớp với danh mục (Model) đã chọn."
                )

    @api.constrains("category_id", "warranty_date", "warranty_start")
    def _check_require_warranty(self):
        for equipment in self:
            if (
                equipment.category_id.require_warranty
                and equipment.eam_state not in ("draft", "disposed")
                and not equipment.warranty_date
            ):
                raise ValidationError(
                    "Nhóm '%s' bắt buộc nhập ngày hết hạn bảo hành."
                    % (equipment.category_id.display_name,)
                )

    def _eam_category_code_token(self, category):
        """Lấy token ngắn cho mã TS-{TOKEN}-{YEAR}-{SEQ}."""
        if not category:
            return "GEN"
        current = category
        token_source = category
        while current:
            if current.code_token:
                token_source = current
                break
            if current.code and str(current.code).upper().startswith("GRP_"):
                token_source = current
                break
            if not current.parent_id:
                token_source = current
                break
            current = current.parent_id
        if token_source.code_token:
            token = token_source.code_token
        else:
            token = token_source.code or "GEN"
            token = re.sub(r"^(GRP_|CAT_)", "", token, flags=re.IGNORECASE)
        token = re.sub(r"[^A-Za-z0-9]", "", token or "GEN").upper()
        return (token or "GEN")[:12]

    def _eam_next_asset_code(self, category=None):
        category = category or self.category_id
        if category and category.asset_sequence_id:
            code = category.asset_sequence_id.next_by_id()
            if not code:
                raise UserError("Sequence nhóm tài sản không trả về mã.")
            return code

        token = self._eam_category_code_token(category)
        year = fields.Date.context_today(self).year
        seq = self.env["ir.sequence"].next_by_code("eam.asset")
        if not seq:
            raise UserError("Chưa cấu hình sequence mã tài sản (eam.asset).")
        # Sequence chỉ còn phần số (padding); ghép prefix nghiệp vụ.
        number = re.sub(r"\D", "", str(seq)) or str(seq)
        return "TS-%s-%s-%s" % (token, year, number.zfill(5)[-5:])

    def _eam_prepare_identity_vals(self, vals, category=None):
        """Ensure asset_code / barcode / qr_code when creating or confirming."""
        result = dict(vals)
        Category = self.env["maintenance.equipment.category"]
        if category is None:
            category = Category.browse(result.get("category_id")) if result.get("category_id") else self.category_id
        if not result.get("asset_code"):
            result["asset_code"] = self._eam_next_asset_code(category=category)
        code = result["asset_code"]
        if not result.get("barcode"):
            result["barcode"] = code
        require_qr = True
        if category:
            require_qr = category.require_qr
        if require_qr and not result.get("qr_code"):
            result["qr_code"] = code
        return result

    @api.model_create_multi
    def create(self, vals_list):
        Category = self.env["maintenance.equipment.category"]
        Model = self.env["eam.model"]
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get("eam_model_id") and not vals.get("category_id"):
                model = Model.browse(vals["eam_model_id"])
                vals["category_id"] = model.category_id.id
                if not vals.get("model"):
                    vals["model"] = "%s %s" % (model.brand_id.name or "", model.name).strip()
                if not vals.get("name"):
                    brand = model.brand_id.name or ""
                    vals["name"] = ("%s %s" % (brand, model.name)).strip() or model.display_name
            category = Category.browse(vals["category_id"]) if vals.get("category_id") else Category
            vals = self._eam_prepare_identity_vals(vals, category=category)
            if vals.get("serial_no") == "":
                vals["serial_no"] = False
            prepared.append(vals)
        equipments = super().create(prepared)
        for equipment in equipments:
            equipment._eam_log_history(
                "create",
                self.env._("Tạo tài sản %s") % (equipment.asset_code or equipment.name),
                to_state=equipment.eam_state,
                location_note=equipment.location_note,
            )
        return equipments

    def write(self, vals):
        vals = dict(vals)
        if vals.get("serial_no") == "":
            vals["serial_no"] = False
        if vals.get("eam_model_id") and "category_id" not in vals:
            model = self.env["eam.model"].browse(vals["eam_model_id"])
            vals["category_id"] = model.category_id.id

        state_changes = []
        if "eam_state" in vals and not self.env.context.get("eam_skip_state_check"):
            for equipment in self:
                new_state = vals["eam_state"]
                if new_state != equipment.eam_state:
                    equipment._eam_assert_transition(new_state)
                    state_changes.append((equipment, equipment.eam_state, new_state))

        res = super().write(vals)
        for equipment in self.filtered(lambda e: not e.asset_code):
            identity = equipment._eam_prepare_identity_vals({})
            super(MaintenanceEquipment, equipment).write(identity)
        for equipment, old_state, new_state in state_changes:
            equipment._eam_log_history(
                "state",
                self.env._("Đổi trạng thái %s → %s") % (old_state, new_state),
                from_state=old_state,
                to_state=new_state,
                location_note=equipment.location_note,
            )
        return res

    def _eam_assert_transition(self, new_state):
        self.ensure_one()
        allowed = EAM_STATE_TRANSITIONS.get(self.eam_state, set())
        if new_state == self.eam_state:
            return
        if new_state not in allowed:
            raise UserError(
                self.env._(
                    "Không chuyển tài sản %(code)s từ '%(frm)s' sang '%(to)s'."
                )
                % {
                    "code": self.asset_code or self.name,
                    "frm": self.eam_state,
                    "to": new_state,
                }
            )

    def _eam_log_history(self, event_type, name, **kwargs):
        History = self.env["eam.asset.history"]
        for equipment in self:
            History.log_event(equipment, event_type, name, **kwargs)

    def _eam_open_transaction(self, txn_type, extra_context=None):
        self.ensure_one()
        ctx = {
            "default_txn_type": txn_type,
            "default_company_id": self.company_id.id,
            "default_partner_id": self.partner_id.id if txn_type == "in" else False,
            "default_contract_ref": self.contract_ref if txn_type == "in" else False,
            "default_line_ids": [(0, 0, {"asset_id": self.id, "unit_cost": self.cost or 0.0})],
        }
        if txn_type == "out":
            ctx["default_department_id"] = self.department_id.id
            ctx["default_owner_employee_id"] = self.owner_employee_id.id
        if txn_type in ("in", "recall") and self.location_note:
            ctx["default_src_location_note"] = self.location_note
        if extra_context:
            ctx.update(extra_context)
        action = {
            "type": "ir.actions.act_window",
            "name": dict(self.env["eam.transaction"]._fields["txn_type"].selection).get(txn_type),
            "res_model": "eam.transaction",
            "view_mode": "form",
            "target": "current",
            "context": ctx,
        }
        return action

    def action_eam_receive(self):
        return self._eam_open_transaction("in")

    def action_eam_assign(self):
        return self._eam_open_transaction("out")

    def action_eam_transfer(self):
        return self._eam_open_transaction(
            "transfer",
            {"default_src_location_note": self.location_note},
        )

    def action_eam_recall(self):
        return self._eam_open_transaction(
            "recall",
            {"default_src_location_note": self.location_note},
        )

    def action_eam_dispose(self):
        return self._eam_open_transaction("disposal")

    def action_eam_report_failure(self):
        """Báo hỏng → tạo Maintenance Request / Work Order."""
        self.ensure_one()
        if self.eam_state in ("disposed", "draft"):
            raise UserError(
                self.env._("Không báo hỏng tài sản ở trạng thái '%s'.") % self.eam_state
            )
        Request = self.env["maintenance.request"]
        team = self.maintenance_team_id
        if not team:
            team = self.env["maintenance.team"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            ) or self.env["maintenance.team"].search([], limit=1)
        if not team:
            raise UserError(self.env._("Chưa cấu hình Đội bảo trì (Maintenance Team)."))
        request = Request.create(
            {
                "name": self.env._("Báo hỏng: %s") % (self.asset_code or self.name),
                "equipment_id": self.id,
                "maintenance_type": "corrective",
                "maintenance_team_id": team.id,
                "user_id": self.technician_user_id.id or self.env.user.id,
                "company_id": self.company_id.id,
                "priority": "2",
                "failure_symptom": self.env._("Báo hỏng từ hồ sơ tài sản %s")
                % (self.asset_code or self.name),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Work Order"),
            "res_model": "maintenance.request",
            "res_id": request.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_eam_create_preventive(self):
        """Tạo phiếu bảo trì phòng ngừa."""
        self.ensure_one()
        team = self.maintenance_team_id
        if not team:
            team = self.env["maintenance.team"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            ) or self.env["maintenance.team"].search([], limit=1)
        if not team:
            raise UserError(self.env._("Chưa cấu hình Đội bảo trì (Maintenance Team)."))
        request = self.env["maintenance.request"].create(
            {
                "name": self.env._("BT định kỳ: %s") % (self.asset_code or self.name),
                "equipment_id": self.id,
                "maintenance_type": "preventive",
                "maintenance_team_id": team.id,
                "user_id": self.technician_user_id.id or False,
                "company_id": self.company_id.id,
                "priority": "1",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Work Order"),
            "res_model": "maintenance.request",
            "res_id": request.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_transactions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Phiếu liên quan"),
            "res_model": "eam.transaction",
            "view_mode": "list,form",
            "domain": [("line_ids.asset_id", "=", self.id)],
            "context": {"default_line_ids": [(0, 0, {"asset_id": self.id})]},
        }

    def action_open_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Lịch sử tài sản"),
            "res_model": "eam.asset.history",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"default_asset_id": self.id},
        }

    def action_generate_qr(self):
        for equipment in self:
            if not equipment.asset_code:
                identity = equipment._eam_prepare_identity_vals({})
                equipment.write(identity)
            elif not equipment.qr_code:
                equipment.qr_code = equipment.asset_code
            if not equipment.barcode:
                equipment.barcode = equipment.asset_code
        return True

    def action_print_label(self):
        return self.env.ref("lug_eam.action_report_eam_asset_label").report_action(self)

    def action_open_maintenance_requests(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "maintenance.hr_equipment_request_action_from_equipment"
        )
        action["domain"] = [("equipment_id", "=", self.id)]
        action["context"] = {
            "default_equipment_id": self.id,
            "default_company_id": self.company_id.id,
            "default_maintenance_team_id": self.maintenance_team_id.id,
            "search_default_equipment_id": self.id,
        }
        return action
