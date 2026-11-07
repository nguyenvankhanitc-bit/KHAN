# -*- coding: utf-8 -*-
"""
Unit test for 'Thời gian thông báo' configuration in lug_project.
Tests res.config.settings model, ir.config_parameter default and views.
"""

import sys
import unittest
import xml.etree.ElementTree as ET
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


class TestLugProjectConfig(unittest.TestCase):
    """Test 'Thời gian thông báo' configuration."""

    def test_res_config_settings_field_defined(self):
        """Verify res.config.settings defines lug_notify_lead_days."""
        from lug_project.models.res_config_settings import ResConfigSettings
        self.assertTrue(
            hasattr(ResConfigSettings, "lug_notify_lead_days"),
            "ResConfigSettings must define lug_notify_lead_days",
        )

    def test_ir_config_parameter_in_ir_cron_data(self):
        """Verify ir.config_parameter for notify_lead_days exists in ir_cron_data.xml."""
        tree = ET.parse("lug_project/data/ir_cron_data.xml")
        root = tree.getroot()

        param_keys = []
        for record in root.findall(".//record[@model='ir.config_parameter']"):
            key_field = record.find("./field[@name='key']")
            if key_field is not None and key_field.text:
                param_keys.append(key_field.text.strip())

        self.assertIn(
            "lug_project.notify_lead_days",
            param_keys,
            "ir_cron_data.xml must define ir.config_parameter lug_project.notify_lead_days",
        )

    def test_res_config_settings_view_in_manifest(self):
        """Verify res_config_settings_views.xml is registered in __manifest__.py."""
        with open("lug_project/__manifest__.py", "r") as f:
            manifest_content = f.read()

        self.assertIn(
            "views/res_config_settings_views.xml",
            manifest_content,
            "__manifest__.py must include views/res_config_settings_views.xml",
        )


if __name__ == "__main__":
    unittest.main()
