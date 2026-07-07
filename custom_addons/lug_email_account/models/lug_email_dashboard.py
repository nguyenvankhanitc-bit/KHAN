# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class LugEmailDashboard(models.AbstractModel):
    _name = "lug.email.dashboard"
    _description = "Dashboard quản lý tài khoản email"

    @api.model
    def _base_domain(self):
        return [("active", "=", True)]

    @api.model
    def _parse_month_key(self, record):
        text = (record.date_created or "").strip()
        if text:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt).strftime("%Y-%m")
                except ValueError:
                    continue
        if record.create_date:
            return fields.Datetime.to_datetime(record.create_date).strftime("%Y-%m")
        return False

    @api.model
    def _month_label(self, month_key):
        try:
            dt = datetime.strptime(month_key, "%Y-%m")
            return dt.strftime("%m/%Y")
        except ValueError:
            return month_key

    @api.model
    def _group_by_label(self, records, label_fn):
        buckets = defaultdict(int)
        for record in records:
            label = label_fn(record) or "Khác"
            buckets[label] += 1
        rows = [{"label": label, "count": count} for label, count in buckets.items()]
        rows.sort(key=lambda row: (-row["count"], row["label"]))
        return rows

    @api.model
    def _monthly_series(self, records, months=12):
        today = fields.Date.context_today(self)
        if hasattr(today, "replace"):
            anchor = today.replace(day=1)
        else:
            anchor = fields.Date.from_string(today).replace(day=1)

        keys = []
        labels = []
        for offset in range(months - 1, -1, -1):
            month_date = anchor - relativedelta(months=offset)
            key = month_date.strftime("%Y-%m")
            keys.append(key)
            labels.append(self._month_label(key))

        buckets = defaultdict(int)
        for record in records:
            month_key = self._parse_month_key(record)
            if month_key:
                buckets[month_key] += 1

        return {
            "labels": labels,
            "counts": [buckets.get(key, 0) for key in keys],
        }

    @api.model
    def _status_kpi(self, records):
        buckets = {"active": 0, "lock": 0, "cancel": 0, "other": 0}
        for record in records:
            code = record.status_code or "other"
            if code not in buckets:
                buckets["other"] += 1
            else:
                buckets[code] += 1
        total = len(records)
        return {
            "total": total,
            "active": buckets["active"],
            "lock": buckets["lock"],
            "cancel": buckets["cancel"],
            "other": buckets["other"],
            "active_percent": round(buckets["active"] * 100 / total, 1) if total else 0,
            "lock_percent": round(buckets["lock"] * 100 / total, 1) if total else 0,
            "cancel_percent": round(buckets["cancel"] * 100 / total, 1) if total else 0,
        }

    @api.model
    def _with_percent(self, rows):
        total = sum(row["count"] for row in rows) or 1
        for row in rows:
            row["percent"] = round(row["count"] * 100 / total, 1)
        return rows

    @api.model
    def get_dashboard_data(self):
        emails = self.env["lug.email.account"].search(
            self._base_domain(),
            order="id desc",
        )

        by_department = self._with_percent(
            self._group_by_label(
                emails,
                lambda rec: rec.department_id.name or rec.department or "Chưa phân loại",
            )
        )
        by_status = self._with_percent(
            self._group_by_label(
                emails,
                lambda rec: rec.status_id.name if rec.status_id else "Chưa rõ",
            )
        )
        by_month = self._monthly_series(emails)
        kpi = self._status_kpi(emails)

        recent_emails = []
        for record in emails[:10]:
            recent_emails.append(
                {
                    "id": record.id,
                    "stt": record.stt or "",
                    "email": record.email or "",
                    "employee_name": record.employee_name or "",
                    "department": record.department_id.name or record.department or "",
                    "status": record.status_id.name if record.status_id else "",
                    "date_created": record.date_created or "",
                }
            )

        return {
            "total": kpi["total"],
            "kpi": kpi,
            "by_department": by_department,
            "by_status": by_status,
            "by_month": by_month,
            "recent_emails": recent_emails,
        }
