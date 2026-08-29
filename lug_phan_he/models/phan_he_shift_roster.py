# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models


def _week_monday(day):
    return day - timedelta(days=day.weekday())


class PhanHeShiftRoster(models.Model):
    _name = "phan.he.shift.roster"
    _description = "Bản xếp ca"
    _order = "week_start desc, id desc"
    _inherit = ["mail.thread", "lug.menu.access.mixin"]
    _linkq_menu_key = "schedule_main"

    name = fields.Char(compute="_compute_name", store=True)
    week_start = fields.Date(
        string="Tuần từ (T2)",
        required=True,
        default=lambda self: _week_monday(fields.Date.context_today(self)),
        tracking=True,
    )
    week_end = fields.Date(string="Đến (CN)", compute="_compute_week_end", store=True)
    store_id = fields.Many2one("phan.he.store", string="Cửa hàng", ondelete="set null")
    department_id = fields.Many2one("hr.department", string="Phòng ban", ondelete="set null")
    state = fields.Selection(
        [("draft", "Nháp"), ("confirmed", "Đã chốt")],
        default="draft",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many("phan.he.shift.roster.line", "roster_id", string="Nhân sự")
    line_count = fields.Integer(compute="_compute_line_count")
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.depends("week_start", "store_id", "department_id")
    def _compute_name(self):
        for rec in self:
            if rec.week_start:
                end = rec.week_start + timedelta(days=6)
                label = f"Xếp ca {rec.week_start.strftime('%d/%m')}–{end.strftime('%d/%m/%Y')}"
            else:
                label = "Bản xếp ca"
            if rec.store_id:
                label = f"{rec.store_id.name} — {label}"
            elif rec.department_id:
                label = f"{rec.department_id.name} — {label}"
            rec.name = label

    @api.depends("week_start")
    def _compute_week_end(self):
        for rec in self:
            rec.week_end = rec.week_start + timedelta(days=6) if rec.week_start else False

    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.onchange("week_start")
    def _onchange_week_start(self):
        if self.week_start:
            self.week_start = _week_monday(self.week_start)

    def action_load_employees(self):
        self.ensure_one()
        domain = [("active", "=", True)]
        if self.department_id:
            domain.append(("department_id", "=", self.department_id.id))
        employees = self.env["hr.employee"].search(domain, order="name")
        existing = set(self.line_ids.mapped("employee_id").ids)
        vals = [
            (0, 0, {"employee_id": emp.id})
            for emp in employees
            if emp.id not in existing
        ]
        if vals:
            self.write({"line_ids": vals})
        return True

    def action_copy_previous_week(self):
        self.ensure_one()
        if not self.week_start:
            return True
        prev = self.search(
            [
                ("week_start", "=", self.week_start - timedelta(days=7)),
                ("store_id", "=", self.store_id.id),
                ("department_id", "=", self.department_id.id),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if not prev:
            return True
        self.line_ids.unlink()
        commands = []
        for line in prev.line_ids:
            commands.append((0, 0, {
                "employee_id": line.employee_id.id,
                "mon_shift_id": line.mon_shift_id.id,
                "tue_shift_id": line.tue_shift_id.id,
                "wed_shift_id": line.wed_shift_id.id,
                "thu_shift_id": line.thu_shift_id.id,
                "fri_shift_id": line.fri_shift_id.id,
                "sat_shift_id": line.sat_shift_id.id,
                "sun_shift_id": line.sun_shift_id.id,
            }))
        self.write({"line_ids": commands})
        return True

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_draft(self):
        self.write({"state": "draft"})


class PhanHeShiftRosterLine(models.Model):
    _name = "phan.he.shift.roster.line"
    _description = "Dòng xếp ca"
    _order = "employee_id"
    _inherit = ["lug.menu.access.mixin"]
    _linkq_menu_key = "schedule_main"

    roster_id = fields.Many2one(
        "phan.he.shift.roster", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Nhân viên", required=True, ondelete="restrict"
    )
    department_id = fields.Many2one(
        related="employee_id.department_id", store=True, string="Phòng ban"
    )
    mon_shift_id = fields.Many2one("phan.he.work.shift", string="T2", ondelete="restrict")
    tue_shift_id = fields.Many2one("phan.he.work.shift", string="T3", ondelete="restrict")
    wed_shift_id = fields.Many2one("phan.he.work.shift", string="T4", ondelete="restrict")
    thu_shift_id = fields.Many2one("phan.he.work.shift", string="T5", ondelete="restrict")
    fri_shift_id = fields.Many2one("phan.he.work.shift", string="T6", ondelete="restrict")
    sat_shift_id = fields.Many2one("phan.he.work.shift", string="T7", ondelete="restrict")
    sun_shift_id = fields.Many2one("phan.he.work.shift", string="CN", ondelete="restrict")
    total_hours = fields.Float(string="Tổng giờ", compute="_compute_totals", store=True)
    actual_hours = fields.Float(string="Công thực tế", compute="_compute_totals", store=True)

    _employee_roster_uniq = models.Constraint(
        "unique(roster_id, employee_id)",
        "Mỗi nhân viên chỉ có một dòng trong bản xếp ca.",
    )

    @api.depends(
        "mon_shift_id.total_hours",
        "mon_shift_id.actual_hours",
        "tue_shift_id.total_hours",
        "tue_shift_id.actual_hours",
        "wed_shift_id.total_hours",
        "wed_shift_id.actual_hours",
        "thu_shift_id.total_hours",
        "thu_shift_id.actual_hours",
        "fri_shift_id.total_hours",
        "fri_shift_id.actual_hours",
        "sat_shift_id.total_hours",
        "sat_shift_id.actual_hours",
        "sun_shift_id.total_hours",
        "sun_shift_id.actual_hours",
    )
    def _compute_totals(self):
        day_fields = [
            "mon_shift_id",
            "tue_shift_id",
            "wed_shift_id",
            "thu_shift_id",
            "fri_shift_id",
            "sat_shift_id",
            "sun_shift_id",
        ]
        for rec in self:
            total = actual = 0.0
            for fname in day_fields:
                shift = rec[fname]
                if shift:
                    total += shift.total_hours
                    actual += shift.actual_hours
            rec.total_hours = total
            rec.actual_hours = actual
