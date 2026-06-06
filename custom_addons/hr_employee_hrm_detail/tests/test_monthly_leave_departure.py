from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthlyLeaveDeparture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Monthly Leave Cutoff Employee",
                "tong_so_phep": 5,
            }
        )

    def test_departure_before_day_20_blocks_monthly_bonus(self):
        self.employee.ngay_nghi_viec = date(2026, 10, 15)

        self.employee.with_context(
            monthly_leave_bonus_date=date(2026, 10, 1)
        ).write({"tong_so_phep": 6})

        self.assertEqual(self.employee.tong_so_phep, 5)

    def test_departure_on_day_20_keeps_monthly_bonus(self):
        self.employee.ngay_nghi_viec = date(2026, 10, 20)

        self.employee.with_context(
            monthly_leave_bonus_date=date(2026, 10, 1)
        ).write({"tong_so_phep": 6})

        self.assertEqual(self.employee.tong_so_phep, 6)

    def test_departure_in_another_month_keeps_monthly_bonus(self):
        self.employee.ngay_nghi_viec = date(2026, 11, 15)

        self.employee.with_context(
            monthly_leave_bonus_date=date(2026, 10, 1)
        ).write({"tong_so_phep": 6})

        self.assertEqual(self.employee.tong_so_phep, 6)

    def test_previous_month_bonus_is_not_affected(self):
        self.employee.ngay_nghi_viec = date(2026, 10, 15)

        self.employee.with_context(
            monthly_leave_bonus_date=date(2026, 9, 1)
        ).write({"tong_so_phep": 6})

        self.assertEqual(self.employee.tong_so_phep, 6)

    def test_non_bonus_total_update_is_not_blocked(self):
        self.employee.ngay_nghi_viec = date(2026, 10, 15)

        self.employee.with_context(
            monthly_leave_bonus_date=date(2026, 10, 1)
        ).write({"tong_so_phep": 7})

        self.assertEqual(self.employee.tong_so_phep, 7)
