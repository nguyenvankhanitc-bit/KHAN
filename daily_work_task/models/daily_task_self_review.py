# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DailyTaskSelfReview(models.Model):
    """Phân quyền TỰ KIỂM TRA công việc cá nhân.

    User được cấp quyền thấy việc của chính mình trên Kiểm tra CV và tự Xác nhận QL /
    đánh giá % Hoàn thành / ghi chú (vd: quản lý không có cấp trên duyệt).
    """

    _name = "daily.task.self.review"
    _description = "Phân quyền tự kiểm tra công việc cá nhân"
    _order = "user_id"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        index=True,
        ondelete="cascade",
        domain="[('share', '=', False)]",
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Nhân viên", compute="_compute_employee", store=True,
    )
    department_id = fields.Many2one(
        "hr.department", string="Phòng ban", compute="_compute_employee", store=True,
    )
    active = fields.Boolean(string="Đang áp dụng", default=True)
    note = fields.Char(string="Ghi chú")

    _user_uniq = models.Constraint(
        "unique(user_id)",
        "User này đã có quyền tự kiểm tra.",
    )

    @api.depends("user_id")
    def _compute_employee(self):
        Emp = self.env["hr.employee"].sudo()
        for rec in self:
            emp = Emp.search([("user_id", "=", rec.user_id.id)], limit=1) if rec.user_id else Emp
            rec.employee_id = emp
            rec.department_id = emp.department_id

    @api.model
    def user_can_self_review(self, user=None):
        user = user or self.env.user
        return bool(
            self.sudo().search_count([("user_id", "=", user.id), ("active", "=", True)], limit=1)
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._after_change()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._after_change()
        return res

    def unlink(self):
        res = super().unlink()
        self._after_change()
        return res

    def _after_change(self):
        self.env["daily.task"]._req_cache_clear()
        # Menu Kiểm tra CV hiện / ẩn theo quyền → xoá cache menu
        self.env.cr.postcommit.add(self.env.registry.clear_cache)
