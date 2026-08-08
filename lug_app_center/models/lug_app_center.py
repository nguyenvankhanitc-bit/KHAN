# -*- coding: utf-8 -*-

from odoo import api, fields, models


_WEEKDAYS_VI = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)


class LugAppCenter(models.AbstractModel):
    _name = "lug.app.center"
    _description = "Enterprise Application Center"

    @api.model
    def get_portal_data(self):
        """User/company header data. App list comes from the web menu service."""
        user = self.env.user
        company = self.env.company
        partner = user.partner_id
        today = fields.Date.context_today(self)

        first_name = "bạn"
        if user.name:
            first_name = user.name.split()[-1]

        avatar_url = False
        if partner and partner.image_128:
            avatar_url = f"/web/image/res.partner/{partner.id}/image_128"

        greeting = self._build_greeting_dashboard(user=user, today=today)

        return {
            "company_name": "CÔNG TY TNHH SÁNG TÂM",
            "company_slogan": "Bền vững hôm nay - Thịnh vượng ngày mai",
            "company_website": "www.sangtam.com.vn",
            "company_address": self._format_company_address(company),
            "company_logo_url": (
                f"/web/image/res.company/{company.id}/logo"
                if company.logo
                else "/lug_app_center/static/src/img/sataco_logo.png"
            ),
            "user_name": user.name or "",
            "user_first_name": first_name,
            "user_login": user.login or "",
            "user_email": user.email or partner.email or "",
            "user_phone": user.phone or partner.phone or "",
            "user_role": (
                "Quản trị hệ thống"
                if user.has_group("base.group_system")
                else "Người dùng"
            ),
            "user_initial": (user.name or "U")[:1].upper(),
            "avatar_url": avatar_url,
            "welcome": greeting.get("headline")
            or "Chào mừng bạn đến với hệ thống quản trị doanh nghiệp",
            "greeting": greeting,
        }

    @api.model
    def _format_company_address(self, company):
        parts = [
            company.street,
            company.street2,
            company.city,
            company.state_id.name if company.state_id else False,
            company.country_id.name if company.country_id else False,
        ]
        return ", ".join(part for part in parts if part) or (
            "30-34 Đường 74, Phường Bình Phú, TP. Hồ Chí Minh"
        )

    @api.model
    def _build_greeting_dashboard(self, user=None, today=None):
        """
        Greeting Dashboard cho khung Welcome.
        Đếm việc từ daily.task (nếu module có) — đúng user login, không sudo.
        """
        user = user or self.env.user
        today = today or fields.Date.context_today(self)
        weekday = _WEEKDAYS_VI[today.weekday()]
        today_label = "Hôm nay, ngày %s" % today.strftime("%d/%m/%Y")
        today_label_full = "Hôm nay là %s, ngày %s" % (
            weekday,
            today.strftime("%d/%m/%Y"),
        )

        today_count = 0
        overdue_count = 0
        has_tasks = False

        if "daily.task" in self.env:
            try:
                Task = self.env["daily.task"]
                today_count, overdue_count = self._count_user_daily_tasks(Task, today)
                has_tasks = True
            except Exception:
                # Module có model nhưng ACL/cấu hình lỗi → không làm hỏng App Center
                self.env.cr.rollback()
                today_count = 0
                overdue_count = 0
                has_tasks = False

        primary, tip = self._greeting_messages(today_count, overdue_count, has_tasks)

        return {
            "headline": "Xin chào, %s! 👋" % (user.name or "bạn"),
            "today_label": today_label,
            "today_label_full": today_label_full,
            "today_iso": today.isoformat(),
            "today_count": today_count,
            "overdue_count": overdue_count,
            "has_task_module": has_tasks,
            "primary_line": primary,
            "tip_line": tip,
            "show_overdue": bool(overdue_count),
            "overdue_line": (
                "🔴 Bạn có %s việc quá hạn. Hãy ưu tiên xử lý." % overdue_count
                if overdue_count
                else ""
            ),
        }

    @api.model
    def _count_user_daily_tasks(self, Task, today):
        """
        today_count: việc của user, hạn = hôm nay, chưa done.
        overdue_count: việc của user, hạn < hôm nay, chưa done.
        Tôn trọng ACL — không sudo.
        """
        emp = False
        if hasattr(Task, "_my_hr_employee"):
            emp = Task._my_hr_employee()
        if not emp and "hr.employee" in self.env:
            emp = self.env["hr.employee"].search(
                [("user_id", "=", self.env.uid)], limit=1
            )
        if not emp:
            return 0, 0

        base = [
            ("assignee_id.employee_id", "=", emp.id),
            ("state", "!=", "done"),
        ]
        today_count = Task.search_count(base + [("deadline", "=", today)])
        overdue_count = Task.search_count(base + [("deadline", "<", today)])
        return today_count, overdue_count

    @api.model
    def _greeting_messages(self, today_count, overdue_count, has_tasks):
        """Câu primary + tip theo số việc / quá hạn."""
        if not has_tasks:
            return (
                "Chào mừng bạn đến với hệ thống quản trị doanh nghiệp.",
                "Chúc bạn một ngày mới vui vẻ và hiệu quả! 🌟",
            )

        if overdue_count > 0:
            primary = "🔴 Bạn có %s việc đã quá hạn." % overdue_count
            tip = "Hãy ưu tiên xử lý các công việc này."
            if today_count > 0:
                tip = (
                    "🟠 Hôm nay còn %s việc cần xử lý. Hãy ưu tiên việc quá hạn trước."
                    % today_count
                )
            return primary, tip

        if today_count <= 0:
            return (
                "🎉 Tuyệt vời! Bạn đã hoàn thành toàn bộ công việc hôm nay.",
                "Chúc bạn một ngày làm việc thật hiệu quả!",
            )
        if today_count == 1:
            return (
                "📋 Bạn còn 1 việc cần hoàn thành hôm nay.",
                "⏰ Hãy tranh thủ xử lý trước khi hết ngày nhé!",
            )
        if today_count <= 5:
            return (
                "📋 Bạn còn %s việc cần xử lý hôm nay." % today_count,
                "💪 Hãy tiếp tục xử lý nhé!",
            )
        return (
            "📋 Hôm nay bạn có %s việc cần xử lý." % today_count,
            "💪 Hãy ưu tiên các công việc quan trọng trước nhé!",
        )
