# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    last_latitude = fields.Float(
        string="Vĩ độ gần nhất",
        digits=(10, 7),
        readonly=True,
        help="Vĩ độ GPS được trích xuất tự động khi nhân viên thao tác trên webclient.",
    )
    last_longitude = fields.Float(
        string="Kinh độ gần nhất",
        digits=(10, 7),
        readonly=True,
        help="Kinh độ GPS được trích xuất tự động khi nhân viên thao tác trên webclient.",
    )
    last_location_time = fields.Datetime(
        string="Thời gian ghi nhận GPS",
        readonly=True,
        help="Thời điểm cuối cùng tọa độ GPS được gửi về từ trình duyệt.",
    )
    store_ids = fields.Many2many(
        "hr.store",
        "hr_employee_store_network_rel",
        "employee_id",
        "store_id",
        string="Cửa hàng trực thuộc",
        help="Danh sách các cửa hàng mà nhân viên phụ trách hoặc làm việc.",
    )
    device_identifier = fields.Char(
        string="Mã thiết bị",
        readonly=True,
        help="Mã định danh duy nhất của thiết bị nhân viên sử dụng để truy cập hệ thống.",
    )
    device_name = fields.Char(
        string="Tên thiết bị",
        readonly=True,
        help="Tên hệ điều hành và trình duyệt của thiết bị (ví dụ: Windows PC (Chrome), iPhone (Safari)).",
    )
    device_type = fields.Selection(
        [
            ("computer", "Máy tính"),
            ("mobile", "Điện thoại"),
            ("tablet", "Máy tính bảng"),
        ],
        string="Loại thiết bị",
        readonly=True,
        default="computer",
        help="Phân loại thiết bị truy cập: Máy tính, Điện thoại hoặc Máy tính bảng.",
    )
    max_device_count = fields.Integer(
        string="Số thiết bị tối đa",
        related="user_id.max_device_count",
        readonly=True,
        help="Số thiết bị tối đa được phép đăng nhập đồng thời được cấu hình cho tài khoản người dùng liên kết.",
    )
    gps_status = fields.Selection(
        [
            ("active", "Đang hoạt động (GPS mới)"),
            ("stale", "Tín hiệu cũ (>1h)"),
            ("none", "Chưa có GPS"),
        ],
        string="Trạng thái GPS",
        compute="_compute_gps_status",
        store=False,
    )

    @api.depends("last_location_time", "last_latitude", "last_longitude")
    def _compute_gps_status(self):
        now = fields.Datetime.now()
        for emp in self:
            if not emp.last_location_time or not emp.last_latitude or not emp.last_longitude:
                emp.gps_status = "none"
            elif emp.last_location_time >= (now - timedelta(hours=1)):
                emp.gps_status = "active"
            else:
                emp.gps_status = "stale"


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    last_latitude = fields.Float(related="employee_id.last_latitude", readonly=True)
    last_longitude = fields.Float(related="employee_id.last_longitude", readonly=True)
    last_location_time = fields.Datetime(related="employee_id.last_location_time", readonly=True)
    store_ids = fields.Many2many(related="employee_id.store_ids", readonly=True)
    gps_status = fields.Selection(related="employee_id.gps_status", readonly=True)
    device_identifier = fields.Char(related="employee_id.device_identifier", readonly=True)
    device_name = fields.Char(related="employee_id.device_name", readonly=True)
    device_type = fields.Selection(related="employee_id.device_type", readonly=True)
    max_device_count = fields.Integer(related="employee_id.max_device_count", readonly=True)
