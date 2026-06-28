# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import date

from odoo import api, fields, models, SUPERUSER_ID

from .lug_hr_snapshot import job_title_label_from_employee

MIEN_COLORS = {
    "company": ("#22c55e", "#94a3b8"),
    "Tất cả": ("#0d6efd", "#bfdbfe"),
    "Văn phòng": ("#8b5cf6", "#ddd6fe"),
    "VP": ("#8b5cf6", "#ddd6fe"),
    "Miền Nam": ("#2563eb", "#bfdbfe"),
    "Miền Bắc": ("#dc2626", "#fecaca"),
    "Miền ĐTT": ("#14b8a6", "#99f6e4"),
    "ĐTT": ("#14b8a6", "#99f6e4"),
    "Khác": ("#f59e0b", "#fde68a"),
}

MIEN_ORDER = ["Văn phòng", "Miền Nam", "Miền Bắc", "Miền ĐTT", "Khác"]

DASHBOARD_HIDDEN_STORES = frozenset(("LUG_KDV", "LUG_THD"))
MIEN_SKIP_VALUES = frozenset({"Tất cả"})
TIER2_MAIN_MIENS = ("Miền Nam", "Miền ĐTT", "Miền Bắc")
TIER2_RESERVED_MIENS = frozenset((*TIER2_MAIN_MIENS, "Văn phòng", "Khác", "Tất cả"))

MIEN_ALIASES = {
    "VP": "Văn phòng",
    "Văn phòng": "Văn phòng",
    "Miền Nam": "Miền Nam",
    "Nam": "Miền Nam",
    "MIỀN NAM": "Miền Nam",
    "Miền Bắc": "Miền Bắc",
    "Bắc": "Miền Bắc",
    "MIỀN BẮC": "Miền Bắc",
    "Miền ĐTT": "Miền ĐTT",
    "ĐTT": "Miền ĐTT",
    "DONG THAP": "Miền ĐTT",
}


class LugSecurityDashboard(models.TransientModel):
    _name = "lug.security.dashboard"
    _description = "Lug Security Dashboard"

    @api.model
    def _parse_filters(self, filters):
        filters = filters or {}
        today = fields.Date.context_today(self)
        year = int(filters.get("year") or today.year)
        month = int(filters.get("month") or today.month)
        day = int(filters.get("day") or today.day)
        try:
            summary_date = date(year, month, day)
        except ValueError:
            summary_date = today
        search_text = (filters.get("search") or "").strip()
        return {
            "year": year,
            "month": month,
            "day": day,
            "summary_date": summary_date,
            "search": search_text,
            "selected_mien": (filters.get("selected_mien") or "").strip(),
        }

    @api.model
    def _parse_month_filters(self, filters):
        filters = filters or {}
        today = fields.Date.context_today(self)
        year = int(filters.get("year") or today.year)
        month = int(filters.get("month") or today.month)
        month = min(max(month, 1), 12)
        return {
            "year": year,
            "month": month,
            "search": (filters.get("search") or "").strip(),
        }

    @api.model
    def _session_domain(self, filters):
        return [("login_date", "=", filters["summary_date"])]

    @api.model
    def _normalize_mien(self, label):
        raw = (label or "").strip()
        if not raw:
            return "Khác"
        return MIEN_ALIASES.get(raw, MIEN_ALIASES.get(raw.title(), raw))

    @api.model
    def _employee_mien_label(self, employee):
        if not employee:
            return "Khác"
        candidates = []
        if "mien_zone_id" in employee._fields and employee.mien_zone_id:
            zone = employee.mien_zone_id
            legacy = (getattr(zone, "legacy_mien", False) or zone.display_name or "").strip()
            if legacy and legacy not in MIEN_SKIP_VALUES:
                candidates.append(legacy)
        if "mien" in employee._fields and employee.mien:
            mien_code = (employee.mien or "").strip()
            if mien_code and mien_code not in MIEN_SKIP_VALUES:
                candidates.append(mien_code)
        if "ma_bo_phan_id" in employee._fields and employee.ma_bo_phan_id:
            bp = employee.ma_bo_phan_id
            if "mien" in bp._fields and bp.mien:
                bp_mien = (bp.mien or "").strip()
                if bp_mien and bp_mien not in MIEN_SKIP_VALUES:
                    candidates.append(bp_mien)
        if (
            "employee_visibility" in employee._fields
            and employee.employee_visibility == "office"
        ):
            candidates.append("VP")
        for raw in candidates:
            label = self._normalize_mien(raw)
            if label and label not in MIEN_SKIP_VALUES:
                return label
        return "Khác"

    @api.model
    def _employee_store_label(self, employee):
        if not employee:
            return "Khác"
        if "ma_bo_phan_id" in employee._fields and employee.ma_bo_phan_id:
            bp = employee.ma_bo_phan_id
            return (getattr(bp, "code", False) or bp.display_name or "Khác").strip()
        if employee.department_id:
            return employee.department_id.name
        return "Khác"

    @api.model
    def _employee_user_maps(self, limit_user_ids=None):
        Employee = self.env(user=SUPERUSER_ID)["hr.employee"]
        employees = Employee.search([("user_id", "!=", False)])
        mien_users = defaultdict(set)
        store_users = defaultdict(set)
        mien_store_users = defaultdict(lambda: defaultdict(set))
        for employee in employees:
            uid = employee.user_id.id
            if limit_user_ids is not None and uid not in limit_user_ids:
                continue
            mien = self._employee_mien_label(employee)
            store = self._employee_store_label(employee)
            mien_users[mien].add(uid)
            store_users[store].add(uid)
            mien_store_users[mien][store].add(uid)
        return mien_users, store_users, mien_store_users

    @api.model
    def _field_supports_ilike(self, model, field_expr):
        parts = field_expr.split(".")
        current = model
        for index, part in enumerate(parts):
            field = current._fields.get(part)
            if not field:
                return False
            if index == len(parts) - 1:
                if getattr(field, "translate", False):
                    return False
                return field.type in ("char", "text", "selection")
            if field.type == "many2one" and field.comodel_name:
                current = self.env[field.comodel_name]
                continue
            return False
        return False

    @api.model
    def _employee_search_fields(self):
        Employee = self.env(user=SUPERUSER_ID)["hr.employee"]
        candidates = [
            "name",
            "user_id.login",
            "user_id.name",
            "job_title",
            "id_hrm",
            "ten_khong_dau",
            "ma_bo_phan",
            "ten_bo_phan",
            "ma_nv_ke_toan",
            "ma_cham_cong",
            "work_email",
            "mobile_phone",
            "mien",
            "ma_bo_phan_id.code",
            "mien_zone_id.legacy_mien",
        ]
        return [
            field_expr
            for field_expr in candidates
            if self._field_supports_ilike(Employee, field_expr)
        ]

    @api.model
    def _or_ilike_domain(self, needle, field_exprs):
        domain = []
        for index, field_expr in enumerate(field_exprs):
            if index:
                domain.insert(0, "|")
            domain.append((field_expr, "ilike", needle))
        return domain

    @api.model
    def _search_employee_user_ids(self, search_text):
        needle = (search_text or "").strip()
        if not needle:
            return None
        Employee = self.env(user=SUPERUSER_ID)["hr.employee"]
        field_exprs = self._employee_search_fields()
        if not field_exprs:
            return set()
        domain = [("user_id", "!=", False)]
        domain += self._or_ilike_domain(needle, field_exprs)
        return set(Employee.search(domain).mapped("user_id.id"))

    @api.model
    def _sessions_for_users(self, sessions, user_ids):
        if user_ids is None:
            return sessions
        if not user_ids:
            return sessions.browse()
        return sessions.filtered(lambda session: session.user_id.id in user_ids)

    @api.model
    def _online_user_ids(self):
        Session = self.env["lug.user.session"].sudo()
        return set(Session.search([("is_online", "=", True)]).mapped("user_id.id"))

    @api.model
    def _session_duration_minutes(self, session):
        if session.duration_minutes:
            return session.duration_minutes
        if session.is_online and session.login_time:
            delta = fields.Datetime.now() - session.login_time
            return max(int(delta.total_seconds() // 60), 0)
        return 0

    @api.model
    def _format_hours(self, minutes):
        hours = (minutes or 0) / 60.0
        if hours >= 1000:
            return f"{hours:,.0f}h".replace(",", ".")
        if hours == int(hours):
            return f"{int(hours)}h"
        return f"{hours:.1f}h"

    @api.model
    def _build_donut_chart(self, key, title, online, offline, subtitle=None, extra_lines=None):
        total = online + offline
        colors = MIEN_COLORS.get(key, MIEN_COLORS["Khác"])
        footer_lines = [
            f"User: {total}",
            f"Online: {online}",
            f"Offline: {offline}",
        ]
        if extra_lines:
            footer_lines.extend(extra_lines)
        return {
            "key": key,
            "title": title,
            "subtitle": subtitle or "",
            "labels": ["Online", "Offline"],
            "values": [online, max(offline, 0)],
            "colors": list(colors),
            "total": total,
            "center_text": str(total),
            "footer_lines": footer_lines,
        }

    @api.model
    def _mien_chart(self, mien, mien_users, online_ids):
        user_ids = mien_users.get(mien, set())
        online = len(user_ids & online_ids)
        offline = len(user_ids) - online
        return self._build_donut_chart(mien, mien, online, offline)

    @api.model
    def _mien_chart_if_any(self, mien, mien_users, online_ids):
        if not mien_users.get(mien):
            return None
        return self._mien_chart(mien, mien_users, online_ids)

    @api.model
    def _charts_by_mien(self, mien_users, online_ids):
        charts_by_mien = {}
        for mien in MIEN_ORDER:
            chart = self._mien_chart_if_any(mien, mien_users, online_ids)
            if chart:
                charts_by_mien[mien] = chart
        for mien, user_ids in sorted(mien_users.items()):
            if mien in charts_by_mien or not user_ids or mien in TIER2_RESERVED_MIENS:
                continue
            online = len(user_ids & online_ids)
            offline = len(user_ids) - online
            charts_by_mien[mien] = self._build_donut_chart(mien, mien, online, offline)
        return charts_by_mien

    @api.model
    def _build_tier1_donuts(self, mien_users, online_ids, total_minutes):
        charts_by_mien = self._charts_by_mien(mien_users, online_ids)
        all_ids = set().union(*mien_users.values()) if mien_users else set()
        online_all = len(all_ids & online_ids)
        offline_all = len(all_ids) - online_all
        tat_ca = self._build_donut_chart(
            "Tất cả",
            "Tất cả",
            online_all,
            offline_all,
            extra_lines=[f"Tổng giờ hôm nay: {self._format_hours(total_minutes)}"],
        )
        charts = [tat_ca]
        if charts_by_mien.get("Văn phòng"):
            charts.append(charts_by_mien["Văn phòng"])
        return charts

    @api.model
    def _chart_row(self, charts, row_class=""):
        return {"charts": charts, "row_class": row_class}

    @api.model
    def _build_tier2_donuts(self, mien_users, online_ids):
        charts_by_mien = self._charts_by_mien(mien_users, online_ids)
        region_row = [
            self._mien_chart(mien, mien_users, online_ids)
            for mien in TIER2_MAIN_MIENS
        ]
        if charts_by_mien.get("Khác"):
            region_row.append(charts_by_mien["Khác"])
        for mien, chart in sorted(charts_by_mien.items()):
            if mien in TIER2_RESERVED_MIENS:
                continue
            region_row.append(chart)
        chart_rows = [self._chart_row(region_row, "o_lug_donut_row_tier2_bottom")]
        return {"charts": region_row, "chart_rows": chart_rows}

    @api.model
    def _build_store_donuts(self, mien_store_users, online_ids, selected_mien=None, limit=6):
        charts = []
        targets = []
        if selected_mien and selected_mien in mien_store_users:
            targets = sorted(
                mien_store_users[selected_mien].items(),
                key=lambda item: len(item[1]),
                reverse=True,
            )[:limit]
        else:
            all_stores = defaultdict(set)
            for stores in mien_store_users.values():
                for store, user_ids in stores.items():
                    all_stores[store] |= user_ids
            targets = sorted(all_stores.items(), key=lambda item: len(item[1]), reverse=True)[:limit]
        for store, user_ids in targets:
            if not user_ids or store == "Khác":
                continue
            if (store or "").upper() in {code.upper() for code in DASHBOARD_HIDDEN_STORES}:
                continue
            online = len(user_ids & online_ids)
            offline = len(user_ids) - online
            charts.append(self._build_donut_chart(
                f"store_{store}",
                store,
                online,
                offline,
                subtitle=selected_mien or "Cửa hàng / BP",
            ))
        return charts

    @api.model
    def _build_hourly_chart(self, sessions):
        buckets = defaultdict(int)
        for session in sessions:
            if not session.login_time:
                continue
            local_dt = fields.Datetime.context_timestamp(session, session.login_time)
            hour = local_dt.hour
            buckets[hour] += 1
        hours = sorted(buckets.keys())
        return {
            "title": "User Online theo thời gian",
            "labels": [f"{hour:02d}h" for hour in hours],
            "values": [buckets[hour] for hour in hours],
        }

    @api.model
    def _session_row(self, session):
        return {
            "id": session.id,
            "login_date_display": (
                session.login_date.strftime("%d/%m/%Y") if session.login_date else ""
            ),
            "mien_label": session.mien_label or "",
            "user_login": session.user_id.login or "",
            "user_name": session.user_id.name or "",
            "user_id": session.user_id.id,
            "department_name": session.department_id.name or "",
            "job_title_label": session.job_title_label or "",
            "login_time_display": session.login_time_display or "",
            "logout_time_display": session.logout_time_display or "",
            "duration_display": session.duration_display or "",
            "device_category": session.device_category or "",
            "ip_display": session.ip_display or "",
            "status_label": session.status_label or "",
            "is_online": session.is_online,
        }

    @api.model
    def _filter_rows(self, rows, search_text, search_user_ids=None):
        if search_user_ids is not None:
            return [
                row for row in rows
                if row.get("user_id") in search_user_ids
            ]
        if not search_text:
            return rows
        needle = search_text.casefold()
        return [
            row for row in rows
            if needle in (row.get("user_login") or "").casefold()
            or needle in (row.get("user_name") or "").casefold()
            or needle in (row.get("department_name") or "").casefold()
            or needle in (row.get("job_title_label") or "").casefold()
            or needle in (row.get("mien_label") or "").casefold()
        ]

    @api.model
    def _dedupe_online_rows(self, sessions):
        rows = []
        seen_users = set()
        for session in sessions:
            user_id = session.user_id.id
            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            rows.append(self._session_row(session))
        return rows

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = self._parse_filters(filters)
        Session = self.env["lug.user.session"].sudo()
        base_domain = self._session_domain(filters)

        day_sessions = Session.search(base_domain, order="login_time desc, id desc")

        online_ids = self._online_user_ids()
        Users = self.env["res.users"].sudo()
        total_internal = Users.search_count([("share", "=", False), ("active", "=", True)])
        online_count = len(online_ids)
        offline_count = max(total_internal - online_count, 0)

        total_minutes = sum(self._session_duration_minutes(s) for s in day_sessions)
        mien_users, _store_users, mien_store_users = self._employee_user_maps()

        tier1_donuts = self._build_tier1_donuts(mien_users, online_ids, total_minutes)
        tier2_donuts = self._build_tier2_donuts(mien_users, online_ids)
        store_donuts = self._build_store_donuts(
            mien_store_users,
            online_ids,
            selected_mien=filters.get("selected_mien"),
        )
        hourly_chart = self._build_hourly_chart(day_sessions)
        rows = self.get_online_table_rows(filters)

        today = fields.Date.context_today(self)
        return {
            "kpi": {
                "online": online_count,
                "offline": offline_count,
                "total": total_internal,
                "total_hours": self._format_hours(total_minutes),
            },
            "donut_sections": [
                {
                    "key": "tier1",
                    "title": "Tầng 1: KPI tổng quan toàn công ty",
                    "charts": tier1_donuts,
                    "chart_rows": [self._chart_row(tier1_donuts, "o_lug_donut_row_tier1")],
                },
                {
                    "key": "tier2",
                    "title": "Tầng 2: Theo Miền",
                    "charts": tier2_donuts["charts"],
                    "chart_rows": tier2_donuts["chart_rows"],
                },
                {
                    "key": "tier3",
                    "title": "Tầng 3: Theo Phòng ban / Cửa hàng",
                    "charts": store_donuts,
                },
            ],
            "hourly_chart": hourly_chart,
            "rows": rows,
            "filters": {
                "year": filters["year"],
                "month": filters["month"],
                "day": filters["day"],
                "search": filters["search"],
                "selected_mien": filters.get("selected_mien") or "",
            },
            "filter_options": {
                **self._filter_options_payload(),
                "miens": [{"value": m, "label": m} for m in MIEN_ORDER if mien_users.get(m)],
            },
        }

    @api.model
    def _filter_options_payload(self):
        today = fields.Date.context_today(self)
        return {
            "years": list(range(today.year - 2, today.year + 2)),
            "months": [
                {"value": m, "label": f"Tháng {m:02d}"}
                for m in range(1, 13)
            ],
            "days": list(range(1, 32)),
        }

    @api.model
    def _get_session_table_rows(self, filters):
        Session = self.env["lug.user.session"].sudo()
        base_domain = self._session_domain(filters)
        sessions = Session.search(base_domain, order="login_time desc, id desc")
        search_user_ids = self._search_employee_user_ids(filters["search"])
        sessions = self._sessions_for_users(sessions, search_user_ids)
        rows = [self._session_row(session) for session in sessions]
        return self._filter_rows(rows, filters["search"], search_user_ids)

    @api.model
    def get_session_list_data(self, filters=None):
        filters = self._parse_filters(filters)
        rows = self._get_session_table_rows(filters)
        return {
            "rows": rows,
            "total": len(rows),
            "filters": {
                "year": filters["year"],
                "month": filters["month"],
                "day": filters["day"],
                "search": filters["search"],
            },
            "filter_options": self._filter_options_payload(),
        }

    @api.model
    def _month_summary_row(self, record):
        employee = record.employee_id
        if employee:
            employee = self.env(user=SUPERUSER_ID)["hr.employee"].browse(employee.id)
        job_title = job_title_label_from_employee(employee)
        if not job_title and record.job_id:
            job_title = record.job_id.name
        return {
            "id": record.id,
            "month_label": record.month_label or "",
            "user_login": record.user_id.login or "",
            "user_name": record.employee_name or record.user_id.name or "",
            "user_id": record.user_id.id,
            "job_title_label": job_title or "",
            "department_name": record.department_id.name or "",
            "mien_label": record.mien_label or "",
            "total_login_days": record.total_login_days or 0,
            "total_hours_display": record.total_hours_display or "0h",
            "average_hours_display": record.average_hours_display or "0h",
            "total_sessions": record.total_sessions or 0,
            "device_count": record.device_count or 0,
        }

    @api.model
    def get_month_report_data(self, filters=None):
        parsed = self._parse_month_filters(filters)
        self.env["lug.user.session"].sudo().rebuild_month_summary(
            parsed["year"],
            parsed["month"],
        )
        MonthSummary = self.env["lug.user.month.summary"].sudo()
        records = MonthSummary.search([
            ("year", "=", parsed["year"]),
            ("month", "=", parsed["month"]),
        ], order="employee_name, user_id")
        search_user_ids = self._search_employee_user_ids(parsed["search"])
        rows = []
        for record in records:
            if search_user_ids is not None and record.user_id.id not in search_user_ids:
                continue
            rows.append(self._month_summary_row(record))
        return {
            "rows": rows,
            "total": len(rows),
            "filters": parsed,
            "filter_options": self._filter_options_payload(),
        }

    @api.model
    def action_export_month_report(self, filters=None):
        parsed = self._parse_month_filters(filters)
        action = self.env.ref("lug_security_audit.action_lug_user_month_summary").read()[0]
        domain = [
            ("year", "=", parsed["year"]),
            ("month", "=", parsed["month"]),
        ]
        search_user_ids = self._search_employee_user_ids(parsed["search"])
        if search_user_ids is not None:
            if not search_user_ids:
                domain.append(("user_id", "=", False))
            else:
                domain.append(("user_id", "in", list(search_user_ids)))
        action["domain"] = domain
        return action

    @api.model
    def get_online_table_rows(self, filters=None):
        filters = self._parse_filters(filters)
        Session = self.env["lug.user.session"].sudo()
        base_domain = self._session_domain(filters) + [("is_online", "=", True)]
        online_sessions = Session.search(base_domain, order="login_time desc, id desc")
        search_user_ids = self._search_employee_user_ids(filters["search"])
        online_sessions = self._sessions_for_users(online_sessions, search_user_ids)
        rows = self._dedupe_online_rows(online_sessions)
        return self._filter_rows(rows, filters["search"], search_user_ids)

    @api.model
    def action_export_online(self, filters=None):
        filters = self._parse_filters(filters)
        action = self.env.ref("lug_security_audit.action_lug_user_session_online").read()[0]
        domain = self._session_domain(filters) + [("is_online", "=", True)]
        search_user_ids = self._search_employee_user_ids(filters["search"])
        if search_user_ids is not None:
            if not search_user_ids:
                domain.append(("user_id", "=", False))
            else:
                domain.append(("user_id", "in", list(search_user_ids)))
        action["domain"] = domain
        return action

    @api.model
    def action_export_sessions(self, filters=None):
        filters = self._parse_filters(filters)
        action = self.env.ref("lug_security_audit.action_lug_user_session").read()[0]
        domain = list(self._session_domain(filters))
        search_user_ids = self._search_employee_user_ids(filters["search"])
        if search_user_ids is not None:
            if not search_user_ids:
                domain.append(("user_id", "=", False))
            else:
                domain.append(("user_id", "in", list(search_user_ids)))
        action["domain"] = domain
        return action

    @api.model
    def action_cleanup_duplicate_online(self):
        Session = self.env(user=SUPERUSER_ID)["lug.user.session"]
        online = Session.search([("is_online", "=", True)], order="login_time desc, id desc")
        keep_by_user = {}
        to_close = Session.browse()
        for session in online:
            uid = session.user_id.id
            if uid not in keep_by_user:
                keep_by_user[uid] = session
            else:
                to_close |= session
        for session in to_close:
            session._close_session()
        return len(to_close)
