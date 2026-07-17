# -*- coding: utf-8 -*-

from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        """Ẩn menu Xem NV / Báo cáo tổng nếu chưa được phân quyền cấu hình."""
        res = super()._load_menus_blacklist()
        user = self.env.user
        if user.has_group("daily_work_task.group_daily_work_manager"):
            return res

        Task = self.env["daily.task"]
        # Xem công việc NV — cần có NV trong Phân quyền xem
        if not Task._viewable_employee_ids():
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_viewer", raise_if_not_found=False
            )
            if menu:
                res.append(menu.id)

        # Báo cáo tổng — cần phòng ban hoặc User bị xem trong Phân quyền BCT
        allowed = self.env[
            "daily.task.report.access"
        ].reportable_employee_ids_for_user()
        if not allowed:
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_summary_report",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)

        # Báo cáo hiệu suất — cần dòng Phân quyền BCHS
        if not self.env["daily.task.performance.access"].user_can_view():
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_performance_report",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)
        return res
