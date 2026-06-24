# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class HrLeaveAnalyticsJobTitleMixin(models.AbstractModel):
    _name = "hr.leave.analytics.job.title.mixin"
    _description = "Chức danh display helpers for leave analytics"

    @api.model
    def _job_title_selection_labels(self):
        Version = self.env["hr.version"]
        if "job_title" in Version._fields and Version._fields["job_title"].type == "selection":
            return dict(Version._fields["job_title"]._description_selection(self.env))
        Employee = self.env["hr.employee"]
        if "job_title" in Employee._fields and Employee._fields["job_title"].type == "selection":
            return dict(Employee._fields["job_title"]._description_selection(self.env))
        return {}

    @api.model
    def _job_title_label(self, key, employee=None):
        if not key and employee:
            key = employee.job_title or ""
        label = self._job_title_selection_labels().get(key, key or "")
        if not label and employee and employee.job_id:
            label = (employee.job_id.name or "").strip()
        return label

    @api.model
    def _job_titles_label(self, keys_csv, employee=None):
        if not keys_csv:
            return self._job_title_label("", employee=employee)
        labels = []
        seen = set()
        for key in keys_csv.split(","):
            key = key.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            labels.append(self._job_title_label(key))
        return ", ".join(labels)
