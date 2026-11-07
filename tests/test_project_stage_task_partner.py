# -*- coding: utf-8 -*-
"""
Unit test for 'Đối tác' (partner_name) field in lug_project.
Tests project.stage.task and project.task field definitions and isolation from daily.task.
"""

import sys
import unittest
from unittest.mock import MagicMock

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
    mock_fields.Date = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Char = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Float = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Integer = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Text = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Date.context_today = MagicMock(return_value="2026-11-07")
    mock_fields.Date.to_date = lambda d: (
        __import__("datetime").date.fromisoformat(d) if isinstance(d, str) else d
    )

    mock_models = MagicMock()

    class MockModel:
        _name = "mock.model"
        _inherit = ""

        def __init__(self, *args, **kwargs):
            pass

        def write(self, vals):
            return True

        def sudo(self):
            return self

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


class TestProjectStageTaskPartner(unittest.TestCase):
    """Test 'Đối tác' field definition and isolation."""

    def test_partner_name_field_defined_on_stage_task(self):
        """Verify project.stage.task has partner_name field."""
        from lug_project.models.project_stage_task import ProjectStageTask
        self.assertTrue(
            hasattr(ProjectStageTask, "partner_name"),
            "ProjectStageTask must define partner_name field",
        )

    def test_partner_name_field_defined_on_project_task(self):
        """Verify project.task has lug_partner_name field."""
        from lug_project.models.project_task import ProjectTask
        self.assertTrue(
            hasattr(ProjectTask, "lug_partner_name"),
            "ProjectTask must define lug_partner_name field",
        )

    def test_views_contain_partner_field(self):
        """Verify views contain partner_name in popup form and list."""
        import xml.etree.ElementTree as ET

        # Check popup form and stage task list in project_stage_line_views.xml
        tree = ET.parse("lug_project/views/project_stage_line_views.xml")
        root = tree.getroot()

        # Find field name="partner_name"
        fields = [elem.get("name") for elem in root.iter("field")]
        self.assertIn(
            "partner_name",
            fields,
            "project_stage_line_views.xml must contain partner_name field",
        )

        # Check project_stage_views.xml
        tree_stage = ET.parse("lug_project/views/project_stage_views.xml")
        root_stage = tree_stage.getroot()
        stage_fields = [elem.get("name") for elem in root_stage.iter("field")]
        self.assertIn(
            "lug_partner_name",
            stage_fields,
            "project_stage_views.xml must contain lug_partner_name field",
        )

    def test_sync_to_daily_does_not_leak_partner_name(self):
        """Verify _lug_sync_to_daily in project_stage_task does not include partner_name in daily_vals."""
        import inspect
        from lug_project.models.project_stage_task import ProjectStageTask

        source = inspect.getsource(ProjectStageTask._lug_sync_to_daily)
        self.assertNotIn(
            "'partner_name':",
            source,
            "_lug_sync_to_daily must not sync partner_name to daily.task",
        )
        self.assertNotIn(
            '"partner_name":',
            source,
            "_lug_sync_to_daily must not sync partner_name to daily.task",
        )


if __name__ == "__main__":
    unittest.main()
