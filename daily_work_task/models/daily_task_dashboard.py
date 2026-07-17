# -*- coding: utf-8 -*-

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class DailyTaskDashboard(models.AbstractModel):
    _name = "daily.task.dashboard"
    _description = "Dashboard Quản lý công việc hàng ngày"

    @api.model
    def get_filter_options(self):
        Task = self.env["daily.task"]
        today = fields.Date.context_today(self)
        year, month = today.year, today.month
        last = monthrange(year, month)[1]
        date_from = "%04d-%02d-01" % (year, month)
        date_to = "%04d-%02d-%02d" % (year, month, last)

        if Task._is_manager():
            employees = self.env["daily.task.employee"].search_read(
                [("active", "=", True)],
                ["id", "name", "employee_id"],
                order="name",
            )
        else:
            allowed_hr = set(Task._viewable_employee_ids() or [])
            my = Task._my_hr_employee()
            if my:
                allowed_hr.add(my.id)
            bridges = (
                self.env["daily.task.employee"]
                .sudo()
                .search(
                    [
                        ("active", "=", True),
                        ("employee_id", "in", list(allowed_hr) or [0]),
                    ]
                )
            )
            employees = [
                {
                    "id": b.id,
                    "name": b.name,
                    "employee_id": b.employee_id.id if b.employee_id else False,
                }
                for b in bridges
            ]

        def _m2o_id(val):
            if isinstance(val, (list, tuple)):
                return val[0] if val else False
            return val or False

        # Departments from HR (manager) or from visible employees
        dept_ids = set()
        for e in employees:
            hr_id = _m2o_id(e.get("employee_id"))
            if not hr_id:
                continue
            emp = self.env["hr.employee"].sudo().browse(hr_id)
            if emp.exists() and emp.department_id:
                dept_ids.add(emp.department_id.id)
        if Task._is_manager():
            self.env.cr.execute(
                """
                SELECT DISTINCT d.id,
                       COALESCE(d.name->>'en_US', d.name::text)
                  FROM hr_department d
              ORDER BY 2
                 LIMIT 200
                """
            )
            departments = [
                {"id": r[0], "name": r[1] or "—"} for r in self.env.cr.fetchall()
            ]
        else:
            departments = []
            for did in sorted(dept_ids):
                d = self.env["hr.department"].sudo().browse(did)
                name = d.display_name or "—"
                departments.append({"id": did, "name": name})
            departments.sort(key=lambda x: x["name"])

        return {
            "employees": [{"id": e["id"], "name": e["name"]} for e in employees],
            "departments": departments,
            "default_date_from": date_from,
            "default_date_to": date_to,
            "is_manager": Task._is_manager(),
            "can_see_performance": self.env[
                "daily.task.performance.access"
            ].user_can_view(),
            "user_name": self.env.user.name or "",
            "company_name": self.env.company.name or "",
        }

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        Task = self.env["daily.task"]
        today = fields.Date.context_today(self)

        domain = self._build_domain(filters)
        tasks = Task.search(domain, order="deadline asc, id desc")
        Task._refresh_overdue_flags(tasks)

        total = len(tasks)
        done = len(tasks.filtered(lambda t: t.state == "done"))
        in_progress = len(tasks.filtered(lambda t: t.state == "in_progress"))
        not_started = len(tasks.filtered(lambda t: t.state == "not_started"))
        overdue = tasks.filtered(lambda t: t.is_overdue)
        overdue_count = len(overdue)

        def pct(n):
            return round(100.0 * n / float(total), 1) if total else 0.0

        hours = round(sum(float(t.duration_hours or 0.0) for t in tasks), 1)
        efficiency = pct(done)

        upcoming_end = today + timedelta(days=7)
        upcoming = tasks.filtered(
            lambda t: t.state != "done"
            and not t.is_overdue
            and t.deadline
            and today <= t.deadline <= upcoming_end
        )
        upcoming_count = len(upcoming)
        assigned_count = len(tasks.filtered(lambda t: bool(t.assignee_id)))

        # Employees with active tasks / total visible employees
        emp_ids = set(
            tasks.mapped("assignee_id.employee_id").ids
            if tasks
            else []
        )
        all_emp = len(self.env["daily.task.employee"].search([("active", "=", True)]))
        if not Task._is_manager():
            allowed = set(Task._viewable_employee_ids() or [])
            my = Task._my_hr_employee()
            if my:
                allowed.add(my.id)
            all_emp = len(allowed) or 1
        emp_active = len([i for i in emp_ids if i]) or 0

        # Growth vs previous period (same length before date_from)
        growth = self._period_growth(filters, total)

        kpi = {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "not_started": not_started,
            "overdue": overdue_count,
            "done_pct": pct(done),
            "in_progress_pct": pct(in_progress),
            "not_started_pct": pct(not_started),
            "overdue_pct": pct(overdue_count),
            "duration_hours": hours,
            "efficiency": efficiency,
            "upcoming": upcoming_count,
            "assigned": assigned_count,
            "emp_active": emp_active,
            "emp_total": all_emp,
            "growth_pct": growth,
        }

        priority_counter = Counter(tasks.mapped("priority"))
        priority_chart = {
            "labels": ["Cao", "Trung bình", "Thấp"],
            "values": [
                priority_counter.get("high", 0),
                priority_counter.get("medium", 0),
                priority_counter.get("low", 0),
            ],
            "colors": ["#ef4444", "#f59e0b", "#22c55e"],
        }

        state_chart = {
            "labels": ["Hoàn thành", "Đang xử lý", "Chưa bắt đầu"],
            "values": [done, in_progress, not_started],
            "percents": [pct(done), pct(in_progress), pct(not_started)],
            "colors": ["#22c55e", "#f59e0b", "#94a3b8"],
            "center_total": total,
        }

        # Weekly completion trend within filter window
        weekly = self._weekly_trend(tasks, filters, today)

        # Department donut
        dept_chart, dept_perf = self._department_stats(tasks)

        # Bảng xếp hạng KPI — NV trong phòng ban của mình, 3 tháng gần nhất
        kpi_rank = []
        kpi_rank_dept = ""
        if not Task._is_manager():
            from_3m = today - relativedelta(months=3)
            my = Task._my_hr_employee()
            domain_rank = [
                ("deadline", ">=", from_3m),
                ("deadline", "<=", today),
            ]
            if my and my.department_id:
                dept = my.department_id
                kpi_rank_dept = dept.display_name or dept.name or ""
                domain_rank += [
                    "|",
                    ("department_id", "=", dept.id),
                    ("assignee_id.employee_id.department_id", "=", dept.id),
                ]
            elif my:
                domain_rank.append(("assignee_id.employee_id", "=", my.id))
            else:
                domain_rank.append(("id", "=", 0))
            rank_tasks = Task.sudo().search(domain_rank)
            Task.sudo()._refresh_overdue_flags(rank_tasks)
            kpi_rank = self._employee_kpi_rank(rank_tasks, limit=20)

        # Top 5 employees by efficiency
        top_employees = self._top_employees(tasks, limit=5)

        # Alerts
        alerts = []
        if overdue_count:
            alerts.append(
                {
                    "type": "danger",
                    "icon": "fa-exclamation-circle",
                    "title": "%s công việc quá hạn" % overdue_count,
                    "subtitle": "Cần xử lý ngay",
                }
            )
        if upcoming_count:
            alerts.append(
                {
                    "type": "warning",
                    "icon": "fa-clock-o",
                    "title": "%s công việc sắp đến hạn" % upcoming_count,
                    "subtitle": "Trong 7 ngày tới",
                }
            )
        missing_cv = max(0, all_emp - emp_active)
        if missing_cv:
            alerts.append(
                {
                    "type": "amber",
                    "icon": "fa-user",
                    "title": "%s NV chưa có CV trong kỳ" % missing_cv,
                    "subtitle": "Nhắc nhập công việc",
                }
            )

        def serialize(recs, limit=50):
            rows = []
            for t in recs[:limit]:
                overdue_days = 0
                if t.deadline and t.is_overdue:
                    overdue_days = max(0, (today - t.deadline).days)
                dept = ""
                if t.department_id:
                    dept = t.department_id.display_name or ""
                elif t.assignee_id.employee_id and t.assignee_id.employee_id.department_id:
                    dept = t.assignee_id.employee_id.department_id.display_name or ""
                rows.append(
                    {
                        "id": t.id,
                        "name": t.name or "",
                        "deadline": t.deadline.strftime("%d/%m/%Y") if t.deadline else "",
                        "assignee": t.assignee_id.name or "",
                        "department": dept,
                        "priority": t.priority or "",
                        "priority_label": dict(t._fields["priority"].selection).get(
                            t.priority, ""
                        ),
                        "state": t.state or "",
                        "state_label": dict(t._fields["state"].selection).get(
                            t.state, ""
                        ),
                        "is_overdue": bool(t.is_overdue),
                        "overdue_days": overdue_days,
                        "progress": int(t.completion_percent or 0)
                        if t.state != "done"
                        else max(int(t.completion_percent or 0), 100),
                        "duration_hours": float(t.duration_hours or 0.0),
                    }
                )
            return rows

        # Today schedule
        today_tasks = tasks.filtered(
            lambda t: t.deadline == today and t.state != "done"
        )
        today_schedule = []
        for i, t in enumerate(today_tasks[:12]):
            hour = 8 + (i % 8)
            today_schedule.append(
                {
                    "id": t.id,
                    "time": "%02d:00" % hour,
                    "name": t.name or "",
                    "assignee": t.assignee_id.name or "",
                    "state": t.state,
                    "priority": t.priority,
                }
            )

        return {
            "kpi": kpi,
            "priority_chart": priority_chart,
            "state_chart": state_chart,
            "weekly_chart": weekly,
            "department_chart": dept_chart,
            "dept_performance": dept_perf,
            "kpi_rank": kpi_rank,
            "kpi_rank_dept": kpi_rank_dept,
            "top_employees": top_employees,
            "alerts": alerts,
            "overdue_list": serialize(overdue, 20),
            "done_list": serialize(
                tasks.filtered(lambda t: t.state == "done"),
                20,
            ),
            "in_progress_list": serialize(
                tasks.filtered(
                    lambda t: t.state == "in_progress" and not t.is_overdue
                ),
                20,
            ),
            "not_started_list": serialize(
                tasks.filtered(
                    lambda t: t.state == "not_started" and not t.is_overdue
                ),
                20,
            ),
            "recent_tasks": serialize(tasks[:15], 15),
            "upcoming_list": serialize(upcoming, 10),
            "today_schedule": today_schedule,
            "today_label": today.strftime("%d/%m/%Y"),
            "overdue_count": overdue_count,
            "is_manager": Task._is_manager(),
        }

    @api.model
    def _period_growth(self, filters, current_total):
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if not date_from or not date_to:
            return 0.0
        try:
            d_from = fields.Date.to_date(date_from)
            d_to = fields.Date.to_date(date_to)
        except Exception:
            return 0.0
        span = (d_to - d_from).days + 1
        if span <= 0:
            return 0.0
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)
        prev_filters = dict(filters)
        prev_filters["date_from"] = prev_from.isoformat()
        prev_filters["date_to"] = prev_to.isoformat()
        prev_domain = self._build_domain(prev_filters)
        prev_total = self.env["daily.task"].search_count(prev_domain)
        if not prev_total:
            return 100.0 if current_total else 0.0
        return round(100.0 * (current_total - prev_total) / float(prev_total), 1)

    @api.model
    def _weekly_trend(self, tasks, filters, today):
        date_from = filters.get("date_from")
        try:
            base = fields.Date.to_date(date_from) if date_from else today.replace(day=1)
        except Exception:
            base = today.replace(day=1)
        buckets = defaultdict(list)
        for t in tasks:
            d = t.deadline or t.assign_date
            if not d:
                continue
            week_idx = min(5, max(1, ((d.day - 1) // 7) + 1))
            buckets[week_idx].append(
                100
                if t.state == "done"
                else int(t.completion_percent or 0)
            )
        labels = ["Tuần %s" % w for w in range(1, 6)]
        values = []
        for w in range(1, 6):
            vals = buckets.get(w) or []
            values.append(round(sum(vals) / float(len(vals)), 1) if vals else 0.0)
        return {"labels": labels, "values": values}

    @api.model
    def _department_stats(self, tasks):
        by_dept = defaultdict(
            lambda: {"total": 0, "done": 0, "overdue": 0, "name": "Khác"}
        )
        for t in tasks:
            dept = t.department_id
            if not dept and t.assignee_id.employee_id:
                dept = t.assignee_id.employee_id.department_id
            key = dept.id if dept else 0
            by_dept[key]["name"] = dept.display_name if dept else "Khác"
            by_dept[key]["total"] += 1
            if t.state == "done":
                by_dept[key]["done"] += 1
            if t.is_overdue:
                by_dept[key]["overdue"] += 1

        colors = ["#3b82f6", "#22c55e", "#f59e0b", "#06b6d4", "#94a3b8", "#a855f7", "#ef4444"]
        items = sorted(by_dept.items(), key=lambda x: -x[1]["total"])
        total_all = sum(v["total"] for _, v in items) or 1
        labels, values, legend = [], [], []
        perf = []
        for idx, (key, data) in enumerate(items[:8]):
            color = colors[idx % len(colors)]
            labels.append(data["name"])
            values.append(data["total"])
            share = round(100.0 * data["total"] / float(total_all), 1)
            legend.append(
                {
                    "name": data["name"],
                    "count": data["total"],
                    "pct": share,
                    "color": color,
                }
            )
            eff = (
                round(100.0 * data["done"] / float(data["total"]), 1)
                if data["total"]
                else 0.0
            )
            perf.append(
                {
                    "id": key,
                    "name": data["name"],
                    "total": data["total"],
                    "done": data["done"],
                    "overdue": data["overdue"],
                    "efficiency": eff,
                }
            )
        # Xếp hạng KPI theo hiệu suất (cao → thấp)
        perf.sort(
            key=lambda r: (-r["efficiency"], -r["done"], -r["total"], r["name"] or "")
        )
        return (
            {
                "labels": labels,
                "values": values,
                "colors": [colors[i % len(colors)] for i in range(len(labels))],
                "legend": legend,
            },
            perf,
        )

    @api.model
    def _employee_kpi_rank(self, tasks, limit=20):
        """Xếp hạng KPI theo nhân viên (hiệu suất) trong tập task đã lọc."""
        by_emp = defaultdict(
            lambda: {"total": 0, "done": 0, "overdue": 0, "name": ""}
        )
        for t in tasks:
            emp = t.assignee_id
            if not emp:
                continue
            by_emp[emp.id]["name"] = emp.name or ""
            by_emp[emp.id]["total"] += 1
            if t.state == "done":
                by_emp[emp.id]["done"] += 1
            if t.is_overdue:
                by_emp[emp.id]["overdue"] += 1
        rows = []
        for eid, data in by_emp.items():
            if not data["total"]:
                continue
            eff = round(100.0 * data["done"] / float(data["total"]), 1)
            rows.append(
                {
                    "id": eid,
                    "name": data["name"],
                    "done": data["done"],
                    "total": data["total"],
                    "overdue": data["overdue"],
                    "efficiency": eff,
                }
            )
        rows.sort(
            key=lambda r: (-r["efficiency"], -r["done"], -r["total"], r["name"] or "")
        )
        return rows[:limit]

    @api.model
    def _top_employees(self, tasks, limit=5):
        by_emp = defaultdict(lambda: {"total": 0, "done": 0, "name": ""})
        for t in tasks:
            emp = t.assignee_id
            if not emp:
                continue
            by_emp[emp.id]["name"] = emp.name or ""
            by_emp[emp.id]["total"] += 1
            if t.state == "done":
                by_emp[emp.id]["done"] += 1
        rows = []
        for eid, data in by_emp.items():
            if not data["total"]:
                continue
            eff = round(100.0 * data["done"] / float(data["total"]), 1)
            rows.append(
                {
                    "id": eid,
                    "name": data["name"],
                    "done": data["done"],
                    "total": data["total"],
                    "efficiency": eff,
                }
            )
        rows.sort(key=lambda r: (-r["efficiency"], -r["done"], r["name"]))
        return rows[:limit]

    @api.model
    def _build_domain(self, filters):
        domain = []
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        assignee_id = filters.get("assignee_id")
        department_id = filters.get("department_id")
        state = (filters.get("state") or "").strip()
        if date_from:
            domain.append(("deadline", ">=", date_from))
        if date_to:
            domain.append(("deadline", "<=", date_to))
        Task = self.env["daily.task"]
        if assignee_id:
            domain.append(("assignee_id", "=", int(assignee_id)))
        elif not Task._is_manager():
            allowed_hr = list(Task._viewable_employee_ids() or [])
            my = Task._my_hr_employee()
            if my:
                allowed_hr.append(my.id)
            domain.append(("assignee_id.employee_id", "in", allowed_hr or [0]))
        if department_id:
            domain.append(("department_id", "=", int(department_id)))
        if state in ("done", "in_progress", "not_started"):
            domain.append(("state", "=", state))
        return domain

    @api.model
    def get_calendar_data(self, year=None, month=None):
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        last_day = monthrange(year, month)[1]
        start = fields.Date.to_date("%04d-%02d-01" % (year, month))
        end = fields.Date.to_date("%04d-%02d-%02d" % (year, month, last_day))

        tasks = self.env["daily.task"].search(
            [("deadline", ">=", start), ("deadline", "<=", end)],
            order="deadline asc",
        )
        by_day = {}
        for task in tasks:
            key = str(task.deadline.day)
            by_day.setdefault(key, [])
            by_day[key].append(
                {
                    "id": task.id,
                    "name": task.name,
                    "state": task.state,
                    "priority": task.priority,
                    "assignee": task.assignee_id.name,
                }
            )
        return {
            "year": year,
            "month": month,
            "days": by_day,
            "today": today.isoformat(),
        }
