# -*- coding: utf-8 -*-
from odoo.tests.common import HttpCase


class TestGeolocationController(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]
        cls.User = cls.env["res.users"]

        cls.test_user = cls.User.create({
            "name": "Nhân viên Test GPS",
            "login": "test_gps_user",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

        cls.test_emp = cls.Employee.create({
            "name": "Nhân viên Test GPS",
            "user_id": cls.test_user.id,
        })

    def test_01_update_position_authenticated(self):
        """Kiểm tra gọi RPC cập nhật tọa độ GPS thành công."""
        self.authenticate("test_gps_user", "test_gps_user")
        response = self.url_open(
            "/hr_employee_location/update_position",
            headers={"Content-Type": "application/json"},
            data="""{
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "latitude": 10.7769,
                    "longitude": 106.7009,
                    "accuracy": 15.0
                }
            }""",
        )
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertIn("result", res_json)
        self.assertEqual(res_json["result"]["status"], "ok")

        # Kiểm tra database đã cập nhật
        self.test_emp.invalidate_recordset()
        self.assertAlmostEqual(self.test_emp.last_latitude, 10.7769)
        self.assertAlmostEqual(self.test_emp.last_longitude, 106.7009)
        self.assertTrue(self.test_emp.last_location_time)
