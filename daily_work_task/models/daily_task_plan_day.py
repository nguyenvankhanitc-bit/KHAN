# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models

# Giới hạn số ngày quét cho 1 dòng (tránh dải ngày nhập sai kéo dài nhiều năm)
_MAX_SPAN_DAYS = 400


class DailyTaskPlanDay(models.Model):
    """Ô 'x' trên Plan công việc cho 1 người × 1 ngày, gắn với:

    - 1 dòng phân công (line_id) — plan team, hoặc
    - 1 việc cá nhân không thuộc dòng phân công (task_id) — việc tự nhập ở Nhập công việc.

    auto (manual=False): sinh từ dải Ngày bắt đầu → Deadline, tự làm lại khi đổi ngày.
    manual=True: nhân viên tự bấm bật/tắt ô — giữ nguyên khi dải ngày thay đổi.
    """

    _name = "daily.task.plan.day"
    _description = "Ngày kế hoạch (Plan công việc)"
    _order = "date, id"

    line_id = fields.Many2one(
        "daily.task.assign",
        string="Dòng phân công",
        index=True,
        ondelete="cascade",
    )
    task_id = fields.Many2one(
        "daily.task",
        string="Việc cá nhân",
        index=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Người phụ trách",
        required=True,
        index=True,
        ondelete="cascade",
    )
    date = fields.Date(string="Ngày", required=True, index=True)
    planned = fields.Boolean(string="Có kế hoạch (x)", default=True)
    manual = fields.Boolean(string="Nhập tay", default=False)

    _line_user_date_uniq = models.Constraint(
        "UNIQUE(line_id, user_id, date)",
        "Mỗi người chỉ có 1 ô kế hoạch cho 1 ngày của 1 dòng phân công.",
    )
    _task_date_uniq = models.Constraint(
        "UNIQUE(task_id, date)",
        "Mỗi việc cá nhân chỉ có 1 ô kế hoạch cho 1 ngày.",
    )
    _has_source = models.Constraint(
        "CHECK(line_id IS NOT NULL OR task_id IS NOT NULL)",
        "Ô kế hoạch phải gắn với dòng phân công hoặc việc cá nhân.",
    )

    @api.model
    def _dates_between(self, start, end, skip_sunday=False):
        """Dải ngày Ngày bắt đầu → Deadline (bỏ Chủ nhật nếu là việc lặp hằng ngày).

        Ngày hiện tại nằm trong dải thì tự có trong kết quả → cột hôm nay được đánh 'x'.
        """
        if not start and not end:
            return set()
        start, end = start or end, end or start
        if end < start:
            start, end = end, start
        end = min(end, start + timedelta(days=_MAX_SPAN_DAYS))
        dates, cur = set(), start
        while cur <= end:
            if not (skip_sunday and cur.weekday() == 6):
                dates.add(cur)
            cur += timedelta(days=1)
        return dates

    @api.model
    def _planned_dates(self, line):
        # Người dùng tự chọn Ngày kế hoạch Từ ngày → Đến ngày
        if line.plan_date_from or line.plan_date_to:
            return self._dates_between(line.plan_date_from, line.plan_date_to, skip_sunday=line.plan_daily)
        return self._dates_between(line.date_start, line.deadline, skip_sunday=line.plan_daily)

    @api.model
    def _resync(self, existing, wanted, base_vals):
        """Giữ ô nhập tay; bỏ ô tự động ngoài dải; thêm ô còn thiếu trong dải."""
        stale = existing.filtered(lambda d: not d.manual and d.date not in wanted)
        have = set((existing - stale).mapped("date"))
        stale.unlink()
        new_dates = sorted(wanted - have)
        if new_dates:
            self.sudo().create([{**base_vals, "date": d, "planned": True} for d in new_dates])

    @api.model
    def sync_lines(self, lines):
        """Làm lại các ô 'x' tự động theo dải ngày + người phụ trách hiện tại của từng dòng."""
        PlanDay = self.sudo()
        for line in lines.sudo():
            users = line._responsible_users() if line.active else self.env["res.users"]
            wanted = self._planned_dates(line)
            existing = PlanDay.search([("line_id", "=", line.id)])
            # Người không còn phụ trách → bỏ hết ô của họ
            existing.filtered(lambda d, u=users: d.user_id not in u).unlink()
            existing = existing.exists()
            for user in users:
                mine = existing.exists().filtered(lambda d, u=user: d.user_id == u)
                self._resync(mine, wanted, {"line_id": line.id, "user_id": user.id})

    @api.model
    def sync_tasks(self, tasks):
        """Ô 'x' cho mỗi việc cá nhân (kể cả việc gắn dòng phân công) — không áp dụng việc sinh từ mẫu lặp."""
        PlanDay = self.sudo()
        for task in tasks.sudo():
            existing = PlanDay.search([("task_id", "=", task.id)])
            user = task.assignee_user_id
            if task.recurring_id or not user:
                existing.unlink()
                continue
            existing.filtered(lambda d, u=user: d.user_id != u).unlink()
            wanted = self._dates_between(task.assign_date, task.deadline)
            self._resync(existing.exists(), wanted, {"task_id": task.id, "user_id": user.id})
