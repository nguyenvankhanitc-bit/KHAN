# -*- coding: utf-8 -*-

import calendar
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class DailyTaskRecurring(models.Model):
    """Mẫu công việc lặp — user khai báo 1 lần, cron 5h00 sinh daily.task mỗi ngày."""

    _name = "daily.task.recurring"
    _description = "Công việc lặp lại"
    _order = "active desc, name, id desc"

    name = fields.Char(string="Tên công việc", required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Người khai báo",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        index=True,
        ondelete="cascade",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        index=True,
        ondelete="set null",
    )
    work_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        index=True,
        ondelete="restrict",
        domain="[('department_id', '=', department_id)]",
    )
    duration_minutes = fields.Integer(string="Thời gian (phút)", default=0)
    priority = fields.Selection(
        [
            ("high", "Cao"),
            ("medium", "Trung bình"),
            ("low", "Thấp"),
        ],
        string="Mức ưu tiên",
        default="medium",
        required=True,
    )
    recurrence_type = fields.Selection(
        [
            ("daily", "Hằng ngày"),
            ("weekly", "Theo tuần"),
            ("monthly", "Theo tháng"),
            ("yearly", "Cố định ngày"),
        ],
        string="Chu kỳ lặp",
        default="daily",
        required=True,
        index=True,
    )
    recurrence_weekdays = fields.Char(
        string="Các thứ trong tuần",
        default="0,1,2,3,4",
        help="Danh sách thứ dạng 0=Thứ 2 … 6=Chủ nhật.",
    )
    recurrence_day = fields.Integer(
        string="Ngày trong tháng",
        default=1,
        help="Ngày tạo việc đối với chu kỳ theo tháng.",
    )
    recurrence_month = fields.Integer(
        string="Tháng cố định",
        default=1,
        help="Tháng tạo việc đối với chu kỳ cố định ngày.",
    )
    note = fields.Text(string="Ghi chú")
    active = fields.Boolean(
        string="Đang lặp",
        default=True,
        help="Tắt để tạm dừng tạo việc mỗi sáng (không xóa mẫu).",
    )
    skip_saturday = fields.Boolean(
        string="Bỏ qua Thứ 7",
        default=False,
        help="Nếu bật, không tạo công việc vào thứ Bảy.",
    )
    skip_sunday = fields.Boolean(
        string="Bỏ qua Chủ nhật",
        default=False,
        help="Nếu bật, không tạo công việc vào Chủ nhật.",
    )
    skip_weekend = fields.Boolean(
        string="Bỏ qua T7–CN",
        default=False,
        help="Tương thích cũ: tương đương bỏ qua cả Thứ 7 và Chủ nhật.",
    )
    deadline_offset_days = fields.Integer(
        string="Hạn = ngày giao + N ngày",
        default=0,
        help="0 = hạn trong ngày. Ví dụ 1 = hạn ngày hôm sau.",
    )
    last_generated_date = fields.Date(
        string="Ngày sinh gần nhất",
        readonly=True,
        copy=False,
    )
    task_ids = fields.One2many(
        "daily.task",
        "recurring_id",
        string="Công việc đã sinh",
    )
    task_count = fields.Integer(compute="_compute_task_count", string="Số lần đã tạo")

    @api.depends("task_ids")
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.constrains("duration_minutes")
    def _check_duration_minutes(self):
        for rec in self:
            if rec.duration_minutes is not None and rec.duration_minutes < 0:
                raise ValidationError("Thời gian thực hiện (phút) không được âm.")

    @api.constrains("deadline_offset_days")
    def _check_deadline_offset(self):
        for rec in self:
            if rec.deadline_offset_days is not None and rec.deadline_offset_days < 0:
                raise ValidationError("Số ngày cộng hạn không được âm.")

    @api.constrains("recurrence_day", "recurrence_month")
    def _check_recurrence_date(self):
        for rec in self:
            if not 1 <= int(rec.recurrence_day or 0) <= 31:
                raise ValidationError("Ngày lặp phải từ 1 đến 31.")
            if not 1 <= int(rec.recurrence_month or 0) <= 12:
                raise ValidationError("Tháng lặp phải từ 1 đến 12.")

    @api.constrains("work_group_id", "department_id")
    def _check_work_group_department(self):
        for rec in self:
            if (
                rec.work_group_id
                and rec.department_id
                and rec.work_group_id.department_id
                and rec.work_group_id.department_id != rec.department_id
            ):
                raise ValidationError(
                    "Hạng mục phải thuộc cùng phòng ban với mẫu công việc lặp."
                )

    def _to_dict(self):
        self.ensure_one()
        wg = self.sudo().work_group_id
        return {
            "id": self.id,
            "name": self.name or "",
            "work_group_id": wg.id if wg else False,
            "work_group_label": (wg.name or "") if wg else "",
            "duration_minutes": int(self.duration_minutes or 0),
            "priority": self.priority or "medium",
            "priority_label": dict(self._fields["priority"].selection).get(
                self.priority, ""
            )
            or "",
            "recurrence_type": self.recurrence_type or "daily",
            "recurrence_label": dict(self._fields["recurrence_type"].selection).get(
                self.recurrence_type, ""
            )
            or "",
            "recurrence_weekdays": self._weekday_values(),
            "recurrence_weekdays_label": self._weekday_label(),
            "recurrence_day": int(self.recurrence_day or 1),
            "recurrence_month": int(self.recurrence_month or 1),
            "note": self.note or "",
            "active": bool(self.active),
            "skip_saturday": bool(self.skip_saturday or self.skip_weekend),
            "skip_sunday": bool(self.skip_sunday or self.skip_weekend),
            "skip_weekend": bool(
                (self.skip_saturday or self.skip_weekend)
                and (self.skip_sunday or self.skip_weekend)
            ),
            "deadline_offset_days": int(self.deadline_offset_days or 0),
            "last_generated_date": self.last_generated_date.isoformat()
            if self.last_generated_date
            else "",
            "last_generated_display": self.last_generated_date.strftime("%d/%m/%Y")
            if self.last_generated_date
            else "—",
            "task_count": int(self.task_count or 0),
        }

    def _weekday_values(self):
        self.ensure_one()
        result = []
        for value in (self.recurrence_weekdays or "").split(","):
            try:
                day = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= day <= 6 and day not in result:
                result.append(day)
        return sorted(result)

    def _weekday_label(self):
        self.ensure_one()
        labels = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
        values = self._weekday_values()
        return ", ".join(labels[day] for day in values) if values else "Chưa chọn thứ"

    @api.model
    def _my_hr_employee(self):
        return self.env["hr.employee"].search(
            [("user_id", "=", self.env.user.id)],
            limit=1,
        )

    @api.model
    def _validate_work_group(self, work_group_id, department_id):
        if not work_group_id:
            return False
        group = self.env["daily.task.work.group"].sudo().browse(work_group_id)
        if not group.exists() or not group.active:
            raise ValidationError("Hạng mục không hợp lệ.")
        if department_id and group.department_id.id != department_id:
            raise ValidationError(
                "Bạn chỉ được chọn hạng mục của phòng ban mình."
            )
        if group.user_ids and self.env.uid not in group.user_ids.ids:
            raise ValidationError(
                "Bạn không nằm trong danh sách User áp dụng của hạng mục này."
            )
        return group.id

    @api.model
    def get_my_recurring(self):
        """Bootstrap danh sách mẫu lặp của user đang đăng nhập."""
        emp = self._my_hr_employee()
        priorities = [
            {"value": k, "label": v}
            for k, v in self._fields["priority"].selection
        ]
        recurrence_types = [
            {"value": k, "label": v}
            for k, v in self._fields["recurrence_type"].selection
        ]
        if not emp:
            return {
                "employee": False,
                "items": [],
                "priorities": priorities,
                "recurrence_types": recurrence_types,
                "work_groups": [],
                "message": "Tài khoản chưa gắn hồ sơ nhân viên (hr.employee).",
            }
        dept_id = emp.department_id.id if emp.department_id else False
        work_groups = self.env["daily.task.work.group"].get_groups_for_user(
            department_id=dept_id,
            user_id=self.env.uid,
        )
        items = self.search(
            [("user_id", "=", self.env.uid)],
            order="active desc, name, id desc",
        )
        return {
            "employee": {
                "id": emp.id,
                "name": emp.name or "",
                "department_id": dept_id or False,
            },
            "items": [r._to_dict() for r in items],
            "priorities": priorities,
            "recurrence_types": recurrence_types,
            "work_groups": work_groups,
            "message": False,
        }

    @api.model
    def create_from_employee(self, vals):
        """Nhân viên tự khai báo mẫu lặp."""
        emp = self._my_hr_employee()
        if not emp:
            raise ValidationError(
                "Tài khoản chưa gắn hồ sơ nhân viên. Liên hệ quản trị để liên kết User với Employee."
            )
        name = (vals.get("name") or "").strip()
        if not name:
            raise ValidationError("Vui lòng nhập tên công việc lặp.")
        department_id = emp.department_id.id if emp.department_id else False
        work_group_id = self._validate_work_group(
            int(vals.get("work_group_id") or 0) or False,
            department_id,
        )
        try:
            duration_minutes = int(vals.get("duration_minutes") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Thời gian thực hiện (phút) phải là số nguyên.") from exc
        if duration_minutes < 0:
            raise ValidationError("Thời gian thực hiện (phút) không được âm.")
        try:
            offset = int(vals.get("deadline_offset_days") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Số ngày cộng hạn phải là số nguyên.") from exc
        if offset < 0:
            raise ValidationError("Số ngày cộng hạn không được âm.")
        recurrence_vals = self._sanitize_recurrence_vals(vals)

        rec = self.create(
            {
                "name": name,
                "user_id": self.env.uid,
                "employee_id": emp.id,
                "department_id": department_id,
                "work_group_id": work_group_id,
                "duration_minutes": duration_minutes,
                "priority": vals.get("priority") or "medium",
                **recurrence_vals,
                "note": vals.get("note") or "",
                "active": True if vals.get("active", True) else False,
                **self._sanitize_skip_vals(vals),
                "deadline_offset_days": offset,
            }
        )
        # Tạo luôn việc hôm nay nếu đang bật — không chờ tới 5h sáng mai
        if rec.active:
            try:
                rec._generate_task_for_date(fields.Date.context_today(self))
            except Exception:  # noqa: BLE001 — không chặn lưu mẫu
                _logger.exception(
                    "Không tạo được việc hôm nay từ mẫu lặp %s", rec.id
                )
        return rec._to_dict()

    @api.model
    def _sanitize_recurrence_vals(self, vals):
        recurrence_type = vals.get("recurrence_type") or "daily"
        allowed_types = dict(self._fields["recurrence_type"].selection)
        if recurrence_type not in allowed_types:
            raise ValidationError("Chu kỳ lặp không hợp lệ.")
        raw_weekdays = vals.get("recurrence_weekdays", [0, 1, 2, 3, 4])
        if not isinstance(raw_weekdays, (list, tuple)):
            raw_weekdays = []
        weekdays = sorted(
            {
                int(day)
                for day in raw_weekdays
                if str(day).lstrip("-").isdigit() and 0 <= int(day) <= 6
            }
        )
        if recurrence_type == "weekly" and not weekdays:
            raise ValidationError("Vui lòng chọn ít nhất một thứ trong tuần.")
        try:
            recurrence_day = int(vals.get("recurrence_day") or 1)
            recurrence_month = int(vals.get("recurrence_month") or 1)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Ngày/tháng lặp không hợp lệ.") from exc
        if not 1 <= recurrence_day <= 31:
            raise ValidationError("Ngày lặp phải từ 1 đến 31.")
        if not 1 <= recurrence_month <= 12:
            raise ValidationError("Tháng lặp phải từ 1 đến 12.")
        return {
            "recurrence_type": recurrence_type,
            "recurrence_weekdays": ",".join(str(day) for day in weekdays),
            "recurrence_day": recurrence_day,
            "recurrence_month": recurrence_month,
        }

    @api.model
    def _sanitize_skip_vals(self, vals):
        """Chuẩn hóa bỏ qua T7 / CN — hỗ trợ cả flag cũ skip_weekend."""
        has_split = "skip_saturday" in vals or "skip_sunday" in vals
        if has_split:
            skip_saturday = bool(vals.get("skip_saturday"))
            skip_sunday = bool(vals.get("skip_sunday"))
        elif "skip_weekend" in vals:
            skip_saturday = skip_sunday = bool(vals.get("skip_weekend"))
        else:
            skip_saturday = skip_sunday = False
        return {
            "skip_saturday": skip_saturday,
            "skip_sunday": skip_sunday,
            "skip_weekend": skip_saturday and skip_sunday,
        }

    def update_from_employee(self, vals):
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.user.has_group(
            "daily_work_task.group_daily_work_manager"
        ):
            raise AccessError("Bạn chỉ được sửa mẫu công việc lặp của mình.")
        vals = vals or {}
        write_vals = {}
        if "name" in vals:
            name = (vals.get("name") or "").strip()
            if not name:
                raise ValidationError("Vui lòng nhập tên công việc lặp.")
            write_vals["name"] = name
        if "priority" in vals:
            write_vals["priority"] = vals.get("priority") or "medium"
        if "note" in vals:
            write_vals["note"] = vals.get("note") or ""
        if "active" in vals:
            write_vals["active"] = bool(vals.get("active"))
        if any(key in vals for key in ("skip_saturday", "skip_sunday", "skip_weekend")):
            write_vals.update(self._sanitize_skip_vals(vals))
        if any(
            key in vals
            for key in (
                "recurrence_type",
                "recurrence_weekdays",
                "recurrence_day",
                "recurrence_month",
            )
        ):
            recurrence_source = {
                "recurrence_type": vals.get("recurrence_type", self.recurrence_type),
                "recurrence_weekdays": vals.get(
                    "recurrence_weekdays", self._weekday_values()
                ),
                "recurrence_day": vals.get("recurrence_day", self.recurrence_day),
                "recurrence_month": vals.get(
                    "recurrence_month", self.recurrence_month
                ),
            }
            write_vals.update(self._sanitize_recurrence_vals(recurrence_source))
        if "duration_minutes" in vals:
            try:
                duration_minutes = int(vals.get("duration_minutes") or 0)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "Thời gian thực hiện (phút) phải là số nguyên."
                ) from exc
            if duration_minutes < 0:
                raise ValidationError("Thời gian thực hiện (phút) không được âm.")
            write_vals["duration_minutes"] = duration_minutes
        if "deadline_offset_days" in vals:
            try:
                offset = int(vals.get("deadline_offset_days") or 0)
            except (TypeError, ValueError) as exc:
                raise ValidationError("Số ngày cộng hạn phải là số nguyên.") from exc
            if offset < 0:
                raise ValidationError("Số ngày cộng hạn không được âm.")
            write_vals["deadline_offset_days"] = offset
        if "work_group_id" in vals:
            dept_id = self.department_id.id if self.department_id else False
            write_vals["work_group_id"] = self._validate_work_group(
                int(vals.get("work_group_id") or 0) or False,
                dept_id,
            )
        if write_vals:
            self.write(write_vals)
        return self._to_dict()

    def unlink_from_employee(self):
        for rec in self:
            if rec.user_id.id != self.env.uid and not self.env.user.has_group(
                "daily_work_task.group_daily_work_manager"
            ):
                raise AccessError("Bạn chỉ được xóa mẫu công việc lặp của mình.")
        self.unlink()
        return True

    def toggle_active_from_employee(self):
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.user.has_group(
            "daily_work_task.group_daily_work_manager"
        ):
            raise AccessError("Bạn chỉ được bật/tắt mẫu của mình.")
        self.active = not self.active
        if self.active:
            try:
                self._generate_task_for_date(fields.Date.context_today(self))
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "Không tạo được việc hôm nay khi bật mẫu lặp %s", self.id
                )
        return self._to_dict()

    def generate_today_from_employee(self):
        """Nút thủ công: tạo việc hôm nay từ mẫu (nếu chưa có)."""
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.user.has_group(
            "daily_work_task.group_daily_work_manager"
        ):
            raise AccessError("Bạn chỉ được tạo việc từ mẫu của mình.")
        if not self.active:
            raise ValidationError("Mẫu đang tắt. Hãy bật lặp trước khi tạo việc.")
        task = self._generate_task_for_date(fields.Date.context_today(self))
        return {
            "recurring": self._to_dict(),
            "created": bool(task),
            "task_id": task.id if task else False,
        }

    def _should_generate_on(self, day):
        self.ensure_one()
        if not self.active:
            return False
        weekday = day.weekday()
        skip_saturday = bool(self.skip_saturday or self.skip_weekend)
        skip_sunday = bool(self.skip_sunday or self.skip_weekend)
        if weekday == 5 and skip_saturday:
            return False
        if weekday == 6 and skip_sunday:
            return False
        recurrence_type = self.recurrence_type or "daily"
        if recurrence_type == "weekly":
            return day.weekday() in self._weekday_values()
        if recurrence_type == "monthly":
            return day.day == min(
                int(self.recurrence_day or 1),
                calendar.monthrange(day.year, day.month)[1],
            )
        if recurrence_type == "yearly":
            if day.month != int(self.recurrence_month or 1):
                return False
            return day.day == min(
                int(self.recurrence_day or 1),
                calendar.monthrange(day.year, day.month)[1],
            )
        return True

    def _generate_task_for_date(self, day):
        """Sinh 1 daily.task cho ngày `day`. Trả về task mới hoặc False nếu đã có / bỏ qua."""
        self.ensure_one()
        if not day:
            day = fields.Date.context_today(self)
        if not self._should_generate_on(day):
            return False

        Task = self.env["daily.task"].sudo()
        existing = Task.search(
            [
                ("recurring_id", "=", self.id),
                ("assign_date", "=", day),
            ],
            limit=1,
        )
        if existing:
            return False

        emp = self.employee_id
        if not emp or not emp.exists():
            _logger.warning(
                "Mẫu lặp %s thiếu employee — bỏ qua ngày %s", self.id, day
            )
            return False

        bridge = (
            self.env["daily.task.employee"]
            .sudo()
            .get_or_create_from_hr(emp.id)
        )
        from datetime import timedelta

        deadline = day + timedelta(days=int(self.deadline_offset_days or 0))
        assigner_uid = self.user_id.id or self.env.uid

        # Làm mới phòng ban / hạng mục nếu NV đổi dept
        department_id = (
            emp.department_id.id
            if emp.department_id
            else (self.department_id.id if self.department_id else False)
        )
        work_group_id = self.work_group_id.id if self.work_group_id else False
        if work_group_id and department_id:
            group = self.work_group_id.sudo()
            if group.department_id and group.department_id.id != department_id:
                work_group_id = False

        task = Task.with_context(daily_task_assigner_uid=assigner_uid).create(
            {
                "name": self.name,
                "assign_date": day,
                "assigned_by_id": assigner_uid,
                "deadline": deadline,
                "department_id": department_id,
                "assignee_id": bridge.id,
                "work_group_id": work_group_id,
                "duration_minutes": int(self.duration_minutes or 0),
                "priority": self.priority or "medium",
                "state": "not_started",
                "note": self.note or "",
                "recurring_id": self.id,
            }
        )
        self.sudo().write({"last_generated_date": day})
        return task

    @api.model
    def cron_generate_recurring_tasks(self):
        """Cron ~5h00: tạo công việc ngày hôm nay từ mọi mẫu đang bật."""
        today = fields.Date.context_today(self)
        templates = self.sudo().search([("active", "=", True)])
        created = 0
        skipped = 0
        for tpl in templates:
            try:
                task = tpl._generate_task_for_date(today)
                if task:
                    created += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001 — một mẫu lỗi không dừng cả cron
                _logger.exception(
                    "Lỗi sinh việc lặp từ mẫu %s (ngày %s)", tpl.id, today
                )
        _logger.info(
            "Cron công việc lặp: ngày=%s, tạo=%s, bỏ qua=%s, mẫu=%s",
            today,
            created,
            skipped,
            len(templates),
        )
        return True
