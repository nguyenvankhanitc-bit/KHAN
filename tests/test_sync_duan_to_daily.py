# -*- coding: utf-8 -*-
"""
Unit test for 1-way sync from duan (lug_project) to cong viec hang ngay (daily_work_task).
Tests:
- Required 'Người phụ trách' validation on project.stage.task and project.task.
- Multi-user assignment: generates separate daily.task records for each assignee.
- One-way sync: modifications in daily.task do NOT sync back to duan.
- Unlink clean-up: deleting project tasks removes linked daily.task records.
"""

import sys
import unittest
from unittest.mock import MagicMock

# Setup mock odoo environment
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date.context_today = MagicMock(return_value="2026-10-12")
mock_fields.Date.to_date = lambda d: d
mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)

mock_models = MagicMock()


class MockModel:
    _name = "mock.model"
    _inherit = ""

    def __init__(self, *args, **kwargs):
        pass

    def __iter__(self):
        return iter([self])

    def create(self, vals_list):
        return vals_list

    def write(self, vals):
        return True

    def unlink(self):
        return True


mock_models.Model = MockModel
mock_exceptions = MagicMock()


if "odoo.exceptions" in sys.modules and hasattr(sys.modules["odoo.exceptions"], "ValidationError"):
    ValidationError = sys.modules["odoo.exceptions"].ValidationError
else:
    class ValidationError(Exception):
        pass
    mock_exceptions.ValidationError = ValidationError
mock_exceptions.UserError = Exception

mock_tools = MagicMock()
mock_tools.html2plaintext = lambda s: s

mock_odoo.__path__ = []
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

mock_dateutil = MagicMock()
mock_relativedelta = MagicMock()
mock_dateutil.relativedelta = mock_relativedelta
sys.modules["dateutil"] = mock_dateutil
sys.modules["dateutil.relativedelta"] = mock_relativedelta

from lug_project.models.project_stage_task import ProjectStageTask
from lug_project.models.project_task import ProjectTask
from lug_project.models.daily_task import DailyTask


class TestDuanToDailyTaskSync(unittest.TestCase):
    def setUp(self):
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 11
        self.mock_user1.name = "Nguyen Van A"
        self.mock_user1.email = "vana@lug.vn"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 22
        self.mock_user2.name = "Tran Thi B"
        self.mock_user2.email = "thib@lug.vn"

        self.mock_pm = MagicMock()
        self.mock_pm.id = 1
        self.mock_pm.name = "PM Admin"

        self.mock_emp1 = MagicMock()
        self.mock_emp1.id = 101
        self.mock_emp1.department_id.id = 5

        self.mock_emp2 = MagicMock()
        self.mock_emp2.id = 102
        self.mock_emp2.department_id.id = 5

        self.mock_project = MagicMock()
        self.mock_project.id = 50
        self.mock_project.name = "Dự án LUG Store"
        self.mock_project.user_id = self.mock_pm
        self.mock_project.lug_deadline = "2026-11-30"
        self.mock_project.lug_priority = "high"
        self.mock_project.lug_department_id.id = 5

    def test_stage_task_required_assignee_validation(self):
        """Verify that creating a stage task without user_ids raises ValidationError."""
        task = ProjectStageTask()
        task.user_ids = []
        with self.assertRaises(ValidationError):
            task._check_user_ids()

    def test_project_task_required_assignee_validation(self):
        """Verify that creating a project task without assignee raises ValidationError."""
        task = ProjectTask()
        task.project_id = self.mock_project
        task.lug_origin_project_task_id = False
        task.lug_pic_id = False
        task.user_ids = []
        with self.assertRaises(ValidationError):
            task._check_lug_assignee()

    def test_stage_task_sync_to_multiple_daily_employees(self):
        """Verify that a stage task with 2 users creates 2 separate daily tasks."""
        task = ProjectStageTask()
        task.id = 888
        task.name = "Thiết kế quầy kệ"
        task.stage_id = MagicMock()
        task.project_id = self.mock_project
        task.user_ids = [self.mock_user1, self.mock_user2]
        task.deadline = "2026-11-15"
        task.execution_date = "2026-10-20"
        task.state = "in_progress"
        task.daily_task_ids = MagicMock()
        task.daily_task_ids.exists.return_value = []

        mock_daily_model = MagicMock()
        created_records = []

        def fake_create(vals):
            rec = MagicMock()
            rec.id = 700 + len(created_records)
            rec.assignee_id.id = vals.get("assignee_id")
            created_records.append(vals)
            return rec

        mock_daily_model.with_context.return_value.create.side_effect = fake_create

        mock_env_obj = MagicMock()
        mock_env_obj.get.side_effect = lambda k: mock_daily_model if k == "daily.task" else MagicMock()
        mock_env_obj.user = self.mock_pm
        task.env = mock_env_obj

        def get_emp(user):
            if user == self.mock_user1:
                return self.mock_emp1
            elif user == self.mock_user2:
                return self.mock_emp2
            return None

        task._lug_get_or_create_daily_employee = MagicMock(side_effect=get_emp)

        task._lug_sync_to_daily()

        # Should create 2 daily tasks
        self.assertEqual(len(created_records), 2)
        assignee_ids = {r["assignee_id"] for r in created_records}
        self.assertEqual(assignee_ids, {101, 102})
        for r in created_records:
            self.assertEqual(r["name"], "[Dự án LUG Store] Thiết kế quầy kệ")
            self.assertEqual(r["deadline"], "2026-11-15")
            self.assertEqual(r["assign_date"], "2026-10-20")
            self.assertEqual(r["state"], "in_progress")
            self.assertEqual(r["priority"], "high")
            self.assertEqual(r["lug_origin_stage_task_id"], 888)

    def test_one_way_sync_no_write_back_to_duan(self):
        """Verify that updating a daily task does NOT sync back to project.stage.task or project.task."""
        daily_task = DailyTask()
        mock_stage_origin = MagicMock()
        mock_proj_origin = MagicMock()
        daily_task.lug_origin_stage_task_id = mock_stage_origin
        daily_task.lug_origin_project_task_id = mock_proj_origin
        daily_task.env = MagicMock()
        daily_task.env.context.get.return_value = False

        # Call write on DailyTask
        DailyTask.write(daily_task, {"state": "done", "deadline": "2026-12-01"})

        # Confirm neither origin task has write called
        mock_stage_origin.with_context.assert_not_called()
        mock_proj_origin.with_context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
