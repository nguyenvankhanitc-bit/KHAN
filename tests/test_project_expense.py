# -*- coding: utf-8 -*-
"""
Unit tests for Expense integration (Chi phí) in lug_project.
Mocks odoo framework primitives so tests run standalone.
"""

import sys
import unittest
from unittest.mock import MagicMock

# Setup mock odoo environment
mock_odoo = MagicMock()
mock_api = MagicMock()
mock_api.model_create_multi = lambda f: f
mock_api.depends = lambda *args: lambda f: f
mock_api.onchange = lambda *args: lambda f: f
mock_api.constrains = lambda *args: lambda f: f

mock_fields = MagicMock()
mock_fields.Date.context_today = MagicMock(return_value="2026-10-12")
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

    def create(self, vals_list):
        return vals_list

    def write(self, vals):
        return True

    def unlink(self):
        return True

    def sudo(self):
        return self

    def with_context(self, *args, **kwargs):
        return self

    def ensure_one(self):
        return self


mock_models.Model = MockModel
mock_models.Constraint = MagicMock()

mock_exceptions = MagicMock()


if "odoo.exceptions" in sys.modules and hasattr(sys.modules["odoo.exceptions"], "ValidationError"):
    ValidationError = sys.modules["odoo.exceptions"].ValidationError
else:
    class ValidationError(Exception):
        pass
mock_exceptions.ValidationError = ValidationError

if "odoo.exceptions" in sys.modules and hasattr(sys.modules["odoo.exceptions"], "UserError"):
    UserError = sys.modules["odoo.exceptions"].UserError
else:
    class UserError(Exception):
        pass
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

mock_dateutil = MagicMock()
mock_relativedelta = MagicMock()
mock_dateutil.relativedelta = mock_relativedelta
sys.modules["dateutil"] = mock_dateutil
sys.modules["dateutil.relativedelta"] = mock_relativedelta

from lug_project.models.project_project import ProjectProject
from lug_project.models.hr_expense import HrExpense


class TestProjectExpenseIntegration(unittest.TestCase):
    def setUp(self):
        self.project = ProjectProject()
        self.project.id = 100
        self.project.name = "Dự án LUG Store Aeon Mall"
        self.project.account_id = False

    def test_compute_lug_total_expense_valid_states(self):
        """Verify that only approved, posted, in_payment, and paid expenses are counted."""
        exp_approved = MagicMock()
        exp_approved.id = 1
        exp_approved.state = "approved"
        exp_approved.total_amount = 500000.0

        exp_paid = MagicMock()
        exp_paid.id = 2
        exp_paid.state = "paid"
        exp_paid.total_amount = 1200000.0

        exp_posted = MagicMock()
        exp_posted.id = 3
        exp_posted.state = "posted"
        exp_posted.total_amount = 800000.0

        exp_draft = MagicMock()
        exp_draft.id = 4
        exp_draft.state = "draft"
        exp_draft.total_amount = 300000.0

        exp_refused = MagicMock()
        exp_refused.id = 5
        exp_refused.state = "refused"
        exp_refused.total_amount = 400000.0

        all_expenses = [exp_approved, exp_paid, exp_posted, exp_draft, exp_refused]

        mock_expense_recordset = MagicMock()
        mock_expense_recordset.filtered.side_effect = lambda fn: [e for e in all_expenses if fn(e)]

        self.project.lug_expense_ids = mock_expense_recordset

        # Mock env
        mock_expense_model = MagicMock()
        mock_env = {"hr.expense": mock_expense_model}
        self.project.env = mock_env

        # Run compute
        self.project._compute_lug_total_expense()

        # Expected: 500000 + 1200000 + 800000 = 2500000
        self.assertEqual(self.project.lug_total_expense, 2500000.0)
        self.assertEqual(self.project.lug_expense_count, 3)

    def test_compute_lug_total_expense_empty(self):
        """Verify that when a project has no expenses, total is 0.0."""
        mock_expense_recordset = MagicMock()
        mock_expense_recordset.filtered.return_value = []
        self.project.lug_expense_ids = mock_expense_recordset
        self.project.env = {"hr.expense": MagicMock()}

        self.project._compute_lug_total_expense()

        self.assertEqual(self.project.lug_total_expense, 0.0)
        self.assertEqual(self.project.lug_expense_count, 0)

    def test_action_view_lug_expenses(self):
        """Verify that action_view_lug_expenses returns an action with domain for project_id."""
        self.project.ensure_one = MagicMock()
        mock_actions_model = MagicMock()
        mock_actions_model._for_xml_id.return_value = {
            "name": "Expenses",
            "type": "ir.actions.act_window",
            "res_model": "hr.expense",
        }
        self.project.env = {"ir.actions.actions": mock_actions_model}

        action = self.project.action_view_lug_expenses()

        self.assertEqual(action["domain"], [("project_id", "=", 100)])
        self.assertEqual(action["context"]["default_project_id"], 100)

    def test_hr_expense_onchange_project_id(self):
        """Verify that onchange project_id populates analytic_distribution if project has account_id."""
        expense = HrExpense()
        mock_proj = MagicMock()
        mock_proj.account_id.id = 55
        expense.project_id = mock_proj
        expense.analytic_distribution = False

        expense._onchange_project_id()

        self.assertEqual(expense.analytic_distribution, {"55": 100.0})


if __name__ == "__main__":
    unittest.main()
