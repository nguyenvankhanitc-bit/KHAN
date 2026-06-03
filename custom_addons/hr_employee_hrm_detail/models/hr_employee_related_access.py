# -*- coding: utf-8 -*-

from odoo import api, models

RELATED_EMPLOYEE_FIELDS = ("parent_id", "coach_id")


class HrEmployeeRelatedAccess(models.Model):
    _inherit = "hr.employee"

    def _related_employee_fk_superuser(self, fname):
        """Read a related hr.employee FK from SQL (for approval routing only)."""
        self.ensure_one()
        if fname not in RELATED_EMPLOYEE_FIELDS:
            return False
        self.env.cr.execute(
            f"SELECT {fname} FROM hr_employee WHERE id = %s",
            (self.id,),
        )
        row = self.env.cr.fetchone()
        return row[0] if row and row[0] else False

    def _readable_related_employee(self, employee, fname):
        """Return the related employee if visible to the current user."""
        rel_id = employee._related_employee_fk_superuser(fname)
        if not rel_id:
            return self.env["hr.employee"]
        return self.env["hr.employee"].search([("id", "=", rel_id)], limit=1)

    def _fetch_accessible_related(self, fname):
        """Load parent_id/coach_id without exposing out-of-scope employees."""
        field = self._fields[fname]
        if not self.ids:
            return
        self.env.cr.execute(
            f"SELECT id, {fname} FROM hr_employee WHERE id IN %s",
            (tuple(self.ids),),
        )
        by_id = dict(self.env.cr.fetchall())
        for emp in self:
            rel_id = by_id.get(emp.id) or False
            if rel_id and not self.env["hr.employee"].search([("id", "=", rel_id)], limit=1):
                rel_id = False
            self.env.cache.set(emp, field, rel_id)

    def fetch(self, field_names=None):
        if field_names is None:
            fields_to_fetch = self._determine_fields_to_fetch()
            fnames = [field.name for field in fields_to_fetch]
        else:
            fnames = list(field_names)
        rel_fields = [name for name in fnames if name in RELATED_EMPLOYEE_FIELDS]
        base_fnames = [name for name in fnames if name not in rel_fields]
        if base_fnames:
            super().fetch(base_fnames)
        for fname in rel_fields:
            self._fetch_accessible_related(fname)

    def read(self, fields=None, load="_classic_read"):
        if not fields:
            return super().read(fields, load)
        fields = list(fields)
        rel_fields = [name for name in RELATED_EMPLOYEE_FIELDS if name in fields]
        if not rel_fields:
            return super().read(fields, load)
        base_fields = [name for name in fields if name not in rel_fields]
        result = super().read(base_fields or ["id"], load)
        for vals in result:
            emp = self.browse(vals["id"])
            for fname in rel_fields:
                readable = self._readable_related_employee(emp, fname)
                if readable:
                    vals[fname] = (readable.id, readable.display_name)
                else:
                    vals[fname] = False
        return result

    def _web_read_related_value(self, readable, rel_spec):
        """Build web_read payload for a related hr.employee (many2one target)."""
        if not isinstance(rel_spec, dict):
            return {"id": readable.id, "display_name": readable.display_name}
        if "fields" not in rel_spec:
            if rel_spec:
                return readable.web_read(rel_spec)[0]
            return {"id": readable.id, "display_name": readable.display_name}
        inner = dict(rel_spec["fields"])
        want_display = "display_name" in inner
        inner.pop("display_name", None)
        if inner:
            data = readable.web_read(inner)[0]
        else:
            data = {"id": readable.id}
        if want_display:
            data["display_name"] = readable.display_name
        return data.get("id") and data

    def web_read(self, specification):
        if not specification:
            return super().web_read(specification)
        spec = dict(specification)
        rel_fields = [name for name in RELATED_EMPLOYEE_FIELDS if name in spec]
        for name in rel_fields:
            del spec[name]
        result = super().web_read(spec)
        if rel_fields:
            for fname in rel_fields:
                for vals in result:
                    emp = self.browse(vals["id"])
                    readable = self._readable_related_employee(emp, fname)
                    if readable:
                        vals[fname] = self._web_read_related_value(
                            readable, specification[fname]
                        )
                    else:
                        vals[fname] = False
        return result
