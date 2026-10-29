# -*- coding: utf-8 -*-
"""
Unit tests for 'Người phụ trách' (PIC options), unified intake form trigger,
and manual task assignee selection in Duan.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

# Mock odoo environment
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model = lambda f: f
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date.context_today = MagicMock(return_value="2026-10-29")
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

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestPicAndIntakeForm(unittest.TestCase):
    """Test suite for PIC options, intake form views, and task manual assignment."""

    def test_xml_intake_form_structure(self):
        """Verify view_project_intake_form has priority 1 and proper Người phụ trách layout."""
        view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_project_views.xml")
        self.assertTrue(os.path.exists(view_path), f"File {view_path} must exist.")

        tree = ET.parse(view_path)
        root = tree.getroot()

        intake_record = None
        for record in root.findall(".//record"):
            if record.get("id") == "view_project_intake_form":
                intake_record = record
                break

        self.assertIsNotNone(intake_record, "Record view_project_intake_form must exist.")
        priority_elem = intake_record.find("./field[@name='priority']")
        self.assertIsNotNone(priority_elem, "Priority field must exist on view_project_intake_form.")
        self.assertEqual(priority_elem.text.strip(), "1", "Priority must be 1 for highest precedence.")

        # Check fields inside intake form arch
        arch = intake_record.find("./field[@name='arch']")
        self.assertIsNotNone(arch)

        # Check lug_pic_type field exists
        pic_type_field = arch.find(".//field[@name='lug_pic_type']")
        self.assertIsNotNone(pic_type_field, "lug_pic_type field must be present in intake form.")
        self.assertEqual(pic_type_field.get("nolabel"), "1")

        # Check conditional row for values below Người phụ trách
        # Row with invisible="not lug_pic_type"
        conditional_div = None
        for div in arch.findall(".//div[@class='o_lug_kv']"):
            if div.get("invisible") == "not lug_pic_type":
                conditional_div = div
                break

        self.assertIsNotNone(conditional_div, "Conditional div with invisible='not lug_pic_type' must exist.")

        # Check that lug_pic_id and lug_pic_partner_name are present inside this div
        pic_id_field = conditional_div.find(".//field[@name='lug_pic_id']")
        self.assertIsNotNone(pic_id_field, "lug_pic_id must be in the conditional div.")
        self.assertEqual(pic_id_field.get("invisible"), "lug_pic_type != 'internal'")
        self.assertEqual(pic_id_field.get("nolabel"), "1")

        partner_name_field = conditional_div.find(".//field[@name='lug_pic_partner_name']")
        self.assertIsNotNone(partner_name_field, "lug_pic_partner_name must be in the conditional div.")
        self.assertEqual(partner_name_field.get("invisible"), "lug_pic_type != 'partner'")
        self.assertEqual(partner_name_field.get("nolabel"), "1")

        # Ensure redundant visible 'Đối tác' label is removed
        visible_labels = [span.text.strip() for span in arch.findall(".//span[@class='o_lug_k']") if span.text]
        self.assertNotIn("Đối tác", visible_labels, "'Đối tác' should not be a visible label in the intake form.")
        partner_field = arch.find(".//field[@name='partner_id']")
        self.assertIsNotNone(partner_field)
        self.assertEqual(partner_field.get("invisible"), "1")

    def test_xml_open_create_project_points_to_intake_form(self):
        """Verify project.open_create_project action uses view_project_intake_form."""
        view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_project_views.xml")
        tree = ET.parse(view_path)
        root = tree.getroot()

        create_act = None
        for record in root.findall(".//record"):
            if record.get("id") == "project.open_create_project":
                create_act = record
                break

        self.assertIsNotNone(create_act, "Record project.open_create_project must exist.")
        view_id_elem = create_act.find("./field[@name='view_id']")
        self.assertIsNotNone(view_id_elem, "view_id field must exist.")
        self.assertEqual(view_id_elem.get("ref"), "lug_project.view_project_intake_form")

        target_elem = create_act.find("./field[@name='target']")
        self.assertIsNotNone(target_elem)
        self.assertEqual(target_elem.text.strip(), "new")

    def test_xml_project_actions_use_intake_form(self):
        """Verify open_view_project_all and action_lug_project_main configure intake form."""
        proj_view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_project_views.xml")
        tree = ET.parse(proj_view_path)
        root = tree.getroot()

        all_proj_act = None
        for record in root.findall(".//record"):
            if record.get("id") == "project.open_view_project_all":
                all_proj_act = record
                break

        self.assertIsNotNone(all_proj_act)
        ctx = all_proj_act.find("./field[@name='context']")
        self.assertIsNotNone(ctx)
        self.assertIn("lug_project.view_project_intake_form", ctx.text)

        shell_view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_shell_views.xml")
        shell_tree = ET.parse(shell_view_path)
        shell_root = shell_tree.getroot()

        main_act = None
        for record in shell_root.findall(".//record"):
            if record.get("id") == "action_lug_project_main":
                main_act = record
                break

        self.assertIsNotNone(main_act)
        main_ctx = main_act.find("./field[@name='context']")
        self.assertIsNotNone(main_ctx)
        self.assertIn("lug_project.view_project_intake_form", main_ctx.text)

    def test_stage_line_action_add_task_popup_no_auto_fill(self):
        """Verify action_add_task_popup does not inject default_user_ids."""
        import importlib
        import lug_project.models.project_stage_line as psl

        importlib.reload(psl)

        stage_line = psl.ProjectStageLine()
        stage_line.id = 123
        stage_line.ensure_one = MagicMock()
        mock_proj = MagicMock()
        mock_proj.id = 456
        mock_proj.date_start = "2026-11-01"
        mock_proj.lug_deadline = "2026-11-30"
        mock_proj.lug_pic_id = MagicMock(id=999)
        stage_line.project_id = mock_proj

        mock_view = MagicMock(id=789)
        stage_line.env = MagicMock()
        stage_line.env.ref = MagicMock(return_value=mock_view)

        action = stage_line.action_add_task_popup()

        self.assertEqual(action["res_model"], "project.stage.task")
        self.assertEqual(action["target"], "new")
        ctx = action.get("context", {})
        self.assertNotIn("default_user_ids", ctx, "default_user_ids must NOT be set when creating a task.")
        self.assertEqual(ctx.get("default_stage_id"), 123)
        self.assertEqual(ctx.get("default_project_id"), 456)

    def test_project_onchange_pic_type(self):
        """Verify onchange behavior between lug_pic_type and assignee fields."""
        import importlib
        import lug_project.models.project_project as pp

        importlib.reload(pp)

        project = pp.ProjectProject()
        project.lug_pic_type = "partner"
        project.lug_pic_id = MagicMock(id=10)
        project.lug_pic_partner_name = "Công ty ABC"

        # When switching to partner, internal user should be cleared
        project._onchange_lug_pic_type()
        self.assertFalse(project.lug_pic_id)
        self.assertEqual(project.lug_pic_partner_name, "Công ty ABC")

        # When switching to internal, partner name should be cleared
        project.lug_pic_type = "internal"
        project.lug_pic_id = MagicMock(id=10)
        project._onchange_lug_pic_type()
        self.assertFalse(project.lug_pic_partner_name)

        # When setting lug_pic_id, lug_pic_type defaults to internal and sets user_id
        project.lug_pic_type = False
        project.user_id = False
        mock_user = MagicMock(id=25)
        project.lug_pic_id = mock_user
        project._onchange_lug_pic_id()
        self.assertEqual(project.user_id, mock_user)
        self.assertEqual(project.lug_pic_type, "internal")

    def test_project_dashboard_partner_serialization(self):
        """Verify dashboard row serializer formats partner PIC correctly."""
        import importlib
        import lug_project.models.project_dashboard as pd

        importlib.reload(pd)

        dashboard = pd.ProjectProjectDashboard()
        mock_proj = MagicMock()
        mock_proj.id = 1
        mock_proj.lug_workflow_state = "progress"
        mock_proj.lug_progress_pct = 60
        mock_proj.active = True
        mock_proj.lug_contract_attachment_ids = []
        mock_proj.lug_stt = 1
        mock_proj.lug_code = "DA-01"
        mock_proj._lug_project_title = MagicMock(return_value="Dự án Đối Tác")
        mock_proj.lug_type_id = MagicMock()
        mock_proj.date_start = "2026-10-01"
        mock_proj.lug_priority = "high"
        mock_proj.lug_pic_type = "partner"
        mock_proj.lug_pic_partner_name = "Đối tác xây dựng Hòa Bình"
        mock_proj.lug_pic_id = False
        mock_proj.user_id = False
        mock_proj.lug_assignee_ids = []
        mock_proj.task_ids.user_ids = []
        mock_proj.lug_total_expense = 0.0
        mock_proj.lug_expense_count = 0

        dashboard._lug_deadline_badge = MagicMock(return_value={"date": "2026-11-01", "late": False, "state": "ok", "label": "Còn 3 ngày"})
        dashboard._lug_trash_days = MagicMock(return_value=30)
        dashboard._lug_type_chip = MagicMock(return_value={"label": "Setup", "tone": "blue"})
        dashboard._lug_fmt_date = MagicMock(return_value="01/10/2026")
        dashboard._lug_phase_tracker = MagicMock(return_value={"label": "GĐ 1", "step": 1})
        dashboard._lug_project_timeleft_meta = MagicMock(return_value={"label": "Còn 3 ngày"})

        row = dashboard._lug_serialize_project_row(mock_proj)
        self.assertEqual(row["manager"]["name"], "Đối tác xây dựng Hòa Bình")
        self.assertFalse(row["manager"]["id"])
        self.assertEqual(row["manager"]["color"], "#64748B")


if __name__ == "__main__":
    unittest.main()
