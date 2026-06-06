from datetime import date
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTimeOffRemainingBalance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Remaining Balance Employee",
                "tong_so_phep": 5,
            }
        )

    def test_summary_period_uses_calendar_year(self):
        self.assertEqual(
            self.employee._time_off_summary_period_bounds(date(2026, 6, 15)),
            (date(2026, 1, 1), date(2026, 12, 31)),
        )

    def test_negative_historical_balance_is_displayed_as_zero(self):
        with patch.object(
            type(self.employee),
            "_get_leave_days_used_for_summary",
            autospec=True,
            return_value=7,
        ):
            self.employee.with_context(
                employees_no_timeoff_write=True,
                employees_no_allowed_employee_ids=self.employee.ids,
            )._compute_time_off_summary()

        self.assertEqual(self.employee.da_su_dung, 7)
        self.assertEqual(self.employee.con_lai, 0)

    def test_projected_negative_balance_is_blocked(self):
        Leave = self.env["hr.leave"]
        with patch.object(
            type(Leave),
            "_con_lai_committed_days",
            autospec=True,
            return_value=5,
        ):
            with self.assertRaises(ValidationError):
                Leave._assert_con_lai_not_negative(self.employee, 1)

    def test_projected_zero_balance_is_allowed(self):
        Leave = self.env["hr.leave"]
        with patch.object(
            type(Leave),
            "_con_lai_committed_days",
            autospec=True,
            return_value=4,
        ):
            Leave._assert_con_lai_not_negative(self.employee, 1)
