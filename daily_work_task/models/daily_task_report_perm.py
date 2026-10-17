# -*- coding: utf-8 -*-
"""Cài đặt → Phân quyền báo cáo (ma trận giống Phân quyền phân công công việc).

Nhóm: Báo cáo CV theo hạng mục (catrep) · Báo cáo tổng hợp theo hạng mục (summary).
Quyền: Xem · Xem NV khác · Chỉnh sửa · Xuất Excel.
- Quản lý module: đủ quyền.
- User chưa có dòng phân quyền: dùng như trước (xem / sửa / xuất báo cáo của chính mình;
  xem NV khác theo quyền quản lý sẵn có).
- User đã có dòng: đúng theo ô đã tích.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

GROUPS = ("catrep", "summary")
PERMS = ("view", "others", "write", "export")
LABELS = {"catrep": "Báo cáo CV theo hạng mục", "summary": "Báo cáo tổng hợp theo hạng mục"}
ACTS = {"view": "xem", "others": "xem báo cáo của nhân viên khác ở", "write": "chỉnh sửa", "export": "xuất Excel"}


class DailyTaskReportPerm(models.Model):
    _name = "daily.task.report.perm"
    _description = "Phân quyền báo cáo"
    _order = "employee_id"

    employee_id = fields.Many2one("hr.employee", string="User được phân quyền", required=True,
                                  ondelete="cascade", index=True, domain="[('user_id', '!=', False)]")
    department_id = fields.Many2one(related="employee_id.department_id", string="Bộ phận", store=True)
    user_id = fields.Many2one("res.users", related="employee_id.user_id", store=True, readonly=True, index=True)
    active = fields.Boolean(default=True)

    perm_catrep_view = fields.Boolean(string="BC theo hạng mục: Xem")
    perm_catrep_others = fields.Boolean(string="BC theo hạng mục: Xem NV khác")
    perm_catrep_write = fields.Boolean(string="BC theo hạng mục: Chỉnh sửa")
    perm_catrep_export = fields.Boolean(string="BC theo hạng mục: Xuất Excel")
    perm_summary_view = fields.Boolean(string="BC tổng hợp: Xem")
    perm_summary_others = fields.Boolean(string="BC tổng hợp: Xem NV khác")
    perm_summary_write = fields.Boolean(string="BC tổng hợp: Chỉnh sửa")
    perm_summary_export = fields.Boolean(string="BC tổng hợp: Xuất Excel")

    _employee_uniq = models.Constraint("UNIQUE(employee_id)", "Mỗi nhân viên chỉ có 1 dòng phân quyền báo cáo.")

    @api.constrains("employee_id")
    def _check_employee_user(self):
        for rec in self:
            if not rec.employee_id.user_id:
                raise ValidationError("«%s» chưa gắn user đăng nhập." % (rec.employee_id.name or ""))

    # ------------------------------------------------------------------
    @api.model
    def _is_manager(self, user=None):
        return (user or self.env.user).has_group("daily_work_task.group_daily_work_manager")

    @api.model
    def get_map(self, user=None):
        """{'catrep': {view, others, write, export}, 'summary': {...}, 'configured': bool}.
        others=None → chưa cấu hình, dùng quyền quản lý sẵn có."""
        user = user or self.env.user
        if self.env.su or self._is_manager(user):
            return {g: {p: True for p in PERMS} for g in GROUPS} | {"configured": True}
        line = self.sudo().search([("active", "=", True), ("user_id", "=", user.id)], limit=1)
        if not line:
            return {g: {"view": True, "others": None, "write": True, "export": True} for g in GROUPS} | {"configured": False}
        return {g: {p: bool(line["perm_%s_%s" % (g, p)]) for p in PERMS} for g in GROUPS} | {"configured": True}

    @api.model
    def check(self, group, perm):
        val = self.get_map().get(group, {}).get(perm)
        if val is False:
            raise AccessError("Bạn không có quyền %s «%s»." % (ACTS.get(perm, perm), LABELS.get(group, group)))
        return val

    # ------------------------------------------------------------------ ma trận (OWL)
    @api.model
    def get_report_perm_matrix(self):
        if not self._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền báo cáo.")
        employees = self.env["hr.employee"].sudo().search([("user_id", "!=", False), ("active", "=", True)], order="name")
        emp_payload = [{
            "id": e.id, "name": e.name or "",
            "department_id": e.department_id.id or 0,
            "department_name": e.department_id.display_name or "",
        } for e in employees]
        rows = []
        for line in self.sudo().search([], order="department_id, employee_id"):
            row = {"id": line.id, "employee_id": line.employee_id.id, "department_id": line.department_id.id or 0}
            for g in GROUPS:
                row[g] = {p: bool(line["perm_%s_%s" % (g, p)]) for p in PERMS}
            rows.append(row)
        return {"rows": rows, "employees": emp_payload}

    @api.model
    def save_report_perm_matrix(self, rows):
        if not self._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền báo cáo.")
        keep = set()
        for row in rows or []:
            emp_id = int(row.get("employee_id") or 0)
            if not emp_id:
                continue
            vals = {"active": True}
            for g in GROUPS:
                grp = row.get(g) or {}
                flags = {p: bool(grp.get(p)) for p in PERMS}
                if flags["others"] or flags["write"] or flags["export"]:
                    flags["view"] = True
                if not flags["view"]:
                    flags = {p: False for p in PERMS}
                for p in PERMS:
                    vals["perm_%s_%s" % (g, p)] = flags[p]
            rec = self.sudo().search([("employee_id", "=", emp_id)], limit=1)
            if rec:
                rec.write(vals)
            else:
                rec = self.sudo().create(dict(vals, employee_id=emp_id))
            keep.add(rec.id)
        self.sudo().search([("id", "not in", list(keep) or [0])]).unlink()
        return True


class DailyTask(models.Model):
    _inherit = "daily.task"

    @api.model
    def _report_perm_apply(self, group, data, requested_employee_id=None):
        """Áp quyền vào dữ liệu báo cáo: chặn Xem, giới hạn Xem NV khác, gắn cờ cho UI."""
        Perm = self.env["daily.task.report.perm"]
        pmap = Perm.get_map()[group]
        others = pmap["others"]
        if others is not None:
            data["can_pick_employee"] = bool(others) and bool(data.get("can_pick_employee", True))
            if others is False and data.get("filters"):
                me = self.env["hr.employee"].sudo().search([("user_id", "=", self.env.uid)], limit=1)
                data["filters"]["employees"] = [e for e in data["filters"].get("employees") or [] if e.get("id") == me.id]
        data["report_perm"] = {k: (v if v is not None else True) for k, v in pmap.items()}
        return data

    @api.model
    def _report_perm_employee(self, group, employee_id):
        """Bỏ chọn NV khác nếu không có quyền «Xem NV khác»."""
        if not employee_id:
            return employee_id
        others = self.env["daily.task.report.perm"].get_map()[group]["others"]
        if others is False:
            me = self.env["hr.employee"].sudo().search([("user_id", "=", self.env.uid)], limit=1)
            if int(employee_id) != me.id:
                return False
        return employee_id

    # --- Báo cáo CV theo hạng mục
    @api.model
    def get_category_report(self, year=None, month=None, filters=None):
        if self.env.context.get("skip_report_perm"):
            # Gọi nội bộ từ Báo cáo tổng hợp (đã kiểm tra quyền nhóm «summary»)
            return super().get_category_report(year=year, month=month, filters=filters)
        self.env["daily.task.report.perm"].check("catrep", "view")
        filters = dict(filters or {})
        if filters.get("employee_id"):
            filters["employee_id"] = self._report_perm_employee("catrep", filters["employee_id"])
        data = super().get_category_report(year=year, month=month, filters=filters)
        return self._report_perm_apply("catrep", data)

    @api.model
    def export_category_report_excel(self, year=None, month=None, filters=None):
        self.env["daily.task.report.perm"].check("catrep", "export")
        return super().export_category_report_excel(year=year, month=month, filters=filters)

    # --- Báo cáo tổng hợp theo hạng mục
    @api.model
    def get_user_summary(self, year=None, month=None, employee_id=None):
        Perm = self.env["daily.task.report.perm"]
        Perm.check("summary", "view")
        employee_id = self._report_perm_employee("summary", employee_id)
        data = super(DailyTask, self.with_context(skip_report_perm=True)).get_user_summary(
            year=year, month=month, employee_id=employee_id)
        data = self._report_perm_apply("summary", data)
        if Perm.get_map()["summary"]["write"] is False:
            data["can_edit_self"] = False
        return data

    @api.model
    def save_user_summary(self, year, month, employee_id=None, vals=None):
        self.env["daily.task.report.perm"].check("summary", "write")
        return super().save_user_summary(year, month, self._report_perm_employee("summary", employee_id), vals)

    @api.model
    def export_user_summary_excel(self, year=None, month=None, employee_id=None):
        self.env["daily.task.report.perm"].check("summary", "export")
        return super().export_user_summary_excel(year=year, month=month, employee_id=employee_id)
