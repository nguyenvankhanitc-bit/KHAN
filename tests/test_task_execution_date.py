# -*- coding: utf-8 -*-
"""
Unit test for 'Ngày thực hiện' (execution date) field in lug_project.
Tests project.stage.task and project.task field definitions and properties.
"""

import sys
import unittest
from unittest.mock import MagicMock

# Setup mock odoo environment if not already loaded
if "odoo" not in sys.modules:
    mock_odoo = MagicMock()
    mock_api = MagicMock()
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
    mock_fields.Date.context_today = MagicMock(return_value="2026-10-09")
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
from lug_project.models.project_task import ProjectTask


class TestTaskExecutionDate(unittest.TestCase):
    def test_project_stage_task_execution_date_field(self):
        """Verify execution_date field on project.stage.task."""
        self.assertTrue(
            hasattr(ProjectStageTask, "execution_date"),
            "ProjectStageTask must define execution_date field",
        )
        field_kwargs = getattr(ProjectStageTask, "execution_date")
        if isinstance(field_kwargs, dict):
            self.assertEqual(field_kwargs.get("string"), "Ngày thực hiện")

    def test_project_task_lug_execution_date_field(self):
        """Verify lug_execution_date field on project.task."""
        self.assertTrue(
            hasattr(ProjectTask, "lug_execution_date"),
            "ProjectTask must define lug_execution_date field",
        )
        field_kwargs = getattr(ProjectTask, "lug_execution_date")
        if isinstance(field_kwargs, dict):
            self.assertEqual(field_kwargs.get("string"), "Ngày thực hiện")
            self.assertFalse(field_kwargs.get("copy", True), "lug_execution_date should have copy=False")


if __name__ == "__main__":
    unittest.main()
