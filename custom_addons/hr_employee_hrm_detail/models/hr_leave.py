# -*- coding: utf-8 -*-

from odoo import api, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    @api.model
    def _safe_timeoff_context_employee(self):
        Employee = self.env["hr.employee"]
        context = self.env.context
        for key in ("default_employee_id", "employee_id"):
            if key not in context:
                continue
            employee = Employee._search_accessible_employee(context[key])
            if employee:
                return employee
        return Employee.search(
            [
                ("user_id", "=", self.env.uid),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )

    @api.model
    def default_get(self, fields_list):
        employee = self._safe_timeoff_context_employee()
        context = dict(self.env.context)
        if "employee_id" in fields_list:
            context["default_employee_id"] = employee.id if employee else False
        for key in ("default_employee_id", "employee_id"):
            if key in context:
                context[key] = employee.id if employee else False

        defaults = super(HrLeave, self.with_context(context)).default_get(fields_list)
        if "employee_id" in defaults and defaults.get("employee_id"):
            default_employee = self.env["hr.employee"].search(
                [("id", "=", defaults["employee_id"])], limit=1
            )
            if not default_employee:
                defaults["employee_id"] = employee.id if employee else False
        return defaults

    @api.model
    def get_unusual_days(self, date_from, date_to=None):
        employee = self.env["hr.employee"]._get_contextual_employee()
        return employee._get_unusual_days(date_from, date_to) if employee else {}
