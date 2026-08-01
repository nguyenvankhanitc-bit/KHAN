from unittest.mock import patch

from odoo.addons.hr.models.hr_employee import _ALLOW_READ_HR_EMPLOYEE
from odoo.fields import Domain
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHrEmployeeInternalRead(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="hr-employee-internal-read",
            groups="base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Internal Relation Employee",
                "company_id": cls.user.company_id.id,
            }
        )

    def test_internal_relation_context_bypasses_custom_employee_scope(self):
        Employee = self.env["hr.employee"].with_user(self.user)
        access_mixin_type = type(self.env["hr.employee.access.mixin"])

        with patch.object(
            access_mixin_type,
            "_hr_employee_access_extra_domain",
            autospec=True,
            return_value=Domain.FALSE,
        ):
            self.assertFalse(Employee.search([("id", "=", self.employee.id)]))

            internal_employee = Employee.with_context(
                _allow_read_hr_employee=_ALLOW_READ_HR_EMPLOYEE
            ).search([("id", "=", self.employee.id)])

            self.assertEqual(internal_employee.ids, self.employee.ids)
            self.assertFalse(internal_employee._hr_employee_read_is_restricted())
            internal_employee.invalidate_recordset(["name"])
            self.assertEqual(internal_employee.name, self.employee.name)

    def test_public_sudo_can_walk_out_of_scope_parent_chain(self):
        """Org chart uses sudo() to walk managers; must not MissingError on parent_id."""
        company = self.user.company_id
        manager = self.env["hr.employee"].create(
            {"name": "Out-of-scope Manager", "company_id": company.id}
        )
        peer = self.env["hr.employee"].create(
            {
                "name": "Visible Peer",
                "company_id": company.id,
                "parent_id": manager.id,
                "user_id": self.user.id,
            }
        )
        self.user.visibility_policy = "self"
        self.env.flush_all()

        Public = self.env["hr.employee.public"].with_user(self.user)
        self.assertTrue(Public._hr_employee_read_is_restricted())
        self.assertFalse(Public.sudo()._hr_employee_read_is_restricted())
        self.assertNotIn(manager.id, Public.search([]).ids)
        self.assertIn(peer.id, Public.search([]).ids)

        # Same path as /hr/get_org_chart: sudo walk via parent_id.
        current = Public.browse(peer.id).sudo()
        parent = current.parent_id
        self.assertEqual(parent.id, manager.id)
        self.assertEqual(parent.name, manager.name)
