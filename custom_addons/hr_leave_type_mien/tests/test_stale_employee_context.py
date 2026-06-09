from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestStaleEmployeeContext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="timeoff-stale-employee-context",
            groups="base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Time Off Context Employee",
                "user_id": cls.user.id,
                "company_id": cls.user.company_id.id,
            }
        )

    def test_default_get_replaces_deleted_context_employee(self):
        deleted_employee = self.env["hr.employee"].create(
            {
                "name": "Deleted Time Off Context Employee",
                "company_id": self.user.company_id.id,
            }
        )
        deleted_employee_id = deleted_employee.id
        deleted_employee.unlink()

        defaults = (
            self.env["hr.leave"]
            .with_user(self.user)
            .with_context(
                default_employee_id=deleted_employee_id,
                employee_id=deleted_employee_id,
            )
            .default_get(["employee_id", "holiday_status_id"])
        )

        self.assertEqual(defaults["employee_id"], self.employee.id)

    def test_mien_filter_ignores_inaccessible_context_employee(self):
        other_company = self.env["res.company"].create(
            {"name": "Inaccessible Employee Company"}
        )
        inaccessible_employee = self.env["hr.employee"].create(
            {
                "name": "Inaccessible Time Off Context Employee",
                "company_id": other_company.id,
            }
        )

        LeaveType = (
            self.env["hr.leave.type"]
            .with_user(self.user)
            .with_context(
                filter_leave_types_by_employee_mien=True,
                employee_id=inaccessible_employee.id,
            )
        )

        self.assertEqual(LeaveType._domain_with_employee_mien([]), [])
