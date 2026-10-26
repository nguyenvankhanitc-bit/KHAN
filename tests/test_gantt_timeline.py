# -*- coding: utf-8 -*-
"""
Unit tests for Gantt chart timeline matching in lug_project.
Tests that task progress bars match project startdate and deadline,
and correctly draw progress based on 'Ngày thực hiện' and 'Ngày hết hạn'.
"""

import sys
import unittest
from datetime import date, timedelta
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
    mock_fields.Date.context_today = MagicMock(return_value=date(2026, 10, 26))
    mock_fields.Date.to_date = lambda d: d
    mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Boolean = MagicMock(side_effect=lambda **kwargs: kwargs)

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

        def sudo(self):
            return self

        def search(self, *args, **kwargs):
            return []

        def with_context(self, *args, **kwargs):
            return self

        def ensure_one(self):
            pass

        def filtered(self, func):
            return [x for x in self if func(x)]

        def mapped(self, field):
            return []

    mock_models.Model = MockModel
    mock_models.TransientModel = MockModel
    class ValidationError(Exception):
        pass

    class UserError(Exception):
        pass

    mock_exceptions = MagicMock()
    mock_exceptions.ValidationError = ValidationError
    mock_exceptions.UserError = UserError

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

if "dateutil" not in sys.modules:
    class MockRelativedelta:
        def __init__(self, months=0, **kwargs):
            self.months = months

        def __radd__(self, other):
            if hasattr(other, "year") and hasattr(other, "month"):
                y = other.year
                m = other.month + self.months
                while m > 12:
                    m -= 12
                    y += 1
                while m < 1:
                    m += 12
                    y -= 1
                return other.replace(year=y, month=m, day=1)
            return other

    mock_dateutil = MagicMock()
    mock_dateutil.relativedelta = MockRelativedelta
    sys.modules["dateutil"] = mock_dateutil
    sys.modules["dateutil.relativedelta"] = mock_dateutil

from lug_project.models.project_dashboard import ProjectProjectDashboard
from lug_project.models.project_stage_line import ProjectStageLine


class TestGanttTimeline(unittest.TestCase):
    def setUp(self):
        self.dashboard = ProjectProjectDashboard()
        self.dashboard.env = MagicMock()
        self.today = date(2026, 10, 26)

    def test_gantt_clip_calculation(self):
        """Verify _lug_gantt_clip properly calculates start offset and span."""
        win_start = date(2026, 10, 1)
        win_end = date(2026, 10, 31)

        # Task from Oct 5 to Oct 12: offset should be 4 days, span 8 days (inclusive)
        clip = self.dashboard._lug_gantt_clip(date(2026, 10, 5), date(2026, 10, 12), win_start, win_end)
        self.assertIsNotNone(clip)
        self.assertEqual(clip, (4, 8))

        # Task exactly on window boundaries
        clip = self.dashboard._lug_gantt_clip(date(2026, 10, 1), date(2026, 10, 31), win_start, win_end)
        self.assertEqual(clip, (0, 31))

        # Task ending before window starts -> None
        clip = self.dashboard._lug_gantt_clip(date(2026, 9, 1), date(2026, 9, 20), win_start, win_end)
        self.assertIsNone(clip)

    def test_gantt_stage_task_timeline_matching(self):
        """Verify that project.stage.task draws progress on execution_date/deadline and matches project bounds."""
        proj_start = date(2026, 11, 1)
        proj_deadline = date(2026, 11, 30)

        mock_project = MagicMock()
        mock_project.id = 101
        mock_project.date_start = proj_start
        mock_project.lug_deadline = proj_deadline
        mock_project.date = False
        mock_project._lug_project_title.return_value = "Dự án Biệt thự A"
        mock_project.last_update_status = "on_track"
        mock_project.lug_assignee_ids = []
        mock_project.lug_pic_id = []
        mock_project.stage_line_ids = MagicMock()

        # Task 1: Both execution_date and deadline set
        stask1 = MagicMock()
        stask1.id = 1
        stask1.project_id = mock_project
        stask1.name = "Khảo sát mặt bằng"
        stask1.execution_date = date(2026, 11, 5)
        stask1.deadline = date(2026, 11, 10)
        stask1.state = "done"
        stask1.user_ids = []
        stask1.supervisor_ids = []

        # Task 2: No execution_date -> must fallback to project startdate (2026-11-01)
        stask2 = MagicMock()
        stask2.id = 2
        stask2.project_id = mock_project
        stask2.name = "Thiết kế 3D"
        stask2.execution_date = False
        stask2.deadline = date(2026, 11, 20)
        stask2.state = "in_progress"
        stask2.user_ids = []
        stask2.supervisor_ids = []

        # Task 3: No deadline -> must fallback to project deadline (2026-11-30)
        stask3 = MagicMock()
        stask3.id = 3
        stask3.project_id = mock_project
        stask3.name = "Sản xuất nội thất"
        stask3.execution_date = date(2026, 11, 15)
        stask3.deadline = False
        stask3.state = "draft"
        stask3.user_ids = []
        stask3.supervisor_ids = []

        # Task 4: Neither date set -> matches full project duration (2026-11-01 to 2026-11-30)
        stask4 = MagicMock()
        stask4.id = 4
        stask4.project_id = mock_project
        stask4.name = "Bàn giao"
        stask4.execution_date = False
        stask4.deadline = False
        stask4.state = "draft"
        stask4.user_ids = []
        stask4.supervisor_ids = []

        # Setup mock env search for project.stage.task
        mock_stage_task_model = MagicMock()
        mock_stage_task_model.search.return_value = [stask1, stask2, stask3, stask4]

        env_dict = {
            "project.stage.task": mock_stage_task_model,
            "project.task": MagicMock(search=MagicMock(return_value=[])),
            "project.milestone": MagicMock(search=MagicMock(return_value=[])),
        }
        self.dashboard.env.__contains__.side_effect = lambda key: key in env_dict
        self.dashboard.env.__getitem__.side_effect = lambda key: env_dict[key]

        projects = [mock_project]
        rows, axis, today_pct, cal = self.dashboard._lug_gantt_data(projects, self.today)

        # Verify project row
        proj_row = next(r for r in rows if r["kind"] == "project")
        self.assertEqual(proj_row["project_id"], 101)
        self.assertEqual(proj_row["name"], "Dự án Biệt thự A")

        # Verify Task 1: 2026-11-05 to 2026-11-10
        task1_row = next(r for r in rows if r["res_id"] == 1 and r["kind"] == "task")
        self.assertEqual(task1_row["label"], "Hoàn thành")
        self.assertEqual(task1_row["model"], "project.stage.task")

        # Verify Task 2: starts at project startdate (2026-11-01)
        task2_row = next(r for r in rows if r["res_id"] == 2 and r["kind"] == "task")
        self.assertEqual(task2_row["label"], "Đang làm")
        self.assertEqual(task2_row["model"], "project.stage.task")

        # Verify Task 3: ends at project deadline (2026-11-30)
        task3_row = next(r for r in rows if r["res_id"] == 3 and r["kind"] == "task")
        self.assertEqual(task3_row["label"], "Chưa bắt đầu")
        self.assertEqual(task3_row["model"], "project.stage.task")

        # Verify Task 4: spans project start (2026-11-01) to project deadline (2026-11-30)
        task4_row = next(r for r in rows if r["res_id"] == 4 and r["kind"] == "task")
        self.assertEqual(task4_row["start"], proj_row["start"])
        self.assertEqual(task4_row["span"], proj_row["span"])

    def test_gantt_native_task_timeline_matching(self):
        """Verify that native project.task uses lug_execution_date and date_deadline."""
        proj_start = date(2026, 12, 1)
        proj_deadline = date(2026, 12, 25)

        mock_project = MagicMock()
        mock_project.id = 202
        mock_project.date_start = proj_start
        mock_project.lug_deadline = proj_deadline
        mock_project.date = False
        mock_project._lug_project_title.return_value = "Dự án Văn phòng B"
        mock_project.last_update_status = "done"
        mock_project.lug_assignee_ids = []
        mock_project.lug_pic_id = []
        mock_project.stage_line_ids = False
        mock_project.task_ids = MagicMock(user_ids=[], lug_supervisor_id=[])

        ntask1 = MagicMock()
        ntask1.id = 55
        ntask1.project_id = mock_project
        ntask1.name = "Nhiệm vụ thi công"
        ntask1.lug_execution_date = date(2026, 12, 5)
        ntask1.date_deadline = date(2026, 12, 15)
        ntask1.date_end = False
        ntask1.date_assign = False
        ntask1.state = "01_in_progress"
        ntask1.user_ids = []
        ntask1.lug_pic_id = []
        ntask1.lug_supervisor_id = []

        env_dict = {
            "project.stage.task": MagicMock(search=MagicMock(return_value=[])),
            "project.task": MagicMock(search=MagicMock(return_value=[ntask1])),
            "project.milestone": MagicMock(search=MagicMock(return_value=[])),
        }
        self.dashboard.env.__contains__.side_effect = lambda key: key in env_dict
        self.dashboard.env.__getitem__.side_effect = lambda key: env_dict[key]

        rows, axis, today_pct, cal = self.dashboard._lug_gantt_data([mock_project], self.today)
        task_row = next(r for r in rows if r["res_id"] == 55 and r["kind"] == "task")
        self.assertEqual(task_row["model"], "project.task")
        self.assertEqual(task_row["label"], "Đang thực hiện")

    def test_stage_line_action_add_task_popup_defaults(self):
        """Verify action_add_task_popup defaults execution_date and deadline to project dates."""
        line = ProjectStageLine()
        line.id = 10
        line.ensure_one = MagicMock()
        mock_proj = MagicMock()
        mock_proj.id = 99
        mock_proj.date_start = date(2026, 11, 10)
        mock_proj.lug_deadline = date(2026, 11, 28)
        mock_proj.date = False
        mock_proj.lug_pic_id = False
        line.project_id = mock_proj
        line.env = MagicMock()
        mock_view = MagicMock()
        mock_view.id = 888
        line.env.ref.return_value = mock_view

        action = line.action_add_task_popup()
        ctx = action.get("context", {})
        self.assertEqual(ctx.get("default_execution_date"), date(2026, 11, 10))
        self.assertEqual(ctx.get("default_deadline"), date(2026, 11, 28))


if __name__ == "__main__":
    unittest.main()
