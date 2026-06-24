# Part of Odoo. See LICENSE file for full copyright and licensing details.



from calendar import monthrange

from dateutil.relativedelta import relativedelta



from odoo import api, fields, models

from odoo.exceptions import AccessError

from .res_users import MIEN_ACTION_XMLIDS





class HrLeaveAnalyticsDashboard(models.AbstractModel):

    _name = "hr.leave.analytics.dashboard"

    _inherit = ["hr.leave.analytics.job.title.mixin"]

    _description = "HR Leave Analytics Dashboard"



    _MIEN_ORDER = ("VP", "Nam", "ĐTT", "Bắc")



    @api.model

    def _default_period(self):

        today = fields.Date.context_today(self)

        start = today.replace(day=1)

        return start, today



    @api.model

    def _resolve_employee_mien(self, filters=None):

        filters = filters or {}

        return filters.get("employee_mien") or self.env.context.get("dashboard_mien") or False



    @api.model

    def _parse_filters(self, filters=None):

        filters = filters or {}

        date_from = filters.get("date_from")

        date_to = filters.get("date_to")

        if not date_from or not date_to:

            date_from, date_to = self._default_period()

        active_mien = self._resolve_employee_mien(filters)

        return {

            "date_from": fields.Date.to_date(date_from),

            "date_to": fields.Date.to_date(date_to),

            "employee_mien": active_mien,

        }



    @api.model

    def _mien_domain(self, filters):

        domain = [("company_id", "in", self.env.companies.ids)]

        if filters.get("employee_mien"):

            domain.append(("employee_mien", "=", filters["employee_mien"]))

        return domain



    @api.model

    def _business_days_in_month(self, date_from, date_to):

        count = 0

        day = date_from

        while day <= date_to:

            if day.weekday() < 5:

                count += 1

            day += relativedelta(days=1)

        return count



    @api.model

    def _serialize_mien_rows(self, rows, active_mien=False):

        labels = dict(self.env["hr.leave.analytics.mien.summary"]._fields["employee_mien"]._description_selection(self.env))

        mien_list = (active_mien,) if active_mien in self._MIEN_ORDER else self._MIEN_ORDER

        totals = {mien: {"employee_count": 0, "leave_days": 0.0} for mien in mien_list}

        for row in rows:

            if row.employee_mien not in totals:

                continue

            totals[row.employee_mien]["employee_count"] += row.employee_count or 0

            totals[row.employee_mien]["leave_days"] += row.leave_days or 0.0



        business_days = self._business_days_in_month(*self._default_period())

        result = []

        for mien in mien_list:

            employee_count = totals[mien]["employee_count"]

            leave_days = round(totals[mien]["leave_days"], 2)

            if employee_count and business_days:

                leave_rate = round((leave_days / (employee_count * business_days)) * 100, 2)

            else:

                leave_rate = 0.0

            result.append(

                {

                    "mien": mien,

                    "label": labels.get(mien, mien),

                    "employee_count": employee_count,

                    "leave_days": leave_days,

                    "leave_rate": leave_rate,

                }

            )

        return result



    @api.model

    def action_open_for_user(self):

        user = self.env.user

        allowed = user._hr_leave_analytics_allowed_miens_list()

        if allowed is None:

            xmlid = "hr_leave_analytics.action_hr_leave_analytics_dashboard_client"

        else:

            if not allowed:

                raise AccessError("Bạn không có quyền xem báo cáo nghỉ phép.")

            preferred = [m for m in ("VP", "Nam", "ĐTT", "Bắc") if m in allowed]

            xmlid = MIEN_ACTION_XMLIDS[preferred[0]]

        action = self.env.ref(xmlid).sudo().read()[0]

        return action



    @api.model

    def get_dashboard_data(self, filters=None):

        filters = self._parse_filters(filters)

        active_mien = filters["employee_mien"]

        user = self.env.user

        if active_mien:

            user._hr_leave_analytics_check_mien_access(active_mien)

        else:

            user._hr_leave_analytics_check_overview_access()

        mien_domain = self._mien_domain(filters)

        store_domain = list(mien_domain)

        employee_domain = list(mien_domain)



        Mien = self.env["hr.leave.analytics.mien.summary"]

        Store = self.env["hr.leave.analytics.store.summary"]

        Employee = self.env["hr.leave.analytics.employee.watch"]



        mien_domain_all = [("company_id", "in", self.env.companies.ids)]

        if active_mien:

            mien_rows = self._serialize_mien_rows(Mien.search(mien_domain), active_mien=active_mien)

        else:

            mien_rows = self._serialize_mien_rows(Mien.search(mien_domain_all))

        top_stores = Store.search(store_domain, order="leave_days desc", limit=10)

        alert_stores = Store.search(

            store_domain,

            order="on_leave_rate desc, on_leave_today desc",

            limit=10,

        )

        watch_employees = Employee.search(employee_domain, order="leave_days desc", limit=10)



        mien_label = False

        if active_mien:

            labels = dict(Mien._fields["employee_mien"]._description_selection(self.env))

            mien_label = labels.get(active_mien, active_mien)



        return {

            "title": mien_label or "Tổng quan toàn hệ thống",

            "is_regional_dashboard": bool(active_mien),

            "mien_chart_title": (

                f"{mien_label} — Tổng ngày nghỉ & Tỷ lệ nghỉ phép"

                if mien_label

                else "So sánh giữa các Miền — Tổng ngày nghỉ & Tỷ lệ nghỉ phép"

            ),

            "active_mien": active_mien or False,

            "filters": {

                "date_from": fields.Date.to_string(filters["date_from"]),

                "date_to": fields.Date.to_string(filters["date_to"]),

                "employee_mien": active_mien or False,

            },

            "mien_comparison": mien_rows,

            "top_stores": [

                {

                    "store_name": row.store_name,

                    "job_title": row.top_job_title_display or "—",

                    "employee_count": row.employee_count,

                    "leave_days": round(row.leave_days or 0.0, 2),

                    "store_id": row.store_id.id,

                }

                for row in top_stores

            ],

            "watch_employees": [

                {

                    "employee_name": row.employee_name,

                    "store_name": row.store_name or "—",

                    "job_title": row.job_title_display or "—",

                    "leave_days": round(row.leave_days or 0.0, 2),

                    "employee_id": row.employee_id.id,

                }

                for row in watch_employees

            ],

            "store_alerts": [

                {

                    "store_name": row.store_name,

                    "job_title": row.on_leave_job_titles_display or row.top_job_title_display or "—",

                    "employee_count": row.employee_count,

                    "on_leave_today": row.on_leave_today,

                    "on_leave_rate": round(row.on_leave_rate or 0.0, 2),

                    "store_id": row.store_id.id,

                }

                for row in alert_stores

            ],

        }



    @api.model

    def action_drill_down(self, drill_type, filters=None, record_id=False):

        filters = self._parse_filters(filters)

        base_domain = self._mien_domain(filters)



        if drill_type == "employee" and record_id:

            action = self.env.ref("hr_leave_analytics.action_hr_leave_analytics_employee_watch").sudo().read()[0]

            action["domain"] = base_domain + [("employee_id", "=", record_id)]

            return action

        if drill_type == "store" and record_id:

            action = self.env.ref("hr_leave_analytics.action_hr_leave_analytics_store_rank").sudo().read()[0]

            action["domain"] = base_domain + [("store_id", "=", record_id)]

            return action

        if drill_type == "mien" and record_id:

            action = self.env.ref("hr_leave_analytics.action_hr_leave_analytics_mien_compare").sudo().read()[0]

            action["domain"] = base_domain + [("employee_mien", "=", record_id)]

            return action



        action = self.env.ref("hr_leave_analytics.action_hr_leave_analytics_report").sudo().read()[0]

        action["domain"] = base_domain + [("state", "=", "validate")]

        return action



    @api.model

    def action_export_excel(self, export_type, filters=None):

        filters = self._parse_filters(filters)

        if export_type == "mien_compare" and not filters.get("employee_mien"):
            domain = [("company_id", "in", self.env.companies.ids)]
        else:
            domain = self._mien_domain(filters)

        mapping = {

            "watch_employees": "hr_leave_analytics.action_hr_leave_analytics_employee_watch",

            "top_stores": "hr_leave_analytics.action_hr_leave_analytics_store_rank",

            "store_alerts": "hr_leave_analytics.action_hr_leave_analytics_store_alert",

            "mien_compare": "hr_leave_analytics.action_hr_leave_analytics_mien_compare",

        }

        xmlid = mapping.get(export_type, mapping["mien_compare"])

        action = self.env.ref(xmlid).sudo().read()[0]

        action["domain"] = domain

        return action


