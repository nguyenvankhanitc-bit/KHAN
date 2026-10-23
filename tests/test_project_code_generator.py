# -*- coding: utf-8 -*-
"""
Unit tests for project code formula: [Type]-[dd/mm/yyyy]-[STT in month].
"""

import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

# Ensure mock odoo environment exists
if "odoo" not in sys.modules:
    import types
    mock_odoo = MagicMock()
    mock_api = MagicMock()
    mock_api.model = lambda f: f
    mock_api.model_create_multi = lambda f: f
    mock_api.depends = lambda *args: lambda f: f
    mock_api.onchange = lambda *args: lambda f: f
    mock_api.constrains = lambda *args: lambda f: f

    mock_fields = MagicMock()
    mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Date.context_today = MagicMock(return_value=date(2026, 10, 23))
    mock_fields.Date.to_date = lambda d: d if isinstance(d, date) else date.fromisoformat(str(d))
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

    mock_models = MagicMock()

    class MockModel:
        _name = "mock.model"
        _inherit = ""
        def __init__(self, *args, **kwargs): pass
        def __iter__(self): return iter([self])
        def create(self, vals_list): return vals_list
        def write(self, vals): return True
        def unlink(self): return True
        def sudo(self): return self
        def search(self, *args, **kwargs): return []
        def with_context(self, *args, **kwargs): return self
        def ensure_one(self): pass
        def flush_model(self, *args, **kwargs): pass

    mock_models.Model = MockModel
    mock_models.Constraint = MagicMock()

    class ExceptionsModule(types.ModuleType):
        def __getattr__(self, name):
            cls = type(name, (Exception,), {})
            setattr(self, name, cls)
            return cls

    exceptions_mod = ExceptionsModule("odoo.exceptions")
    exceptions_mod.ValidationError = type("ValidationError", (Exception,), {})
    exceptions_mod.UserError = type("UserError", (Exception,), {})

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

from lug_project.models.project_project import ProjectProject


class DummyType:
    def __init__(self, code="NB", name="Nội bộ"):
        self.code = code
        self.name = name

    def exists(self):
        return True


class TestProjectCodeGenerator(unittest.TestCase):
    def setUp(self):
        self.project_model = ProjectProject()
        self.project_model.env = MagicMock()
        self.project_model.env["project.project"].flush_model = MagicMock()
        self.project_model.sudo = MagicMock(return_value=self.project_model)
        self.project_model.search_count = MagicMock(return_value=0)

    def test_code_format_with_type(self):
        """Code format should be [Type]-[dd/mm/yyyy]-[STT]."""
        dummy_type = DummyType("NB", "Nội bộ")
        test_date = date(2026, 10, 23)

        # Mock DB returns max_seq = 0
        self.project_model.env.cr.fetchone.return_value = (0,)

        code = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=dummy_type,
            project_date=test_date,
        )
        self.assertEqual(code, "NB-23/10/2026-01")

    def test_code_format_without_type(self):
        """When no type is specified, prefix defaults to DA."""
        test_date = date(2026, 10, 23)
        self.project_model.env.cr.fetchone.return_value = (0,)

        code = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=None,
            project_date=test_date,
        )
        self.assertEqual(code, "DA-23/10/2026-01")

    def test_sequence_increments_in_month_across_types(self):
        """Sequence in the same month increments regardless of type."""
        type_nb = DummyType("NB", "Nội bộ")
        type_kh = DummyType("KH", "Khách hàng")
        test_date = date(2026, 10, 25)

        # First project in month
        self.project_model.env.cr.fetchone.return_value = (0,)
        code1 = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=type_nb,
            project_date=test_date,
        )
        self.assertEqual(code1, "NB-25/10/2026-01")

        # Second project in month (different type)
        self.project_model.env.cr.fetchone.return_value = (1,)
        code2 = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=type_kh,
            project_date=test_date,
        )
        self.assertEqual(code2, "KH-25/10/2026-02")

        # Third project in month (no type)
        self.project_model.env.cr.fetchone.return_value = (2,)
        code3 = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=None,
            project_date=test_date,
        )
        self.assertEqual(code3, "DA-25/10/2026-03")

    def test_batch_excluded_codes(self):
        """Batch generation correctly increments when codes are in excluded_codes."""
        type_nb = DummyType("NB", "Nội bộ")
        test_date = date(2026, 10, 23)
        self.project_model.env.cr.fetchone.return_value = (0,)

        used = set()
        code1 = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=type_nb,
            project_date=test_date,
            excluded_codes=used,
        )
        self.assertEqual(code1, "NB-23/10/2026-01")
        used.add(code1)

        code2 = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=type_nb,
            project_date=test_date,
            excluded_codes=used,
        )
        self.assertEqual(code2, "NB-23/10/2026-02")

    def test_new_month_resets_sequence(self):
        """In a new month, when DB has no records for that month, seq starts at 01."""
        type_nb = DummyType("NB", "Nội bộ")
        november_date = date(2026, 11, 1)

        # November has max_seq = 0
        self.project_model.env.cr.fetchone.return_value = (0,)

        code = ProjectProject._lug_generate_code(
            self.project_model,
            type_id=type_nb,
            project_date=november_date,
        )
        self.assertEqual(code, "NB-01/11/2026-01")


if __name__ == "__main__":
    unittest.main()
