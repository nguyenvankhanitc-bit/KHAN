# -*- coding: utf-8 -*-
"""Báo cáo NV Kho (BÁO CÁO → Các loại báo cáo).

Dữ liệu từ Quản lý công việc / Danh sách công việc của nhân viên trong Team, theo tháng:
STT · Hạng mục · Tên chi tiết hạng mục · Tên công việc · Ngày bắt đầu · Deadline · Thời gian (phút)
· Xếp loại · Ghi chú.

Xếp loại = Kiểm tra CV → Quản lý đánh giá (Đạt / Trung bình / Không đạt); chưa chọn tay mà đã có
% QL đánh giá thì quy đổi theo Cài đặt → Xếp loại đạt.
"""

import base64
import io

from odoo import api, models
from odoo.exceptions import ValidationError

from .daily_task_category_report import _roman

_RATING_LABELS = {"pass": "Đạt", "average": "Trung bình", "fail": "Không đạt"}


class DailyTask(models.Model):
    _inherit = "daily.task"

    # ------------------------------------------------------------------ phạm vi
    @api.model
    def _kho_teams(self):
        """Team được xem: Quản lý module → mọi team; người khác → team mình quản lý / là thành viên."""
        Team = self.env["daily.task.team"].sudo()
        if self.env.su or self._is_manager():
            return Team.search([("active", "=", True)], order="sequence, name")
        uid = self.env.uid
        return Team.search(
            [("active", "=", True), "|", ("manager_ids", "in", uid), ("member_ids", "in", uid)],
            order="sequence, name",
        )

    @api.model
    def _kho_default_team(self, teams):
        kho = teams.filtered(lambda t: "KHO" in (t.name or "").upper())
        return (kho or teams)[:1]

    # ------------------------------------------------------------------ dữ liệu
    @api.model
    def get_kho_report(self, year=None, month=None, team_id=None, employee_id=None):
        Perm = self.env["daily.task.report.perm"]
        Perm.check("kho", "view")
        pmap = Perm.get_map()["kho"]
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        teams = self._kho_teams()
        team = teams.filtered(lambda t: t.id == int(team_id or 0))[:1] or self._kho_default_team(teams)
        base = {
            "year": year,
            "month": month,
            "teams": [{"id": t.id, "name": t.name or ""} for t in teams],
            "team_id": team.id if team else False,
            "team_name": team.name if team else "",
            "team_dept": (team.department_id.name or "") if team else "",
            "employees": [],
            "employee_id": False,
            "can_pick_employee": False,
            "rows": [],
            "report_perm": {k: (v if v is not None else True) for k, v in pmap.items()},
            "eval_tiers": [
                {"from_percent": t["from_percent"], "rating_key": t["rating_key"], "name": t["name"]}
                for t in self.env["daily.task.rating.tier"].get_tiers(kind="eval")["tiers"] if t["apply"]
            ],
        }
        if not team:
            base["message"] = "Bạn chưa thuộc Team nào. Vào Cài đặt → Bộ phận để gán Team."
            return base

        users = (team.manager_ids | team.member_ids).filtered("active")
        Emp = self.env["hr.employee"].sudo()
        me = Emp.search([("user_id", "=", self.env.uid)], limit=1)
        # Xem cả team: Quản lý module · User quản lý team · tick «Xem NV khác»; bỏ tick → chỉ mình
        see_all = (
            self.env.su or self._is_manager() or self.env.uid in team.manager_ids.ids or pmap["others"] is True
        )
        if pmap["others"] is False:
            see_all = False
        emps = Emp.search([("user_id", "in", users.ids)], order="name")
        if not see_all:
            emps = emps.filtered(lambda e: e.id == me.id)
        base["employees"] = [{"id": e.id, "name": e.name or ""} for e in emps]
        base["can_pick_employee"] = len(emps) > 1
        emp = emps.filtered(lambda e: e.id == int(employee_id or 0))[:1]
        if not see_all:
            emp = emps[:1]
        base["employee_id"] = emp.id if emp else False
        target_users = emp.user_id if emp else emps.mapped("user_id")
        if not target_users:
            return base

        tasks = self.sudo().search(
            [
                ("assignee_user_id", "in", target_users.ids),
                "|",
                "&", ("deadline", ">=", date_from), ("deadline", "<=", date_to),
                "&", ("assign_date", ">=", date_from), ("assign_date", "<=", date_to),
            ],
            order="assign_date asc, deadline asc, id asc",
        )
        base["rows"] = self._kho_rows(tasks, show_employee=not emp)
        base["show_employee"] = not emp
        return base

    def _kho_rating(self):
        self.ensure_one()
        if self.manager_rating:
            return _RATING_LABELS.get(self.manager_rating, "")
        if self.manager_confirmed or self.manager_eval_percent:
            key = self.env["daily.task.rating.tier"].rate_eval(self.manager_eval_percent or 0)
            return _RATING_LABELS.get(key, "")
        return ""

    @api.model
    def _kho_rows(self, tasks, show_employee=False):
        WG = self.env["daily.task.work.group"]
        groups = {}
        for t in tasks:
            wg = t.work_group_id
            head = wg.category_head_id or wg
            name = WG._norm_category_name(head.name or wg.name or "") if wg else ""
            key = (name or "").upper() or "~"
            g = groups.setdefault(key, {
                "label": (name or "Không có hạng mục").upper(),
                "order": (head.sequence if wg else 10 ** 6, key),
                "tasks": [],
            })
            g["tasks"].append(t)
        rows = []
        for g_idx, g in enumerate(sorted(groups.values(), key=lambda x: x["order"]), start=1):
            cat = "%s. %s" % (_roman(g_idx), g["label"])
            for d_idx, t in enumerate(g["tasks"], start=1):
                wg = t.work_group_id
                rows.append({
                    "id": t.id,
                    "stt": "%s.%s" % (g_idx, d_idx),
                    "category": cat,
                    "detail": ((wg.task_name or WG._norm_category_name(wg.name or "")) if wg else "").upper(),
                    "name": t.name or "",
                    "start": t.assign_date.strftime("%d/%m/%Y") if t.assign_date else "",
                    "deadline": t.deadline.strftime("%d/%m/%Y") if t.deadline else "",
                    "minutes": int(t.duration_minutes or 0),
                    "rating": t._kho_rating(),
                    "rating_key": t.manager_rating or "",
                    # % QL đánh giá (Kiểm tra CV) — chỉ tính việc đã đánh giá
                    "evaluated": bool(t.manager_rating or t.manager_confirmed or t.manager_eval_percent),
                    "eval_percent": int(t.manager_eval_percent or (100 if t.manager_confirmed else 0)),
                    "note": t.note or "",
                    "employee": (t.assignee_id.name or "") if show_employee else "",
                })
        return rows

    # ------------------------------------------------------------------ Excel
    @api.model
    def export_kho_report_excel(self, year=None, month=None, team_id=None, employee_id=None):
        self.env["daily.task.report.perm"].check("kho", "export")
        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc
        data = self.get_kho_report(year=year, month=month, team_id=team_id, employee_id=employee_id)
        if data.get("message"):
            raise ValidationError(data["message"])
        show_emp = bool(data.get("show_employee"))
        cols = [("STT", 6), ("Hạng mục", 24), ("Tên chi tiết hạng mục", 26), ("Tên công việc", 42)]
        if show_emp:
            cols.append(("Nhân viên", 22))
        cols += [("Ngày bắt đầu", 14), ("Deadline", 14), ("Thời gian (phút)", 15), ("Xếp loại", 13), ("Ghi chú", 40)]
        last = len(cols) - 1

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Báo cáo NV Kho")
        title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": "#5B3A8C",
                               "align": "center", "valign": "vcenter"})
        sub = wb.add_format({"italic": True, "font_color": "#555555"})
        head = wb.add_format({"bold": True, "bg_color": "#D9EAD3", "border": 1, "border_color": "#A9B8C8",
                              "align": "center", "valign": "vcenter", "text_wrap": True})
        cell = {}
        for band, bg in (("odd", "#FFFFFF"), ("even", "#F3F6FA")):
            base = {"border": 1, "border_color": "#C9D3DF", "valign": "vcenter", "bg_color": bg, "text_wrap": True}
            cell[band] = {
                "left": wb.add_format(base),
                "center": wb.add_format(dict(base, align="center")),
            }
        ws.merge_range(0, 0, 0, last, "BÁO CÁO CÔNG VIỆC", title)
        ws.set_row(0, 30)
        ws.write(1, 0, "Tháng: %s     Năm: %s     Team: %s" % (data["month"], data["year"], data.get("team_name") or ""), sub)
        hr = 3
        for c, (label, width) in enumerate(cols):
            ws.write(hr, c, label, head)
            ws.set_column(c, c, width)
        ws.set_row(hr, 22)
        r = hr + 1
        for i, row in enumerate(data.get("rows") or []):
            f = cell["even" if i % 2 else "odd"]
            vals = [(row["stt"], "center"), (row["category"], "left"), (row["detail"], "left"), (row["name"], "left")]
            if show_emp:
                vals.append((row["employee"], "left"))
            vals += [(row["start"], "center"), (row["deadline"], "center"), (row["minutes"], "center"),
                     (row["rating"], "center"), (row["note"], "left")]
            for c, (v, align) in enumerate(vals):
                ws.write(r, c, v, f[align])
            ws.set_row(r, 24)
            r += 1
        ws.autofilter(hr, 0, max(r - 1, hr), last)
        ws.freeze_panes(hr + 1, 0)
        wb.close()
        name = "bao_cao_nv_kho_%s_%02d.xlsx" % (data["year"], int(data["month"]))
        return {"file_base64": base64.b64encode(buf.getvalue()).decode(), "filename": name}
