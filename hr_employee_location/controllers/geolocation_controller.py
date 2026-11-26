# -*- coding: utf-8 -*-
import logging
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GeolocationController(http.Controller):

    @http.route("/hr_employee_location/update_position", type="json", auth="user", methods=["POST"])
    def update_position(self, latitude, longitude, accuracy=None):
        """
        Nhận tọa độ GPS từ browser webclient của nhân viên và cập nhật vào hr.employee.
        Yêu cầu user đã đăng nhập.
        """
        user = request.env.user
        employee = user.employee_id
        if not employee:
            # Fallback tìm employee theo user_id nếu chưa liên kết trực tiếp
            employee = request.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)

        if not employee:
            _logger.info("User %s không liên kết với hồ sơ nhân viên nào, bỏ qua lưu GPS.", user.login)
            return {"status": "no_employee"}

        try:
            lat = float(latitude)
            lng = float(longitude)
        except (ValueError, TypeError):
            return {"status": "invalid_coordinates"}

        # Cập nhật bằng sudo để nhân viên tự cập nhật được vị trí của mình
        employee.sudo().write({
            "last_latitude": lat,
            "last_longitude": lng,
            "last_location_time": fields.Datetime.now(),
        })

        _logger.debug("Đã cập nhật vị trí GPS nhân viên %s: (%f, %f)", employee.name, lat, lng)
        return {
            "status": "ok",
            "employee_id": employee.id,
            "last_location_time": fields.Datetime.to_string(employee.last_location_time),
        }
