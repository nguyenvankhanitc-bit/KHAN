# -*- coding: utf-8 -*-

from odoo import api, models

from .resource_calendar_leaves import HOLIDAY_SCOPE_CH, HOLIDAY_SCOPE_VP

_STORE_MIENS = frozenset({"Bắc", "Nam", "ĐTT"})
_STORE_CALENDAR_XMLID = "hr_public_holiday_mien.resource_calendar_store_full_week"


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _employee_schedule_mien(self):
        self.ensure_one()
        emp = self.sudo()
        mien = (emp.mien or "").strip()
        if not mien and emp.mien_zone_id:
            mien = (emp.mien_zone_id.legacy_mien or "").strip()
        if not mien and emp.ma_bo_phan_id:
            mien = (emp.ma_bo_phan_id.mien or "").strip()
        return mien

    def _uses_store_full_week_schedule(self):
        self.ensure_one()
        return self._employee_schedule_mien() in _STORE_MIENS

    def _public_holiday_scope_for_employee(self):
        self.ensure_one()
        mien = self._employee_schedule_mien()
        if mien == "VP":
            return HOLIDAY_SCOPE_VP
        if mien in _STORE_MIENS:
            return HOLIDAY_SCOPE_CH
        return False

    @api.model
    def _public_holiday_scope_for_current_user(self):
        employee = self.env.user.employee_id
        if not employee:
            return False
        return employee._public_holiday_scope_for_employee()

    def _get_public_holidays(self, date_start, date_end):
        self.ensure_one()
        if self._uses_store_full_week_schedule():
            return self.env["resource.calendar.leaves"]
        holidays = super()._get_public_holidays(date_start, date_end)
        scope = self._public_holiday_scope_for_employee()
        if scope:
            holidays = holidays.filtered(lambda leave: leave.holiday_scope == scope)
        return holidays

    def _recompute_open_leaves_calendar(self):
        if not self:
            return
        leaves = self.env["hr.leave"].search(
            [
                ("employee_id", "in", self.ids),
                ("state", "in", ["draft", "confirm", "validate1"]),
            ]
        )
        if not leaves:
            return
        fields_to_recompute = ("resource_calendar_id", "number_of_days", "number_of_hours")
        for field_name in fields_to_recompute:
            self.env.add_to_compute(leaves._fields[field_name], leaves)
        leaves._recompute_recordset(list(fields_to_recompute))

    def _sync_store_working_calendar(self):
        store_calendar = self.env.ref(_STORE_CALENDAR_XMLID, raise_if_not_found=False)
        if not store_calendar:
            return
        store_employees = self.env["hr.employee"]
        for employee in self:
            if not employee._uses_store_full_week_schedule():
                continue
            version = employee.version_id
            if version and version.resource_calendar_id != store_calendar:
                version.resource_calendar_id = store_calendar
            store_employees |= employee
        store_employees._recompute_open_leaves_calendar()

    @api.model
    def _upgrade_sync_store_working_calendars(self):
        self.search([])._sync_store_working_calendar()

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._sync_store_working_calendar()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if {"mien", "mien_zone_id", "ma_bo_phan_id"} & set(vals):
            self._sync_store_working_calendar()
        return res
