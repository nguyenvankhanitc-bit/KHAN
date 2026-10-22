# -*- coding: utf-8 -*-
"""Báo cáo hiệu suất nhân sự (app Dự án) — cùng mẫu «Hiệu suất nhân sự» của Công việc hằng ngày.

Nguồn: công việc giai đoạn (project.stage.task) + nhiệm vụ Odoo (project.task) của dự án
đang hoạt động. Công việc thuộc tháng theo hạn chót; chưa có hạn → theo ngày tạo.
«QL đánh giá tổng»: % quản lý chốt cho từng nhân sự theo tháng.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

_NO_DEPT = "Chưa có phòng ban"


class LugProjectManagerPerf(models.Model):
    _name = "lug.project.manager.perf"
    _description = "QL đánh giá tổng (hiệu suất dự án theo tháng)"
    _order = "year desc, month desc, user_id"

    user_id = fields.Many2one("res.users", string="Nhân sự", required=True, index=True, ondelete="cascade")
    year = fields.Integer(required=True, index=True)
    month = fields.Integer(required=True, index=True)
    percent = fields.Float(string="QL đánh giá tổng (%)", digits=(5, 1), required=True)
    set_by_id = fields.Many2one("res.users", string="Người chốt", readonly=True)
    set_date = fields.Datetime(string="Ngày chốt", readonly=True)

    _uniq_user_month = models.Constraint(
        "unique(user_id, year, month)",
        "Mỗi nhân sự chỉ có một QL đánh giá tổng trong tháng.",
    )


class ProjectProjectPerfReport(models.Model):
    _inherit = "project.project"

    @api.model
    def _lug_perf_period(self, year=None, month=None):
        today = fields.Date.context_today(self)
        try:
            year = int(year or today.year)
            month = int(month or today.month)
        except (TypeError, ValueError):
            year, month = today.year, today.month
        if not 1 <= month <= 12:
            month = today.month
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return year, month, start, end

    @api.model
    def _lug_perf_can_rate(self, user, pmap=None):
        pmap = pmap or self.env["lug.project.app.perm"].get_map()
        if user.id == self.env.uid and not self.env.su:
            return False
        return bool(pmap["full"] or (pmap["configured"] and pmap["people"]["write"]))

    @api.model
    def _lug_perf_bucket(self, done, deadline, doing, today):
        if done:
            return "done"
        if deadline and deadline < today:
            return "late"
        return "doing" if doing else "todo"

    @api.model
    def _lug_perf_iter_tasks(self, project_ids, start=None, end=None):
        """Yield (project_id, users, bucket); start/end rỗng → mọi thời gian."""
        today = fields.Date.context_today(self)
        if start and end:
            start_dt = datetime.combine(start, time.min)
            end_dt = datetime.combine(end + timedelta(days=1), time.min)

        def _in_period(deadline, created):
            if not (start and end):
                return True
            if deadline:
                return start <= deadline <= end
            return bool(created) and start_dt <= created < end_dt

        stage_tasks = self.env["project.stage.task"].sudo().search([("project_id", "in", project_ids or [0])])
        for task in stage_tasks:
            if not _in_period(task.deadline, task.create_date):
                continue
            bucket = self._lug_perf_bucket(task.state == "done", task.deadline, task.state == "in_progress", today)
            yield task.project_id.id, task.user_ids, bucket

        native = self.env["project.task"].sudo().search([
            ("project_id", "in", project_ids or [0]),
            ("state", "!=", "1_canceled"),
        ])
        for task in native:
            deadline = task.date_deadline.date() if task.date_deadline else False
            if not _in_period(deadline, task.create_date):
                continue
            bucket = self._lug_perf_bucket(
                task.state == "1_done", deadline, task.state != "04_waiting_normal", today)
            yield task.project_id.id, task.user_ids, bucket

    @api.model
    def _lug_perf_task_counts(self, start, end):
        """{user_id: {done, doing, todo, late}} cho công việc trong tháng."""
        project_ids = self.search(self._lug_base_domain()).ids
        counts = defaultdict(lambda: {"done": 0, "doing": 0, "todo": 0, "late": 0})
        for _pid, users, bucket in self._lug_perf_iter_tasks(project_ids, start, end):
            for user in users:
                counts[user.id][bucket] += 1
        return counts

    @api.model
    def get_lug_project_perf_report(self, year=None, month=None):
        """Hiệu suất theo từng dự án; year/month rỗng → mọi thời gian."""
        Perm = self.env["lug.project.app.perm"]
        Perm.check("perf", "view")
        if year and month:
            year, month, start, end = self._lug_perf_period(year, month)
            period_label = "Tháng %02d/%s" % (month, year)
        else:
            year = month = start = end = False
            period_label = "Mọi thời gian"
        scoped = self
        if Perm.own_only("perf"):
            scoped = self.with_context(lug_perm_scope_uid=self.env.uid)
        projects = scoped.search(scoped._lug_base_domain(), order="name")
        empty = {"done": 0, "doing": 0, "todo": 0, "late": 0}
        proj_counts = {p.id: dict(empty) for p in projects}
        user_counts = defaultdict(lambda: defaultdict(lambda: dict(empty)))
        for pid, users, bucket in self._lug_perf_iter_tasks(projects.ids, start, end):
            proj_counts[pid][bucket] += 1
            for user in users or [False]:
                user_counts[pid][user.id if user else 0][bucket] += 1

        user_names = {u.id: u.name for u in self.env["res.users"].sudo().browse(
            [uid for per in user_counts.values() for uid in per if uid])}
        rows = []
        for proj in projects:
            c = proj_counts[proj.id]
            total = sum(c.values())
            members = []
            for uid, uc in user_counts[proj.id].items():
                utotal = sum(uc.values())
                members.append({
                    "id": uid,
                    "name": user_names.get(uid) or "Chưa giao",
                    "unassigned": not uid,
                    "total": utotal,
                    **uc,
                    "efficiency": self._lug_perf_eff(uc["done"], utotal),
                })
            members.sort(key=lambda m: (m["unassigned"], -m["total"], m["name"]))
            manager = proj.user_id or getattr(proj, "lug_pic_id", False)
            rows.append({
                "id": proj.id,
                "code": getattr(proj, "lug_code", False) or "",
                "name": proj.name or "",
                "manager_name": manager.name if manager else "",
                "total": total,
                **c,
                "efficiency": self._lug_perf_eff(c["done"], total),
                "members": members,
            })
        rows.sort(key=lambda r: (-r["total"], r["name"]))
        agg = {k: sum(r[k] for r in rows) for k in ("total", "done", "doing", "todo", "late")}
        return {
            "year": year,
            "month": month,
            "period_label": period_label,
            "rows": rows,
            "project_count": len(rows),
            "summary": {**agg, "efficiency": self._lug_perf_eff(agg["done"], agg["total"])},
        }

    @api.model
    def _lug_perf_eff(self, done, total):
        return round(done * 100.0 / total, 1) if total else 0

    @api.model
    def get_lug_perf_report(self, year=None, month=None):
        Perm = self.env["lug.project.app.perm"]
        Perm.check("people", "view")
        year, month, start, end = self._lug_perf_period(year, month)
        pmap = Perm.get_map()
        own_only = pmap["people"]["others"] is False
        scoped = self.with_context(lug_perm_scope_uid=self.env.uid) if own_only else self
        counts = scoped._lug_perf_task_counts(start, end)

        employees = self.env["hr.employee"].sudo().search(
            [("user_id", "!=", False), ("user_id.share", "=", False), ("active", "=", True)], order="name")
        if own_only:
            employees = employees.filtered(lambda e: e.user_id.id == self.env.uid)
        ratings = {
            rec.user_id.id: rec.percent
            for rec in self.env["lug.project.manager.perf"].sudo().search(
                [("year", "=", year), ("month", "=", month), ("user_id", "in", employees.user_id.ids)])
        }
        groups = {}
        seen_users = set()
        for emp in employees:
            user = emp.user_id
            if user.id in seen_users:
                continue
            seen_users.add(user.id)
            c = counts.get(user.id) or {"done": 0, "doing": 0, "todo": 0, "late": 0}
            total = sum(c.values())
            dept = emp.department_id
            key = str(dept.id) if dept else "0"
            group = groups.setdefault(key, {
                "key": key,
                "name": dept.display_name if dept else _NO_DEPT,
                "rows": [],
            })
            group["rows"].append({
                "id": user.id,
                "name": emp.name or user.name or "",
                "job": emp.job_title or (emp.job_id.name if emp.job_id else "") or "",
                "total": total,
                **c,
                "efficiency": self._lug_perf_eff(c["done"], total),
                "manager_perf": ratings.get(user.id),
                "can_rate": self._lug_perf_can_rate(user, pmap),
            })
        result = []
        for group in groups.values():
            rows = sorted(group["rows"], key=lambda r: (-r["total"], r["name"]))
            agg = {k: sum(r[k] for r in rows) for k in ("total", "done", "doing", "todo", "late")}
            result.append({
                **group,
                "rows": rows,
                "count": len(rows),
                **agg,
                "efficiency": self._lug_perf_eff(agg["done"], agg["total"]),
            })
        result.sort(key=lambda g: (g["key"] == "0", -g["total"], g["name"]))
        return {
            "year": year,
            "month": month,
            "period_label": "Tháng %02d/%s" % (month, year),
            "groups": result,
            "staff_count": len(seen_users),
        }

    @api.model
    def save_lug_manager_perf(self, year, month, values):
        """values: [{user_id, percent}] — percent rỗng → xoá (dùng hiệu suất tự tính)."""
        self.env["lug.project.app.perm"].check("people", "view")
        year, month, _start, _end = self._lug_perf_period(year, month)
        Rating = self.env["lug.project.manager.perf"].sudo()
        pmap = self.env["lug.project.app.perm"].get_map()
        for item in values or []:
            user = self.env["res.users"].sudo().browse(int(item.get("user_id") or 0)).exists()
            if not user:
                continue
            if not self._lug_perf_can_rate(user, pmap):
                raise AccessError("Bạn không có quyền chốt QL đánh giá tổng cho «%s»." % user.name)
            percent = item.get("percent")
            rec = Rating.search([("user_id", "=", user.id), ("year", "=", year), ("month", "=", month)], limit=1)
            if percent in (None, False, ""):
                rec.unlink()
                continue
            try:
                value = round(float(str(percent).replace(",", ".")), 1)
            except (TypeError, ValueError):
                raise ValidationError("% QL đánh giá tổng của «%s» không hợp lệ." % user.name)
            if value < 0 or value > 100:
                raise ValidationError("% QL đánh giá tổng phải từ 0 đến 100.")
            vals = {"percent": value, "set_by_id": self.env.uid, "set_date": fields.Datetime.now()}
            if rec:
                rec.write(vals)
            else:
                Rating.create(dict(vals, user_id=user.id, year=year, month=month))
        return self.get_lug_perf_report(year=year, month=month)
