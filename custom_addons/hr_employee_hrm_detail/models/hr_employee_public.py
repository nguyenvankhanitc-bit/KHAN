# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.hr.models.hr_employee import _ALLOW_READ_HR_EMPLOYEE


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    ma_bo_phan_id = fields.Many2one(
        "hr.store.code",
        string="Mã bộ phận",
        readonly=True,
    )
    mien_zone_id = fields.Many2one(
        related="employee_id.mien_zone_id",
        readonly=True,
    )
    mien = fields.Selection(related="employee_id.mien", readonly=True)
    employee_visibility = fields.Selection(
        related="employee_id.employee_visibility",
        readonly=True,
    )
    # Time-off balance fields: exposed on public profile so employees without
    # HR officer rights can read their own leave counters when creating requests.
    phep_chuan = fields.Float(readonly=True)
    tong_so_phep = fields.Float(readonly=True)
    da_su_dung = fields.Float(readonly=True)
    con_lai = fields.Float(readonly=True)
    ngay_het_han = fields.Date(readonly=True)
    con_lai_nam_truoc = fields.Float(readonly=True)
    nam_chot_con_lai = fields.Integer(readonly=True)
    monthly_paid_leave_cap = fields.Integer(readonly=True)
    last_monthly_leave_bonus_date = fields.Date(readonly=True)
    departure_monthly_leave_reversal_date = fields.Date(readonly=True)
    can_edit_monthly_paid_leave_cap = fields.Boolean(
        related="employee_id.can_edit_monthly_paid_leave_cap",
        readonly=True,
    )

    def _hr_employee_read_is_restricted(self):
        # Mirror hr.employee: sudo() must bypass scope filters so trusted code
        # (org-chart manager walk, related parent_id, etc.) can resolve FKs
        # outside the interactive user's visibility without MissingError.
        if self.env.su:
            return False
        if (
            self.env.context.get("_allow_read_hr_employee")
            is _ALLOW_READ_HR_EMPLOYEE
        ):
            return False
        return (
            self.env["hr.employee.access.mixin"]._hr_employee_access_extra_domain(
                model_name="hr.employee.public"
            )
            is not None
        )

    def _hr_employee_filter_accessible(self):
        if not self._hr_employee_read_is_restricted():
            return self
        if not self.ids:
            return self
        mixin = self.env["hr.employee.access.mixin"]
        domain = mixin._hr_employee_apply_access_domain(
            [("id", "in", self.ids)],
            model_name="hr.employee.public",
        )
        allowed_ids = super(HrEmployeePublic, self)._search(domain)
        return self.browse(allowed_ids)

    def _filtered_access(self, operation):
        records = super()._filtered_access(operation)
        if operation == "read" and self._hr_employee_read_is_restricted():
            allowed = self.browse(records.ids)._hr_employee_filter_accessible()
            return records.browse(allowed.ids)
        return records

    def _check_access(self, operation):
        if (
            operation == "read"
            and self.env.context.get("_allow_read_hr_employee")
            is _ALLOW_READ_HR_EMPLOYEE
        ):
            return None
        if operation == "read" and self.ids and self._hr_employee_read_is_restricted():
            allowed = self._hr_employee_filter_accessible()
            forbidden = self - allowed
            if forbidden:
                return super(HrEmployeePublic, forbidden)._check_access(operation)
            if allowed:
                return super(HrEmployeePublic, allowed)._check_access(operation)
            return super()._check_access(operation)
        return super()._check_access(operation)

    def read(self, fields=None, load="_classic_read"):
        if not self._hr_employee_read_is_restricted():
            return super().read(fields, load)
        allowed = self._hr_employee_filter_accessible()
        if not allowed:
            return []
        return super(HrEmployeePublic, allowed).read(fields, load)

    def fetch(self, field_names):
        if not self._hr_employee_read_is_restricted():
            return super().fetch(field_names)
        allowed = self._hr_employee_filter_accessible()
        if allowed:
            super(HrEmployeePublic, allowed).fetch(field_names)
        return

    def web_read(self, specification):
        return super(HrEmployeePublic, self._hr_employee_filter_accessible()).web_read(
            specification
        )

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
        if (
            self.env.context.get("_allow_read_hr_employee")
            is _ALLOW_READ_HR_EMPLOYEE
        ):
            return super()._search(
                domain,
                offset=offset,
                limit=limit,
                order=order,
                active_test=active_test,
                bypass_access=True,
                **{},
            )
        # Core hr.employee._search (no ACL) delegates here; skip mixin to avoid
        # double-filter and employee_id.* sub-search recursion.
        if (
            not self.env.su
            and not bypass_access
            and not self.env.context.get("hr_employee_search_bridge")
        ):
            mixin = self.env["hr.employee.access.mixin"]
            extra = mixin._hr_employee_access_extra_domain(model_name=self._name)
            domain = list(
                mixin._hr_employee_apply_access_domain(
                    domain, model_name=self._name
                )
            )
        else:
            extra = None
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access or extra is not None,
        )

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        if (
            not self.env.su
            and not self.env.context.get("hr_employee_search_bridge")
        ):
            domain = list(
                self.env["hr.employee.access.mixin"]._hr_employee_apply_access_domain(
                    domain, model_name=self._name
                )
            )
        return super().search_fetch(domain, field_names, offset, limit, order)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        domain = list(domain or [])
        if self._hr_employee_read_is_restricted():
            extra = self.env["hr.employee.access.mixin"]._hr_employee_apply_access_domain(
                domain, model_name="hr.employee.public"
            )
            domain = list(Domain(domain) & extra)
        return super().search_read(
            domain, fields, offset, limit, order, **read_kwargs
        )

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        domain = list(domain or [])
        if self._hr_employee_read_is_restricted():
            extra = self.env["hr.employee.access.mixin"]._hr_employee_apply_access_domain(
                domain, model_name="hr.employee.public"
            )
            domain = list(Domain(domain) & extra)
        return super().web_search_read(
            domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit
        )
