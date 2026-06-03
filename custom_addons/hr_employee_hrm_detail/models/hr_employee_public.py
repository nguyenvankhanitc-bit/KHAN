# -*- coding: utf-8 -*-

from odoo import api, models


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    @api.model
    def _search(
        self,
        domain,
        offset=0,
        limit=None,
        order=None,
        *,
        active_test=True,
        bypass_access=False,
    ):
        domain = self.env["hr.employee.access.mixin"]._hr_employee_apply_access_domain(
            domain, model_name=self._name
        )
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        domain = self.env["hr.employee.access.mixin"]._hr_employee_apply_access_domain(
            domain, model_name=self._name
        )
        return super().search_fetch(domain, field_names, offset, limit, order)
