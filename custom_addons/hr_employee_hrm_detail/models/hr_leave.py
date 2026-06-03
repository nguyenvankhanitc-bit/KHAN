# -*- coding: utf-8 -*-

from odoo import api, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "employee_id" in defaults and defaults.get("employee_id"):
            employee = self.env["hr.employee"].search(
                [("id", "=", defaults["employee_id"])], limit=1
            )
            if not employee:
                defaults["employee_id"] = self.env.user.employee_id.id
        return defaults

    @api.model
    def get_unusual_days(self, date_from, date_to=None):
        employee_id = self.env.context.get("employee_id", False)
        if employee_id:
            employee = self.env["hr.employee"]._search_accessible_employee(employee_id)
        else:
            employee = self.env.user.employee_id
        if not employee:
            employee = self.env.user.employee_id
        return employee.sudo(False)._get_unusual_days(date_from, date_to)
