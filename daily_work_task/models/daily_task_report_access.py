# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyTaskReportAccess(models.Model):
    """
    Phân quyền Báo cáo tổng:
    - Chọn phòng ban → xem tất cả NV trong phòng ban đó
    - và/hoặc chọn User bị xem → chỉ xem các NV cụ thể (không cần cả phòng)
    """

    _name = "daily.task.report.access"
    _description = "Phân quyền Báo cáo tổng theo phòng ban / nhân viên"
    _order = "employee_id"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="User được xem",
        required=True,
        ondelete="cascade",
        index=True,
        help="Người được quyền mở Báo cáo tổng.",
        domain="[('user_id', '!=', False)]",
    )
    department_ids = fields.Many2many(
        "hr.department",
        "daily_task_report_access_dept_rel",
        "access_id",
        "department_id",
        string="Phòng ban được xem",
        help="Chọn phòng ban → được xem toàn bộ nhân viên thuộc phòng ban đó.",
    )
    target_ids = fields.Many2many(
        "hr.employee",
        "daily_task_report_access_target_rel",
        "access_id",
        "employee_id",
        string="User bị xem",
        help="Chọn từng nhân viên khi không muốn mở cả phòng ban. "
        "Có thể dùng riêng hoặc kết hợp với phòng ban.",
        domain="[('user_id', '!=', False)]",
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Ghi chú")
    user_id = fields.Many2one(
        "res.users",
        string="Tài khoản login",
        related="employee_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )

    _sql_constraints = [
        (
            "daily_task_report_access_employee_uniq",
            "unique(employee_id)",
            "Đã có dòng phân quyền Báo cáo tổng cho nhân viên này. Hãy sửa dòng hiện có.",
        )
    ]

    @api.depends("employee_id", "department_ids", "target_ids")
    def _compute_name(self):
        for rec in self:
            viewer = rec.employee_id.name or "?"
            parts = []
            if rec.department_ids:
                depts = ", ".join(rec.department_ids.mapped("name")[:3])
                if len(rec.department_ids) > 3:
                    depts += "…"
                parts.append("PB: %s" % depts)
            if rec.target_ids:
                targets = ", ".join(rec.target_ids.mapped("name")[:3])
                if len(rec.target_ids) > 3:
                    targets += "…"
                parts.append("NV: %s" % targets)
            rec.name = "%s → [%s]" % (viewer, " | ".join(parts) or "chưa chọn")

    @api.constrains("employee_id", "department_ids", "target_ids")
    def _check_scope(self):
        for rec in self:
            if not rec.employee_id.user_id:
                raise ValidationError(
                    "«%s» chưa gắn Related User — không đăng nhập được để dùng quyền."
                    % (rec.employee_id.name or "")
                )
            if not rec.department_ids and not rec.target_ids:
                raise ValidationError(
                    "Vui lòng chọn ít nhất một «Phòng ban được xem» "
                    "hoặc «User bị xem»."
                )
            if rec.employee_id in rec.target_ids:
                raise ValidationError(
                    "Không chọn chính mình trong «User bị xem»."
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_viewer_group()
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_viewer_group()
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    def _ensure_viewer_group(self):
        """Có quyền BCT → tự gán nhóm Người xem (để mở menu Báo cáo tổng)."""
        g_viewer = self.env.ref(
            "daily_work_task.group_daily_work_viewer", raise_if_not_found=False
        )
        if not g_viewer:
            return
        for rec in self:
            user = rec.user_id
            if user and g_viewer not in user.group_ids:
                user.sudo().write({"group_ids": [(4, g_viewer.id)]})

    @api.model
    def reportable_department_ids_for_user(self, user=None):
        """
        Danh sách ID phòng ban được xem BCT (chỉ phần chọn theo phòng ban).
        None = quản lý / xem tất cả.
        [] = không có phòng ban nào được tích.
        """
        user = user or self.env.user
        Task = self.env["daily.task"]
        if Task._is_manager():
            return None
        lines = self.sudo().search(
            [
                ("active", "=", True),
                ("user_id", "=", user.id),
            ]
        )
        return list(set(lines.mapped("department_ids").ids))

    @api.model
    def reportable_employee_ids_for_user(self, user=None):
        """
        Danh sách ID nhân viên được xem trên Báo cáo tổng
        (= NV thuộc phòng ban đã chọn ∪ User bị xem).
        None = quản lý / xem tất cả.
        [] = chưa được phân quyền.
        """
        user = user or self.env.user
        Task = self.env["daily.task"]
        if Task._is_manager():
            return None
        lines = self.sudo().search(
            [
                ("active", "=", True),
                ("user_id", "=", user.id),
            ]
        )
        emp_ids = set(lines.mapped("target_ids").ids)
        dept_ids = list(set(lines.mapped("department_ids").ids))
        if dept_ids:
            self.env.cr.execute(
                """
                SELECT e.id
                  FROM hr_employee e
             LEFT JOIN hr_version v ON v.id = e.current_version_id
                 WHERE COALESCE(e.active, true) = true
                   AND v.department_id IN %s
                """,
                (tuple(dept_ids),),
            )
            emp_ids.update(row[0] for row in self.env.cr.fetchall())
        return list(emp_ids)
