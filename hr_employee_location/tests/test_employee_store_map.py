# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestEmployeeStoreMapData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Store = cls.env["hr.store"]
        cls.Employee = cls.env["hr.employee"]

        cls.store1 = cls.Store.create({
            "name": "Cửa hàng Quận 1",
            "code": "CH_Q1",
            "latitude": 10.7769,
            "longitude": 106.7009,
            "geocode_status": "success",
        })

        cls.store2 = cls.Store.create({
            "name": "Cửa hàng Tân Bình",
            "code": "CH_TB",
            "latitude": 10.8015,
            "longitude": 106.6534,
            "geocode_status": "manual",
        })

        cls.employee = cls.Employee.create({
            "name": "Nguyễn Văn Giám Sát",
            "job_title": "Giám sát chuỗi",
            "last_latitude": 10.7850,
            "last_longitude": 106.6800,
            "store_ids": [(6, 0, [cls.store1.id, cls.store2.id])],
        })

    def test_01_store_network_relation(self):
        """Kiểm tra quan hệ many2many giữa nhân viên và danh sách cửa hàng trực thuộc."""
        self.assertEqual(len(self.employee.store_ids), 2)
        self.assertIn(self.store1, self.employee.store_ids)
        self.assertIn(self.store2, self.employee.store_ids)
        self.assertIn(self.employee, self.store1.employee_ids)

    def test_02_map_client_action_record(self):
        """Kiểm tra client action XML được tạo thành công trong hệ thống."""
        action = self.env.ref("hr_employee_location.action_employee_store_map")
        self.assertTrue(action)
        self.assertEqual(action.tag, "hr_employee_location.map_workspace")
