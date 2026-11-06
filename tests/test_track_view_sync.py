# -*- coding: utf-8 -*-
"""
Unit tests for "Theo dõi dự án" (track view) data sync, permissions, and modal task contract.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock

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
mock_fields.Html = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Monetary = MagicMock(side_effect=lambda **kwargs: kwargs)

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
mock_models.Constraint = MagicMock(side_effect=lambda *args, **kwargs: (args, kwargs))


class ExceptionsModule(types.ModuleType):
    def __getattr__(self, name):
        cls = type(name, (Exception,), {})
        setattr(self, name, cls)
        return cls


if "odoo.exceptions" in sys.modules and hasattr(sys.modules["odoo.exceptions"], "ValidationError"):
    exceptions_mod = sys.modules["odoo.exceptions"]
else:
    exceptions_mod = ExceptionsModule("odoo.exceptions")
    exceptions_mod.ValidationError = type("ValidationError", (Exception,), {})
    exceptions_mod.UserError = type("UserError", (Exception,), {})
    exceptions_mod.AccessError = type("AccessError", (Exception,), {})

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

from lug_project.models.project_app_perm import LIST_GROUPS, ProjectProjectAppPerm
from lug_project.models.project_project import ProjectProject


class DummyTask:
    def __init__(self, state="draft", lug_status="todo", lug_progress=0, is_closed=False):
        self.state = state
        self.lug_status = lug_status
        self.lug_progress = lug_progress
        self.is_closed = is_closed
        self.stage_id = MagicMock(fold=False)


class DummyTaskSet(list):
    def filtered(self, func):
        return DummyTaskSet([x for x in self if func(x)])


class DummyStageLine:
    def __init__(self, sequence=10, id=1, name="Giai đoạn 1", tasks=None):
        self.sequence = sequence
        self.id = id
        self.name = name
        self.task_ids = DummyTaskSet(tasks or [])


class DummyStageLineSet(list):
    def sorted(self, key):
        return DummyStageLineSet(sorted(self, key=key))

    @property
    def task_ids(self):
        all_tasks = []
        for line in self:
            all_tasks.extend(line.task_ids)
        return DummyTaskSet(all_tasks)


class TestTrackBackendSync(unittest.TestCase):
    def test_track_in_list_groups(self):
        """LIST_GROUPS must include 'track' so _lug_list_perm_group honors lug_perm_group='track'."""
        self.assertIn("track", LIST_GROUPS)
        rec = ProjectProjectAppPerm()
        rec.env = MagicMock()
        rec.env.context = {"lug_perm_group": "track"}
        self.assertEqual(rec._lug_list_perm_group(), "track")
        self.assertEqual(rec._lug_list_perm_group(archived=True), "archived")
        self.assertEqual(rec._lug_list_perm_group(overdue=True), "overdue")

    def test_unknown_perm_group_falls_back_to_list(self):
        rec = ProjectProjectAppPerm()
        rec.env = MagicMock()
        rec.env.context = {"lug_perm_group": "unknown_group"}
        self.assertEqual(rec._lug_list_perm_group(), "list")

    def test_compute_project_progress_matches_lug_progress_pct(self):
        """_compute_project_progress and _compute_lug_progress_pct must agree for both stage tasks and legacy tasks."""
        proj = ProjectProject()
        proj.stage_line_ids = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1", tasks=[DummyTask(state="done"), DummyTask(state="draft")]),
        ])
        proj.task_ids = DummyTaskSet([])
        ProjectProject._compute_lug_progress_pct(proj)
        ProjectProject._compute_project_progress(proj)
        self.assertEqual(proj.lug_progress_pct, 50)
        self.assertEqual(proj.progress, 50.0)

        # Legacy tasks with lug_progress
        proj_legacy = ProjectProject()
        proj_legacy.stage_line_ids = DummyStageLineSet([])
        proj_legacy.task_ids = DummyTaskSet([
            DummyTask(lug_progress=40),
            DummyTask(lug_progress=80),
        ])
        ProjectProject._compute_lug_progress_pct(proj_legacy)
        ProjectProject._compute_project_progress(proj_legacy)
        self.assertEqual(proj_legacy.lug_progress_pct, 60)
        self.assertEqual(proj_legacy.progress, 60.0)

    def test_compute_project_phase_done_workflow_state(self):
        """When lug_workflow_state is 'done', _compute_project_phase sets phase_num = 4."""
        proj = ProjectProject()
        proj.lug_workflow_state = "done"
        proj.stage_id = MagicMock(name=False)
        proj.stage_line_ids = DummyStageLineSet([
            DummyStageLine(10, 1, "GĐ 1: Chuẩn bị", tasks=[DummyTask("draft")]),
        ])
        ProjectProject._compute_project_phase(proj)
        self.assertEqual(proj.phase_num, 4)


if __name__ == "__main__":
    unittest.main()
