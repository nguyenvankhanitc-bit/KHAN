# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models
from odoo.exceptions import UserError

# Tiền tố mặc định khi loại chưa cấu hình code_prefix (bộ đếm độc lập từng nhóm).
IT_ASSET_CODE_PREFIX = {
    "physical": "SRV",
    "virtual": "VM",
    "cloud": "CLD",
    "network": "NET",
    "security": "SEC",
    "software": "SW",
}


class PhanHeItAssetType(models.Model):
    _name = "phan.he.it.asset.type"
    _description = "Loại tài sản IT"
    _order = "sequence, name"

    name = fields.Char(string="Tên loại", required=True)
    code = fields.Char(string="Mã loại", required=True)
    code_prefix = fields.Char(
        string="Tiền tố mã tài sản",
        help="VD: SRV, NET, SEC, CLD — dùng sinh mã SRV-0001. Mỗi tiền tố có bộ đếm riêng.",
    )
    sequence = fields.Integer(default=10)
    color = fields.Char(string="Màu", default="#64748b")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "unique(code)",
        "Mã loại tài sản phải duy nhất.",
    )

    def get_code_prefix(self):
        self.ensure_one()
        raw = (self.code_prefix or "").strip().upper()
        if raw:
            return raw
        return IT_ASSET_CODE_PREFIX.get(self.code) or (self.code or "AST").upper()[:3]


class PhanHeItAsset(models.Model):
    _name = "phan.he.it.asset"
    _description = "Tài sản Máy chủ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code, id"
    _rec_names_search = ["code", "name", "model_name", "serial_number"]

    code = fields.Char(
        string="Mã tài sản",
        required=True,
        copy=False,
        tracking=True,
        default="New",
    )
    name = fields.Char(string="Tên tài sản", required=True, tracking=True)
    asset_type_id = fields.Many2one(
        "phan.he.it.asset.type",
        string="Loại tài sản",
        required=True,
        tracking=True,
        ondelete="restrict",
        index=True,
    )
    asset_type_code = fields.Char(related="asset_type_id.code", store=True, index=True)
    manufacturer = fields.Char(string="Hãng sản xuất", tracking=True)
    model_name = fields.Char(string="Model", tracking=True)
    serial_number = fields.Char(string="Serial Number", tracking=True)
    location = fields.Char(string="Vị trí lắp đặt", tracking=True)
    mien_id = fields.Many2one("phan.he.mien", string="Khu vực / Miền", tracking=True, index=True)
    store_id = fields.Many2one("phan.he.store", string="Đơn vị / Cửa hàng", tracking=True, index=True)
    date_start = fields.Date(string="Ngày mua / bắt đầu sử dụng", tracking=True)
    provider_id = fields.Many2one("phan.he.provider", string="Nhà cung cấp", tracking=True, index=True)
    responsible_id = fields.Many2one("hr.employee", string="Người phụ trách", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("active", "Đang sử dụng"),
            ("suspended", "Ngừng sử dụng tạm"),
            ("retired", "Lưu trữ / Thanh lý"),
        ],
        string="Trạng thái",
        default="active",
        required=True,
        tracking=True,
    )
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        default=lambda self: self.env.company,
        index=True,
    )

    # --- Máy chủ vật lý ---
    cpu_info = fields.Char(string="CPU")
    ram_gb = fields.Float(string="RAM (GB)")
    storage_gb = fields.Float(string="Dung lượng lưu trữ (GB)")
    raid_info = fields.Char(string="RAID")
    nic_info = fields.Char(string="Card mạng")
    hypervisor = fields.Char(string="vCPUs")
    warranty_end = fields.Date(string="Hết hạn bảo hành")

    # --- Máy chủ ảo ---
    vm_name = fields.Char(string="Tên VM")
    host_asset_id = fields.Many2one(
        "phan.he.it.asset",
        string="Tên máy chủ",
        domain="[('asset_type_code', '=', 'physical'), ('active', '=', True)]",
        ondelete="restrict",
        tracking=True,
        help="Chọn máy chủ vật lý chứa VM (vd: Dell R530, Dell R650).",
    )
    host_label = fields.Char(
        string="Tên máy chủ",
        compute="_compute_host_label",
        store=True,
    )
    ip_address = fields.Char(string="Địa chỉ IP")
    ip_wan = fields.Char(string="IP WAN")
    login_user = fields.Char(string="User")
    login_password = fields.Char(string="Pass")
    # VM: storage_gb = SSD; hdd_gb = HDD (riêng)
    hdd_gb = fields.Float(string="Dung lượng HDD (GB)")

    # --- Cloud ---
    cloud_provider = fields.Char(string="Nhà cung cấp cloud")
    cloud_account = fields.Char(string="Tài khoản / Subscription")
    cloud_region = fields.Char(string="Region")
    cloud_service_type = fields.Char(string="Loại dịch vụ cloud")
    cloud_billing_cycle = fields.Selection(
        [
            ("monthly", "Hàng tháng"),
            ("yearly", "Hàng năm"),
            ("other", "Khác"),
        ],
        string="Chu kỳ thanh toán cloud",
    )
    cloud_budget = fields.Monetary(string="Ngân sách dự kiến", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self.env.ref("base.VND", raise_if_not_found=False)
        or self.env.company.currency_id,
    )

    # --- Mạng & bảo mật ---
    admin_url = fields.Char(string="Địa chỉ quản trị")
    license_end = fields.Date(string="Hết hạn license")
    firmware_version = fields.Char(string="Phiên bản firmware")

    cost_ids = fields.One2many("phan.he.it.cost", "asset_id", string="Khoản chi phí")
    cost_count = fields.Integer(compute="_compute_counts")
    ticket_ids = fields.One2many("phan.he.it.ticket", "asset_id", string="Phiếu bảo trì / sự cố")
    ticket_count = fields.Integer(compute="_compute_counts")

    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "Mã tài sản phải duy nhất trong cùng công ty.",
    )

    def _compute_counts(self):
        for rec in self:
            rec.cost_count = len(rec.cost_ids)
            rec.ticket_count = len(rec.ticket_ids)

    @api.depends(
        "host_asset_id",
        "host_asset_id.name",
        "host_asset_id.manufacturer",
        "host_asset_id.model_name",
    )
    def _compute_host_label(self):
        for rec in self:
            rec.host_label = rec.host_asset_id._format_host_label() if rec.host_asset_id else ""

    def _format_host_label(self):
        """Nhãn chọn máy chủ vật lý: Dell R530 / Dell R650."""
        self.ensure_one()
        model = (self.model_name or "").replace("PowerEdge ", "").strip()
        manufacturer = (self.manufacturer or "").strip()
        if manufacturer and model:
            return "%s %s" % (manufacturer, model)
        if model:
            return model
        return self.name or self.code or ""

    @api.depends("name", "code", "manufacturer", "model_name", "asset_type_code")
    def _compute_display_name(self):
        for rec in self:
            if rec.asset_type_code == "physical":
                rec.display_name = rec._format_host_label()
            else:
                rec.display_name = rec.name or rec.code or ""

    @api.onchange("host_asset_id")
    def _onchange_host_asset_id(self):
        if self.asset_type_code != "virtual" or not self.host_asset_id:
            return
        host = self.host_asset_id
        if not self.hypervisor and host.hypervisor:
            self.hypervisor = host.hypervisor
        if not self.name:
            self.name = "VM trên %s" % host._format_host_label()

    @api.constrains("host_asset_id", "asset_type_id")
    def _check_virtual_host(self):
        for rec in self:
            if rec.asset_type_code == "virtual" and not rec.host_asset_id:
                raise UserError("Máy chủ ảo phải chọn Tên máy chủ từ danh sách máy chủ vật lý.")
            if rec.host_asset_id and rec.host_asset_id.asset_type_code != "physical":
                raise UserError("Tên máy chủ phải là máy chủ vật lý.")
            if rec.host_asset_id and rec.host_asset_id == rec:
                raise UserError("Máy chủ ảo không thể trỏ về chính nó.")

    @api.model
    def next_asset_code(self, asset_type_id):
        """Sinh mã tiếp theo theo tiền tố loại: SRV-0001, NET-0002… (bộ đếm độc lập)."""
        if not asset_type_id:
            return False
        asset_type = self.env["phan.he.it.asset.type"].browse(int(asset_type_id))
        if not asset_type.exists():
            return False
        prefix = asset_type.get_code_prefix()
        pattern = re.compile(r"^%s-(\d+)$" % re.escape(prefix), re.IGNORECASE)
        # Lấy mọi mã cùng tiền tố (kể cả đã archive) để không trùng số.
        codes = self.with_context(active_test=False).search([
            ("code", "=ilike", "%s-%%" % prefix),
        ]).mapped("code")
        max_n = 0
        for code in codes:
            match = pattern.match((code or "").strip())
            if match:
                max_n = max(max_n, int(match.group(1)))
        return "%s-%04d" % (prefix, max_n + 1)

    @api.onchange("asset_type_id")
    def _onchange_asset_type_id_code(self):
        if self.asset_type_id and (
            not self.code or self.code in ("New", "/") or self._origin.id is False
        ):
            # Chỉ tự điền khi tạo mới hoặc mã còn placeholder.
            if not self._origin.id:
                self.code = self.next_asset_code(self.asset_type_id.id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            code = (vals.get("code") or "").strip()
            if (not code or code in ("New", "/")) and vals.get("asset_type_id"):
                vals["code"] = self.next_asset_code(vals["asset_type_id"])
        return super().create(vals_list)

    def unlink(self):
        blocked = self.filtered(lambda a: a.cost_ids or a.ticket_ids)
        if blocked:
            raise UserError(
                "Không xóa cứng tài sản đã có chi phí / bảo trì / sự cố.\n"
                "Hãy chuyển trạng thái Lưu trữ hoặc bỏ kích hoạt."
            )
        return super().unlink()

    def action_retire(self):
        self.write({"state": "retired", "active": False})

    def action_set_active(self):
        self.write({"state": "active", "active": True})

    def action_open_costs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Chi phí — %s" % self.code,
            "res_model": "phan.he.it.cost",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"default_asset_id": self.id},
        }

    def action_open_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Bảo trì / sự cố — %s" % self.code,
            "res_model": "phan.he.it.ticket",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"default_asset_id": self.id},
        }

    @api.model
    def _seed_reference_assets(self):
        """Seed idempotent 4 tài sản tham chiếu (không điền SN/IP/giá/hạn)."""
        Type = self.env["phan.he.it.asset.type"].sudo()
        type_map = {t.code: t for t in Type.search([])}
        rows = [
            {
                "code": "SRV-001",
                "name": "Dell R530",
                "type_code": "physical",
                "manufacturer": "Dell",
                "model_name": "PowerEdge R530",
            },
            {
                "code": "SRV-002",
                "name": "Dell R650",
                "type_code": "physical",
                "manufacturer": "Dell",
                "model_name": "PowerEdge R650",
            },
            {
                "code": "NET-001",
                "name": "Firewall 01",
                "type_code": "network",
                "manufacturer": "Sophos",
                "model_name": "XG 310",
            },
            {
                "code": "NET-002",
                "name": "Thiết bị mạng 02",
                "type_code": "network",
                "manufacturer": False,
                "model_name": "SWC9100",
            },
        ]
        Asset = self.sudo()
        for row in rows:
            atype = type_map.get(row["type_code"])
            if not atype:
                continue
            existing = Asset.search([("code", "=", row["code"])], limit=1)
            vals = {
                "name": row["name"],
                "asset_type_id": atype.id,
                "manufacturer": row["manufacturer"] or False,
                "model_name": row["model_name"],
                "state": "active",
            }
            if existing:
                existing.write(vals)
            else:
                Asset.create({"code": row["code"], **vals})
