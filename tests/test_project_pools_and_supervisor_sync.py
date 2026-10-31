# -*- coding: utf-8 -*-
"""
Unit tests for:
1. Staffing pools & PIC pools on project.project.
2. Domain constraints for PIC & Staff on project.stage.task and project.task.
3. Supervisor synchronization to daily.task with role isolation ('pic' vs 'supervisor').
4. Safeguard preventing supervisor daily.task edits from corrupting project origin tasks.
5. Dual-view / dual-action Daily Work navigation for PIC vs Supervisor.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

# Mock odoo environment if not present
if "odoo" not in sys.modules:
    mock_odoo = MagicMock()
    mock_api = MagicMock()
    mock_api.model = lambda f: f
    mock_api.model_create_multi = lambda f: f
    mock_api.depends = lambda *args: lambda f: f
    mock_api.onchange = lambda *args: lambda f: f
    mock_api.constrains = lambda *args: lambda f: f

    mock_fields = MagicMock()
    mock_fields.Date.context_today = MagicMock(return_value="2026-10-31")
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
    mock_fields.Boolean = MagicMock(side_effect=lambda **kwargs: kwargs)

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

    class ValidationError(Exception):
        pass

    class UserError(Exception):
        pass

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
else:
    from odoo.exceptions import ValidationError, UserError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class MockRecordset(set):
    """Minimal Odoo Recordset mock supporting subtraction and mapped()."""

    def __init__(self, items=()):
        super().__init__(items or ())

    def __sub__(self, other):
        other_ids = {getattr(x, "id", x) for x in (other or ())}
        return MockRecordset(x for x in self if getattr(x, "id", x) not in other_ids)

    def mapped(self, attr):
        return [getattr(x, attr, str(x)) for x in self]

    def __bool__(self):
        return len(self) > 0


class TestProjectPoolsAndSupervisorSync(unittest.TestCase):
    """Test suite for staffing pools and supervisor sync functionality."""

    def test_xml_project_views_pools(self):
        """Verify XML views include lug_pic_pool_ids and lug_staff_pool_ids."""
        view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_project_views.xml")
        self.assertTrue(os.path.exists(view_path))
        tree = ET.parse(view_path)
        root = tree.getroot()

        # Check intake form has pools
        intake_record = root.find(".//record[@id='view_project_intake_form']")
        self.assertIsNotNone(intake_record)
        arch = intake_record.find("./field[@name='arch']")
        self.assertIsNotNone(arch.find(".//field[@name='lug_pic_pool_ids']"))
        self.assertIsNotNone(arch.find(".//field[@name='lug_staff_pool_ids']"))

        # Check edit form has pools
        edit_record = root.find(".//record[@id='edit_project_lug']")
        self.assertIsNotNone(edit_record)
        arch_edit = edit_record.find("./field[@name='arch']")
        self.assertIsNotNone(arch_edit.find(".//field[@name='lug_pic_pool_ids']"))
        self.assertIsNotNone(arch_edit.find(".//field[@name='lug_staff_pool_ids']"))

    def test_xml_stage_task_views_staff(self):
        """Verify XML views for stage task include staff_ids."""
        view_path = os.path.join(REPO_ROOT, "lug_project", "views", "project_stage_line_views.xml")
        self.assertTrue(os.path.exists(view_path))
        tree = ET.parse(view_path)
        root = tree.getroot()

        list_view = root.find(".//record[@id='view_project_stage_task_list']")
        self.assertIsNotNone(list_view)
        arch_list = list_view.find("./field[@name='arch']")
        self.assertIsNotNone(arch_list.find(".//field[@name='staff_ids']"))

        popup_view = root.find(".//record[@id='view_project_stage_task_popup_form']")
        self.assertIsNotNone(popup_view)
        arch_popup = popup_view.find("./field[@name='arch']")
        self.assertIsNotNone(arch_popup.find(".//field[@name='staff_ids']"))

    def test_xml_daily_task_views_supervisor_role(self):
        """Verify Daily Task project views have role filters, role badge, and supervisor action."""
        view_path = os.path.join(REPO_ROOT, "lug_project", "views", "daily_task_views.xml")
        self.assertTrue(os.path.exists(view_path))
        tree = ET.parse(view_path)
        root = tree.getroot()

        # Search view
        search_view = root.find(".//record[@id='view_daily_task_project_search']")
        self.assertIsNotNone(search_view)
        arch_search = search_view.find("./field[@name='arch']")
        self.assertIsNotNone(arch_search.find(".//filter[@name='filter_role_pic']"))
        self.assertIsNotNone(arch_search.find(".//filter[@name='filter_role_supervisor']"))
        self.assertIsNotNone(arch_search.find(".//filter[@name='group_role']"))

        # Tree view
        tree_view = root.find(".//record[@id='view_daily_task_project_tree']")
        self.assertIsNotNone(tree_view)
        arch_tree = tree_view.find("./field[@name='arch']")
        self.assertIsNotNone(arch_tree.find(".//field[@name='lug_task_role']"))

        # Actions and Menuitems
        pic_action = root.find(".//record[@id='action_daily_task_my_projects']")
        self.assertIsNotNone(pic_action)
        sup_action = root.find(".//record[@id='action_daily_task_my_supervisor_projects']")
        self.assertIsNotNone(sup_action)

        pic_menu = root.find(".//menuitem[@id='menu_daily_work_projects']")
        self.assertIsNotNone(pic_menu)
        sup_menu = root.find(".//menuitem[@id='menu_daily_work_projects_supervisor']")
        self.assertIsNotNone(sup_menu)

    def test_xml_daily_work_employee_ws_supervisor_tab(self):
        """Verify Employee Workspace XML has 'Dự án (Giám sát)' button calling projects_supervisor."""
        view_path = os.path.join(
            REPO_ROOT, "daily_work_task", "static", "src", "employee_ws", "daily_work_employee_ws.xml"
        )
        self.assertTrue(os.path.exists(view_path))
        with open(view_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("openWorkPage('projects_supervisor')", content)
        self.assertIn("Dự án (Giám sát)", content)

    def test_project_create_auto_adds_pic_to_pic_pool(self):
        """Verify project.create() automatically adds lug_pic_id to lug_pic_pool_ids."""
        import importlib
        import lug_project.models.project_project as pp
        importlib.reload(pp)

        model_cls = pp.ProjectProject
        vals = {"name": "Test Project", "lug_pic_id": 10}
        with unittest.mock.patch.object(model_cls, "__init__", return_value=None):
            with unittest.mock.patch("lug_project.models.project_project.super") as mock_super:
                mock_created = MagicMock()
                mock_super.return_value.create.return_value = mock_created

                obj = model_cls()
                obj.env = MagicMock()
                obj.env.context = {"lug_sync_lock": True}
                obj._lug_generate_code = MagicMock(return_value="DA-99")
                obj._lug_name_from_vals = MagicMock(return_value="DA-99 Test Project")
                obj.create([vals])
                self.assertIn("lug_pic_pool_ids", vals)
                self.assertEqual(vals["lug_pic_pool_ids"], [(4, 10)])

    def test_project_stage_task_pool_constraints(self):
        """Verify project.stage.task raises ValidationError when user is not in pool."""
        import importlib
        import lug_project.models.project_stage_task as pst
        importlib.reload(pst)

        task = pst.ProjectStageTask()
        task.name = "Test Task"
        mock_proj = MagicMock()
        user1 = MagicMock(id=1, name="User 1")
        user2 = MagicMock(id=2, name="User 2")
        user3 = MagicMock(id=3, name="User 3")

        mock_proj.lug_pic_pool_ids = MockRecordset([user1, user2])
        mock_proj.lug_staff_pool_ids = MockRecordset([user2])
        task.project_id = mock_proj
        task.stage_id = False

        # 1. Valid case
        task.user_ids = MockRecordset([user1])
        task.staff_ids = MockRecordset([user2])
        task._check_user_ids()  # Should not raise

        # 2. Invalid PIC (user3 not in lug_pic_pool_ids)
        task.user_ids = MockRecordset([user3])
        task.staff_ids = MockRecordset([user2])
        with self.assertRaises(Exception):
            task._check_user_ids()

        # 3. Invalid Staff (user1 not in lug_staff_pool_ids)
        task.user_ids = MockRecordset([user1])
        task.staff_ids = MockRecordset([user1])
        with self.assertRaises(Exception):
            task._check_user_ids()

    def test_project_task_pool_constraints(self):
        """Verify project.task raises ValidationError when user is not in pool."""
        import importlib
        import lug_project.models.project_task as pt
        importlib.reload(pt)

        task = pt.ProjectTask()
        mock_proj = MagicMock()
        u1 = MagicMock(id=10, name="User 10")
        u2 = MagicMock(id=20, name="User 20")
        u3 = MagicMock(id=30, name="User 30")

        mock_proj.lug_pic_pool_ids = MockRecordset([u1, u2])
        mock_proj.lug_staff_pool_ids = MockRecordset([u2])
        task.project_id = mock_proj
        task.lug_origin_project_task_id = False

        # Valid
        task.lug_pic_id = False
        task.user_ids = MockRecordset([u1])
        task.lug_staff_ids = MockRecordset([u2])
        task._check_lug_assignee()

        # Invalid PIC in user_ids
        task.user_ids = MockRecordset([u3])
        with self.assertRaises(Exception):
            task._check_lug_assignee()

        # Reset user_ids, invalid lug_staff_ids
        task.user_ids = MockRecordset([u1])
        task.lug_staff_ids = MockRecordset([u1])
        with self.assertRaises(Exception):
            task._check_lug_assignee()

    def test_supervisor_sync_to_daily_stage_task(self):
        """Verify project.stage.task creates daily.task with lug_task_role='supervisor'."""
        import importlib
        import lug_project.models.project_stage_task as pst
        importlib.reload(pst)

        task = pst.ProjectStageTask()
        task.id = 100
        task.name = "Stage Task 1"
        task.deadline = "2026-11-10"
        task.execution_date = "2026-11-01"
        task.state = "in_progress"
        task.note = "Notes"
        task.daily_task_ids = MagicMock()
        task.daily_task_ids.exists.return_value = []

        mock_proj = MagicMock(id=50, name="Project 50")
        mock_proj.lug_priority = "high"
        mock_proj.user_id = MagicMock(id=999)
        task.project_id = mock_proj
        task.stage_id = False

        u_pic = MagicMock(id=1)
        u_sup = MagicMock(id=2)
        task.user_ids = [u_pic]
        task.supervisor_ids = [u_sup]
        task.staff_ids = [MagicMock(id=88)]  # staff_ids should NOT sync

        emp1 = MagicMock(id=101)
        emp1.department_id.id = False
        emp2 = MagicMock(id=102)
        emp2.department_id.id = False

        def mock_get_emp(user):
            if user == u_pic:
                return emp1
            elif user == u_sup:
                return emp2
            return None

        task._lug_get_or_create_daily_employee = MagicMock(side_effect=mock_get_emp)

        mock_daily_task_model = MagicMock()
        created_records = []

        def mock_create(vals):
            rec = MagicMock()
            rec.id = len(created_records) + 1
            for k, v in vals.items():
                setattr(rec, k, v)
            created_records.append(rec)
            return rec

        mock_daily_task_model.create = MagicMock(side_effect=mock_create)
        mock_daily_task_model.sudo.return_value = mock_daily_task_model
        mock_daily_task_model.with_context.return_value = mock_daily_task_model
        mock_daily_task_model.search.return_value = []

        env = MagicMock()
        env.__contains__.side_effect = lambda k: True
        env.__getitem__.side_effect = lambda k: mock_daily_task_model if k == "daily.task" else MagicMock()
        env.user = MagicMock(id=999)
        task.env = env
        task.sudo = MagicMock(return_value=task)

        # Run sync
        task._lug_sync_to_daily()

        # Verify two daily tasks were created: 1 for PIC, 1 for supervisor
        self.assertEqual(len(created_records), 2)
        pic_daily = [r for r in created_records if r.lug_task_role == "pic"][0]
        sup_daily = [r for r in created_records if r.lug_task_role == "supervisor"][0]

        self.assertEqual(pic_daily.assignee_id, 101)
        self.assertEqual(sup_daily.assignee_id, 102)

    def test_supervisor_unlink_when_removed(self):
        """Verify that when a supervisor is removed from stage task, the supervisor daily task is unlinked."""
        import importlib
        import lug_project.models.project_stage_task as pst
        importlib.reload(pst)

        task = pst.ProjectStageTask()
        task.id = 100
        task.name = "Stage Task 1"
        task.deadline = "2026-11-10"
        task.execution_date = "2026-11-01"
        task.state = "in_progress"
        task.note = "Notes"

        mock_proj = MagicMock(id=50, name="Project 50")
        mock_proj.lug_priority = "high"
        mock_proj.user_id = MagicMock(id=999)
        task.project_id = mock_proj
        task.stage_id = False

        u_pic = MagicMock(id=1)
        task.user_ids = [u_pic]
        task.supervisor_ids = []  # No supervisor now!

        emp1 = MagicMock(id=101)
        emp1.department_id.id = False
        task._lug_get_or_create_daily_employee = MagicMock(side_effect=lambda u: emp1 if u == u_pic else None)

        # Existing daily tasks has 1 supervisor task from previous sync
        existing_sup_task = MagicMock(id=202, lug_task_role="supervisor")
        existing_sup_task.assignee_id.id = 999
        existing_sup_task.assignee_user_id.id = 999
        existing_sup_task.with_context.return_value = existing_sup_task
        existing_sup_task.sudo.return_value = existing_sup_task

        mock_daily_task_model = MagicMock()
        mock_daily_task_model.sudo.return_value = mock_daily_task_model
        mock_daily_task_model.with_context.return_value = mock_daily_task_model
        mock_daily_task_model.search.return_value = [existing_sup_task]

        task.daily_task_ids = MagicMock()
        task.daily_task_ids.exists.return_value = [existing_sup_task]

        env = MagicMock()
        env.__contains__.side_effect = lambda k: True
        env.__getitem__.side_effect = lambda k: mock_daily_task_model if k == "daily.task" else MagicMock()
        env.user = MagicMock(id=999)
        task.env = env
        task.sudo = MagicMock(return_value=task)

        task._lug_sync_to_daily()

        # The orphan supervisor daily task should have been unlinked
        existing_sup_task.unlink.assert_called_once()

    def test_supervisor_sync_to_daily_project_task(self):
        """Verify project.task syncs lug_supervisor_id to daily.task with role='supervisor'."""
        import importlib
        import lug_project.models.project_task as pt
        importlib.reload(pt)

        task = pt.ProjectTask()
        task.id = 555
        task.name = "Project Task Sync Test"
        task.project_id = MagicMock(id=77, name="Project 77")
        task.project_id.lug_department_id.id = False
        task.lug_stage_id = False
        task.lug_origin_project_task_id = False
        task.date_deadline = "2026-11-20"
        task.date_assign = "2026-11-01"
        task.priority = "0"
        task.description = "Task Description"

        u_pic = MagicMock(id=10)
        u_sup = MagicMock(id=20)
        task.user_ids = [u_pic]
        task.lug_pic_id = u_pic
        task.lug_supervisor_id = u_sup
        task.lug_staff_ids = [MagicMock(id=30)]  # staff should NOT sync

        emp10 = MagicMock(id=110)
        emp10.department_id.id = False
        emp20 = MagicMock(id=120)
        emp20.department_id.id = False

        def mock_get_emp(user):
            if user == u_pic:
                return emp10
            elif user == u_sup:
                return emp20
            return None

        task._lug_get_or_create_daily_employee = MagicMock(side_effect=mock_get_emp)

        created_records = []
        mock_daily_model = MagicMock()
        def mock_create(vals):
            rec = MagicMock()
            rec.id = len(created_records) + 1
            for k, v in vals.items():
                setattr(rec, k, v)
            created_records.append(rec)
            return rec

        mock_daily_model.create = MagicMock(side_effect=mock_create)
        mock_daily_model.sudo.return_value = mock_daily_model
        mock_daily_model.with_context.return_value = mock_daily_model
        mock_daily_model.search.return_value = []

        env = MagicMock()
        env.__contains__.side_effect = lambda k: True
        env.__getitem__.side_effect = lambda k: mock_daily_model if k == "daily.task" else MagicMock()
        env.user = MagicMock(id=999)
        task.env = env
        task.sudo = MagicMock(return_value=task)

        task._lug_sync_to_todo_and_daily()

        # Both PIC and Supervisor daily tasks should be created
        self.assertEqual(len(created_records), 2)
        roles = {r.lug_task_role for r in created_records}
        self.assertEqual(roles, {"pic", "supervisor"})

    def test_supervisor_daily_task_does_not_sync_back_to_origin(self):
        """Verify daily.task with lug_task_role='supervisor' skips _lug_sync_back_to_origin."""
        import importlib
        import lug_project.models.daily_task as dt
        importlib.reload(dt)

        daily_task = dt.DailyTask()
        daily_task.lug_task_role = "supervisor"
        daily_task.state = "done"
        daily_task.lug_origin_stage_task_id = MagicMock()
        daily_task.lug_origin_project_task_id = MagicMock()

        # Call _lug_sync_back_to_origin with state change
        daily_task._lug_sync_back_to_origin({"state": "done"})

        # origin task write should never be called
        daily_task.lug_origin_stage_task_id.write.assert_not_called()
        daily_task.lug_origin_project_task_id.write.assert_not_called()

    def test_daily_task_action_open_roles(self):
        """Verify action_open_my_project_tasks filters correctly for role='pic' vs role='supervisor'."""
        import importlib
        import lug_project.models.daily_task as dt
        importlib.reload(dt)

        daily = dt.DailyTask()
        daily.env = MagicMock()
        daily.env.user = MagicMock(id=77)
        daily.env.ref = MagicMock(return_value=MagicMock(id=99))
        daily.env.context = {}
        daily._my_hr_employee = MagicMock(return_value=None)

        # 1. Default (PIC)
        act_pic = daily.action_open_my_project_tasks()
        self.assertIn(("lug_task_role", "!=", "supervisor"), act_pic["domain"])
        self.assertEqual(act_pic["context"].get("search_default_filter_role_pic"), 1)
        self.assertEqual(act_pic["name"], "Dự án - Tôi phụ trách")

        # 2. Supervisor
        act_sup = daily.action_open_my_supervisor_project_tasks()
        self.assertIn(("lug_task_role", "=", "supervisor"), act_sup["domain"])
        self.assertEqual(act_sup["context"].get("search_default_filter_role_supervisor"), 1)
        self.assertEqual(act_sup["name"], "Dự án - Tôi giám sát")


if __name__ == "__main__":
    unittest.main()
