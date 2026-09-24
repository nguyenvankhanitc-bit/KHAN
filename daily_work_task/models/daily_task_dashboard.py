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
            "can_assign": Task._is_assigner(),
            "can_view_others": Task._is_viewer(),
            "can_view_checklist": Task._is_manager()
            or bool(Task._checklist_employee_ids()),
            "can_see_performance": self.env[
                "daily.task.performance.access"
            ].user_can_view(),
            "user_name": self.env.user.name or "",
            "company_name": self.env.company.name or "",
        }

    @api.model
    def get_dashboard_bootstrap(self, filters=None):
        """1 RPC: filter options + dashboard data (giảm round-trip mở phân hệ)."""
        opts = self.get_filter_options()
        payload = dict(filters or {})
        if not payload.get("date_from"):
            payload["date_from"] = opts.get("default_date_from") or False
        if not payload.get("date_to"):
            payload["date_to"] = opts.get("default_date_to") or False
        data = self.get_dashboard_data(payload)
        return {"options": opts, "data": data, "filters": payload}

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        Task = self.env["daily.task"]
        today = fields.Date.context_today(self)

        domain = self._build_domain(filters)
        # Sync nhẹ vài bản ghi lệch cờ — không đụng toàn bộ kỳ.
        stale_ids = Task.search(
            domain
            + [
                ("state", "!=", "done"),
                ("deadline", "!=", False),
                ("deadline", "<", today),
                ("is_overdue", "=", False),
            ],
            limit=100,
        ).ids
        if stale_ids:
            Task._refresh_overdue_flags(Task.browse(stale_ids))

        # search_read: tránh N+1 ORM khi duyệt recordset lớn.
        rows = Task.search_read(
            domain,
            [
                "name",
                "deadline",
                "assign_date",
                "state",
                "priority",
                "is_overdue",
                "duration_minutes",
                "duration_hours",
                "completion_percent",
                "assignee_id",
                "department_id",
            ],
            order="deadline asc, id desc",
            limit=5000,
        )

        def _m2o_name(val):
            if isinstance(val, (list, tuple)) and val:
                return val[1] or ""
            return ""

        def _m2o_id(val):
            if isinstance(val, (list, tuple)) and val:
                return val[0]
            return val or False

        total = len(rows)
        done = sum(1 for r in rows if r.get("state") == "done")
        in_progress = sum(1 for r in rows if r.get("state") == "in_progress")
        not_started = sum(1 for r in rows if r.get("state") == "not_started")
        overdue_rows = [r for r in rows if r.get("is_overdue")]
        overdue_count = len(overdue_rows)

        def pct(n):
            return round(100.0 * n / float(total), 1) if total else 0.0

        hours = round(sum(float(r.get("duration_hours") or 0.0) for r in rows), 1)
        efficiency = pct(done)

        upcoming_end = today + timedelta(days=7)
        upcoming_rows = []
        for r in rows:
            dl = r.get("deadline")
            if not dl or r.get("state") == "done" or r.get("is_overdue"):
                continue
            try:
                d = fields.Date.to_date(dl)
            except Exception:
                continue
            if today <= d <= upcoming_end:
                upcoming_rows.append(r)
        upcoming_count = len(upcoming_rows)
        assigned_count = sum(1 for r in rows if r.get("assignee_id"))

        note_ov = note_up = 0
        try:
            self.env.cr.execute("SELECT to_regclass('public.daily_work_note')")
            has_table = bool(self.env.cr.fetchone()[0])
            if has_table and "daily.work.note" in self.env:
                rows_ov, rows_up = (
                    self.env["daily.work.note"]
                    .sudo()
                    .get_reminder_rows_for_user(
                        self.env.user.id, today=today, upcoming_days=7
                    )
                )
                note_ov = len(rows_ov or [])
                note_up = len(rows_up or [])
        except Exception:
            self.env.cr.rollback()
            note_ov = note_up = 0
        overdue_count += note_ov
        upcoming_count += note_up

        emp_ids = set()
        for r in rows:
            # employee_hr stored on task via related — fallback assignee only for count
            aid = _m2o_id(r.get("assignee_id"))
            if aid:
                emp_ids.add(aid)
        all_emp = self.env["daily.task.employee"].search_count([("active", "=", True)])
        if not Task._is_manager():
            allowed = set(Task._viewable_employee_ids() or [])
            my = Task._my_hr_employee()
            if my:
                allowed.add(my.id)
            all_emp = len(allowed) or 1
        emp_active = len(emp_ids)

        growth = self._period_growth(filters, total)
        today_count = Task.search_count(
            self._build_domain(filters) + [("deadline", "=", today)]
        )

        kpi = {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "not_started": not_started,
            "overdue": overdue_count,
            "today": today_count,
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

        priority_counter = Counter((r.get("priority") or "medium") for r in rows)
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

        weekly = self._weekly_trend_rows(rows, filters, today)
        dept_chart, dept_perf = self._department_stats_rows(rows)
        top_employees = self._top_employees_rows(rows, limit=5)

        kpi_rank = []
        kpi_rank_dept = ""
        # Bỏ search thêm 3 tháng + refresh flags (rất chậm). Dùng luôn data kỳ lọc.
        if not Task._is_manager():
            my = Task._my_hr_employee()
            if my and my.department_id:
                kpi_rank_dept = my.department_id.display_name or ""
            kpi_rank = self._employee_kpi_rank_rows(rows, limit=20)

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

        pri_sel = dict(Task._fields["priority"].selection)
        state_sel = dict(Task._fields["state"].selection)

        def serialize(recs, limit=50):
            out = []
            for r in recs[:limit]:
                dl = r.get("deadline")
                try:
                    d = fields.Date.to_date(dl) if dl else None
                except Exception:
                    d = None
                overdue_days = 0
                if d and r.get("is_overdue"):
                    overdue_days = max(0, (today - d).days)
                st = r.get("state") or ""
                pr = r.get("priority") or ""
                out.append(
                    {
                        "id": r["id"],
                        "name": r.get("name") or "",
                        "deadline": d.strftime("%d/%m/%Y") if d else "",
                        "assignee": _m2o_name(r.get("assignee_id")),
                        "department": _m2o_name(r.get("department_id")),
                        "priority": pr,
                        "priority_label": pri_sel.get(pr, ""),
                        "state": st,
                        "state_label": state_sel.get(st, ""),
                        "is_overdue": bool(r.get("is_overdue")),
                        "overdue_days": overdue_days,
                        "progress": int(r.get("completion_percent") or 0)
                        if st != "done"
                        else max(int(r.get("completion_percent") or 0), 100),
                        "duration_hours": float(r.get("duration_hours") or 0.0),
                    }
                )
            return out

        today_rows = [
            r
            for r in rows
            if r.get("deadline") == fields.Date.to_string(today) and r.get("state") != "done"
        ]
        today_schedule = []
        for i, r in enumerate(today_rows[:12]):
            hour = 8 + (i % 8)
            today_schedule.append(
                {
                    "id": r["id"],
                    "time": "%02d:00" % hour,
                    "name": r.get("name") or "",
                    "assignee": _m2o_name(r.get("assignee_id")),
                    "state": r.get("state"),
                    "priority": r.get("priority"),
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
            "overdue_list": serialize(overdue_rows, 20),
            "done_list": serialize([r for r in rows if r.get("state") == "done"], 20),
            "in_progress_list": serialize(
                [
                    r
                    for r in rows
                    if r.get("state") == "in_progress" and not r.get("is_overdue")
                ],
                20,
            ),
            "not_started_list": serialize(
                [
                    r
                    for r in rows
                    if r.get("state") == "not_started" and not r.get("is_overdue")
                ],
                20,
            ),
            "recent_tasks": serialize(rows[:15], 15),
            "upcoming_list": serialize(upcoming_rows, 10),
            "today_schedule": today_schedule,
            "today_label": today.strftime("%d/%m/%Y"),
            "overdue_count": overdue_count,
            "is_manager": Task._is_manager(),
        }

    @api.model
    def _weekly_trend_rows(self, rows, filters, today):
        date_from = filters.get("date_from")
        try:
            base = fields.Date.to_date(date_from) if date_from else today.replace(day=1)
        except Exception:
            base = today.replace(day=1)
        buckets = defaultdict(list)
        for r in rows:
            raw = r.get("deadline") or r.get("assign_date")
            if not raw:
                continue
            try:
                d = fields.Date.to_date(raw)
            except Exception:
                continue
            week_idx = min(5, max(1, ((d.day - 1) // 7) + 1))
            buckets[week_idx].append(
                100
                if r.get("state") == "done"
                else int(r.get("completion_percent") or 0)
            )
        labels = ["Tuần %s" % w for w in range(1, 6)]
        values = []
        for w in range(1, 6):
            vals = buckets.get(w) or []
            values.append(round(sum(vals) / float(len(vals)), 1) if vals else 0.0)
        return {"labels": labels, "values": values}

    @api.model
    def _department_stats_rows(self, rows):
        by_dept = defaultdict(
            lambda: {"total": 0, "done": 0, "overdue": 0, "name": "Khác"}
        )

        def _m2o_name(val):
            if isinstance(val, (list, tuple)) and val:
                return val[1] or "Khác"
            return "Khác"

        def _m2o_id(val):
            if isinstance(val, (list, tuple)) and val:
                return val[0]
            return val or 0

        for r in rows:
            dept = r.get("department_id")
            key = _m2o_id(dept) or 0
            by_dept[key]["name"] = _m2o_name(dept) if key else "Khác"
            by_dept[key]["total"] += 1
            if r.get("state") == "done":
                by_dept[key]["done"] += 1
            if r.get("is_overdue"):
                by_dept[key]["overdue"] += 1

        colors = ["#3b82f6", "#22c55e", "#f59e0b", "#06b6d4", "#94a3b8", "#a855f7", "#ef4444"]
        items = sorted(by_dept.items(), key=lambda x: -x[1]["total"])
        total_all = sum(v["total"] for _, v in items) or 1
        labels, values, legend, perf = [], [], [], []
        for idx, (key, data) in enumerate(items[:8]):
            color = colors[idx % len(colors)]
            labels.append(data["name"])
            values.append(data["total"])
            share = round(100.0 * data["total"] / float(total_all), 1)
            legend.append(
                {"name": data["name"], "count": data["total"], "pct": share, "color": color}
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
    def _employee_kpi_rank_rows(self, rows, limit=20):
        by_emp = defaultdict(
            lambda: {
                "total": 0,
                "done": 0,
                "overdue": 0,
                "duration_minutes": 0,
                "name": "",
            }
        )

        def _m2o_name(val):
            if isinstance(val, (list, tuple)) and val:
                return val[1] or ""
            return ""

        def _m2o_id(val):
            if isinstance(val, (list, tuple)) and val:
                return val[0]
            return val or False

        for r in rows:
            eid = _m2o_id(r.get("assignee_id"))
            if not eid:
                continue
            by_emp[eid]["name"] = _m2o_name(r.get("assignee_id"))
            by_emp[eid]["total"] += 1
            by_emp[eid]["duration_minutes"] += int(r.get("duration_minutes") or 0)
            if r.get("state") == "done":
                by_emp[eid]["done"] += 1
            if r.get("is_overdue"):
                by_emp[eid]["overdue"] += 1
        out = []
        for eid, data in by_emp.items():
            if not data["total"]:
                continue
            eff = round(100.0 * data["done"] / float(data["total"]), 1)
            minutes = data["duration_minutes"] or 0
            out.append(
                {
                    "id": eid,
                    "name": data["name"],
                    "done": data["done"],
                    "total": data["total"],
                    "overdue": data["overdue"],
                    "duration_hours": round(minutes / 60.0, 2) if minutes else 0.0,
                    "efficiency": eff,
                }
            )
        out.sort(
            key=lambda r: (-r["efficiency"], -r["done"], -r["total"], r["name"] or "")
        )
        return out[:limit]

    @api.model
    def _top_employees_rows(self, rows, limit=5):
        by_emp = defaultdict(lambda: {"total": 0, "done": 0, "name": ""})

        def _m2o_name(val):
            if isinstance(val, (list, tuple)) and val:
                return val[1] or ""
            return ""

        def _m2o_id(val):
            if isinstance(val, (list, tuple)) and val:
                return val[0]
            return val or False

        for r in rows:
            eid = _m2o_id(r.get("assignee_id"))
            if not eid:
                continue
            by_emp[eid]["name"] = _m2o_name(r.get("assignee_id"))
            by_emp[eid]["total"] += 1
            if r.get("state") == "done":
                by_emp[eid]["done"] += 1
        out = []
        for eid, data in by_emp.items():
            if not data["total"]:
                continue
            eff = round(100.0 * data["done"] / float(data["total"]), 1)
            out.append(
                {
                    "id": eid,
                    "name": data["name"],
                    "done": data["done"],
                    "total": data["total"],
                    "efficiency": eff,
                }
            )
        out.sort(key=lambda r: (-r["efficiency"], -r["done"], r["name"]))
        return out[:limit]

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
        """Báo cáo CV theo nhân viên (hiệu suất + tổng giờ) trong tập task đã lọc."""
        by_emp = defaultdict(
            lambda: {
                "total": 0,
                "done": 0,
                "overdue": 0,
                "duration_minutes": 0,
                "name": "",
            }
        )
        for t in tasks:
            emp = t.assignee_id
            if not emp:
                continue
            by_emp[emp.id]["name"] = emp.name or ""
            by_emp[emp.id]["total"] += 1
            by_emp[emp.id]["duration_minutes"] += int(t.duration_minutes or 0)
            if t.state == "done":
                by_emp[emp.id]["done"] += 1
            if t.is_overdue:
                by_emp[emp.id]["overdue"] += 1
        rows = []
        for eid, data in by_emp.items():
            if not data["total"]:
                continue
            eff = round(100.0 * data["done"] / float(data["total"]), 1)
            minutes = data["duration_minutes"] or 0
            rows.append(
                {
                    "id": eid,
                    "name": data["name"],
                    "done": data["done"],
                    "total": data["total"],
                    "overdue": data["overdue"],
                    "duration_hours": round(minutes / 60.0, 2) if minutes else 0.0,
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
