# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import html2plaintext


_WEEKDAYS_VI = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)
_TASK_BAR_COLORS = (
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
    "#ec4899",
    "#84cc16",
    "#f97316",
    "#14b8a6",
)
_DONE_STATUSES = ("done",)
_PROJECT_DOMAIN = [("is_template", "=", False)]


class ProjectProjectDashboard(models.Model):
    _inherit = "project.project"

    @api.model
    def get_lug_shell_data(self, project_id=False):
        """Header + dashboard for the custom Project shell."""
        header = self._get_lug_shell_header()
        try:
            dashboard = self._get_lug_dashboard(project_id=project_id)
        except Exception:
            self.env.cr.rollback()
            dashboard = self._empty_lug_dashboard()
        return {**header, "dashboard": dashboard}

    @api.model
    def _get_lug_shell_header(self):
        if "lug.app.center" in self.env:
            try:
                return self.env["lug.app.center"].get_portal_data()
            except Exception:
                self.env.cr.rollback()
        user = self.env.user
        company = self.env.company
        partner = user.partner_id
        today = fields.Date.context_today(self)
        weekday = _WEEKDAYS_VI[today.weekday()]
        avatar_url = False
        if partner and partner.image_128:
            avatar_url = "/web/image/res.partner/%s/image_128" % partner.id
        return {
            "company_name": "CÔNG TY TNHH SÁNG TÂM",
            "company_address": ", ".join(
                part
                for part in [
                    company.street,
                    company.street2,
                    company.city,
                    company.state_id.name if company.state_id else False,
                ]
                if part
            )
            or "30-34 Đường 74, Phường Bình Phú, TP. Hồ Chí Minh",
            "company_logo_url": (
                "/web/image/res.company/%s/logo" % company.id
                if company.logo
                else "/lug_app_center/static/src/img/sataco_logo.png"
            ),
            "user_name": user.name or "",
            "user_role": (
                "Quản trị viên"
                if user.has_group("base.group_system")
                else "Người dùng"
            ),
            "user_initial": (user.name or "U")[:1].upper(),
            "avatar_url": avatar_url,
            "greeting": {
                "headline": "Xin chào, %s!" % (user.name or "bạn"),
                "today_label_full": "%s, %s" % (weekday, today.strftime("%d/%m/%Y")),
                "primary_line": "Tổng quan tiến độ và hạn các dự án đang phụ trách.",
            },
        }

    @api.model
    def _empty_lug_dashboard(self):
        return {
            "kpis": [],
            "months": [],
            "upcoming": [],
            "personnel": [],
            "activities": [],
            "overdue_count": 0,
            "project_count": 0,
            "featured_title": "Báo cáo KPI dự án",
            "status": [],
            "gantt": [],
            "gantt_axis": [],
            "gantt_today": 0,
            "gantt_cal": {"months": [], "days": [], "count": 0, "today": 0, "day_px": 22},
            "progress": [],
            "status_pie": [],
            "at_risk_tasks": [],
            "heatmap": {"months": [], "rows": []},
            "filter_projects": [],
            "filter_project_id": False,
        }

    @api.model
    def _get_lug_dashboard(self, project_id=False):
        today = fields.Date.context_today(self)
        Project = self.with_context(active_test=True)
        try:
            project_id = int(project_id) if project_id else False
        except (TypeError, ValueError):
            project_id = False
        all_projects = Project.search(_PROJECT_DOMAIN)
        filter_projects = [{"id": rec.id, "name": rec.name} for rec in all_projects[:80]]
        if project_id:
            projects = all_projects.filtered(lambda rec: rec.id == project_id)
            if not projects:
                projects = all_projects
                project_id = False
        else:
            projects = all_projects
        chart_domain = list(_PROJECT_DOMAIN)
        if project_id:
            chart_domain.append(("id", "=", project_id))
        prev_end = today.replace(day=1) - timedelta(days=1)
        prev_start = prev_end.replace(day=1)

        def _is_done(project):
            return project.last_update_status in _DONE_STATUSES

        def _deadline(project):
            return project.lug_deadline or project.date

        total = len(projects)
        done_recs = projects.filtered(_is_done)
        overdue_recs = projects.filtered(
            lambda p: (not _is_done(p)) and _deadline(p) and _deadline(p) < today
        )
        ongoing_recs = projects - done_recs
        done = len(done_recs)
        overdue = len(overdue_recs)
        ongoing = len(ongoing_recs)

        prev_month_dt = datetime.combine(today.replace(day=1), datetime.min.time())
        prev_projects = Project.search(
            chart_domain + [("create_date", "<", prev_month_dt)]
        )
        prev_done = len(prev_projects.filtered(_is_done))
        prev_overdue = len(
            prev_projects.filtered(
                lambda p: (not _is_done(p))
                and _deadline(p)
                and _deadline(p) < prev_start
            )
        )
        prev_total = len(prev_projects)
        prev_ongoing = max(prev_total - prev_done, 0)

        def _pct(now, prev):
            if not prev:
                return 0
            return round((now - prev) * 100.0 / prev)

        upcoming = []
        for project in projects.sorted(key=lambda p: _deadline(p) or fields.Date.to_date("9999-12-31")):
            due = _deadline(project)
            if _is_done(project) or not due:
                continue
            upcoming.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "code": project.lug_code or "",
                    "deadline": due.strftime("%d/%m/%Y"),
                    "overdue": due < today,
                    "status_label": "Quá hạn" if due < today else "Sắp tới hạn",
                }
            )
            if len(upcoming) >= 6:
                break

        months = []
        month_start = today.replace(day=1) - relativedelta(months=5)
        for index in range(6):
            start = month_start + relativedelta(months=index)
            end = start + relativedelta(months=1)
            start_dt = datetime.combine(start, datetime.min.time())
            end_dt = datetime.combine(end, datetime.min.time())
            created_count = Project.search_count(
                chart_domain
                + [
                    ("create_date", ">=", start_dt),
                    ("create_date", "<", end_dt),
                ]
            )
            month_done = Project.search_count(
                chart_domain
                + [
                    ("last_update_status", "=", "done"),
                    ("write_date", ">=", start_dt),
                    ("write_date", "<", end_dt),
                ]
            )
            month_overdue = len(
                projects.filtered(
                    lambda p: (not _is_done(p))
                    and _deadline(p)
                    and start <= _deadline(p) < end
                    and _deadline(p) < today
                )
            )
            months.append(
                {
                    "label": "T%s" % start.month,
                    "done": month_done,
                    "ongoing": max(created_count - month_done, 0),
                    "overdue": month_overdue,
                }
            )

        personnel = []
        if "project.task" in self.env:
            task_domain = [
                ("has_template_ancestor", "=", False),
                ("has_project_template", "=", False),
                ("user_ids", "!=", False),
            ]
            if project_id:
                task_domain.append(("project_id", "=", project_id))
            tasks = self.env["project.task"].search(task_domain)
            grouped = defaultdict(set)
            for task in tasks:
                label = (
                    task.project_id.lug_type_id.name
                    or task.project_id.name
                    or "Chưa phân loại"
                )
                grouped[label].update(task.user_ids.ids)
            personnel = [
                {"label": name, "value": len(user_ids)}
                for name, user_ids in sorted(grouped.items(), key=lambda item: -len(item[1]))[:6]
            ]

        activities = []
        try:
            messages = self.env["mail.message"].search(
                [
                    ("model", "=", "project.project"),
                    ("message_type", "in", ["comment", "notification", "auto_comment"]),
                ],
                limit=8,
                order="id desc",
            )
            now = fields.Datetime.now()
            for msg in messages:
                project = Project.browse(msg.res_id)
                if not project.exists():
                    continue
                body = (html2plaintext(msg.body or "") or msg.subject or "Cập nhật dự án").strip()
                if len(body) > 90:
                    body = body[:87] + "…"
                delta = now - (msg.date or now)
                secs = max(int(delta.total_seconds()), 0)
                if secs < 60:
                    ago = "Vừa xong"
                elif secs < 3600:
                    ago = "%s phút trước" % (secs // 60)
                elif secs < 86400:
                    ago = "%s giờ trước" % (secs // 3600)
                else:
                    ago = "%s ngày trước" % max(secs // 86400, 1)
                author = msg.author_id
                activities.append(
                    {
                        "id": msg.id,
                        "author": author.name or msg.email_from or "Hệ thống",
                        "avatar": (
                            "/web/image/res.partner/%s/image_128" % author.id
                            if author
                            else False
                        ),
                        "initial": (author.name or "H")[:1].upper(),
                        "text": body,
                        "project": project.name,
                        "project_id": project.id,
                        "ago": ago,
                    }
                )
        except Exception:
            self.env.cr.rollback()
            activities = []

        gantt_rows, gantt_axis, gantt_today, gantt_cal = self._lug_gantt_data(projects, today)
        at_risk_tasks = self._lug_at_risk_tasks(today, project_id=project_id)
        heatmap = self._lug_heatmap(today, project_id=project_id)

        return {
            "kpis": [
                {
                    "key": "total",
                    "label": "Tổng dự án",
                    "value": total,
                    "icon": "fa-folder-open",
                    "tone": "purple",
                    "delta": _pct(total, prev_total),
                },
                {
                    "key": "ongoing",
                    "label": "Đang triển khai",
                    "value": ongoing,
                    "icon": "fa-clipboard",
                    "tone": "blue",
                    "delta": _pct(ongoing, prev_ongoing),
                },
                {
                    "key": "done",
                    "label": "Đã hoàn thành",
                    "value": done,
                    "icon": "fa-check-circle",
                    "tone": "green",
                    "delta": _pct(done, prev_done),
                },
                {
                    "key": "overdue",
                    "label": "Dự án quá hạn",
                    "value": overdue,
                    "icon": "fa-exclamation-triangle",
                    "tone": "red",
                    "delta": _pct(overdue, prev_overdue),
                },
            ],
            "months": months,
            "upcoming": upcoming,
            "personnel": personnel,
            "activities": activities,
            "overdue_count": overdue,
            "project_count": total,
            "featured_title": self._lug_featured_title(projects),
            "status": self._lug_status_breakdown(projects),
            "gantt": gantt_rows,
            "gantt_axis": gantt_axis,
            "gantt_today": gantt_today,
            "gantt_cal": gantt_cal,
            "progress": self._lug_progress_rows(projects),
            "status_pie": self._lug_status_pie(projects, today, done, overdue, total),
            "at_risk_tasks": at_risk_tasks,
            "heatmap": heatmap,
            "filter_projects": filter_projects,
            "filter_project_id": project_id or False,
        }

    @api.model
    def _lug_featured_title(self, projects):
        ongoing = projects.filtered(lambda p: p.last_update_status != "done")
        pick = ongoing[:1] or projects[:1]
        if pick:
            return pick.name
        return "Báo cáo KPI dự án"

    @api.model
    def _lug_status_breakdown(self, projects):
        total = len(projects) or 1
        mapping = [
            ("on_track", "Đúng tiến độ", "on-track", "#16a34a"),
            ("at_risk", "Có rủi ro", "at-risk", "#f59e0b"),
            ("off_track", "Nghiêm trọng", "critical", "#dc2626"),
            ("to_define", "Chưa đánh giá", "undefined", "#64748b"),
        ]
        counts = defaultdict(int)
        for project in projects:
            key = project.last_update_status or "to_define"
            if key == "on_hold":
                key = "to_define"
            if key == "done":
                continue
            counts[key] += 1
        rows = []
        for key, label, css, color in mapping:
            value = counts.get(key, 0)
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "css": css,
                    "color": color,
                    "count": value,
                    "pct": round(value * 100.0 / total, 2),
                }
            )
        return rows

    @api.model
    def _lug_as_date(self, value):
        if not value:
            return None
        if hasattr(value, "date") and callable(value.date):
            return value.date()
        return value

    @api.model
    def _lug_gantt_clip(self, start, end, win_start, win_end):
        if not start:
            return None
        if not end or end < start:
            end = start
        start = max(start, win_start)
        end = min(end, win_end)
        if end < start:
            return None
        return (start - win_start).days, (end - start).days + 1

    @api.model
    def _lug_gantt_data(self, projects, today):
        empty_cal = {"months": [], "days": [], "count": 0, "today": 0, "day_px": 22}
        single = len(projects) == 1
        picked = projects[:1] if single else projects[:5]
        if not picked:
            return [], [], 0, empty_cal

        def _project_span(project):
            start = self._lug_as_date(project.date_start)
            if not start:
                start = self._lug_as_date(project.create_date) or today
            end = self._lug_as_date(project.lug_deadline) or self._lug_as_date(project.date)
            if not end:
                end = start + timedelta(days=30)
            if end < start:
                end = start + timedelta(days=7)
            return start, end

        spans = {project.id: _project_span(project) for project in picked}
        all_dates = [today]
        for start, end in spans.values():
            all_dates.extend((start, end))

        tasks_by_project = defaultdict(list)
        if "project.task" in self.env:
            try:
                tasks = self.env["project.task"].search(
                    [
                        ("project_id", "in", picked.ids),
                        ("has_template_ancestor", "=", False),
                        ("has_project_template", "=", False),
                    ],
                    limit=80 if single else 40,
                    order="priority desc, date_deadline, id",
                )
                for task in tasks:
                    t_start = (
                        self._lug_as_date(task.date_assign)
                        or self._lug_as_date(task.create_date)
                        or spans.get(task.project_id.id, (today, today))[0]
                    )
                    t_end = (
                        self._lug_as_date(task.date_end)
                        or self._lug_as_date(task.date_deadline)
                        or (t_start + timedelta(days=7))
                    )
                    if t_end < t_start:
                        t_end = t_start + timedelta(days=3)
                    all_dates.extend((t_start, t_end))
                    tasks_by_project[task.project_id.id].append(
                        {
                            "id": task.id,
                            "name": task.name,
                            "start": t_start,
                            "end": t_end,
                            "state": task.state or "01_in_progress",
                        }
                    )
            except Exception:
                self.env.cr.rollback()
                tasks_by_project = defaultdict(list)

        milestones_by_project = defaultdict(list)
        if "project.milestone" in self.env:
            try:
                milestones = self.env["project.milestone"].search(
                    [
                        ("project_id", "in", picked.ids),
                        ("deadline", "!=", False),
                    ],
                    limit=24,
                    order="deadline, id",
                )
                for milestone in milestones:
                    due = self._lug_as_date(milestone.deadline)
                    if not due:
                        continue
                    all_dates.append(due)
                    milestones_by_project[milestone.project_id.id].append(
                        {"id": milestone.id, "name": milestone.name, "deadline": due}
                    )
            except Exception:
                self.env.cr.rollback()
                milestones_by_project = defaultdict(list)

        min_d = min(all_dates)
        max_d = max(all_dates)
        win_start = min_d.replace(day=1)
        win_end = (max_d.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        max_span = 120
        if (win_end - win_start).days + 1 > max_span:
            win_start = today.replace(day=1) - relativedelta(months=1)
            win_end = win_start + timedelta(days=max_span - 1)

        count = (win_end - win_start).days + 1
        months = []
        cursor = win_start
        while cursor <= win_end:
            month_end = min(
                (cursor + relativedelta(months=1)) - timedelta(days=1),
                win_end,
            )
            months.append(
                {
                    "label": "Tháng %s %s" % (cursor.month, cursor.year),
                    "days": (month_end - cursor).days + 1,
                }
            )
            cursor = cursor + relativedelta(months=1)

        days = []
        for offset in range(count):
            day = win_start + timedelta(days=offset)
            days.append(
                {
                    "n": day.day,
                    "we": day.weekday() >= 5,
                    "su": day.weekday() == 6,
                    "t": day == today,
                }
            )

        today_idx = max(0, min(count - 1, (today - win_start).days))
        today_pct = round(today_idx * 100.0 / max(count - 1, 1), 2)
        axis = [month["label"] for month in months]
        cal = {
            "months": months,
            "days": days,
            "count": count,
            "today": today_idx,
            "day_px": 22,
        }

        status_label = {
            "done": "Hoàn thành",
            "on_track": "Đúng tiến độ",
            "at_risk": "Có rủi ro",
            "off_track": "Trễ hạn",
            "on_hold": "Tạm dừng",
            "to_define": "Chưa bắt đầu",
        }
        task_label = {
            "01_in_progress": "Đang thực hiện",
            "02_changes_requested": "Chỉnh sửa",
            "03_approved": "Đã duyệt",
            "1_done": "Hoàn thành",
            "1_canceled": "Hủy",
            "04_waiting_normal": "Đang chờ",
        }

        rows = []
        for project in picked:
            start, end = spans[project.id]
            clip = self._lug_gantt_clip(start, end, win_start, win_end)
            child_tasks = tasks_by_project.get(project.id, [])[:20 if single else 5]
            child_ms = milestones_by_project.get(project.id, [])
            ms_idx = []
            for milestone in child_ms:
                if win_start <= milestone["deadline"] <= win_end:
                    ms_idx.append((milestone["deadline"] - win_start).days)
            rows.append(
                {
                    "id": "p-%s" % project.id,
                    "kind": "project",
                    "name": project.name,
                    "project_id": project.id,
                    "res_id": project.id,
                    "has_children": bool(child_tasks or child_ms),
                    "start": clip[0] if clip else 0,
                    "span": clip[1] if clip else 1,
                    "left": 0,
                    "width": 6,
                    "color": "#334155",
                    "label": status_label.get(project.last_update_status or "to_define", ""),
                    "ms": ms_idx,
                    "status": project.last_update_status or "to_define",
                }
            )
            for task_index, task in enumerate(child_tasks):
                tclip = self._lug_gantt_clip(task["start"], task["end"], win_start, win_end)
                if not tclip:
                    continue
                rows.append(
                    {
                        "id": "t-%s" % task["id"],
                        "kind": "task",
                        "name": task["name"],
                        "project_id": project.id,
                        "res_id": task["id"],
                        "has_children": False,
                        "start": tclip[0],
                        "span": tclip[1],
                        "left": 0,
                        "width": 6,
                        "color": _TASK_BAR_COLORS[task_index % len(_TASK_BAR_COLORS)],
                        "label": task_label.get(task["state"], ""),
                        "ms": [],
                        "status": task["state"],
                    }
                )
            if child_ms:
                first_due = child_ms[0]["deadline"]
                mclip = self._lug_gantt_clip(first_due, first_due, win_start, win_end)
                rows.append(
                    {
                        "id": "m-%s" % project.id,
                        "kind": "milestone",
                        "name": "Milestone",
                        "project_id": project.id,
                        "res_id": project.id,
                        "has_children": False,
                        "start": mclip[0] if mclip else 0,
                        "span": 1,
                        "left": 0,
                        "width": 6,
                        "color": "#64748b",
                        "label": "",
                        "ms": ms_idx,
                        "status": "milestone",
                    }
                )
        return rows, axis, today_pct, cal

    @api.model
    def _lug_status_pie(self, projects, today, done, overdue, total):
        not_started = len(
            projects.filtered(lambda p: (p.last_update_status or "to_define") == "to_define")
        )
        in_progress = max(total - done - overdue - not_started, 0)
        return [
            {"key": "done", "label": "Hoàn thành", "count": done, "color": "#22c55e"},
            {"key": "progress", "label": "Đang làm", "count": in_progress, "color": "#3b82f6"},
            {"key": "wait", "label": "Chưa bắt đầu", "count": not_started, "color": "#94a3b8"},
            {"key": "overdue", "label": "Trễ hạn", "count": overdue, "color": "#ef4444"},
        ]

    @api.model
    def _lug_progress_rows(self, projects):
        score = {
            "done": 100,
            "on_track": 72,
            "at_risk": 48,
            "off_track": 22,
            "on_hold": 15,
            "to_define": 8,
        }
        rows = []
        for project in projects[:8]:
            pct = score.get(project.last_update_status or "to_define", 8)
            if pct >= 70:
                tone = "green"
            elif pct >= 40:
                tone = "amber"
            else:
                tone = "red"
            rows.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "pct": pct,
                    "tone": tone,
                }
            )
        return rows

    @api.model
    def _lug_at_risk_tasks(self, today, project_id=False):
        if "project.task" not in self.env:
            return []
        domain = [
            ("has_template_ancestor", "=", False),
            ("has_project_template", "=", False),
            "|",
            ("date_deadline", "<", today),
            ("project_id.last_update_status", "in", ["at_risk", "off_track"]),
        ]
        if project_id:
            domain.insert(0, ("project_id", "=", project_id))
        try:
            tasks = self.env["project.task"].search(
                domain,
                limit=8,
                order="priority desc, date_deadline",
            )
        except Exception:
            self.env.cr.rollback()
            return []
        priority_map = {
            "0": "Thấp",
            "1": "Trung bình",
            "2": "Cao",
            "3": "Khẩn",
        }
        status_map = {
            "on_track": ("Đúng tiến độ", "on-track"),
            "at_risk": ("Có rủi ro", "at-risk"),
            "off_track": ("Nghiêm trọng", "critical"),
            "done": ("Hoàn thành", "done"),
        }
        rows = []
        for task in tasks:
            project_status = task.project_id.last_update_status or "to_define"
            due = task.date_deadline
            if due and hasattr(due, "date"):
                due = due.date()
            overdue = bool(due and due < today)
            if overdue and project_status not in ("off_track", "at_risk"):
                label, css = "Có rủi ro", "at-risk"
            else:
                label, css = status_map.get(project_status, ("Chưa đánh giá", "undefined"))
            priority = task.priority or "0"
            rows.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "status_label": label,
                    "status_css": css,
                    "priority_label": priority_map.get(priority, "Thấp"),
                    "priority_css": "high" if priority in ("2", "3") else "low",
                    "pr": int(priority) + 1,
                    "project_id": task.project_id.id,
                }
            )
        return rows

    @api.model
    def _lug_heatmap(self, today, project_id=False):
        empty = {"months": [], "rows": []}
        if "project.task" not in self.env:
            return empty
        month_starts = []
        start = today.replace(day=1) - relativedelta(months=5)
        for index in range(6):
            month_starts.append(start + relativedelta(months=index))
        month_labels = ["T%s" % dt.month for dt in month_starts]
        domain = [
            ("has_template_ancestor", "=", False),
            ("has_project_template", "=", False),
            ("user_ids", "!=", False),
            ("date_deadline", "!=", False),
            ("date_deadline", ">=", month_starts[0]),
            ("date_deadline", "<", month_starts[-1] + relativedelta(months=1)),
        ]
        if project_id:
            domain.append(("project_id", "=", project_id))
        try:
            tasks = self.env["project.task"].search(domain)
        except Exception:
            self.env.cr.rollback()
            return empty
        per_user = defaultdict(lambda: [0] * 6)
        names = {}
        for task in tasks:
            due = task.date_deadline
            if due and hasattr(due, "date"):
                due = due.date()
            if not due:
                continue
            month_index = None
            for index, month_start in enumerate(month_starts):
                month_end = month_start + relativedelta(months=1)
                if month_start <= due < month_end:
                    month_index = index
                    break
            if month_index is None:
                continue
            for user in task.user_ids[:3]:
                per_user[user.id][month_index] += 1
                names[user.id] = user.name
        if not per_user:
            return {"months": month_labels, "rows": []}
        ranked = sorted(per_user.items(), key=lambda item: -sum(item[1]))[:5]
        peak = max(max(values) for _uid, values in ranked) or 1
        rows = []
        for user_id, values in ranked:
            rows.append(
                {
                    "id": user_id,
                    "name": names.get(user_id) or "Người dùng",
                    "values": [round(value * 100.0 / peak) for value in values],
                }
            )
        return {"months": month_labels, "rows": rows}

    _LUG_WF_LABELS = {
        "todo": "Chưa bắt đầu",
        "progress": "Đang thực hiện",
        "done": "Hoàn thành",
        "closed": "Đóng",
    }
    _LUG_TASK_STATE_LABELS = {
        "draft": "Chưa bắt đầu",
        "in_progress": "Đang làm",
        "done": "Hoàn thành",
    }
    _LUG_PHASE_TONES = ("purple", "orange", "blue", "teal", "pink", "amber")

    @api.model
    def _lug_fmt_date(self, value):
        if not value:
            return False
        if hasattr(value, "date"):
            value = value.date()
        return value.strftime("%d/%m/%Y")

    _LUG_TYPE_TONES = ("purple", "violet", "blue", "teal", "pink", "amber")
    _LUG_AVATAR_COLORS = (
        "#2563eb",
        "#7c3aed",
        "#0891b2",
        "#ea580c",
        "#db2777",
        "#16a34a",
        "#4f46e5",
        "#0d9488",
    )

    @api.model
    def _lug_user_chip(self, user):
        if not user:
            return False
        name = user.name or "?"
        partner = user.partner_id
        avatar_url = (
            "/web/image/res.partner/%s/image_128" % partner.id
            if partner and partner.image_128
            else False
        )
        return {
            "id": user.id,
            "name": name,
            "initial": name.strip()[:1].upper() or "?",
            "avatar_url": avatar_url,
            "color": self._LUG_AVATAR_COLORS[user.id % len(self._LUG_AVATAR_COLORS)],
        }

    @api.model
    def _lug_assignee_chips(self, project):
        if project.lug_assignee_ids:
            pool = project.lug_assignee_ids
        elif project.task_ids.user_ids:
            pool = project.task_ids.user_ids
        elif project.lug_pic_id:
            pool = project.lug_pic_id
        else:
            return {"users": [], "extra": 0}
        total = len(pool)
        visible = pool[:3]
        chips = [self._lug_user_chip(user) for user in visible if user]
        return {"users": chips, "extra": max(0, total - len(chips))}

    @api.model
    def _lug_type_chip(self, type_rec):
        if not type_rec:
            return {"label": "—", "tone": "none"}
        tone = self._LUG_TYPE_TONES[type_rec.id % len(self._LUG_TYPE_TONES)]
        return {"label": type_rec.name, "tone": tone}

    @api.model
    def _lug_project_timeleft_meta(self, project, today=None):
        today = today or fields.Date.context_today(self)
        if project.lug_workflow_state == "done" or project.last_update_status == "done":
            return {"state": "done", "label": "Hoàn thành", "short": "Hoàn thành", "hint": False}
        deadline = project.lug_deadline or project.date
        if not deadline:
            return {"state": "none", "label": "—", "short": "—", "hint": False}
        delta = (deadline - today).days
        if delta >= 0:
            hint = "Đúng tiến độ" if (project.lug_progress_pct or 0) >= 50 else False
            short = "Còn %s n" % delta if delta >= 10 else "Còn %s ngày" % delta
            return {
                "state": "ok",
                "label": "Còn %s ngày" % delta,
                "short": short,
                "hint": hint,
            }
        return {
            "state": "late",
            "label": "Trễ %s ngày" % abs(delta),
            "short": "Trễ %s n" % abs(delta),
            "hint": "Quá hạn",
        }

    @api.model
    def _lug_task_timeleft_meta(self, task, today=None):
        today = today or fields.Date.context_today(self)
        if task.state == "done":
            if task.deadline:
                delta = (task.deadline - today).days
                if delta < 0:
                    return {"state": "done", "label": "%s ngày" % delta, "short": "%s ngày" % delta}
            return {"state": "done", "label": "Hoàn thành", "short": "Xong"}
        if not task.deadline:
            return {"state": "none", "label": "—", "short": "—"}
        delta = (task.deadline - today).days
        if delta >= 0:
            short = "Còn %s n" % delta if delta >= 10 else "Còn %s ngày" % delta
            return {"state": "ok", "label": "Còn %s ngày" % delta, "short": short}
        return {
            "state": "late",
            "label": "Trễ %s ngày" % abs(delta),
            "short": "%s ngày" % delta,
        }

    @api.model
    def _lug_project_assignees_label(self, project):
        users = project.lug_assignee_ids or project.task_ids.user_ids
        if users:
            names = users.mapped("name")
            if len(names) <= 3:
                return ", ".join(names)
            return ", ".join(names[:2]) + ", …"
        if project.lug_pic_id:
            return project.lug_pic_id.name
        return "—"

    @api.model
    def _lug_serialize_project_row(self, project, today=None):
        today = today or fields.Date.context_today(self)
        wf = project.lug_workflow_state or "todo"
        deadline_raw = project.lug_deadline or project.date
        is_late = bool(
            deadline_raw
            and deadline_raw < today
            and wf not in ("done", "closed")
            and project.last_update_status != "done"
        )
        manager = self._lug_user_chip(project.user_id)
        assignees = self._lug_assignee_chips(project)
        return {
            "id": project.id,
            "stt": project.lug_stt or 0,
            "code": project.lug_code or "—",
            "name": project.name or "—",
            "type": self._lug_type_chip(project.lug_type_id),
            "deadline": self._lug_fmt_date(deadline_raw),
            "deadline_late": is_late,
            "manager": manager,
            "assignees": assignees,
            "status": wf,
            "status_label": self._LUG_WF_LABELS.get(wf, wf),
            "timeleft": self._lug_project_timeleft_meta(project, today=today),
        }

    @api.model
    def get_lug_project_list_data(self, search="", offset=0, limit=50):
        """Paginated project rows for the custom dark list UI."""
        today = fields.Date.context_today(self)
        domain = list(_PROJECT_DOMAIN)
        search = (search or "").strip()
        if search:
            domain += [
                "|",
                "|",
                "|",
                ("name", "ilike", search),
                ("lug_code", "ilike", search),
                ("lug_content", "ilike", search),
                ("lug_type_id.name", "ilike", search),
            ]
        Project = self.with_context(active_test=True)
        total = Project.search_count(domain)
        try:
            offset = max(0, int(offset or 0))
            limit = max(1, min(200, int(limit or 50)))
        except (TypeError, ValueError):
            offset, limit = 0, 50
        projects = Project.search(domain, order="lug_stt, id", offset=offset, limit=limit)
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "rows": [self._lug_serialize_project_row(rec, today=today) for rec in projects],
        }

    @api.model
    def get_lug_project_list_detail(self, project_id):
        """Expanded row payload: project info + staged tasks."""
        project = self.browse(int(project_id)).exists()
        if not project or project.is_template:
            return False
        today = fields.Date.context_today(self)
        docs = project.lug_attachment_ids.filtered(
            lambda att: (att.name or "").lower().endswith(
                (".pdf", ".doc", ".docx", ".xls", ".xlsx")
            )
        )
        attachment = docs.sorted("id", reverse=True)[:1] or project.lug_attachment_ids[:1]
        tasks = project.stage_line_ids.task_ids
        done_count = len(tasks.filtered(lambda t: t.state == "done"))
        total_count = len(tasks)
        stages = []
        for index, stage in enumerate(
            project.stage_line_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0)),
            1,
        ):
            tone = self._LUG_PHASE_TONES[(index - 1) % len(self._LUG_PHASE_TONES)]
            stage_name = (stage.name or "").strip() or ("Giai đoạn %s" % index)
            stage_tasks = []
            for task in stage.task_ids.sorted(lambda rec: (rec.sequence or 0, rec.id or 0)):
                tl = self._lug_task_timeleft_meta(task, today=today)
                state = task.state or "draft"
                stage_tasks.append(
                    {
                        "id": task.id,
                        "stt": task.stt or "%s.%s" % (index, len(stage_tasks) + 1),
                        "name": task.name or "—",
                        "assignees": task.user_display or "—",
                        "supervisors": task.supervisor_display or False,
                        "deadline": self._lug_fmt_date(task.deadline),
                        "result": (task.notes or "")[:120] or "—",
                        "state": state,
                        "state_label": self._LUG_TASK_STATE_LABELS.get(state, state),
                        "timeleft": tl,
                        "notes": task.notes or "",
                    }
                )
            stages.append(
                {
                    "id": stage.id,
                    "phase_no": index,
                    "phase_label": stage_name,
                    "phase_tone": tone,
                    "tasks": stage_tasks,
                }
            )
        tl = self._lug_project_timeleft_meta(project, today=today)
        wf = project.lug_workflow_state or "todo"
        type_chip = self._lug_type_chip(project.lug_type_id)
        assignees = self._lug_assignee_chips(project)
        return {
            "id": project.id,
            "code": project.lug_code or "—",
            "name": project.name or "—",
            "type": type_chip,
            "type_label": type_chip.get("label") or "—",
            "type_id": project.lug_type_id.id if project.lug_type_id else False,
            "manager": self._lug_user_chip(project.user_id),
            "assignees": assignees,
            "assignees_label": self._lug_project_assignees_label(project),
            "pdf_name": attachment.name if attachment else False,
            "pdf_id": attachment.id if attachment else False,
            "date_start": self._lug_fmt_date(project.date_start),
            "deadline": self._lug_fmt_date(project.lug_deadline or project.date),
            "date_end": self._lug_fmt_date(project.date),
            "supply_date": self._lug_fmt_date(project.lug_supply_date),
            "timeleft": tl,
            "workflow_state": wf,
            "progress_pct": project.lug_progress_pct or 0,
            "progress_done": done_count,
            "progress_total": total_count,
            "stages": stages,
        }

    def lug_set_workflow_state(self, state):
        self.ensure_one()
        allowed = set(self._LUG_WF_LABELS)
        if state not in allowed:
            return False
        self.write({"lug_workflow_state": state})
        return True
