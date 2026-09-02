# -*- coding: utf-8 -*-

from calendar import monthrange
from datetime import datetime, timedelta, date, time

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from pytz import UTC, timezone as py_timezone


class LinkqRosterLockConfig(models.Model):
    _name = "linkq.roster.lock.config"
    _description = "Cài đặt khóa lịch ca"

    name = fields.Char(default="Cài đặt khóa lịch ca")
    auto_lock_enabled = fields.Boolean(string="Bật tự động khóa lịch", default=True)
    lock_day = fields.Integer(string="Ngày khóa", default=10)
    repeat_type = fields.Selection(
        [("weekly", "Hàng tuần"), ("monthly", "Hằng tháng")],
        default="monthly",
        required=True,
    )
    lock_time = fields.Char(string="Giờ khóa", default="22:00")
    notify_odoo = fields.Boolean(string="Thông báo hệ thống", default=True)
    notify_email = fields.Boolean(string="Thông báo email", default=True)
    notify_zalo = fields.Boolean(string="Thông báo Zalo", default=False)
    audit_log = fields.Boolean(string="Ghi log khi mở khóa", default=True)
    lock_before = fields.Selection(
        [
            ("1_day", "1 ngày"),
            ("2_day", "2 ngày"),
            ("3_day", "3 ngày"),
            ("day_10", "Ngày 10 cố định"),
        ],
        default="day_10",
        string="Khóa trước ngày bắt đầu",
        required=True,
    )
    lock_hour = fields.Float(string="Giờ khóa mặc định", default=17.0)
    apply_to_new = fields.Boolean(string="Tự động áp dụng cho lịch mới", default=True)
    allow_manager_unlock = fields.Boolean(string="Cho phép quản trị viên/quản lý mở khóa", default=True)
    notify_expiring = fields.Boolean(string="Gửi thông báo khi sắp khóa", default=True)
    notify_offset = fields.Selection(
        [
            ("1h", "1 giờ"),
            ("2h", "2 giờ trước khi khóa"),
            ("12h", "12 giờ trước khi khóa"),
            ("1d", "1 ngày"),
        ],
        default="2h",
        string="Thông báo trước khi khóa",
        required=True,
    )
    notify_employees = fields.Boolean(string="Nhân viên liên quan", default=True)
    notify_store_manager = fields.Boolean(string="Quản lý cửa hàng", default=True)
    notify_admin = fields.Boolean(string="Quản trị hệ thống", default=True)
    lock_anchor_date = fields.Date(string="Ngày khóa (mốc)")
    unlock_mode = fields.Selection(
        [("manual", "Mở khóa thủ công"), ("auto", "Mở khóa tự động")],
        default="manual",
        required=True,
    )
    unlock_date = fields.Date(string="Ngày mở khóa")
    unlock_time = fields.Char(string="Giờ mở khóa", default="08:00")
    unlock_repeat = fields.Selection(
        [("none", "Không lặp lại"), ("weekly", "Hằng tuần"), ("monthly", "Hằng tháng")],
        default="none",
        required=True,
    )

    @api.model
    def _get(self):
        rec = self.search([], limit=1)
        if not rec:
            rec = self.sudo().create({"name": "Cài đặt khóa lịch ca"})
        return rec

    def _lock_hm(self):
        self.ensure_one()
        raw = (self.lock_time or "").strip()
        if raw and ":" in raw:
            parts = raw.split(":")
            try:
                return min(int(parts[0]), 23), min(int(parts[1]), 59)
            except (TypeError, ValueError):
                pass
        hours = self.lock_hour or 22.0
        h = int(hours)
        m = int(round((hours - h) * 60))
        if m >= 60:
            h += 1
            m = 0
        return min(h, 23), min(m, 59)

    def _notify_delta(self):
        self.ensure_one()
        if self.notify_offset == "1h":
            return timedelta(hours=1)
        if self.notify_offset == "12h":
            return timedelta(hours=12)
        if self.notify_offset == "1d":
            return timedelta(days=1)
        return timedelta(hours=2)

    @api.model
    def _can_configure_lock(self):
        user = self.env.user
        return bool(
            user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_phan_he_lock_settings")
        )

    @api.model
    def action_save_settings(self, vals):
        if not self._can_configure_lock():
            raise AccessError("Bạn không có quyền cài đặt khóa lịch ca.")
        rec = self._get()
        mapped = dict(vals or {})
        if "auto_lock" in mapped:
            mapped["auto_lock_enabled"] = mapped.pop("auto_lock")
        if "lock_day_val" in mapped:
            mapped["lock_day"] = mapped.pop("lock_day_val")
        if "notify_before" in mapped:
            mapped["notify_offset"] = mapped.pop("notify_before")
        if mapped.get("lock_time"):
            parts = str(mapped["lock_time"]).split(":")
            try:
                mapped["lock_hour"] = int(parts[0]) + int(parts[1]) / 60.0
            except (TypeError, ValueError, IndexError):
                pass
        if "notify_odoo" in mapped:
            mapped["notify_expiring"] = bool(mapped["notify_odoo"])
        today = fields.Date.context_today(self)
        raw_day = mapped.get("lock_day", mapped.get("lock_day_val", rec.lock_day))
        try:
            lock_day = int(raw_day)
        except (TypeError, ValueError):
            lock_day = rec.lock_day or 10
        lock_day = min(max(lock_day, 1), 31)
        mapped["lock_day"] = lock_day
        last_lock = monthrange(today.year, today.month)[1]
        mapped["lock_anchor_date"] = date(today.year, today.month, min(lock_day, last_lock))
        raw_unlock = mapped.get("unlock_date")
        unlock_day = None
        if isinstance(raw_unlock, str) and len(raw_unlock) >= 10:
            try:
                unlock_day = int(raw_unlock[8:10])
            except (TypeError, ValueError):
                unlock_day = None
        if unlock_day:
            unlock_day = min(max(unlock_day, 1), 31)
            last_unlock = monthrange(today.year, today.month)[1]
            mapped["unlock_date"] = date(today.year, today.month, min(unlock_day, last_unlock))
        allowed = set(self._fields)
        rec.sudo().write({k: v for k, v in mapped.items() if k in allowed})
        rec.invalidate_recordset()
        Roster = self.env["linkq.monthly.roster"]
        try:
            with self.env.cr.savepoint():
                Roster.search([("is_locked", "=", False)])._sync_lock_datetime()
                Roster._cron_process_roster_locks()
        except Exception:
            pass
        return rec._as_dashboard_dict()

    def _parse_clock(self, raw, default_h=8, default_m=0):
        text = (raw or "").strip().upper().replace(" ", "")
        text = text.replace("AM", "").replace("PM", "")
        if text and ":" in text:
            parts = text.split(":")
            try:
                return min(int(parts[0]), 23), min(int(parts[1]), 59)
            except (TypeError, ValueError, IndexError):
                pass
        return default_h, default_m

    def _unlock_utc_naive(self, on_date=None):
        self.ensure_one()
        if (self.unlock_mode or "manual") != "auto":
            return False
        day = on_date or self.unlock_date
        if not day:
            return False
        hour, minute = self._parse_clock(self.unlock_time, 8, 0)
        tz = py_timezone("Asia/Ho_Chi_Minh")
        local = tz.localize(datetime.combine(day, time(hour, minute, 0)))
        return local.astimezone(UTC).replace(tzinfo=None)

    def _as_dashboard_dict(self):
        rec = self._get()
        return {
            "id": rec.id,
            "auto_lock": rec.auto_lock_enabled,
            "auto_lock_enabled": rec.auto_lock_enabled,
            "lock_day": rec.lock_day if rec.lock_day else 10,
            "lock_day_val": rec.lock_day if rec.lock_day else 10,
            "repeat_type": rec.repeat_type or "monthly",
            "lock_time": rec.lock_time or "22:00",
            "lock_hour": rec.lock_hour,
            "lock_before": rec.lock_before,
            "notify_before": rec.notify_offset or "2h",
            "notify_offset": rec.notify_offset,
            "notify_odoo": rec.notify_odoo,
            "notify_email": rec.notify_email,
            "notify_zalo": rec.notify_zalo,
            "notify_expiring": rec.notify_expiring,
            "notify_employees": rec.notify_employees,
            "notify_store_manager": rec.notify_store_manager,
            "notify_admin": rec.notify_admin,
            "allow_manager_unlock": rec.allow_manager_unlock,
            "audit_log": rec.audit_log,
            "apply_to_new": rec.apply_to_new,
            "lock_anchor_date": rec.lock_anchor_date.isoformat() if rec.lock_anchor_date else False,
            "unlock_mode": rec.unlock_mode or "manual",
            "unlock_date": rec.unlock_date.isoformat() if rec.unlock_date else False,
            "unlock_time": rec.unlock_time or "08:00",
            "unlock_repeat": rec.unlock_repeat or "none",
            "write_display": fields.Datetime.context_timestamp(rec, rec.write_date).strftime("%d/%m/%Y %H:%M")
            if rec.write_date
            else "",
            "write_user": rec.write_uid.name if rec.write_uid else "",
            "create_display": fields.Datetime.context_timestamp(rec, rec.create_date).strftime("%d/%m/%Y %H:%M")
            if rec.create_date
            else "",
            "create_user": rec.create_uid.name if rec.create_uid else "",
        }


class LinkqRosterLockEvent(models.Model):
    _name = "linkq.roster.lock.event"
    _description = "Thông báo khóa lịch ca"
    _order = "event_time desc, id desc"

    roster_id = fields.Many2one("linkq.monthly.roster", ondelete="cascade", index=True)
    event_type = fields.Selection(
        [
            ("expiring", "Sắp khóa"),
            ("locked", "Đã khóa"),
            ("ended", "Đã kết thúc"),
            ("reminder", "Nhắc nhở"),
            ("success", "Thành công"),
            ("unlocked", "Mở khóa"),
        ],
        required=True,
    )
    name = fields.Char(required=True)
    detail = fields.Char()
    event_time = fields.Datetime(default=fields.Datetime.now, required=True)

    def _as_dict(self):
        ui = {
            "expiring": ("Sắp khóa", "badge-warning-custom", "bg-warning-light text-warning", "fa fa-bell-o"),
            "reminder": ("Nhắc nhở", "badge-warning-custom", "bg-warning-light text-warning", "fa fa-bell-o"),
            "locked": ("Đã khóa", "badge-danger-custom", "bg-danger-light text-danger", "fa fa-lock"),
            "ended": ("Đã kết thúc", "badge-info-custom", "bg-info-light text-primary", "fa fa-clock-o"),
            "success": ("Thành công", "badge-success-custom", "bg-success-light text-success", "fa fa-check-circle-o"),
            "unlocked": ("Thành công", "badge-success-custom", "bg-success-light text-success", "fa fa-unlock"),
        }
        label, badge, icon_wrap, icon = ui.get(
            self.event_type,
            ("Thông báo", "badge-info-custom", "bg-info-light text-primary", "fa fa-info"),
        )
        return {
            "id": self.id,
            "type": self.event_type,
            "badge": label,
            "badgeClass": badge,
            "iconWrap": icon_wrap,
            "icon": icon,
            "title": self.name,
            "detail": self.detail or "",
            "time": fields.Datetime.context_timestamp(self, self.event_time).strftime("%d/%m/%Y %H:%M")
            if self.event_time
            else "",
        }

    @api.model
    def _cron_purge_lock_events(self):
        """Dọn log thông báo: 90 ngày (nhắc), 180 ngày (kết thúc), không xóa khóa/mở khóa."""
        now = datetime.utcnow()
        retention = {
            "expiring": 90,
            "reminder": 90,
            "success": 90,
            "ended": 180,
        }
        protected = ("locked", "unlocked")
        Event = self.sudo()
        for event_type, days in retention.items():
            cutoff = now - timedelta(days=days)
            Event.search(
                [
                    ("event_type", "=", event_type),
                    ("event_time", "<", cutoff),
                    ("event_type", "not in", list(protected)),
                ]
            ).unlink()



class LinkqMonthlyRosterLock(models.Model):
    _inherit = "linkq.monthly.roster"

    is_paused = fields.Boolean(string="Tạm dừng", default=False)
    is_locked = fields.Boolean(string="Đã khóa", default=False, tracking=True, copy=False)
    auto_lock = fields.Boolean(string="Tự động khóa", default=True, copy=False)
    lock_datetime = fields.Datetime(string="Thời điểm khóa", copy=False, index=True)
    expire_notified = fields.Boolean(copy=False)
    unlock_uid = fields.Many2one("res.users", string="Người mở khóa", copy=False)
    unlock_time = fields.Datetime(copy=False)
    unlock_reason = fields.Char(copy=False)
    period_start = fields.Date(compute="_compute_period_start", store=True)
    period_label = fields.Char(compute="_compute_period_label", store=True)
    lock_status = fields.Selection(
        [("unlocked", "Chưa khóa"), ("expiring", "Sắp khóa"), ("locked", "Đã khóa")],
        compute="_compute_lock_status",
        store=True,
    )
    apply_status = fields.Selection(
        [
            ("applying", "Đang áp dụng"),
            ("upcoming", "Sắp áp dụng"),
            ("paused", "Tạm dừng"),
            ("locked", "Đang bị khóa"),
        ],
        compute="_compute_apply_status",
        store=True,
    )
    lock_badge_text = fields.Char(compute="_compute_lock_status", store=True)
    period_edit_blocked = fields.Boolean(compute="_compute_period_edit_blocked")
    period_lock_notice = fields.Char(compute="_compute_period_lock_notice")

    @api.depends("year", "month")
    def _compute_period_start(self):
        for rec in self:
            y = rec.year or fields.Date.context_today(rec).year
            m = int(rec.month or 1)
            rec.period_start = date(y, m, 1)

    @api.depends("month", "year")
    def _compute_period_label(self):
        for rec in self:
            rec.period_label = f"Tháng {int(rec.month or 0)} / {rec.year or ''}"

    def _lock_tz(self):
        name = self.env.user.tz or self.env.company.partner_id.tz or "Asia/Ho_Chi_Minh"
        try:
            return py_timezone(name)
        except Exception:
            return py_timezone("Asia/Ho_Chi_Minh")

    def _local_to_utc_naive(self, local_dt):
        if local_dt.tzinfo is None:
            local_dt = self._lock_tz().localize(local_dt)
        return local_dt.astimezone(UTC).replace(tzinfo=None)

    def _lock_date_for_month(self, year, month, lock_before=None):
        config = self.env["linkq.roster.lock.config"]._get()
        last_n = monthrange(year, month)[1]
        day_n = min(max(int(config.lock_day or 10), 1), last_n)
        return date(year, month, day_n)

    @api.model
    def _period_lock_utc(self, year, month):
        config = self.env["linkq.roster.lock.config"]._get()
        year = int(year or fields.Date.context_today(self).year)
        month = int(month or 1)
        hour, minute = config._lock_hm()
        day = self._lock_date_for_month(year, month)
        return self._local_to_utc_naive(datetime.combine(day, time(hour, minute)))

    @api.model
    def _period_is_auto_locked(self, year, month):
        config = self.env["linkq.roster.lock.config"]._get()
        if not config.auto_lock_enabled:
            return False
        return fields.Datetime.now() >= self._period_lock_utc(year, month)

    @api.model
    def _in_auto_unlock_window(self, now=None):
        config = self.env["linkq.roster.lock.config"]._get()
        now = now or fields.Datetime.now()
        if (config.unlock_mode or "manual") != "auto" or not config.unlock_date:
            return False
        repeat = config.unlock_repeat or "none"
        if repeat == "monthly":
            local_now = fields.Datetime.context_timestamp(self, now)
            y, m = local_now.year, local_now.month
            last_n = monthrange(y, m)[1]
            day_n = min(max(config.unlock_date.day, 1), last_n)
            occ = config._unlock_utc_naive(date(y, m, day_n))
            if occ and now < occ:
                prev_m = 12 if m == 1 else m - 1
                prev_y = y - 1 if m == 1 else y
                prev_last = monthrange(prev_y, prev_m)[1]
                prev_day = min(max(config.unlock_date.day, 1), prev_last)
                occ = config._unlock_utc_naive(date(prev_y, prev_m, prev_day))
            if not occ or now < occ:
                return False
            nxt = self._next_lock_utc_after(occ)
            return not nxt or now < nxt
        unlock_utc = config._unlock_utc_naive()
        if not unlock_utc or now < unlock_utc:
            return False
        nxt = self._next_lock_utc_after(unlock_utc)
        return not nxt or now < nxt

    def _edit_blocked(self):
        self.ensure_one()
        if not self.auto_lock and not self.is_locked:
            return False
        if self._in_auto_unlock_window():
            return False
        if self.is_locked:
            return True
        if not self.auto_lock:
            return False
        return self._period_is_auto_locked(self.year, self.month)

    @api.depends("is_locked", "auto_lock", "year", "month")
    def _compute_period_edit_blocked(self):
        for rec in self:
            rec.period_edit_blocked = rec._edit_blocked()

    def _format_lock_local(self, utc_dt):
        if not utc_dt:
            return ""
        local = fields.Datetime.context_timestamp(self, utc_dt)
        return local.strftime("%d/%m/%Y %H:%M")

    def _next_lock_utc_after(self, after_dt):
        after_dt = after_dt or fields.Datetime.now()
        y = after_dt.year
        m = after_dt.month
        for _ in range(24):
            stamp = self._period_lock_utc(y, m)
            if stamp > after_dt:
                return stamp
            m += 1
            if m > 12:
                m = 1
                y += 1
        return False

    def _format_unlock_from_config(self, config):
        if (config.unlock_mode or "manual") != "auto" or not config.unlock_date:
            return ""
        raw = (config.unlock_time or "08:00").strip().upper().replace(" ", "")
        raw = raw.replace("AM", "").replace("PM", "")
        parts = raw.split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError, IndexError):
            hour, minute = 8, 0
        hm = f"{hour}h{minute:02d}"
        return f"ngày mở khóa: {config.unlock_date.strftime('%d/%m/%Y')} lúc {hm}"

    @api.depends("year", "month", "lock_datetime", "is_locked")
    def _compute_period_lock_notice(self):
        config = self.env["linkq.roster.lock.config"]._get()
        unlock_txt = self._format_unlock_from_config(config)
        for rec in self:
            base = (
                "Kỳ xếp ca này đã khóa theo thời gian cài đặt. "
                "Không thể thêm nhân viên, sửa lịch ca"
            )
            if unlock_txt:
                rec.period_lock_notice = f"{base}, {unlock_txt}."
            else:
                rec.period_lock_notice = (
                    f"{base}. Chọn tháng chưa khóa hoặc nhờ quản trị viên mở khóa."
                )

    def _sync_lock_datetime(self):
        config = self.env["linkq.roster.lock.config"]._get()
        now = fields.Datetime.now()
        for rec in self:
            if rec.is_locked or not rec.auto_lock or not config.auto_lock_enabled:
                continue
            y = rec.year or fields.Date.context_today(rec).year
            m = int(rec.month or 1)
            utc_dt = rec._period_lock_utc(y, m)
            vals = {"lock_datetime": utc_dt}
            if utc_dt <= now and not rec._in_auto_unlock_window(now):
                vals["is_locked"] = True
                vals["expire_notified"] = True
            rec.sudo().write(vals)

    @api.depends("is_locked", "lock_datetime")
    def _compute_lock_status(self):
        now = fields.Datetime.now()
        offset = self.env["linkq.roster.lock.config"]._get()._notify_delta()
        for rec in self:
            if rec.is_locked:
                rec.lock_status = "locked"
                stamp = rec.lock_datetime or rec.write_date
                local = fields.Datetime.context_timestamp(rec, stamp) if stamp else None
                rec.lock_badge_text = (
                    f"Đã khóa - Từ {local.strftime('%d/%m/%Y %H:%M')}" if local else "Đã khóa"
                )
            elif rec.lock_datetime and rec.lock_datetime > now and rec.lock_datetime - now <= offset:
                rec.lock_status = "expiring"
                rec.lock_badge_text = "Sắp khóa"
            elif rec.lock_datetime:
                rec.lock_status = "unlocked"
                rec.lock_badge_text = "Chưa khóa"
            else:
                rec.lock_status = "unlocked"
                rec.lock_badge_text = "Chưa khóa - Chưa đặt thời gian"

    @api.depends("is_paused", "is_locked", "lock_status", "year", "month", "state")
    def _compute_apply_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.is_paused:
                rec.apply_status = "paused"
            elif rec.is_locked or rec.lock_status == "locked":
                rec.apply_status = "locked"
            elif rec.year > today.year or (rec.year == today.year and int(rec.month or 1) > today.month):
                rec.apply_status = "upcoming"
            else:
                rec.apply_status = "applying"

    def action_open_schedule_popup(self):
        """Mở bảng xếp ca toàn màn hình (form current)."""
        self.ensure_one()
        view = self.env.ref("lug_phan_he.view_linkq_monthly_roster_form")
        return {
            "name": self.name or "Chi tiết bảng xếp ca",
            "type": "ir.actions.act_window",
            "res_model": "linkq.monthly.roster",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
            "context": {
                "form_view_initial_mode": "readonly",
            },
        }

    def action_edit_schedule(self):
        self.ensure_one()
        action = self.action_open_schedule_popup()
        action["context"] = {
            "form_view_initial_mode": "edit",
        }
        return action

    @api.model_create_multi
    def create(self, vals_list):
        config = self.env["linkq.roster.lock.config"]._get()
        today = fields.Date.context_today(self)
        for vals in vals_list:
            if "auto_lock" not in vals:
                vals["auto_lock"] = bool(config.apply_to_new and config.auto_lock_enabled)
            y = vals.get("year") or today.year
            m = int(vals.get("month") or today.month)
            if (
                vals.get("auto_lock")
                and self._period_is_auto_locked(y, m)
                and not self._in_auto_unlock_window()
            ):
                raise UserError(
                    f"Kỳ xếp ca Tháng {m}/{y} đã bị khóa theo cài đặt. "
                    "Không thể thêm lịch ca mới. Chọn tháng chưa khóa hoặc nhờ quản trị viên mở khóa."
                )
        recs = super().create(vals_list)
        recs._sync_lock_datetime()
        return recs

    def write(self, vals):
        blocked_keys = {
            "name",
            "store_id",
            "year",
            "month",
            "region",
            "line_ids",
            "state",
            "holiday_map",
            "is_paused",
        }
        if not self.env.su and (set(vals) & blocked_keys) and any(rec._edit_blocked() for rec in self):
            raise UserError("Bảng xếp ca đã bị khóa. Bạn không thể chỉnh sửa.")
        res = super().write(vals)
        if any(k in vals for k in ("year", "month", "auto_lock")):
            unlocked = self.filtered(lambda r: not r.is_locked)
            unlocked._sync_lock_datetime()
        return res

    @api.model
    def action_save_shift_grid(self, schedule_id, changes):
        roster = self.browse(schedule_id)
        if roster.exists() and roster._edit_blocked():
            return {"success": False, "message": "Bảng xếp ca đã bị khóa, không thể chỉnh sửa."}
        return super().action_save_shift_grid(schedule_id, changes)

    @api.model
    def _can_unlock(self):
        config = self.env["linkq.roster.lock.config"]._get()
        if not config.allow_manager_unlock:
            return False
        user = self.env.user
        return bool(
            user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_linkq_manager")
        )

    def action_unlock_roster(self, reason=""):
        self.ensure_one()
        if not self.is_locked:
            return True
        if not self._can_unlock():
            raise AccessError("Bạn không có quyền mở khóa lịch ca.")
        config = self.env["linkq.roster.lock.config"]._get()
        reason = (reason or "Quản lý mở khóa").strip()
        self.sudo().write(
            {
                "is_locked": False,
                "auto_lock": False,
                "expire_notified": False,
                "unlock_uid": self.env.user.id,
                "unlock_time": fields.Datetime.now(),
                "unlock_reason": reason,
            }
        )
        if config.audit_log:
            self.message_post(
                body=f"<p>Mở khóa lịch ca bởi <b>{self.env.user.name}</b>. Lý do: {reason}</p>"
            )
            self._log_lock_event(
                "unlocked",
                f"Đã mở khóa {self.name}",
                f"{self.env.user.name} · {reason}",
            )
        return True

    def action_lock_roster(self, reason=""):
        self.ensure_one()
        if self.is_locked:
            return True
        if not self._can_unlock():
            raise AccessError("Bạn không có quyền khóa lịch ca.")
        self.sudo().write({"is_locked": True, "expire_notified": True})
        self._log_lock_event(
            "locked",
            f"Đã khóa {self.name}",
            f"{self.env.user.name} · {(reason or 'Khóa thủ công').strip()}",
        )
        return True

    def action_duplicate_roster(self):
        self.ensure_one()
        new = models.Model.copy(
            self,
            {
                "name": "%s (sao chép)" % (self.name or "Bảng xếp ca"),
                "is_locked": False,
                "auto_lock": True,
                "state": "draft",
                "lock_datetime": False,
                "expire_notified": False,
            },
        )
        return new.id

    def _log_lock_event(self, event_type, title, detail=""):
        self.ensure_one()
        self.env["linkq.roster.lock.event"].sudo().create(
            {
                "roster_id": self.id,
                "event_type": event_type,
                "name": title,
                "detail": detail,
                "event_time": fields.Datetime.now(),
            }
        )

    def _notify_lock_partners(self, title, body):
        config = self.env["linkq.roster.lock.config"]._get()
        partner_ids = set()
        if config.notify_employees:
            for line in self.line_ids:
                emp = line.employee_id
                if emp and emp.user_id and emp.user_id.partner_id:
                    partner_ids.add(emp.user_id.partner_id.id)
        if config.notify_store_manager and self.store_id:
            manager = getattr(self.store_id, "manager_id", False)
            if manager and getattr(manager, "user_id", False) and manager.user_id.partner_id:
                partner_ids.add(manager.user_id.partner_id.id)
        if config.notify_admin:
            group = self.env.ref("lug_phan_he.group_phan_he_admin", raise_if_not_found=False)
            if group:
                partner_ids.update(group.sudo().all_user_ids.mapped("partner_id").ids)
        if partner_ids:
            try:
                self.message_notify(
                    partner_ids=list(partner_ids),
                    subject=title,
                    body=body,
                )
            except Exception:
                pass
        self.message_post(body=f"<p>{body}</p>")

    @api.model
    def _cron_process_roster_locks(self):
        config = self.env["linkq.roster.lock.config"]._get()
        now = fields.Datetime.now()
        if not config.auto_lock_enabled:
            self.search([])._compute_lock_status()
            return True
        offset = config._notify_delta()
        domain = [("auto_lock", "=", True), ("is_locked", "=", False), ("lock_datetime", "!=", False)]
        records = self.search(domain)
        if not records:
            records = self.search([("is_locked", "=", False)])
            records._sync_lock_datetime()
            records = self.search(domain)
        unlocking = self._in_auto_unlock_window(now)
        if unlocking:
            for rec in self.search([("is_locked", "=", True)]):
                rec.sudo().write({"is_locked": False, "expire_notified": False})
                rec._log_lock_event(
                    "unlocked",
                    f"Đã mở khóa {rec.name}",
                    "Mở khóa tự động theo cài đặt",
                )
        for rec in records:
            if rec.lock_datetime <= now:
                if unlocking:
                    continue
                rec.sudo().write({"is_locked": True, "expire_notified": True})
                rec._log_lock_event("locked", f"Đã khóa {rec.name}", rec.lock_badge_text)
                try:
                    rec._notify_lock_partners(
                        f"Đã khóa lịch ca: {rec.name}",
                        f"Lịch ca {rec.name} đã bị khóa tự động. Nhân viên không thể chỉnh sửa.",
                    )
                except Exception:
                    rec.message_post(body="<p>Đã khóa tự động (không gửi được thông báo).</p>")
            elif config.notify_expiring and not rec.expire_notified and rec.lock_datetime - now <= offset:
                rec.sudo().write({"expire_notified": True})
                rec._log_lock_event("expiring", f"Sắp khóa {rec.name}", rec.lock_badge_text)
                try:
                    rec._notify_lock_partners(
                        f"Sắp khóa lịch ca: {rec.name}",
                        f"Lịch ca {rec.name} sẽ bị khóa lúc {rec.lock_datetime}.",
                    )
                except Exception:
                    pass
        self.search([])._compute_lock_status()
        self.search([])._compute_apply_status()
        return True

    @api.model
    def get_lock_dashboard(self):
        config = self.env["linkq.roster.lock.config"]._get()
        self.sudo()._cron_process_roster_locks()
        rosters = self.search([])
        events = self.env["linkq.roster.lock.event"].search([], limit=12)
        return {
            "kpis": {
                "total": len(rosters),
                "applying": len(rosters.filtered(lambda r: r.apply_status == "applying")),
                "upcoming": len(rosters.filtered(lambda r: r.apply_status == "upcoming")),
                "paused": len(rosters.filtered(lambda r: r.apply_status == "paused")),
                "locked": len(rosters.filtered(lambda r: r.apply_status == "locked")),
            },
            "config": config._as_dashboard_dict(),
            "events": [ev._as_dict() for ev in events],
            "can_manage": self._can_unlock(),
            "can_configure": self.env["linkq.roster.lock.config"]._can_configure_lock(),
        }

    def _lack_summary(self):
        self.ensure_one()
        n = self.days_in_month or 0
        morning = self.lack_morning or []
        evening = self.lack_evening or []
        slots = 0
        first_day = 0
        limit = min(n, len(morning), len(evening))
        for i in range(limit):
            miss_m = bool(morning[i])
            miss_e = bool(evening[i])
            if miss_m or miss_e:
                slots += int(miss_m) + int(miss_e)
                if not first_day:
                    first_day = i + 1
        return slots, first_day

    def _shift_filled_count(self):
        self.ensure_one()
        n_days = self.days_in_month or 0
        total = 0
        for line in self.line_ids:
            actual = line.actual_codes or {}
            plan = line.plan_codes or {}
            for day in range(1, n_days + 1):
                code = actual.get(str(day)) or actual.get(day) or plan.get(str(day)) or plan.get(day)
                if code and str(code).upper() not in ("OFF", "LE", "LỄ", ""):
                    total += 1
        return total

    def _store_notif_type(self, now, has_lack, staff):
        self.ensure_one()
        lock_dt = self.lock_datetime
        if has_lack:
            return "need"
        if self.is_locked or self.lock_status == "locked":
            return "locked"
        if lock_dt and lock_dt > now:
            return "expiring"
        if not staff:
            return "reminder"
        return "info"

    def _make_store_notif_card(self, ntype, now):
        self.ensure_one()
        slots, first_day = self._lack_summary()
        staff = self.line_count or len(self.line_ids)
        month_n = int(self.month or 1)
        days = self.days_in_month or 31
        lock_dt = self.lock_datetime
        lock_txt = ""
        lock_full = ""
        if lock_dt:
            local = fields.Datetime.context_timestamp(self, lock_dt)
            lock_txt = local.strftime("%d/%m/%Y %H:%M")
            lock_full = local.strftime("%d/%m/%Y lúc %H:%M")
        first_date = ""
        shift_span = "14:00 – 18:00"
        morning = self.lack_morning or []
        evening = self.lack_evening or []
        if first_day:
            first_date = f"{first_day:02d}/{month_n:02d}/{self.year or ''}"
            idx = first_day - 1
            miss_m = idx < len(morning) and morning[idx]
            miss_e = idx < len(evening) and evening[idx]
            if miss_m and not miss_e:
                shift_span = "08:00 – 14:00"
            elif miss_e and not miss_m:
                shift_span = "14:00 – 22:00"
        store = self.store_id.name or ""
        period = f"{month_n:02d}/{self.year}"
        return {
            "key": f"{self.id}-{ntype}",
            "id": self.id,
            "type": ntype,
            "store_name": store,
            "store_line": f"Cửa hàng {store} • Lịch tháng {period}",
            "period": f"Tháng {period}",
            "period_long": f"Tháng {month_n} năm {self.year} (ngày 01–{days:02d})",
            "lock_txt": lock_txt,
            "lock_full": lock_full,
            "lock_at": fields.Datetime.to_string(lock_dt) if lock_dt else "",
            "staff": staff,
            "shift_count": self._shift_filled_count(),
            "missing_slots": slots,
            "need_n": staff + slots,
            "first_date": first_date,
            "shift_span": shift_span,
        }

    @api.model
    def get_store_notification_cards(self, kind="all"):
        return self.env["linkq.store.notification"].get_store_notification_cards(kind)

    def action_request_unlock(self):
        self.ensure_one()
        self.message_post(
            body=(
                f"<p>Cửa hàng <b>{self.store_id.name or ''}</b> yêu cầu mở khóa "
                f"bảng ca <b>{self.name}</b>.</p>"
            )
        )
        if self._can_unlock() and self.is_locked:
            self.action_unlock_roster("Yêu cầu mở khóa từ cửa hàng")
            return {"unlocked": True}
        self._log_lock_event(
            "reminder",
            f"Yêu cầu mở khóa {self.name}",
            self.env.user.name,
        )
        return {"requested": True}


class LinkqMonthlyRosterLineLock(models.Model):
    _inherit = "linkq.monthly.roster.line"

    def write(self, vals):
        blocked_keys = {
            "employee_id",
            "employee_name",
            "job_title",
            "employee_code",
            "plan_codes",
            "actual_codes",
            "plan_notes",
            "actual_notes",
            "sequence",
        }
        if (
            not self.env.su
            and (set(vals) & blocked_keys)
            and any(line.roster_id and line.roster_id._edit_blocked() for line in self)
        ):
            raise UserError("Bảng xếp ca đã bị khóa. Không thể sửa ca hoặc ghi chú.")
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        Roster = self.env["linkq.monthly.roster"]
        for vals in vals_list:
            rid = vals.get("roster_id")
            if rid and not self.env.su:
                roster = Roster.browse(rid)
                if roster.exists() and roster._edit_blocked():
                    raise UserError("Bảng xếp ca đã bị khóa. Không thể thêm nhân viên.")
        return super().create(vals_list)

    def unlink(self):
        if not self.env.su and any(line.roster_id and line.roster_id._edit_blocked() for line in self):
            raise UserError("Bảng xếp ca đã bị khóa. Không thể xóa dòng ca.")
        return super().unlink()
