# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyTaskEmployee(models.Model):
    _name = "daily.task.employee"
    _description = "Nhân viên (Quản lý công việc)"
    _order = "name"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Hồ sơ nhân viên",
        ondelete="restrict",
        index=True,
    )
    name = fields.Char(string="Tên nhân viên", required=True, index=True)
    email = fields.Char(string="Email")
    active = fields.Boolean(default=True)
    department_id = fields.Many2one(
        related="employee_id.department_id",
        string="Bộ phận (HR)",
        store=True,
        readonly=True,
    )
    task_ids = fields.One2many("daily.task", "assignee_id", string="Công việc")
    task_count = fields.Integer(compute="_compute_task_count", string="Số việc")

    _employee_uniq = models.Constraint(
        "unique(employee_id)",
        "Mỗi hồ sơ nhân viên chỉ được liên kết một lần.",
    )

    @api.depends("task_ids")
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            self.name = self.employee_id.name
            self.email = self._email_from_hr(self.employee_id)
            if self.employee_id.active is not None:
                self.active = self.employee_id.active

    @api.model
    def _normalize_email(self, value):
        text = (value or "").strip()
        if not text:
            return False
        if "@" not in text or " " in text:
            return False
        return text

    @api.model
    def _email_from_hr(self, hr):
        user = hr.user_id if hr else False
        for cand in (
            hr.work_email if hr else False,
            hr.private_email if hr else False,
            user.email if user else False,
            user.login if user else False,
        ):
            mail = self._normalize_email(cand)
            if mail:
                return mail
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("employee_id"):
                hr = self.env["hr.employee"].browse(vals["employee_id"])
                vals.setdefault("name", hr.name)
                if not vals.get("email"):
                    vals["email"] = self._email_from_hr(hr)
            if "email" in vals:
                vals["email"] = self._normalize_email(vals.get("email"))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("employee_id"):
            hr = self.env["hr.employee"].browse(vals["employee_id"])
            vals.setdefault("name", hr.name)
            if "email" not in vals:
                vals["email"] = self._email_from_hr(hr)
        if "email" in vals:
            vals["email"] = self._normalize_email(vals.get("email"))
        return super().write(vals)

    @api.constrains("email")
    def _check_email(self):
        for rec in self:
            if rec.email and not self._normalize_email(rec.email):
                raise ValidationError("Email không hợp lệ: %s" % rec.email)

    @api.model
    def get_or_create_from_hr(self, hr_employee_id):
        hr_employee_id = int(hr_employee_id)
        existing = self.search([("employee_id", "=", hr_employee_id)], limit=1)
        if existing:
            if existing.email and not self._normalize_email(existing.email):
                existing.write({"email": False})
            return existing
        # SQL bypass HR visibility mixin (LUG / hr_employee_hrm_detail)
        self.env.cr.execute(
            """
            SELECT e.id, e.name, e.work_email, u.login, p.email
              FROM hr_employee e
         LEFT JOIN res_users u ON u.id = e.user_id
         LEFT JOIN res_partner p ON p.id = u.partner_id
             WHERE e.id = %s
            """,
            (hr_employee_id,),
        )
        row = self.env.cr.fetchone()
        if not row:
            raise ValidationError("Không tìm thấy hồ sơ nhân viên.")
        _eid, hr_name, work_email, login, user_email = row
        email = (
            self._normalize_email(work_email)
            or self._normalize_email(user_email)
            or self._normalize_email(login)
        )
        by_name = self.search(
            [("name", "=ilike", hr_name), ("employee_id", "=", False)],
            limit=1,
        )
        if by_name:
            by_name.write(
                {
                    "employee_id": hr_employee_id,
                    "email": email or False,
                }
            )
            return by_name
        return self.create(
            {
                "employee_id": hr_employee_id,
                "name": hr_name,
                "email": email,
            }
        )

    def action_open_hr_employee(self):
        self.ensure_one()
        if not self.employee_id:
            raise ValidationError("Chưa liên kết hồ sơ nhân viên.")
        return {
            "type": "ir.actions.act_window",
            "name": "Hồ sơ nhân viên",
            "res_model": "hr.employee",
            "res_id": self.employee_id.id,
            "view_mode": "form",
            "target": "current",
        }
