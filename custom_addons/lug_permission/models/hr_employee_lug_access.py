# -*- coding: utf-8 -*-
"""Delegate hr.employee read access to LUG public access helpers (same employee ids)."""

from odoo import SUPERUSER_ID, api, models

from .hr_employee_access import _lug_filter_web_read_specification, _lug_filter_readable_field_names


class HrEmployeeLugAccess(models.Model):
    _inherit = "hr.employee"

    def _lug_employee_guard_active(self):
        """LUG read caps apply to interactive users only — never block env.su()."""
        return (
            not self.env.su
            and self._hr_employee_read_is_restricted()
            and self.env.user.sudo()._lug_permission_is_enforced()
        )

    def _lug_public_delegate(self):
        return self.env["hr.employee.public"].browse(self.ids)

    def _hr_employee_filter_accessible(self):
        if self._lug_employee_guard_active():
            allowed = self._lug_public_delegate()._hr_employee_filter_accessible()
            return self.browse(allowed.ids)
        return super()._hr_employee_filter_accessible()

    def _filtered_access(self, operation):
        if operation == "read" and self._lug_employee_guard_active():
            allowed = self._hr_employee_filter_accessible()
            if not allowed:
                return self.browse()
            policy_allowed = self.browse(
                self._lug_public_delegate()._lug_split_policy_and_ref()[0].ids
            )
            ref_only = allowed - policy_allowed
            result = self.browse(ref_only.ids)
            if policy_allowed:
                result |= super(HrEmployeeLugAccess, policy_allowed)._filtered_access(
                    operation
                )
            return result
        return super()._filtered_access(operation)

    def _check_access(self, operation):
        if operation == "read" and self.ids and self._lug_employee_guard_active():
            return self._lug_public_delegate()._check_access(operation)
        return super()._check_access(operation)

    def fetch(self, field_names=None):
        if not self._lug_employee_guard_active():
            return super().fetch(field_names)
        if field_names is not None:
            field_names = _lug_filter_readable_field_names(self, list(field_names))
            if not field_names:
                return
        allowed = self._hr_employee_filter_accessible()
        if not allowed:
            return
        policy_allowed = self.browse(
            self._lug_public_delegate()._lug_split_policy_and_ref()[0].ids
        )
        ref_only = allowed - policy_allowed
        if policy_allowed:
            super(HrEmployeeLugAccess, policy_allowed).fetch(field_names)
        if ref_only:
            Public = self._lug_public_delegate()
            safe_names = Public._lug_ref_only_safe_field_names(field_names)
            # Only fetch fields that exist on hr.employee.
            safe_names = [n for n in (safe_names or []) if n in self._fields]
            if safe_names:
                self.env["hr.employee"].with_user(SUPERUSER_ID).browse(
                    ref_only.ids
                ).fetch(safe_names)
            for fname in set(field_names or []) - set(safe_names or []):
                field = self._fields.get(fname)
                if field and field.type in ("one2many", "many2many"):
                    for rec in ref_only:
                        self.env.cache.set(rec, field, ())
        return

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        if field_names:
            field_names = _lug_filter_readable_field_names(self, list(field_names))
        return super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)

    def web_read(self, specification):
        specification = _lug_filter_web_read_specification(self, specification)
        if self._lug_employee_guard_active():
            allowed = self._hr_employee_filter_accessible()
            if not allowed:
                return []
            target_ids = [rec_id for rec_id in self.ids if rec_id in allowed.ids]
            if not specification:
                return [{"id": rec_id} for rec_id in target_ids]
            # Reuse public web_read for shared fields, map back to employee ids.
            pub_spec = {
                key: value
                for key, value in specification.items()
                if key in self.env["hr.employee.public"]._fields
            }
            extra_spec = {
                key: value for key, value in specification.items() if key not in pub_spec
            }
            rows_by_id = {}
            if pub_spec:
                for row in self._lug_public_delegate().browse(allowed.ids).web_read(pub_spec):
                    rows_by_id[row["id"]] = row
            if extra_spec:
                policy_allowed = self.browse(
                    self._lug_public_delegate()._lug_split_policy_and_ref()[0].ids
                )
                policy_target = policy_allowed.browse(
                    [i for i in target_ids if i in policy_allowed.ids]
                )
                if policy_target:
                    for row in super(HrEmployeeLugAccess, policy_target).web_read(extra_spec):
                        rows_by_id.setdefault(row["id"], {}).update(row)
            if not rows_by_id:
                return [{"id": rec_id} for rec_id in target_ids]
            rows = [rows_by_id[rec_id] for rec_id in target_ids if rec_id in rows_by_id]
            return self._lug_public_delegate()._lug_scrub_employee_x2many_rows(rows)
        return super().web_read(specification)

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        specification = _lug_filter_web_read_specification(self, specification or {})
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )
