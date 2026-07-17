# -*- coding: utf-8 -*-

from calendar import monthrange
from collections import defaultdict
from datetime import date

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
        efficiency = round(100.0 * done / float(total), 2) if total else 0.0

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
            "departments": dept_opts,
            "tree": tree,
            "selected_employee_id": selected.id,
            "detail": detail,
        }

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
            "departments": [],
            "tree": [],
            "selected_employee_id": False,
            "detail": {},
        }

    @api.model
    def _assignee_for_emp(self, emp, assignee_by_hr):
        return assignee_by_hr.get(emp.id)

    @api.model
    def _emp_stats(self, tasks):
        total = len(tasks)
        done = len(tasks.filtered(lambda t: t.state == "done"))
        overdue = len(tasks.filtered(lambda t: t.is_overdue))
        in_progress = len(tasks.filtered(lambda t: t.state == "in_progress"))
        eff = round(100.0 * done / float(total), 1) if total else 0.0
        return {
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
