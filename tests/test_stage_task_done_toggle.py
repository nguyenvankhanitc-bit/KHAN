# -*- coding: utf-8 -*-
"""
Unit test for 'Hoàn thành' stage task checkbox toggle in lug_project.
"""

import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

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
    mock_fields.Date.context_today = MagicMock(return_value=date(2026, 11, 6))
    mock_fields.Date.to_date = lambda d: d

    mock_models = MagicMock()

    class MockModel:
        _name = "mock.model"
        _inherit = ""

        def __init__(self, *args, **kwargs):
            pass

    mock_models.Model = MockModel
    mock_exceptions = MagicMock()
    mock_exceptions.ValidationError = Exception
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
from lug_project.models.project_dashboard import ProjectProjectDashboard


class TestStageTaskDoneToggle(unittest.TestCase):
    def setUp(self):
        self.task = ProjectStageTask()
        self.task.id = 42
        self.task.state = "draft"
        self.task.execution_date = None
        self.task.deadline = date(2026, 11, 10)
        self.task.notes = "Test task notes"

        # Mock project & stage
        self.mock_stage = MagicMock()
        self.mock_project = MagicMock()
        self.mock_project.id = 100
        self.mock_project._lug_check_list_write = MagicMock()
        self.mock_project.lug_progress_pct = 50

        # Link project and task
        self.task.stage_id = self.mock_stage
        self.task.project_id = self.mock_project
        self.mock_stage.project_id = self.mock_project

        all_tasks = [self.task]
        self.mock_project.stage_line_ids.task_ids = MagicMock()
        self.mock_project.stage_line_ids.task_ids.filtered = lambda fn: [t for t in all_tasks if fn(t)]
        self.mock_project.stage_line_ids.task_ids.__len__ = lambda s: len(all_tasks)

        # Mock ensure_one & write
        self.task.ensure_one = MagicMock()
        def mock_write(vals):
            for k, v in vals.items():
                setattr(self.task, k, v)
            return True
        self.task.write = MagicMock(side_effect=mock_write)

        # Mock env
        mock_env = MagicMock()
        mock_env["project.project"] = MagicMock()
        mock_env["project.project"]._lug_task_timeleft_meta.return_value = {
            "state": "ok",
            "label": "Còn 4 ngày",
            "short": "Còn 4 ngày",
        }
        mock_env["project.project"]._LUG_TASK_STATE_LABELS = {
            "draft": "Chưa bắt đầu",
            "in_progress": "Đang làm",
            "done": "Hoàn thành",
        }
        self.task.env = mock_env

    def test_toggle_done_to_true(self):
        """Testing checking the checkbox (is_done=True)."""
        res = self.task.lug_toggle_done(is_done=True)
        self.task.write.assert_called_with({"state": "done"})
        self.assertEqual(res["task_id"], 42)
        self.assertEqual(res["state"], "done")
        self.assertTrue(res["is_done"])
        self.assertEqual(res["state_label"], "Hoàn thành")

    def test_toggle_done_to_false_no_exec_date(self):
        """Testing unchecking when task has no execution_date -> reverts to draft."""
        self.task.state = "done"
        self.task.execution_date = None
        res = self.task.lug_toggle_done(is_done=False)
        self.task.write.assert_called_with({"state": "draft"})
        self.assertEqual(res["state"], "draft")
        self.assertFalse(res["is_done"])
        self.assertEqual(res["state_label"], "Chưa bắt đầu")

    def test_toggle_done_to_false_with_past_exec_date(self):
        """Testing unchecking when task has past/today execution_date -> reverts to in_progress."""
        self.task.state = "done"
        self.task.execution_date = date(2026, 10, 1)
        res = self.task.lug_toggle_done(is_done=False)
        self.task.write.assert_called_with({"state": "in_progress"})
        self.assertEqual(res["state"], "in_progress")
        self.assertFalse(res["is_done"])
        self.assertEqual(res["state_label"], "Đang làm")

    def test_toggle_done_toggle_without_arg(self):
        """Testing toggle without passing is_done (inverts current state)."""
        self.task.state = "draft"
        res1 = self.task.lug_toggle_done()
        self.assertEqual(res1["state"], "done")
        self.assertTrue(res1["is_done"])

        res2 = self.task.lug_toggle_done()
        self.assertEqual(res2["state"], "draft")
        self.assertFalse(res2["is_done"])

    def test_project_dashboard_lug_toggle_stage_task_done(self):
        """Testing project dashboard RPC delegating to stage task."""
        dash = ProjectProjectDashboard()
        mock_env = MagicMock()
        mock_task_model = MagicMock()
        mock_task_rec = MagicMock()
        mock_task_rec.exists.return_value = self.task
        mock_task_model.browse.return_value = mock_task_rec
        mock_env.__getitem__.side_effect = lambda key: mock_task_model if key == "project.stage.task" else MagicMock()
        dash.env = mock_env

        res = dash.lug_toggle_stage_task_done(42, is_done=True)
        mock_task_model.browse.assert_called_with(42)
        self.assertEqual(res["state"], "done")


if __name__ == "__main__":
    unittest.main()
