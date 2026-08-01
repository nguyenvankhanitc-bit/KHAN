# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api, models

from .hr_employee_access import (
    _lug_employee_access_denied,
    _lug_filter_readable_field_names,
    _lug_filter_web_read_specification,
)

RELATED_EMPLOYEE_PUBLIC_FIELDS = ("parent_id", "coach_id")
# employee_id on public is hr.employee with the same pk; nested web_read breaks under LUG.
PUBLIC_SELF_MANY2ONE_FIELDS = ("employee_id",)
# x2many to employees must never be filled via SUPERUSER for reference-only rows:
# leaking out-of-scope child ids makes the web client check_access() raise AccessError.
REF_ONLY_SKIP_X2MANY_FIELDS = frozenset({"child_ids", "subordinate_ids"})


class HrEmployeePublicLugAccess(models.Model):
    _inherit = "hr.employee.public"

    def _lug_reference_readable_ids(self):
        return self.env["hr.employee.access.mixin"]._hr_employee_access_reference_readable_ids(
            self.env.user
        )

    def _lug_employee_x2many_field_names(self):
        return [
            name
            for name, field in self._fields.items()
            if field.type in ("one2many", "many2many")
            and field.comodel_name in ("hr.employee", "hr.employee.public")
        ]

    def _lug_scrub_employee_x2many_rows(self, rows):
        """Drop out-of-scope employee ids from x2many payloads (child_ids, etc.)."""
        x2m_names = [
            name
            for name in self._lug_employee_x2many_field_names()
            if any(name in row for row in rows)
        ]
        if not x2m_names:
            return rows
        related_ids = set()
        for row in rows:
            for name in x2m_names:
                raw = row.get(name) or []
                for item in raw:
                    if isinstance(item, dict) and item.get("id"):
                        related_ids.add(item["id"])
                    elif isinstance(item, (list, tuple)) and item:
                        related_ids.add(item[0])
                    elif isinstance(item, int):
                        related_ids.add(item)
        if not related_ids:
            return rows
        visible = set(self.browse(list(related_ids))._hr_employee_filter_accessible().ids)

        def _keep(item):
            if isinstance(item, dict):
                return item.get("id") in visible
            if isinstance(item, (list, tuple)) and item:
                return item[0] in visible
            if isinstance(item, int):
                return item in visible
            return False

        for row in rows:
            for name in x2m_names:
                if name in row and row[name]:
                    row[name] = [item for item in row[name] if _keep(item)]
        return rows

    def _lug_ref_only_safe_field_names(self, field_names):
        if not field_names:
            return field_names
        skip = REF_ONLY_SKIP_X2MANY_FIELDS | set(self._lug_employee_x2many_field_names())
        return [name for name in field_names if name not in skip]

    def _lug_public_related_fk_map(self, fname):
        if fname not in RELATED_EMPLOYEE_PUBLIC_FIELDS or not self.ids:
            return {}
        self.env.cr.execute(
            f"SELECT id, {fname} FROM hr_employee_public WHERE id IN %s",
            (tuple(self.ids),),
        )
        return dict(self.env.cr.fetchall())

    def _lug_web_read_related_public(self, related, rel_spec):
        if not isinstance(rel_spec, dict):
            return {"id": related.id, "display_name": related.display_name}
        if "fields" not in rel_spec:
            if rel_spec:
                return related.web_read(rel_spec)[0]
            return {"id": related.id, "display_name": related.display_name}
        inner = dict(rel_spec["fields"])
        want_display = "display_name" in inner
        inner.pop("display_name", None)
        if inner:
            data = related.web_read(inner)[0]
        else:
            data = {"id": related.id}
        if want_display:
            data["display_name"] = related.display_name
        return data.get("id") and data

    def _lug_split_policy_and_ref(self):
        """Split accessible records into policy-visible vs org-reference-only."""
        allowed = self._hr_employee_filter_accessible()
        if not allowed:
            return self.browse(), self.browse()
        policy = self._lug_policy_accessible()
        ref_only = allowed - policy
        return allowed - ref_only, ref_only

    def _hr_employee_filter_accessible(self):
        if not self._hr_employee_read_is_restricted():
            return super()._hr_employee_filter_accessible()
        ref_ids = set(
            self.env["hr.employee.access.mixin"]._hr_employee_access_reference_readable_ids(
                self.env.user
            )
        )
        allowed = super()._hr_employee_filter_accessible()
        if not ref_ids:
            return allowed
        include_ids = set(allowed.ids)
        for rec_id in self.ids:
            if rec_id in ref_ids:
                include_ids.add(rec_id)
        return self.browse(list(include_ids))

    def _lug_policy_accessible(self):
        return super(HrEmployeePublicLugAccess, self)._hr_employee_filter_accessible()

    def _filtered_access(self, operation):
        if operation == "read" and self._hr_employee_read_is_restricted():
            allowed = self._hr_employee_filter_accessible()
            if not allowed:
                return self.browse()
            policy_allowed, ref_only = self._lug_split_policy_and_ref()
            result = self.browse(ref_only.ids)
            if policy_allowed:
                result |= super(
                    HrEmployeePublicLugAccess, policy_allowed
                )._filtered_access(operation)
            return result
        return super()._filtered_access(operation)

    def _check_access(self, operation):
        if operation == "read" and self.ids and self._hr_employee_read_is_restricted():
            allowed = self._hr_employee_filter_accessible()
            forbidden = self - allowed
            if forbidden:
                return _lug_employee_access_denied(forbidden, operation)
            policy_allowed, ref_only = self._lug_split_policy_and_ref()
            if policy_allowed:
                result = super(
                    HrEmployeePublicLugAccess, policy_allowed
                )._check_access(operation)
                if result:
                    return result
            return None
        return super()._check_access(operation)

    def read(self, fields=None, load="_classic_read"):
        if fields:
            fields = _lug_filter_readable_field_names(self, list(fields))
        if not self._hr_employee_read_is_restricted():
            return super().read(fields, load)
        allowed = self._hr_employee_filter_accessible()
        if not allowed:
            return []
        ref_ids = set(self._lug_reference_readable_ids())
        policy_allowed = self._lug_policy_accessible()
        ref_only = allowed.filtered(
            lambda rec: rec.id in ref_ids and rec.id not in policy_allowed.ids
        )
        normal = allowed - ref_only
        rows = []
        if normal:
            rows.extend(super(HrEmployeePublicLugAccess, normal).read(fields, load))
        if ref_only:
            ref_fields = self._lug_ref_only_safe_field_names(fields)
            if ref_fields:
                rows.extend(
                    self.env["hr.employee.public"]
                    .with_user(SUPERUSER_ID)
                    .browse(ref_only.ids)
                    .read(ref_fields, load)
                )
            elif not fields:
                rows.extend(
                    self.env["hr.employee.public"]
                    .with_user(SUPERUSER_ID)
                    .browse(ref_only.ids)
                    .read(
                        self._lug_ref_only_safe_field_names(
                            list(self._fields)
                        ),
                        load,
                    )
                )
            else:
                rows.extend({"id": rid} for rid in ref_only.ids)
        return self._lug_scrub_employee_x2many_rows(rows)

    def fetch(self, field_names=None):
        # ORM calls fetch() directly for attribute access (org chart manager
        # chain, computed fields, mail). Reference-only records (managers/coaches
        # outside the policy scope) are added to `allowed` by
        # _hr_employee_filter_accessible but fail the base fetch's ir.rule/scope
        # re-check, raising AccessError. Fill their cache via SUPERUSER instead.
        if not self._hr_employee_read_is_restricted():
            return super().fetch(field_names)
        if field_names is not None:
            field_names = _lug_filter_readable_field_names(self, list(field_names))
            if not field_names:
                return
        allowed = self._hr_employee_filter_accessible()
        if not allowed:
            return
        policy_allowed, ref_only = self._lug_split_policy_and_ref()
        if policy_allowed:
            super(HrEmployeePublicLugAccess, policy_allowed).fetch(field_names)
        if ref_only:
            safe_names = self._lug_ref_only_safe_field_names(field_names)
            if safe_names:
                self.env["hr.employee.public"].with_user(SUPERUSER_ID).browse(
                    ref_only.ids
                ).fetch(safe_names)
            # Keep x2many empty in cache so the client never sees out-of-scope kids.
            for fname in set(field_names or []) - set(safe_names or []):
                field = self._fields.get(fname)
                if field and field.type in ("one2many", "many2many"):
                    for rec in ref_only:
                        self.env.cache.set(rec, field, ())
        return

    def _lug_fill_self_many2one_fields(self, result, specification):
        if "employee_id" not in specification:
            return
        for vals in result:
            emp_id = vals.get("id")
            if not emp_id:
                vals["employee_id"] = False
                continue
            vals["employee_id"] = {
                "id": emp_id,
                "display_name": vals.get("display_name") or vals.get("name") or "",
            }

    def web_read(self, specification):
        specification = _lug_filter_web_read_specification(self, specification)
        if not specification:
            return super().web_read(specification)
        spec_in = dict(specification)
        for name in PUBLIC_SELF_MANY2ONE_FIELDS:
            spec_in.pop(name, None)
        if not self._hr_employee_read_is_restricted():
            result = super().web_read(spec_in)
            self._lug_fill_self_many2one_fields(result, specification)
            return result
        spec = dict(spec_in)
        rel_fields = [name for name in RELATED_EMPLOYEE_PUBLIC_FIELDS if name in spec]
        for name in rel_fields:
            del spec[name]
        # Reference-only rows: do not ask the ORM for employee x2many (filled via
        # SUPERUSER elsewhere and would leak out-of-scope child ids to the client).
        allowed = self._hr_employee_filter_accessible()
        policy_allowed, ref_only = self._lug_split_policy_and_ref()
        x2m_skip = set(self._lug_employee_x2many_field_names()) | REF_ONLY_SKIP_X2MANY_FIELDS
        ref_spec = {k: v for k, v in spec.items() if k not in x2m_skip}
        result = []
        if policy_allowed:
            result.extend(super(HrEmployeePublicLugAccess, policy_allowed).web_read(spec))
        if ref_only and ref_spec:
            result.extend(
                self.env["hr.employee.public"]
                .with_user(SUPERUSER_ID)
                .browse(ref_only.ids)
                .web_read(ref_spec)
            )
        elif ref_only:
            result.extend({"id": rid} for rid in ref_only.ids)
        # Preserve caller order.
        by_id = {row["id"]: row for row in result if row.get("id")}
        result = [by_id[i] for i in allowed.ids if i in by_id]
        self._lug_fill_self_many2one_fields(result, specification)
        self._lug_scrub_employee_x2many_rows(result)
        if not rel_fields:
            return result
        ref_ids = set(self._lug_reference_readable_ids())
        fk_maps = {
            fname: self._lug_public_related_fk_map(fname) for fname in rel_fields
        }
        Public = self.env["hr.employee.public"]
        for vals in result:
            emp_id = vals.get("id")
            if not emp_id:
                for fname in rel_fields:
                    vals[fname] = False
                continue
            for fname in rel_fields:
                rel_id = fk_maps[fname].get(emp_id) or False
                if not rel_id:
                    vals[fname] = False
                    continue
                if rel_id in ref_ids:
                    related = Public.with_user(SUPERUSER_ID).browse(rel_id)
                    vals[fname] = self._lug_web_read_related_public(
                        related, specification[fname]
                    )
                    continue
                related = Public.search([("id", "=", rel_id)], limit=1)
                if related:
                    vals[fname] = self._lug_web_read_related_public(
                        related, specification[fname]
                    )
                else:
                    vals[fname] = False
        return result

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        if field_names:
            field_names = _lug_filter_readable_field_names(self, list(field_names))
        return super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)

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
