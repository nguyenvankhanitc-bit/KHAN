# -*- coding: utf-8 -*-
"""Bảng xếp ca tháng (sheet). Model thật: linkq.monthly.roster / .line."""

from datetime import datetime

from odoo import api, fields, models

from .monthly_matrix_schedule import _clean_shift_code


class LinkqMonthlyShiftSheet(models.Model):
    _inherit = "linkq.monthly.roster"

    region = fields.Selection(
        related="store_id.mien",
        string="Khu vực / Miền",
        store=True,
        readonly=True,
    )

    @api.onchange("store_id", "month", "year")
    def _onchange_store_and_month_title(self):
        if not self.year:
            self.year = datetime.now().year
        self.name = self._default_sheet_name()

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            rec.name = rec._default_sheet_name()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ("store_id", "month", "year")) and "name" not in vals:
            for rec in self:
                rec.name = rec._default_sheet_name()
        return res

    def action_clean_shift_display(self):
        return super().action_clean_shift_display()


class LinkqMonthlyShiftSheetLine(models.Model):
    _inherit = "linkq.monthly.roster.line"

    @api.onchange("plan_codes", "actual_codes")
    def _onchange_shift_days(self):
        for rec in self:
            rec.plan_codes = rec._code_map(rec.plan_codes)
            rec.actual_codes = rec._code_map(rec.actual_codes)
            rec._compute_counts()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._apply_clean_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._apply_clean_vals(vals)
        return super().write(vals)

    def _apply_clean_vals(self, vals):
        if not vals:
            return vals
        if "plan_codes" in vals:
            vals["plan_codes"] = self._code_map(vals.get("plan_codes"))
        if "actual_codes" in vals:
            vals["actual_codes"] = self._code_map(vals.get("actual_codes"))
        for day in range(1, 32):
            field_name = f"d_{day}"
            if field_name in vals and vals[field_name]:
                vals[field_name] = _clean_shift_code(vals[field_name])
        return vals
