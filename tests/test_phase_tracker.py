# -*- coding: utf-8 -*-
"""
Unit tests for phase tracker pills logic (_lug_phase_tracker in project_dashboard.py
and _compute_project_phase in project_project.py).
"""

import sys
import unittest
from unittest.mock import MagicMock

# 1. Setup mocks before importing
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model = lambda f: f
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Date.context_today = MagicMock(return_value="2026-10-05")
mock_fields.Date.to_date = lambda d: d
mock_fields.Datetime.now = MagicMock()
mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Boolean = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)

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
mock_models.AbstractModel = MockModel
mock_models.TransientModel = MockModel


import types

class ExceptionsModule(types.ModuleType):
    def __getattr__(self, name):
        cls = type(name, (Exception,), {})
        setattr(self, name, cls)
        return cls

exceptions_mod = ExceptionsModule("odoo.exceptions")
ValidationError = type("ValidationError", (Exception,), {})
UserError = type("UserError", (Exception,), {})
AccessError = type("AccessError", (Exception,), {})
exceptions_mod.ValidationError = ValidationError
exceptions_mod.UserError = UserError
exceptions_mod.AccessError = AccessError

mock_tools = MagicMock()
mock_tools.html2plaintext = lambda s: s

mock_odoo.__path__ = []
mock_odoo.api = mock_api
mock_odoo.fields = mock_fields
mock_odoo.models = mock_models
mock_odoo.exceptions = exceptions_mod
mock_odoo.tools = mock_tools

sys.modules["odoo"] = mock_odoo
sys.modules["odoo.api"] = mock_api
sys.modules["odoo.fields"] = mock_fields
sys.modules["odoo.models"] = mock_models
sys.modules["odoo.exceptions"] = exceptions_mod
sys.modules["odoo.tools"] = mock_tools

mock_dateutil = MagicMock()
mock_relativedelta = MagicMock()
mock_dateutil.relativedelta = mock_relativedelta
sys.modules["dateutil"] = mock_dateutil
sys.modules["dateutil.relativedelta"] = mock_relativedelta

from lug_project.models.project_dashboard import ProjectProjectDashboard
from lug_project.models.project_project import ProjectProject


class DummyTask:
    def __init__(self, state="draft"):
        self.state = state


class DummyStageLine:
    def __init__(self, sequence=10, id=1, name="Giai đoạn 1", tasks=None):
        self.sequence = sequence
        self.id = id
        self.name = name
        self.task_ids = tasks or []


class DummyStageLineSet(list):
    def sorted(self, key):
        return DummyStageLineSet(sorted(self, key=key))


class TestPhaseTracker(unittest.TestCase):
    def setUp(self):
        self.dashboard = ProjectProjectDashboard()
        self.dashboard.env = {"project.stage.task": []}

    def test_no_tasks_in_any_stage(self):
        """When 0 tasks exist in any stage, all pills must be 'todo' (not active/yellow)."""
        project = MagicMock()
        lines = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[]),
            DummyStageLine(30, 3, "GĐ 3: Nghiệm thu", tasks=[]),
            DummyStageLine(40, 4, "GĐ 4: Đóng DA", tasks=[]),
        ])
        project.stage_line_ids = lines

        result = self.dashboard._lug_phase_tracker(project)
        states = [step["state"] for step in result["steps"]]
        self.assertEqual(states, ["todo", "todo", "todo", "todo"])

    def test_stage_1_has_in_progress_task(self):
        """When stage 1 has task in progress, only stage 1 is active; others remain todo."""
        project = MagicMock()
        lines = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[DummyTask("in_progress")]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[]),
            DummyStageLine(30, 3, "GĐ 3: Nghiệm thu", tasks=[]),
            DummyStageLine(40, 4, "GĐ 4: Đóng DA", tasks=[]),
        ])
        project.stage_line_ids = lines

        result = self.dashboard._lug_phase_tracker(project)
        states = [step["state"] for step in result["steps"]]
        self.assertEqual(states, ["active", "todo", "todo", "todo"])

    def test_stage_1_has_draft_task(self):
        """When stage 1 has task in draft, only stage 1 is active (color changes); others remain todo."""
        project = MagicMock()
        lines = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[DummyTask("draft")]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[]),
            DummyStageLine(30, 3, "GĐ 3: Nghiệm thu", tasks=[]),
            DummyStageLine(40, 4, "GĐ 4: Đóng DA", tasks=[]),
        ])
        project.stage_line_ids = lines

        result = self.dashboard._lug_phase_tracker(project)
        states = [step["state"] for step in result["steps"]]
        self.assertEqual(states, ["active", "todo", "todo", "todo"])

    def test_stage_1_done_stage_2_empty(self):
        """When stage 1 is done and stage 2 has 0 tasks, stage 2 must NOT be active (yellow)."""
        project = MagicMock()
        lines = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[DummyTask("done")]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[]),
            DummyStageLine(30, 3, "GĐ 3: Nghiệm thu", tasks=[]),
            DummyStageLine(40, 4, "GĐ 4: Đóng DA", tasks=[]),
        ])
        project.stage_line_ids = lines

        result = self.dashboard._lug_phase_tracker(project)
        states = [step["state"] for step in result["steps"]]
        self.assertEqual(states, ["done", "todo", "todo", "todo"])

    def test_stage_1_done_stage_2_in_progress(self):
        """When stage 1 is done and stage 2 has in_progress task, stage 1 is done, stage 2 is active, others todo."""
        project = MagicMock()
        lines = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[DummyTask("done")]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[DummyTask("in_progress")]),
            DummyStageLine(30, 3, "GĐ 3: Nghiệm thu", tasks=[]),
            DummyStageLine(40, 4, "GĐ 4: Đóng DA", tasks=[]),
        ])
        project.stage_line_ids = lines

        result = self.dashboard._lug_phase_tracker(project)
        states = [step["state"] for step in result["steps"]]
        self.assertEqual(states, ["done", "active", "todo", "todo"])

    def test_stage_compute_project_phase_no_tasks(self):
        """_compute_project_phase sets phase_num = 0 when no stage has tasks."""
        proj = ProjectProject()
        proj.stage_id = MagicMock(name=False)
        proj._lug_phase_from_name = lambda name: False
        proj.stage_line_ids = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[]),
            DummyStageLine(20, 2, "GĐ 2: Thực hiện", tasks=[]),
        ])
        ProjectProject._compute_project_phase(proj)
        self.assertEqual(proj.phase_num, 0)


if __name__ == "__main__":
    unittest.main()
