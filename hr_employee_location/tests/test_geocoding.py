# -*- coding: utf-8 -*-
from unittest.mock import patch, MagicMock
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestGeocodingAndEmployeeLocation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Store = cls.env["hr.store"]
        cls.Employee = cls.env["hr.employee"]

        cls.test_store = cls.Store.create({
            "name": "Cửa hàng Quận 10",
            "code": "CH_Q10",
            "address": "11 Sư Vạn Hạnh, Phường 12, Quận 10, TP Hồ Chí Minh",
        })

        cls.test_employee = cls.Employee.create({
            "name": "Nguyễn Văn Test",
            "store_ids": [(4, cls.test_store.id)],
        })

    def test_01_address_sanitization(self):
        """Kiểm tra làm sạch chuỗi địa chỉ để tìm trên OSM Nominatim."""
        raw_address = "Tầng 1, TTTM Vạn Hạnh Mall, 11 Sư Vạn Hạnh, Phường 12, Quận 10"
        cleaned = self.test_store._sanitize_address_for_nominatim(raw_address)
        self.assertNotIn("Tầng 1", cleaned)
        self.assertNotIn("TTTM", cleaned)
        self.assertIn("11 Sư Vạn Hạnh", cleaned)

    @patch("hr_employee_location.models.hr_store.Nominatim")
    def test_02_geocode_success(self, mock_nominatim_cls):
        """Kiểm tra geocode thành công khi geopy trả về tọa độ."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 10.7719
        mock_location.longitude = 106.6672
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        self.test_store.action_geocode_address(raise_if_error=True)
        self.assertEqual(self.test_store.geocode_status, "success")
        self.assertAlmostEqual(self.test_store.latitude, 10.7719)
        self.assertAlmostEqual(self.test_store.longitude, 106.6672)
        self.assertTrue(self.test_store.last_geocode_time)

    def test_03_manual_override_protection(self):
        """Admin nhập tọa độ thủ công -> chuyển sang manual và không bị ghi đè tự động."""
        self.test_store.write({
            "latitude": 10.8000,
            "longitude": 106.7000,
        })
        self.assertEqual(self.test_store.geocode_status, "manual")

        # Cập nhật địa chỉ nhưng geocode_status đang là manual thì không tự động ghi đè
        self.test_store.write({"address": "Địa chỉ mới thay đổi"})
        self.assertEqual(self.test_store.geocode_status, "manual")
        self.assertAlmostEqual(self.test_store.latitude, 10.8000)

    def test_04_employee_gps_status_computation(self):
        """Kiểm tra tính toán gps_status dựa vào thời gian cập nhật."""
        # Chưa có GPS
        self.assertEqual(self.test_employee.gps_status, "none")

        # Có GPS mới (vừa cập nhật)
        now = fields.Datetime.now()
        self.test_employee.write({
            "last_latitude": 10.7769,
            "last_longitude": 106.7009,
            "last_location_time": now,
        })
        self.assertEqual(self.test_employee.gps_status, "active")

        # GPS cũ hơn 1 giờ
        stale_time = now - timedelta(hours=2)
        self.test_employee.write({"last_location_time": stale_time})
        self.assertEqual(self.test_employee.gps_status, "stale")
