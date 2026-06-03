# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

from .hr_employee_privacy import (
    _privacy_is_employee_edit_forbidden,
    _privacy_is_personal_tab_hidden,
    _privacy_raise_if_employee_create_forbidden,
    _privacy_raise_if_employee_no_write,
)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _check_employees_no_readonly(self):
        _privacy_raise_if_employee_no_write(self.env, self)

    personal_tab_hidden_for_privacy = fields.Boolean(
        compute="_compute_personal_tab_hidden_for_privacy",
        help="When true, the Personal tab is hidden (View Personal Information: No).",
    )
    employee_form_force_readonly_ui = fields.Boolean(
        compute="_compute_employee_form_force_readonly_ui",
        help="When true, employee form opens in readonly mode (Edit Employee Profile: No).",
    )

    @api.depends_context("uid")
    def _compute_employee_form_force_readonly_ui(self):
        lock = _privacy_is_employee_edit_forbidden(self.env)
        for emp in self:
            emp.employee_form_force_readonly_ui = lock

    @api.depends_context("uid")
    def _compute_personal_tab_hidden_for_privacy(self):
        hidden = _privacy_is_personal_tab_hidden(self.env)
        for emp in self:
            emp.personal_tab_hidden_for_privacy = hidden

    @api.model_create_multi
    def create(self, vals_list):
        _privacy_raise_if_employee_create_forbidden(self.env)
        return super().create(vals_list)

    def write(self, vals):
        self._check_employees_no_readonly()
        return super().write(vals)

    def unlink(self):
        self._check_employees_no_readonly()
        return super().unlink()
