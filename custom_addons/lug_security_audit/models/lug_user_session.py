# -*- coding: utf-8 -*-

import logging
import uuid
from datetime import date, timedelta

from odoo import api, fields, models, SUPERUSER_ID
from odoo.http import request

from .lug_hr_snapshot import job_title_label_from_employee
from .lug_request_utils import collect_request_meta, device_category_from_meta, is_usable_client_ip

_logger = logging.getLogger(__name__)

HEARTBEAT_OFFLINE_MINUTES = 2


class LugUserSession(models.Model):
    _name = "lug.user.session"
    _description = "Lug Security User Session"
    _order = "login_time desc, id desc"
    _rec_name = "session_uuid"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        ondelete="set null",
        index=True,
    )
    login_date = fields.Date(string="Ngày", index=True)
    login_time = fields.Datetime(string="Login", required=True, index=True)
    logout_time = fields.Datetime(string="Logout", index=True)
    duration_minutes = fields.Integer(string="Tổng phút")
    is_online = fields.Boolean(string="Online", default=True, index=True)
    last_seen = fields.Datetime(string="Last Seen", index=True)
    session_uuid = fields.Char(string="Session UUID", required=True, index=True)
    device_id = fields.Many2one(
        "lug.device",
        string="Thiết bị",
        ondelete="set null",
        index=True,
    )
    ip_address = fields.Char(string="IP")
    browser = fields.Char(string="Browser")
    os = fields.Char(string="OS")
    department_id = fields.Many2one("hr.department", string="Phòng ban", ondelete="set null")
    job_id = fields.Many2one("hr.job", string="Chức danh (job)", ondelete="set null")
    job_title_label = fields.Char(string="Chức danh", index=True)
    mien_label = fields.Char(string="Miền")
    store_label = fields.Char(string="Cửa hàng")
    status_label = fields.Char(
        string="Trạng thái",
        compute="_compute_status_label",
        search="_search_status_label",
    )
    duration_display = fields.Char(
        string="Tổng thời gian",
        compute="_compute_duration_display",
    )
    login_date_display = fields.Char(
        string="Ngày (hiển thị)",
        compute="_compute_datetime_displays",
    )
    login_time_display = fields.Char(
        string="Giờ login",
        compute="_compute_datetime_displays",
    )
    logout_time_display = fields.Char(
        string="Giờ logout",
        compute="_compute_datetime_displays",
    )
    device_category = fields.Char(
        string="Loại thiết bị",
        compute="_compute_device_category",
    )
    ip_display = fields.Char(
        string="IP (hiển thị)",
        compute="_compute_ip_display",
    )

    _session_uuid_uniq = models.Constraint(
        "UNIQUE(session_uuid)",
        "Session UUID phải là duy nhất.",
    )

    @api.depends("is_online")
    def _compute_status_label(self):
        for rec in self:
            rec.status_label = "Online" if rec.is_online else "Offline"

    def _search_status_label(self, operator, value):
        if operator != "=":
            return []
        online = (value or "").strip().lower() == "online"
        return [("is_online", "=", online)]

    @api.depends("duration_minutes", "is_online", "login_time")
    def _compute_duration_display(self):
        for rec in self:
            minutes = rec.duration_minutes or 0
            if rec.is_online and rec.login_time:
                minutes = max(
                    int((fields.Datetime.now() - rec.login_time).total_seconds() // 60),
                    0,
                )
            hours, mins = divmod(minutes, 60)
            rec.duration_display = f"{hours:02d}:{mins:02d}"

    @api.depends("login_date", "login_time", "logout_time")
    def _compute_datetime_displays(self):
        for rec in self:
            rec.login_date_display = (
                rec.login_date.strftime("%d/%m/%Y") if rec.login_date else ""
            )
            rec.login_time_display = rec._format_user_datetime(rec.login_time)
            rec.logout_time_display = rec._format_user_datetime(rec.logout_time)

    def _format_user_datetime(self, dt_value):
        if not dt_value:
            return ""
        local_dt = fields.Datetime.context_timestamp(self, dt_value)
        return local_dt.strftime("%H:%M %d/%m/%Y")

    @api.depends("device_id", "device_id.device_name", "browser", "os")
    def _compute_device_category(self):
        valid = {"PC", "Laptop", "Di động"}
        for rec in self:
            device_name = rec.device_id.device_name if rec.device_id else ""
            if device_name in valid:
                rec.device_category = device_name
            else:
                rec.device_category = device_category_from_meta({
                    "user_agent": rec.browser or "",
                    "platform": rec.os or "",
                })

    @api.depends("ip_address")
    def _compute_ip_display(self):
        for rec in self:
            ip = (rec.ip_address or "").strip()
            rec.ip_display = ip if is_usable_client_ip(ip) else ""

    # -------------------------------------------------------------------------
    # Request metadata helpers
    # -------------------------------------------------------------------------

    @api.model
    def _request_meta(self):
        """Collect browser / IP metadata from the current HTTP request."""
        if not request:
            return {}
        return collect_request_meta(request.httprequest.environ)

    @api.model
    def _employee_org_snapshot(self, user):
        """Snapshot HR org data via superuser — không kích hoạt LUG permission."""
        user = user.sudo()
        employee = self.env(user=SUPERUSER_ID)["hr.employee"].search(
            [
                ("user_id", "=", user.id),
                ("company_id", "in", user.company_ids.ids),
            ],
            limit=1,
        )
        if not employee:
            return {"employee_id": False}
        vals = {"employee_id": employee.id}
        if employee.department_id:
            vals["department_id"] = employee.department_id.id
        title = job_title_label_from_employee(employee)
        if title:
            vals["job_title_label"] = title
        if employee.job_id:
            vals["job_id"] = employee.job_id.id
        if "mien_zone_id" in employee._fields and employee.mien_zone_id:
            zone = employee.mien_zone_id
            legacy = getattr(zone, "legacy_mien", False) or zone.display_name
            vals["mien_label"] = legacy
        elif "mien" in employee._fields and employee.mien:
            vals["mien_label"] = employee.mien
        if "ma_bo_phan_id" in employee._fields and employee.ma_bo_phan_id:
            bp = employee.ma_bo_phan_id
            vals["store_label"] = getattr(bp, "code", False) or bp.display_name
        return vals

    @api.model
    def _session_uuid_from_request(self):
        if request and getattr(request, "session", None) and request.session.sid:
            return request.session.sid
        return str(uuid.uuid4())

    # -------------------------------------------------------------------------
    # Session lifecycle
    # -------------------------------------------------------------------------

    @api.model
    def _register_login(self, user_id):
        """Run as superuser so login audit never depends on user ACL."""
        return self.env(user=SUPERUSER_ID)["lug.user.session"]._register_login_impl(user_id)

    @api.model
    def _register_login_impl(self, user_id):
        user = self.env["res.users"].browse(user_id)
        if not user.exists():
            return self.env["lug.user.session"]
        meta = self._request_meta()
        device = self.env["lug.device"]._touch_from_request(user, meta)
        now = fields.Datetime.now()
        session_uuid = self._session_uuid_from_request()
        existing = self.search([("session_uuid", "=", session_uuid)], limit=1)
        if existing and existing.is_online:
            existing.write({"last_seen": now})
            self._close_other_online_sessions(user.id, session_uuid, now)
            return existing
        self._close_other_online_sessions(user.id, session_uuid, now)
        vals = {
            "user_id": user.id,
            "login_date": fields.Date.context_today(self),
            "login_time": now,
            "last_seen": now,
            "is_online": True,
            "session_uuid": session_uuid,
            "device_id": device.id,
            "ip_address": meta.get("ip_address") or False,
            "browser": meta.get("browser"),
            "os": meta.get("os"),
        }
        vals.update(self._employee_org_snapshot(user))
        return self.create(vals)

    @api.model
    def _close_other_online_sessions(self, user_id, keep_session_uuid, close_time=None):
        others = self.search([
            ("user_id", "=", user_id),
            ("is_online", "=", True),
            ("session_uuid", "!=", keep_session_uuid),
        ])
        for session in others:
            session._close_session(logout_time=close_time)

    @api.model
    def _close_by_session_uuid(self, session_uuid, logout_time=None):
        if not session_uuid:
            return
        rec = self.sudo().search(
            [("session_uuid", "=", session_uuid), ("is_online", "=", True)],
            limit=1,
        )
        if not rec:
            return
        rec._close_session(logout_time=logout_time)

    def _close_session(self, logout_time=None):
        self.ensure_one()
        if not self.is_online:
            return
        end = logout_time or fields.Datetime.now()
        start = self.login_time
        minutes = 0
        if start and end:
            minutes = max(int((end - start).total_seconds() // 60), 0)
        self.write({
            "logout_time": end,
            "duration_minutes": minutes,
            "is_online": False,
            "last_seen": end,
        })

    @api.model
    def _heartbeat(self, session_uuid=None):
        session_uuid = session_uuid or self._session_uuid_from_request()
        rec = self.sudo().search(
            [("session_uuid", "=", session_uuid), ("is_online", "=", True)],
            limit=1,
        )
        now = fields.Datetime.now()
        if rec:
            rec.write({"last_seen": now})
            return {"status": "ok", "session_id": rec.id}
        user = self.env.user
        if user and user._is_public():
            return {"status": "ignored"}
        return self._register_login(user.id)

    # -------------------------------------------------------------------------
    # Cron jobs
    # -------------------------------------------------------------------------

    @api.model
    def _cron_auto_offline(self):
        threshold = fields.Datetime.now() - timedelta(minutes=HEARTBEAT_OFFLINE_MINUTES)
        stale = self.sudo().search([
            ("is_online", "=", True),
            ("last_seen", "!=", False),
            ("last_seen", "<", threshold),
        ])
        for rec in stale:
            rec._close_session(logout_time=rec.last_seen)
        if stale:
            _logger.info("Lug Security: auto-offline %s session(s)", len(stale))

    @api.model
    def _session_duration_minutes(self, session):
        if session.duration_minutes:
            return session.duration_minutes
        if session.is_online and session.login_time:
            delta = fields.Datetime.now() - session.login_time
            return max(int(delta.total_seconds() // 60), 0)
        return 0

    @api.model
    def _build_daily_summary_for_date(self, day):
        Summary = self.env["lug.user.daily.summary"].sudo()
        sessions = self.sudo().search([("login_date", "=", day)])
        grouped = {}
        for session in sessions:
            key = session.user_id.id
            bucket = grouped.setdefault(key, {
                "user_id": key,
                "login_count": 0,
                "total_minutes": 0,
                "total_sessions": 0,
                "first_login": False,
                "last_logout": False,
                "department_id": session.department_id.id,
                "mien_label": session.mien_label,
                "job_title_label": session.job_title_label,
            })
            bucket["total_sessions"] += 1
            bucket["total_minutes"] += self._session_duration_minutes(session)
            if session.login_time and (
                not bucket["first_login"] or session.login_time < bucket["first_login"]
            ):
                bucket["first_login"] = session.login_time
            end_time = session.logout_time or (
                session.last_seen if session.is_online else False
            )
            if end_time and (
                not bucket["last_logout"] or end_time > bucket["last_logout"]
            ):
                bucket["last_logout"] = end_time
        for user_id, bucket in grouped.items():
            bucket["login_count"] = 1 if bucket["total_sessions"] else 0
            existing = Summary.search(
                [("summary_date", "=", day), ("user_id", "=", user_id)],
                limit=1,
            )
            vals = {
                "summary_date": day,
                "user_id": user_id,
                "login_count": bucket["login_count"],
                "total_minutes": bucket["total_minutes"],
                "total_sessions": bucket["total_sessions"],
                "first_login": bucket["first_login"],
                "last_logout": bucket["last_logout"],
                "department_id": bucket["department_id"],
                "mien_label": bucket["mien_label"],
                "job_title_label": bucket["job_title_label"],
            }
            if existing:
                existing.write(vals)
            else:
                Summary.create(vals)
        return len(grouped)

    @api.model
    def _cron_daily_summary(self, target_date=None):
        if target_date:
            day = (
                fields.Date.from_string(target_date)
                if isinstance(target_date, str)
                else target_date
            )
            count = self._build_daily_summary_for_date(day)
            _logger.info("Lug Security: daily summary for %s — %s user(s)", day, count)
            return
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        for day in (yesterday, today):
            count = self._build_daily_summary_for_date(day)
            _logger.info("Lug Security: daily summary for %s — %s user(s)", day, count)

    @api.model
    def action_open_daily_summary(self):
        """Rebuild today + yesterday then open the list."""
        today = fields.Date.context_today(self)
        self._build_daily_summary_for_date(today)
        self._build_daily_summary_for_date(today - timedelta(days=1))
        action = self.env.ref("lug_security_audit.action_lug_user_daily_summary").read()[0]
        action.setdefault("context", {})
        return action

    @api.model
    def action_backfill_job_titles(self):
        Employee = self.env(user=SUPERUSER_ID)["hr.employee"]
        for session in self.sudo().search([("employee_id", "!=", False)]):
            employee = Employee.browse(session.employee_id.id)
            title = job_title_label_from_employee(employee)
            if title and session.job_title_label != title:
                session.write({"job_title_label": title})

    @api.model
    def rebuild_month_summary(self, year, month):
        import calendar

        y, m = int(year), int(month)
        first_day = date(y, m, 1)
        last_day = date(y, m, calendar.monthrange(y, m)[1])
        sessions = self.sudo().search([
            ("login_date", ">=", first_day),
            ("login_date", "<=", last_day),
        ])
        for day in sorted(set(sessions.mapped("login_date"))):
            self._build_daily_summary_for_date(day)
        self._cron_monthly_summary(y, m)
        return True

    @api.model
    def _cron_monthly_summary(self, year=None, month=None):
        today = fields.Date.context_today(self)
        if year and month:
            y, m = int(year), int(month)
        else:
            first_this_month = today.replace(day=1)
            prev = first_this_month - timedelta(days=1)
            y, m = prev.year, prev.month
        domain = [
            ("summary_date", ">=", date(y, m, 1)),
        ]
        if m == 12:
            domain.append(("summary_date", "<", date(y + 1, 1, 1)))
        else:
            domain.append(("summary_date", "<", date(y, m + 1, 1)))
        daily_rows = self.env["lug.user.daily.summary"].sudo().search(domain)
        grouped = {}
        for row in daily_rows:
            key = row.user_id.id
            bucket = grouped.setdefault(key, {
                "total_login_days": 0,
                "total_minutes": 0,
                "total_sessions": 0,
                "device_ids": set(),
            })
            bucket["total_login_days"] += 1 if row.total_sessions else 0
            bucket["total_minutes"] += row.total_minutes or 0
            bucket["total_sessions"] += row.total_sessions or 0
        session_domain = [
            ("login_date", ">=", date(y, m, 1)),
        ]
        if m == 12:
            session_domain.append(("login_date", "<", date(y + 1, 1, 1)))
        else:
            session_domain.append(("login_date", "<", date(y, m + 1, 1)))
        for session in self.sudo().search(session_domain):
            if session.device_id:
                grouped.setdefault(session.user_id.id, {
                    "total_login_days": 0,
                    "total_minutes": 0,
                    "total_sessions": 0,
                    "device_ids": set(),
                })["device_ids"].add(session.device_id.id)
        MonthSummary = self.env["lug.user.month.summary"].sudo()
        for user_id, bucket in grouped.items():
            days = bucket["total_login_days"] or 1
            avg = int(bucket["total_minutes"] / days) if days else 0
            vals = {
                "year": y,
                "month": m,
                "user_id": user_id,
                "total_login_days": bucket["total_login_days"],
                "total_minutes": bucket["total_minutes"],
                "total_sessions": bucket["total_sessions"],
                "average_minutes": avg,
                "device_count": len(bucket.get("device_ids") or []),
            }
            existing = MonthSummary.search([
                ("year", "=", y),
                ("month", "=", m),
                ("user_id", "=", user_id),
            ], limit=1)
            if existing:
                existing.write(vals)
            else:
                MonthSummary.create(vals)
        _logger.info("Lug Security: monthly summary %02d/%s — %s user(s)", m, y, len(grouped))
