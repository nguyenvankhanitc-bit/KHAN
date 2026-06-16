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

    def test_year_rollover_snapshots_then_resets_current_balance_once(self):
        with patch.object(
            type(self.employee),
            "_get_leave_days_used_for_summary",
            autospec=True,
            return_value=2,
        ):
            self.env["hr.employee"].cron_snapshot_con_lai_prev_year()

        self.assertEqual(self.employee.con_lai_nam_truoc, 3)
        self.assertEqual(self.employee.nam_chot_con_lai, 2025)
        self.assertEqual(self.employee.tong_so_phep, 0)
        self.assertEqual(self.employee.con_lai, 0)

        self.employee.write({"tong_so_phep": 1})
        self.env["hr.employee"].cron_snapshot_con_lai_prev_year()

        self.assertEqual(self.employee.con_lai_nam_truoc, 3)
        self.assertEqual(self.employee.tong_so_phep, 1)
        self.assertEqual(self.employee.con_lai, 1)

    def test_zero_balance_does_not_request_confirmation(self):
        Leave = self.env["hr.leave"]
        preview = Leave.check_con_lai_zero_confirmation(
            vals={"employee_id": self.employee.id}
        )

        self.assertFalse(preview["needs_confirmation"])

    def test_summary_counts_only_paid_leave_types(self):
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
                "_read_group",
                autospec=True,
                return_value=[(4,)],
            ) as read_group,
        ):
            used = self.employee._get_leave_days_used_for_summary(date(2026, 6, 15))

        self.assertEqual(used, 4)
        self.assertIn(
            ("state", "in", ("confirm", "validate1", "validate")),
            read_group.call_args.kwargs["domain"],
        )
        self.assertIn(
            ("holiday_status_id", "in", [11, 12]),
            read_group.call_args.kwargs["domain"],
        )

    def test_committed_budget_counts_only_paid_leave_types(self):
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
                "_read_group",
                autospec=True,
                return_value=[(3,)],
            ) as read_group,
        ):
            committed = Leave._con_lai_committed_days(
                self.employee, target_date=date(2026, 6, 15)
            )

        self.assertEqual(committed, 3)
        self.assertIn(
            ("state", "in", ("confirm", "validate1", "validate")),
            read_group.call_args.kwargs["domain"],
        )

    def test_summary_paid_leave_types_include_p1_p2_only(self):
        paid_p = self.env["hr.leave.type"].create(
            {
                "name": "Paid Time Off (P)",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )
        paid_p1 = self.env["hr.leave.type"].create(
            {
                "name": "Annual Leave (P1)",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )
        paid_p2 = self.env["hr.leave.type"].create(
            {
                "name": "Annual Leave (P2)",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )
        unpaid_o = self.env["hr.leave.type"].create(
            {
                "name": "Unpaid Leave (O)",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )

        paid_ids = self.employee._summary_paid_leave_type_ids()

        self.assertNotIn(paid_p.id, paid_ids)
        self.assertIn(paid_p1.id, paid_ids)
        self.assertIn(paid_p2.id, paid_ids)
        self.assertNotIn(unpaid_o.id, paid_ids)

    def test_maternity_first_day_license_adds_one_remaining_day_and_recomputes(self):
        with patch.object(
            type(self.employee),
            "_get_leave_days_used_for_summary",
            autospec=True,
            return_value=0,
        ):
            self.employee.write({"thai_san_ngay_cap_phep": date(2026, 2, 1)})
            self.assertEqual(self.employee.con_lai, 6)

            self.employee.write({"thai_san_ngay_cap_phep": date(2026, 2, 2)})
            self.assertEqual(self.employee.con_lai, 5)

            self.employee.write({"thai_san_ngay_cap_phep": date(2026, 3, 1)})
            self.assertEqual(self.employee.con_lai, 6)

    def test_retroactive_previous_year_leave_deducts_and_restores_snapshot(self):
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "P1 previous-year balance test",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )
        self.employee.write(
            {
                "con_lai_nam_truoc": 5,
                "nam_chot_con_lai": 2025,
            }
        )
        Leave = self.env["hr.leave"]

        with (
            patch.object(
                type(Leave),
                "_previous_year_balance_today",
                autospec=True,
                return_value=date(2026, 1, 2),
            ),
            patch.object(
                type(self.employee),
                "_summary_paid_leave_type_ids",
                autospec=True,
                return_value=[leave_type.id],
            ),
        ):
            leave = Leave.create(
                {
                    "name": "Retroactive leave",
                    "employee_id": self.employee.id,
                    "holiday_status_id": leave_type.id,
                    "request_date_from": date(2025, 12, 29),
                    "request_date_to": date(2025, 12, 29),
                    "state": "confirm",
                }
            )
            self.assertEqual(leave.previous_year_balance_deduction, 1)
            self.assertEqual(self.employee.con_lai_nam_truoc, 4)

            leave.write({"state": "refuse"})
            self.assertEqual(leave.previous_year_balance_deduction, 0)
            self.assertEqual(self.employee.con_lai_nam_truoc, 5)

    def test_previous_year_balance_rebalances_waiting_retroactive_leaves(self):
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "P1 previous-year rebalance test",
                "requires_allocation": False,
                "company_id": self.env.company.id,
            }
        )
        self.employee.write(
            {
                "con_lai_nam_truoc": 1,
                "nam_chot_con_lai": 2025,
            }
        )
        Leave = self.env["hr.leave"]

        with (
            patch.object(
                type(Leave),
                "_previous_year_balance_today",
                autospec=True,
                return_value=date(2026, 1, 2),
            ),
            patch.object(
                type(self.employee),
                "_summary_paid_leave_type_ids",
                autospec=True,
                return_value=[leave_type.id],
            ),
        ):
            first, second = Leave.create(
                [
                    {
                        "name": "First retroactive leave",
                        "employee_id": self.employee.id,
                        "holiday_status_id": leave_type.id,
                        "request_date_from": date(2025, 12, 29),
                        "request_date_to": date(2025, 12, 29),
                        "state": "confirm",
                    },
                    {
                        "name": "Second retroactive leave",
                        "employee_id": self.employee.id,
                        "holiday_status_id": leave_type.id,
                        "request_date_from": date(2025, 12, 30),
                        "request_date_to": date(2025, 12, 30),
                        "state": "confirm",
                    },
                ]
            )
            self.assertEqual(first.previous_year_balance_deduction, 1)
            self.assertTrue(second.previous_year_balance_synced)
            self.assertEqual(second.previous_year_balance_deduction, 0)

            first.write({"state": "refuse"})
            self.assertEqual(second.previous_year_balance_deduction, 1)
            self.assertEqual(self.employee.con_lai_nam_truoc, 0)
