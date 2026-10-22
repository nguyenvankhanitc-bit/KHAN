# -*- coding: utf-8 -*-
"""Cấu hình → Phân quyền ứng dụng Dự án (ma trận giống Phân quyền báo cáo của Công việc hằng ngày).

Nhóm: mỗi mục trên thanh bên của app Dự án.
Quyền: Xem · Xem DA người khác · Chỉnh sửa · Xuất Excel.
- Quản trị hệ thống / Quản lý dự án: đủ quyền, cấu hình được ma trận.
- User chưa có dòng phân quyền: dùng như trước (đủ quyền theo nhóm Odoo sẵn có).
- User đã có dòng: đúng theo ô đã tích.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

GROUP_LIST = [
    ("kpi", "Tổng quan / Báo cáo KPI Dự án"),
    ("intake", "Nhập dự án mới"),
    ("list", "Danh sách dự án"),
    ("track", "Theo dõi dự án"),
    ("gantt", "Gantt Chart"),
    ("assign", "Phân công nhân sự"),
    ("overdue", "Dự án trễ hạn"),
    ("milestones", "Nhắc mốc dự án"),
    ("report_all", "Báo cáo tổng thể"),
    ("people", "Báo cáo nhân sự"),
    ("perf", "Báo cáo hiệu suất"),
    ("config", "Cấu hình (Giai đoạn, Loại DA, Trạng thái, Ưu tiên)"),
    ("archived", "Thùng rác"),
    ("contacts", "Danh bạ"),
]
GROUPS = tuple(k for k, _l in GROUP_LIST)
PERMS = ("view", "others", "write", "export")
PERM_LABELS = {"view": "Xem", "others": "Thêm", "write": "Chỉnh sửa", "export": "Xuất Excel"}
LABELS = dict(GROUP_LIST)
ACTS = {"view": "xem", "others": "thêm mới ở", "write": "chỉnh sửa", "export": "xuất Excel"}
LIST_GROUPS = ("list", "overdue", "archived")


class LugProjectAppPerm(models.Model):
    _name = "lug.project.app.perm"
    _description = "Phân quyền ứng dụng Dự án"
    _order = "user_id"

    user_id = fields.Many2one("res.users", string="User được phân quyền",
                              ondelete="cascade", index=True, domain="[('share', '=', False)]")
    lug_group_ids = fields.Many2many(
        "lug.group", "lug_project_app_perm_lug_group_rel", "perm_id", "group_id",
        string="Nhóm quyền (LUG Permission)",
    )
    row_key = fields.Char(string="Dòng ma trận", index=True)
    active = fields.Boolean(default=True)

    for _g, _gl in GROUP_LIST:
        for _p in PERMS:
            locals()["perm_%s_%s" % (_g, _p)] = fields.Boolean(string="%s: %s" % (_gl, PERM_LABELS[_p]))
    del _g, _gl, _p

    @api.constrains("user_id")
    def _check_user_uniq(self):
        for rec in self:
            if not rec.user_id:
                continue
            other = self.sudo().search([("user_id", "=", rec.user_id.id), ("id", "!=", rec.id)], limit=1)
            if other:
                raise ValidationError("Mỗi user chỉ có 1 dòng phân quyền dự án.")

    @api.constrains("user_id", "lug_group_ids")
    def _check_internal_user(self):
        for rec in self:
            if not rec.user_id and not rec.lug_group_ids:
                raise ValidationError("Dòng phân quyền dự án cần ít nhất 1 user hoặc 1 nhóm quyền.")
            if rec.user_id and rec.user_id.share:
                raise ValidationError("«%s» không phải user nội bộ." % (rec.user_id.name or ""))

    # ------------------------------------------------------------------
    @api.model
    def _is_full(self, user=None):
        user = user or self.env.user
        return bool(
            user._is_superuser()
            or user.has_group("base.group_system")
            or user.has_group("project.group_project_manager")
        )

    @api.model
    def get_map(self, user=None):
        """{nhóm: {view, others=Thêm, write, export}, 'configured': bool, 'full': bool}.
        others=None → chưa cấu hình, được thêm mới."""
        user = user or self.env.user
        if self.env.su or self._is_full(user):
            return {g: {p: True for p in PERMS} for g in GROUPS} | {"configured": True, "full": True}
        lines = self.sudo().search([("active", "=", True), ("user_id", "=", user.id)], limit=1)
        if not lines and user.sudo().lug_group_ids:
            lines = self.sudo().search([
                ("active", "=", True),
                ("user_id", "=", False),
                ("lug_group_ids", "in", user.sudo().lug_group_ids.ids),
            ])
        if not lines:
            return {g: {"view": True, "others": None, "write": True, "export": True} for g in GROUPS} | {
                "configured": False, "full": False}
        return {
            g: {p: any(line["perm_%s_%s" % (g, p)] for line in lines) for p in PERMS} for g in GROUPS
        } | {"configured": True, "full": False}

    @api.model
    def get_client_map(self):
        pmap = self.get_map()
        return {
            "full": pmap["full"],
            "configured": pmap["configured"],
            "groups": {g: {k: (v if v is not None else True) for k, v in pmap[g].items()} for g in GROUPS},
        }

    @api.model
    def check(self, group, perm):
        val = self.get_map().get(group, {}).get(perm)
        if val is False:
            raise AccessError("Bạn không có quyền %s «%s»." % (ACTS.get(perm, perm), LABELS.get(group, group)))
        return val

    @api.model
    def own_only(self, group):
        """Không còn giới hạn «chỉ dự án của mình» — cột đó đã đổi thành quyền Thêm."""
        return False

    # ------------------------------------------------------------------ ma trận (OWL)
    @api.model
    def _user_payload(self, user):
        dept = user.employee_ids[:1].department_id if "employee_ids" in user._fields else False
        return {
            "id": user.id,
            "name": user.name or "",
            "login": user.login or "",
            "department_id": dept.id if dept else 0,
            "department_name": dept.display_name if dept else "",
        }

    @api.model
    def get_app_perm_matrix(self):
        if not self._is_full():
            raise AccessError("Chỉ Quản lý dự án / Quản trị viên mới cấu hình phân quyền dự án.")
        users = self.env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)], order="name")
        users = users.filtered(lambda u: not self._is_full(u))
        lug_groups = self.env["lug.group"].sudo().search([("active", "=", True)], order="name")
        rows = []
        lines = self.sudo().search([
            "|", ("user_id", "in", users.ids),
            "&", ("user_id", "=", False), ("lug_group_ids", "!=", False),
        ])
        for line in lines:
            row = {
                "id": line.id,
                "row_key": line.row_key or "",
                "user_id": line.user_id.id or 0,
                "group_ids": line.lug_group_ids.ids,
                "department_id": self._user_payload(line.user_id)["department_id"] if line.user_id else 0,
            }
            for g in GROUPS:
                row[g] = {p: bool(line["perm_%s_%s" % (g, p)]) for p in PERMS}
            rows.append(row)
        return {
            "rows": rows,
            "lug_groups": [
                {
                    "id": g.id,
                    "name": g.name or "",
                    "code": g.code or "",
                    "user_count": len(g.user_ids),
                    "user_names": [u.name or u.login or "" for u in g.user_ids.sorted("name")],
                }
                for g in lug_groups
            ],
            "users": [self._user_payload(u) for u in users],
            "groups": [{"key": k, "label": l} for k, l in GROUP_LIST],
            "perms": [{"key": p, "label": PERM_LABELS[p]} for p in PERMS],
        }

    @api.model
    def save_app_perm_matrix(self, rows):
        """rows: [{row_key, user_ids, group_ids, <nhóm>: {quyền}}] — 1 bản ghi / user + 1 bản ghi nhóm / dòng."""
        if not self._is_full():
            raise AccessError("Chỉ Quản lý dự án / Quản trị viên mới cấu hình phân quyền dự án.")
        Rec = self.sudo().with_context(active_test=False)
        valid_groups = set(self.env["lug.group"].sudo().search([]).ids)
        keep = set()
        seen_users = set()
        for index, row in enumerate(rows or []):
            user_ids = [int(u) for u in (row.get("user_ids") or []) if int(u or 0)]
            group_ids = [int(g) for g in (row.get("group_ids") or []) if int(g or 0) in valid_groups]
            if not user_ids and not group_ids:
                continue
            row_key = (row.get("row_key") or "").strip() or "row-%s" % index
            vals = {"active": True, "row_key": row_key}
            for g in GROUPS:
                grp = row.get(g) or {}
                flags = {p: bool(grp.get(p)) for p in PERMS}
                if flags["others"] or flags["write"] or flags["export"]:
                    flags["view"] = True
                if not flags["view"]:
                    flags = {p: False for p in PERMS}
                for p in PERMS:
                    vals["perm_%s_%s" % (g, p)] = flags[p]
            for user_id in user_ids:
                if user_id in seen_users:
                    raise ValidationError("Có user bị chọn trùng trên nhiều dòng phân quyền.")
                seen_users.add(user_id)
                rec = Rec.search([("user_id", "=", user_id)], limit=1)
                if rec:
                    rec.write(dict(vals, lug_group_ids=[(5, 0, 0)]))
                else:
                    rec = Rec.create(dict(vals, user_id=user_id))
                keep.add(rec.id)
            if group_ids:
                rec = Rec.search([("user_id", "=", False), ("row_key", "=", row_key), ("id", "not in", list(keep) or [0])], limit=1)
                gvals = dict(vals, lug_group_ids=[(6, 0, group_ids)])
                if rec:
                    rec.write(gvals)
                else:
                    rec = Rec.create(gvals)
                keep.add(rec.id)
        Rec.search([("id", "not in", list(keep) or [0])]).unlink()
        return True


class ProjectProjectAppPerm(models.Model):
    _inherit = "project.project"

    @api.model
    def _lug_perm(self):
        return self.env["lug.project.app.perm"]

    @api.model
    def _lug_list_perm_group(self, archived=False, overdue=False):
        if archived:
            return "archived"
        if overdue:
            return "overdue"
        group = self.env.context.get("lug_perm_group")
        return group if group in LIST_GROUPS else "list"

    @api.model
    def _lug_scoped(self, group):
        if self._lug_perm().own_only(group):
            return self.with_context(lug_perm_scope_uid=self.env.uid)
        return self

    @api.model
    def _lug_base_domain(self):
        domain = super()._lug_base_domain()
        uid = self.env.context.get("lug_perm_scope_uid")
        if uid:
            domain += [
                "|", "|", "|",
                ("user_id", "=", uid),
                ("lug_pic_id", "=", uid),
                ("lug_assignee_ids", "in", [uid]),
                ("task_ids.user_ids", "in", [uid]),
            ]
        return domain

    @api.model
    def get_lug_shell_data(self, project_id=False, period="month", type_id=False, perm_group="kpi"):
        group = perm_group if perm_group in GROUPS else "kpi"
        Perm = self._lug_perm()
        if Perm.get_map()[group]["view"] is False:
            data = {**self._get_lug_shell_header(), "dashboard": self._empty_lug_dashboard()}
        else:
            data = super(ProjectProjectAppPerm, self._lug_scoped(group)).get_lug_shell_data(
                project_id=project_id, period=period, type_id=type_id)
        data["app_perm"] = Perm.get_client_map()
        return data

    @api.model
    def get_lug_project_list_data(self, search="", offset=0, limit=50, priority=None, type_id=None,
                                  status=None, manager_id=None, date_preset=None, date_field="deadline",
                                  date_from=None, date_to=None, archived=False, overdue=False):
        group = self._lug_list_perm_group(archived, overdue)
        self._lug_perm().check(group, "view")
        return super(ProjectProjectAppPerm, self._lug_scoped(group)).get_lug_project_list_data(
            search=search, offset=offset, limit=limit, priority=priority, type_id=type_id,
            status=status, manager_id=manager_id, date_preset=date_preset, date_field=date_field,
            date_from=date_from, date_to=date_to, archived=archived, overdue=overdue)

    @api.model
    def export_lug_project_list_xlsx(self, **params):
        group = self._lug_list_perm_group(params.get("archived"), params.get("overdue"))
        self._lug_perm().check(group, "export")
        return super(ProjectProjectAppPerm, self._lug_scoped(group)).export_lug_project_list_xlsx(**params)

    @api.model
    def get_lug_project_report(self, type_id=False, status=False):
        self._lug_perm().check("report_all", "view")
        return super(ProjectProjectAppPerm, self._lug_scoped("report_all")).get_lug_project_report(
            type_id=type_id, status=status)

    @api.model
    def export_lug_overview_xlsx(self, period="month", type_id=False):
        self._lug_perm().check("kpi", "export")
        return super(ProjectProjectAppPerm, self._lug_scoped("kpi")).export_lug_overview_xlsx(
            period=period, type_id=type_id)

    def _lug_check_list_write(self):
        self._lug_perm().check(self._lug_list_perm_group(), "write")

    def lug_set_workflow_state(self, state):
        self._lug_check_list_write()
        return super().lug_set_workflow_state(state)

    def lug_toggle_priority(self):
        self._lug_check_list_write()
        return super().lug_toggle_priority()

    def lug_action_open_form(self):
        self._lug_check_list_write()
        return super().lug_action_open_form()

    def lug_action_delete(self):
        self._lug_check_list_write()
        return super().lug_action_delete()

    def lug_action_restore(self):
        self._lug_perm().check("archived", "write")
        return super().lug_action_restore()
