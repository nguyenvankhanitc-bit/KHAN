# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyTaskAccess(models.Model):
    """
    Mẫu Excel (đúng ý dùng):
    User được phân quyền (Khan) | Bộ phận | Xem việc của (Hùng, Phú, Thành) | Xem | Giao | Sửa | Xóa
    → Khan thấy / giao việc của Hùng, Phú, Thành.
    """

    _name = "daily.task.access"
    _description = "Phân quyền công việc hàng ngày"
    _order = "employee_id"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="User được phân quyền",
        required=True,
        ondelete="cascade",
        index=True,
        help="Nhân viên A (vd: Nguyễn Văn Khan) — người được xem / giao việc của người khác.",
        domain="[('user_id', '!=', False)]",
    )
    department_id = fields.Many2one(
        related="employee_id.department_id",
        string="Bộ phận",
        store=True,
    )
    target_ids = fields.Many2many(
        "hr.employee",
        "daily_task_access_grantee_rel",
        "access_id",
        "employee_id",
        string="Xem việc của (chọn nhiều)",
        help="Các nhân viên B (vd: Hùng, Phú, Thành) — việc của họ sẽ hiện cho A.",
    )
    perm_view = fields.Boolean(string="Xem", default=True)
    perm_assign = fields.Boolean(string="Giao", default=False)
    perm_edit = fields.Boolean(string="Chỉnh sửa", default=False)
    perm_delete = fields.Boolean(string="Xóa", default=False)
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
    grantee_id = fields.Many2one("hr.employee", string="Grantee (legacy)")

    _sql_constraints = [
        (
            "daily_task_access_employee_uniq",
            "unique(employee_id)",
            "Đã có dòng phân quyền cho nhân viên này. Hãy sửa dòng hiện có và thêm người vào «Xem việc của».",
        )
    ]

    @api.depends("employee_id", "target_ids")
    def _compute_name(self):
        for rec in self:
            viewer = rec.employee_id.name or "?"
            targets = ", ".join(rec.target_ids.mapped("name")[:5]) or "(chưa chọn)"
            if len(rec.target_ids) > 5:
                targets += "…"
            rec.name = "%s → [%s]" % (viewer, targets)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id and self.target_ids:
            self.target_ids = self.target_ids.filtered(
                lambda e: e.id != self.employee_id.id
            )

    @api.onchange("perm_assign", "perm_edit", "perm_delete")
    def _onchange_perm_implies_view(self):
        if self.perm_assign or self.perm_edit or self.perm_delete:
            self.perm_view = True

    @api.constrains("employee_id", "target_ids")
    def _check_targets(self):
        for rec in self:
            if not rec.employee_id.user_id:
                raise ValidationError(
                    "«%s» chưa gắn Related User — không đăng nhập được để dùng quyền."
                    % (rec.employee_id.name or "")
                )
            if not rec.target_ids:
                raise ValidationError(
                    "Vui lòng chọn ít nhất một nhân viên ở «Xem việc của (chọn nhiều)»."
                )
            if rec.employee_id in rec.target_ids:
                raise ValidationError(
                    "Không chọn chính mình trong «Xem việc của». Việc của mình xem ở Nhân viên nhập CV."
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("perm_assign") or vals.get("perm_edit") or vals.get("perm_delete"):
                vals["perm_view"] = True
            # migrate: grantee_ids cũ → target_ids
            if vals.get("grantee_ids") and not vals.get("target_ids"):
                vals["target_ids"] = vals["grantee_ids"]
        records = super().create(vals_list)
        records._after_access_change()
        return records

    def write(self, vals):
        if vals.get("perm_assign") or vals.get("perm_edit") or vals.get("perm_delete"):
            vals = dict(vals, perm_view=True)
        if vals.get("grantee_ids") and not vals.get("target_ids"):
            vals = dict(vals, target_ids=vals["grantee_ids"])
        old_users = self.mapped("user_id")
        res = super().write(vals)
        self._after_access_change(extra_users=old_users)
        return res

    def unlink(self):
        users = self.mapped("user_id")
        res = super().unlink()
        users._sync_daily_work_employees()
        self.env.registry.clear_cache()
        return res

    def _after_access_change(self, extra_users=None):
        users = self.mapped("user_id")
        if extra_users:
            users |= extra_users
        self._ensure_security_groups()
        users._sync_daily_work_employees()
        self.env.registry.clear_cache()

    def _ensure_security_groups(self):
        """Tự gán nhóm Người xem / Người giao việc theo tick quyền."""
        Group = self.env["res.groups"].sudo()
        g_viewer = Group.search(
            [("id", "=", self.env.ref("daily_work_task.group_daily_work_viewer").id)],
            limit=1,
        )
        g_assigner = Group.search(
            [("id", "=", self.env.ref("daily_work_task.group_daily_work_assigner").id)],
            limit=1,
        )
        for rec in self:
            user = rec.user_id
            if not user:
                continue
            to_add = []
            if (rec.perm_view or rec.perm_edit or rec.perm_delete) and g_viewer:
                if g_viewer not in user.group_ids:
                    to_add.append(g_viewer.id)
            if rec.perm_assign and g_assigner:
                if g_assigner not in user.group_ids:
                    to_add.append(g_assigner.id)
            if to_add:
                user.sudo().write({"group_ids": [(4, gid) for gid in to_add]})


class ResUsers(models.Model):
    _inherit = "res.users"

    daily_work_access_ids = fields.One2many(
        "daily.task.access",
        "user_id",
        string="Phân quyền CVHN",
    )
    daily_work_view_employee_ids = fields.Many2many(
        "hr.employee",
        "daily_work_user_view_employee_rel",
        "user_id",
        "employee_id",
        string="NV được xem việc (CVHN)",
    )
    daily_work_assign_employee_ids = fields.Many2many(
        "hr.employee",
        "daily_work_user_assign_employee_rel",
        "user_id",
        "employee_id",
        string="NV được giao việc (CVHN)",
    )
    daily_work_edit_employee_ids = fields.Many2many(
        "hr.employee",
        "daily_work_user_edit_employee_rel",
        "user_id",
        "employee_id",
        string="NV được sửa (CVHN)",
    )
    daily_work_delete_employee_ids = fields.Many2many(
        "hr.employee",
        "daily_work_user_delete_employee_rel",
        "user_id",
        "employee_id",
        string="NV được xóa (CVHN)",
    )

    def _sync_daily_work_employees(self):
        """
        Dòng access: employee_id = Khan (người được quyền),
        target_ids = Hùng, Phú, Thành (việc được xem).
        → Khan.user.daily_work_view_employee_ids = [Hùng, Phú, Thành]
        """
        Access = self.env["daily.task.access"].sudo()
        for user in self:
            if not user:
                continue
            lines = Access.search([("active", "=", True), ("user_id", "=", user.id)])
            view_ids = set()
            assign_ids = set()
            edit_ids = set()
            delete_ids = set()
            for line in lines:
                targets = line.target_ids.ids
                if line.perm_view:
                    view_ids.update(targets)
                if line.perm_assign:
                    assign_ids.update(targets)
                if line.perm_edit:
                    edit_ids.update(targets)
                if line.perm_delete:
                    delete_ids.update(targets)
            user.sudo().write(
                {
                    "daily_work_view_employee_ids": [(6, 0, list(view_ids))],
                    "daily_work_assign_employee_ids": [(6, 0, list(assign_ids))],
                    "daily_work_edit_employee_ids": [(6, 0, list(edit_ids))],
                    "daily_work_delete_employee_ids": [(6, 0, list(delete_ids))],
                }
            )
