# -*- coding: utf-8 -*-
"""
Unit tests for 'File hợp đồng' (Contract Files) in lug_project.
Tests field definition, serialization, Excel export, and view integration.
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

# Setup mock odoo environment
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model = lambda f: f
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date.context_today = MagicMock(return_value="2026-10-26")
mock_fields.Date.to_date = lambda d: d
mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Html = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)
mock_fields.Monetary = MagicMock(side_effect=lambda **kwargs: kwargs)

mock_models = MagicMock()


class MockModel:
    _name = "mock.model"
    _inherit = ""

    def __init__(self, *args, **kwargs):
        pass

    def __iter__(self):
        return iter([self])

    def sudo(self):
        return self

    def with_context(self, *args, **kwargs):
        return self


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

if "dateutil" not in sys.modules:
    mock_dateutil = MagicMock()
    mock_relativedelta = MagicMock()
    mock_dateutil.relativedelta = mock_relativedelta
    sys.modules["dateutil"] = mock_dateutil
    sys.modules["dateutil.relativedelta"] = mock_relativedelta

from lug_project.models.project_project import ProjectProject
from lug_project.models.project_dashboard import ProjectProjectDashboard


class TestProjectContractFiles(unittest.TestCase):
    def test_project_contract_attachment_ids_field(self):
        """Verify lug_contract_attachment_ids field is defined on ProjectProject."""
        self.assertTrue(
            hasattr(ProjectProject, "lug_contract_attachment_ids"),
            "ProjectProject must define lug_contract_attachment_ids field",
        )
        field_kwargs = getattr(ProjectProject, "lug_contract_attachment_ids")
        if isinstance(field_kwargs, dict):
            self.assertEqual(field_kwargs.get("string"), "File hợp đồng")

    def test_serialize_project_row_contract_files(self):
        """Verify _lug_serialize_project_row returns serialized contract files with correct icon and url."""
        dashboard = ProjectProjectDashboard()
        dashboard._lug_type_chip = MagicMock(return_value={"label": "Thi công", "tone": "blue"})
        dashboard._lug_fmt_date = MagicMock(return_value="26/10/2026")
        dashboard._lug_deadline_badge = MagicMock(return_value={"date": "30/10/2026", "late": False, "state": "ok", "label": "Còn 4 ngày"})
        dashboard._lug_phase_tracker = MagicMock(return_value={"steps": []})
        dashboard._lug_trash_days = MagicMock(return_value=30)
        dashboard._lug_project_timeleft_meta = MagicMock(return_value={})

        # Mock project
        project = MagicMock()
        project.id = 101
        project.lug_stt = 1
        project.lug_code = "DA-2026-001"
        project._lug_project_title.return_value = "Cửa hàng LUG Aeon Tân Phú"
        project.lug_type_id = MagicMock()
        project.date_start = "2026-10-26"
        project.lug_priority = "high"
        project.user_id = MagicMock(id=1, name="Nguyễn Văn A")
        project.lug_assignee_ids = []
        project.task_ids.user_ids = []
        project.lug_workflow_state = "progress"
        project.active = True
        project.lug_total_expense = 50000000.0
        project.lug_expense_count = 3
        project.last_update_status = "on_track"

        # Mock attachments
        att1 = MagicMock()
        att1.id = 501
        att1.name = "Hop_dong_kinh_te.pdf"
        att2 = MagicMock()
        att2.id = 502
        att2.name = "Phu_luc_01.xlsx"
        att3 = MagicMock()
        att3.id = 503
        att3.name = "Bien_ban.docx"

        project.lug_contract_attachment_ids = [att1, att2, att3]

        row = dashboard._lug_serialize_project_row(project)
        self.assertIn("contract_files", row)
        contract_files = row["contract_files"]
        self.assertEqual(len(contract_files), 3)

        self.assertEqual(contract_files[0]["id"], 501)
        self.assertEqual(contract_files[0]["name"], "Hop_dong_kinh_te.pdf")
        self.assertEqual(contract_files[0]["icon"], "fa-file-pdf-o")
        self.assertEqual(contract_files[0]["download_url"], "/web/content/501?download=true")

        self.assertEqual(contract_files[1]["id"], 502)
        self.assertEqual(contract_files[1]["name"], "Phu_luc_01.xlsx")
        self.assertEqual(contract_files[1]["icon"], "fa-file-excel-o")
        self.assertEqual(contract_files[1]["download_url"], "/web/content/502?download=true")

        self.assertEqual(contract_files[2]["id"], 503)
        self.assertEqual(contract_files[2]["name"], "Bien_ban.docx")
        self.assertEqual(contract_files[2]["icon"], "fa-file-word-o")
        self.assertEqual(contract_files[2]["download_url"], "/web/content/503?download=true")

    def test_serialize_project_row_empty_contract_files(self):
        """Verify _lug_serialize_project_row handles empty contract files gracefully."""
        dashboard = ProjectProjectDashboard()
        dashboard._lug_type_chip = MagicMock(return_value=None)
        dashboard._lug_fmt_date = MagicMock(return_value="")
        dashboard._lug_deadline_badge = MagicMock(return_value={})
        dashboard._lug_phase_tracker = MagicMock(return_value={})
        dashboard._lug_trash_days = MagicMock(return_value=30)
        dashboard._lug_project_timeleft_meta = MagicMock(return_value={})

        project = MagicMock()
        project.id = 102
        project.lug_stt = 2
        project.lug_code = "DA-2026-002"
        project._lug_project_title.return_value = "Dự án mới"
        project.lug_type_id = False
        project.date_start = False
        project.lug_priority = "medium"
        project.user_id = False
        project.lug_assignee_ids = []
        project.task_ids.user_ids = []
        project.lug_workflow_state = "todo"
        project.active = True
        project.lug_total_expense = 0.0
        project.lug_expense_count = 0
        project.last_update_status = "to_define"
        project.lug_contract_attachment_ids = []

        row = dashboard._lug_serialize_project_row(project)
        self.assertIn("contract_files", row)
        self.assertEqual(row["contract_files"], [])

    def test_xml_views_contract_file_integration(self):
        """Verify XML views contain lug_contract_attachment_ids in required views."""
        tree = ET.parse("lug_project/views/project_project_views.xml")
        root = tree.getroot()

        # Check view_project_intake_form
        intake_view = root.find(".//record[@id='view_project_intake_form']")
        self.assertIsNotNone(intake_view, "view_project_intake_form must exist")
        intake_arch_str = ET.tostring(intake_view, encoding="utf-8").decode()
        self.assertIn('name="lug_contract_attachment_ids"', intake_arch_str)
        self.assertIn("File hợp đồng", intake_arch_str)

        # Check project_project_view_form_simplified_lug
        simplified_view = root.find(".//record[@id='project_project_view_form_simplified_lug']")
        self.assertIsNotNone(simplified_view, "project_project_view_form_simplified_lug must exist")
        simplified_arch_str = ET.tostring(simplified_view, encoding="utf-8").decode()
        self.assertIn('name="lug_contract_attachment_ids"', simplified_arch_str)

        # Check view_project_lug
        list_view = root.find(".//record[@id='view_project_lug']")
        self.assertIsNotNone(list_view, "view_project_lug must exist")
        list_arch_str = ET.tostring(list_view, encoding="utf-8").decode()
        self.assertIn('name="lug_contract_attachment_ids"', list_arch_str)

    def test_owl_list_xml_template_contract_files(self):
        """Verify OWL template lug_project_list.xml renders contract_files."""
        tree = ET.parse("lug_project/static/src/list/lug_project_list.xml")
        root = tree.getroot()
        xml_str = ET.tostring(root, encoding="utf-8").decode()
        self.assertIn("o_lug_contract_chip", xml_str)
        self.assertIn("contract_files", xml_str)


if __name__ == "__main__":
    unittest.main()
