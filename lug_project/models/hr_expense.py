# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrExpense(models.Model):
    _inherit = "hr.expense"

    project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        index=True,
        tracking=True,
        ondelete="set null",
    )

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if (
            self.project_id
            and hasattr(self.project_id, "account_id")
            and self.project_id.account_id
            and hasattr(self, "analytic_distribution")
            and not self.analytic_distribution
        ):
            self.analytic_distribution = {str(self.project_id.account_id.id): 100.0}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            proj_id = vals.get("project_id") or self.env.context.get("default_project_id")
            if proj_id and not vals.get("analytic_distribution"):
                project = self.env["project.project"].browse(proj_id)
                if hasattr(project, "account_id") and project.account_id:
                    vals["analytic_distribution"] = {str(project.account_id.id): 100.0}
        return super().create(vals_list)
