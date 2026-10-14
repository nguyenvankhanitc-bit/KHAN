# -*- coding: utf-8 -*-

from calendar import monthrange
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class DailyTaskPerformanceReport(models.AbstractModel):
    _name = "daily.task.performance.report"
    _description = "Báo cáo hiệu suất tháng"

    @api.model
    def get_performance_report(self, year=None, month=None, employee_id=None, department_id=None):
        Access = self.env["daily.task.performance.access"]
        Task = self.env["daily.task"]
        today = fields.Date.context_today(self)

        if not Access.user_can_view():
            raise AccessError(
                "Bạn chưa được phân quyền xem Báo cáo hiệu suất. "
                "Liên hệ quản trị viên để cấp quyền."
            )

        year = int(year or today.year)
        month = int(month or today.month)
        if month < 1 or month > 12:
            raise UserError("Tháng không hợp lệ.")
        last = monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to = date(year, month, last)

        allowed = Access.performance_employee_ids_for_user()
        Emp = self.env["hr.employee"].sudo()
        emp_domain = [("active", "=", True), ("user_id", "!=", False)]
        if allowed is not None:
            if not allowed:
                return self._empty_payload(
                    year,
                    month,
                    date_from,
                    date_to,
                    "Bạn chưa được phân phạm vi nhân viên nào để xem.",
                )
            emp_domain.append(("id", "in", allowed))
        if department_id:
            emp_domain.append(("department_id", "=", int(department_id)))

        employees = Emp.search(emp_domain, order="name")
        if not employees:
            return self._empty_payload(
                year, month, date_from, date_to, "Không có nhân viên trong phạm vi."
            )

        assignees = self.env["daily.task.employee"].sudo().search(
            [("employee_id", "in", employees.ids)]
        )
        assignee_by_hr = {a.employee_id.id: a for a in assignees if a.employee_id}
        tasks = Task.sudo().search(
            [
                ("deadline", ">=", date_from),
                ("deadline", "<=", date_to),
                ("assignee_id", "in", assignees.ids or [0]),
            ]
        )
        Task._refresh_overdue_flags(tasks)

        by_assignee = defaultdict(lambda: self.env["daily.task"])
        for t in tasks:
            by_assignee[t.assignee_id.id] |= t

        # KPI tổng phạm vi
        total = len(tasks)
        done = len(tasks.filtered(lambda t: t.state == "done"))
        in_progress = len(tasks.filtered(lambda t: t.state == "in_progress"))
        overdue = len(tasks.filtered(lambda t: t.is_overdue))
        efficiency = self._eval_avg(tasks, 2)

        # So sánh tháng trước (cùng phạm vi nhân viên)
        prev_to = date_from.replace(day=1) - relativedelta(days=1)
        prev_from = prev_to.replace(day=1)
        prev_tasks = self._scope_tasks(assignees, prev_from, prev_to)
        prev = {
            "total": len(prev_tasks),
            "done": len(prev_tasks.filtered(lambda t: t.state == "done")),
            "overdue": len(prev_tasks.filtered(lambda t: t.is_overdue)),
            "efficiency": self._eval_avg(prev_tasks, 2),
        }

        # Hiệu suất theo phòng ban (cột chồng)
        dept_chart = self._team_chart(tasks, employees, department_id)
        # Xu hướng 7 tháng gần nhất: tổng việc vs hoàn thành
        trend = self._trend(assignees, date_from)
        # Bảng hiệu suất nhân sự
        staff = self._staff_table(employees, by_assignee, assignee_by_hr)

        # Hierarchy từ parent_id
        tree = self._build_hierarchy(employees, by_assignee, assignee_by_hr)

        # Chọn NV đang xem
        selected = False
        if employee_id:
            selected = employees.filtered(lambda e: e.id == int(employee_id))[:1]
        if not selected:
            selected = employees[:1]
        selected = selected[0] if selected else employees[0]

        detail = self._employee_detail(
            selected, by_assignee, assignee_by_hr, date_from, date_to
        )

        depts = Emp.search_read(
            [("id", "in", employees.ids)],
            ["department_id"],
        )
        dept_opts = []
        seen = set()
        for row in depts:
            d = row.get("department_id")
            if d and d[0] not in seen:
                seen.add(d[0])
                dept_opts.append({"id": d[0], "name": d[1]})
        dept_opts.sort(key=lambda x: x["name"] or "")

        return {
            "year": year,
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "month_label": "Tháng %02d/%s" % (month, year),
            "message": False,
            "can_view": True,
            "user_name": self.env.user.name or "",
            "is_manager": Task._is_manager(),
            "kpi": {
                "total": total,
                "done": done,
                "done_pct": round(100.0 * done / float(total), 2) if total else 0.0,
                "overdue": overdue,
                "overdue_pct": round(100.0 * overdue / float(total), 2) if total else 0.0,
                "in_progress": in_progress,
                "in_progress_pct": round(100.0 * in_progress / float(total), 2)
                if total
                else 0.0,
                "efficiency": efficiency,
            },
            "kpi_prev": prev,
            "dept_chart": dept_chart,
            "trend": trend,
            "staff": staff,
            "departments": dept_opts,
            "tree": tree,
            "selected_employee_id": selected.id,
            "detail": detail,
        }

    @api.model
    def export_excel(self, year=None, month=None, department_id=None):
        """Xuất Excel: KPI tháng + Hiệu suất theo team + Hiệu suất nhân sự (đúng phạm vi được xem)."""
        import base64
        import io

        try:
            import xlsxwriter
        except ImportError as exc:
            raise UserError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc

        data = self.get_performance_report(year=year, month=month, department_id=department_id)
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Hieu suat")
        base = {"font_name": "Times New Roman", "font_size": 11, "valign": "vcenter"}
        f = lambda **kw: wb.add_format(dict(base, **kw))
        title = f(bold=True, font_size=16, align="center")
        sub = f(italic=True, align="center")
        h = f(bold=True, align="center", border=1, bg_color="#FCE4D6", text_wrap=True)
        sec = f(bold=True, font_size=12)
        c = f(border=1, align="center")
        l = f(border=1)
        pct = f(border=1, align="center", num_format='0.0"%"')
        kh = f(bold=True, border=1, bg_color="#B4C6E7")

        ws.merge_range(0, 0, 0, 7, "ĐÁNH GIÁ HIỆU SUẤT THÁNG", title)
        ws.merge_range(1, 0, 1, 7, "%s · Người xuất: %s" % (data.get("month_label") or "", self.env.user.name or ""), sub)
        r = 3
        k = data.get("kpi") or {}
        p = data.get("kpi_prev") or {}
        ws.write(r, 0, "CHỈ SỐ", sec)
        r += 1
        for col, txt in enumerate(["Chỉ số", "Tháng này", "Tháng trước"]):
            ws.write(r, col, txt, h)
        r += 1
        for label, cur, prev, is_pct in (
            ("Tổng công việc", k.get("total"), p.get("total"), False),
            ("Hoàn thành", k.get("done"), p.get("done"), False),
            ("Quá hạn", k.get("overdue"), p.get("overdue"), False),
            ("Hiệu suất TB (QL đánh giá)", k.get("efficiency"), p.get("efficiency"), True),
        ):
            ws.write(r, 0, label, kh)
            ws.write(r, 1, cur or 0, pct if is_pct else c)
            ws.write(r, 2, prev or 0, pct if is_pct else c)
            r += 1

        r += 1
        ws.write(r, 0, "HIỆU SUẤT THEO TEAM", sec)
        r += 1
        for col, txt in enumerate(["Team", "Hoàn thành", "Đang thực hiện", "Trễ hạn", "Tổng"]):
            ws.write(r, col, txt, h)
        r += 1
        for t in data.get("dept_chart") or []:
            ws.write(r, 0, t["name"], l)
            ws.write(r, 1, t["done"], c)
            ws.write(r, 2, t["other"], c)
            ws.write(r, 3, t["overdue"], c)
            ws.write(r, 4, t["done"] + t["other"] + t["overdue"], c)
            r += 1

        r += 1
        ws.write(r, 0, "HIỆU SUẤT NHÂN SỰ", sec)
        r += 1
        heads = ["STT", "Nhân sự", "Chức danh · Phòng ban", "Tổng CV", "Hoàn thành", "Đang làm", "Chưa làm", "Trễ hạn", "Hiệu suất"]
        for col, txt in enumerate(heads):
            ws.write(r, col, txt, h)
        r += 1
        for i, s in enumerate(data.get("staff") or [], start=1):
            ws.write(r, 0, i, c)
            ws.write(r, 1, s["name"], l)
            ws.write(r, 2, " · ".join(x for x in (s.get("job"), s.get("department")) if x), l)
            for col, key in ((3, "total"), (4, "done"), (5, "doing"), (6, "todo"), (7, "late")):
                ws.write(r, col, s.get(key) or 0, c)
            ws.write(r, 8, s.get("efficiency") or 0, pct)
            r += 1

        ws.set_column(0, 0, 28)
        ws.set_column(1, 1, 26)
        ws.set_column(2, 2, 36)
        ws.set_column(3, 8, 13)
        ws.freeze_panes(0, 0)
        wb.close()
        filename = "Danh_gia_hieu_suat_%02d_%s.xlsx" % (int(data.get("month") or 0), data.get("year") or "")
        return {"file_base64": base64.b64encode(buf.getvalue()).decode("ascii"), "filename": filename}

    @api.model
    def _empty_payload(self, year, month, date_from, date_to, message):
        return {
            "year": year,
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "month_label": "Tháng %02d/%s" % (month, year),
            "message": message,
            "can_view": True,
            "user_name": self.env.user.name or "",
            "is_manager": self.env["daily.task"]._is_manager(),
            "kpi": {
                "total": 0,
                "done": 0,
                "done_pct": 0.0,
                "overdue": 0,
                "overdue_pct": 0.0,
                "in_progress": 0,
                "in_progress_pct": 0.0,
                "efficiency": 0.0,
            },
            "kpi_prev": {},
            "dept_chart": [],
            "trend": [],
            "staff": [],
            "departments": [],
            "tree": [],
            "selected_employee_id": False,
            "detail": {},
        }

    @api.model
    def _eval_avg(self, tasks, digits=1):
        """Hiệu suất = TB % Hoàn thành do Quản lý đánh giá (Kiểm tra CV); việc chưa đánh giá = 0%."""
        if not tasks:
            return 0.0
        return round(sum(int(t.manager_eval_percent or 0) for t in tasks) / float(len(tasks)), digits)

    @api.model
    def _scope_tasks(self, assignees, date_from, date_to):
        tasks = self.env["daily.task"].sudo().search([
            ("deadline", ">=", date_from),
            ("deadline", "<=", date_to),
            ("assignee_id", "in", assignees.ids or [0]),
        ])
        return tasks

    @api.model
    def _dept_chart(self, tasks, employees, assignee_by_hr):
        dept_of = {}
        for emp in employees:
            a = assignee_by_hr.get(emp.id)
            if a:
                dept_of[a.id] = emp.department_id.display_name if emp.department_id else "Chưa có phòng ban"
        rows = {}
        for t in tasks:
            name = dept_of.get(t.assignee_id.id) or "Chưa có phòng ban"
            r = rows.setdefault(name, {"name": name, "done": 0, "overdue": 0, "other": 0})
            if t.state == "done":
                r["done"] += 1
            elif t.is_overdue:
                r["overdue"] += 1
            else:
                r["other"] += 1
        return sorted(rows.values(), key=lambda r: -(r["done"] + r["overdue"] + r["other"]))

    @api.model
    def _team_chart(self, tasks, employees, department_id=None):
        """Hiệu suất theo TEAM: mỗi team của phòng ban trong phạm vi là 1 cột (kể cả chưa có việc).

        Việc thuộc team theo hạng mục (Team của hạng mục); không có → team mà người phụ trách
        là thành viên (User Group) / quản lý.
        """
        Team = self.env["daily.task.team"].sudo()
        dept_ids = set(employees.mapped("department_id").ids)
        if department_id:
            dept_ids = {int(department_id)}
        teams = Team.search([("active", "=", True), ("department_id", "in", list(dept_ids) or [0])])
        team_of_user = {}
        for t in teams:
            for u in t.manager_ids | t.member_ids:
                team_of_user.setdefault(u.id, t.id)
        rows = {t.id: {"id": t.id, "name": t.name, "done": 0, "overdue": 0, "other": 0} for t in teams}
        for task in tasks:
            tid = task.work_group_id.team_id.id
            if tid not in rows:
                tid = team_of_user.get(task.assignee_user_id.id)
            if tid not in rows:
                tid = 0
                rows.setdefault(0, {"id": 0, "name": "Chưa có team", "done": 0, "overdue": 0, "other": 0})
            r = rows[tid]
            if task.state == "done":
                r["done"] += 1
            elif task.is_overdue:
                r["overdue"] += 1
            else:
                r["other"] += 1
        out = [rows[t.id] for t in teams.sorted(lambda t: (t.sequence, (t.name or "").casefold()))]
        if 0 in rows:
            out.append(rows[0])
        return out

    @api.model
    def _trend(self, assignees, date_from, months=7):
        out = []
        start = date_from.replace(day=1) - relativedelta(months=months - 1)
        for i in range(months):
            m_from = start + relativedelta(months=i)
            m_to = m_from + relativedelta(months=1, days=-1)
            ts = self._scope_tasks(assignees, m_from, m_to)
            out.append({
                "label": m_from.strftime("%m/%Y"),
                "total": len(ts),
                "done": len(ts.filtered(lambda t: t.state == "done")),
            })
        return out

    @api.model
    def _staff_table(self, employees, by_assignee, assignee_by_hr):
        rows = []
        for emp in employees:
            a = assignee_by_hr.get(emp.id)
            st = self._emp_stats(by_assignee[a.id] if a else self.env["daily.task"])
            rows.append({
                "id": emp.id,
                "name": emp.name or "",
                "job": emp.job_id.name if emp.job_id else (emp.job_title or ""),
                "department": emp.department_id.display_name if emp.department_id else "",
                **st,
            })
        rows.sort(key=lambda r: (r["total"] == 0, -r["efficiency"], -r["total"], r["name"].casefold()))
        return rows

    @api.model
    def _assignee_for_emp(self, emp, assignee_by_hr):
        return assignee_by_hr.get(emp.id)

    @api.model
    def _emp_stats(self, tasks):
        total = len(tasks)
        done = len(tasks.filtered(lambda t: t.state == "done"))
        overdue = len(tasks.filtered(lambda t: t.is_overdue))
        in_progress = len(tasks.filtered(lambda t: t.state == "in_progress"))
        eff = self._eval_avg(tasks, 1)
        # Chia trạng thái không trùng nhau: Hoàn thành + Đang làm + Chưa làm + Trễ hạn = Tổng
        open_tasks = tasks.filtered(lambda t: t.state != "done")
        late = open_tasks.filtered(lambda t: t.is_overdue)
        on_time = open_tasks - late
        return {
            "late": len(late),
            "doing": len(on_time.filtered(lambda t: t.state == "in_progress")),
            "todo": len(on_time.filtered(lambda t: t.state != "in_progress")),
            "total": total,
            "done": done,
            "overdue": overdue,
            "in_progress": in_progress,
            "efficiency": eff,
        }

    @api.model
    def _build_hierarchy(self, employees, by_assignee, assignee_by_hr):
        emp_ids = set(employees.ids)
        nodes = {}
        for emp in employees:
            assignee = self._assignee_for_emp(emp, assignee_by_hr)
            stats = self._emp_stats(
                by_assignee[assignee.id] if assignee else self.env["daily.task"]
            )
            job = ""
            if emp.job_id:
                job = emp.job_id.name or ""
            elif emp.job_title:
                job = emp.job_title
            dept = emp.department_id.display_name if emp.department_id else ""
            nodes[emp.id] = {
                "id": emp.id,
                "name": emp.name or "",
                "job": job,
                "department": dept,
                "parent_id": emp.parent_id.id
                if emp.parent_id and emp.parent_id.id in emp_ids
                else False,
                "children": [],
                "stats": stats,
            }

        roots = []
        for nid, node in nodes.items():
            pid = node["parent_id"]
            if pid and pid in nodes:
                nodes[pid]["children"].append(node)
            else:
                roots.append(node)

        def sort_rec(items):
            items.sort(key=lambda n: (n["name"] or "").lower())
            for n in items:
                sort_rec(n["children"])

        sort_rec(roots)
        return roots

    @api.model
    def _employee_detail(self, emp, by_assignee, assignee_by_hr, date_from, date_to):
        assignee = self._assignee_for_emp(emp, assignee_by_hr)
        tasks = by_assignee[assignee.id] if assignee else self.env["daily.task"]
        stats = self._emp_stats(tasks)
        total = stats["total"]
        done = stats["done"]
        overdue = stats["overdue"]
        efficiency = stats["efficiency"]

        rating = "Trung bình"
        if efficiency >= 85:
            rating = "Tốt"
        elif efficiency >= 70:
            rating = "Khá"
        elif efficiency < 50:
            rating = "Cần cải thiện"
        stars = min(5.0, round((efficiency / 20.0) * 2) / 2.0) if efficiency else 0.0

        # criteria derived from task metrics
        overdue_pct = (100.0 * overdue / float(total)) if total else 0.0
        progress_score = max(0.0, round(100.0 - overdue_pct, 1))
        high = tasks.filtered(lambda t: t.priority == "high")
        high_done = len(high.filtered(lambda t: t.state == "done"))
        skill = (
            round(100.0 * high_done / float(len(high)), 1) if high else efficiency
        )
        criteria = [
            {"key": "quality", "label": "Chất lượng công việc", "score": efficiency},
            {"key": "progress", "label": "Tiến độ / hạn", "score": progress_score},
            {"key": "skill", "label": "Kỹ năng chuyên môn", "score": skill},
            {
                "key": "attitude",
                "label": "Thái độ",
                "score": round((efficiency + progress_score) / 2.0, 1),
            },
            {
                "key": "coop",
                "label": "Hợp tác",
                "score": round((efficiency + skill) / 2.0, 1),
            },
        ]

        state_map = dict(tasks._fields["state"].selection)
        pri_map = dict(tasks._fields["priority"].selection)
        rows = []
        for t in tasks.sorted(key=lambda r: (r.deadline or date_to, r.id)):
            prog = int(t.completion_percent or 0)
            if t.state == "done":
                prog = max(prog, 100)
            t_stars = min(5.0, round((prog / 20.0) * 2) / 2.0) if prog else 0.0
            rows.append(
                {
                    "id": t.id,
                    "name": t.name or "",
                    "priority": t.priority or "medium",
                    "priority_label": pri_map.get(t.priority, ""),
                    "deadline": t.deadline.strftime("%d/%m/%Y") if t.deadline else "",
                    "state": t.state or "",
                    "state_label": state_map.get(t.state, ""),
                    "is_overdue": bool(t.is_overdue),
                    "progress": prog,
                    "stars": t_stars,
                }
            )

        job = emp.job_id.name if emp.job_id else (emp.job_title or "")
        return {
            "id": emp.id,
            "name": emp.name or "",
            "job": job,
            "department": emp.department_id.display_name if emp.department_id else "",
            "efficiency": efficiency,
            "stars": stars,
            "rating": rating,
            "stats": stats,
            "state_chart": {
                "done": done,
                "overdue": overdue,
                "other": max(0, total - done - overdue),
                "done_pct": round(100.0 * done / float(total), 1) if total else 0.0,
                "overdue_pct": round(100.0 * overdue / float(total), 1) if total else 0.0,
            },
            "tasks": rows,
            "criteria": criteria,
        }
