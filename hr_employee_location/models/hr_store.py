# -*- coding: utf-8 -*-
import logging
import re
import socket
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
            ("ip", "Ước tính theo IP"),
        ],
        string="Trạng thái định vị",
        default="draft",
        help="Nguồn gốc tọa độ cửa hàng: geopy tự động, nhập tay, hay chưa tính.",
    )
    last_geocode_time = fields.Datetime(
        string="Thời gian định vị",
        readonly=True,
    )
    ddns_domain = fields.Char(
        string="Tên miền DDNS",
        help="Tên miền DDNS của mạng cửa hàng, ví dụ: sangtamlugkdv.ddns.net",
    )
    wan_ip = fields.Char(
        string="IP WAN",
        readonly=True,
        help="Địa chỉ IP WAN hiện tại của cửa hàng (cập nhật từ Tên miền DDNS).",
    )
    last_ip_sync = fields.Datetime(
        string="Cập nhật IP lúc",
        readonly=True,
    )
    ip_location = fields.Char(
        string="Khu vực theo IP",
        readonly=True,
        help="Tỉnh/thành và nhà mạng ước tính từ IP WAN (chỉ gần đúng, không phải địa chỉ cửa hàng).",
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
        records.filtered("ddns_domain")._sync_wan_ip()
        to_geocode = self.browse()
        for record, vals in zip(records, vals_list):
            if "latitude" in vals or "longitude" in vals:
                if vals.get("latitude") or vals.get("longitude"):
                    record.geocode_status = "manual"
                    continue
            if record._full_address():
                to_geocode |= record
        for record in to_geocode:
            record._auto_geocode_safely()
        return records

    def write(self, vals):
        if "latitude" in vals or "longitude" in vals:
            if "geocode_status" not in vals:
                vals["geocode_status"] = "manual"
        if "ddns_domain" in vals:
            vals["ddns_domain"] = self._clean_ddns_domain(vals["ddns_domain"])
            if not vals["ddns_domain"]:
                vals.update(wan_ip=False, last_ip_sync=False)
        addr_changed = any(k in vals for k in ("street", "street2", "city", "state_id", "country_id", "zip")) and not (
            "latitude" in vals or "longitude" in vals) and not self.env.context.get("skip_auto_geocode")
        res = super().write(vals)
        if addr_changed:
            for rec in self.with_context(skip_auto_geocode=True):
                if rec.geocode_status == "manual" and (rec.latitude or rec.longitude):
                    continue  # tọa độ nhập tay: giữ nguyên
                if rec._full_address():
                    rec._auto_geocode_safely()
        if vals.get("ddns_domain"):
            self._sync_wan_ip()
        return res

    # ---------------- DDNS -> IP WAN ----------------
    @staticmethod
    def _clean_ddns_domain(value):
        """Chuẩn hóa tên miền dán vào: bỏ khoảng trắng, http(s)://, đường dẫn, cổng."""
        v = (value or "").strip()
        v = re.sub(r"(?i)^[a-z]+://", "", v)
        v = v.split("/")[0].split(":")[0].strip().strip(".").lower()
        return v or False

    def _resolve_ddns(self, domain):
        """Tra IPv4 của tên miền DDNS (DNS). Trả về IP hoặc None nếu không tra được."""
        old = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(5)
            infos = socket.getaddrinfo(domain, None, socket.AF_INET)
            ips = sorted({i[4][0] for i in infos})
            return ips[0] if ips else None
        except (socket.gaierror, socket.herror, socket.timeout, OSError, UnicodeError) as e:
            _logger.warning("Không tra được IP của tên miền DDNS %s: %s", domain, e)
            return None
        finally:
            socket.setdefaulttimeout(old)

    def _sync_wan_ip(self, raise_if_error=False):
        """Cập nhật IP WAN cho các cửa hàng có Tên miền DDNS. Trả về danh sách tên miền không tra được."""
        failed = []
        for rec in self.filtered("ddns_domain"):
            ip = rec._resolve_ddns(rec.ddns_domain)
            if not ip:
                failed.append(rec.ddns_domain)
                continue
            vals = {"last_ip_sync": fields.Datetime.now()}
            changed = ip != rec.wan_ip
            if changed:
                vals["wan_ip"] = ip
            super(HrStore, rec).write(vals)
            # Chưa có tọa độ thật (geopy / nhập tay): tự ước tính vị trí theo IP (lần đầu hoặc khi IP đổi)
            if rec._needs_ip_location(changed):
                rec._auto_locate_by_ip()
        if failed and raise_if_error:
            raise UserError(_(
                "Không tra được IP của tên miền DDNS: %s. "
                "Kiểm tra lại tên miền hoặc kết nối mạng của máy chủ."
            ) % ", ".join(failed))
        return failed

    def action_sync_wan_ip(self):
        """Nút "Cập nhật IP" trên form Cửa hàng."""
        if not self.filtered("ddns_domain"):
            raise UserError(_("Vui lòng nhập Tên miền DDNS trước."))
        self._sync_wan_ip(raise_if_error=True)
        return True

    @api.model
    def _store_for_ip(self, ip, prefer=None):
        """Cửa hàng có IP WAN trùng IP truy cập (ưu tiên cửa hàng trong prefer)."""
        if not ip:
            return self.browse()
        stores = self.sudo().search([("wan_ip", "=", ip)])
        if prefer:
            mine = stores & prefer
            if mine:
                return mine[:1]
        return stores[:1]

    @api.model
    def _lookup_ip_location(self, ip):
        """Tra vị trí gần đúng của IP qua dịch vụ HTTPS: ipwho.is, dự phòng ipinfo.io.
        Trả về dict(lat, lon, city, region, country, isp, source) hoặc raise UserError."""
        import requests
        errors = []
        try:
            d = requests.get("https://ipwho.is/%s" % ip, timeout=8).json()
            if d.get("success") and d.get("latitude") is not None:
                return {
                    "lat": d.get("latitude"), "lon": d.get("longitude"),
                    "city": d.get("city"), "region": d.get("region"), "country": d.get("country"),
                    "isp": (d.get("connection") or {}).get("isp") or (d.get("connection") or {}).get("org"),
                    "source": "ipwho.is",
                }
            errors.append("ipwho.is: %s" % (d.get("message") or "không có dữ liệu"))
        except Exception as e:
            errors.append("ipwho.is: %s" % e)
        try:
            d = requests.get("https://ipinfo.io/%s/json" % ip, timeout=8).json()
            if d.get("loc"):
                lat, lon = (float(x) for x in d["loc"].split(","))
                return {
                    "lat": lat, "lon": lon,
                    "city": d.get("city"), "region": d.get("region"), "country": d.get("country"),
                    "isp": d.get("org"), "source": "ipinfo.io",
                }
            errors.append("ipinfo.io: %s" % ((d.get("error") or {}).get("message") or "không có dữ liệu"))
        except Exception as e:
            errors.append("ipinfo.io: %s" % e)
        raise UserError(_("Không tra được vị trí của IP %s.\n%s") % (ip, "\n".join(errors)))

    def _needs_ip_location(self, ip_changed=False):
        self.ensure_one()
        if not self.wan_ip:
            return False
        if self.geocode_status in ("success", "manual") and (self.latitude or self.longitude):
            return False  # đã có tọa độ thật: không đụng tới
        if not (self.latitude or self.longitude) or not self.ip_location:
            return True
        return bool(ip_changed and self.geocode_status == "ip")

    def _auto_locate_by_ip(self):
        """Định vị chạy ngầm: có địa chỉ thì định vị theo địa chỉ (chính xác); không có địa chỉ mới ước tính theo IP.
        Lỗi mạng / dịch vụ chỉ ghi log, không báo lỗi người dùng."""
        for rec in self:
            try:
                if (rec.street or "").strip():
                    rec._auto_geocode_safely()
                    if rec.geocode_status == "success":
                        continue
                rec.action_geolocate_by_ip()
            except Exception as e:
                _logger.warning("Không ước tính được vị trí theo IP cho cửa hàng %s: %s", rec.display_name, e)

    @staticmethod
    def _ip_region_conflict(mien, lat):
        """Vị trí theo IP mâu thuẫn với Miền của cửa hàng (vd IP báo Hà Nội nhưng cửa hàng Miền Nam)."""
        if not lat:
            return False
        if mien == "Nam" and lat > 16.0:
            return True
        if mien == "Bắc" and lat < 16.0:
            return True
        return False

    def action_geolocate_by_ip(self):
        """Nút "Ước tính vị trí theo IP": tra IP WAN -> vĩ độ / kinh độ gần đúng + tỉnh/thành, nhà mạng.
        Không ghi đè tọa độ đã có từ địa chỉ (geopy) hoặc nhập tay."""
        for rec in self:
            if not rec.wan_ip and rec.ddns_domain:
                rec._sync_wan_ip()
            if not rec.wan_ip:
                raise UserError(_("Cửa hàng %s chưa có IP WAN. Nhập Tên miền DDNS rồi bấm Cập nhật IP trước.") % rec.display_name)
            data = self._lookup_ip_location(rec.wan_ip)
            area = ", ".join(x for x in (data.get("city"), data.get("region"), data.get("country")) if x)
            if data.get("isp"):
                area = "%s (%s)" % (area, data["isp"])
            place = rec._reverse_geocode(data.get("lat"), data.get("lon"))
            label = "%s · nguồn %s" % (place or area, data["source"])
            if place and data.get("isp"):
                label = "%s (%s) · nguồn %s" % (place, data["isp"], data["source"])
            mien = getattr(rec, "mien", False)
            conflict = rec._ip_region_conflict(mien, data.get("lat"))
            if conflict:
                # IP đăng ký ở miền khác (nhà mạng hay gán IP về trung tâm Hà Nội / TP.HCM): không dùng tọa độ này
                label = "%s · KHÔNG khớp Miền %s, bỏ qua tọa độ" % (label, mien)
            vals = {"ip_location": label}
            has_real = (rec.latitude or rec.longitude) and rec.geocode_status in ("success", "manual")
            if not has_real and not conflict:
                vals.update({
                    "latitude": data.get("lat") or 0.0,
                    "longitude": data.get("lon") or 0.0,
                    "geocode_status": "ip",
                    "last_geocode_time": fields.Datetime.now(),
                })
            rec.write(vals)
            if conflict and not self.env.context.get("ip_locate_silent"):
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Vị trí theo IP không dùng được"),
                        "message": _("IP %s được nhà mạng đăng ký ở %s, khác Miền %s của cửa hàng. "
                                     "Vui lòng nhập địa chỉ cửa hàng rồi bấm Định vị tọa độ (geopy).") % (rec.wan_ip, area, mien),
                        "type": "warning",
                        "sticky": True,
                    },
                }
        return True

    @api.model
    def _reverse_geocode(self, lat, lon):
        """Tọa độ -> tên địa điểm (phường/quận, thành phố) bằng OpenStreetMap Nominatim. Lỗi thì trả về None."""
        if not Nominatim or not (lat or lon):
            return None
        try:
            geolocator = Nominatim(user_agent="khan_odoo_store_geocoder", timeout=10)
            loc = geolocator.reverse((lat, lon), language="vi", zoom=16, exactly_one=True)
        except Exception as e:
            _logger.warning("Không tra ngược được địa chỉ của tọa độ %s, %s: %s", lat, lon, e)
            return None
        if not loc:
            return None
        addr = (loc.raw or {}).get("address") or {}
        parts = []
        for key in ("road", "quarter", "suburb", "city_district", "district", "city", "town", "state"):
            val = addr.get(key)
            if val and val not in parts:
                parts.append(val)
        return ", ".join(parts) or loc.address

    @api.model
    def _cron_sync_wan_ip(self):
        """Tác vụ định kỳ: cập nhật IP WAN cho mọi cửa hàng có Tên miền DDNS."""
        self.search([("ddns_domain", "!=", False)])._sync_wan_ip()

    def _full_address(self):
        """Địa chỉ đầy đủ để định vị: Street, Street2, City, State, Country (mặc định Việt Nam)."""
        self.ensure_one()
        parts = []
        for name in ("street", "street2", "city"):
            if name in self._fields and (self[name] or "").strip():
                parts.append(self[name].strip())
        if not parts:
            return ""
        if "state_id" in self._fields and self.state_id and self.state_id.name not in parts:
            parts.append(self.state_id.name)
        country = self.country_id.name if "country_id" in self._fields and self.country_id else "Việt Nam"
        text = ", ".join(parts)
        # địa chỉ dán từ Google Maps thường đã có "Việt Nam" ở cuối: không thêm lần nữa
        if not re.search(r"(?i)(việt nam|viet nam|vietnam)\s*$", text):
            text = "%s, %s" % (text, country)
        return text

    def _mark_geocode_failed(self):
        """Không tìm được tọa độ theo địa chỉ: đánh dấu thất bại và bỏ tọa độ ước tính theo IP cũ
        (giữ nguyên tọa độ nhập tay / định vị thành công trước đó)."""
        for rec in self:
            vals = {"geocode_status": "failed"}
            if rec.geocode_status == "ip":
                vals.update(latitude=0.0, longitude=0.0)
            super(HrStore, rec).write(vals)

    @staticmethod
    def _address_variants(address):
        """Các cách viết rút gọn của địa chỉ VN để OpenStreetMap dễ tìm:
        bỏ phần Phường/Quận/Huyện/Xã/Thị xã/Khu phố/Ấp, chuẩn hóa "Đ." -> "Đường", "TP." -> "Thành phố"."""
        parts = []
        for p in (address or "").split(","):
            p = re.sub(r"\s+\d{5,6}$", "", p.strip())  # bỏ mã bưu chính (vd "Hồ Chí Minh 70000")
            if p and p not in parts:  # bỏ phần lặp (vd "Việt Nam, Việt Nam")
                parts.append(p)
        admin = re.compile(r"(?i)^(p\.|q\.|phường|quận|huyện|xã|thị xã|thị trấn|khu phố|kp\.?|ấp|tổ)(?=[\s\d.]|$)")
        kept = [p for p in parts if not admin.match(p)]
        norm = []
        for p in kept:
            p = re.sub(r"(?i)^đ\.\s*", "Đường ", p)
            p = re.sub(r"(?i)^tp\.?\s*", "Thành phố ", p)
            p = re.sub(r"(?i)^thành phố\s+", "", p) if len(kept) > 2 else p
            norm.append(p)
        variants = []
        for cand in (kept, norm):
            v = ", ".join(cand)
            if v and v != address and v not in variants:
                variants.append(v)
        # không số nhà: chỉ tên đường + tỉnh/thành
        if norm and re.match(r"^\d+[\w/]*\s+", norm[0]):
            v = ", ".join([re.sub(r"^\d+[\w/]*\s+", "", norm[0])] + norm[1:])
            if v not in variants:
                variants.append(v)
        return variants

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

        address = self._full_address()
        if not address:
            if raise_if_error:
                raise UserError(_("Vui lòng nhập địa chỉ trước khi định vị tọa độ."))
            return False

        try:
            geolocator = Nominatim(user_agent="khan_odoo_store_geocoder", timeout=10)
            
            # Thử lần 1: Nguyên văn địa chỉ
            loc = geolocator.geocode(address, country_codes="vn")
            
            # Thử lần 2: Fallback sau khi làm sạch tiền tố tầng / TTTM
            if not loc:
                sanitized = self._sanitize_address_for_nominatim(address)
                if sanitized and sanitized != address:
                    loc = geolocator.geocode(sanitized, country_codes="vn")
                    
            # Thử lần 2b: bỏ Phường / Quận / Huyện / Xã cũ (bản đồ đã đổi theo sáp nhập hành chính 2025),
            # giữ số nhà + tên đường + tỉnh/thành
            if not loc:
                for variant in self._address_variants(sanitized if sanitized else address):
                    loc = geolocator.geocode(variant, country_codes="vn")
                    if loc:
                        break

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
                self._mark_geocode_failed()
                if raise_if_error:
                    raise UserError(
                        _("Không thể tìm thấy tọa độ phù hợp cho địa chỉ này trên OpenStreetMap. "
                          "Vui lòng kiểm tra lại địa chỉ hoặc nhập tay tọa độ Vĩ độ / Kinh độ.")
                    )
                return False

        except (GeocoderTimedOut, GeocoderUnavailable) as exc:
            self._mark_geocode_failed()
            msg = _("Dịch vụ định vị OpenStreetMap bị quá thời gian hoặc không phản hồi: %s") % str(exc)
            _logger.warning(msg)
            if raise_if_error:
                raise UserError(msg)
            return False
        except Exception as e:
            self._mark_geocode_failed()
            _logger.exception("Geocoding exception: %s", e)
            if raise_if_error:
                raise UserError(_("Lỗi trong quá trình định vị: %s") % str(e))
            return False
