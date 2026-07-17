# -*- coding: utf-8 -*-

import logging
from html import escape

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class DailyTask(models.Model):
    _name = "daily.task"
    _description = "Công việc hàng ngày"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline asc, priority asc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Tên công việc", required=True, tracking=True)
    assign_date = fields.Date(
        string="Ngày giao việc",
        default=fields.Date.context_today,
        tracking=True,
        index=True,
        help="Ngày giao / tạo việc. Mặc định = ngày hiện tại.",
    )
    assigned_by_id = fields.Many2one(
        "res.users",
        string="Người giao việc",
        tracking=True,
        index=True,
        ondelete="set null",
        help="User đã giao / tạo công việc này.",
    )
    deadline = fields.Date(string="Hạn hoàn thành", required=True, tracking=True, index=True)
    department_id = fields.Many2one(
        "hr.department",
        string="Bộ phận",
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    assignee_id = fields.Many2one(
        "daily.task.employee",
        string="Người phụ trách",
        required=True,
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    employee_hr_id = fields.Many2one(
        related="assignee_id.employee_id",
        string="Hồ sơ nhân viên",
        store=True,
        readonly=True,
    )
    priority = fields.Selection(
        [
            ("high", "Cao"),
            ("medium", "Trung bình"),
            ("low", "Thấp"),
        ],
        string="Mức ưu tiên",
        default="medium",
        required=True,
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("not_started", "Chưa bắt đầu"),
            ("in_progress", "Đang xử lý"),
            ("done", "Đã hoàn thành"),
        ],
        string="Trạng thái",
        default="not_started",
        required=True,
        tracking=True,
        index=True,
    )
    note = fields.Text(string="Ghi chú")
    work_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        index=True,
        ondelete="restrict",
        tracking=True,
        domain="[('department_id', '=', department_id)]",
        help="Hạng mục công việc theo phòng ban (nhóm CV).",
    )
    duration_minutes = fields.Integer(
        string="Thời gian thực hiện (phút)",
        default=0,
        tracking=True,
        help="Nhập số phút thực hiện công việc (vd: 60).",
    )
    duration_hours = fields.Float(
        string="Tổng thời gian thực hiện (giờ)",
        compute="_compute_duration_hours",
        store=True,
        digits=(16, 2),
        help="Tự tính = phút / 60.",
    )
    completion_percent = fields.Integer(
        string="% hoàn thành CV",
        default=0,
        tracking=True,
        help="Nhập % hoàn thành công việc (0–100). Khi trạng thái = Đã hoàn thành sẽ tự = 100.",
    )
    is_overdue = fields.Boolean(
        string="Quá hạn",
        compute="_compute_is_overdue",
        store=True,
        index=True,
    )
    color = fields.Integer(
        string="Màu lịch",
        compute="_compute_color",
        store=True,
        help="Màu trên Calendar theo trạng thái: xanh=hoàn thành, vàng=đang xử lý, xám=chưa bắt đầu, đỏ=quá hạn.",
    )
    recurring_id = fields.Many2one(
        "daily.task.recurring",
        string="Mẫu lặp",
        index=True,
        ondelete="set null",
        copy=False,
        help="Công việc được sinh tự động từ mẫu lặp (cron 5h00).",
    )

    _recurring_assign_date_uniq = models.Constraint(
        "unique(recurring_id, assign_date)",
        "Công việc lặp này đã được tạo cho ngày đó.",
    )

    @api.depends("duration_minutes")
    def _compute_duration_hours(self):
        for rec in self:
            minutes = rec.duration_minutes or 0
            rec.duration_hours = round(minutes / 60.0, 2) if minutes else 0.0

    @api.constrains("duration_minutes")
    def _check_duration_minutes(self):
        for rec in self:
            if rec.duration_minutes is not None and rec.duration_minutes < 0:
                raise ValidationError("Thời gian thực hiện (phút) không được âm.")

    @api.constrains("completion_percent")
    def _check_completion_percent(self):
        for rec in self:
            pct = rec.completion_percent
            if pct is not None and (pct < 0 or pct > 100):
                raise ValidationError("% hoàn thành CV phải từ 0 đến 100.")

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
                    "Nhóm công việc phải thuộc cùng phòng ban với công việc."
                )

    @api.depends("deadline", "state")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(
                rec.deadline and rec.state != "done" and rec.deadline < today
            )

    def _is_overdue_today(self):
        """Quá hạn đang mở: đã qua hạn và chưa hoàn thành (cho KPI / nhắc mail)."""
        self.ensure_one()
        return self.state != "done" and self._days_past_deadline() > 0

    def _days_past_deadline(self):
        """Số ngày đã trễ so với hạn (không phụ thuộc trạng thái hoàn thành)."""
        self.ensure_one()
        if not self.deadline:
            return 0
        today = fields.Date.context_today(self)
        if self.deadline >= today:
            return 0
        return (today - self.deadline).days

    def _overdue_days(self):
        """Số ngày trễ hiển thị cột Quá hạn — giữ cả khi đã hoàn thành."""
        return self._days_past_deadline()

    @api.depends("state", "is_overdue")
    def _compute_color(self):
        # Index khớp palette Odoo calendar (o_calendar_color_N):
        # 0 xám, 1 đỏ, 3 vàng, 10 xanh lá
        mapping = {
            "done": 10,  # Đã hoàn thành — xanh (giống badge)
            "in_progress": 3,  # Đang xử lý — vàng
            "not_started": 0,  # Chưa bắt đầu — xám
        }
        for rec in self:
            if rec.is_overdue:
                rec.color = 1  # Quá hạn — đỏ
            else:
                rec.color = mapping.get(rec.state, 0)

    def action_set_not_started(self):
        for rec in self:
            if not rec._can_edit_task():
                raise AccessError("Bạn không được cập nhật trạng thái công việc này.")
        self.write({"state": "not_started"})

    def action_set_in_progress(self):
        for rec in self:
            if not rec._can_edit_task():
                raise AccessError("Bạn không được cập nhật trạng thái công việc này.")
        self.write({"state": "in_progress"})

    def action_set_done(self):
        for rec in self:
            if not rec._can_edit_task():
                raise AccessError("Bạn không được cập nhật trạng thái công việc này.")
        self.write({"state": "done", "completion_percent": 100})

    def write(self, vals):
        vals = dict(vals)
        if vals.get("state") == "done" and "completion_percent" not in vals:
            vals["completion_percent"] = 100
        return super().write(vals)

    def _assigner_uid(self):
        """UID người thật sự thao tác — không lấy OdooBot khi đang sudo()."""
        return (
            self.env.context.get("daily_task_assigner_uid")
            or (False if self.env.su else self.env.uid)
            or self.env.uid
        )

    @api.model_create_multi
    def create(self, vals_list):
        assigner = self._assigner_uid()
        for vals in vals_list:
            if not vals.get("assigned_by_id") and assigner:
                vals["assigned_by_id"] = assigner
            # Tránh default/sudo ghi OdooBot đè người giao thật
            if vals.get("assigned_by_id") in (1, False, None) and assigner and assigner != 1:
                vals["assigned_by_id"] = assigner
        return super().create(vals_list)

    def _assignee_user(self):
        """User của người được giao — đọc SQL tránh HR ACL chặn."""
        self.ensure_one()
        hr = self.assignee_id.employee_id
        if not hr:
            return self.env["res.users"]
        self.env.cr.execute(
            """
            SELECT e.user_id
              FROM hr_employee e
             WHERE e.id = %s
               AND e.user_id IS NOT NULL
            """,
            (hr.id,),
        )
        row = self.env.cr.fetchone()
        if not row or not row[0]:
            return self.env["res.users"]
        return self.env["res.users"].sudo().browse(row[0]).exists()

    def _get_assign_bot_user(self):
        bot_user = self.env.ref(
            "daily_work_task.user_bot_assign_task", raise_if_not_found=False
        )
        if not bot_user:
            bot_user = self.env.ref("base.user_root", raise_if_not_found=False)
        return bot_user

    def _ensure_assign_bot_avatar(self, bot_user):
        """Mượn avatar bot duyệt đơn (nếu có) — không phụ thuộc module khác."""
        if not bot_user or not bot_user.partner_id or bot_user.partner_id.image_1920:
            return
        src = self.env.ref(
            "business_discuss_bots.partner_bot_approval", raise_if_not_found=False
        )
        if src and src.image_1920:
            bot_user.partner_id.sudo().write({"image_1920": src.image_1920})

    def _post_assign_bot_discuss_message(self, recipient_user, body):
        """Discuss DM từ OdooBot Giao việc (cùng kiểu OdooBot Duyệt đơn)."""
        Message = self.env["mail.message"]
        if not recipient_user or recipient_user.share or not recipient_user.partner_id:
            return Message
        bot_user = self._get_assign_bot_user()
        if not bot_user or not bot_user.partner_id:
            return Message
        self._ensure_assign_bot_avatar(bot_user)
        bot_partner = bot_user.partner_id
        try:
            chat = (
                self.env["discuss.channel"]
                .sudo()
                .with_user(recipient_user)
                ._get_or_create_chat([bot_partner.id], pin=True)
            )
            # Ghim chat cho người nhận + cập nhật interest để hiện trên Discuss
            member = chat.sudo().channel_member_ids.filtered(
                lambda m: m.partner_id == recipient_user.partner_id
            )[:1]
            if member:
                member.write(
                    {
                        "unpin_dt": False,
                        "last_interest_dt": fields.Datetime.now(),
                    }
                )
            msg = (
                chat.with_user(bot_user)
                .sudo()
                .with_context(business_bot_skip_apply_logic=True)
                .message_post(
                    body=body,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    author_id=bot_partner.id,
                )
            )
            # Broadcast để systray/Discuss nhận tin ngay (kể cả user đang online)
            chat.sudo()._broadcast(recipient_user.partner_id.ids)
            if member:
                try:
                    from odoo.addons.mail.tools.discuss import Store

                    payload = {
                        "channel_id": chat.id,
                        "data": Store(bus_channel=member._bus_channel())
                        .add(chat)
                        .add(member, "unpin_dt")
                        .get_result(),
                    }
                    member._bus_send("discuss.channel/joined", payload)
                except Exception:
                    _logger.debug(
                        "daily_work_task: bus joined skip channel=%s", chat.id,
                        exc_info=True,
                    )
            return msg
        except Exception:
            _logger.exception(
                "daily_work_task: Discuss DM giao việc thất bại user_id=%s",
                recipient_user.id,
            )
            return Message

    def _notify_assignee_assigned(self):
        """Thông báo Discuss/Inbox/Activity khi giao việc (giống OdooBot Duyệt đơn)."""
        for task in self:
            try:
                recipient = task._assignee_user()
                assigner = task.assigned_by_id or self.env.user
                if not recipient or not recipient.partner_id:
                    _logger.warning(
                        "daily_work_task: bỏ qua notify task_id=%s — NV chưa gắn User",
                        task.id,
                    )
                    continue

                assigner_name = assigner.name or "—"
                assignee_name = recipient.name or "—"
                deadline = (
                    task.deadline.strftime("%d/%m/%Y") if task.deadline else "—"
                )
                assign_date = (
                    task.assign_date.strftime("%d/%m/%Y")
                    if task.assign_date
                    else "—"
                )
                priority = dict(task._fields["priority"].selection).get(
                    task.priority, ""
                ) or "—"
                note = (task.note or "").strip() or "—"
                dept = (
                    task.department_id.display_name if task.department_id else "—"
                )

                body_assignee = Markup(
                    "<b>CÔNG VIỆC ĐƯỢC GIAO</b><br/>"
                    "Người giao: <b>{assigner}</b><br/>"
                    "Công việc: <b>{name}</b><br/>"
                    "Ngày giao: <b>{assign_date}</b><br/>"
                    "Hạn hoàn thành: <b>{deadline}</b><br/>"
                    "Ưu tiên: <b>{priority}</b><br/>"
                    "Bộ phận: <b>{dept}</b><br/>"
                    "Ghi chú: <b>{note}</b><br/><br/>"
                    "Vào menu <b>Công việc hàng ngày → Nhân viên nhập CV</b> để xử lý."
                ).format(
                    assigner=escape(str(assigner_name)),
                    name=escape(str(task.name or "")),
                    assign_date=escape(assign_date),
                    deadline=escape(deadline),
                    priority=escape(str(priority)),
                    dept=escape(str(dept)),
                    note=escape(str(note)),
                )

                # Người nhận việc → Discuss + Inbox + Activity
                if recipient.id != assigner.id:
                    task._post_assign_bot_discuss_message(recipient, body_assignee)
                    bot_user = task._get_assign_bot_user()
                    task.sudo().message_post(
                        body=body_assignee,
                        partner_ids=recipient.partner_id.ids,
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                        author_id=bot_user.partner_id.id
                        if bot_user and bot_user.partner_id
                        else None,
                    )
                    act_type = self.env.ref(
                        "daily_work_task.mail_act_daily_task_assigned",
                        raise_if_not_found=False,
                    )
                    if act_type:
                        task.sudo().activity_schedule(
                            act_type_xmlid="daily_work_task.mail_act_daily_task_assigned",
                            user_id=recipient.id,
                            summary="Công việc được giao: %s" % (task.name or ""),
                            note=body_assignee,
                            date_deadline=task.deadline
                            or fields.Date.context_today(task),
                        )

                # Người giao → tin ngắn để thấy chat «OdooBot Giao việc» trên Discuss
                if assigner and assigner.partner_id and not assigner.share:
                    body_assigner = Markup(
                        "<b>ĐÃ GIAO VIỆC</b><br/>"
                        "Đã gửi thông báo cho: <b>{assignee}</b><br/>"
                        "Công việc: <b>{name}</b><br/>"
                        "Hạn: <b>{deadline}</b><br/>"
                        "Người nhận sẽ thấy tin từ <b>OdooBot Giao việc</b> "
                        "trong Discuss (giống OdooBot Duyệt đơn)."
                    ).format(
                        assignee=escape(str(assignee_name)),
                        name=escape(str(task.name or "")),
                        deadline=escape(deadline),
                    )
                    task._post_assign_bot_discuss_message(assigner, body_assigner)
            except Exception:
                _logger.exception(
                    "daily_work_task: thông báo giao việc thất bại task_id=%s",
                    task.id,
                )

    @api.model
    def cron_recompute_overdue(self):
        """Cập nhật cờ quá hạn mỗi ngày (phụ thuộc ngày hiện tại)."""
        tasks = self.search([("state", "!=", "done")])
        tasks._compute_is_overdue()
        tasks._compute_color()
        done = self.search([("state", "=", "done"), ("is_overdue", "=", True)])
        if done:
            done._compute_is_overdue()
            done._compute_color()
        # Đảm bảo ghi xuống DB (field store)
        (tasks | done).flush_recordset(["is_overdue", "color"])
        return True

    @api.model
    def _refresh_overdue_flags(self, tasks=None):
        """Đồng bộ cờ quá hạn trước khi trả API / mở bảng tháng."""
        if tasks is None:
            self.cron_recompute_overdue()
            return self.browse()
        todo = tasks.filtered(lambda t: t.state != "done") | tasks.filtered("is_overdue")
        if todo:
            todo._compute_is_overdue()
            todo._compute_color()
            todo.flush_recordset(["is_overdue", "color"])
        return tasks

    @api.model
    def get_overdue_tasks(self, assignee_id=False):
        domain = [("is_overdue", "=", True)]
        if assignee_id:
            domain.append(("assignee_id", "=", int(assignee_id)))
        return self.search(domain, order="deadline asc")

    @api.model
    def cron_send_overdue_reminders(self):
        """Cron hàng ngày: gửi mail giục quá hạn theo từng nhân viên."""
        self.cron_recompute_overdue()
        overdue = self.search([("is_overdue", "=", True)])
        if not overdue:
            return True
        by_assignee = {}
        for task in overdue:
            by_assignee.setdefault(task.assignee_id, self.env["daily.task"])
            by_assignee[task.assignee_id] |= task
        Mail = self.env["mail.mail"].sudo()
        for employee, tasks in by_assignee.items():
            if not employee.email:
                continue
            body = self._build_overdue_email_body(employee, tasks)
            Mail.create(
                {
                    "subject": "[Nhắc việc] Bạn có %s công việc quá hạn" % len(tasks),
                    "body_html": body,
                    "email_to": employee.email,
                    "auto_delete": True,
                }
            ).send()
        return True

    @api.model
    def _build_overdue_email_body(self, employee, tasks):
        rows = []
        for task in tasks:
            rows.append(
                "<tr>"
                "<td style='padding:6px;border:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;border:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;border:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;border:1px solid #ddd;'>%s</td>"
                "</tr>"
                % (
                    task.name,
                    task.deadline.strftime("%d/%m/%Y") if task.deadline else "",
                    dict(task._fields["priority"].selection).get(task.priority, ""),
                    dict(task._fields["state"].selection).get(task.state, ""),
                )
            )
        return (
            "<p>Xin chào <b>%s</b>,</p>"
            "<p>Bạn đang có <b>%s</b> công việc quá hạn. Vui lòng cập nhật:</p>"
            "<table style='border-collapse:collapse;width:100%%;'>"
            "<thead><tr>"
            "<th style='padding:6px;border:1px solid #ddd;background:#f5f5f5;'>Tên công việc</th>"
            "<th style='padding:6px;border:1px solid #ddd;background:#f5f5f5;'>Hạn cuối</th>"
            "<th style='padding:6px;border:1px solid #ddd;background:#f5f5f5;'>Ưu tiên</th>"
            "<th style='padding:6px;border:1px solid #ddd;background:#f5f5f5;'>Trạng thái</th>"
            "</tr></thead><tbody>%s</tbody></table>"
            "<p>Trân trọng.</p>"
        ) % (employee.name, len(tasks), "".join(rows))

    def action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "daily.task",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _to_manager_dict(self):
        self.ensure_one()
        minutes = int(self.duration_minutes or 0)
        hours = float(self.duration_hours or 0.0)
        wg = self.sudo().work_group_id
        overdue_days = self._days_past_deadline()
        active_overdue = self.state != "done" and overdue_days > 0
        return {
            "id": self.id,
            "name": self.name or "",
            "assign_date": self.assign_date.isoformat() if self.assign_date else "",
            "assign_date_display": self.assign_date.strftime("%d/%m/%Y")
            if self.assign_date
            else "",
            "assigned_by_id": self.assigned_by_id.id if self.assigned_by_id else False,
            "assigned_by_name": self.assigned_by_id.name if self.assigned_by_id else "",
            "deadline": self.deadline.isoformat() if self.deadline else "",
            "deadline_display": self.deadline.strftime("%d/%m/%Y") if self.deadline else "",
            "department_id": self.department_id.id if self.department_id else False,
            "department_label": self.department_id.display_name if self.department_id else "",
            "assignee_id": self.assignee_id.id,
            "assignee_name": self.assignee_id.name or "",
            "hr_employee_id": self.assignee_id.employee_id.id
            if self.assignee_id.employee_id
            else False,
            "work_group_id": wg.id if wg else False,
            "work_group_label": (wg.name or "") if wg else "",
            "duration_minutes": minutes,
            "duration_hours": hours,
            "duration_hours_display": ("%.2f" % hours).rstrip("0").rstrip(".") or "0",
            "completion_percent": int(self.completion_percent or 0)
            if self.state != "done"
            else max(int(self.completion_percent or 0), 100),
            "priority": self.priority or "",
            "priority_label": dict(self._fields["priority"].selection).get(self.priority, "")
            or "",
            "state": self.state or "",
            "state_label": dict(self._fields["state"].selection).get(self.state, "") or "",
            "note": self.note or "",
            # Cột Quá hạn: hiện số ngày trễ kể cả khi đã hoàn thành
            "is_overdue": overdue_days > 0,
            "is_active_overdue": active_overdue,
            "overdue_days": overdue_days,
            "overdue_label": ("Trễ hạn %s ngày" % overdue_days) if overdue_days else "",
            "color": int(self.color or 0),
            "color_token": (
                "overdue"
                if active_overdue
                else (self.state or "not_started")
            ),
            "recurring_id": self.recurring_id.id if self.recurring_id else False,
            "is_from_recurring": bool(self.recurring_id),
            "progress": int(self.completion_percent or 0)
            if self.state != "done"
            else max(int(self.completion_percent or 0), 100),
        }

    @api.model
    def _calendar_visible_domain(self):
        """Calendar To Do List: chỉ việc của user đang đăng nhập."""
        my = self._my_hr_employee()
        if my:
            return [("assignee_id.employee_id", "=", my.id)]
        # Fallback: bridge gắn HR của user login
        bridge = (
            self.env["daily.task.employee"]
            .sudo()
            .search([("employee_id.user_id", "=", self.env.user.id)], limit=1)
        )
        if bridge:
            return [("assignee_id", "=", bridge.id)]
        return [("id", "=", 0)]

    @api.model
    def get_fluent_calendar_data(self, year=None, month=None, department_id=None, search=None):
        """Dữ liệu Calendar Fluent: KPI + lưới tháng + sidebar (cá nhân)."""
        from calendar import monthrange

        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        last_day = monthrange(year, month)[1]
        start = fields.Date.to_date("%04d-%02d-01" % (year, month))
        end = fields.Date.to_date("%04d-%02d-%02d" % (year, month, last_day))

        domain = list(self._calendar_visible_domain())
        # Bỏ lọc phòng ban trên calendar cá nhân — chỉ việc của mình
        q = (search or "").strip()
        if q:
            domain += [
                "|",
                ("name", "ilike", q),
                ("note", "ilike", q),
            ]

        month_domain = domain + [
            ("deadline", ">=", start),
            ("deadline", "<=", end),
        ]
        tasks = self.search(month_domain, order="deadline asc, priority asc, id desc")

        by_day = {}
        for task in tasks:
            key = task.deadline.day
            by_day.setdefault(key, [])
            by_day[key].append(task._to_manager_dict())

        # KPI trong phạm vi việc của user hiện tại
        all_visible = self.search(domain)
        total = len(all_visible)
        done = len(all_visible.filtered(lambda t: t.state == "done"))
        in_progress = len(all_visible.filtered(lambda t: t.state == "in_progress"))
        overdue = len(all_visible.filtered(lambda t: t.is_overdue))
        today_tasks_rs = all_visible.filtered(lambda t: t.deadline == today)
        completion = int(round((done * 100.0 / total), 0)) if total else 0

        upcoming = self.search(
            domain
            + [
                ("deadline", ">", today),
                ("state", "!=", "done"),
            ],
            order="deadline asc",
            limit=20,
        )
        overdue_list = self.search(
            domain + [("is_overdue", "=", True)],
            order="deadline asc",
            limit=20,
        )
        today_list = self.search(
            domain + [("deadline", "=", today)],
            order="priority asc, id desc",
            limit=20,
        )

        my = self._my_hr_employee()
        my_dept = my.department_id if my else False
        departments = []
        if my_dept:
            departments = [{"id": my_dept.id, "name": my_dept.display_name or ""}]

        return {
            "year": year,
            "month": month,
            "today": today.isoformat(),
            "today_display": today.strftime("%d/%m/%Y"),
            "month_label": "Tháng %s, %s" % (month, year),
            "days_in_month": last_day,
            "first_weekday": start.weekday(),  # Mon=0 … Sun=6
            "by_day": {str(k): v for k, v in by_day.items()},
            "kpi": {
                "total": total,
                "today": len(today_tasks_rs),
                "in_progress": in_progress,
                "completion_rate": completion,
                "overdue": overdue,
            },
            "sidebar": {
                "today": [t._to_manager_dict() for t in today_list],
                "overdue": [t._to_manager_dict() for t in overdue_list],
                "upcoming": [t._to_manager_dict() for t in upcoming],
            },
            "departments": departments,
            "states": [
                {"value": k, "label": v}
                for k, v in self._fields["state"].selection
            ],
            # Calendar cá nhân: user nhập việc cho chính mình
            "can_create": True,
            "my_employee_id": my.id if my else False,
        }

    @api.model
    def _is_manager(self):
        return self.env.user.has_group("daily_work_task.group_daily_work_manager")

    @api.model
    def _is_assigner(self):
        return self.env.user.has_group("daily_work_task.group_daily_work_assigner")

    @api.model
    def _is_viewer(self):
        return self.env.user.has_group("daily_work_task.group_daily_work_viewer")

    @api.model
    def _my_hr_employee(self):
        return self.env["hr.employee"].search(
            [("user_id", "=", self.env.user.id)],
            limit=1,
        )

    @api.model
    def _access_target_ids_sql(self, perm_field):
        """Đọc ID nhân viên mục tiêu từ bảng quan hệ — không qua rule hr.employee."""
        if perm_field not in ("perm_view", "perm_assign", "perm_edit", "perm_delete"):
            return []
        self.env.cr.execute(
            """
            SELECT DISTINCT rel.employee_id
              FROM daily_task_access_grantee_rel rel
              JOIN daily_task_access a ON a.id = rel.access_id
             WHERE a.user_id = %s
               AND COALESCE(a.active, true) = true
               AND a."""
            + perm_field
            + """ = true
            """,
            (self.env.uid,),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _assignable_employee_ids(self):
        """Danh sách HR employee được phép giao việc (None = tất cả nếu quản lý)."""
        if self._is_manager():
            return None
        return self._access_target_ids_sql("perm_assign")

    @api.model
    def _viewable_employee_ids(self):
        if self._is_manager():
            return None
        return self._access_target_ids_sql("perm_view")

    @api.model
    def _editable_employee_ids(self):
        if self._is_manager():
            return None
        return self._access_target_ids_sql("perm_edit")

    @api.model
    def _deletable_employee_ids(self):
        if self._is_manager():
            return None
        return self._access_target_ids_sql("perm_delete")

    @api.model
    def rule_viewable_employee_ids(self):
        """Dùng trong ir.rule domain_force (gọi với uid của user đang login)."""
        uid = self.env.uid
        self.env.cr.execute(
            """
            SELECT DISTINCT rel.employee_id
              FROM daily_task_access_grantee_rel rel
              JOIN daily_task_access a ON a.id = rel.access_id
             WHERE a.user_id = %s
               AND COALESCE(a.active, true) = true
               AND a.perm_view = true
            """,
            (uid,),
        )
        return [row[0] for row in self.env.cr.fetchall()] or [0]

    @api.model
    def rule_assignable_employee_ids(self):
        """NV được giao việc — dùng cho ir.rule write/create."""
        uid = self.env.uid
        self.env.cr.execute(
            """
            SELECT DISTINCT rel.employee_id
              FROM daily_task_access_grantee_rel rel
              JOIN daily_task_access a ON a.id = rel.access_id
             WHERE a.user_id = %s
               AND COALESCE(a.active, true) = true
               AND a.perm_assign = true
            """,
            (uid,),
        )
        return [row[0] for row in self.env.cr.fetchall()] or [0]

    @api.model
    def rule_editable_employee_ids(self):
        """NV được chỉnh sửa — dùng cho ir.rule write."""
        uid = self.env.uid
        self.env.cr.execute(
            """
            SELECT DISTINCT rel.employee_id
              FROM daily_task_access_grantee_rel rel
              JOIN daily_task_access a ON a.id = rel.access_id
             WHERE a.user_id = %s
               AND COALESCE(a.active, true) = true
               AND a.perm_edit = true
            """,
            (uid,),
        )
        return [row[0] for row in self.env.cr.fetchall()] or [0]

    @api.model
    def rule_deletable_employee_ids(self):
        """NV được xóa việc — dùng cho ir.rule unlink."""
        uid = self.env.uid
        self.env.cr.execute(
            """
            SELECT DISTINCT rel.employee_id
              FROM daily_task_access_grantee_rel rel
              JOIN daily_task_access a ON a.id = rel.access_id
             WHERE a.user_id = %s
               AND COALESCE(a.active, true) = true
               AND a.perm_delete = true
            """,
            (uid,),
        )
        return [row[0] for row in self.env.cr.fetchall()] or [0]

    def _can_edit_task(self):
        self.ensure_one()
        if self._is_manager():
            return True
        emp = self.assignee_id.employee_id
        my = self._my_hr_employee()
        if my and emp and emp.id == my.id:
            return True
        allowed = self._editable_employee_ids() or []
        return bool(emp and emp.id in allowed)

    @api.model
    def _is_system_admin(self):
        """Tài khoản Administrator (Settings / base.group_system)."""
        return self.env.user.has_group("base.group_system")

    def _can_delete_task(self):
        """Chỉ Administrator hệ thống được xóa công việc."""
        self.ensure_one()
        return self._is_system_admin()

    def delete_from_manager(self):
        self.ensure_one()
        if not self._can_delete_task():
            raise ValidationError(
                "Chỉ tài khoản Administrator mới được xóa công việc."
            )
        self.sudo().unlink()
        return True

    @api.model
    def get_employee_workspace(self, filters=None):
        """Không gian nhân viên: chỉ việc của user đang đăng nhập."""
        filters = filters or {}
        emp = self._my_hr_employee()
        states = [
            {"value": k, "label": v}
            for k, v in self._fields["state"].selection
        ]
        if not emp:
            return {
                "employee": False,
                "tasks": [],
                "states": states,
                "priorities": [],
                "work_groups": [],
                "total_duration_minutes": 0,
                "total_duration_hours": 0.0,
                "completion_percent_avg": 0.0,
                "message": "Tài khoản chưa gắn hồ sơ nhân viên (hr.employee). Liên hệ quản trị để liên kết User với Employee.",
            }
        domain = [("assignee_id.employee_id", "=", emp.id)]
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if date_from:
            domain.append(("deadline", ">=", date_from))
        if date_to:
            domain.append(("deadline", "<=", date_to))
        # Danh sách đang làm: ẩn việc đã hoàn thành (chúng nằm ở bảng tổng tháng)
        domain.append(("state", "!=", "done"))
        tasks = self.search(domain, order="deadline asc, id desc")
        self._refresh_overdue_flags(tasks)
        priorities = [
            {"value": k, "label": v}
            for k, v in self._fields["priority"].selection
        ]
        dept_id = emp.department_id.id if emp.department_id else False
        work_groups = self.env["daily.task.work.group"].get_groups_for_user(
            department_id=dept_id,
            user_id=self.env.uid,
        )
        total_minutes = sum(int(t.duration_minutes or 0) for t in tasks)
        avg_pct = 0.0
        if tasks:
            avg_pct = round(
                sum(
                    max(int(t.completion_percent or 0), 100 if t.state == "done" else 0)
                    for t in tasks
                )
                / float(len(tasks)),
                1,
            )
        return {
            "employee": {
                "id": emp.id,
                "name": emp.name or "",
                "department": emp.department_id.display_name if emp.department_id else "",
                "department_id": dept_id or False,
            },
            "tasks": [t._to_manager_dict() for t in tasks],
            "states": states,
            "priorities": priorities,
            "work_groups": work_groups,
            "total_duration_minutes": total_minutes,
            "total_duration_hours": round(total_minutes / 60.0, 2) if total_minutes else 0.0,
            "completion_percent_avg": avg_pct,
            "message": False,
        }

    @api.model
    def _month_date_bounds(self, year=None, month=None):
        from calendar import monthrange

        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        last_day = monthrange(year, month)[1]
        date_from = fields.Date.to_date("%04d-%02d-01" % (year, month))
        date_to = fields.Date.to_date("%04d-%02d-%02d" % (year, month, last_day))
        return year, month, date_from, date_to

    @api.model
    def _monthly_task_domain(self, employee_id, date_from, date_to):
        """Việc thuộc tháng: hạn trong tháng HOẶC ngày giao trong tháng."""
        return [
            ("assignee_id.employee_id", "=", int(employee_id)),
            "|",
            "&",
            ("deadline", ">=", date_from),
            ("deadline", "<=", date_to),
            "&",
            ("assign_date", ">=", date_from),
            ("assign_date", "<=", date_to),
        ]

    @api.model
    def _task_completion_percent(self, task):
        """% HT hiệu lực của 1 việc (đã hoàn thành tối thiểu 100)."""
        pct = int(task.completion_percent or 0)
        if getattr(task, "state", None) == "done":
            return max(pct, 100)
        return max(0, min(pct, 100))

    @api.model
    def _completion_averages_by_work_group(self, tasks):
        """
        % HT từng nhóm = AVERAGE(% các việc trong nhóm).
        Tổng % HT = AVERAGE(các % TB nhóm) — giống AVERAGE trong Excel trên các dòng tổng nhóm.
        Returns: (list[{work_group_id, label, avg, count}], month_avg)
        """
        buckets = {}
        for task in tasks:
            wg = task.work_group_id
            key = wg.id if wg else 0
            if key not in buckets:
                buckets[key] = {
                    "work_group_id": key or False,
                    "label": (wg.name if wg else "") or "Không có hạng mục",
                    "values": [],
                }
            buckets[key]["values"].append(self._task_completion_percent(task))

        group_avgs = []
        for key, bucket in buckets.items():
            values = bucket["values"]
            avg = round(sum(values) / float(len(values)), 1) if values else 0.0
            group_avgs.append(
                {
                    "work_group_id": bucket["work_group_id"],
                    "label": bucket["label"],
                    "avg": avg,
                    "count": len(values),
                }
            )

        group_avgs.sort(
            key=lambda g: (0 if g["work_group_id"] else 1, str(g["label"] or ""))
        )
        month_avg = 0.0
        if group_avgs:
            month_avg = round(
                sum(g["avg"] for g in group_avgs) / float(len(group_avgs)),
                1,
            )
        return group_avgs, month_avg

    @api.model
    def _build_monthly_summary_for_employee(self, emp, year=None, month=None, use_sudo=False):
        """Payload bảng tổng công việc tháng — dùng chung NV cập nhật + Xem công việc NV."""
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        empty_kpi = {
            "total": 0,
            "done": 0,
            "in_progress": 0,
            "not_started": 0,
            "overdue": 0,
            "duration_minutes": 0,
            "duration_hours": 0.0,
            "completion_percent_avg": 0.0,
            "completion_percent_by_group": [],
        }
        if not emp:
            return {
                "employee": False,
                "year": year,
                "month": month,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "kpi": empty_kpi,
                "rows": [],
                "message": "Tài khoản chưa gắn hồ sơ nhân viên.",
            }
        Task = self.sudo() if use_sudo else self
        tasks = Task.search(
            self._monthly_task_domain(emp.id, date_from, date_to),
            order="deadline asc, id asc",
        )
        # Cập nhật cờ store + KPI dùng tính realtime (ngày hôm nay)
        self._refresh_overdue_flags(tasks)
        rows = []
        for idx, task in enumerate(tasks, start=1):
            data = task._to_manager_dict()
            data["stt"] = idx
            rows.append(data)
        total_minutes = sum(int(t.duration_minutes or 0) for t in tasks)
        # % HT từng nhóm = AVERAGE(% việc trong nhóm);
        # Tổng % HT tháng = AVERAGE(các % TB nhóm) — giống hàm AVERAGE trong Excel.
        group_avgs, month_avg = self._completion_averages_by_work_group(tasks)
        kpi = {
            "total": len(tasks),
            "done": len(tasks.filtered(lambda t: t.state == "done")),
            "in_progress": len(tasks.filtered(lambda t: t.state == "in_progress")),
            "not_started": len(tasks.filtered(lambda t: t.state == "not_started")),
            "overdue": len(tasks.filtered(lambda t: t._is_overdue_today())),
            "duration_minutes": total_minutes,
            "duration_hours": round(total_minutes / 60.0, 2) if total_minutes else 0.0,
            "completion_percent_avg": month_avg,
            "completion_percent_by_group": group_avgs,
        }
        dept_name = ""
        if emp.department_id:
            dept_name = emp.department_id.display_name or emp.department_id.name or ""
        return {
            "employee": {
                "id": emp.id,
                "name": emp.name or "",
                "department": dept_name,
            },
            "year": year,
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "kpi": kpi,
            "rows": rows,
            "message": False,
        }

    @api.model
    def get_employee_monthly_summary(self, year=None, month=None, employee_id=None):
        """Tổng hợp công việc trong tháng (NV đang login, hoặc employee_id nếu có quyền xem)."""
        emp = False
        use_sudo = False
        if employee_id:
            emp_id = int(employee_id)
            if not self._is_viewer():
                raise ValidationError("Bạn không có quyền xem.")
            allowed = self._viewable_employee_ids()
            if allowed is not None and emp_id not in allowed:
                raise ValidationError("Bạn không được xem công việc của nhân viên này.")
            emp = self.env["hr.employee"].sudo().browse(emp_id).exists()
            use_sudo = True
        else:
            emp = self._my_hr_employee()
        return self._build_monthly_summary_for_employee(
            emp, year=year, month=month, use_sudo=use_sudo
        )

    @api.model
    def export_employee_monthly_excel(self, year=None, month=None):
        """Xuất Excel báo cáo tháng — logo cạnh tiêu đề, bố cục in A4 ngang."""
        import base64
        import io

        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError(
                "Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter"
            ) from exc

        summary = self.get_employee_monthly_summary(year=year, month=month)
        if summary.get("message") and not summary.get("employee"):
            raise ValidationError(summary["message"])

        emp = summary.get("employee") or {}
        emp_name = emp.get("name") or "NhanVien"
        dept_name = emp.get("department") or ""
        year = summary["year"]
        month = summary["month"]
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Bao_cao_cong_viec")

        # ---- Trang in A4 ngang, vừa 1 trang theo chiều ngang ----
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.set_margins(left=0.4, right=0.4, top=0.45, bottom=0.45)
        ws.fit_to_pages(1, 0)
        ws.set_print_scale(100)
        ws.center_horizontally()
        ws.hide_gridlines(2)
        ws.set_header("&C&B SATACO — Sáng Tâm Co.Ltd")
        ws.set_footer("&L&D &T&RTrang &P / &N")

        FONT = "Times New Roman"

        def _make_fmt(**kwargs):
            data = {"font_name": FONT, "font_size": 11}
            data.update(kwargs)
            return wb.add_format(data)

        def _row_height(texts, col_widths, base=18, line_h=14, max_h=96):
            """Ước lượng chiều cao dòng để chữ wrap không bị che."""
            lines = 1
            for text, width in zip(texts, col_widths):
                raw = str(text or "").strip()
                if not raw:
                    continue
                per_line = max(int(width * 0.95), 6)
                need = 0
                for part in raw.split("\n"):
                    need += max(1, (len(part) + per_line - 1) // per_line)
                lines = max(lines, need)
            return min(base + (lines - 1) * line_h, max_h)

        title_fmt = _make_fmt(
            bold=True,
            font_size=18,
            font_color="#14532d",
            align="center",
            valign="vcenter",
        )
        emp_fmt = _make_fmt(
            bold=True,
            font_size=12,
            font_color="#0f172a",
            align="center",
            valign="vcenter",
        )
        meta_label = _make_fmt(bold=True, font_size=11, font_color="#334155")
        meta_val = _make_fmt(bold=True, font_size=11, font_color="#0f172a")
        header_fmt = _make_fmt(
            bold=True,
            font_size=11,
            bg_color="#166534",
            font_color="#FFFFFF",
            border=1,
            align="center",
            valign="vcenter",
            text_wrap=True,
        )
        cell_fmt = _make_fmt(border=1, font_size=11, valign="vcenter", text_wrap=True)
        cell_center = _make_fmt(
            border=1,
            font_size=11,
            align="center",
            valign="vcenter",
            text_wrap=True,
        )
        done_fmt = _make_fmt(
            border=1,
            font_size=11,
            bg_color="#DCFCE7",
            valign="vcenter",
            text_wrap=True,
        )
        done_center = _make_fmt(
            border=1,
            font_size=11,
            bg_color="#DCFCE7",
            align="center",
            valign="vcenter",
            text_wrap=True,
        )
        overdue_fmt = _make_fmt(
            border=1,
            font_size=11,
            bg_color="#FEE2E2",
            valign="vcenter",
            text_wrap=True,
        )
        overdue_center = _make_fmt(
            border=1,
            font_size=11,
            bg_color="#FEE2E2",
            align="center",
            valign="vcenter",
            text_wrap=True,
        )
        kpi_label = _make_fmt(
            bold=True,
            font_size=10,
            font_color="#334155",
            align="center",
            valign="vcenter",
            border=1,
            bg_color="#f8fafc",
            text_wrap=True,
        )
        kpi_val = _make_fmt(
            bold=True,
            font_size=13,
            align="center",
            valign="vcenter",
            border=1,
        )
        kpi_done = _make_fmt(
            bold=True,
            font_size=13,
            font_color="#15803d",
            align="center",
            valign="vcenter",
            border=1,
        )
        kpi_progress = _make_fmt(
            bold=True,
            font_size=13,
            font_color="#0369a1",
            align="center",
            valign="vcenter",
            border=1,
        )
        kpi_overdue = _make_fmt(
            bold=True,
            font_size=13,
            font_color="#dc2626",
            align="center",
            valign="vcenter",
            border=1,
        )
        group_fmt = _make_fmt(
            bold=True,
            font_size=11,
            bg_color="#DCFCE7",
            font_color="#14532d",
            border=1,
            valign="vcenter",
            text_wrap=True,
        )

        # Cột rộng hơn + wrap để tên việc / ghi chú không bị che
        widths = [5, 36, 12, 12, 11, 13, 8, 8, 14, 22, 10]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        # Tiêu đề + tên NV canh giữa TOÀN bộ bảng (A–K); logo nổi góc trái (không đẩy lệch phải)
        ws.set_row(0, 40)
        ws.set_row(1, 24)
        ws.merge_range(0, 0, 0, 10, "BÁO CÁO CÔNG VIỆC", title_fmt)
        ws.merge_range(1, 0, 1, 10, emp_name, emp_fmt)

        logo_info = self._sataco_logo_bytes()
        if logo_info:
            # Logo ~+15%: scale 0.38 → 0.44
            ws.insert_image(
                0,
                0,
                "sataco_logo.png",
                {
                    "image_data": logo_info,
                    "x_offset": 2,
                    "y_offset": 4,
                    "x_scale": 0.44,
                    "y_scale": 0.44,
                    "object_position": 1,
                },
            )

        ws.write(2, 0, "Bộ phận:", meta_label)
        ws.merge_range(2, 1, 2, 3, dept_name, meta_val)
        ws.write(2, 4, "Kỳ:", meta_label)
        ws.write(2, 5, "%02d/%s" % (month, year), meta_val)
        ws.write(2, 6, "Tháng BC:", meta_label)
        ws.write(2, 7, "%02d/%s" % (month, year), meta_val)

        kpi = summary.get("kpi") or {}
        kpi_items = [
            ("TỔNG SỐ", kpi.get("total", 0), kpi_val),
            ("HOÀN THÀNH", kpi.get("done", 0), kpi_done),
            ("ĐANG XỬ LÝ", kpi.get("in_progress", 0), kpi_progress),
            ("CHƯA BẮT ĐẦU", kpi.get("not_started", 0), kpi_val),
            ("QUÁ HẠN", kpi.get("overdue", 0), kpi_overdue),
            ("TỔNG TG\n(GIỜ)", kpi.get("duration_hours", 0), kpi_done),
            (
                "% Hoàn thành CV\n(AVERAGE hạng mục)",
                "%s%%" % (kpi.get("completion_percent_avg", 0) or 0),
                kpi_val,
            ),
        ]
        for col, (label, _val, _kpi_fmt) in enumerate(kpi_items):
            ws.write(4, col, label, kpi_label)
        for col, (_label, val, fmt) in enumerate(kpi_items):
            ws.write(5, col, val, fmt)
        ws.set_row(4, 32)
        ws.set_row(5, 24)

        headers = [
            "STT",
            "Tên công việc",
            "Ngày giao",
            "Hạn HT",
            "Ưu tiên",
            "Trạng thái",
            "Phút",
            "Giờ",
            "% Hoàn thành CV",
            "Ghi chú",
            "Quá hạn",
        ]
        start_row = 7
        ws.set_row(start_row, 28)
        for col, header in enumerate(headers):
            ws.write(start_row, col, header, header_fmt)
        ws.repeat_rows(start_row, start_row)

        groups = {}
        group_order = []
        for row in summary.get("rows") or []:
            key = row.get("work_group_id") or 0
            label = (row.get("work_group_label") or "").strip() or "Không có hạng mục"
            if key not in groups:
                groups[key] = {"label": label, "rows": [], "minutes": 0}
                group_order.append(key)
            groups[key]["rows"].append(row)
            groups[key]["minutes"] += int(row.get("duration_minutes") or 0)

        def _group_sort_key(gid):
            if gid == 0:
                return (1, "")
            return (0, groups[gid]["label"])

        group_order.sort(key=_group_sort_key)

        center_cols = {0, 2, 3, 4, 5, 6, 7, 8, 10}
        r = start_row
        group_avg_values = []
        for gid in group_order:
            g = groups[gid]
            hours = round(g["minutes"] / 60.0, 2) if g["minutes"] else 0.0
            pct_vals = [
                max(
                    int(row.get("completion_percent") or 0),
                    100 if row.get("state") == "done" else 0,
                )
                for row in g["rows"]
            ]
            g_avg = round(sum(pct_vals) / float(len(pct_vals)), 1) if pct_vals else 0.0
            group_avg_values.append(g_avg)
            r += 1
            group_title = (
                "%s  —  %s việc · %s giờ · %% Hoàn thành CV TB hạng mục (AVERAGE): %s%%"
                % (g["label"], len(g["rows"]), hours, g_avg)
            )
            ws.merge_range(r, 0, r, 10, group_title, group_fmt)
            ws.set_row(r, _row_height([group_title], [sum(widths)]))
            for stt, row in enumerate(g["rows"], start=1):
                r += 1
                late_days = int(row.get("overdue_days") or 0)
                is_done = row.get("state") == "done"
                is_active_overdue = (not is_done) and late_days > 0
                name_text = row.get("name") or ""
                note_text = row.get("note") or ""
                values = [
                    stt,
                    name_text,
                    row.get("assign_date_display") or "",
                    row.get("deadline_display") or "",
                    row.get("priority_label") or "",
                    row.get("state_label") or "",
                    row.get("duration_minutes") or 0,
                    row.get("duration_hours") or 0,
                    "%s%%" % (row.get("completion_percent") or 0),
                    note_text,
                    ("%s" % (row.get("overdue_label") or ("Trễ hạn %s ngày" % late_days)))
                    if late_days > 0
                    else "",
                ]
                for col, val in enumerate(values):
                    if is_done:
                        fmt = done_center if col in center_cols else done_fmt
                    elif is_active_overdue:
                        fmt = overdue_center if col in center_cols else overdue_fmt
                    else:
                        fmt = cell_center if col in center_cols else cell_fmt
                    ws.write(r, col, val, fmt)
                ws.set_row(
                    r,
                    _row_height(
                        [name_text, note_text],
                        [widths[1], widths[9]],
                    ),
                )

        # Tổng % HT tháng = AVERAGE các % TB nhóm
        month_avg = (
            round(sum(group_avg_values) / float(len(group_avg_values)), 1)
            if group_avg_values
            else 0.0
        )
        r += 1
        total_avg_fmt = _make_fmt(
            bold=True,
            font_size=11,
            bg_color="#FEF3C7",
            font_color="#92400e",
            border=1,
            valign="vcenter",
            text_wrap=True,
        )
        ws.merge_range(
            r,
            0,
            r,
            10,
            "Tổng %% hoàn thành công việc trong tháng (AVERAGE các hạng mục): %s%%"
            % month_avg,
            total_avg_fmt,
        )
        ws.set_row(r, 24)

        # ---- Khối chữ ký phía dưới (theo mẫu) ----
        sign_date_fmt = _make_fmt(
            italic=True,
            font_size=11,
            align="right",
            valign="vcenter",
        )
        sign_role_fmt = _make_fmt(
            bold=True,
            font_size=12,
            align="center",
            valign="vcenter",
        )
        sign_name_fmt = _make_fmt(
            bold=True,
            font_size=12,
            align="center",
            valign="vcenter",
            underline=True,
        )

        today = fields.Date.context_today(self)
        r += 2
        ws.merge_range(
            r,
            6,
            r,
            10,
            "TP.HCM, ngày %02d tháng %02d năm %s"
            % (today.day, today.month, today.year),
            sign_date_fmt,
        )

        r += 2
        ws.merge_range(r, 0, r, 2, "Người lập", sign_role_fmt)
        ws.merge_range(r, 3, r, 5, "Trưởng bộ phận", sign_role_fmt)
        ws.merge_range(r, 6, r, 10, "Giám đốc", sign_role_fmt)

        # Khoảng trống ký tên
        for _ in range(5):
            r += 1
            ws.set_row(r, 16)

        r += 1
        ws.merge_range(r, 0, r, 2, emp_name, sign_name_fmt)
        ws.merge_range(r, 3, r, 5, "", sign_name_fmt)
        ws.merge_range(r, 6, r, 10, "Huỳnh Thị Thanh Tâm", sign_name_fmt)

        # Vùng in: từ đầu đến hết chữ ký
        ws.print_area(0, 0, max(r, start_row), 10)

        wb.close()
        raw = buffer.getvalue()
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in emp_name)
        filename = "Bao_cao_cong_viec_%s_%02d_%s.xlsx" % (safe_name, month, year)
        return {
            "filename": filename,
            "file_base64": base64.b64encode(raw).decode("ascii"),
        }

    @api.model
    def _sataco_logo_bytes(self):
        """Đọc logo SATACO dạng RGB PNG (tránh lỗi RGBA khi chèn Excel)."""
        import io
        import os

        from odoo.tools import file_path

        path = False
        for rel in (
            "daily_work_task/static/description/sataco_logo.png",
            "daily_work_task/static/src/img/sataco_logo.png",
        ):
            try:
                path = file_path(rel)
            except Exception:
                path = False
            if path and os.path.isfile(path):
                break
        if not path or not os.path.isfile(path):
            module_dir = os.path.dirname(os.path.dirname(__file__))
            path = os.path.join(module_dir, "static", "description", "sataco_logo.png")
        if not path or not os.path.isfile(path):
            return False
        try:
            from PIL import Image

            img = Image.open(path)
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="PNG")
            out.seek(0)
            return out
        except Exception:
            with open(path, "rb") as handle:
                return io.BytesIO(handle.read())

    @api.model
    def create_from_employee(self, vals):
        """Nhân viên tự tạo việc — luôn gán cho chính mình."""
        emp = self._my_hr_employee()
        if not emp:
            raise ValidationError(
                "Tài khoản chưa gắn hồ sơ nhân viên. Liên hệ quản trị để liên kết User với Employee."
            )
        bridge = self.env["daily.task.employee"].sudo().get_or_create_from_hr(emp.id)
        department_id = emp.department_id.id if emp.department_id else False
        work_group_id = int(vals.get("work_group_id") or 0) or False
        if work_group_id:
            group = self.env["daily.task.work.group"].sudo().browse(work_group_id)
            if not group.exists() or not group.active:
                raise ValidationError("Nhóm công việc không hợp lệ.")
            if department_id and group.department_id.id != department_id:
                raise ValidationError(
                    "Bạn chỉ được chọn nhóm công việc của phòng ban mình."
                )
            if group.user_ids and self.env.uid not in group.user_ids.ids:
                raise ValidationError(
                    "Bạn không nằm trong danh sách User áp dụng của nhóm này."
                )
        try:
            duration_minutes = int(vals.get("duration_minutes") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Thời gian thực hiện (phút) phải là số nguyên.") from exc
        if duration_minutes < 0:
            raise ValidationError("Thời gian thực hiện (phút) không được âm.")
        assign_date = vals.get("assign_date") or fields.Date.context_today(self)
        assigner_uid = self.env.uid
        task = self.with_context(daily_task_assigner_uid=assigner_uid).create(
            {
                "name": (vals.get("name") or "").strip(),
                "assign_date": assign_date,
                "assigned_by_id": assigner_uid,
                "deadline": vals.get("deadline"),
                "department_id": department_id,
                "assignee_id": bridge.id,
                "work_group_id": work_group_id,
                "duration_minutes": duration_minutes,
                "priority": vals.get("priority") or "medium",
                "state": vals.get("state") or "not_started",
                "note": vals.get("note") or "",
            }
        )
        return task._to_manager_dict()

    @api.model
    def _hr_employee_rows_by_ids(self, employee_ids):
        """Đọc thông tin NV bằng SQL — tránh bị HR access mixin / LUG lọc ORM."""
        ids = [int(i) for i in (employee_ids or []) if i]
        if not ids:
            return []
        self.env.cr.execute(
            """
            SELECT e.id,
                   e.name,
                   e.work_email,
                   v.department_id,
                   COALESCE(d.name->>'en_US', d.name::text) AS department_name
              FROM hr_employee e
         LEFT JOIN hr_version v ON v.id = e.current_version_id
         LEFT JOIN hr_department d ON d.id = v.department_id
             WHERE e.id IN %s
               AND COALESCE(e.active, true) = true
          ORDER BY COALESCE(d.name->>'en_US', d.name::text) NULLS LAST, e.name
            """,
            (tuple(ids),),
        )
        rows = []
        for eid, name, email, dept_id, dept_name in self.env.cr.fetchall():
            rows.append(
                {
                    "id": eid,
                    "name": name or "",
                    "email": email or "",
                    "department_id": dept_id or False,
                    "department": dept_name or "",
                }
            )
        return rows

    @api.model
    def get_assign_bootstrap(self):
        """Bootstrap màn Giao việc — cần nhóm Người giao việc / Quản lý."""
        if not self._is_assigner():
            raise ValidationError(
                "Bạn không có quyền Giao việc. Liên hệ quản trị để gán nhóm "
                "'Người giao việc' và cấu hình Phân quyền."
            )
        is_manager = self._is_manager()
        my_emp = self._my_hr_employee()
        if is_manager:
            self.env.cr.execute(
                """
                SELECT e.id
                  FROM hr_employee e
                 WHERE COALESCE(e.active, true) = true
              ORDER BY e.name
                """
            )
            allowed_ids = [r[0] for r in self.env.cr.fetchall()]
        else:
            allowed_ids = self._assignable_employee_ids() or []
        hr_rows = self._hr_employee_rows_by_ids(allowed_ids)
        bridges = self.env["daily.task.employee"].sudo().search([("active", "=", True)])
        bridge_by_hr = {b.employee_id.id: b.id for b in bridges if b.employee_id}
        employees = []
        for h in hr_rows:
            employees.append(
                {
                    "id": h["id"],
                    "name": h["name"],
                    "bridge_id": bridge_by_hr.get(h["id"]) or False,
                    "department_id": h["department_id"],
                    "department": h["department"],
                    "email": h["email"],
                }
            )
        self.env.cr.execute(
            """
            SELECT id, COALESCE(name->>'en_US', name::text)
              FROM hr_department
          ORDER BY 2
            """
        )
        departments = [
            {"id": did, "name": dname or ""} for did, dname in self.env.cr.fetchall()
        ]
        priorities = [
            {"value": k, "label": v}
            for k, v in self._fields["priority"].selection
        ]
        states = [
            {"value": k, "label": v}
            for k, v in self._fields["state"].selection
        ]
        return {
            "is_manager": is_manager,
            "my_employee_id": my_emp.id if my_emp else False,
            "employees": employees,
            "departments": departments,
            "priorities": priorities,
            "states": states,
            "tasks": self.get_assign_tasks(),
            "message": False
            if employees
            else "Chưa được phân quyền giao việc cho nhân viên nào. Vào Cấu hình → Phân quyền.",
        }

    @api.model
    def get_assign_tasks(self):
        """Danh sách việc đã giao (chưa hoàn thành)."""
        if not self._is_assigner():
            return []
        domain = [("state", "!=", "done")]
        if not self._is_manager():
            allowed = self._assignable_employee_ids() or []
            domain.append(("assignee_id.employee_id", "in", allowed or [0]))
        tasks = self.sudo().search(domain, order="deadline asc, id desc")
        return [t._to_manager_dict() for t in tasks]

    @api.model
    def create_from_assign(self, vals):
        """Giao việc cho nhân viên — việc vào danh sách của user được giao."""
        if not self._is_assigner():
            raise ValidationError("Bạn không có quyền giao việc.")
        hr_id = int(vals.get("assignee_id") or 0)
        if not hr_id:
            raise ValidationError("Vui lòng chọn người được giao.")
        allowed = self._assignable_employee_ids()
        if allowed is not None and hr_id not in allowed:
            raise ValidationError(
                "Bạn không được phân quyền giao việc cho nhân viên này."
            )
        name = (vals.get("name") or "").strip()
        if not name:
            raise ValidationError("Vui lòng nhập tên công việc.")
        if not vals.get("deadline"):
            raise ValidationError("Vui lòng chọn hạn hoàn thành.")
        bridge = (
            self.env["daily.task.employee"].sudo().get_or_create_from_hr(hr_id)
        )
        department_id = int(vals.get("department_id") or 0) or False
        if not department_id:
            self.env.cr.execute(
                """
                SELECT v.department_id
                  FROM hr_employee e
             LEFT JOIN hr_version v ON v.id = e.current_version_id
                 WHERE e.id = %s
                """,
                (hr_id,),
            )
            row = self.env.cr.fetchone()
            if row and row[0]:
                department_id = row[0]
        assigner_uid = self.env.uid
        task = (
            self.with_context(daily_task_assigner_uid=assigner_uid)
            .sudo()
            .create(
                {
                    "name": name,
                    "assign_date": vals.get("assign_date")
                    or fields.Date.context_today(self),
                    "assigned_by_id": assigner_uid,
                    "deadline": vals.get("deadline"),
                    "department_id": department_id,
                    "assignee_id": bridge.id,
                    "priority": vals.get("priority") or "medium",
                    "state": vals.get("state") or "not_started",
                    "note": vals.get("note") or "",
                }
            )
        )
        task._notify_assignee_assigned()
        return task._to_manager_dict()

    @api.model
    def get_viewer_bootstrap(self):
        """Màn Xem công việc nhân viên (User A)."""
        if not self._is_viewer():
            raise ValidationError(
                "Bạn không có quyền xem công việc nhân viên khác. "
                "Cần nhóm 'Người xem' và cấu hình Phân quyền."
            )
        if self._is_manager():
            self.env.cr.execute(
                """
                SELECT e.id
                  FROM hr_employee e
                 WHERE COALESCE(e.active, true) = true
              ORDER BY e.name
                """
            )
            allowed = [r[0] for r in self.env.cr.fetchall()]
        else:
            allowed = self._viewable_employee_ids() or []
        result_emps = self._hr_employee_rows_by_ids(allowed)
        states = [
            {"value": k, "label": v}
            for k, v in self._fields["state"].selection
        ]
        return {
            "is_manager": self._is_manager(),
            "can_edit_all": self._is_manager(),
            "employees": result_emps,
            "states": states,
            "message": False
            if result_emps
            else "Chưa được phân quyền xem nhân viên nào. Vào Cấu hình → Phân quyền.",
        }

    @api.model
    def get_viewer_tasks(self, employee_id=None, filters=None):
        """Tổng công việc trong tháng của 1 NV — cùng nguồn bảng tổng tháng."""
        if not self._is_viewer():
            raise ValidationError("Bạn không có quyền xem.")
        filters = filters or {}
        allowed = self._viewable_employee_ids()
        emp_id = int(employee_id or 0)
        today = fields.Date.context_today(self)
        year = int(filters.get("year") or today.year)
        month = int(filters.get("month") or today.month)
        if not emp_id:
            return {
                "tasks": [],
                "rows": [],
                "kpi": {
                    "total": 0,
                    "done": 0,
                    "in_progress": 0,
                    "not_started": 0,
                    "overdue": 0,
                    "duration_minutes": 0,
                    "duration_hours": 0.0,
                },
                "can_edit": False,
                "can_delete": False,
                "year": year,
                "month": month,
            }
        if allowed is not None and emp_id not in allowed:
            raise ValidationError("Bạn không được xem công việc của nhân viên này.")

        emp = self.env["hr.employee"].sudo().browse(emp_id).exists()
        summary = self._build_monthly_summary_for_employee(
            emp, year=year, month=month, use_sudo=True
        )
        can_edit = self._is_manager() or emp_id in (self._editable_employee_ids() or [])
        can_delete = self._is_system_admin()
        rows = summary.get("rows") or []
        return {
            "tasks": rows,
            "rows": rows,
            "kpi": summary.get("kpi") or {},
            "year": summary.get("year"),
            "month": summary.get("month"),
            "date_from": summary.get("date_from"),
            "date_to": summary.get("date_to"),
            "can_edit": can_edit,
            "can_delete": can_delete,
            "message": summary.get("message") or False,
        }

    @api.model
    def get_viewer_month_counts(self, employee_ids=None, year=None, month=None):
        """Đếm nhanh tổng việc / giờ theo tháng cho nhiều NV (khi mở phòng ban)."""
        if not self._is_viewer():
            raise ValidationError("Bạn không có quyền xem.")
        allowed = self._viewable_employee_ids()
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        counts = {}
        for raw in employee_ids or []:
            emp_id = int(raw or 0)
            if not emp_id:
                continue
            if allowed is not None and emp_id not in allowed:
                continue
            tasks = self.sudo().search(self._monthly_task_domain(emp_id, date_from, date_to))
            total_minutes = sum(int(t.duration_minutes or 0) for t in tasks)
            counts[str(emp_id)] = {
                "total": len(tasks),
                "duration_minutes": total_minutes,
                "duration_hours": round(total_minutes / 60.0, 2) if total_minutes else 0.0,
            }
        return {"year": year, "month": month, "counts": counts}

    @api.model
    def get_summary_report(self, year=None, month=None):
        """Báo cáo tổng theo phòng ban / nhân viên (mẫu Excel)."""
        if not self._is_viewer():
            raise ValidationError(
                "Bạn không có quyền xem báo cáo. Cần nhóm 'Người xem' "
                "hoặc quản lý."
            )
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        ReportAccess = self.env["daily.task.report.access"]
        allowed_emp_ids = ReportAccess.reportable_employee_ids_for_user()

        if self._is_manager():
            self.env.cr.execute(
                """
                SELECT e.id
                  FROM hr_employee e
                 WHERE COALESCE(e.active, true) = true
              ORDER BY e.name
                """
            )
            allowed = [r[0] for r in self.env.cr.fetchall()]
        else:
            if not allowed_emp_ids:
                return {
                    "year": year,
                    "month": month,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "departments": [],
                    "totals": {
                        "total": 0,
                        "done": 0,
                        "in_progress": 0,
                        "not_started": 0,
                        "overdue": 0,
                        "duration_hours": 0.0,
                    },
                    "message": (
                        "Chưa được phân quyền trên Báo cáo tổng. "
                        "Vào Cấu hình → Phân quyền Báo cáo tổng "
                        "để chọn phòng ban hoặc User bị xem."
                    ),
                }
            allowed = list(allowed_emp_ids)

        employees = self._hr_employee_rows_by_ids(allowed)
        if allowed_emp_ids is not None:
            allowed_set = set(allowed_emp_ids)
            employees = [e for e in employees if e.get("id") in allowed_set]
        if not employees:
            return {
                "year": year,
                "month": month,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "departments": [],
                "totals": {
                    "total": 0,
                    "done": 0,
                    "in_progress": 0,
                    "not_started": 0,
                    "overdue": 0,
                    "duration_hours": 0.0,
                },
                "message": "Không có nhân viên trong phạm vi được phân quyền.",
            }

        emp_ids = [e["id"] for e in employees]
        month_domain = [
            ("assignee_id.employee_id", "in", emp_ids),
            "|",
            "&",
            ("deadline", ">=", date_from),
            ("deadline", "<=", date_to),
            "&",
            ("assign_date", ">=", date_from),
            ("assign_date", "<=", date_to),
        ]
        tasks = self.sudo().search(month_domain)
        self._refresh_overdue_flags(tasks)

        stats_by_emp = {
            eid: {
                "total": 0,
                "done": 0,
                "in_progress": 0,
                "not_started": 0,
                "overdue": 0,
                "duration_minutes": 0,
            }
            for eid in emp_ids
        }
        for task in tasks:
            eid = (
                task.assignee_id.employee_id.id
                if task.assignee_id and task.assignee_id.employee_id
                else 0
            )
            if eid not in stats_by_emp:
                continue
            s = stats_by_emp[eid]
            s["total"] += 1
            if task.state == "done":
                s["done"] += 1
            elif task.state == "in_progress":
                s["in_progress"] += 1
            else:
                s["not_started"] += 1
            if task._is_overdue_today():
                s["overdue"] += 1
            s["duration_minutes"] += int(task.duration_minutes or 0)

        dept_map = {}
        for emp in employees:
            dept_name = (emp.get("department") or "").strip() or "Chưa có phòng ban"
            dept_key = dept_name.casefold()
            if dept_key not in dept_map:
                dept_map[dept_key] = {
                    "id": emp.get("department_id") or 0,
                    "name": dept_name,
                    "employees": [],
                }
            st = stats_by_emp.get(emp["id"]) or {}
            hours = round((st.get("duration_minutes") or 0) / 60.0, 2)
            dept_map[dept_key]["employees"].append(
                {
                    "id": emp["id"],
                    "name": emp.get("name") or "",
                    "total": st.get("total") or 0,
                    "done": st.get("done") or 0,
                    "in_progress": st.get("in_progress") or 0,
                    "not_started": st.get("not_started") or 0,
                    "overdue": st.get("overdue") or 0,
                    "duration_minutes": st.get("duration_minutes") or 0,
                    "duration_hours": hours,
                }
            )

        departments = list(dept_map.values())
        departments.sort(
            key=lambda d: (
                1 if d["name"] == "Chưa có phòng ban" else 0,
                d["name"].casefold(),
            )
        )
        for dept in departments:
            dept["employees"].sort(key=lambda e: (e.get("name") or "").casefold())
            for idx, row in enumerate(dept["employees"], start=1):
                row["stt"] = idx

        totals = {
            "total": 0,
            "done": 0,
            "in_progress": 0,
            "not_started": 0,
            "overdue": 0,
            "duration_minutes": 0,
            "duration_hours": 0.0,
        }
        for dept in departments:
            for row in dept["employees"]:
                totals["total"] += row["total"]
                totals["done"] += row["done"]
                totals["in_progress"] += row["in_progress"]
                totals["not_started"] += row["not_started"]
                totals["overdue"] += row["overdue"]
                totals["duration_minutes"] += row["duration_minutes"]
        totals["duration_hours"] = (
            round(totals["duration_minutes"] / 60.0, 2)
            if totals["duration_minutes"]
            else 0.0
        )

        return {
            "year": year,
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "departments": departments,
            "totals": totals,
            "message": False,
        }

    @api.model
    def _report_profile_for_employee(self, employee_id):
        """Hồ sơ NV cho báo cáo cá nhân (tên, chức danh, phòng, avatar)."""
        eid = int(employee_id or 0)
        if not eid:
            return {
                "id": False,
                "name": self.env.user.name or "",
                "job_title": "",
                "department": "",
                "avatar_url": "/web/image/res.users/%s/avatar_128" % self.env.user.id,
            }
        self.env.cr.execute(
            """
            SELECT e.id,
                   e.name,
                   COALESCE(NULLIF(v.job_title, ''), j.name->>'en_US', j.name::text, '') AS job_title,
                   COALESCE(d.name->>'en_US', d.name::text, '') AS department_name
              FROM hr_employee e
         LEFT JOIN hr_version v ON v.id = e.current_version_id
         LEFT JOIN hr_job j ON j.id = v.job_id
         LEFT JOIN hr_department d ON d.id = v.department_id
             WHERE e.id = %s
             LIMIT 1
            """,
            (eid,),
        )
        row = self.env.cr.fetchone()
        if not row:
            return {
                "id": eid,
                "name": self.env.user.name or "",
                "job_title": "",
                "department": "",
                "avatar_url": "/web/image/hr.employee/%s/avatar_128" % eid,
            }
        return {
            "id": row[0],
            "name": row[1] or "",
            "job_title": row[2] or "Nhân viên",
            "department": row[3] or "",
            "avatar_url": "/web/image/hr.employee/%s/avatar_128" % row[0],
        }

    @api.model
    def get_report_overview(self, year=None, month=None, filters=None):
        """
        Báo cáo công việc cá nhân (mẫu dashboard): KPI + biểu đồ + hôm nay /
        deadline / nhắc việc + bảng + đánh giá.
        filters: department_id, employee_id, work_group_id, state, search
        """
        from collections import defaultdict
        from datetime import timedelta

        filters = filters or {}
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        today = fields.Date.context_today(self)
        ReportAccess = self.env["daily.task.report.access"]
        allowed_emp_ids = ReportAccess.reportable_employee_ids_for_user()
        my = self._my_hr_employee()

        if self._is_manager():
            self.env.cr.execute(
                """
                SELECT e.id FROM hr_employee e
                 WHERE COALESCE(e.active, true) = true
              ORDER BY e.name
                """
            )
            allowed = [r[0] for r in self.env.cr.fetchall()]
        elif self._is_viewer():
            if not allowed_emp_ids and not my:
                return {
                    "year": year,
                    "month": month,
                    "message": (
                        "Chưa được phân quyền Báo cáo tổng. "
                        "Vào Cấu hình → Phân quyền Báo cáo tổng."
                    ),
                    "user_name": self.env.user.name or "",
                    "profile": self._report_profile_for_employee(False),
                    "kpi": {},
                    "rows": [],
                    "groups": [],
                    "charts": {},
                    "today": {"date_label": "", "tasks": [], "total_hours": 0},
                    "deadlines": {"in_1_day": [], "in_2_3_days": [], "this_week": []},
                    "reminders": {"overdue": 0, "today": 0, "tomorrow": 0, "this_week": 0},
                    "evaluation": {},
                    "filters": {"departments": [], "employees": [], "work_groups": []},
                    "can_delete": self._is_system_admin(),
                }
            allowed = list(allowed_emp_ids or [])
            if my and my.id not in allowed:
                allowed.append(my.id)
        elif my:
            allowed = [my.id]
        else:
            raise ValidationError(
                "Không tìm thấy hồ sơ nhân viên gắn với tài khoản. "
                "Liên hệ quản trị để liên kết hr.employee."
            )

        employees = self._hr_employee_rows_by_ids(allowed)
        emp_ids = [e["id"] for e in employees]
        emp_id = int(filters.get("employee_id") or 0)
        wg_id = int(filters.get("work_group_id") or 0)
        state_f = (filters.get("state") or "").strip()
        search = (filters.get("search") or "").strip().lower()
        personal_only = bool(filters.get("personal_only"))

        # Dashboard cá nhân: luôn khóa đúng user đang đăng nhập
        if personal_only:
            if not my:
                raise ValidationError(
                    "Không tìm thấy hồ sơ nhân viên gắn với tài khoản. "
                    "Liên hệ quản trị để liên kết hr.employee."
                )
            emp_id = my.id
        elif not emp_id:
            # Mặc định xem cá nhân: NV đang đăng nhập (nếu được phép)
            if my and my.id in (emp_ids or []):
                emp_id = my.id
            elif emp_ids:
                emp_id = emp_ids[0]

        profile = self._report_profile_for_employee(emp_id)

        domain = [
            ("assignee_id.employee_id", "=", emp_id or 0),
            "|",
            "&",
            ("deadline", ">=", date_from),
            ("deadline", "<=", date_to),
            "&",
            ("assign_date", ">=", date_from),
            ("assign_date", "<=", date_to),
        ]
        if wg_id:
            domain.append(("work_group_id", "=", wg_id))
        if state_f in ("done", "in_progress", "not_started"):
            domain.append(("state", "=", state_f))

        tasks = self.sudo().search(domain, order="deadline asc, id asc")
        self._refresh_overdue_flags(tasks)

        rows = []
        for task in tasks:
            data = task._to_manager_dict()
            if search:
                blob = " ".join(
                    [
                        data.get("name") or "",
                        data.get("work_group_label") or "",
                        data.get("note") or "",
                    ]
                ).lower()
                if search not in blob:
                    continue
            rows.append(data)
        for idx, row in enumerate(rows, start=1):
            row["stt"] = idx
            heid = row.get("hr_employee_id") or False
            row["assignee_avatar"] = (
                "/web/image/hr.employee/%s/avatar_128" % heid
                if heid
                else "/web/image/res.users/%s/avatar_128" % self.env.user.id
            )

        # Nhóm theo hạng mục (bảng danh sách)
        group_map = {}
        group_order = []
        for r in rows:
            key = r.get("work_group_id") or 0
            label = (r.get("work_group_label") or "").strip() or "Không có hạng mục"
            if key not in group_map:
                group_map[key] = {
                    "key": str(key),
                    "label": label,
                    "rows": [],
                    "minutes": 0,
                    "pct_sum": 0,
                    "done": 0,
                }
                group_order.append(key)
            g = group_map[key]
            g["rows"].append(r)
            g["minutes"] += int(r.get("duration_minutes") or 0)
            g["pct_sum"] += int(r.get("completion_percent") or 0)
            if r.get("state") == "done":
                g["done"] += 1

        groups = []
        for key in group_order:
            g = group_map[key]
            count = len(g["rows"])
            g_avg = round(g["pct_sum"] / float(count), 1) if count else 0.0
            g_hours = round(g["minutes"] / 60.0, 2) if g["minutes"] else 0.0
            # STT trong từng nhóm
            for idx, row in enumerate(g["rows"], start=1):
                row["stt"] = idx
            groups.append(
                {
                    "key": g["key"],
                    "label": g["label"],
                    "count": count,
                    "duration_hours": g_hours,
                    "avg_progress": g_avg,
                    "efficiency": g_avg,
                    "meta": "%s việc · %s giờ · %s%% HT"
                    % (
                        count,
                        ("%.2f" % g_hours).rstrip("0").rstrip(".") or "0",
                        g_avg,
                    ),
                    "rows": g["rows"],
                }
            )
        groups.sort(
            key=lambda x: (
                0 if x["key"] != "0" else 1,
                str(x["label"] or "").casefold(),
            )
        )

        # KPI
        total = len(rows)
        done = sum(1 for r in rows if r.get("state") == "done")
        in_progress = sum(1 for r in rows if r.get("state") == "in_progress")
        not_started = sum(1 for r in rows if r.get("state") == "not_started")
        overdue = sum(
            1
            for r in rows
            if r.get("is_active_overdue")
            or (r.get("state") != "done" and (r.get("overdue_days") or 0) > 0)
        )
        minutes = sum(int(r.get("duration_minutes") or 0) for r in rows)
        hours = round(minutes / 60.0, 2) if minutes else 0.0
        avg_progress = (
            round(
                sum(int(r.get("completion_percent") or 0) for r in rows) / float(len(rows)),
                1,
            )
            if rows
            else 0.0
        )
        efficiency = round((done / float(total)) * 100.0, 1) if total else 0.0

        # Thời gian theo hạng mục (biểu đồ ngang)
        time_map = defaultdict(int)
        for r in rows:
            label = (r.get("work_group_label") or "").strip() or "Khác"
            time_map[label] += int(r.get("duration_minutes") or 0)
        time_items = sorted(time_map.items(), key=lambda x: -x[1])[:6]
        cat_colors = ["#3b82f6", "#22c55e", "#eab308", "#a855f7", "#94a3b8", "#14b8a6"]
        by_time_category = {
            "labels": [x[0] for x in time_items],
            "values": [round(x[1] / 60.0, 1) for x in time_items],
            "colors": cat_colors[: len(time_items)],
        }

        # Donut: Hoàn thành / Đang thực hiện / Quá hạn / Chưa bắt đầu
        # (Quá hạn ưu tiên hơn trạng thái chưa xong)
        st_done = done
        st_progress = sum(
            1
            for r in rows
            if r.get("state") == "in_progress" and not r.get("is_active_overdue")
        )
        st_overdue = overdue
        st_todo = sum(
            1
            for r in rows
            if r.get("state") == "not_started" and not r.get("is_active_overdue")
        )
        state_legend = [
            {"key": "done", "label": "Hoàn thành", "count": st_done, "color": "#22c55e"},
            {
                "key": "in_progress",
                "label": "Đang thực hiện",
                "count": st_progress,
                "color": "#eab308",
            },
            {"key": "overdue", "label": "Quá hạn", "count": st_overdue, "color": "#ef4444"},
            {
                "key": "not_started",
                "label": "Chưa bắt đầu",
                "count": st_todo,
                "color": "#94a3b8",
            },
        ]
        for item in state_legend:
            item["pct"] = (
                round((item["count"] / float(total)) * 100, 1) if total else 0.0
            )
        by_state = {
            "labels": [x["label"] for x in state_legend],
            "values": [x["count"] for x in state_legend],
            "colors": [x["color"] for x in state_legend],
            "legend": state_legend,
            "center_total": total,
        }

        week_buckets = defaultdict(list)
        for r in rows:
            raw = r.get("deadline") or r.get("assign_date") or ""
            try:
                d = fields.Date.to_date(raw) if raw else False
            except Exception:
                d = False
            if not d:
                continue
            week_idx = min(5, max(1, ((d.day - 1) // 7) + 1))
            week_buckets[week_idx].append(int(r.get("completion_percent") or 0))
        weekly = {
            "labels": ["Tuần %s" % w for w in range(1, 6)],
            "values": [
                round(sum(week_buckets[w]) / float(len(week_buckets[w])), 1)
                if week_buckets.get(w)
                else 0.0
                for w in range(1, 6)
            ],
        }

        pri_order = [("high", "Cao", "#ef4444"), ("medium", "Trung bình", "#f59e0b"), ("low", "Thấp", "#3b82f6")]
        pri_counts = {k: sum(1 for r in rows if r.get("priority") == k) for k, _l, _c in pri_order}
        by_priority = {
            "labels": [l for _k, l, _c in pri_order],
            "values": [pri_counts[k] for k, _l, _c in pri_order],
            "colors": [c for _k, _l, c in pri_order],
        }
        wg_colors = ["#6366f1", "#22c55e", "#f59e0b", "#06b6d4", "#a855f7", "#94a3b8"]
        by_work_group = {
            "labels": [g["label"] for g in groups[:6]],
            "values": [g["count"] for g in groups[:6]],
            "colors": wg_colors[: max(1, min(6, len(groups)))],
        }

        # Việc active (không giới hạn tháng) cho hôm nay / deadline / nhắc
        active = self.sudo().search(
            [
                ("assignee_id.employee_id", "=", emp_id or 0),
                ("state", "!=", "done"),
            ],
            order="deadline asc, id asc",
        )
        self._refresh_overdue_flags(active)
        active_rows = []
        for t in active:
            data = t._to_manager_dict()
            heid = data.get("hr_employee_id") or False
            data["assignee_avatar"] = (
                "/web/image/hr.employee/%s/avatar_128" % heid
                if heid
                else "/web/image/res.users/%s/avatar_128" % self.env.user.id
            )
            active_rows.append(data)

        weekday_vi = [
            "Thứ Hai",
            "Thứ Ba",
            "Thứ Tư",
            "Thứ Năm",
            "Thứ Sáu",
            "Thứ Bảy",
            "Chủ Nhật",
        ]
        today_label = "%s, %s" % (
            weekday_vi[today.weekday()],
            today.strftime("%d/%m/%Y"),
        )

        def _deadline(r):
            raw = r.get("deadline") or ""
            try:
                return fields.Date.to_date(raw) if raw else False
            except Exception:
                return False

        def _in_range(r, d_from, d_to):
            d = _deadline(r)
            if not d:
                return False
            return d_from <= d <= d_to

        # Việc hạn đúng hôm nay
        today_tasks = [r for r in active_rows if _deadline(r) == today]
        today_hours = round(
            sum(float(r.get("duration_hours") or 0) for r in today_tasks), 1
        )

        d1 = today + timedelta(days=1)
        d3 = today + timedelta(days=3)
        week_end = today + timedelta(days=(6 - today.weekday()))
        upcoming_end = today + timedelta(days=7)
        deadlines = {
            "in_1_day": [r for r in active_rows if _in_range(r, d1, d1)],
            "in_2_3_days": [r for r in active_rows if _in_range(r, today + timedelta(days=2), d3)],
            "this_week": [
                r
                for r in active_rows
                if _in_range(r, today + timedelta(days=4), week_end)
            ],
        }
        overdue_tasks = [r for r in active_rows if r.get("is_active_overdue")]
        # Sắp tới hạn: còn hạn từ hôm nay → 7 ngày tới (chưa quá hạn)
        upcoming_tasks = [
            r
            for r in active_rows
            if not r.get("is_active_overdue") and _in_range(r, today, upcoming_end)
        ]
        for idx, row in enumerate(overdue_tasks, start=1):
            row["stt"] = idx
        for idx, row in enumerate(upcoming_tasks, start=1):
            row["stt"] = idx
        reminders = {
            "overdue": len(overdue_tasks),
            "today": len(today_tasks),
            "tomorrow": len(deadlines["in_1_day"]),
            "this_week": sum(
                1 for r in active_rows if _in_range(r, today, week_end)
            ),
            "upcoming": len(upcoming_tasks),
            "overdue_tasks": overdue_tasks,
            "upcoming_tasks": upcoming_tasks,
        }
        near_deadline = len(
            [
                r
                for r in active_rows
                if not r.get("is_active_overdue") and _in_range(r, today, d3)
            ]
        )
        recent_tasks = sorted(
            rows,
            key=lambda r: int(r.get("id") or 0),
            reverse=True,
        )[:8]
        alerts = [
            {
                "key": "overdue",
                "tone": "danger",
                "icon": "fa-exclamation-circle",
                "title": "%s việc quá hạn" % len(overdue_tasks),
                "subtitle": "Cần xử lý ngay",
                "count": len(overdue_tasks),
            },
            {
                "key": "near",
                "tone": "warning",
                "icon": "fa-clock-o",
                "title": "%s việc gần đến hạn" % near_deadline,
                "subtitle": "Trong 3 ngày tới",
                "count": near_deadline,
            },
            {
                "key": "today",
                "tone": "info",
                "icon": "fa-calendar-check-o",
                "title": "%s việc hôm nay" % len(today_tasks),
                "subtitle": today_label,
                "count": len(today_tasks),
            },
        ]
        hour = fields.Datetime.context_timestamp(self, fields.Datetime.now()).hour
        if hour < 12:
            greet = "Chào buổi sáng"
        elif hour < 18:
            greet = "Chào buổi chiều"
        else:
            greet = "Chào buổi tối"

        rating = "Trung bình"
        if efficiency >= 85 or avg_progress >= 85:
            rating = "Tốt"
        elif efficiency >= 70 or avg_progress >= 70:
            rating = "Khá"
        elif efficiency < 50 and avg_progress < 50:
            rating = "Cần cải thiện"
        stars = min(5.0, round((efficiency / 20.0) * 2) / 2.0) if efficiency else 0.0

        depts = {}
        for e in employees:
            did = e.get("department_id") or 0
            if did and did not in depts:
                depts[did] = e.get("department") or "—"
        work_groups = self.env["daily.task.work.group"].sudo().search_read(
            [("active", "=", True)],
            ["id", "name"],
            order="name",
            limit=200,
        )

        return {
            "year": year,
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "message": False,
            "user_name": self.env.user.name or "",
            "profile": profile,
            "selected_employee_id": emp_id,
            "kpi": {
                "total": total,
                "done": done,
                "in_progress": in_progress,
                "not_started": not_started,
                "overdue": overdue,
                "near_deadline": near_deadline,
                "duration_hours": hours,
                "efficiency": efficiency,
                "avg_progress": avg_progress,
                "done_pct": round((done / float(total)) * 100, 1) if total else 0.0,
                "in_progress_pct": round((in_progress / float(total)) * 100, 1)
                if total
                else 0.0,
                "not_started_pct": round((not_started / float(total)) * 100, 1)
                if total
                else 0.0,
                "overdue_pct": round((overdue / float(total)) * 100, 1) if total else 0.0,
                "near_deadline_pct": round((near_deadline / float(total)) * 100, 1)
                if total
                else 0.0,
                "rating": rating,
            },
            "rows": rows,
            "groups": groups,
            "charts": {
                "by_state": by_state,
                "by_time_category": by_time_category,
                "by_priority": by_priority,
                "by_work_group": by_work_group,
                "weekly": weekly,
            },
            "today": {
                "date_label": today_label,
                "tasks": today_tasks,
                "total_hours": today_hours,
            },
            "deadlines": deadlines,
            "reminders": reminders,
            "recent_tasks": recent_tasks,
            "alerts": alerts,
            "greeting": greet,
            "evaluation": {
                "score": efficiency,
                "stars": stars,
                "rating": rating,
                "total": total,
                "done": done,
                "overdue": overdue,
                "hours": hours,
            },
            "filters": {
                "departments": [
                    {"id": k, "name": v}
                    for k, v in sorted(depts.items(), key=lambda x: x[1])
                ],
                "employees": [
                    {
                        "id": e["id"],
                        "name": e.get("name") or "",
                        "department_id": e.get("department_id") or 0,
                    }
                    for e in employees
                ],
                "work_groups": work_groups,
            },
            "can_delete": self._is_system_admin(),
            "can_pick_employee": False
            if personal_only
            else (self._is_viewer() or self._is_manager()),
            "personal_only": personal_only,
        }

    @api.model
    def _personal_report_sign_block(self, preparer_name=None):
        """Khối chữ ký cuối báo cáo: địa điểm/ngày + 3 cột ký."""
        today = fields.Date.context_today(self)
        ICP = self.env["ir.config_parameter"].sudo()
        place = ICP.get_param("daily_work_task.sign_place", "TP.HCM") or "TP.HCM"
        # Người lập = user đăng nhập (có thể ghi đè bằng preparer_name)
        preparer = (preparer_name or "").strip() or (self.env.user.name or "").strip() or "—"
        dept_head = ICP.get_param("daily_work_task.sign_dept_head", "") or ""
        director = (
            ICP.get_param("daily_work_task.sign_director", "Huỳnh Thị Thanh Tâm")
            or "Huỳnh Thị Thanh Tâm"
        )
        return {
            "date_label": "%s, ngày %02d tháng %02d năm %s"
            % (place, today.day, today.month, today.year),
            "preparer": preparer,
            "dept_head": dept_head,
            "director": director,
        }

    @api.model
    def _work_group_export_icon(self, label):
        text = (label or "").casefold()
        if any(k in text for k in ("máy vi tính", "vi tính", "cntt", "tin học", "laptop")):
            return "💻"
        if "camera" in text:
            return "📷"
        if "điện" in text:
            return "⚡"
        if any(k in text for k in ("máy lạnh", "điều hòa")):
            return "❄️"
        if "xe" in text:
            return "🚗"
        return "📁"

    @api.model
    def _decode_data_url_image(self, data_url):
        """Decode data:image/...;base64,... → BytesIO PNG."""
        import base64
        import io

        if not data_url:
            return False
        raw = data_url
        if isinstance(raw, str) and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            bio = io.BytesIO(base64.b64decode(raw))
            bio.seek(0)
            return bio
        except Exception:
            return False

    @api.model
    def export_personal_report_excel(self, year=None, month=None, filters=None, chart_images=None):
        """
        Xuất Excel báo cáo cá nhân: logo + KPI + ảnh biểu đồ (từ canvas) + bảng nhóm.
        chart_images: {state, weekly, eval} dataURL base64 từ UI.
        """
        import base64
        import io
        import re

        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError(
                "Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter"
            ) from exc

        data = self.get_report_overview(year=year, month=month, filters=filters or {})
        if data.get("message"):
            raise ValidationError(data["message"])

        year = data["year"]
        month = data["month"]
        profile = data.get("profile") or {}
        kpi = data.get("kpi") or {}
        evaluation = data.get("evaluation") or {}
        groups = data.get("groups") or []
        chart_images = chart_images or {}

        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Bao_cao_ca_nhan")
        ws.set_landscape()
        ws.set_paper(9)
        ws.set_margins(left=0.35, right=0.35, top=0.4, bottom=0.4)
        ws.hide_gridlines(2)

        FONT = "Times New Roman"
        GREEN = "#166534"
        GREEN_SOFT = "#ecfdf5"
        GREEN_MID = "#bbf7d0"
        BORDER_CLR = "#166534"

        def fmt(**kw):
            d = {"font_name": FONT, "font_size": 11}
            d.update(kw)
            return wb.add_format(d)

        # Khung ngoài section
        box_title = fmt(
            bold=True, font_size=12, font_color="#14532d", bg_color=GREEN_SOFT,
            align="left", valign="vcenter",
            border=2, border_color=BORDER_CLR,
        )
        box_empty = fmt(border=1, border_color=BORDER_CLR, bg_color="#ffffff")
        box_empty_soft = fmt(border=1, border_color=GREEN_MID, bg_color="#f8fafc")

        title_fmt = fmt(
            bold=True, font_size=16, font_color="#14532d", align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR, bg_color="#ffffff",
        )
        sub_fmt = fmt(
            bold=True, font_size=11, font_color="#166534", align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )
        meta_fmt = fmt(
            font_size=10, font_color="#334155", align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )
        kpi_label = fmt(
            bold=True, font_size=9, font_color="#64748b", align="center", valign="vcenter",
            border=1, border_color=GREEN_MID, bg_color=GREEN_SOFT,
        )
        kpi_val = fmt(
            bold=True, font_size=14, font_color="#14532d", align="center", valign="vcenter",
            border=1, border_color=GREEN_MID, bg_color="#ffffff",
        )
        kpi_sub = fmt(
            font_size=9, font_color="#64748b", align="center", valign="vcenter",
            border=1, border_color=GREEN_MID, bg_color="#ffffff",
        )
        chart_caption = fmt(
            bold=True, font_size=10, font_color="#14532d", align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR, bg_color=GREEN_SOFT,
        )
        chart_body = fmt(
            border=2, border_color=BORDER_CLR, bg_color="#ffffff", valign="vcenter",
        )
        section_fmt = box_title
        group_fmt = fmt(
            bold=True, font_size=11, font_color="#14532d", bg_color="#f0fdf4",
            border=2, border_color=BORDER_CLR, valign="vcenter",
        )
        header_fmt = fmt(
            bold=True, font_size=10, bg_color=GREEN, font_color="#ffffff",
            align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )
        cell_fmt = fmt(border=1, border_color="#94a3b8", valign="vcenter", text_wrap=True)
        center_fmt = fmt(
            border=1, border_color="#94a3b8", align="center", valign="vcenter",
        )
        urgent_fmt = fmt(
            border=1, border_color="#94a3b8", font_color="#dc2626", bold=True, valign="vcenter",
        )
        frame_fill = fmt(border=2, border_color=BORDER_CLR, bg_color="#ffffff")

        # Cột rộng
        widths = [6, 28, 12, 12, 14, 12, 11, 18, 22, 12]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)

        r = 0
        # ===== KHUNG HEADER =====
        # Hàng 1: logo | tiêu đề
        logo = self._sataco_logo_bytes()
        if logo:
            ws.set_row(r, 70)
            ws.insert_image(
                r, 0, "sataco_logo.png",
                {"image_data": logo, "x_scale": 0.85, "y_scale": 0.85},
            )
        ws.write(r, 0, "", frame_fill)
        ws.write(r, 1, "", frame_fill)
        ws.merge_range(r, 2, r, 9, "BÁO CÁO CÔNG VIỆC CÁ NHÂN", title_fmt)
        r += 1
        # Hàng 2: họ tên · phòng ban (căn giữa, cạnh tiêu đề)
        name_dept = "%s%s" % (
            profile.get("name") or "",
            (" · %s" % profile.get("department")) if profile.get("department") else "",
        )
        ws.merge_range(r, 2, r, 9, name_dept, sub_fmt)
        ws.write(r, 0, "", frame_fill)
        ws.write(r, 1, "", frame_fill)
        r += 1
        # Hàng 3: Tháng MM/YYYY — dòng riêng, căn giữa toàn bảng
        month_fmt = fmt(
            bold=True, font_size=12, font_color="#166534",
            align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )
        ws.merge_range(r, 0, r, 9, "Tháng %02d/%s" % (month, year), month_fmt)
        r += 2

        # ===== KHUNG KPI =====
        ws.merge_range(r, 0, r, 9, "  ■ TỔNG QUAN KPI", section_fmt)
        r += 1
        kpi_items = [
            ("Tổng CV", kpi.get("total"), "100%"),
            ("Hoàn thành", kpi.get("done"), "%s%%" % (kpi.get("done_pct") or 0)),
            ("Đang thực hiện", kpi.get("in_progress"), "%s%%" % (kpi.get("in_progress_pct") or 0)),
            ("Quá hạn", kpi.get("overdue"), "%s%%" % (kpi.get("overdue_pct") or 0)),
            ("Tổng giờ", kpi.get("duration_hours"), "giờ"),
            ("Hiệu suất", "%s%%" % (kpi.get("efficiency") or 0), "chung"),
            ("Tiến độ TB", "%s%%" % (kpi.get("avg_progress") or 0), ""),
        ]
        for col in range(10):
            if col < len(kpi_items):
                lab, val, sub = kpi_items[col]
                ws.write(r, col, lab, kpi_label)
                ws.write(r + 1, col, val if val is not None else 0, kpi_val)
                ws.write(r + 2, col, sub, kpi_sub)
            else:
                ws.write(r, col, "", kpi_label)
                ws.write(r + 1, col, "", kpi_val)
                ws.write(r + 2, col, "", kpi_sub)
        r += 4

        # ===== KHUNG BIỂU ĐỒ: dán 3 ảnh chụp cả thẻ UI (như xu hướng tuần) =====
        ws.merge_range(r, 0, r, 9, "  ■ BIỂU ĐỒ", section_fmt)
        r += 1
        chart_label_row = r
        for c1, c2, label in (
            (0, 2, "Tỷ lệ trạng thái công việc"),
            (3, 5, "Xu hướng hoàn thành công việc (theo tuần)"),
            (6, 9, "Đánh giá hiệu suất tháng"),
        ):
            ws.merge_range(chart_label_row, c1, chart_label_row, c2, label, chart_caption)
        r += 1

        pane_box = fmt(
            border=2, border_color=BORDER_CLR, bg_color="#ffffff",
            valign="vcenter", align="center",
        )
        img_h = 12
        body_top = r
        body_bottom = r + img_h - 1
        for rr in range(body_top, body_bottom + 1):
            ws.set_row(rr, 15)

        panels = [
            ("state", 0, 2, 0.42),
            ("weekly", 3, 5, 0.42),
            ("eval", 6, 9, 0.42),
        ]
        for key, c1, c2, scale in panels:
            ws.merge_range(body_top, c1, body_bottom, c2, "", pane_box)
            img = self._decode_data_url_image(chart_images.get(key))
            if img:
                ws.insert_image(
                    body_top,
                    c1,
                    "%s.png" % key,
                    {
                        "image_data": img,
                        "x_scale": scale,
                        "y_scale": scale,
                        "x_offset": 6,
                        "y_offset": 6,
                    },
                )

        r = body_bottom + 2

        # ===== KHUNG BẢNG NHÓM =====
        headers = [
            "STT", "Công việc", "Ưu tiên", "Tiến độ", "Trạng thái",
            "Deadline", "Thời gian", "Người phụ trách", "Ghi chú", "Quá hạn",
        ]
        for group in groups:
            ws.merge_range(
                r, 0, r, 9,
                "%s %s  (%s)"
                % (
                    self._work_group_export_icon(group.get("label")),
                    group.get("label") or "",
                    group.get("meta") or "",
                ),
                group_fmt,
            )
            r += 1
            for col, h in enumerate(headers):
                ws.write(r, col, h, header_fmt)
            r += 1
            rows_in_group = group.get("rows") or []
            if not rows_in_group:
                for col in range(10):
                    ws.write(r, col, "" if col else "(không có công việc)", cell_fmt)
                r += 1
            for row in rows_in_group:
                vals = [
                    row.get("stt") or "",
                    row.get("name") or "",
                    row.get("priority_label") or "",
                    "%s%%" % (row.get("completion_percent") or 0),
                    row.get("state_label") or "",
                    row.get("deadline_display") or "",
                    "%s giờ" % (row.get("duration_hours_display") or 0),
                    row.get("assignee_name") or "",
                    row.get("note") or "",
                    row.get("overdue_label") or "",
                ]
                for col, val in enumerate(vals):
                    use = urgent_fmt if (col in (5, 9) and row.get("is_active_overdue")) else (
                        center_fmt if col in (0, 3, 6) else cell_fmt
                    )
                    ws.write(r, col, val, use)
                r += 1
            for col in range(10):
                ws.write(r, col, "", box_empty_soft)
            r += 1

        # ===== KHUNG CHỮ KÝ =====
        sign = self._personal_report_sign_block()
        date_fmt = fmt(
            bold=True, italic=True, font_size=11, font_color="#0f172a",
            align="right", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )
        sign_title = fmt(
            bold=True, font_size=11, font_color="#0f172a",
            align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR, bg_color=GREEN_SOFT,
        )
        sign_space = fmt(
            border=1, border_color=BORDER_CLR, bg_color="#ffffff",
        )
        sign_name = fmt(
            bold=True, font_size=11, font_color="#0f172a",
            align="center", valign="vcenter",
            border=1, border_color=BORDER_CLR,
        )

        r += 1
        # Dòng ngày — căn phải (không có tiêu đề ■ CHỮ KÝ)
        ws.merge_range(r, 0, r, 5, "", sign_space)
        ws.merge_range(r, 6, r, 9, sign["date_label"], date_fmt)
        r += 1
        # Tiêu đề 3 cột: A–C | D–F | G–J
        ws.merge_range(r, 0, r, 2, "Người lập", sign_title)
        ws.merge_range(r, 3, r, 5, "Trưởng bộ phận", sign_title)
        ws.merge_range(r, 6, r, 9, "Giám đốc", sign_title)
        r += 1
        # Khoảng trống ký (~5 dòng)
        for _ in range(5):
            ws.set_row(r, 18)
            ws.merge_range(r, 0, r, 2, "", sign_space)
            ws.merge_range(r, 3, r, 5, "", sign_space)
            ws.merge_range(r, 6, r, 9, "", sign_space)
            r += 1
        # Họ tên
        ws.merge_range(r, 0, r, 2, sign.get("preparer") or "", sign_name)
        ws.merge_range(r, 3, r, 5, sign.get("dept_head") or "", sign_name)
        ws.merge_range(r, 6, r, 9, sign.get("director") or "", sign_name)
        r += 1

        wb.close()
        raw = buffer.getvalue()
        safe_name = re.sub(r"[^\w\-]+", "_", profile.get("name") or "NhanVien")
        filename = "Bao_cao_ca_nhan_%s_%02d_%s.xlsx" % (safe_name, month, year)
        return {
            "filename": filename,
            "file_base64": base64.b64encode(raw).decode("ascii"),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

    @api.model
    def export_personal_report_pdf(self, year=None, month=None, filters=None, chart_images=None):
        """Xuất PDF: logo + KPI + ảnh biểu đồ canvas + bảng nhóm hạng mục."""
        import base64
        import io
        import re

        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                Image as RLImage,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise ValidationError(
                "Thiếu thư viện reportlab. Cài đặt: pip install reportlab"
            ) from exc

        data = self.get_report_overview(year=year, month=month, filters=filters or {})
        if data.get("message"):
            raise ValidationError(data["message"])

        year = data["year"]
        month = data["month"]
        profile = data.get("profile") or {}
        kpi = data.get("kpi") or {}
        evaluation = data.get("evaluation") or {}
        groups = data.get("groups") or []
        chart_images = chart_images or {}

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleVN",
            parent=styles["Title"],
            fontSize=16,
            textColor=colors.HexColor("#14532d"),
            alignment=TA_CENTER,
            spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "SubVN",
            parent=styles["Normal"],
            fontSize=11,
            textColor=colors.HexColor("#166534"),
            alignment=TA_CENTER,
            spaceAfter=8,
        )
        body = ParagraphStyle(
            "BodyVN",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
        )
        small = ParagraphStyle(
            "SmallVN", parent=body, fontSize=8, textColor=colors.HexColor("#64748b")
        )

        story = []
        header_bits = []
        logo = self._sataco_logo_bytes()
        if logo:
            try:
                header_bits.append(RLImage(logo, width=42 * mm, height=18 * mm))
            except Exception:
                pass
        header_bits.append(
            Paragraph(
                "<b>BÁO CÁO CÔNG VIỆC CÁ NHÂN</b>",
                title_style,
            )
        )
        if len(header_bits) == 2:
            ht = Table([[header_bits[0], header_bits[1]]], colWidths=[50 * mm, 220 * mm])
            ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story.append(ht)
        else:
            story.append(header_bits[0])
        story.append(
            Paragraph(
                "%s%s"
                % (
                    profile.get("name") or "",
                    (" · %s" % profile.get("department")) if profile.get("department") else "",
                ),
                sub_style,
            )
        )
        story.append(
            Paragraph(
                "<b>Tháng %02d/%s</b>" % (month, year),
                sub_style,
            )
        )
        story.append(Spacer(1, 3 * mm))

        # KPI table
        kpi_data = [
            ["Tổng CV", "Hoàn thành", "Đang TH", "Quá hạn", "Giờ", "Hiệu suất", "Tiến độ"],
            [
                str(kpi.get("total") or 0),
                "%s (%s%%)" % (kpi.get("done") or 0, kpi.get("done_pct") or 0),
                "%s (%s%%)" % (kpi.get("in_progress") or 0, kpi.get("in_progress_pct") or 0),
                "%s (%s%%)" % (kpi.get("overdue") or 0, kpi.get("overdue_pct") or 0),
                str(kpi.get("duration_hours") or 0),
                "%s%%" % (kpi.get("efficiency") or 0),
                "%s%%" % (kpi.get("avg_progress") or 0),
            ],
        ]
        kt = Table(kpi_data, colWidths=[35 * mm] * 7)
        kt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#14532d")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#166534")),
                    ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#166534")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(kt)
        story.append(Spacer(1, 6 * mm))

        # 3 ảnh chụp cả thẻ biểu đồ (giống dán ảnh Excel)
        def _panel_img(key, title):
            bits = [Paragraph("<b>%s</b>" % title, body)]
            img = self._decode_data_url_image(chart_images.get(key))
            if img:
                try:
                    bits.append(RLImage(img, width=86 * mm, height=58 * mm))
                except Exception:
                    bits.append(Paragraph("(không đọc được ảnh)", small))
            else:
                bits.append(Paragraph("(không có ảnh khung biểu đồ)", small))
            inner = Table([[b] for b in bits], colWidths=[88 * mm])
            inner.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#166534")),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                    ]
                )
            )
            return inner

        ct = Table(
            [[
                _panel_img("state", "Tỷ lệ trạng thái công việc"),
                _panel_img("weekly", "Xu hướng hoàn thành công việc (theo tuần)"),
                _panel_img("eval", "Đánh giá hiệu suất tháng"),
            ]],
            colWidths=[90 * mm, 90 * mm, 90 * mm],
        )
        ct.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(ct)
        story.append(Spacer(1, 4 * mm))

        for group in groups:
            story.append(
                Paragraph(
                    "<b>%s %s</b> <font color='#64748b'>(%s)</font>"
                    % (
                        self._work_group_export_icon(group.get("label")),
                        group.get("label") or "",
                        group.get("meta") or "",
                    ),
                    body,
                )
            )
            table_data = [[
                "STT", "Công việc", "Ưu tiên", "Tiến độ", "Trạng thái",
                "Deadline", "Giờ", "PT", "Ghi chú",
            ]]
            for row in group.get("rows") or []:
                table_data.append([
                    str(row.get("stt") or ""),
                    Paragraph(row.get("name") or "", small),
                    row.get("priority_label") or "",
                    "%s%%" % (row.get("completion_percent") or 0),
                    row.get("state_label") or "",
                    row.get("deadline_display") or "",
                    str(row.get("duration_hours_display") or 0),
                    Paragraph(row.get("assignee_name") or "", small),
                    Paragraph((row.get("note") or "—")[:80], small),
                ])
            col_w = [10 * mm, 48 * mm, 22 * mm, 16 * mm, 24 * mm, 20 * mm, 14 * mm, 28 * mm, 40 * mm]
            gt = Table(table_data, colWidths=col_w, repeatRows=1)
            style_cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (6, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
            for i, row in enumerate(group.get("rows") or [], start=1):
                if row.get("is_active_overdue"):
                    style_cmds.append(("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#dc2626")))
            gt.setStyle(TableStyle(style_cmds))
            story.append(gt)
            story.append(Spacer(1, 3 * mm))

        # ===== Chữ ký =====
        sign = self._personal_report_sign_block()
        story.append(Spacer(1, 6 * mm))
        date_style = ParagraphStyle(
            "SignDate",
            parent=styles["Normal"],
            fontSize=10,
            alignment=2,  # TA_RIGHT
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        )
        sign_head = ParagraphStyle(
            "SignHead",
            parent=styles["Normal"],
            fontSize=10,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0f172a"),
        )
        sign_name_st = ParagraphStyle(
            "SignName",
            parent=styles["Normal"],
            fontSize=10,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0f172a"),
        )
        story.append(Paragraph(sign["date_label"], date_style))
        sign_tbl = Table(
            [
                [
                    Paragraph("Người lập", sign_head),
                    Paragraph("Trưởng bộ phận", sign_head),
                    Paragraph("Giám đốc", sign_head),
                ],
                ["", "", ""],
                ["", "", ""],
                ["", "", ""],
                ["", "", ""],
                ["", "", ""],
                [
                    Paragraph(sign.get("preparer") or "", sign_name_st),
                    Paragraph(sign.get("dept_head") or "", sign_name_st),
                    Paragraph(sign.get("director") or "", sign_name_st),
                ],
            ],
            colWidths=[90 * mm, 90 * mm, 90 * mm],
        )
        sign_tbl.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#166534")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#166534")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 1), (-1, -2), 8),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                    ("TOPPADDING", (0, -1), (-1, -1), 6),
                ]
            )
        )
        story.append(sign_tbl)

        doc.build(story)
        raw = buffer.getvalue()
        safe_name = re.sub(r"[^\w\-]+", "_", profile.get("name") or "NhanVien")
        filename = "Bao_cao_ca_nhan_%s_%02d_%s.pdf" % (safe_name, month, year)
        return {
            "filename": filename,
            "file_base64": base64.b64encode(raw).decode("ascii"),
            "mimetype": "application/pdf",
        }

    @api.model
    def export_summary_report_excel(self, year=None, month=None):
        """Xuất Excel Báo cáo tổng theo mẫu phòng ban."""
        import base64
        import io

        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError(
                "Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter"
            ) from exc

        data = self.get_summary_report(year=year, month=month)
        year = data["year"]
        month = data["month"]
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Bao_cao_tong")

        title_fmt = wb.add_format(
            {"bold": True, "font_size": 14, "font_color": "#1e3a5f"}
        )
        dept_fmt = wb.add_format({"bold": True, "font_size": 11, "font_color": "#0f172a"})
        header_fmt = wb.add_format(
            {
                "bold": True,
                "bg_color": "#1e3a5f",
                "font_color": "#ffffff",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        cell_fmt = wb.add_format({"border": 1, "valign": "vcenter"})
        center_fmt = wb.add_format(
            {"border": 1, "align": "center", "valign": "vcenter"}
        )
        overdue_fmt = wb.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#b91c1c",
                "bold": True,
            }
        )

        headers = [
            "STT",
            "HỌ VÀ TÊN NV",
            "Tổng số",
            "Hoàn Thành",
            "Đang xử lý",
            "Chưa bắt đầu",
            "Quá hạn",
            "Tổng giờ",
        ]
        r = 0
        ws.write(r, 0, "Báo cáo tổng — Tháng %02d/%s" % (month, year), title_fmt)
        r += 2

        for dept in data.get("departments") or []:
            ws.write(r, 0, dept.get("name") or "", dept_fmt)
            r += 1
            for col, h in enumerate(headers):
                ws.write(r, col, h, header_fmt)
            r += 1
            rows = dept.get("employees") or []
            if not rows:
                ws.write(r, 0, "", cell_fmt)
                for col in range(1, 8):
                    ws.write(r, col, "", cell_fmt)
                r += 1
            else:
                for emp in rows:
                    vals = [
                        emp.get("stt") or "",
                        emp.get("name") or "",
                        emp.get("total") or 0,
                        emp.get("done") or 0,
                        emp.get("in_progress") or 0,
                        emp.get("not_started") or 0,
                        emp.get("overdue") or 0,
                        emp.get("duration_hours") or 0,
                    ]
                    for col, val in enumerate(vals):
                        fmt = overdue_fmt if col == 6 and val else (
                            center_fmt if col != 1 else cell_fmt
                        )
                        ws.write(r, col, val, fmt)
                    r += 1
            r += 1

        widths = [6, 28, 10, 12, 12, 14, 10, 10]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        wb.close()
        raw = buffer.getvalue()
        filename = "Bao_cao_tong_%02d_%s.xlsx" % (month, year)
        return {
            "filename": filename,
            "file_base64": base64.b64encode(raw).decode("ascii"),
        }

    @api.model
    def get_manager_bootstrap(self):
        is_manager = self._is_manager()
        my_emp = self._my_hr_employee()
        hr_domain = [("active", "=", True)]
        if not is_manager:
            if my_emp:
                hr_domain = [("id", "=", my_emp.id)]
            else:
                hr_domain = [("id", "=", 0)]
        hr_employees = self.env["hr.employee"].search_read(
            hr_domain,
            ["id", "name", "department_id", "work_email"],
            order="name",
        )
        bridges = self.env["daily.task.employee"].search([("active", "=", True)])
        bridge_by_hr = {b.employee_id.id: b.id for b in bridges if b.employee_id}
        employees = []
        for h in hr_employees:
            dept_id = False
            dept_name = ""
            if h.get("department_id"):
                dept_id = h["department_id"][0]
                dept_name = h["department_id"][1] or ""
            employees.append(
                {
                    "id": h["id"],
                    "name": h["name"] or "",
                    "bridge_id": bridge_by_hr.get(h["id"]) or False,
                    "department_id": dept_id or False,
                    "department": dept_name,
                    "email": h.get("work_email") or "",
                }
            )

        if is_manager:
            departments = self.env["hr.department"].search_read(
                [], ["id", "name"], order="name"
            )
            departments = [{"id": d["id"], "name": d.get("name") or ""} for d in departments]
        elif my_emp and my_emp.department_id:
            departments = [
                {"id": my_emp.department_id.id, "name": my_emp.department_id.name or ""}
            ]
        else:
            departments = []
        priorities = [
            {"value": k, "label": v}
            for k, v in self._fields["priority"].selection
        ]
        states = [
            {"value": k, "label": v}
            for k, v in self._fields["state"].selection
        ]
        return {
            "is_manager": is_manager,
            "can_delete": self._is_system_admin(),
            "employees": employees,
            "departments": departments,
            "priorities": priorities,
            "states": states,
            "tasks": self.get_manager_tasks(),
        }

    @api.model
    def get_manager_tasks(self):
        tasks = self.search([], order="deadline asc, id desc")
        return [t._to_manager_dict() for t in tasks]

    @api.model
    def create_from_manager(self, vals):
        if not self._is_manager():
            raise ValidationError(
                "Bạn không có quyền tạo công việc. Chỉ quản lý được giao việc."
            )
        hr_id = int(vals.get("assignee_id") or 0)
        if not hr_id:
            raise ValidationError("Vui lòng chọn người phụ trách.")
        bridge = self.env["daily.task.employee"].get_or_create_from_hr(hr_id)
        hr = self.env["hr.employee"].browse(hr_id)
        department_id = int(vals.get("department_id") or 0) or False
        if not department_id and hr.department_id:
            department_id = hr.department_id.id
        assigner_uid = self.env.uid
        task = self.with_context(daily_task_assigner_uid=assigner_uid).create(
            {
                "name": (vals.get("name") or "").strip(),
                "assign_date": vals.get("assign_date") or fields.Date.context_today(self),
                "assigned_by_id": assigner_uid,
                "deadline": vals.get("deadline"),
                "department_id": department_id,
                "assignee_id": bridge.id,
                "priority": vals.get("priority") or "medium",
                "state": vals.get("state") or "not_started",
                "note": vals.get("note") or "",
            }
        )
        task._notify_assignee_assigned()
        return task._to_manager_dict()

    def update_from_manager(self, vals):
        self.ensure_one()
        if not self._can_edit_task():
            raise ValidationError("Bạn không có quyền chỉnh sửa công việc này.")
        write_vals = {}
        is_manager = self._is_manager()
        my = self._my_hr_employee()
        is_own = bool(
            my and self.assignee_id.employee_id and self.assignee_id.employee_id.id == my.id
        )
        has_edit = is_manager or (
            self.assignee_id.employee_id
            and self.assignee_id.employee_id.id in (self._editable_employee_ids() or [])
        )
        can_edit_content = is_own or has_edit or is_manager
        if "name" in vals and can_edit_content:
            name = (vals.get("name") or "").strip()
            if not name:
                raise ValidationError("Tên công việc không được để trống.")
            write_vals["name"] = name
        if "deadline" in vals and can_edit_content:
            if not vals.get("deadline"):
                raise ValidationError("Hạn hoàn thành không được để trống.")
            write_vals["deadline"] = vals["deadline"]
        if "assign_date" in vals and can_edit_content:
            write_vals["assign_date"] = vals.get("assign_date") or False
        if "state" in vals and vals.get("state") and (is_own or has_edit):
            write_vals["state"] = vals["state"]
        if "note" in vals and can_edit_content:
            write_vals["note"] = vals.get("note") or ""
        if "priority" in vals and vals.get("priority") and can_edit_content:
            write_vals["priority"] = vals["priority"]
        if "department_id" in vals and is_manager:
            write_vals["department_id"] = int(vals.get("department_id") or 0) or False
        if "work_group_id" in vals and can_edit_content:
            wg_id = int(vals.get("work_group_id") or 0) or False
            if wg_id:
                group = self.env["daily.task.work.group"].sudo().browse(wg_id)
                dept = self.department_id
                if not group.exists():
                    raise ValidationError("Nhóm công việc không hợp lệ.")
                if dept and group.department_id and group.department_id != dept:
                    raise ValidationError(
                        "Nhóm công việc phải thuộc cùng phòng ban với công việc."
                    )
            write_vals["work_group_id"] = wg_id
        if "duration_minutes" in vals and can_edit_content:
            try:
                minutes = int(vals.get("duration_minutes") or 0)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "Thời gian thực hiện (phút) phải là số nguyên."
                ) from exc
            if minutes < 0:
                raise ValidationError("Thời gian thực hiện (phút) không được âm.")
            write_vals["duration_minutes"] = minutes
        if "completion_percent" in vals and can_edit_content:
            try:
                pct = int(vals.get("completion_percent") or 0)
            except (TypeError, ValueError) as exc:
                raise ValidationError("% hoàn thành CV phải là số nguyên.") from exc
            if pct < 0 or pct > 100:
                raise ValidationError("% hoàn thành CV phải từ 0 đến 100.")
            write_vals["completion_percent"] = pct
            if pct >= 100 and vals.get("state") is None and not write_vals.get("state"):
                # Tự đánh dấu hoàn thành khi đạt 100%
                write_vals["state"] = "done"
        if write_vals:
            self.sudo().write(write_vals)
        return self._to_manager_dict()

    @api.onchange("assignee_id")
    def _onchange_assignee_id(self):
        if self.assignee_id and self.assignee_id.employee_id and self.assignee_id.employee_id.department_id:
            self.department_id = self.assignee_id.employee_id.department_id

    @api.model
    def action_open_hr_employee(self, hr_employee_id):
        hr_employee_id = int(hr_employee_id or 0)
        if not hr_employee_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": "Hồ sơ nhân viên",
            "res_model": "hr.employee",
            "res_id": hr_employee_id,
            "view_mode": "form",
            "target": "current",
        }
