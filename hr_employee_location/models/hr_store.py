# -*- coding: utf-8 -*-
import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
except ImportError:
    Nominatim = None
    GeocoderTimedOut = None
    GeocoderUnavailable = None


class HrStore(models.Model):
    _inherit = "hr.store"

    address = fields.Char(
        string="Địa chỉ",
        related="street",
        readonly=False,
        store=True,
    )
    latitude = fields.Float(
        string="Vĩ độ",
        digits=(10, 7),
        help="Tọa độ vĩ độ địa lý của cửa hàng (do geopy tự động tính hoặc admin nhập tay).",
    )
    longitude = fields.Float(
        string="Kinh độ",
        digits=(10, 7),
        help="Tọa độ kinh độ địa lý của cửa hàng (do geopy tự động tính hoặc admin nhập tay).",
    )
    geocode_status = fields.Selection(
        [
            ("draft", "Chưa định vị"),
            ("success", "Định vị thành công"),
            ("failed", "Định vị thất bại"),
            ("manual", "Nhập thủ công"),
        ],
        string="Trạng thái định vị",
        default="draft",
        help="Nguồn gốc tọa độ cửa hàng: geopy tự động, nhập tay, hay chưa tính.",
    )
    last_geocode_time = fields.Datetime(
        string="Thời gian định vị",
        readonly=True,
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "hr_employee_store_network_rel",
        "store_id",
        "employee_id",
        string="Nhân viên trực thuộc",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if "latitude" in vals or "longitude" in vals:
                if vals.get("latitude") or vals.get("longitude"):
                    record.geocode_status = "manual"
        return records

    def write(self, vals):
        if "latitude" in vals or "longitude" in vals:
            if "geocode_status" not in vals:
                vals["geocode_status"] = "manual"
        return super().write(vals)

    def _auto_geocode_safely(self):
        """Hàm helper chạy ngầm geocode mà không throw UserError nếu lỗi kết nối."""
        self.ensure_one()
        try:
            self.action_geocode_address(raise_if_error=False)
        except Exception as e:
            _logger.warning("Lỗi tự động geocode cho cửa hàng %s: %s", self.name or self.id, e)

    def _sanitize_address_for_nominatim(self, address_raw):
        """
        Làm sạch chuỗi địa chỉ để OpenStreetMap Nominatim dễ tìm kiếm:
        Lược bỏ các cụm từ như: Tầng 1, Tầng 2, Gian hàng..., Lô A..., TTTM...
        """
        if not address_raw:
            return ""
        cleaned = address_raw.strip()
        # Loại bỏ các tiền tố tầng / lầu / gian hàng
        cleaned = re.sub(r"(?i)\b(tầng|lầu|gian hàng|kiosk|lô|shop)\s*[\w\d\.-]+,?", "", cleaned)
        cleaned = re.sub(r"(?i)\bTTTM\s*[^,]+,?", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(", ").strip()
        return cleaned

    def action_geocode_address(self, raise_if_error=True):
        """
        Tính toán tọa độ kinh độ và vĩ độ qua thư viện geopy (Nominatim).
        Hỗ trợ fallback làm sạch địa chỉ nếu lần tìm đầu tiên không khớp.
        """
        self.ensure_one()
        if not Nominatim:
            msg = _("Thư viện 'geopy' chưa được cài đặt trong môi trường Python của Odoo.")
            if raise_if_error:
                raise UserError(msg)
            _logger.error(msg)
            return False

        address = (self.address or self.street or "").strip()
        if not address:
            if raise_if_error:
                raise UserError(_("Vui lòng nhập địa chỉ trước khi định vị tọa độ."))
            return False

        try:
            geolocator = Nominatim(user_agent="khan_odoo_store_geocoder", timeout=10)
            
            # Thử lần 1: Nguyên văn địa chỉ
            loc = geolocator.geocode(address)
            
            # Thử lần 2: Fallback sau khi làm sạch tiền tố tầng / TTTM
            if not loc:
                sanitized = self._sanitize_address_for_nominatim(address)
                if sanitized and sanitized != address:
                    loc = geolocator.geocode(sanitized)
                    
            # Thử lần 3: Nếu vẫn không ra, thử lấy tên Tỉnh/Thành phố hoặc Quận
            if not loc and hasattr(self, 'province') and self.province:
                loc = geolocator.geocode(f"{self.province}, Việt Nam")

            if loc:
                self.write({
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "geocode_status": "success",
                    "last_geocode_time": fields.Datetime.now(),
                })
                return True
            else:
                self.write({"geocode_status": "failed"})
                if raise_if_error:
                    raise UserError(
                        _("Không thể tìm thấy tọa độ phù hợp cho địa chỉ này trên OpenStreetMap. "
                          "Vui lòng kiểm tra lại địa chỉ hoặc nhập tay tọa độ Vĩ độ / Kinh độ.")
                    )
                return False

        except (GeocoderTimedOut, GeocoderUnavailable) as exc:
            self.write({"geocode_status": "failed"})
            msg = _("Dịch vụ định vị OpenStreetMap bị quá thời gian hoặc không phản hồi: %s") % str(exc)
            _logger.warning(msg)
            if raise_if_error:
                raise UserError(msg)
            return False
        except Exception as e:
            self.write({"geocode_status": "failed"})
            _logger.exception("Geocoding exception: %s", e)
            if raise_if_error:
                raise UserError(_("Lỗi trong quá trình định vị: %s") % str(e))
            return False
