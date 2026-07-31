# -*- coding: utf-8 -*-

from odoo import api, fields, models


class EamAssetHistory(models.Model):
    _name = "eam.asset.history"
    _description = "Lịch sử / Timeline tài sản"
    _order = "event_date desc, id desc"

    asset_id = fields.Many2one(
        "maintenance.equipment",
        string="Tài sản",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="asset_id.company_id",
        store=True,
        index=True,
    )
    event_date = fields.Datetime(
        string="Thời điểm",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    event_type = fields.Selection(
        [
            ("create", "Tạo mới"),
            ("in", "Nhập kho"),
            ("out", "Cấp phát"),
            ("transfer", "Điều chuyển"),
            ("recall", "Thu hồi"),
            ("disposal", "Thanh lý"),
            ("maintenance", "Bảo trì"),
            ("state", "Đổi trạng thái"),
            ("note", "Ghi chú"),
        ],
        string="Loại sự kiện",
        required=True,
        index=True,
    )
    name = fields.Char(string="Tóm tắt", required=True)
    from_state = fields.Char(string="Từ trạng thái")
    to_state = fields.Char(string="Sang trạng thái")
    location_note = fields.Char(string="Vị trí")
    employee_id = fields.Many2one("hr.employee", string="Nhân viên liên quan")
    department_id = fields.Many2one("hr.department", string="Phòng ban")
    transaction_id = fields.Many2one("eam.transaction", string="Phiếu", ondelete="set null")
    user_id = fields.Many2one(
        "res.users",
        string="Người thực hiện",
        default=lambda self: self.env.user,
    )
    note = fields.Text(string="Chi tiết")

    @api.model
    def log_event(self, asset, event_type, name, **kwargs):
        vals = {
            "asset_id": asset.id,
            "event_type": event_type,
            "name": name,
            "from_state": kwargs.get("from_state"),
            "to_state": kwargs.get("to_state"),
            "location_note": kwargs.get("location_note"),
            "employee_id": kwargs.get("employee_id") or False,
            "department_id": kwargs.get("department_id") or False,
            "transaction_id": kwargs.get("transaction_id") or False,
            "note": kwargs.get("note"),
            "user_id": kwargs.get("user_id") or self.env.user.id,
            "event_date": kwargs.get("event_date") or fields.Datetime.now(),
        }
        return self.create(vals)
