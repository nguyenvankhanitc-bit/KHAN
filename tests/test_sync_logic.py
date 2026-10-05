# -*- coding: utf-8 -*-
"""
Standalone Unit Test for sync logic between lug_project, project_todo, and daily_work_task.
Mocks odoo framework primitives so it runs without full Odoo dependencies.
"""

import sys
import unittest
from unittest.mock import MagicMock

# 1. Mock odoo modules before importing project_task / daily_task
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date.context_today = MagicMock(return_value="2026-10-05")
mock_fields.Date.to_date = lambda d: d

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
mock_exceptions.ValidationError = Exception

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

# 2. Import the classes under test
from lug_project.models.project_task import ProjectTask
from lug_project.models.daily_task import DailyTask


class TestSyncLogic(unittest.TestCase):
    def setUp(self):
        self.mock_user = MagicMock()
        self.mock_user.id = 42
        self.mock_user.name = "Nguyen Van A"
        self.mock_user.email = "vana@lug.vn"
        self.mock_user.login = "vana@lug.vn"

        self.mock_pm = MagicMock()
        self.mock_pm.id = 1
        self.mock_pm.name = "PM Admin"

        self.mock_daily_emp = MagicMock()
        self.mock_daily_emp.id = 101
        self.mock_daily_emp.department_id.id = 5

        self.mock_project = MagicMock()
        self.mock_project.id = 10
        self.mock_project.name = "Dự án Nâng cấp Hệ thống"
        self.mock_project.user_id = self.mock_pm
        self.mock_project.lug_deadline = "2026-12-31"
        self.mock_project.lug_priority = "high"
        self.mock_project.lug_department_id.id = 5

    def test_sync_to_todo_and_daily_creation(self):
        """Verify that when a project task is created, a To-Do and a Daily Task are generated."""
        task = ProjectTask()
        task.project_id = self.mock_project
        task.lug_origin_project_task_id = False
        task.lug_pic_id = self.mock_user
        task.user_ids = [self.mock_user]
        task.name = "Khảo sát mặt bằng"
        task.date_deadline = "2026-10-15"
        task.lug_status = "progress"
        task.lug_todo_task_id = False
        task.lug_daily_task_id = False
        task.id = 999

        # Mock env
        mock_todo_model = MagicMock()
        mock_daily_model = MagicMock()
        mock_emp_model = MagicMock()

        mock_env = {
            "daily.task.employee": mock_emp_model,
            "daily.task": mock_daily_model,
            "project.task": mock_todo_model,
        }
        mock_env_obj = MagicMock()
        mock_env_obj.__getitem__.side_effect = lambda k: mock_env[k]
        mock_env_obj.get.side_effect = lambda k: mock_env.get(k)
        mock_env_obj.user = self.mock_pm
        task.env = mock_env_obj

        # Helper mock for employee resolution
        task._lug_get_or_create_daily_employee = MagicMock(return_value=self.mock_daily_emp)

        # Mock create returns
        mock_todo_created = MagicMock()
        mock_todo_created.id = 501
        mock_todo_model.with_context.return_value.create.return_value = mock_todo_created

        mock_daily_created = MagicMock()
        mock_daily_created.id = 601
        mock_daily_model.with_context.return_value.create.return_value = mock_daily_created

        # Mock write on task
        task.write = MagicMock()
        task.with_context = MagicMock(return_value=task)

        # Run sync method
        task._lug_sync_to_todo_and_daily()

        # Assert To-Do created
        mock_todo_model.with_context.assert_called_with(lug_sync_lock=True)
        todo_args = mock_todo_model.with_context.return_value.create.call_args[0][0]
        self.assertEqual(todo_args["name"], "[Dự án Nâng cấp Hệ thống] Khảo sát mặt bằng")
        self.assertFalse(todo_args["project_id"])
        self.assertEqual(todo_args["user_ids"], [(6, 0, [42])])
        self.assertEqual(todo_args["date_deadline"], "2026-10-15")
        self.assertEqual(todo_args["state"], "01_in_progress")
        self.assertEqual(todo_args["lug_origin_project_task_id"], 999)

        # Assert Daily Task created
        mock_daily_model.with_context.assert_called_with(lug_sync_lock=True)
        daily_args = mock_daily_model.with_context.return_value.create.call_args[0][0]
        self.assertEqual(daily_args["name"], "[Dự án Nâng cấp Hệ thống] Khảo sát mặt bằng")
        self.assertEqual(daily_args["assignee_id"], 101)
        self.assertEqual(daily_args["deadline"], "2026-10-15")
        self.assertEqual(daily_args["state"], "in_progress")
        self.assertEqual(daily_args["priority"], "high")
        self.assertEqual(daily_args["lug_origin_project_task_id"], 999)

    def test_sync_from_daily_task_to_project(self):
        """Verify that when a daily task is marked done, it syncs back to project task and todo."""
        daily_rec = DailyTask()
        origin_task = MagicMock()
        origin_task.exists.return_value = True
        origin_task.lug_status = "progress"
        origin_task.date_deadline = "2026-10-15"

        mock_todo = MagicMock()
        mock_todo.exists.return_value = True
        origin_task.lug_todo_task_id = mock_todo

        daily_rec.lug_origin_project_task_id = origin_task
        daily_rec.date_done = "2026-10-10"
        daily_rec.env = MagicMock()
        daily_rec.env.context.get.return_value = False

        origin_task.with_context.return_value.write = MagicMock()
        mock_todo.with_context.return_value.write = MagicMock()

        # Run write on DailyTask with state='done'
        DailyTask.write(daily_rec, {"state": "done"})

        # Check origin project task updated to done
        origin_task.with_context.assert_called_with(lug_sync_lock=True)
        origin_write_args = origin_task.with_context.return_value.write.call_args[0][0]
        self.assertEqual(origin_write_args["lug_status"], "done")
        self.assertEqual(origin_write_args["lug_done_date"], "2026-10-10")

        # Check todo updated to 1_done
        mock_todo.with_context.assert_called_with(lug_sync_lock=True)
        todo_write_args = mock_todo.with_context.return_value.write.call_args[0][0]
        self.assertEqual(todo_write_args["state"], "1_done")

    def test_sync_from_todo_to_project(self):
        """Verify that when a todo task is marked done, it syncs back to project task and daily task."""
        todo_rec = ProjectTask()
        origin_task = MagicMock()
        origin_task.exists.return_value = True
        origin_task.lug_status = "progress"
        origin_task.date_deadline = "2026-10-15"

        mock_daily = MagicMock()
        mock_daily.exists.return_value = True
        origin_task.lug_daily_task_id = mock_daily

        todo_rec.project_id = False
        todo_rec.lug_origin_project_task_id = origin_task
        todo_rec.env = MagicMock()

        origin_task.with_context.return_value.write = MagicMock()
        mock_daily.with_context.return_value.write = MagicMock()

        # Run _lug_sync_from_todo_to_project
        todo_rec._lug_sync_from_todo_to_project({"state": "1_done"})

        # Check project task updated
        origin_task.with_context.assert_called_with(lug_sync_lock=True)
        origin_args = origin_task.with_context.return_value.write.call_args[0][0]
        self.assertEqual(origin_args["lug_status"], "done")

        # Check daily task updated
        mock_daily.with_context.assert_called_with(lug_sync_lock=True)
        daily_args = mock_daily.with_context.return_value.write.call_args[0][0]
        self.assertEqual(daily_args["state"], "done")

    def test_recursion_lock_prevents_nested_sync(self):
        """Verify that when lug_sync_lock is True, no sync calls are triggered."""
        daily_rec = DailyTask()
        origin_task = MagicMock()
        daily_rec.lug_origin_project_task_id = origin_task
        daily_rec.env = MagicMock()
        daily_rec.env.context.get.return_value = True  # lock is active

        DailyTask.write(daily_rec, {"state": "done"})

        # origin_task should NOT be called because sync lock is on
        origin_task.with_context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
