# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
    manager_ids = fields.Many2many(
        "res.users",
        "daily_task_team_manager_rel",
        "team_id",
        "user_id",
        string="User quản lý team",
        domain="[('share', '=', False), ('active', '=', True)]",
        help="Quản lý toàn bộ hạng mục của team: thêm việc, sửa việc chung, duyệt Plan nhân sự trong team.",
    )
    member_ids = fields.Many2many(
        "res.users",
        "daily_task_team_member_rel",
        "team_id",
        "user_id",
        string="User Group",
        domain="[('share', '=', False), ('active', '=', True)]",
        help="Thành viên của team — dùng để xác định user thuộc team nào (tự điền Team khi tạo hạng mục).",
    )
    member_count = fields.Integer(string="Số user", compute="_compute_member_count")
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

    @api.depends("member_ids")
    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.member_ids)

    def _compute_work_group_count(self):
        Group = self.env["daily.task.work.group"]
        for rec in self:
            rec.work_group_count = Group.search_count([("team_id", "=", rec.id)])

    def write(self, vals):
        self.env["daily.task"]._req_cache_clear()
        if "manager_ids" in vals and not self.env.su \
                and not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới chọn được User quản lý team.")
        return super().write(vals)

    def set_team_managers(self, user_ids):
        """Chọn User quản lý team (từ Bảng hạng mục). Chỉ Quản lý module."""
        self.ensure_one()
        if not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới chọn được User quản lý team.")
        ids = []
        for raw in user_ids or []:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        users = self.env["res.users"].sudo().search(
            [("id", "in", ids), ("share", "=", False), ("active", "=", True)]
        )
        self.sudo().write({"manager_ids": [(6, 0, users.ids)]})
        return [{"id": u.id, "name": u.name or ""} for u in users]

    @api.constrains("name")
    def _check_name(self):
        for rec in self:
            if not (rec.name or "").strip():
                raise ValidationError("Vui lòng nhập tên Team.")
