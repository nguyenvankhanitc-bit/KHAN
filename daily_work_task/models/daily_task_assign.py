# -*- coding: utf-8 -*-

import base64
import calendar
import io
import re
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_USER_DOMAIN = "[('share', '=', False), ('active', '=', True)]"

REGION_SELECTION = [
    ("south", "Miền Nam"),
    ("dtt", "Miền ĐTT"),
    ("north", "Miền Bắc"),
    ("vptt", "VPTT"),
    ("vpmb", "VPMB"),
]

STATE_SELECTION = [
    ("done", "Hoàn thành"),
    ("in_progress", "Đang thực hiện"),
    ("overdue", "Quá hạn"),
    ("not_started", "Chưa bắt đầu"),
]


class DailyTaskAssign(models.Model):
    """Phân công công việc — theo mẫu Danh sách phân công công việc."""

    _name = "daily.task.assign"
    _description = "Phân công công việc"
    _order = "stt, id"

    @api.model
    def _department_from_user(self, user=None):
        """Phòng ban trên hồ sơ hr.employee gắn với user."""
        user = user or self.env.user
        if not user:
            return False
        emp = getattr(user, "employee_id", False) or self.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)], limit=1
        )
        return emp.department_id if emp and emp.department_id else False

    @api.model
    def _default_department_from_user(self):
        return self._department_from_user()

    # Tần suất thực hiện: tích 1 ô Ngày / Tuần / Tháng (dùng cho Báo cáo công việc tháng)
    freq_day = fields.Boolean(string="Ngày")
    freq_week = fields.Boolean(string="Tuần")
    freq_month = fields.Boolean(string="Tháng")
    # Số ngày người dùng nhập — cột SỐ NGÀY của Báo cáo công việc tháng (để trống = tự đếm ngày hoàn thành)
    freq_days = fields.Integer(
        string="Số ngày",
        help="Số ngày thực hiện trong tháng — đưa vào cột SỐ NGÀY của Báo cáo công việc tháng "
             "(Thời gian thực hiện = phút/lần ÷ 60 × Số ngày). Để 0 = tự đếm số ngày đã hoàn thành.",
    )

    @api.onchange("freq_day")
    def _onchange_freq_day(self):
        if self.freq_day:
            self.freq_week = self.freq_month = False

    @api.onchange("freq_week")
    def _onchange_freq_week(self):
        if self.freq_week:
            self.freq_day = self.freq_month = False

    @api.onchange("freq_month")
    def _onchange_freq_month(self):
        if self.freq_month:
            self.freq_day = self.freq_week = False

    @api.model
    def _effective_frequencies(self, lines, first, last):
        """{line_id: 'day'|'week'|'month'} — ưu tiên: ô Tần suất đã tích → Lặp hằng ngày / mẫu lặp
        → số ngày làm thực tế trong tháng (≥15 ngày: Ngày; ≥3 tuần: Tuần; còn lại: Tháng)."""
        out = {}
        if not lines:
            return out
        rec_map = {}
        for tpl in self.env["daily.task.recurring"].sudo().search([("assign_line_id", "in", lines.ids)]):
            rec_map.setdefault(tpl.assign_line_id.id, tpl.recurrence_type or "daily")
        days_map = {}
        tasks = self.env["daily.task"].sudo().search([
            ("assign_line_id", "in", lines.ids),
            ("assign_date", ">=", first), ("assign_date", "<=", last),
        ])
        for t in tasks:
            days_map.setdefault(t.assign_line_id.id, set()).add(t.assign_date)
        for line in lines:
            key = line._frequency_key()
            if not key and line.plan_daily:
                key = "day"
            if not key and line.id in rec_map:
                key = {"daily": "day", "weekly": "week"}.get(rec_map[line.id], "month")
            if not key:
                days = days_map.get(line.id) or set()
                if len(days) >= 15:
                    key = "day"
                elif len({d.isocalendar()[:2] for d in days}) >= 3:
                    key = "week"
                else:
                    key = "month"
            out[line.id] = key
        return out

    def _frequency_key(self):
        """'day' / 'week' / 'month' hoặc False nếu chưa tích."""
        self.ensure_one()
        return "day" if self.freq_day else "week" if self.freq_week else "month" if self.freq_month else False

    dept_locked = fields.Boolean(
        compute="_compute_dept_locked",
        help="Phòng ban tự lấy theo user đăng nhập — chỉ Quản lý được đổi.",
    )

    @api.depends_context("uid")
    def _compute_dept_locked(self):
        locked = not self.env["daily.task.assign.access"]._is_manager()
        for rec in self:
            rec.dept_locked = locked

    stt = fields.Integer(string="STT", default=0, index=True, copy=False)
    sequence = fields.Integer(string="Thứ tự", default=10)
    name = fields.Char(string="Nội dung công việc", required=False, index=True)
    plan_source = fields.Selection(
        [("team", "Plan tổng / Phân công"), ("personal", "Cá nhân bổ sung")],
        string="Nguồn",
        default="team",
        index=True,
        help="Plan tổng / Phân công: cá nhân không sửa được nội dung (tên, ngày) đã áp xuống. "
        "Cá nhân bổ sung: người tạo tự cập nhật.",
    )
    work_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        required=False,
        index=True,
        ondelete="restrict",
    )
    # UI form: chọn Hạng mục (duy nhất) trước, rồi tick Tên công việc
    category_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        ondelete="set null",
        index=True,
        help="Chọn nhóm hạng mục (Camera, Email…). Không phải dòng công việc con.",
    )
    category_name = fields.Char(
        string="Tên hạng mục",
        related="category_group_id.name",
        store=True,
        readonly=True,
    )
    work_group_ids = fields.Many2many(
        "daily.task.work.group",
        "daily_task_assign_work_group_sel_rel",
        "assign_id",
        "work_group_id",
        string="Tên công việc",
        help="Chọn một hoặc nhiều tên công việc (checkbox). Lưu sẽ tạo từng dòng phân công.",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        index=True,
        default=lambda self: self._default_department_from_user(),
        help="Tự lấy từ hồ sơ nhân viên của user (đăng nhập / người phụ trách).",
    )
    team_id = fields.Many2one(
        related="work_group_id.team_id",
        string="Team",
        store=True,
        readonly=True,
    )
    region = fields.Selection(
        REGION_SELECTION,
        string="Khu vực",
        required=False,
        index=True,
    )
    south_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_south_user_rel",
        "assign_id",
        "user_id",
        string="Miền Nam",
        domain=_USER_DOMAIN,
    )
    dtt_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_dtt_user_rel",
        "assign_id",
        "user_id",
        string="Miền ĐTT",
        domain=_USER_DOMAIN,
    )
    north_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_north_user_rel",
        "assign_id",
        "user_id",
        string="Miền Bắc",
        domain=_USER_DOMAIN,
    )
    office_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_office_user_rel",
        "assign_id",
        "user_id",
        string="Văn phòng",
        domain=_USER_DOMAIN,
    )
    # Giữ boolean cũ (ẩn) — tương thích cột DB đã tạo
    is_south = fields.Boolean(string="Miền Nam (cũ)", default=False)
    is_dtt = fields.Boolean(string="Miền ĐTT (cũ)", default=False)
    is_north = fields.Boolean(string="Miền Bắc (cũ)", default=False)
    is_office = fields.Boolean(string="Văn phòng (cũ)", default=False)
    # UI chính: M2M tags (giống cột miền). M2O giữ để search/group_by.
    assignee_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_assignee_user_rel",
        "assign_id",
        "user_id",
        string="Người phụ trách",
        domain=_USER_DOMAIN,
    )
    detail_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_detail_user_rel",
        "assign_id",
        "user_id",
        string="User chi tiết",
        domain=_USER_DOMAIN,
    )
    check_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_check_user_rel",
        "assign_id",
        "user_id",
        string="User kiểm tra",
        domain=_USER_DOMAIN,
    )
    coord_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_coord_user_rel",
        "assign_id",
        "user_id",
        string="User phối hợp",
        domain=_USER_DOMAIN,
    )
    assignee_user_id = fields.Many2one(
        "res.users",
        string="Người phụ trách (chính)",
        domain=_USER_DOMAIN,
        index=True,
        ondelete="set null",
    )
    detail_user_id = fields.Many2one(
        "res.users",
        string="User chi tiết (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    check_user_id = fields.Many2one(
        "res.users",
        string="User kiểm tra (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    coord_user_id = fields.Many2one(
        "res.users",
        string="User phối hợp (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    participant_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_participant_rel",
        "assign_id",
        "user_id",
        string="Người tham gia",
        domain=_USER_DOMAIN,
    )
    participant_label = fields.Char(
        string="Người tham gia",
        compute="_compute_participant_label",
    )
    date_start = fields.Date(string="Bắt đầu", default=fields.Date.context_today)
    deadline = fields.Date(string="Deadline")
    state = fields.Selection(
        STATE_SELECTION,
        string="Trạng thái",
        default="not_started",
        required=True,
        index=True,
    )
    note = fields.Char(string="Ghi chú")
    active = fields.Boolean(default=True)
    plan_daily = fields.Boolean(
        string="Lặp hằng ngày",
        default=False,
        help="Plan làm mỗi ngày (trừ Chủ nhật) từ Bắt đầu đến Deadline: mỗi người phụ trách "
        "có 1 mẫu Công việc lặp, sinh việc vào Công việc hôm nay thay cho 1 việc cả kỳ.",
    )
    plan_day_ids = fields.One2many(
        "daily.task.plan.day",
        "line_id",
        string="Ô kế hoạch theo ngày",
    )
    plan_days_label = fields.Char(
        string="Ngày kế hoạch (x)",
        compute="_compute_plan_days_label",
        help="Xem trước các ngày được đánh 'x' theo Bắt đầu → Deadline (kể cả hôm nay nếu nằm trong dải).",
    )

    @api.depends("date_start", "deadline", "plan_daily")
    def _compute_plan_days_label(self):
        PlanDay = self.env["daily.task.plan.day"]
        today = fields.Date.context_today(self)
        for rec in self:
            dates = sorted(PlanDay._planned_dates(rec))
            if not dates:
                rec.plan_days_label = ""
                continue
            label = "%s → %s · %s ngày 'x'" % (
                dates[0].strftime("%d/%m/%Y"),
                dates[-1].strftime("%d/%m/%Y"),
                len(dates),
            )
            if today in dates:
                label += " · có hôm nay (%s)" % today.strftime("%d/%m")
            rec.plan_days_label = label

    @api.onchange("date_start", "deadline")
    def _onchange_plan_dates(self):
        """Deadline trước Bắt đầu → cảnh báo ngay trên form (dải 'x' xem ở plan_days_label)."""
        if self.date_start and self.deadline and self.deadline < self.date_start:
            return {
                "warning": {
                    "title": "Ngày chưa hợp lệ",
                    "message": "Deadline đang trước ngày Bắt đầu.",
                }
            }

    @api.depends("participant_ids")
    def _compute_participant_label(self):
        for rec in self:
            n = len(rec.participant_ids)
            rec.participant_label = ("%s người" % n) if n else "—"

    @staticmethod
    def _m2m_command_ids(commands):
        if not commands:
            return []
        # [(6, 0, ids)] phổ biến từ UI tags
        if isinstance(commands, (list, tuple)) and commands and commands[0][0] == 6:
            return list(commands[0][2] or [])
        return []

    def _sync_m2o_from_m2m_vals(self, vals):
        pairs = (
            ("assignee_user_ids", "assignee_user_id"),
            ("detail_user_ids", "detail_user_id"),
            ("check_user_ids", "check_user_id"),
            ("coord_user_ids", "coord_user_id"),
        )
        for m2m_name, m2o_name in pairs:
            if m2m_name in vals and m2o_name not in vals:
                ids = self._m2m_command_ids(vals.get(m2m_name))
                vals[m2o_name] = ids[0] if ids else False

    _REGION_USER_FIELDS = (
        "south_user_ids",
        "dtt_user_ids",
        "north_user_ids",
        "office_user_ids",
    )

    def _fill_assignee_from_regions(self):
        """User ở cột Miền / Văn phòng cũng là Người phụ trách (chỉ thêm, không xóa)."""
        for rec in self:
            region_users = rec.south_user_ids | rec.dtt_user_ids | rec.north_user_ids | rec.office_user_ids
            missing = region_users - rec.assignee_user_ids
            if not missing:
                continue
            vals = {"assignee_user_ids": [(4, uid) for uid in missing.ids]}
            if not rec.assignee_user_id:
                vals["assignee_user_id"] = (rec.assignee_user_ids | missing)[:1].id
            super(DailyTaskAssign, rec).write(vals)

    def _responsible_users(self):
        """User phụ trách chính (+ miền/VP nếu chưa chọn phụ trách)."""
        self.ensure_one()
        users = self.assignee_user_ids
        if users:
            return users
        return (
            self.south_user_ids
            | self.dtt_user_ids
            | self.north_user_ids
            | self.office_user_ids
        )

    def _sync_personal_daily_tasks(self):
        """Tạo/cập nhật công việc cá nhân từ dòng phân công → người phụ trách."""
        # Ô 'x' Plan công việc theo dải Bắt đầu → Deadline (luôn đồng bộ)
        self.env["daily.task.plan.day"].sync_lines(self)
        if self.env.context.get("skip_assign_personal_sync"):
            return
        Task = self.env["daily.task"].sudo().with_context(
            skip_work_group_user_check=True,
            from_daily_task_assign=True,
            mail_notrack=True,
            tracking_disable=True,
        )
        EmpBridge = self.env["daily.task.employee"].sudo()
        HrEmployee = self.env["hr.employee"].sudo()
        today = fields.Date.context_today(self)
        self._sync_plan_recurring()
        for rec in self:
            if rec.plan_daily:
                # Việc hằng ngày do Công việc lặp sinh — không tạo 1 việc cả kỳ
                continue
            users = rec._responsible_users()
            existing = Task.search([("assign_line_id", "=", rec.id), ("recurring_id", "=", False)])
            kept = Task.browse()
            for user in users:
                hr = HrEmployee.search([("user_id", "=", user.id)], limit=1)
                if not hr:
                    continue
                bridge = EmpBridge.get_or_create_from_hr(hr.id)
                # Ưu tiên phòng ban của hạng mục để khớp ràng buộc phòng ban
                wg = rec.work_group_id
                dept = (
                    wg.department_id.id
                    if wg and wg.department_id
                    else (
                        rec.department_id.id
                        if rec.department_id
                        else (hr.department_id.id if hr.department_id else False)
                    )
                )
                task_vals = {
                    "name": rec.name or (wg.task_name if wg else "") or "/",
                    "work_group_id": wg.id if wg else False,
                    "department_id": dept,
                    "assignee_id": bridge.id,
                    "assign_line_id": rec.id,
                    "assign_date": rec.date_start or today,
                    "deadline": rec.deadline or today,
                    "note": rec.note or "",
                    "assigned_by_id": self.env.uid,
                }
                task = existing.filtered(lambda t, b=bridge: t.assignee_id.id == b.id)[:1]
                if task:
                    update_vals = dict(task_vals)
                    if not rec.note:
                        # Không xóa ghi chú nhân viên tự nhập ở bảng cá nhân
                        update_vals.pop("note", None)
                    task.with_context(
                        skip_work_group_user_check=True,
                        from_daily_task_assign=True,
                    ).write(update_vals)
                    kept |= task
                else:
                    kept |= Task.create(
                        {
                            **task_vals,
                            "state": "not_started",
                            "priority": "medium",
                        }
                    )
            # Không xóa việc cá nhân cũ — chỉ tạo/cập nhật theo người phụ trách hiện tại

    def _sync_plan_recurring(self):
        """Dòng 'Lặp hằng ngày' → mỗi người phụ trách 1 mẫu Công việc lặp (trừ CN) trong kỳ plan."""
        Recurring = self.env["daily.task.recurring"].sudo().with_context(active_test=False)
        HrEmployee = self.env["hr.employee"].sudo()
        today = fields.Date.context_today(self)
        for rec in self:
            templates = Recurring.search([("assign_line_id", "=", rec.id)])
            kept = Recurring.browse()
            if rec.active and rec.plan_daily:
                wg = rec.work_group_id
                for user in rec._responsible_users():
                    emp = HrEmployee.search([("user_id", "=", user.id)], limit=1)
                    if not emp:
                        continue
                    dept = wg.department_id if wg and wg.department_id else emp.department_id
                    vals = {
                        "name": rec.name or (wg.task_name if wg else "") or "/",
                        "employee_id": emp.id,
                        "department_id": dept.id if dept else False,
                        "work_group_id": wg.id if wg else False,
                        "recurrence_type": "daily",
                        "skip_sunday": True,
                        "date_from": rec.date_start or False,
                        "date_to": rec.deadline or False,
                        "note": rec.note or "",
                        "active": True,
                    }
                    tpl = templates.filtered(lambda t, e=emp: t.employee_id == e)[:1]
                    if tpl:
                        tpl.write(vals)
                    else:
                        tpl = Recurring.create({
                            **vals,
                            "assign_line_id": rec.id,
                            "user_id": (rec.create_uid or self.env.user).id,
                        })
                    kept |= tpl
                    # Sinh luôn việc hôm nay (cron chỉ chạy 5h sáng)
                    tpl._generate_task_for_date(today)
            (templates - kept).filtered("active").write({"active": False})

    @api.constrains("work_group_id", "name", "date_start", "deadline", "active")
    def _check_duplicate_line(self):
        """Chống trùng: cùng hạng mục + cùng tên CV + thời gian chồng nhau → không cho tạo/sửa."""
        far_past, far_future = date(1900, 1, 1), date(9999, 12, 31)
        for rec in self:
            if not rec.active or not rec.work_group_id:
                continue
            key = " ".join((rec.name or "").split()).casefold()
            if not key:
                continue
            start = rec.date_start or far_past
            end = rec.deadline or far_future
            others = self.sudo().search([
                ("id", "!=", rec.id),
                ("active", "=", True),
                ("work_group_id", "=", rec.work_group_id.id),
            ])
            for other in others:
                if " ".join((other.name or "").split()).casefold() != key:
                    continue
                o_start = other.date_start or far_past
                o_end = other.deadline or far_future
                if start <= o_end and o_start <= end:
                    raise ValidationError(
                        "Trùng công việc: «%s» đã có trong hạng mục «%s» (STT %s, %s → %s).\n"
                        "Hãy thêm nhân sự vào dòng có sẵn, hoặc chọn thời gian không trùng."
                        % (
                            rec.name,
                            rec.work_group_id.name,
                            other.stt or other.id,
                            other.date_start.strftime("%d/%m/%Y") if other.date_start else "…",
                            other.deadline.strftime("%d/%m/%Y") if other.deadline else "…",
                        )
                    )

    def _expand_vals_by_work_groups(self, vals_list):
        """Nhiều tên CV (checkbox) → nhiều dòng phân công (1 dòng / 1 công việc)."""
        if self.env.context.get("skip_assign_expand"):
            return [dict(v) for v in vals_list]
        expanded = []
        for vals in vals_list:
            vals = dict(vals)
            wg_ids = self._m2m_command_ids(vals.pop("work_group_ids", None))
            if not wg_ids and vals.get("work_group_id"):
                wg_ids = [vals["work_group_id"]]
            if not wg_ids:
                raise ValidationError(
                    "Vui lòng chọn Hạng mục và tích ít nhất một Tên công việc."
                )
            first_wg = self.env["daily.task.work.group"].browse(wg_ids[:1])
            for wg_id in wg_ids:
                line = dict(vals)
                line["work_group_id"] = wg_id
                line["work_group_ids"] = [(6, 0, [wg_id])]
                wg = self.env["daily.task.work.group"].browse(wg_id)
                if wg.task_name:
                    line["name"] = wg.task_name
                elif not line.get("name"):
                    line["name"] = wg.name or "/"
                line.update(self._linked_user_vals(line, wg, first_wg))
                # Tránh trùng STT khi tách nhiều dòng từ 1 form
                if "stt" in line and len(wg_ids) > 1:
                    line.pop("stt", None)
                expanded.append(line)
        return expanded

    @api.model
    def _assign_access_feature(self):
        """Context từ board: 'add' | 'list' — mặc định chấp nhận nếu có quyền ở một trong hai."""
        return self.env.context.get("daily_work_assign_feature") or False

    @api.model
    def _check_assign_access(self, action):
        Access = self.env["daily.task.assign.access"]
        feature = self._assign_access_feature()
        if feature in ("add", "list"):
            Access.check(feature, action)
            return
        if Access.can("add", action) or Access.can("list", action):
            return
        Access.check("add", action)

    @api.model_create_multi
    def create(self, vals_list):
        self.env["daily.task"]._req_cache_clear()
        self._check_assign_access("create")
        vals_list = self._expand_vals_by_work_groups(vals_list)
        last = self.search([], order="stt desc", limit=1)
        next_stt = (last.stt or 0) + 1 if last else 1
        for vals in vals_list:
            if not vals.get("stt"):
                vals["stt"] = next_stt
                next_stt += 1
            # Lấy tên CV từ hạng mục cha nếu chưa nhập
            if not vals.get("name") and vals.get("work_group_id"):
                wg = self.env["daily.task.work.group"].browse(vals["work_group_id"])
                if wg.task_name:
                    vals["name"] = wg.task_name
            # Phòng ban: hồ sơ NV của người phụ trách → user tạo → hạng mục
            if not vals.get("department_id"):
                assignee_ids = self._m2m_command_ids(vals.get("assignee_user_ids"))
                if not assignee_ids and vals.get("assignee_user_id"):
                    assignee_ids = [vals["assignee_user_id"]]
                dept = False
                if assignee_ids:
                    dept = self._department_from_user(
                        self.env["res.users"].browse(assignee_ids[0])
                    )
                if not dept:
                    dept = self._department_from_user()
                if not dept and vals.get("work_group_id"):
                    wg = self.env["daily.task.work.group"].browse(vals["work_group_id"])
                    dept = wg.department_id
                if dept:
                    vals["department_id"] = dept.id
            self._sync_m2o_from_m2m_vals(vals)
            for m2m_name, m2o_name in (
                ("assignee_user_ids", "assignee_user_id"),
                ("detail_user_ids", "detail_user_id"),
                ("check_user_ids", "check_user_id"),
                ("coord_user_ids", "coord_user_id"),
            ):
                if m2m_name not in vals and vals.get(m2o_name):
                    vals[m2m_name] = [(6, 0, [vals[m2o_name]])]
        records = super().create(vals_list)
        # Giữ checkbox đã chọn khi mở lại form sửa — đúng 1 tên CV của dòng đó
        for rec in records:
            if rec.work_group_id:
                super(DailyTaskAssign, rec).write(
                    {"work_group_ids": [(6, 0, [rec.work_group_id.id])]}
                )
        records._fill_assignee_from_regions()
        records._sync_personal_daily_tasks()
        records._push_users_to_work_group()
        return records

    _USER_M2M_FIELDS = (
        "assignee_user_ids",
        "south_user_ids",
        "dtt_user_ids",
        "north_user_ids",
        "office_user_ids",
        "check_user_ids",
        "detail_user_ids",
        "coord_user_ids",
        "participant_ids",
    )

    def _merge_m2m_ids(self, existing_ids, commands):
        """Gộp id hiện có với lệnh M2M từ form (ưu tiên union)."""
        new_ids = self._m2m_command_ids(commands)
        if commands is None:
            return list(existing_ids)
        # [(6, 0, ids)] thay thế → vẫn union để không mất user khác trên dòng sẵn có
        return list({int(x) for x in (existing_ids or [])} | {int(x) for x in (new_ids or [])})

    def _apply_users_to_work_groups(self, wg_ids, user_vals):
        """Gắn user (Miền Nam / phụ trách…) lên từng tên CV đã tích — tìm dòng sẵn hoặc tạo mới."""
        self.ensure_one()
        touched = self.browse()
        first = True
        for wg_id in wg_ids:
            wg = self.env["daily.task.work.group"].browse(wg_id)
            if not wg.exists():
                continue
            if first:
                target = self
                first = False
            else:
                target = self.search(
                    [("work_group_id", "=", wg_id), ("active", "=", True)],
                    limit=1,
                )
            payload = {
                "work_group_id": wg_id,
                "name": wg.task_name or wg.name or "/",
                "work_group_ids": [(6, 0, [wg_id])],
            }
            if self.department_id:
                payload["department_id"] = self.department_id.id
            elif wg.department_id:
                payload["department_id"] = wg.department_id.id
            if self.category_group_id:
                payload["category_group_id"] = self.category_group_id.id
            for fname in self._USER_M2M_FIELDS:
                if fname in user_vals:
                    if target:
                        merged = self._merge_m2m_ids(target[fname].ids, user_vals[fname])
                    else:
                        merged = self._m2m_command_ids(user_vals[fname])
                    payload[fname] = [(6, 0, merged)]
            if target:
                super(DailyTaskAssign, target).write(payload)
                touched |= target
            else:
                create_vals = dict(payload)
                # stt để trống → create tự tăng
                create_vals.pop("stt", None)
                touched |= self.with_context(
                    skip_assign_expand=True,
                    skip_assign_personal_sync=True,
                ).create([create_vals])
        return touched

    def write(self, vals):
        self.env["daily.task"]._req_cache_clear()
        self._check_assign_access("write")
        vals = dict(vals)
        self._sync_m2o_from_m2m_vals(vals)

        # Form tích nhiều tên CV → áp user lên từng dòng phân công tương ứng
        if "work_group_ids" in vals and len(self) == 1:
            wg_ids = self._m2m_command_ids(vals.get("work_group_ids"))
            if len(wg_ids) > 1 or (
                wg_ids
                and any(f in vals for f in self._USER_M2M_FIELDS)
            ):
                user_vals = {f: vals[f] for f in self._USER_M2M_FIELDS if f in vals}
                # Nếu form không gửi lại user fields, lấy từ record hiện tại
                for f in self._USER_M2M_FIELDS:
                    if f not in user_vals and self[f]:
                        user_vals[f] = [(6, 0, self[f].ids)]
                other_vals = {
                    k: v
                    for k, v in vals.items()
                    if k not in ("work_group_ids", "work_group_id")
                    and k not in self._USER_M2M_FIELDS
                }
                if other_vals:
                    super().write(other_vals)
                touched = self._apply_users_to_work_groups(wg_ids or self.work_group_id.ids, user_vals)
                touched._fill_assignee_from_regions()
                touched._push_users_to_work_group()
                touched._sync_personal_daily_tasks()
                return True

        res = super().write(vals)
        if set(vals) & set(self._REGION_USER_FIELDS):
            self._fill_assignee_from_regions()
        if not self.env.context.get("skip_link_users") and set(vals) & {
            "assignee_user_ids",
            "check_user_ids",
            "south_user_ids",
            "dtt_user_ids",
            "north_user_ids",
            "work_group_id",
        }:
            self._push_users_to_work_group()
        sync_fields = {
            "name",
            "work_group_id",
            "work_group_ids",
            "assignee_user_ids",
            "south_user_ids",
            "dtt_user_ids",
            "north_user_ids",
            "office_user_ids",
            "date_start",
            "deadline",
            "note",
            "plan_daily",
        }
        if sync_fields & set(vals):
            self._sync_personal_daily_tasks()
        elif "active" in vals:
            self._sync_plan_recurring()
            self.env["daily.task.plan.day"].sync_lines(self)
        return res

    _LINK_USER_FIELDS = (
        ("assignee_user_ids", "assignee_user_ids"),
        ("check_user_ids", "checker_user_ids"),
        ("south_user_ids", "south_user_ids"),
        ("dtt_user_ids", "dtt_user_ids"),
        ("north_user_ids", "north_user_ids"),
    )

    def _push_users_to_work_group(self):
        """User trên dòng phân công được gắn sang đúng hạng mục (không xóa user sẵn có)."""
        if self.env.context.get("skip_link_users"):
            return
        for rec in self:
            wg = rec.work_group_id
            if not wg:
                continue
            vals = {}
            for assign_field, wg_field in self._LINK_USER_FIELDS:
                missing = [
                    user_id
                    for user_id in rec[assign_field].ids
                    if user_id not in wg[wg_field].ids
                ]
                if missing:
                    vals[wg_field] = [(4, user_id) for user_id in missing]
            if vals:
                wg.sudo().with_context(skip_link_users=True).write(vals)

    def unlink(self):
        self.env["daily.task"]._req_cache_clear()
        self._check_assign_access("unlink")
        return super().unlink()

    def _migrate_m2o_into_m2m(self):
        """Đổ user M2O cũ sang cột tags M2M (một lần khi upgrade)."""
        for rec in self:
            updates = {}
            if rec.assignee_user_id and not rec.assignee_user_ids:
                updates["assignee_user_ids"] = [(6, 0, rec.assignee_user_id.ids)]
            if rec.detail_user_id and not rec.detail_user_ids:
                updates["detail_user_ids"] = [(6, 0, rec.detail_user_id.ids)]
            if rec.check_user_id and not rec.check_user_ids:
                updates["check_user_ids"] = [(6, 0, rec.check_user_id.ids)]
            if rec.coord_user_id and not rec.coord_user_ids:
                updates["coord_user_ids"] = [(6, 0, rec.coord_user_id.ids)]
            if updates:
                super(DailyTaskAssign, rec).write(updates)

    @api.onchange("assignee_user_ids")
    def _onchange_assignee_user_ids(self):
        """Đồng bộ M2O. Phòng ban giữ theo user đăng nhập (không đổi theo người phụ trách)."""
        self.assignee_user_id = self.assignee_user_ids[:1]

    def _work_group_task_domain(self):
        self.ensure_one()
        domain = [("active", "=", True)]
        if self.department_id:
            domain.append(("department_id", "=", self.department_id.id))
        cat_name = (self.category_name or "").strip()
        if not cat_name and self.category_group_id:
            cat_name = (self.category_group_id.name or "").strip()
        if cat_name:
            domain.append(("name", "=ilike", cat_name))
        else:
            domain.append(("id", "=", False))
        return domain

    @api.onchange("department_id")
    def _onchange_department_id(self):
        """Lọc hạng mục theo phòng ban hồ sơ NV."""
        if (
            self.category_group_id
            and self.department_id
            and self.category_group_id.department_id
            and self.category_group_id.department_id != self.department_id
        ):
            self.category_group_id = False
            self.work_group_ids = False
            self.work_group_id = False
            self.name = False
        return {
            "domain": {
                "category_group_id": (
                    [("department_id", "=", self.department_id.id)]
                    if self.department_id
                    else [("active", "=", True)]
                ),
                "work_group_ids": self._work_group_task_domain(),
            }
        }

    @api.onchange("category_group_id")
    def _onchange_category_group_id(self):
        """Chọn Hạng mục → hiện checkbox Tên công việc cùng nhóm."""
        self.work_group_ids = [(5, 0, 0)]
        self.work_group_id = False
        self.name = False
        return {"domain": {"work_group_ids": self._work_group_task_domain()}}

    @api.onchange("work_group_ids")
    def _onchange_work_group_ids(self):
        """Tick tên CV → đồng bộ work_group_id / name + gợi ý user."""
        groups = self.work_group_ids
        first = groups[:1]
        self.work_group_id = first
        if first:
            if not self.category_group_id:
                self.category_group_id = first
            if first.task_name:
                self.name = first.task_name
            return self._apply_work_group_user_defaults(first)
        self.name = False

    def _linked_user_vals(self, line, wg, first_wg):
        """Không tự lấy user từ dòng hạng mục — user do người phân công chọn trên form
        (tích tên CV không được kéo theo toàn bộ user của hạng mục)."""
        if not wg or not self.env.context.get("assign_take_work_group_users"):
            return {}
        linked = {}

        def _keep_or_take(field, form_ids, default_ids, take_ids):
            form_ids = list(form_ids or [])
            default_ids = list(default_ids or [])
            take_ids = list(take_ids or [])
            if form_ids and set(form_ids) != set(default_ids):
                return
            if take_ids:
                linked[field] = [(6, 0, take_ids)]

        _keep_or_take(
            "assignee_user_ids",
            self._m2m_command_ids(line.get("assignee_user_ids")),
            first_wg.assignee_user_ids.ids,
            wg.assignee_user_ids.ids,
        )
        if linked.get("assignee_user_ids"):
            linked["assignee_user_id"] = wg.assignee_user_ids[:1].id
        _keep_or_take(
            "south_user_ids",
            self._m2m_command_ids(line.get("south_user_ids")),
            first_wg.south_user_ids.ids,
            wg.south_user_ids.ids,
        )
        _keep_or_take(
            "dtt_user_ids",
            self._m2m_command_ids(line.get("dtt_user_ids")),
            first_wg.dtt_user_ids.ids,
            wg.dtt_user_ids.ids,
        )
        _keep_or_take(
            "north_user_ids",
            self._m2m_command_ids(line.get("north_user_ids")),
            first_wg.north_user_ids.ids,
            wg.north_user_ids.ids,
        )
        office_take = (wg.vptt_user_ids | wg.vpmb_user_ids).ids
        office_default = (first_wg.vptt_user_ids | first_wg.vpmb_user_ids).ids
        _keep_or_take(
            "office_user_ids",
            self._m2m_command_ids(line.get("office_user_ids")),
            office_default,
            office_take,
        )
        check_take = wg.checker_user_ids.ids
        check_default = first_wg.checker_user_ids.ids
        _keep_or_take(
            "check_user_ids",
            self._m2m_command_ids(line.get("check_user_ids")),
            check_default,
            check_take,
        )
        if linked.get("check_user_ids"):
            linked["check_user_id"] = check_take[0]
        return linked

    def _apply_work_group_user_defaults(self, wg):
        """Tích tên CV: KHÔNG tự điền Người phụ trách / Miền / Văn phòng / User chi tiết từ hạng mục
        (người phân công tự chọn). Chỉ gợi ý Phòng ban và User kiểm tra = User quản lý hạng mục / team."""
        if not wg:
            return
        if not self.department_id and wg.department_id:
            self.department_id = wg.department_id
        if not self.check_user_ids:
            managers = wg._category_managers() or wg.sudo().team_id.manager_ids
            if managers:
                self.check_user_ids = managers
                self.check_user_id = managers[:1]
        users = wg.applicable_users()
        domain = (
            [("id", "in", users.ids)]
            if users
            else [("share", "=", False), ("active", "=", True)]
        )
        return {
            "domain": {
                "assignee_user_ids": domain,
                "detail_user_ids": domain,
                "check_user_ids": domain,
                "coord_user_ids": domain,
                "participant_ids": domain,
                "south_user_ids": domain,
                "dtt_user_ids": domain,
                "north_user_ids": domain,
                "office_user_ids": domain,
            }
        }

    @api.onchange(
        "assignee_user_ids",
        "detail_user_ids",
        "check_user_ids",
        "coord_user_ids",
    )
    def _onchange_role_users_sync_m2o(self):
        """Đồng bộ M2O chính từ tags — hai cột phụ trách/chi tiết độc lập."""
        self.assignee_user_id = self.assignee_user_ids[:1]
        self.detail_user_id = self.detail_user_ids[:1]
        self.check_user_id = self.check_user_ids[:1]
        self.coord_user_id = self.coord_user_ids[:1]

    @api.onchange("work_group_id")
    def _onchange_work_group_id(self):
        """Chọn Tên công việc (dòng hạng mục) → điền nội dung + user."""
        wg = self.work_group_id
        if not wg:
            return
        if not self.category_group_id:
            self.category_group_id = wg
        # Ưu tiên phòng ban NV; nếu chưa có thì lấy từ hạng mục
        if not self.department_id and wg.department_id:
            self.department_id = wg.department_id
        if wg.task_name:
            self.name = wg.task_name
        return self._apply_work_group_user_defaults(wg)

    @api.onchange("region", "work_group_id")
    def _onchange_region(self):
        self._suggest_assignee_from_region()

    def _suggest_assignee_from_region(self):
        wg = self.work_group_id
        if not wg or not self.region:
            return
        field_map = {
            "south": "south_user_ids",
            "dtt": "dtt_user_ids",
            "north": "north_user_ids",
            "vptt": "vptt_user_ids",
            "vpmb": "vpmb_user_ids",
        }
        users = getattr(wg, field_map.get(self.region), self.env["res.users"])
        if users and not self.assignee_user_ids:
            self.assignee_user_ids = users[:1]
            self.assignee_user_id = users[:1]

    # ------------------------------------------------------------------
    # Bảng phân công team (client action — chỉ xem)
    # ------------------------------------------------------------------

    @api.model
    def _roman(self, n):
        vals = (
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        )
        out = []
        for value, numeral in vals:
            while n >= value:
                out.append(numeral)
                n -= value
        return "".join(out) or "I"

    @api.model
    def _users_payload(self, users):
        return [{"id": u.id, "name": u.name or ""} for u in users]

    @api.model
    def _assignees_for_row(self, rec):
        """Người phụ trách: dòng phân công cộng User phụ trách người dùng chọn trên hạng mục."""
        assignees = rec.assignee_user_ids
        if rec.assignee_user_id and rec.assignee_user_id not in assignees:
            assignees |= rec.assignee_user_id
        wg = rec.work_group_id
        if wg and wg.assignee_user_ids:
            assignees |= wg.assignee_user_ids
        return assignees

    @api.model
    def _checkers_for_row(self, rec):
        """User kiểm tra: cột trên dòng phân công cộng User kiểm tra trên hạng mục."""
        checkers = rec.check_user_ids
        if rec.check_user_id and rec.check_user_id not in checkers:
            checkers |= rec.check_user_id
        wg = rec.work_group_id
        if wg and wg.checker_user_ids:
            checkers |= wg.checker_user_ids
        return checkers

    @api.model
    def _assign_row_matches(self, rec, needle):
        if not needle:
            return True
        blobs = [
            rec.name or "",
            rec.note or "",
            rec.work_group_id.display_name or "",
            " ".join(rec.south_user_ids.mapped("name")),
            " ".join(rec.dtt_user_ids.mapped("name")),
            " ".join(rec.north_user_ids.mapped("name")),
            " ".join(rec.office_user_ids.mapped("name")),
            " ".join(rec.assignee_user_ids.mapped("name")),
            " ".join(rec.check_user_ids.mapped("name")),
            " ".join(rec.coord_user_ids.mapped("name")),
            " ".join(rec.participant_ids.mapped("name")),
        ]
        return needle in " ".join(blobs).lower()

    @api.model
    def get_assign_board_data(self, search=""):
        """Dữ liệu bảng phân công — nhóm theo hạng mục lớn (I. CAMERA → 1.1, 1.2…)."""
        needle = (search or "").strip().lower()
        WorkGroup = self.env["daily.task.work.group"]
        records = self.search([], order="stt, id")
        records.mapped("work_group_id").mapped("display_stt")
        # Sắp theo thứ tự hạng mục (sequence) rồi STT phân công
        records = records.sorted(
            key=lambda r: (
                int(r.work_group_id.sequence or 0) if r.work_group_id else 10**9,
                int(r.stt or 0),
                r.id,
            )
        )
        groups_map = {}
        group_order = []


        for rec in records:
            if not self._assign_row_matches(rec, needle):
                continue
            wg = rec.work_group_id
            cat = WorkGroup._norm_category_name(wg.name) if wg else "Khác"
            dept = wg.department_id.display_name if wg and wg.department_id else ""
            dept_id = wg.department_id.id if wg and wg.department_id else 0
            gkey = (dept_id, cat.casefold())
            if gkey not in groups_map:
                groups_map[gkey] = {
                    "id": "%s-%s" % (dept_id, cat.casefold()),
                    "name": cat,
                    "department": dept,
                    "tasks": [],
                }
                group_order.append(gkey)
            collab = rec.coord_user_ids | rec.participant_ids
            assignees = self._assignees_for_row(rec)
            checkers = self._checkers_for_row(rec)
            groups_map[gkey]["tasks"].append({
                "id": rec.id,
                "stt": rec.stt,
                "wg_stt": wg.display_stt if wg else "",
                "name": rec.name or "",
                "category": cat,
                "note": rec.note or "",
                # Tần suất = đúng ô người dùng tích trên Thêm phân công (không tích → để trống)
                "freq": rec._frequency_key() or "",
                "south": self._users_payload(rec.south_user_ids),
                "dtt": self._users_payload(rec.dtt_user_ids),
                "north": self._users_payload(rec.north_user_ids),
                "office": self._users_payload(rec.office_user_ids),
                # Người phụ trách: chỉ người chưa nằm ở cột Miền Nam / ĐTT / Bắc / Văn phòng (tránh trùng)
                "assignee": self._users_payload(
                    assignees - (rec.south_user_ids | rec.dtt_user_ids | rec.north_user_ids | rec.office_user_ids)
                ),
                "checker": self._users_payload(checkers),
                "collab": self._users_payload(collab),
            })

        sections = []
        for idx, gkey in enumerate(group_order, start=1):
            g = groups_map[gkey]
            title = "%s. %s" % (self._roman(idx), (g["name"] or "").upper())
            if g.get("department"):
                title = "%s (%s)" % (title, g["department"].upper())
            tasks = []
            for t_idx, task in enumerate(g["tasks"], start=1):
                tasks.append({
                    **task,
                    "display_stt": task.get("wg_stt") or "%s.%s" % (idx, t_idx),
                })
            sections.append({
                "id": g["id"],
                "code": self._roman(idx),
                "title": title,
                "tone": "alt" if idx % 3 == 0 else "default",
                "tasks": tasks,
            })

        today = fields.Date.context_today(self)
        Access = self.env["daily.task.assign.access"]
        feature = self._assign_access_feature() or "list"
        if feature not in ("add", "list"):
            feature = "list"
        Access.check(feature, "view")
        access = Access.get_access_map().get(feature) or {}
        return {
            "month": today.month,
            "year": today.year,
            "month_label": "Tháng %s / Năm %s" % (today.month, today.year),
            "readonly": True,
            "sections": sections,
            "task_count": sum(len(s["tasks"]) for s in sections),
            "access": {
                "view": bool(access.get("view")),
                "create": bool(access.get("create")),
                "write": bool(access.get("write")),
                "unlink": bool(access.get("unlink")),
            },
            "feature": feature,
        }

    @api.model
    def export_assign_board_excel(self, search=""):
        """Xuất Excel bảng phân công team."""
        try:
            import xlsxwriter
        except ImportError as err:
            raise UserError(
                "Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter"
            ) from err

        data = self.get_assign_board_data(search=search)
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Phân công")

        title_fmt = wb.add_format({
            "bold": True, "font_size": 14, "font_color": "#0f172a",
        })
        sub_fmt = wb.add_format({"font_size": 11, "font_color": "#64748b"})
        head_fmt = wb.add_format({
            "bold": True, "font_color": "#ffffff", "bg_color": "#1c2d42",
            "align": "center", "valign": "vcenter", "border": 1,
        })
        section_fmt = wb.add_format({
            "bold": True, "bg_color": "#dbe4ee", "border": 1,
        })
        cell_fmt = wb.add_format({"border": 1, "valign": "vcenter"})
        center_fmt = wb.add_format({
            "border": 1, "align": "center", "valign": "vcenter",
        })

        headers = [
            "STT",
            "Tên công việc / Hạng mục",
            "Ngày",
            "Tuần",
            "Tháng",
            "Miền Nam",
            "Miền ĐTT",
            "Miền Bắc",
            "Văn phòng",
            "Người phụ trách",
            "User kiểm tra",
            "User tham gia / phối hợp",
            "Ghi chú",
        ]
        widths = [8, 48, 7, 7, 7, 18, 18, 18, 16, 18, 18, 24, 16]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)

        ws.merge_range(0, 0, 0, 12, "BẢNG PHÂN CÔNG CÔNG VIỆC TEAM", title_fmt)
        ws.merge_range(1, 0, 1, 12, data.get("month_label") or "", sub_fmt)
        ws.merge_range(2, 0, 2, 12, "Chế độ: Chỉ xem", sub_fmt)

        row = 4
        for col, h in enumerate(headers):
            ws.write(row, col, h, head_fmt)
        row += 1

        def names(users):
            return ", ".join(u["name"] for u in (users or []) if u.get("name")) or "—"

        for section in data.get("sections") or []:
            ws.merge_range(row, 0, row, 12, section.get("title") or "", section_fmt)
            row += 1
            for task in section.get("tasks") or []:
                label = "%s — %s" % (task.get("category") or "", task.get("name") or "")
                ws.write(row, 0, task.get("display_stt") or "", center_fmt)
                ws.write(row, 1, label, cell_fmt)
                for i, key in enumerate(("day", "week", "month")):
                    ws.write(row, 2 + i, "X" if task.get("freq") == key else "", center_fmt)
                ws.write(row, 5, names(task.get("south")), cell_fmt)
                ws.write(row, 6, names(task.get("dtt")), cell_fmt)
                ws.write(row, 7, names(task.get("north")), cell_fmt)
                ws.write(row, 8, names(task.get("office")), cell_fmt)
                ws.write(row, 9, names(task.get("assignee")), cell_fmt)
                ws.write(row, 10, names(task.get("checker")), cell_fmt)
                ws.write(row, 11, names(task.get("collab")), cell_fmt)
                ws.write(row, 12, task.get("note") or "—", cell_fmt)
                row += 1

        wb.close()
        raw = buffer.getvalue()
        month = data.get("month") or 1
        year = data.get("year") or fields.Date.context_today(self).year
        filename = "Bang_Phan_Cong_Cong_Viec_Thang_%s_%s.xlsx" % (month, year)
        return {
            "file_base64": base64.b64encode(raw).decode("ascii"),
            "filename": filename,
        }

    @api.model
    def get_personnel_work_data(self):
        """Tách bảng phân công team thành công việc theo từng nhân sự (chỉ đọc).

        Không ghi dữ liệu mới. Người phụ trách / người kiểm tra mỗi người một dòng.
        """
        Access = self.env["daily.task.assign.access"]
        Access.check("personnel", "view")
        only_self = not Access._is_manager()
        current_uid = self.env.uid
        board = self.with_context(
            daily_work_assign_feature="list"
        ).get_assign_board_data(search="")
        task_ids = []
        for section in board.get("sections") or []:
            for task in section.get("tasks") or []:
                if task.get("id"):
                    task_ids.append(task["id"])
        records = {rec.id: rec for rec in self.browse(task_ids)}
        seen = set()
        people = {}
        people_order = []
        area_cols = (
            ("south", "Miền Nam"),
            ("dtt", "Miền ĐTT"),
            ("north", "Miền Bắc"),
            ("office", "Văn phòng"),
        )

        def _area(task, user_id, role_key):
            own = []
            for key, label in area_cols:
                people_in_col = task.get(key) or []
                if any(u.get("id") == user_id for u in people_in_col):
                    own.append(label)
            if own:
                return ", ".join(own)
            # User phụ trách / User kiểm tra lấy từ hạng mục, không gom mọi miền.
            if role_key in ("assignee", "checker"):
                return ""
            on_row = [
                label
                for key, label in area_cols
                if task.get(key)
            ]
            return ", ".join(on_row)

        def _push(user, role_key, role_label, section, task, rec):
            user_id = user.get("id") if isinstance(user, dict) else user.id
            user_name = user.get("name") if isinstance(user, dict) else user.name
            if not user_id:
                return
            if only_self and user_id != current_uid:
                return
            key = (user_id, rec.id, role_key)
            if key in seen:
                return
            seen.add(key)
            if user_id not in people:
                people[user_id] = {
                    "id": user_id,
                    "name": user_name or "",
                    "categories": {},
                    "category_order": [],
                }
                people_order.append(user_id)
            bucket = people[user_id]
            cat_id = section.get("id") or "0"
            if cat_id not in bucket["categories"]:
                cat_name = (task.get("category") or "Khác").upper()
                bucket["categories"][cat_id] = {
                    "id": cat_id,
                    "title": "HẠNG MỤC %s. %s" % (section.get("code") or "", cat_name),
                    "lines": [],
                }
                bucket["category_order"].append(cat_id)
            dept = rec.work_group_id.department_id or rec.department_id
            team = rec.team_id
            checker_names = ", ".join(
                u.get("name") for u in (task.get("checker") or []) if u.get("name")
            )
            bucket["categories"][cat_id]["lines"].append({
                "assign_id": rec.id,
                "code": task.get("display_stt") or "",
                "name": task.get("name") or "",
                "region": _area(task, user_id, role_key),
                "region_key": rec.region or "",
                "role": role_label,
                "role_key": role_key,
                "user_id": user_id,
                "user_name": user_name or "",
                "task_checker_name": checker_names,
                "category_id": cat_id,
                "category": task.get("category") or "",
                "department_id": dept.id if dept else 0,
                "department": dept.display_name if dept else "",
                "team_id": team.id if team else 0,
                "team": team.display_name if team else "",
            })

        for section in board.get("sections") or []:
            for task in section.get("tasks") or []:
                rec = records.get(task.get("id"))
                if not rec:
                    continue
                for user in task.get("assignee") or []:
                    _push(user, "assignee", "Người phụ trách", section, task, rec)
                for key, _label in area_cols:
                    for user in task.get(key) or []:
                        _push(user, "assignee", "Người phụ trách", section, task, rec)
                for user in task.get("checker") or []:
                    _push(user, "checker", "User kiểm tra", section, task, rec)

        people_order.sort(key=lambda uid: (people[uid]["name"] or "").casefold())
        payload_people = []
        departments = {}
        teams = {}
        categories = {}
        regions = {}
        users = []
        for uid in people_order:
            person = people[uid]
            cats = []
            total = 0
            for cat_id in person["category_order"]:
                cat = person["categories"][cat_id]
                total += len(cat["lines"])
                cats.append({
                    "id": cat["id"],
                    "title": cat["title"],
                    "count": len(cat["lines"]),
                    "lines": cat["lines"],
                })
                categories[cat_id] = cat["title"]
                for line in cat["lines"]:
                    if line["department_id"]:
                        departments[line["department_id"]] = line["department"]
                    if line["team_id"]:
                        teams[line["team_id"]] = line["team"]
                    if line["region"]:
                        regions[line["region"]] = line["region"]
            payload_people.append({
                "id": person["id"],
                "name": person["name"],
                "count": total,
                "categories": cats,
            })
            users.append({"id": person["id"], "name": person["name"]})

        def _opt(mapping):
            return [
                {"id": key, "name": mapping[key]}
                for key in sorted(mapping, key=lambda k: (mapping[k] or "").casefold())
            ]

        return {
            "people": payload_people,
            "filters": {
                "departments": _opt(departments),
                "teams": _opt(teams),
                "users": users,
                "categories": _opt(categories),
                "regions": _opt(regions),
                "roles": [
                    {"id": "assignee", "name": "Người phụ trách"},
                    {"id": "checker", "name": "User kiểm tra"},
                ],
            },
        }

    # ------------------------------------------------------------------
    # Plan công việc theo ngày (mục CÔNG VIỆC → Plan công việc)
    # ------------------------------------------------------------------
    _PLAN_WEEKDAYS = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")

    @api.model
    def get_my_plan_data(self, year=None, month=None, user_id=None):
        """Plan theo ngày của 1 user (mặc định user đăng nhập), lấy từ bảng phân công.

        Ô ngày: kế hoạch (từ Bắt đầu → Deadline, việc lặp bỏ Chủ nhật), đã hoàn thành
        (việc cá nhân gắn dòng phân công đã xong), bỏ lỡ (việc lặp quá ngày chưa xong).
        """
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        if not 1 <= month <= 12:
            raise UserError("Tháng không hợp lệ.")
        is_manager = self.env["daily.task.assign.access"]._is_manager()
        user = self.env.user
        if user_id and int(user_id) != user.id:
            if not is_manager:
                raise UserError("Bạn chỉ xem được plan của chính mình.")
            user = self.env["res.users"].sudo().browse(int(user_id)).exists() or user

        n_days = calendar.monthrange(year, month)[1]
        first, last = date(year, month, 1), date(year, month, n_days)
        Assign = self.sudo()
        Task = self.env["daily.task"].sudo()
        PlanDay = self.env["daily.task.plan.day"].sudo()
        emp = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
        # Dòng Plan = đúng tập việc của tab "Danh sách công việc" (bảng cá nhân) trong tháng:
        # Deadline trong tháng HOẶC Ngày bắt đầu trong tháng
        my_tasks = Task.browse()
        if emp:
            my_tasks = Task.search(
                Task._monthly_task_domain(emp.id, first, last),
                order="assign_date, deadline, id",
            )
        single_tasks = my_tasks.filtered(lambda t: not t.recurring_id)
        recurring_tasks = my_tasks - single_tasks

        days = []
        for d in range(1, n_days + 1):
            day = date(year, month, d)
            days.append({
                "day": d,
                "wd": self._PLAN_WEEKDAYS[day.weekday()],
                "saturday": day.weekday() == 5,
                "sunday": day.weekday() == 6,
                "today": day == today,
            })

        month_domain = [("date", ">=", first), ("date", "<=", last), ("planned", "=", True)]
        task_days = PlanDay.search(month_domain + [("task_id", "in", single_tasks.ids)])
        own_view = user == self.env.user
        is_self_or_manager = own_view or is_manager
        groups, group_index = [], {}
        totals = {"planned": 0, "done": 0}
        # Đếm việc theo trạng thái (giống bảng cá nhân) — việc lặp đếm từng việc sinh trong tháng
        status_count = {"done": 0, "in_progress": 0, "not_started": 0, "overdue": 0}

        def task_state(task):
            """Trạng thái đúng như thẻ ở bảng cá nhân: Đã hoàn thành / Quá hạn / Đang xử lý / Chưa bắt đầu."""
            if not task:
                return "not_started"
            if task.state == "done":
                return "done"
            if task.deadline and task.deadline < today:
                return "overdue"
            return task.state or "not_started"

        def build_cells(planned, row_state="not_started", day_states=None):
            """Ô 'x' tô màu theo trạng thái việc cá nhân (cả dòng, hoặc từng ngày với việc lặp)."""
            cells = []
            for info in days:
                d = info["day"]
                cls = []
                if d in planned:
                    cls.append("is-plan")
                    st = (day_states or {}).get(d, "not_started") if day_states is not None else row_state
                    cls.append("st-" + st)
                if info["saturday"]:
                    cls.append("is-sat")
                if info["sunday"]:
                    cls.append("is-sun")
                if info["today"]:
                    cls.append("is-today")
                cells.append({
                    "day": d,
                    "date": fields.Date.to_string(date(year, month, d)),
                    "cls": " ".join(cls),
                    # Plan chỉ hiện "x"; hoàn thành thể hiện bằng màu xanh của ô x
                    "mark": "x" if d in planned else "",
                })
            return cells

        # Hạng mục theo đúng bảng "Hạng mục" (Phòng ban → Team → Hạng mục, số La Mã I, II…)
        WG = self.env["daily.task.work.group"].sudo()
        cat_by_team, cat_by_name = {}, {}
        board_index = 0
        for dept in WG.get_category_board_data().get("departments") or []:
            for team in dept.get("teams") or []:
                for cat in team.get("categories") or []:
                    board_index += 1
                    team_id = (cat.get("tasks") or [{}])[0].get("team_id") or False
                    info = {"index": board_index, "code": cat.get("code") or "", "name": cat.get("name") or "",
                            "team": team.get("name") or ""}
                    key = (cat.get("name") or "").casefold()
                    cat_by_team[(team_id, key)] = info
                    cat_by_name.setdefault(key, info)
        used_teams = set()

        def resolve_category(work_group, line=None):
            """Hạng mục của việc → mục trên bảng Hạng mục (bỏ tiền tố số "1." như bảng)."""
            wg = work_group or (line.work_group_id or line.category_group_id if line else WG)
            raw = WG._norm_category_name(wg.name) if wg else ((line.category_name if line else "") or "")
            key = raw.casefold()
            team_id = wg.team_id.id if wg and wg.team_id else False
            info = cat_by_team.get((team_id, key)) or cat_by_name.get(key)
            if info and info["team"]:
                used_teams.add(info["team"])
            return info, raw

        def add_row(category, row, start, end, sort_key):
            info, raw = category
            if info:
                gkey = "cat-%s" % info["index"]
                title = "%s. %s" % (info["code"], (info["name"] or "").upper())
                gsort = (0, info["index"], "")
            else:
                # Hạng mục không còn trên bảng Hạng mục (đã xóa/đổi tên) → xếp cuối
                gkey = "other-%s" % (raw or "Khác").casefold()
                title = (raw or "Khác").upper()
                gsort = (1, 0, title)
            group = group_index.get(gkey)
            if not group:
                group = {"name": title, "lines": [], "sort": gsort, "num": info["index"] if info else None}
                group_index[gkey] = group
                groups.append(group)
            row.update({
                "start": start.strftime("%d/%m/%Y") if start else "",
                "deadline": end.strftime("%d/%m/%Y") if end else "",
                "start_iso": fields.Date.to_string(start) if start else "",
                "deadline_iso": fields.Date.to_string(end) if end else "",
                # Số ngày = Deadline - Ngày bắt đầu + 1 (tính cả ngày bắt đầu; cùng ngày = 1)
                "days_count": (end - start).days + 1 if start and end else None,
                "_sort": sort_key,
            })
            group["lines"].append(row)

        def task_category(task):
            return resolve_category(task.work_group_id, task.assign_line_id)

        # 1) Việc cá nhân (mỗi việc 1 dòng) — đúng như "Danh sách việc của tôi"
        for task in single_tasks:
            line = task.assign_line_id
            # Ô x theo Ngày bắt đầu → Deadline của chính việc cá nhân (+ ô bật/tắt tay)
            planned = {d.date.day for d in task_days if d.task_id == task}
            day_kind, day_id = "task", task.id
            state = task_state(task)
            done = state == "done"
            status_count[state] = status_count.get(state, 0) + 1
            totals["planned"] += len(planned)
            if done and task.date_done and first <= task.date_done <= last:
                totals["done"] += 1
            add_row(task_category(task), {
                "id": task.id,
                "kind": "task",
                "key": "task-%s" % task.id,
                "line_id": line.id if line else False,
                "note": (task.note or "").strip(),
                "day_kind": day_kind,
                "day_id": day_id,
                "name": task.name or "",
                "owner": task.assignee_id.name or task.assignee_user_id.name or "",
                "can_edit_dates": is_self_or_manager and task._can_edit_task_details(),
                "plan_daily": False,
                "personal": not line,
                "team_locked": bool(line and line._is_team_locked()),
                "progress": 100 if done else int(task.completion_percent or 0),
                "state": state,
                "locked": done,
                "readonly": False,
                "cells": build_cells(planned, state),
            }, task.assign_date, task.deadline, (task.assign_date or first, task.id))

        # 2) Việc lặp (nhãn "Lặp"): gom các việc sinh mỗi ngày thành 1 dòng / mẫu lặp
        for tpl in recurring_tasks.mapped("recurring_id"):
            tpl_tasks = recurring_tasks.filtered(lambda t, r=tpl: t.recurring_id == r)
            day_states = {}
            for t in tpl_tasks:
                if t.assign_date and first <= t.assign_date <= last:
                    day_states[t.assign_date.day] = task_state(t)
                    status_count[day_states[t.assign_date.day]] = (
                        status_count.get(day_states[t.assign_date.day], 0) + 1
                    )
            planned = set(day_states)
            # Ô x theo lịch lặp cho mọi ngày trong dải (Ngày bắt đầu → Deadline, trừ CN),
            # kể cả ngày đã qua chưa sinh việc; mẫu không có Ngày bắt đầu thì tính từ ngày tạo mẫu
            tpl_start = tpl.date_from or (
                fields.Datetime.context_timestamp(tpl, tpl.create_date).date() if tpl.create_date else first
            )
            for info in days:
                day = date(year, month, info["day"])
                if day >= tpl_start and info["day"] not in planned and tpl._should_generate_on(day):
                    planned.add(info["day"])
            done_days = sum(1 for s in day_states.values() if s == "done")
            totals["planned"] += len(planned)
            totals["done"] += done_days
            starts = [t.assign_date for t in tpl_tasks if t.assign_date]
            ends = [t.deadline for t in tpl_tasks if t.deadline]
            # Hiện đúng dải của mẫu lặp: không có ngày kết thúc = lặp liên tục ("—"),
            # tránh lưu nhầm ngày của việc gần nhất làm ngày kết thúc
            start = tpl.date_from or False
            end = tpl.date_to or False
            add_row(resolve_category(tpl.work_group_id, tpl.assign_line_id) if tpl.work_group_id
                    else task_category(tpl_tasks[:1]), {
                "id": tpl.id,
                "kind": "recurring",
                "key": "rec-%s" % tpl.id,
                "line_id": tpl.assign_line_id.id or False,
                "note": "",
                "day_kind": "",
                "day_id": False,
                "name": tpl.name or "",
                "owner": tpl.employee_id.name or user.name,
                # Sửa mẫu lặp của chính người đó (Tên / Ngày bắt đầu / Deadline của dải lặp)
                "can_edit_dates": is_self_or_manager and tpl.employee_id.user_id == user
                and not (tpl.assign_line_id and tpl.assign_line_id._is_team_locked()),
                "plan_daily": True,
                "personal": not tpl.assign_line_id or tpl.assign_line_id.plan_source == "personal",
                "team_locked": bool(tpl.assign_line_id and tpl.assign_line_id._is_team_locked()),
                "progress": round(100.0 * done_days / len(planned)) if planned else 0,
                "state": "",
                "locked": False,
                "readonly": not (is_self_or_manager and tpl.employee_id.user_id == user),
                "cells": build_cells(planned, day_states=day_states),
            }, start, end, (start or (min(starts) if starts else first), -tpl.id))

        groups.sort(key=lambda g: g["sort"])
        next_num = max([g["num"] for g in groups if g["num"]] or [0])
        for group in groups:
            if not group["num"]:
                next_num += 1
                group["num"] = next_num
            group["code"] = group["num"]
            group["lines"].sort(key=lambda r: r.pop("_sort"))
            for sub, row in enumerate(group["lines"], start=1):
                row["code"] = "%s.%s" % (group["num"], sub)
            group.pop("sort", None)
            group.pop("num", None)
        users = []
        if is_manager:
            pool = Assign.search([("active", "=", True)]).mapped("assignee_user_ids")
            users = [{"id": u.id, "name": u.name} for u in pool.sorted(lambda u: (u.name or "").casefold())]
        return {
            "year": year,
            "month": month,
            "month_label": "Tháng %02d/%s" % (month, year),
            "user": {"id": user.id, "name": user.name},
            "teams": sorted(used_teams),
            # Trạng thái duyệt Plan tháng (Bước 3–4)
            "approval": self.env["daily.task.plan.approval"]._info(user, year, month),
            "can_pick_user": is_manager,
            "can_edit_cells": is_self_or_manager,
            "can_add": is_self_or_manager,
            # Dùng khung "Thêm công việc cho team" (chọn team, hạng mục, miền, kiểm soát)
            "can_team_add": self._team_plan_can_add(),
            "categories": self._plan_categories(user),
            "users": users,
            "days": days,
            "groups": groups,
            "summary": {
                "lines": sum(len(g["lines"]) for g in groups),
                "daily": len(recurring_tasks.mapped("recurring_id")),
                "planned": totals["planned"],
                "done": totals["done"],
                "status": status_count,
                "task_total": sum(status_count.values()),
            },
        }

    def _plan_can_edit_dates(self):
        """Quản lý: mọi dòng. Nhân viên: dòng chỉ mình phụ trách (dòng chung đổi ngày ảnh hưởng cả team)."""
        self.ensure_one()
        if self.env["daily.task.assign.access"]._is_manager():
            return True
        if self.sudo().plan_source == "personal":
            # Việc bổ sung của cá nhân: người phụ trách tự sửa
            return self.sudo()._responsible_users() == self.env.user
        # Việc từ Plan tổng / Phân công: chỉ người có quyền Chỉnh sửa Plan tổng
        return self._plan_content_editor()

    @api.model
    def _plan_content_editor(self):
        """Được sửa nội dung việc Plan tổng đã áp xuống (Quản lý / quyền Chỉnh sửa Plan tổng)."""
        return bool(self.env["daily.task.team.plan.access"].get_perms().get("write"))

    def _is_team_locked(self):
        """Dòng từ Plan tổng / Phân công mà user hiện tại không có quyền sửa nội dung."""
        self.ensure_one()
        return self.sudo().plan_source != "personal" and not self._plan_content_editor()

    @api.model
    def _plan_categories(self, user):
        dept = self._department_from_user(user)
        domain = [("active", "=", True)]
        if dept:
            domain.append(("department_id", "=", dept.id))
        groups = self.env["daily.task.work.group"].sudo().search(domain)
        return sorted({(g.name or "").strip() for g in groups if g.name}, key=str.casefold)

    @api.model
    def _plan_target_user(self, user_id=None):
        """User của plan đang sửa: chính mình, hoặc người khác nếu là quản lý."""
        user = self.env.user
        if user_id and int(user_id) != user.id:
            if not self.env["daily.task.assign.access"]._is_manager():
                raise AccessError("Bạn chỉ được sửa plan của chính mình.")
            user = self.env["res.users"].sudo().browse(int(user_id)).exists()
            if not user:
                raise UserError("Không tìm thấy nhân sự.")
        return user

    @api.model
    def _plan_parse_dates(self, date_start, deadline):
        start = fields.Date.to_date(date_start) if date_start else False
        end = fields.Date.to_date(deadline) if deadline else False
        if start and end and end < start:
            raise UserError("Deadline không được trước ngày Bắt đầu.")
        return start, end

    @api.model
    def _plan_task(self, task_id):
        """Việc cá nhân trên Plan — kiểm tra quyền như bảng cá nhân (việc người khác giao thì khóa)."""
        task = self.env["daily.task"].browse(int(task_id)).exists()
        if not task:
            raise UserError("Công việc không còn tồn tại.")
        if task._is_plan_locked():
            raise AccessError("Việc từ Plan tổng — cá nhân không sửa được Tên / Ngày bắt đầu / Deadline đã áp xuống.")
        if not task._can_edit_task_details():
            raise AccessError("Việc này do người khác giao — bạn không sửa được tên / ngày.")
        return task.sudo()

    @api.model
    def _plan_is_done(self, row_id, kind="line", user=None, day=None):
        """Công việc đã hoàn thành (ô x xanh) → khóa chỉnh sửa trên Plan.

        task: việc cá nhân đã xong. line thường: việc cá nhân của người phụ trách (hoặc tất cả) đã xong.
        line lặp hằng ngày: chỉ khóa đúng ngày có việc đã hoàn thành.
        """
        Task = self.env["daily.task"].sudo()
        if kind == "recurring":
            return False
        if kind == "task":
            task = Task.browse(int(row_id)).exists()
            return bool(task and task._is_work_completed())
        line = self.sudo().browse(int(row_id)).exists()
        if not line:
            return False
        domain = [("assign_line_id", "=", line.id)]
        if user:
            domain.append(("assignee_user_id", "=", user.id))
        if line.plan_daily:
            if not day:
                return False
            tasks = Task.search(domain + [("recurring_id", "!=", False), ("assign_date", "=", day)])
            return any(t._is_work_completed() for t in tasks)
        tasks = Task.search(domain + [("recurring_id", "=", False)])
        return bool(tasks) and all(t._is_work_completed() for t in tasks)
    @api.model
    def plan_update_line(self, line_id, date_start=None, deadline=None, kind="line", name=None):
        """Sửa Nội dung / Ngày bắt đầu / Deadline trên Plan — đồng bộ 2 chiều với bảng cá nhân.

        kind='line': dòng phân công → việc cá nhân của người phụ trách cập nhật theo.
        kind='task': chính việc cá nhân (Nhập công việc) → cùng bản ghi.
        Đổi ngày thì các ô 'x' (kể cả hôm nay) tự làm lại.
        """
        if self._plan_is_done(line_id, kind):
            raise UserError("Công việc đã hoàn thành — không chỉnh sửa được trên Plan.")
        start, end = self._plan_parse_dates(date_start, deadline)
        name = (name or "").strip() if name is not None else None
        if name is not None and not name:
            raise UserError("Tên công việc không được để trống.")
        if kind == "recurring":
            tpl = self.env["daily.task.recurring"].sudo().browse(int(line_id)).exists()
            if not tpl:
                raise UserError("Mẫu công việc lặp không còn tồn tại.")
            owner = tpl.employee_id.user_id
            if owner != self.env.user and not self.env["daily.task.assign.access"]._is_manager():
                raise AccessError("Bạn chỉ sửa được công việc lặp của chính mình.")
            if tpl.assign_line_id and tpl.assign_line_id._is_team_locked():
                raise AccessError("Việc từ Plan tổng — cá nhân không sửa được nội dung đã áp xuống.")
            vals = {"date_from": start, "date_to": end}
            if name is not None:
                vals["name"] = name
            tpl.write(vals)
            # Hôm nay nằm trong dải mới mà chưa có việc → sinh luôn
            tpl._generate_task_for_date(fields.Date.context_today(self))
            return True
        if kind == "task":
            task = self._plan_task(line_id)
            vals = {"assign_date": start, "deadline": end}
            if name is not None:
                vals["name"] = name
            task.write(vals)
            return True
        line = self.sudo().browse(int(line_id)).exists()
        if not line:
            raise UserError("Dòng phân công không còn tồn tại.")
        if line._is_team_locked():
            raise AccessError("Việc từ Plan tổng — cá nhân không sửa được Tên / Ngày bắt đầu / Deadline đã áp xuống.")
        if not line._plan_can_edit_dates():
            raise AccessError(
                "Dòng này có nhiều người phụ trách — chỉ quản lý mới sửa được nội dung / ngày."
            )
        vals = {"date_start": start, "deadline": end}
        if name is not None:
            vals["name"] = name
        line.write(vals)
        return True

    @api.model
    def plan_toggle_day(self, line_id, day, user_id=None, kind="line"):
        """Bật/tắt ô 'x' của 1 ngày. Ghi qua ORM thường để áp Record Rule (của mình / quản lý)."""
        user = self._plan_target_user(user_id)
        date_value = fields.Date.to_date(day)
        if self._plan_is_done(line_id, kind, user=user, day=date_value):
            raise UserError("Công việc / ngày này đã hoàn thành — không chỉnh sửa được trên Plan.")
        PlanDay = self.env["daily.task.plan.day"]
        if kind == "task":
            task = self.env["daily.task"].sudo().browse(int(line_id)).exists()
            if not task or task.assignee_user_id != user:
                raise AccessError("Công việc này không nằm trong plan của bạn.")
            domain = [("task_id", "=", task.id), ("date", "=", date_value)]
            create_vals = {"task_id": task.id}
        else:
            line = self.sudo().browse(int(line_id)).exists()
            if not line or user not in line._responsible_users():
                raise AccessError("Công việc này không nằm trong plan của bạn.")
            if line._is_team_locked():
                raise AccessError("Việc từ Plan tổng — cá nhân không chỉnh ngày kế hoạch (ô x) đã áp xuống.")
            domain = [("line_id", "=", line.id), ("user_id", "=", user.id), ("date", "=", date_value)]
            create_vals = {"line_id": line.id}
        rec = PlanDay.search(domain, limit=1)
        if rec:
            rec.write({"planned": not rec.planned, "manual": True})
        else:
            rec = PlanDay.create({
                **create_vals,
                "user_id": user.id,
                "date": date_value,
                "planned": True,
                "manual": True,
            })
        return rec.planned

    @api.model
    def plan_save_row(self, row_id, kind="line", info=None, year=None, month=None, days=None, user_id=None,
                      day_kind=None, day_id=None):
        """Lưu khung chỉnh sửa 1 công việc trên Plan (chỉ ghi khi bấm Lưu).

        info: {name, date_start, deadline} nếu có đổi — đồng bộ 2 chiều với bảng cá nhân.
        days: danh sách ngày (1–31) có 'x' trong tháng year/month sau khi chỉnh — ô khác hiện
              trạng sẽ được bật/tắt (ghi nhận là nhập tay).
        """
        if info:
            self.plan_update_line(
                row_id,
                info.get("date_start") or False,
                info.get("deadline") or False,
                kind=kind,
                name=info.get("name"),
            )
        if days is None or not year or not month:
            return True
        # Ô x của việc cá nhân gắn dòng phân công nằm trên dòng phân công (day_kind="line")
        kind = day_kind or kind
        row_id = day_id or row_id
        if kind not in ("line", "task"):
            raise UserError("Công việc lặp chỉnh ở mục Công việc lặp — Plan chỉ xem.")
        user = self._plan_target_user(user_id)
        year, month = int(year), int(month)
        n_days = calendar.monthrange(year, month)[1]
        first, last = date(year, month, 1), date(year, month, n_days)
        domain = [("user_id", "=", user.id), ("date", ">=", first), ("date", "<=", last), ("planned", "=", True)]
        if kind == "task":
            domain.append(("task_id", "=", int(row_id)))
        else:
            domain.append(("line_id", "=", int(row_id)))
        current = {d.date.day for d in self.env["daily.task.plan.day"].sudo().search(domain)}
        wanted = {int(d) for d in days if 1 <= int(d) <= n_days}
        for day in sorted(current ^ wanted):
            self.plan_toggle_day(
                row_id, fields.Date.to_string(date(year, month, day)), user_id=user.id, kind=kind
            )
        return True
    @api.model
    def plan_create_line(self, vals, user_id=None):
        """Thêm việc từ trang Plan.

        - Việc thường → tạo Việc cá nhân (hiện cả ở Nhập công việc và Plan).
        - 'Lặp hằng ngày' → tạo dòng phân công (sinh Công việc lặp mỗi ngày trừ CN).
        """
        user = self._plan_target_user(user_id)
        vals = vals or {}
        name = (vals.get("name") or "").strip()
        if not name:
            raise UserError("Vui lòng nhập tên công việc.")
        start, end = self._plan_parse_dates(vals.get("date_start"), vals.get("deadline"))
        today = fields.Date.context_today(self)
        category = (vals.get("category") or "").strip()
        cat_group = self.env["daily.task.work.group"]
        dept = self._department_from_user(user)
        if category:
            domain = [("name", "=ilike", category), ("active", "=", True)]
            if dept:
                domain.append(("department_id", "=", dept.id))
            cat_group = cat_group.sudo().search(domain, limit=1)
        if not vals.get("plan_daily"):
            hr = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
            if not hr:
                raise UserError("Tài khoản chưa gắn hồ sơ nhân viên — không tạo được việc cá nhân.")
            bridge = self.env["daily.task.employee"].sudo().get_or_create_from_hr(hr.id)
            task = self.env["daily.task"].sudo().with_context(
                skip_work_group_user_check=True,
                daily_task_assigner_uid=self.env.uid,
            ).create({
                "name": name,
                "assignee_id": bridge.id,
                "assigned_by_id": self.env.uid,
                "department_id": (cat_group.department_id or dept or hr.department_id).id or False,
                "work_group_id": cat_group.id or False,
                "assign_date": start or today,
                "deadline": end or start or today,
                "state": "not_started",
                "priority": "medium",
            })
            return task.id
        line = self.sudo().with_context(skip_assign_expand=True).create([{
            "name": name,
            "category_group_id": cat_group.id or False,
            "department_id": dept.id if dept else False,
            "date_start": start or today,
            "deadline": end,
            "assignee_user_ids": [(6, 0, [user.id])],
            "plan_daily": True,
            "plan_source": "personal",
        }])
        return line.id

    @api.model
    def export_my_plan_excel(self, year=None, month=None, user_id=None):
        """Xuất Excel Plan CV cá nhân — cùng dữ liệu / màu với màn hình Plan."""
        try:
            import xlsxwriter
        except ImportError as err:
            raise UserError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from err

        data = self.get_my_plan_data(year=year, month=month, user_id=user_id)
        days = data["days"]
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Plan CV ca nhan")
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.3, right=0.3, top=0.4, bottom=0.4)

        FONT = "Times New Roman"

        def fmt(**kw):
            base = {"font_name": FONT, "font_size": 10, "valign": "vcenter"}
            base.update(kw)
            return wb.add_format(base)

        f_title = fmt(bold=True, font_size=15)
        f_sub = fmt(font_size=11, italic=True)
        f_kpi_label = fmt(bold=True, border=1, align="center", bg_color="#F1F5F9")
        f_kpi_val = fmt(bold=True, font_size=12, border=1, align="center")
        f_head = fmt(bold=True, border=1, align="center", text_wrap=True, bg_color="#FCE4D6")
        f_head_sun = fmt(bold=True, border=1, align="center", bg_color="#FDD835")
        f_group = fmt(bold=True, border=1, bg_color="#B4C6E7")
        f_cell = fmt(border=1, text_wrap=True)
        f_center = fmt(border=1, align="center")
        f_pct = fmt(border=1, align="center", num_format="0%")
        f_day = fmt(border=1, align="center")
        f_sun = fmt(border=1, align="center", bg_color="#FFEB3B")
        state_colors = {
            "not_started": ("#E2E8F0", "#334155"),
            "in_progress": ("#FDBA74", "#7C2D12"),
            "done": ("#86EFAC", "#14532D"),
            "overdue": ("#DC2626", "#FFFFFF"),
        }
        f_state = {
            key: fmt(border=1, align="center", bold=True, bg_color=bg, font_color=fg)
            for key, (bg, fg) in state_colors.items()
        }

        fixed = ["STT", "Nội dung công việc", "Người phụ trách", "Ngày bắt đầu", "Deadline", "Số ngày", "Tiến độ"]
        widths = [6, 42, 22, 12, 12, 8, 9]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)
        first_day_col = len(fixed)
        ws.set_column(first_day_col, first_day_col + len(days) - 1, 3.6)
        last_col = first_day_col + len(days) - 1

        ws.merge_range(0, 0, 0, last_col, "PLAN CÔNG VIỆC CÁ NHÂN — %s" % data["month_label"].upper(), f_title)
        teams = ", ".join(data.get("teams") or [])
        ws.merge_range(1, 0, 1, last_col, "%s%s" % (data["user"]["name"], (" · Team: %s" % teams) if teams else ""), f_sub)

        # Dashboard trạng thái (đếm việc giống Danh sách công việc)
        summary = data["summary"]
        status = summary.get("status") or {}
        total = summary.get("task_total") or 0
        # Số ô x theo màu trạng thái (giống dòng "việc · N ô x" trên dashboard)
        x_count = {"total": 0, "done": 0, "in_progress": 0, "not_started": 0, "overdue": 0}
        for group in data["groups"]:
            for line in group["lines"]:
                for cell in line["cells"]:
                    classes = cell["cls"].split()
                    if "is-plan" not in classes:
                        continue
                    x_count["total"] += 1
                    for key in ("done", "in_progress", "not_started", "overdue"):
                        if "st-" + key in classes:
                            x_count[key] += 1

        # Dashboard dạng thẻ màu nằm ngang: (nhãn, số, dòng phụ, màu chữ/viền, màu nền, cột từ, cột đến)
        rate = round(100.0 * status.get("done", 0) / total) if total else 0
        cards = [
            ("☰ Tổng công việc", total, "việc · %s ô x" % x_count["total"], "#2563EB", "#EFF6FF", 1, 1),
            ("✔ Hoàn thành", status.get("done", 0), "việc · %s ô x" % x_count["done"], "#16A34A", "#DCFCE7", 2, 2),
            ("⟳ Đang thực hiện", status.get("in_progress", 0), "việc · %s ô x" % x_count["in_progress"],
             "#EA580C", "#FFEDD5", 3, 4),
            ("⌛ Chưa bắt đầu", status.get("not_started", 0), "việc · %s ô x" % x_count["not_started"],
             "#475569", "#E2E8F0", 5, 10),
            ("⚠ Trễ hạn", status.get("overdue", 0), "việc · %s ô x" % x_count["overdue"],
             "#DC2626", "#FEE2E2", 11, 19),
            ("◔ Tỷ lệ hoàn thành", "%s%%" % rate, "%s / %s việc" % (status.get("done", 0), total),
             "#0F766E", "#CCFBF1", 20, 28),
        ]
        top = 3
        for label, value, sub, color, bg, c1, c2 in cards:
            c2 = min(c2, last_col)
            edge = {"left": 5, "left_color": color, "top": 1, "top_color": color,
                    "right": 1, "right_color": color, "bg_color": bg}
            f_label = fmt(bold=True, font_color=color, font_size=11, align="left", indent=1,
                          bottom=0, **edge)
            f_value = fmt(bold=True, font_color=color, font_size=20, align="left", indent=1,
                          **{k: v for k, v in edge.items() if not k.startswith("top")})
            f_subl = fmt(italic=True, font_color="#475569", font_size=9, align="left", indent=1,
                         bottom=1, bottom_color=color,
                         **{k: v for k, v in edge.items() if not k.startswith("top")})
            for r, txt, f in ((top, label, f_label), (top + 1, value, f_value), (top + 2, sub, f_subl)):
                if c2 > c1:
                    ws.merge_range(r, c1, r, c2, txt, f)
                else:
                    ws.write(r, c1, txt, f)
        ws.set_row(top, 18)
        ws.set_row(top + 1, 30)
        ws.set_row(top + 2, 16)

        head1, head2 = top + 4, top + 5
        for c, title in enumerate(fixed):
            ws.merge_range(head1, c, head2, c, title, f_head)
        for i, d in enumerate(days):
            c = first_day_col + i
            ws.write(head1, c, d["day"], f_head_sun if d["sunday"] else f_head)
            ws.write(head2, c, d["wd"], f_head_sun if d["sunday"] else f_head)
        ws.set_row(head1, 18)
        ws.freeze_panes(head2 + 1, 2)

        row = head2 + 1
        for group in data["groups"]:
            ws.write(row, 0, group["code"], f_group)
            ws.merge_range(row, 1, row, last_col, "%s (%s CV)" % (group["name"], len(group["lines"])), f_group)
            row += 1
            for line in group["lines"]:
                ws.write(row, 0, line["code"], f_center)
                ws.write(row, 1, line["name"] + ("  (lặp)" if line.get("plan_daily") else ""), f_cell)
                ws.write(row, 2, line.get("owner") or "", f_cell)
                ws.write(row, 3, line.get("start") or "—", f_center)
                ws.write(row, 4, line.get("deadline") or "—", f_center)
                ws.write(row, 5, line.get("days_count") if line.get("days_count") is not None else "—", f_center)
                ws.write(row, 6, (line.get("progress") or 0) / 100.0, f_pct)
                for i, cell in enumerate(line["cells"]):
                    c = first_day_col + i
                    classes = cell["cls"].split()
                    st = next((k[3:] for k in classes if k.startswith("st-")), None)
                    if cell["mark"] and st in f_state:
                        ws.write(row, c, cell["mark"], f_state[st])
                    elif "is-sun" in classes:
                        ws.write(row, c, "", f_sun)
                    else:
                        ws.write(row, c, "", f_day)
                row += 1

        row += 1
        legend = [
            ("x Chưa bắt đầu", f_state["not_started"]),
            ("x Đang xử lý", f_state["in_progress"]),
            ("x Đã hoàn thành", f_state["done"]),
            ("x Trễ hạn", f_state["overdue"]),
            ("Chủ nhật", f_sun),
        ]
        ws.write(row, 1, "Chú thích:", fmt(bold=True))
        for i, (label, f) in enumerate(legend):
            ws.write(row + 1 + i, 1, label, f)

        wb.close()
        filename = "Plan_CV_ca_nhan_%s_T%02d_%s.xlsx" % (
            re.sub(r"\W+", "_", data["user"]["name"] or "user").strip("_"),
            data["month"],
            data["year"],
        )
        return {
            "file_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "filename": filename,
        }

    # ------------------------------------------------------------------
    # Plan tổng team — tổng hợp từ Plan CV cá nhân của các thành viên
    # ------------------------------------------------------------------
    _TEAM_STATE_RANK = {"overdue": 4, "in_progress": 3, "not_started": 2, "done": 1}

    @api.model
    def _team_plan_teams(self):
        """Team có hạng mục đang dùng (chọn trên Plan tổng)."""
        teams = self.env["daily.task.work.group"].sudo().search([("active", "=", True)]).mapped("team_id")
        return teams.sorted(lambda t: (t.sequence, (t.name or "").casefold()))

    @api.model
    def _team_plan_members(self, team):
        """Thành viên team = người phụ trách các dòng phân công thuộc hạng mục của team."""
        lines = self.sudo().search([
            ("active", "=", True),
            "|", ("work_group_id.team_id", "=", team.id), ("category_group_id.team_id", "=", team.id),
        ])
        users = self.env["res.users"]
        for line in lines:
            users |= line._responsible_users()
        return users.filtered(lambda u: u.active and not u.share).sorted(lambda u: (u.name or "").casefold())

    @api.model
    def get_team_plan_data(self, year=None, month=None, team_id=None):
        """Plan tổng team theo mẫu PLAN TEAM: mỗi công việc 1 dòng, cột Miền / Văn phòng,
        Người phụ trách, Kiểm soát, Kết quả, lưới ngày; số liệu = tổng Plan cá nhân."""
        if not self._team_plan_can_view():
            raise AccessError("Bạn không có quyền xem Plan tổng team.")
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        teams = self._team_plan_teams()
        team = teams.filtered(lambda t: t.id == int(team_id)) if team_id else self.env["daily.task.team"]
        if not team:
            mine = teams.filtered(lambda t: self.env.user in self._team_plan_members(t))
            team = (mine or teams)[:1]
        members = self._team_plan_members(team) if team else self.env["res.users"]

        days, merged, group_meta = None, {}, {}
        status = {"done": 0, "in_progress": 0, "not_started": 0, "overdue": 0}
        member_stats = []
        Line = self.sudo()
        for member in members:
            pdata = self.with_user(member).sudo(False).get_my_plan_data(year, month)
            days = days or pdata["days"]
            mstat = pdata["summary"].get("status") or {}
            for k in status:
                status[k] += mstat.get(k, 0)
            member_stats.append({
                "id": member.id,
                "name": member.name,
                "total": pdata["summary"].get("task_total") or 0,
                **{k: mstat.get(k, 0) for k in status},
                "approval": self.env["daily.task.plan.approval"]._info(member, year, month, self.env.user),
            })
            for group in pdata["groups"]:
                gname = group["name"]
                group_meta.setdefault(gname, group["code"])
                for row in group["lines"]:
                    if row.get("line_id"):
                        key = ("line", row["line_id"])
                    else:
                        key = (row["kind"], row["id"])
                    item = merged.get(key)
                    if not item:
                        item = merged[key] = {
                            "key": "%s-%s" % key,
                            "group": gname,
                            "name": row["name"],
                            "task_id": row["id"] if row.get("kind") == "task" and not row.get("line_id") else False,
                            "owner_uid": member.id,
                            "line_id": row.get("line_id") or False,
                            "plan_daily": row.get("plan_daily"),
                            "starts": [], "ends": [],
                            "members": [], "progress": [], "notes": [],
                            "cells": {},
                        }
                    item["members"].append(member.name)
                    item["progress"].append(int(row.get("progress") or 0))
                    if row.get("note"):
                        item["notes"].append(row["note"])
                    if row.get("start_iso"):
                        item["starts"].append(row["start_iso"])
                    if row.get("deadline_iso"):
                        item["ends"].append(row["deadline_iso"])
                    for cell in row["cells"]:
                        classes = cell["cls"].split()
                        if "is-plan" not in classes:
                            continue
                        st = next((c[3:] for c in classes if c.startswith("st-")), "not_started")
                        prev = item["cells"].get(cell["day"])
                        # Ô chung của team: lấy trạng thái "xấu" nhất giữa các thành viên
                        if not prev or self._TEAM_STATE_RANK.get(st, 0) > self._TEAM_STATE_RANK.get(prev, 0):
                            item["cells"][cell["day"]] = st

        def names(users):
            return ", ".join(users.mapped("name"))

        # Miền chính của từng thành viên = miền xuất hiện nhiều nhất trên các dòng phân công của team
        # (bằng nhau → ưu tiên Văn phòng). Dùng cho việc cá nhân / dòng chưa gán miền, để cột
        # Người phụ trách luôn đúng bằng những người trong các cột Miền / Văn phòng.
        region_fields = (("office", "office_user_ids"), ("south", "south_user_ids"),
                         ("dtt", "dtt_user_ids"), ("north", "north_user_ids"))
        team_lines = Line.search([
            ("active", "=", True),
            "|", ("work_group_id.team_id", "=", team.id), ("category_group_id.team_id", "=", team.id),
        ]) if team else Line
        home_region = {}
        for member in members:
            counts = {key: sum(1 for ln in team_lines if member in ln[fname]) for key, fname in region_fields}
            best = max(counts.values()) if counts else 0
            home_region[member.name] = next(
                (key for key, _f in region_fields if counts[key] == best and best), "office"
            )

        groups_out = {}
        group_mgr = {}
        for item in merged.values():
            line = Line.browse(item["line_id"]) if item["line_id"] else Line
            owners = list(dict.fromkeys(item["members"]))
            mgr = group_mgr.setdefault(item["group"], [])
            if line and line.sudo().work_group_id:
                for uname in line.sudo().work_group_id._category_managers().mapped("name"):
                    if uname not in mgr:
                        mgr.append(uname)
            region_cols = {"south": "", "dtt": "", "north": "", "office": ""}
            if line and (line.south_user_ids or line.dtt_user_ids or line.north_user_ids or line.office_user_ids):
                region_cols.update({
                    "south": names(line.south_user_ids),
                    "dtt": names(line.dtt_user_ids),
                    "north": names(line.north_user_ids),
                    "office": names(line.office_user_ids),
                })
                owners = list(dict.fromkeys(
                    (line.south_user_ids | line.dtt_user_ids | line.north_user_ids | line.office_user_ids)
                    .mapped("name") + owners
                ))
                # Người có việc nhưng chưa nằm ở cột miền nào của dòng → thêm vào miền chính
                placed = set((line.south_user_ids | line.dtt_user_ids | line.north_user_ids
                              | line.office_user_ids).mapped("name"))
                for name in owners:
                    if name not in placed:
                        key = home_region.get(name, "office")
                        region_cols[key] = ", ".join(filter(None, [region_cols[key], name]))
            else:
                for name in owners:
                    key = home_region.get(name, "office")
                    region_cols[key] = ", ".join(filter(None, [region_cols[key], name]))
            prog = item["progress"]
            done_members = sum(1 for p in prog if p >= 100)
            start = min(item["starts"]) if item["starts"] else ""
            end = max(item["ends"]) if item["ends"] else ""
            row_cells = []
            for d in days or []:
                st = item["cells"].get(d["day"])
                cls = []
                if st:
                    cls += ["is-plan", "st-" + st]
                if d["saturday"]:
                    cls.append("is-sat")
                if d["sunday"]:
                    cls.append("is-sun")
                row_cells.append({"day": d["day"], "cls": " ".join(cls), "mark": "x" if st else ""})
            states = set(item["cells"].values())
            row_state = max(states, key=lambda s: self._TEAM_STATE_RANK.get(s, 0)) if states else ""
            groups_out.setdefault(item["group"], []).append({
                "key": item["key"],
                "name": item["name"],
                "line_id": item["line_id"] or False,
                # Việc bổ sung cá nhân: chính chủ sửa được ngay trên Plan tổng
                "task_id": item["task_id"] or False,
                "own": bool(item["task_id"] and item["owner_uid"] == self.env.uid),
                "task_start_iso": item["starts"][0] if item["task_id"] and item["starts"] else "",
                "task_deadline_iso": item["ends"][0] if item["task_id"] and item["ends"] else "",
                "start_iso": fields.Date.to_string(fields.Date.to_date(line.date_start)) if line and line.date_start else "",
                "deadline_iso": fields.Date.to_string(fields.Date.to_date(line.deadline)) if line and line.deadline else "",
                "plan_daily": bool(item["plan_daily"]),
                **region_cols,
                # Người phụ trách = đúng những người ở các cột Miền Nam / ĐTT / Bắc / Văn phòng
                "owner": ", ".join(owners),
                "checker": names(line.check_user_ids) if line else "",
                "result": "%s/%s HT · %s%%" % (done_members, len(prog), round(sum(prog) / len(prog)) if prog else 0),
                "note": "; ".join(dict.fromkeys(item["notes"])),
                "start": fields.Date.to_date(start).strftime("%d/%m/%Y") if start else "",
                "deadline": fields.Date.to_date(end).strftime("%d/%m/%Y") if end else "",
                "state": row_state,
                "cells": row_cells,
                "_sort": (start or "9999", item["name"].casefold()),
            })

        groups = []
        for gname in sorted(groups_out, key=lambda g: (group_meta.get(g, 999), g)):
            rows = sorted(groups_out[gname], key=lambda r: r.pop("_sort"))
            groups.append({"code": group_meta.get(gname, 0), "name": gname, "lines": rows,
                           "managers": ", ".join(group_mgr.get(gname) or [])})
        # Đánh số lại liên tục 1..n và STT dòng n.m
        for idx, g in enumerate(groups, start=1):
            g["code"] = idx
            for sub, r in enumerate(g["lines"], start=1):
                r["code"] = "%s.%s" % (idx, sub)

        total = sum(status.values())
        return {
            "year": year,
            "month": month,
            "month_label": "Tháng %02d/%s" % (month, year),
            "team": {"id": team.id, "name": team.name} if team else False,
            "teams": [{"id": t.id, "name": t.name} for t in teams],
            "members": member_stats,
            "days": days or [],
            "groups": groups,
            "summary": {"status": status, "task_total": total},
        }

    @api.model
    def export_team_plan_excel(self, year=None, month=None, team_id=None):
        """Xuất Excel Plan tổng team theo mẫu PLAN TEAM."""
        try:
            import xlsxwriter
        except ImportError as err:
            raise UserError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from err
        data = self.get_team_plan_overview(year=year, month=month, team_id=team_id)
        days = data["days"]
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Plan Team")
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.3, right=0.3, top=0.4, bottom=0.4)
        FONT = "Times New Roman"

        def fmt(**kw):
            base = {"font_name": FONT, "font_size": 10, "valign": "vcenter"}
            base.update(kw)
            return wb.add_format(base)

        f_title = fmt(bold=True, font_size=15)
        f_sub = fmt(font_size=11, italic=True)
        f_head = fmt(bold=True, border=1, align="center", text_wrap=True, bg_color="#FCE4D6")
        f_head_sun = fmt(bold=True, border=1, align="center", bg_color="#FDD835")
        f_group = fmt(bold=True, border=1, bg_color="#B4C6E7")
        f_cell = fmt(border=1, text_wrap=True)
        f_center = fmt(border=1, align="center", text_wrap=True)
        f_day = fmt(border=1, align="center")
        f_sun = fmt(border=1, align="center", bg_color="#FFEB3B")
        colors = {"not_started": ("#E2E8F0", "#334155"), "in_progress": ("#FDBA74", "#7C2D12"),
                  "done": ("#86EFAC", "#14532D"), "overdue": ("#DC2626", "#FFFFFF")}
        f_state = {k: fmt(border=1, align="center", bold=True, bg_color=b, font_color=c) for k, (b, c) in colors.items()}

        # Người phụ trách = những người ở các cột Miền / Văn phòng (không lặp thêm cột riêng)
        cols = ["STT", "NỘI DUNG CÔNG VIỆC", "Miền Nam", "Miền ĐTT", "Miền Bắc", "Văn phòng",
                "Kiểm soát", "Bắt đầu", "Deadline", "KẾT QUẢ"]
        widths = [6, 40, 18, 18, 18, 18, 16, 11, 11, 14]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)
        d0 = len(cols)
        ws.set_column(d0, d0 + len(days) - 1, 3.6)
        note_col = d0 + len(days)
        ws.set_column(note_col, note_col, 28)
        last_col = note_col

        team_name = (data.get("team") or {}).get("name") or ("TẤT CẢ TEAM" if data.get("mode") == "all" else "")
        ws.merge_range(0, 0, 0, last_col, "PLAN TỔNG TEAM %s — %s" % (team_name.upper(), data["month_label"].upper()), f_title)
        st = data["summary"]["status"]
        total = data["summary"]["task_total"]
        ws.merge_range(1, 0, 1, last_col,
                       "Tổng %s việc · Hoàn thành %s · Đang thực hiện %s · Chưa bắt đầu %s · Trễ hạn %s · Tỷ lệ %s%%"
                       % (total, st["done"], st["in_progress"], st["not_started"], st["overdue"],
                          round(100.0 * st["done"] / total) if total else 0), f_sub)

        h1, h2 = 3, 4
        for i, title in enumerate(cols):
            if 2 <= i <= 5:
                continue
            ws.merge_range(h1, i, h2, i, title, f_head)
        ws.merge_range(h1, 2, h1, 5, "Nhân sự chính", f_head)
        for i in range(2, 6):
            ws.write(h2, i, cols[i], f_head)
        for i, d in enumerate(days):
            f = f_head_sun if d["sunday"] else f_head
            ws.write(h1, d0 + i, d["day"], f)
            ws.write(h2, d0 + i, d["wd"], f)
        ws.merge_range(h1, note_col, h2, note_col, "GHI CHÚ", f_head)
        ws.freeze_panes(h2 + 1, 2)

        f_dept = fmt(bold=True, border=1, font_size=11, bg_color="#1E293B", font_color="#FFFFFF")
        f_team = fmt(bold=True, border=1, bg_color="#DBE4EE")
        blocks = []
        for dept in data["departments"]:
            blocks.append(("dept", dept, None))
            for team in dept["teams"]:
                blocks.append(("team", team, None))
                for g in team["groups"]:
                    blocks.append(("group", g, team))

        row = h2 + 1
        for kind, obj, _team in blocks:
            if kind == "dept":
                ws.merge_range(row, 0, row, last_col, "%s (%s CV)" % (obj["name"], obj["task_total"]), f_dept)
                row += 1
                continue
            if kind == "team":
                ws.merge_range(row, 0, row, last_col, "Team: %s · %s thành viên · %s CV"
                               % (obj["name"], obj["member_count"], obj["task_total"]), f_team)
                row += 1
                continue
            g = obj
            ws.write(row, 0, g["code"], f_group)
            ws.merge_range(row, 1, row, last_col, "%s (%s CV)" % (g["name"], len(g["lines"])), f_group)
            row += 1
            for line in g["lines"]:
                values = [line["code"], line["name"] + ("  (lặp)" if line.get("plan_daily") else ""),
                          # Mỗi nhân sự 1 dòng trong ô miền
                          *["\n".join(p for p in (line[k] or "").split(", ") if p)
                            for k in ("south", "dtt", "north", "office")],
                          line["checker"], line["start"] or "—", line["deadline"] or "—", line["result"]]
                for i, v in enumerate(values):
                    ws.write(row, i, v, f_cell if i == 1 else f_center)
                for i, cell in enumerate(line["cells"]):
                    classes = cell["cls"].split()
                    s = next((k[3:] for k in classes if k.startswith("st-")), None)
                    if cell["mark"] and s in f_state:
                        ws.write(row, d0 + i, "x", f_state[s])
                    else:
                        ws.write(row, d0 + i, "", f_sun if "is-sun" in classes else f_day)
                ws.write(row, note_col, line.get("note") or "", f_cell)
                row += 1

        row += 1
        ws.write(row, 1, "Tổng hợp theo nhân sự", fmt(bold=True))
        row += 1
        heads = ["Nhân sự", "Tổng", "Hoàn thành", "Đang thực hiện", "Chưa bắt đầu", "Trễ hạn", "Duyệt Plan", "Team"]
        for i, h in enumerate(heads):
            ws.write(row, 1 + i, h, f_head)
        for m in data["members"]:
            row += 1
            appr = m.get("approval") or {}
            appr_txt = appr.get("state_label") or ""
            if appr.get("approver"):
                appr_txt += " (%s %s)" % (appr["approver"], appr.get("date") or "")
            if appr.get("reason"):
                appr_txt += " — %s" % appr["reason"]
            for i, v in enumerate([m["name"], m["total"], m["done"], m["in_progress"], m["not_started"],
                                   m["overdue"], appr_txt, m.get("team") or team_name]):
                ws.write(row, 1 + i, v, f_cell if i in (0, 6, 7) else f_center)

        wb.close()
        filename = "Plan_tong_team_%s_T%02d_%s.xlsx" % (
            re.sub(r"\W+", "_", team_name or "team").strip("_"), data["month"], data["year"])
        return {"file_base64": base64.b64encode(buffer.getvalue()).decode("ascii"), "filename": filename}

    @api.model
    def get_team_plan_overview(self, year=None, month=None, team_id=None):
        """Plan tổng nhóm theo Phòng ban → Team → Hạng mục → Công việc (giống bảng Hạng mục).

        team_id = "all" (quản lý): mọi team; ngược lại 1 team như get_team_plan_data.
        """
        Access = self.env["daily.task.assign.access"]
        is_manager = Access._is_manager()
        perms = self.env["daily.task.team.plan.access"].get_perms()
        teams = self._team_plan_teams()
        if team_id == "all" or (not team_id and is_manager):
            if not is_manager:
                raise AccessError("Chỉ Quản lý xem được Plan của tất cả team.")
            selected = teams
            mode = "all"
        else:
            first = self.get_team_plan_data(year=year, month=month, team_id=team_id)
            selected = self.env["daily.task.team"].browse(first["team"]["id"]) if first.get("team") else teams[:0]
            mode = "team"

        departments, dept_index = [], {}
        status = {"done": 0, "in_progress": 0, "not_started": 0, "overdue": 0}
        members, member_ids = [], set()
        days, month_label, y, m = [], "", year, month
        for team in selected:
            data = self.get_team_plan_data(year=year, month=month, team_id=team.id)
            days = days or data["days"]
            month_label, y, m = data["month_label"], data["year"], data["month"]
            for k in status:
                status[k] += (data["summary"]["status"] or {}).get(k, 0)
            for mem in data["members"]:
                if mem["id"] not in member_ids:
                    member_ids.add(mem["id"])
                    members.append({**mem, "team": team.name})
            dept = team.department_id
            dkey = dept.id or 0
            if dkey not in dept_index:
                dept_index[dkey] = {
                    "id": dkey,
                    "name": (dept.display_name if dept else "Chưa có phòng ban").upper(),
                    "teams": [],
                }
                departments.append(dept_index[dkey])
            for g in data["groups"]:
                g["key"] = "t%s-g%s" % (team.id, g["code"])
            dept_index[dkey]["teams"].append({
                "id": team.id,
                "name": team.name,
                "member_count": len(data["members"]),
                "task_total": data["summary"]["task_total"],
                "groups": data["groups"],
            })
        for d in departments:
            d["task_total"] = sum(t["task_total"] for t in d["teams"])
        return {
            "mode": mode,
            "year": y,
            "month": m,
            "month_label": month_label or "Tháng %02d/%s" % (int(month or 1), year),
            "team": {"id": selected[:1].id, "name": selected[:1].name} if mode == "team" and selected else False,
            "teams": [{"id": t.id, "name": t.name} for t in teams],
            "can_all": is_manager,
            "can_add": self._team_plan_can_add(),
            "can_write": bool(perms.get("write")),
            "can_unlink": bool(perms.get("unlink")),
            "members": members,
            "days": days,
            "departments": departments,
            "summary": {"status": status, "task_total": sum(status.values())},
        }

    @api.model
    def _team_plan_can_view(self):
        """Xem Plan tổng: theo Phân quyền Plan tổng (Quản lý module luôn được)."""
        return bool(self.env["daily.task.team.plan.access"].get_perms().get("view"))

    @api.model
    def _team_plan_can_add(self):
        """Thêm việc trên Plan tổng: theo Phân quyền Plan tổng (Quản lý module luôn được).
        Ràng buộc User quản lý hạng mục / team vẫn áp dụng thêm khi lưu (_check_category_manager)."""
        return bool(self.env["daily.task.team.plan.access"].get_perms().get("create"))

    @api.model
    def team_plan_update_line(self, line_id, vals):
        """Plan tổng: sửa Tên / Ngày bắt đầu / Deadline của dòng phân công (quyền Chỉnh sửa)."""
        if not self.env["daily.task.team.plan.access"].get_perms().get("write"):
            raise AccessError("Bạn không có quyền chỉnh sửa công việc trên Plan tổng.")
        line = self.sudo().browse(int(line_id or 0)).exists()
        if not line:
            raise UserError("Không tìm thấy dòng phân công.")
        vals = vals or {}
        name = (vals.get("name") or "").strip()
        if not name:
            raise UserError("Tên công việc không được để trống.")
        start, end = self._plan_parse_dates(vals.get("date_start"), vals.get("deadline"))
        line.write({"name": name, "date_start": start or False, "deadline": end or False})
        if line.plan_daily:
            # Việc lặp: mẫu lặp đã đổi tên; việc đã sinh mà chưa xong cũng đổi theo cho khớp Plan
            self.env["daily.task"].sudo().search([
                ("assign_line_id", "=", line.id), ("state", "!=", "done"), ("name", "!=", name),
            ]).with_context(from_daily_task_assign=True).write({"name": name})
        return True

    @api.model
    def team_plan_delete_line(self, line_id):
        """Plan tổng: xóa công việc (quyền Xóa).
        Lưu trữ dòng phân công; xóa việc cá nhân chưa bắt đầu, giữ việc đã làm để còn lịch sử."""
        if not self.env["daily.task.team.plan.access"].get_perms().get("unlink"):
            raise AccessError("Bạn không có quyền xóa công việc trên Plan tổng.")
        line = self.sudo().browse(int(line_id or 0)).exists()
        if not line:
            raise UserError("Không tìm thấy dòng phân công.")
        tasks = self.env["daily.task"].sudo().search([("assign_line_id", "=", line.id)])
        fresh = tasks.filtered(lambda t: t.state != "done" and not (t.completion_percent or 0))
        kept = len(tasks) - len(fresh)
        fresh.unlink()
        line.write({"active": False})
        return {"removed": len(fresh), "kept": kept}

    @api.model
    def _check_category_manager(self, wg, user=None):
        """Ràng buộc hạng mục: hạng mục đã có User quản lý → chỉ người đó (hoặc Quản lý module) thêm việc."""
        user = user or self.env.user
        if not wg or self.env["daily.task.assign.access"]._is_manager(user):
            return
        if user in wg.sudo().team_id.manager_ids:
            return
        managers = wg._category_managers()
        if managers and user not in managers:
            raise AccessError(
                "Hạng mục «%s» do %s quản lý — bạn không được thêm công việc vào hạng mục này."
                % (wg.name, ", ".join(managers.mapped("name")))
            )

    @api.model
    def get_team_plan_add_options(self, team_id=None):
        """Dữ liệu khung Thêm công việc của Plan tổng team: team, hạng mục, thành viên."""
        if not self._team_plan_can_add():
            raise AccessError("Bạn không có quyền thêm công việc cho team.")
        teams = self._team_plan_teams()
        # Thứ tự + số La Mã giống bảng Hạng mục
        board_cats = {}
        for dept in self.env["daily.task.work.group"].sudo().get_category_board_data().get("departments") or []:
            for bteam in dept.get("teams") or []:
                for cat in bteam.get("categories") or []:
                    tid = (cat.get("tasks") or [{}])[0].get("team_id") or False
                    board_cats.setdefault(tid, []).append({
                        "name": cat.get("name") or "",
                        "label": "%s. %s" % (cat.get("code"), cat.get("name")),
                        "managers": [m["id"] for m in cat.get("managers") or []],
                    })
        out = []
        for team in teams:
            cats = board_cats.get(team.id, [])
            members = self._team_plan_members(team)
            out.append({
                "id": team.id,
                "name": team.name,
                "categories": cats,
                "members": [{"id": u.id, "name": u.name} for u in members],
            })
        others = self.env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)], order="name")
        return {
            "teams": out,
            "users": [{"id": u.id, "name": u.name} for u in others],
            # Cột "User quản lý hạng mục" chỉ Quản lý module được chọn
            "can_set_manager": bool(self.env["daily.task.assign.access"]._is_manager()),
        }

    # Cột user của khung Thêm công việc → field trên Hạng mục (daily.task.work.group)
    _TEAM_ADD_WG_FIELDS = {
        "south_user_ids": "south_user_ids",
        "dtt_user_ids": "dtt_user_ids",
        "north_user_ids": "north_user_ids",
        "vptt_user_ids": "vptt_user_ids",
        "vpmb_user_ids": "vpmb_user_ids",
        "assignee_user_ids": "assignee_user_ids",
        "check_user_ids": "checker_user_ids",
        "detail_user_ids": "detail_user_ids",
        "detail_check_user_ids": "detail_check_user_ids",
        "total_user_ids": "total_user_ids",
    }

    @api.model
    def team_plan_create_line(self, vals):
        """Thêm việc chung của team từ Plan tổng team → dòng phân công (tự sinh việc cá nhân)."""
        if not self._team_plan_can_add():
            raise AccessError("Bạn không có quyền thêm công việc cho team.")
        vals = vals or {}
        name = (vals.get("name") or "").strip()
        if not name:
            raise UserError("Vui lòng nhập tên công việc.")
        team = self.env["daily.task.team"].sudo().browse(int(vals.get("team_id") or 0)).exists()
        if not team:
            raise UserError("Vui lòng chọn Team.")
        category = (vals.get("category") or "").strip()
        if not category:
            raise UserError("Vui lòng chọn Hạng mục.")
        regions = {
            key: [int(x) for x in (vals.get(key) or [])]
            for key in ("south_user_ids", "dtt_user_ids", "north_user_ids", "office_user_ids")
        }
        extra = {
            key: [int(x) for x in (vals.get(key) or [])]
            for key in ("vptt_user_ids", "vpmb_user_ids", "assignee_user_ids", "detail_user_ids",
                        "detail_check_user_ids", "total_user_ids")
        }
        # VPTT / VPMB là văn phòng → nhận việc như cột Văn phòng
        regions["office_user_ids"] = list(dict.fromkeys(
            regions["office_user_ids"] + extra["vptt_user_ids"] + extra["vpmb_user_ids"]
        ))
        if not (any(regions.values()) or extra["assignee_user_ids"]):
            raise UserError(
                "Vui lòng chọn ít nhất 1 nhân sự ở Miền Nam / Miền ĐTT / Miền Bắc / Văn phòng / VPTT / VPMB "
                "hoặc User phụ trách."
            )
        start, end = self._plan_parse_dates(vals.get("date_start"), vals.get("deadline"))
        WG = self.env["daily.task.work.group"].sudo()
        dept = team.department_id
        same_cat = WG.search([("active", "=", True), ("team_id", "=", team.id)]).filtered(
            lambda g: WG._norm_category_name(g.name).casefold() == category.casefold()
        )
        wg = same_cat.filtered(lambda g: (g.task_name or "").strip().casefold() == name.casefold())[:1]
        if not wg:
            # Thêm tên công việc vào bảng Hạng mục của team (đúng nhóm) để đồng bộ mọi màn hình
            wg = WG.create({
                "name": WG._norm_category_name(same_cat[:1].name) if same_cat else category,
                "task_name": name,
                "team_id": team.id,
                "department_id": (same_cat[:1].department_id or dept).id,
                "sequence": max(same_cat.mapped("sequence") or [10]),
            })
        self._check_category_manager(wg)
        check_ids = [int(x) for x in (vals.get("check_user_ids") or [])]
        if not check_ids:
            # Kiểm soát mặc định = User quản lý hạng mục
            check_ids = (wg._category_managers() or wg.sudo().team_id.manager_ids).ids
        line = self.sudo().with_context(skip_assign_expand=True).create([{
            "name": name,
            "work_group_id": wg.id,
            "category_group_id": wg.id,
            "department_id": wg.department_id.id or (dept.id if dept else False),
            "date_start": start or fields.Date.context_today(self),
            "deadline": end,
            "plan_daily": bool(vals.get("plan_daily")),
            "note": (vals.get("note") or "").strip() or False,
            "check_user_ids": [(6, 0, check_ids)],
            "assignee_user_ids": [(6, 0, extra["assignee_user_ids"])],
            "detail_user_ids": [(6, 0, extra["detail_user_ids"])],
            **{key: [(6, 0, ids)] for key, ids in regions.items()},
        }])
        # Gắn user lên dòng Hạng mục (chỉ thêm, không xóa user đang có)
        picked = dict(extra, check_user_ids=check_ids,
                      **{k: v for k, v in regions.items() if k != "office_user_ids"})
        wg_vals = {}
        for key, wg_field in self._TEAM_ADD_WG_FIELDS.items():
            add = [uid for uid in picked.get(key) or [] if uid not in wg[wg_field].ids]
            if add:
                wg_vals[wg_field] = [(4, uid) for uid in add]
        if wg_vals:
            wg.with_context(skip_link_users=True).write(wg_vals)
        # User quản lý hạng mục: chỉ Quản lý module, áp dụng cho cả hạng mục
        if "category_manager_ids" in vals and self.env["daily.task.assign.access"]._is_manager():
            mgr_ids = [int(x) for x in (vals.get("category_manager_ids") or [])]
            if set(mgr_ids) != set(wg._category_managers().ids):
                wg.set_category_managers(mgr_ids)
        return line.id