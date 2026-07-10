from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLeaveFormAttachment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_user = new_test_user(
            cls.env,
            login="leave-form-attachment-user",
            groups="base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Leave Attachment Tester",
                "user_id": cls.employee_user.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "Attachment validation test",
                "requires_allocation": False,
                "company_id": cls.env.company.id,
            }
        )

    def _base_vals(self):
        return {
            "employee_id": self.employee.id,
            "holiday_status_id": self.leave_type.id,
            "request_date_from": date(2026, 12, 8),
            "request_date_to": date(2026, 12, 8),
            "name": "Nghỉ việc riêng",
            "state": "confirm",
        }

    def _create_attachment(self, name):
        return self.env["ir.attachment"].create(
            {
                "name": name,
                "datas": "dGVzdA==",
                "res_model": "hr.leave",
            }
        )

    def test_submit_requires_named_leave_form_attachment(self):
        leave_model = self.env["hr.leave"].with_context(leave_fast_create=True)
        leave = leave_model.create(self._base_vals())
        wrong_attachment = self._create_attachment("scan_khac.pdf")

        with self.assertRaises(ValidationError):
            leave.write({"supported_attachment_ids": [(4, wrong_attachment.id)]})

        valid_attachment = self._create_attachment("Đơn xin nghỉ phép.docx")
        leave.write({"supported_attachment_ids": [(4, valid_attachment.id)]})

    def test_submit_blocks_when_attachment_missing(self):
        leave_model = self.env["hr.leave"].with_context(leave_fast_create=True)
        leave = leave_model.create(self._base_vals())

        with self.assertRaises(ValidationError):
            leave.write({"name": "Cập nhật lý do"})
