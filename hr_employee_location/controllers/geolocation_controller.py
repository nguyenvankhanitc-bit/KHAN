# -*- coding: utf-8 -*-
import logging
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GeolocationController(http.Controller):

    @http.route("/hr_employee_location/update_position", type="jsonrpc", auth="user", methods=["POST"])
    def update_position(self, latitude=None, longitude=None, accuracy=None, device_name=None, device_type=None, **kwargs):
        """
        Nhận tọa độ GPS và thông tin thiết bị từ browser webclient của nhân viên và cập nhật vào hr.employee.
        Yêu cầu user đã đăng nhập.
        """
        user = request.env.user
        employee = user.employee_id
        if not employee:
            # Fallback tìm employee theo user_id nếu chưa liên kết trực tiếp
            employee = request.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)

        if not employee:
            _logger.info("User %s không liên kết với hồ sơ nhân viên nào, bỏ qua lưu vị trí/thiết bị.", user.login)
            return {"status": "no_employee"}

        vals = {}
        if latitude is not None and longitude is not None:
            try:
                vals["last_latitude"] = float(latitude)
                vals["last_longitude"] = float(longitude)
                vals["last_location_time"] = fields.Datetime.now()
            except (ValueError, TypeError):
                pass

        if device_name:
            vals["device_name"] = str(device_name)[:100]
        if device_type in ("computer", "mobile", "tablet"):
            vals["device_type"] = device_type

        # Fallback nhận diện thiết bị qua HTTP User-Agent nếu client chưa gửi đủ
        if not vals.get("device_name") or not vals.get("device_type"):
            ua = request.httprequest.user_agent
            if ua:
                platform = ua.platform or "Thiết bị"
                browser = ua.browser or "Web"
                if not vals.get("device_name"):
                    vals["device_name"] = f"{platform.capitalize()} ({browser.capitalize()})"
                if not vals.get("device_type"):
                    vals["device_type"] = "mobile" if platform.lower() in ["android", "iphone", "ipad"] else "computer"

        # Dọn dẹp mã DEV-* tự sinh cũ nếu còn lưu trong hồ sơ nhân viên
        if employee.device_identifier and employee.device_identifier.startswith("DEV-"):
            vals["device_identifier"] = False

        if vals:
            employee.sudo().write(vals)

        _logger.debug("Đã cập nhật vị trí & thiết bị nhân viên %s: (%s, %s)", employee.name, vals.get("device_name"), vals.get("device_type"))
        return {
            "status": "ok",
            "employee_id": employee.id,
            "device_name": employee.device_name,
            "device_type": employee.device_type,
            "last_location_time": fields.Datetime.to_string(employee.last_location_time) if employee.last_location_time else False,
        }
