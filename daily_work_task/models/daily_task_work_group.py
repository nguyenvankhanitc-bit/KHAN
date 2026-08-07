# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyTaskWorkGroup(models.Model):
    """Nhóm công việc theo phòng ban — gắn User áp dụng (nhiều user)."""

    _name = "daily.task.work.group"
    _description = "Nhóm công việc"
    _order = "department_id, sequence, name, id"

    sequence = fields.Integer(string="STT", default=10, index=True)
    name = fields.Char(string="Tên hạng mục", required=True, index=True)
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        required=True,
        index=True,
        ondelete="restrict",
    )
    user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_user_rel",
        "group_id",
        "user_id",
        string="User áp dụng",
        domain="[('share', '=', False), ('active', '=', True)]",
        help="Các user được dùng nhóm này khi thêm công việc. "
        "Để trống = mọi nhân viên thuộc phòng ban đều dùng được.",
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Ghi chú")
    task_count = fields.Integer(
        string="Số công việc",
        compute="_compute_task_count",
    )

    _sql_constraints = [
        (
            "daily_task_work_group_uniq",
            "unique(department_id, name)",
            "Nhóm công việc này đã tồn tại trong phòng ban.",
        )
    ]

    @api.depends("name", "department_id")
    def _compute_display_name(self):
        for rec in self:
            dept = rec.department_id.display_name if rec.department_id else ""
            rec.display_name = "%s (%s)" % (rec.name, dept) if dept else (rec.name or "")

    def _compute_task_count(self):
        Task = self.env["daily.task"]
        for rec in self:
            rec.task_count = Task.search_count([("work_group_id", "=", rec.id)])

    @api.constrains("name", "department_id")
    def _check_name(self):
        for rec in self:
            if not (rec.name or "").strip():
                raise ValidationError("Vui lòng nhập tên nhóm công việc.")

    @api.onchange("department_id")
    def _onchange_department_id(self):
        """Gợi ý: nếu chưa chọn user, giữ trống (áp dụng cả phòng ban)."""
        if self.department_id and self.user_ids:
            # Giữ user đã chọn — không tự xóa khi đổi phòng ban
            return

    @api.model
    def get_groups_for_user(self, department_id=None, user_id=None, allow_all_for_manager=False):
        """Nhóm công việc user được phép dùng (theo phòng ban + User áp dụng).

        - Có gắn User áp dụng → chỉ các user trong list thấy hạng mục đó.
        - Để trống User áp dụng → mọi user thuộc phòng ban đều dùng được.
        - Quản lý (allow_all_for_manager=True) thấy tất cả hạng mục active.
        """
        uid = int(user_id or self.env.uid)
        dept_id = int(department_id or 0)
        domain = [("active", "=", True)]
        if dept_id:
            domain.append(("department_id", "=", dept_id))
        groups = self.sudo().search(domain, order="sequence, name, id")
        is_manager = False
        if allow_all_for_manager:
            is_manager = self.env["daily.task"]._is_manager()
        result = []
        for g in groups:
            if not is_manager and g.user_ids and uid not in g.user_ids.ids:
                continue
            result.append(
                {
                    "id": g.id,
                    "name": g.name or "",
                    "sequence": int(g.sequence or 0),
                    "department_id": g.department_id.id if g.department_id else False,
                    "department": g.department_id.display_name if g.department_id else "",
                }
            )
        return result

    @api.model
    def get_groups_for_department(self, department_id):
        """Tương thích cũ — lọc theo phòng ban + user đang đăng nhập."""
        return self.get_groups_for_user(department_id=department_id, user_id=self.env.uid)
