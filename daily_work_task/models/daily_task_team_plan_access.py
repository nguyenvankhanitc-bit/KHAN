# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTaskTeamPlanAccess(models.Model):
    """
    Phân quyền Plan tổng team: Xem / Thêm / Chỉnh sửa / Xóa công việc chung trên Plan tổng.
    Xem → được mở menu Plan tổng team; Thêm / Chỉnh sửa / Xóa luôn kèm Xem.
    """

    _name = "daily.task.team.plan.access"
    _description = "Phân quyền Plan tổng team"
    _order = "department_id, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="User được phân quyền",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('user_id', '!=', False)]",
    )
    department_id = fields.Many2one(related="employee_id.department_id", string="Bộ phận", store=True)
    user_id = fields.Many2one(
        "res.users",
        string="Tài khoản login",
        related="employee_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )
    perm_view = fields.Boolean(string="Xem")
    perm_create = fields.Boolean(string="Thêm")
    perm_write = fields.Boolean(string="Chỉnh sửa")
    perm_unlink = fields.Boolean(string="Xóa")
    active = fields.Boolean(default=True)

    _employee_uniq = models.Constraint(
        "unique(employee_id)",
        "Đã có dòng phân quyền Plan tổng cho nhân viên này. Hãy sửa dòng hiện có.",
    )

    @api.constrains("employee_id")
    def _check_employee_user(self):
        for rec in self:
            if not rec.employee_id.user_id:
                raise ValidationError(
                    "«%s» chưa gắn Related User — không đăng nhập được để dùng quyền."
                    % (rec.employee_id.name or "")
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["daily.task"]._req_cache_clear()
        self.env.cr.postcommit.add(self.env.registry.clear_cache)
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env["daily.task"]._req_cache_clear()
        self.env.cr.postcommit.add(self.env.registry.clear_cache)
        return res

    def unlink(self):
        res = super().unlink()
        self.env["daily.task"]._req_cache_clear()
        self.env.cr.postcommit.add(self.env.registry.clear_cache)
        return res

    # ------------------------------------------------------------------
    @api.model
    def get_perms(self, user=None):
        """{'create','write','unlink'} của user trên Plan tổng. Quản lý module → tất cả."""
        user = user or self.env.user
        return dict(self.env["daily.task"]._req_cache(
            ("tpa_perms", self.env.uid, user.id),
            lambda: self._compute_perms(user),
        ))

    @api.model
    def _compute_perms(self, user):
        if self.env["daily.task.assign.access"]._is_manager(user):
            return {"view": True, "create": True, "write": True, "unlink": True}
        line = self.sudo().search([("active", "=", True), ("user_id", "=", user.id)], limit=1)
        return {
            "view": bool(line.perm_view or line.perm_create or line.perm_write or line.perm_unlink),
            "create": bool(line.perm_create),
            "write": bool(line.perm_write),
            "unlink": bool(line.perm_unlink),
        }

    @api.model
    def has_any(self, user=None):
        return any(self.get_perms(user).values())

    # ---- Ma trận cấu hình (OWL) ----
    @api.model
    def get_matrix(self):
        if not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền Plan tổng.")
        employees = self.env["hr.employee"].sudo().search(
            [("user_id", "!=", False), ("active", "=", True)], order="name"
        )
        lines = self.sudo().search([], order="department_id, employee_id")
        return {
            "employees": [
                {
                    "id": e.id,
                    "name": e.name or "",
                    "department_name": e.department_id.display_name if e.department_id else "",
                }
                for e in employees
            ],
            "rows": [
                {
                    "id": line.id,
                    "employee_id": line.employee_id.id,
                    "view": bool(line.perm_view or line.perm_create or line.perm_write or line.perm_unlink),
                    "create": bool(line.perm_create),
                    "write": bool(line.perm_write),
                    "unlink": bool(line.perm_unlink),
                }
                for line in lines
                if line.employee_id
            ],
        }

    @api.model
    def save_matrix(self, rows):
        """Lưu ma trận: mỗi user 1 dòng; dòng không còn trên ma trận → xóa."""
        if not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền Plan tổng.")
        keep, seen = set(), set()
        for row in rows or []:
            emp_id = int(row.get("employee_id") or 0)
            if not emp_id:
                continue
            if emp_id in seen:
                raise ValidationError("Có user bị chọn trùng trên nhiều dòng. Kiểm tra lại.")
            seen.add(emp_id)
            vals = {
                "perm_create": bool(row.get("create")),
                "perm_write": bool(row.get("write")),
                "perm_unlink": bool(row.get("unlink")),
                "active": True,
            }
            # Thêm / Chỉnh sửa / Xóa luôn kèm Xem
            vals["perm_view"] = bool(row.get("view")) or any(vals[k] for k in ("perm_create", "perm_write", "perm_unlink"))
            rec = self.sudo().with_context(active_test=False).search([("employee_id", "=", emp_id)], limit=1)
            if rec:
                rec.write(vals)
            else:
                rec = self.sudo().create([dict(vals, employee_id=emp_id)])
            keep.add(rec.id)
        self.sudo().with_context(active_test=False).search([("id", "not in", list(keep))]).unlink()
        return True
