# -*- coding: utf-8 -*-

from odoo import api, models

RELATED_EMPLOYEE_FIELDS = ("parent_id", "coach_id")


class HrEmployeeRelatedAccess(models.Model):
    _inherit = "hr.employee"

    def _readable_related_employee(self, employee, fname):
        """Return the related employee if visible to the current user."""
        rel = employee.sudo()[fname]
        if not rel:
            return self.env["hr.employee"]
        return self.env["hr.employee"].search([("id", "=", rel.id)], limit=1)

    def read(self, fields=None, load="_classic_read"):
        if self.env.su or not fields:
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
        if self.env.su or not specification:
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
