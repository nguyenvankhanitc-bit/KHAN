# -*- coding: utf-8 -*-
import ipaddress
import logging
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _client_ip():
    """IP công khai của người dùng. Sau reverse proxy (nginx) remote_addr là IP nội bộ:
    lấy IP cuối trong X-Forwarded-For (do proxy của mình thêm vào, không giả mạo được)."""
    hr = request.httprequest
    ip = (hr.remote_addr or "").strip()
    try:
        addr = ipaddress.ip_address(ip)
        private = addr.is_private or addr.is_loopback
    except ValueError:
        private = True
    if private:
        xff = [x.strip() for x in (hr.headers.get("X-Forwarded-For") or "").split(",") if x.strip()]
        if xff:
            ip = xff[-1]
        elif hr.headers.get("X-Real-IP"):
            ip = hr.headers["X-Real-IP"].strip()
    return ip


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

        # IP truy cập -> cửa hàng có IP WAN trùng (đang dùng mạng / wifi cửa hàng)
        ip = _client_ip()
        if ip:
            store = request.env["hr.store"].sudo()._store_for_ip(ip, prefer=employee.sudo().store_ids)
            vals.update({"last_ip": ip, "last_ip_time": fields.Datetime.now(), "ip_store_id": store.id or False})

        # Dọn dẹp mã DEV-* tự sinh cũ nếu còn lưu trong hồ sơ nhân viên
        if employee.device_identifier and employee.device_identifier.startswith("DEV-"):
            vals["device_identifier"] = False

        if vals:
            employee.sudo().write(vals)

        # Tự Check in / Check out Báo cáo CV ASM theo mạng cửa hàng (module store_checklist, nếu có cài)
        if ip and "store.asm.work.report" in request.env:
            try:
                with request.env.cr.savepoint():
                    request.env["store.asm.work.report"].sudo()._presence_ping(
                        user, ip, latitude, longitude, accuracy)
            except Exception:
                _logger.exception("Tự Check in/out ASM lỗi (user %s, IP %s)", user.login, ip)

        _logger.debug("Đã cập nhật vị trí & thiết bị nhân viên %s: (%s, %s)", employee.name, vals.get("device_name"), vals.get("device_type"))
        return {
            "status": "ok",
            "employee_id": employee.id,
            "device_name": employee.device_name,
            "device_type": employee.device_type,
            "last_location_time": fields.Datetime.to_string(employee.last_location_time) if employee.last_location_time else False,
        }
