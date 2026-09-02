# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    work_status = fields.Selection(
        [
            ("working", "Đang công tác"),
            ("resigned", "Nghỉ việc"),
            ("transferred", "Điều chuyển"),
        ],
        string="Trạng thái",
        default="working",
        tracking=True,
        index=True,
    )
    sequence_number = fields.Integer(string="STT", compute="_compute_sequence_number")
    total_work_hours = fields.Float(
        string="Số giờ",
        compute="_compute_total_work_hours",
        digits=(16, 1),
    )

    def _compute_sequence_number(self):
        for rec in self:
            rec.sequence_number = rec.id or 0

    def _compute_total_work_hours(self):
        Line = self.env["linkq.monthly.roster.line"].sudo()
        today = fields.Date.context_today(self)
        hours_map = {}
        if self.ids and "linkq.monthly.roster.line" in self.env:
            lines = Line.search([("employee_id", "in", self.ids)])
            for line in lines:
                roster = line.roster_id
                if roster and int(roster.month or 0) == today.month and roster.year == today.year:
                    hours_map[line.employee_id.id] = hours_map.get(line.employee_id.id, 0.0) + (
                        line.actual_hours or line.hour_total or 0.0
                    )
        for rec in self:
            rec.total_work_hours = hours_map.get(rec.id, 0.0)


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    work_status = fields.Selection(related="employee_id.work_status", readonly=True)
