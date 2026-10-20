# -*- coding: utf-8 -*-
"""Cài đặt → Phân quyền báo cáo (ma trận giống Phân quyền phân công công việc).

Nhóm: mọi mục con của BÁO CÁO (Báo cáo tổng, cá nhân, theo hạng mục, tổng hợp theo hạng mục,
công việc tháng, CV chi tiết team, hiệu suất, KPI).
Quyền: Xem · Xem NV khác · Chỉnh sửa · Xuất Excel.
- Quản lý module: đủ quyền.
- User chưa có dòng phân quyền: dùng như trước (xem / sửa / xuất báo cáo của chính mình;
  xem NV khác theo quyền quản lý sẵn có).
- User đã có dòng: đúng theo ô đã tích.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

GROUP_LIST = [
    ("summary_report", "Báo cáo tổng"),
    ("personal", "Báo cáo cá nhân"),
    ("catrep", "Báo cáo CV theo hạng mục"),
    ("summary", "Báo cáo tổng hợp theo hạng mục"),
    ("monthly", "Báo cáo công việc tháng"),
    ("team", "Báo cáo CV chi tiết team"),
    ("performance", "Báo cáo hiệu suất"),
    ("kpi", "Báo cáo KPI"),
    ("kho", "Báo cáo NV Kho"),
    ("khocv", "Báo cáo CV NV Kho"),
]
GROUPS = tuple(k for k, _l in GROUP_LIST)
PERMS = ("view", "others", "write", "export")
PERM_LABELS = {"view": "Xem", "others": "Xem NV khác", "write": "Chỉnh sửa", "export": "Xuất Excel"}
LABELS = dict(GROUP_LIST)
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

    # perm_<nhóm>_<quyền> cho mọi nhóm báo cáo
    for _g, _gl in GROUP_LIST:
        for _p in PERMS:
            locals()["perm_%s_%s" % (_g, _p)] = fields.Boolean(string="%s: %s" % (_gl, PERM_LABELS[_p]))
    del _g, _gl, _p

    _employee_uniq = models.Constraint("UNIQUE(employee_id)", "Mỗi nhân viên chỉ có 1 dòng phân quyền báo cáo.")

    def init(self):
        """Dòng tạo trước khi có nhóm báo cáo mới: nhóm mới (cột còn NULL) giữ quyền như cũ
        (Xem / Chỉnh sửa / Xuất Excel). Chỉ chạy với ô chưa từng đặt — không ghi đè lựa chọn đã lưu."""
        super().init()
        for g in GROUPS:
            self.env.cr.execute(
                "UPDATE daily_task_report_perm SET perm_%(g)s_view = TRUE, perm_%(g)s_write = TRUE,"
                " perm_%(g)s_export = TRUE, perm_%(g)s_others = COALESCE(perm_%(g)s_others, FALSE)"
                " WHERE perm_%(g)s_view IS NULL" % {"g": g}
            )

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
    def view_map(self):
        """{nhóm: có được Xem} — ẩn / hiện mục trên thanh bên."""
        pmap = self.get_map()
        return {g: bool(pmap[g]["view"]) for g in GROUPS}

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
        data = super(DailyTask, self.with_context(skip_report_perm=True)).get_category_report(
            year=year, month=month, filters=filters)
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

    # --- Báo cáo cá nhân / Báo cáo CV chi tiết team (cùng get_report_overview; team khi filters.team)
    @api.model
    def _overview_group(self, filters):
        return "team" if (filters or {}).get("team") else "personal"

    @api.model
    def get_report_overview(self, year=None, month=None, filters=None):
        if self.env.context.get("skip_report_perm"):
            return super().get_report_overview(year=year, month=month, filters=filters)
        group = self._overview_group(filters)
        self.env["daily.task.report.perm"].check(group, "view")
        filters = dict(filters or {})
        if group == "personal" and filters.get("employee_id"):
            filters["employee_id"] = self._report_perm_employee("personal", filters["employee_id"])
        data = super().get_report_overview(year=year, month=month, filters=filters)
        return self._report_perm_apply(group, data) if isinstance(data, dict) else data

    @api.model
    def export_personal_report_excel(self, year=None, month=None, filters=None, chart_images=None):
        self.env["daily.task.report.perm"].check(self._overview_group(filters), "export")
        return super().export_personal_report_excel(year=year, month=month, filters=filters, chart_images=chart_images)

    @api.model
    def export_personal_report_pdf(self, year=None, month=None, filters=None, chart_images=None):
        self.env["daily.task.report.perm"].check(self._overview_group(filters), "export")
        return super().export_personal_report_pdf(year=year, month=month, filters=filters, chart_images=chart_images)

    # --- Báo cáo tổng
    @api.model
    def get_summary_report(self, year=None, month=None):
        if not self.env.context.get("skip_report_perm"):
            self.env["daily.task.report.perm"].check("summary_report", "view")
        return super().get_summary_report(year=year, month=month)

    @api.model
    def export_summary_report_excel(self, year=None, month=None):
        self.env["daily.task.report.perm"].check("summary_report", "export")
        return super(DailyTask, self.with_context(skip_report_perm=True)).export_summary_report_excel(year=year, month=month)


class DailyTaskMonthlyReport(models.AbstractModel):
    _inherit = "daily.task.monthly.report"

    @api.model
    def get_report(self, year=None, month=None, employee_id=None):
        if not self.env.context.get("skip_report_perm"):
            self.env["daily.task.report.perm"].check("monthly", "view")
            employee_id = self.env["daily.task"]._report_perm_employee("monthly", employee_id)
        data = super(DailyTaskMonthlyReport, self.with_context(skip_report_perm=True)).get_report(
            year=year, month=month, employee_id=employee_id)
        if isinstance(data, dict):
            others = self.env["daily.task.report.perm"].get_map()["monthly"]["others"]
            if others is False:
                data["can_pick_employee"] = False
            data["report_perm"] = {k: (v if v is not None else True)
                                   for k, v in self.env["daily.task.report.perm"].get_map()["monthly"].items()}
        return data

    @api.model
    def export_excel(self, year=None, month=None, employee_id=None):
        self.env["daily.task.report.perm"].check("monthly", "export")
        employee_id = self.env["daily.task"]._report_perm_employee("monthly", employee_id)
        return super(DailyTaskMonthlyReport, self.with_context(skip_report_perm=True)).export_excel(
            year=year, month=month, employee_id=employee_id)


class DailyTaskPerformanceReport(models.AbstractModel):
    _inherit = "daily.task.performance.report"

    @api.model
    def get_performance_report(self, year=None, month=None, employee_id=None, department_id=None):
        if not self.env.context.get("skip_report_perm"):
            self.env["daily.task.report.perm"].check("performance", "view")
        return super().get_performance_report(year=year, month=month, employee_id=employee_id,
                                              department_id=department_id)

    @api.model
    def export_excel(self, year=None, month=None, department_id=None):
        self.env["daily.task.report.perm"].check("performance", "export")
        return super(DailyTaskPerformanceReport, self.with_context(skip_report_perm=True)).export_excel(
            year=year, month=month, department_id=department_id)
