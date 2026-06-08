from datetime import date
from unittest.mock import patch

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

    def test_zero_balance_does_not_request_confirmation(self):
        Leave = self.env["hr.leave"]
        preview = Leave.check_con_lai_zero_confirmation(
            vals={"employee_id": self.employee.id}
        )

        self.assertFalse(preview["needs_confirmation"])

    def test_summary_counts_only_p1_p2_leave_types(self):
        Leave = self.env["hr.leave"]
        with (
            patch.object(
                type(self.employee),
                "_summary_paid_leave_type_ids",
                autospec=True,
                return_value=[11, 12],
            ),
            patch.object(
                type(Leave),
                "read_group",
                autospec=True,
                return_value=[{"number_of_days": 4}],
            ) as read_group,
        ):
            used = self.employee._get_leave_days_used_for_summary(date(2026, 6, 15))

        self.assertEqual(used, 4)
        self.assertIn(
            ("holiday_status_id", "in", [11, 12]),
            read_group.call_args.kwargs["domain"],
        )

    def test_committed_budget_counts_only_p1_p2_leave_types(self):
        Leave = self.env["hr.leave"]
        with (
            patch.object(
                type(self.employee),
                "_summary_paid_leave_type_ids",
                autospec=True,
                return_value=[11, 12],
            ),
            patch.object(
                type(Leave),
                "read_group",
                autospec=True,
                return_value=[{"number_of_days": 3}],
            ) as read_group,
        ):
            committed = Leave._con_lai_committed_days(
                self.employee, target_date=date(2026, 6, 15)
            )

        self.assertEqual(committed, 3)
        self.assertIn(
            ("holiday_status_id", "in", [11, 12]),
            read_group.call_args.kwargs["domain"],
        )
