# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyTaskTeam(models.Model):
    """Team theo phòng ban — quản trị viên tạo tay, gắn vào hạng mục."""

    _name = "daily.task.team"
    _description = "Team công việc"
    _order = "department_id, sequence, name, id"

    sequence = fields.Integer(string="STT", default=10, index=True)
    name = fields.Char(string="Tên Team", required=True, index=True)
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        required=True,
        index=True,
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Ghi chú")
    work_group_ids = fields.One2many(
        "daily.task.work.group",
        "team_id",
        string="Hạng mục",
    )
    work_group_count = fields.Integer(
        string="Số hạng mục",
        compute="_compute_work_group_count",
    )

    _sql_constraints = [
        (
            "daily_task_team_uniq",
            "unique(department_id, name)",
            "Team này đã tồn tại trong phòng ban.",
        )
    ]

    @api.depends("name", "department_id")
    def _compute_display_name(self):
        for rec in self:
            dept = rec.department_id.display_name if rec.department_id else ""
            rec.display_name = "%s (%s)" % (rec.name, dept) if dept else (rec.name or "")

    def _compute_work_group_count(self):
        Group = self.env["daily.task.work.group"]
        for rec in self:
            rec.work_group_count = Group.search_count([("team_id", "=", rec.id)])

    @api.constrains("name")
    def _check_name(self):
        for rec in self:
            if not (rec.name or "").strip():
                raise ValidationError("Vui lòng nhập tên Team.")
