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
                "daily_work_task.menu_daily_work_viewer",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)

        # Checklist CV NV — tick «Checklist CV» trên Phân quyền
        if not Task._checklist_employee_ids():
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_team_checklist",
                raise_if_not_found=False,
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

        # PHÂN CÔNG CÔNG VIỆC — theo bảng Phân quyền phân công
        AssignAccess = self.env["daily.task.assign.access"]
        # Menu Thêm phân công: cần Xem hoặc Thêm
        if not (AssignAccess.can("add", "view") or AssignAccess.can("add", "create")):
            menu = self.env.ref(
                "daily_work_task.menu_task_team_assign_add",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)
        if not AssignAccess.can("list", "view"):
            menu = self.env.ref(
                "daily_work_task.menu_task_team_assign",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)
        if not AssignAccess.can("personnel", "view"):
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_personnel",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)
        if not AssignAccess.can("category", "view"):
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_work_group",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)
        if not AssignAccess.can_any_assign_menu():
            menu = self.env.ref(
                "daily_work_task.menu_daily_work_cat_assign",
                raise_if_not_found=False,
            )
            if menu:
                res.append(menu.id)

        # Tài khoản khóa app: chỉ còn menu Công việc hàng ngày.
        user = self.env.user
        if user.sudo().daily_work_single_app and not user._is_system():
            root = self.env.ref(
                "daily_work_task.menu_daily_work_root", raise_if_not_found=False
            )
            if root:
                others = self.sudo().with_context(active_test=False).search(
                    [("parent_id", "=", False), ("id", "!=", root.id)]
                )
                res.extend(others.ids)
        return res

