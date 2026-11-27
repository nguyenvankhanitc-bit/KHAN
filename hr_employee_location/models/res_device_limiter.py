# -*- coding: utf-8 -*-
import logging
import odoo
from odoo import api, fields, models
from odoo.http import STORED_SESSION_BYTES, root

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    max_device_count = fields.Integer(
        string="Số thiết bị tối đa",
        default=2,
        help="Số lượng thiết bị tối đa được phép đăng nhập đồng thời (Mặc định: 2, gồm 1 PC và 1 Điện thoại). Đặt 0 để không giới hạn.",
    )
    exempt_device_limit = fields.Boolean(
        string="Miễn giới hạn thiết bị đăng nhập",
        default=False,
        help="Nếu bật, người dùng này không bị giới hạn số lượng thiết bị đăng nhập và các phiên cũ không bị tự động thu hồi.",
    )


class ResDeviceLog(models.Model):
    _inherit = "res.device.log"

    @api.model
    def _update_device(self, request):
        super()._update_device(request)
        try:
            self._enforce_device_limits(request)
        except Exception:
            _logger.exception("Lỗi khi kiểm tra và giới hạn phiên thiết bị đăng nhập")

    @api.model
    def _enforce_device_limits(self, request):
        if not request or not getattr(request, "session", None):
            return

        user_id = request.session.uid
        if not user_id or user_id == odoo.SUPERUSER_ID:
            return

        sid = request.session.sid or ""
        current_sid = sid[:STORED_SESSION_BYTES]
        if not current_sid or len(current_sid) != STORED_SESSION_BYTES:
            return

        # Tránh truy vấn lại nhiều lần trên cùng 1 phiên đã được kiểm tra hợp lệ
        if request.session.get("_device_limits_enforced") == current_sid:
            return

        # Kiểm tra người dùng có thuộc diện miễn giới hạn thiết bị không
        user = self.env["res.users"].sudo().browse(user_id)
        if not user.exists() or user.exempt_device_limit:
            request.session["_device_limits_enforced"] = current_sid
            return

        max_devices = user.max_device_count
        if max_devices is None:
            max_devices = 2
        if max_devices <= 0:
            request.session["_device_limits_enforced"] = current_sid
            return

        # Xác định loại thiết bị của phiên hiện tại (computer hoặc mobile)
        ua = getattr(request.httprequest, "user_agent", None)
        platform = ua.platform if ua else ""
        current_device_type = "mobile" if self._is_mobile(platform) else "computer"

        # Lấy danh sách các session_identifier chưa bị thu hồi của user này
        self.env.cr.execute(
            """
            SELECT session_identifier, device_type, MAX(last_activity) AS last_act
            FROM res_device_log
            WHERE user_id = %(user_id)s AND (revoked IS NOT TRUE)
            GROUP BY session_identifier, device_type
            ORDER BY last_act DESC
            """,
            {"user_id": user_id},
        )
        rows = self.env.cr.dictfetchall()
        if not rows:
            request.session["_device_limits_enforced"] = current_sid
            return

        # Dọn dẹp các session không còn file trên ổ đĩa (do đã logout hoặc hết hạn tự nhiên)
        active_sids = [r["session_identifier"] for r in rows if r.get("session_identifier")]
        missing_sids = root.session_store.get_missing_session_identifiers(set(active_sids))
        if missing_sids:
            self.sudo().search([
                ("user_id", "=", user_id),
                ("session_identifier", "in", list(missing_sids)),
                ("revoked", "!=", True),
            ]).write({"revoked": True})
            rows = [r for r in rows if r["session_identifier"] not in missing_sids]

        # Phân loại các session đang hoạt động trên hệ thống (loại trừ phiên hiện tại)
        computer_sids = [
            r["session_identifier"]
            for r in rows
            if r.get("device_type") == "computer" and r["session_identifier"] != current_sid
        ]
        mobile_sids = [
            r["session_identifier"]
            for r in rows
            if r.get("device_type") == "mobile" and r["session_identifier"] != current_sid
        ]

        to_revoke = []

        if max_devices == 1:
            # Tối đa 1 thiết bị duy nhất: thu hồi toàn bộ các phiên khác (bất kể loại thiết bị)
            to_revoke.extend([r["session_identifier"] for r in rows if r["session_identifier"] != current_sid])

        elif max_devices == 2:
            # Tối đa 2 thiết bị chuẩn: 1 Máy tính + 1 Điện thoại
            if current_device_type == "computer":
                to_revoke.extend(computer_sids)
            elif len(computer_sids) > 1:
                to_revoke.extend(computer_sids[1:])

            if current_device_type == "mobile":
                to_revoke.extend(mobile_sids)
            elif len(mobile_sids) > 1:
                to_revoke.extend(mobile_sids[1:])

        else:
            # Trường hợp cấu hình > 2 thiết bị: thu hồi các phiên cũ nhất vượt quá hạn mức
            other_sids = [r["session_identifier"] for r in rows if r["session_identifier"] != current_sid]
            allowed_others = max(0, max_devices - 1)
            if len(other_sids) > allowed_others:
                to_revoke.extend(other_sids[allowed_others:])

        # Thu hồi các session vi phạm vượt quá giới hạn
        if to_revoke:
            # Lọc chỉ những session identifier hợp lệ và không chứa session hiện tại
            to_revoke = list(set(s for s in to_revoke if s and s != current_sid and len(s) == STORED_SESSION_BYTES))
            if to_revoke:
                # 1. Xóa file session vật lý trên ổ đĩa server
                root.session_store.delete_from_identifiers(to_revoke)
                # 2. Đánh dấu revoked = True trong cơ sở dữ liệu res_device_log
                self.sudo().search([
                    ("user_id", "=", user_id),
                    ("session_identifier", "in", to_revoke),
                ]).write({"revoked": True})
                _logger.info(
                    "Đã thu hồi %d phiên cũ (%s) của user_id=%d để đảm bảo giới hạn tối đa %d thiết bị. Phiên hiện tại: %s (%s)",
                    len(to_revoke),
                    ", ".join(to_revoke),
                    user_id,
                    max_devices,
                    current_sid,
                    current_device_type,
                )

        request.session["_device_limits_enforced"] = current_sid
        request.session.is_dirty = True
