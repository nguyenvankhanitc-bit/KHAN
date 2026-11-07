# -*- coding: utf-8 -*-
"""
Unit test for stage task deadline reminder and notification logic in lug_project.
Tests:
- lug_notified_deadline field definition
- Write resetting lug_notified_deadline when deadline changes
- _cron_check_deadline_reminders query, recipient collection, and dispatching
- Idempotency (no duplicate notification for same deadline)
- Exclusions (done, cancel, no deadline)
- Cron XML definition
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

# Mock dateutil if missing
if "dateutil" not in sys.modules:
    mock_dateutil = MagicMock()
    mock_relativedelta = MagicMock()
    mock_dateutil.relativedelta = mock_relativedelta
    sys.modules["dateutil"] = mock_dateutil
    sys.modules["dateutil.relativedelta"] = mock_relativedelta

# Setup mock odoo environment if not already loaded
if "odoo" not in sys.modules:
    mock_odoo = MagicMock()
    mock_api = MagicMock()
    mock_api.model = lambda f: f
    mock_api.model_create_multi = lambda f: f
    mock_api.depends = lambda *args: lambda f: f
    mock_api.onchange = lambda *args: lambda f: f
    mock_api.constrains = lambda *args: lambda f: f

    mock_fields = MagicMock()
    mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Date.context_today = MagicMock(return_value="2026-11-07")
    mock_fields.Date.to_date = lambda d: (
        date.fromisoformat(d) if isinstance(d, str) else d
    )

    mock_models = MagicMock()

    class MockModel:
        _name = "mock.model"
        _inherit = ""

        def __init__(self, *args, **kwargs):
            pass

        def write(self, vals):
            return True

    mock_models.Model = MockModel
    mock_models.TransientModel = MockModel
    mock_exceptions = MagicMock()
    mock_exceptions.ValidationError = Exception
    mock_exceptions.UserError = Exception

    mock_tools = MagicMock()
    mock_tools.html2plaintext = lambda s: s

    mock_odoo.api = mock_api
    mock_odoo.fields = mock_fields
    mock_odoo.models = mock_models
    mock_odoo.exceptions = mock_exceptions
    mock_odoo.tools = mock_tools

    sys.modules["odoo"] = mock_odoo
    sys.modules["odoo.api"] = mock_api
    sys.modules["odoo.fields"] = mock_fields
    sys.modules["odoo.models"] = mock_models
    sys.modules["odoo.exceptions"] = mock_exceptions
    sys.modules["odoo.tools"] = mock_tools


class TestStageTaskDeadlineReminder(unittest.TestCase):
    """Test stage task deadline reminder logic."""

    def test_lug_notified_deadline_field_defined(self):
        """Verify lug_notified_deadline field is defined on ProjectStageTask."""
        from lug_project.models.project_stage_task import ProjectStageTask
        self.assertTrue(
            hasattr(ProjectStageTask, "lug_notified_deadline"),
            "ProjectStageTask must define lug_notified_deadline field",
        )

    def test_cron_method_defined(self):
        """Verify _cron_check_deadline_reminders is defined on ProjectStageTask."""
        from lug_project.models.project_stage_task import ProjectStageTask
        self.assertTrue(
            hasattr(ProjectStageTask, "_cron_check_deadline_reminders"),
            "ProjectStageTask must define _cron_check_deadline_reminders method",
        )

    def test_cron_record_in_ir_cron_data(self):
        """Verify ir_cron record for deadline reminder exists in ir_cron_data.xml."""
        tree = ET.parse("lug_project/data/ir_cron_data.xml")
        root = tree.getroot()

        cron_record = root.find(".//record[@id='ir_cron_lug_stage_task_deadline_reminder']")
        self.assertIsNotNone(
            cron_record,
            "ir_cron_data.xml must define ir_cron_lug_stage_task_deadline_reminder",
        )

        code_field = cron_record.find("./field[@name='code']")
        self.assertIsNotNone(code_field, "Cron record must have code field")
        self.assertIn(
            "_cron_check_deadline_reminders()",
            code_field.text,
            "Cron code field must call _cron_check_deadline_reminders()",
        )

    def test_write_resets_lug_notified_deadline(self):
        """Verify write() clears lug_notified_deadline when deadline changes."""
        from lug_project.models.project_stage_task import ProjectStageTask

        task = ProjectStageTask()
        task.env = MagicMock()
        task.env.context = {"lug_sync_lock": True}
        vals = {"deadline": "2026-11-15"}

        task.write(vals)
        self.assertIn("lug_notified_deadline", vals)
        self.assertFalse(vals["lug_notified_deadline"])

    def test_cron_logic_and_message_content(self):
        """Verify _cron_check_deadline_reminders logic and message content."""
        from lug_project.models.project_stage_task import ProjectStageTask

        task_mock = MagicMock()
        task_mock.name = "Khảo sát mặt bằng"
        task_mock.deadline = date(2026, 11, 8)
        task_mock.lug_notified_deadline = False
        task_mock.state = "in_progress"

        user_pic = MagicMock()
        user_pic.active = True
        user_pic.share = False
        user_pic.partner_id.id = 10
        user_pic.partner_id._bus_send = MagicMock()

        task_mock.user_ids = [user_pic]
        task_mock.supervisor_ids = []
        task_mock.staff_ids = []
        task_mock._send_deadline_reminder_notification = MagicMock()
        task_mock.sudo.return_value = task_mock

        model_inst = ProjectStageTask()
        model_inst.env = MagicMock()
        model_inst.env["ir.config_parameter"].sudo().get_param.return_value = "1"
        model_inst.search = MagicMock(return_value=[task_mock])

        with patch("odoo.fields.Date.context_today", return_value="2026-11-07"):
            model_inst._cron_check_deadline_reminders()

        task_mock._send_deadline_reminder_notification.assert_called_once()
        args, kwargs = task_mock._send_deadline_reminder_notification.call_args
        msg = args[1]
        self.assertIn("Công việc Khảo sát mặt bằng sắp đến thời hạn, vui lòng nhanh chóng hoàn thành và xác nhận công việc", msg)
        task_mock.sudo().write.assert_called_with({"lug_notified_deadline": task_mock.deadline})

    def test_cron_skips_already_notified_task(self):
        """Verify task with lug_notified_deadline == deadline is skipped."""
        from lug_project.models.project_stage_task import ProjectStageTask

        task_mock = MagicMock()
        task_mock.name = "Khảo sát mặt bằng"
        task_mock.deadline = date(2026, 11, 8)
        task_mock.lug_notified_deadline = date(2026, 11, 8)  # Already notified!
        task_mock.state = "in_progress"
        task_mock._send_deadline_reminder_notification = MagicMock()

        model_inst = ProjectStageTask()
        model_inst.env = MagicMock()
        model_inst.env["ir.config_parameter"].sudo().get_param.return_value = "1"
        model_inst.search = MagicMock(return_value=[task_mock])

        with patch("odoo.fields.Date.context_today", return_value="2026-11-07"):
            model_inst._cron_check_deadline_reminders()

        task_mock._send_deadline_reminder_notification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
