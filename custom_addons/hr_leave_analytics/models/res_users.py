# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import AccessError

MIEN_GROUP_XMLIDS = {
    "Nam": "hr_leave_analytics.group_hr_leave_analytics_mien_nam",
    "Bắc": "hr_leave_analytics.group_hr_leave_analytics_mien_bac",
    "ĐTT": "hr_leave_analytics.group_hr_leave_analytics_mien_dtt",
    "VP": "hr_leave_analytics.group_hr_leave_analytics_mien_vp",
}

MIEN_ACTION_XMLIDS = {
    "Nam": "hr_leave_analytics.action_hr_leave_analytics_dashboard_mien_nam",
    "Bắc": "hr_leave_analytics.action_hr_leave_analytics_dashboard_mien_bac",
    "ĐTT": "hr_leave_analytics.action_hr_leave_analytics_dashboard_mien_dtt",
    "VP": "hr_leave_analytics.action_hr_leave_analytics_dashboard_mien_vp",
}

MIEN_ORDER = ("VP", "Nam", "ĐTT", "Bắc")

DEFAULT_USER_MIENS = {
    "anh.trinh@sangtam.com": ["VP"],
    "admin.lug@sangtam.com": ["Nam", "ĐTT", "Bắc"],
}

MANAGER_GROUP_XMLID = "hr_leave_analytics.group_hr_leave_analytics_manager"


class ResUsers(models.Model):
    _inherit = "res.users"

    hr_leave_analytics_allowed_miens = fields.Json(
        string="Miền được xem báo cáo nghỉ phép",
        compute="_compute_hr_leave_analytics_allowed_miens",
        store=True,
    )
    hr_leave_analytics_dashboard_group_ids = fields.Many2many(
        "res.groups",
        "res_users_hr_leave_analytics_group_rel",
        "user_id",
        "group_id",
        string="Quyền dashboard nghỉ phép",
        compute="_compute_hr_leave_analytics_dashboard_group_ids",
        inverse="_inverse_hr_leave_analytics_dashboard_group_ids",
        domain=lambda self: [
            ("id", "in", self._hr_leave_analytics_dashboard_group_ids_list()),
        ],
    )
    hr_leave_analytics_access_summary = fields.Char(
        string="Phạm vi hiệu lực",
        compute="_compute_hr_leave_analytics_access_summary",
    )

    @api.model
    def _hr_leave_analytics_dashboard_group_ids_list(self):
        xmlids = list(MIEN_GROUP_XMLIDS.values()) + [MANAGER_GROUP_XMLID]
        return [
            group.id
            for group in (
                self.env.ref(xmlid, raise_if_not_found=False) for xmlid in xmlids
            )
            if group
        ]

    @api.depends("group_ids")
    def _compute_hr_leave_analytics_dashboard_group_ids(self):
        all_groups = self.env["res.groups"].browse(
            self._hr_leave_analytics_dashboard_group_ids_list()
        )
        for user in self:
            user.hr_leave_analytics_dashboard_group_ids = user.group_ids & all_groups

    def _inverse_hr_leave_analytics_dashboard_group_ids(self):
        all_groups = self.env["res.groups"].browse(
            self._hr_leave_analytics_dashboard_group_ids_list()
        )
        for user in self:
            other_groups = user.group_ids - all_groups
            user.group_ids = other_groups | user.hr_leave_analytics_dashboard_group_ids

    @api.depends("hr_leave_analytics_allowed_miens", "group_ids")
    def _compute_hr_leave_analytics_access_summary(self):
        for user in self:
            allowed = user._hr_leave_analytics_allowed_miens_list()
            if allowed is None:
                user.hr_leave_analytics_access_summary = (
                    "Toàn quyền (báo cáo tổng quan + tất cả miền)"
                )
            elif not allowed:
                user.hr_leave_analytics_access_summary = "Không có quyền"
            else:
                user.hr_leave_analytics_access_summary = ", ".join(
                    mien for mien in MIEN_ORDER if mien in allowed
                )

    @api.depends(
        "group_ids",
        "lug_hr_employee_edit_policy",
        "lug_hr_employee_edit_mien_zone_ids",
        "lug_hr_employee_edit_mien_zone_ids.legacy_mien",
    )
    def _compute_hr_leave_analytics_allowed_miens(self):
        for user in self.sudo():
            user.hr_leave_analytics_allowed_miens = user._hr_leave_analytics_allowed_miens_list()

    def _hr_leave_analytics_has_full_access(self):
        self.ensure_one()
        user = self.sudo()
        return (
            user.has_group("base.group_system")
            or user.has_group("hr.group_hr_manager")
            or user.has_group("hr_leave_analytics.group_hr_leave_analytics_manager")
        )

    def _hr_leave_analytics_mien_groups(self):
        self.ensure_one()
        allowed = []
        for mien, xmlid in MIEN_GROUP_XMLIDS.items():
            if self.has_group(xmlid):
                allowed.append(mien)
        return allowed

    def _hr_leave_analytics_allowed_miens_list(self):
        """None = unrestricted; list = allowed legacy miền keys."""
        self.ensure_one()
        if self._hr_leave_analytics_has_full_access():
            return None
        allowed = self._hr_leave_analytics_mien_groups()
        if allowed:
            return allowed
        if (self.lug_hr_employee_edit_policy or "none") == "zones":
            zones = [
                (zone.legacy_mien or "").strip()
                for zone in self.lug_hr_employee_edit_mien_zone_ids
                if (zone.legacy_mien or "").strip()
            ]
            if zones:
                return zones
        return []

    def _hr_leave_analytics_set_mien_groups(self, miens):
        self.ensure_one()
        manager_group = self.env.ref(
            "hr_leave_analytics.group_hr_leave_analytics_manager",
            raise_if_not_found=False,
        )
        commands = []
        if manager_group and manager_group in self.group_ids:
            commands.append((3, manager_group.id))
        for mien, xmlid in MIEN_GROUP_XMLIDS.items():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if not group:
                continue
            if mien in miens:
                commands.append((4, group.id))
            elif group in self.group_ids:
                commands.append((3, group.id))
        if commands:
            self.write({"group_ids": commands})

    @api.model
    def _hr_leave_analytics_assign_default_groups(self):
        for login, miens in DEFAULT_USER_MIENS.items():
            user = self.sudo().search([("login", "=", login)], limit=1)
            if user:
                user._hr_leave_analytics_set_mien_groups(miens)

    @api.model
    def _hr_leave_analytics_sync_groups_from_lug_zones(self):
        users = self.sudo().search([
            ("lug_hr_employee_edit_policy", "=", "zones"),
            ("lug_hr_employee_edit_mien_zone_ids", "!=", False),
        ])
        for user in users:
            if user.login in DEFAULT_USER_MIENS:
                continue
            miens = [
                (zone.legacy_mien or "").strip()
                for zone in user.lug_hr_employee_edit_mien_zone_ids
                if (zone.legacy_mien or "").strip()
            ]
            if miens:
                user._hr_leave_analytics_set_mien_groups(miens)

    def _hr_leave_analytics_check_mien_access(self, mien):
        self.ensure_one()
        allowed = self._hr_leave_analytics_allowed_miens_list()
        if allowed is None:
            return
        if not mien or mien not in allowed:
            raise AccessError("Bạn không có quyền xem dashboard miền này.")

    def _hr_leave_analytics_check_overview_access(self):
        self.ensure_one()
        allowed = self._hr_leave_analytics_allowed_miens_list()
        if allowed is not None:
            raise AccessError("Bạn không có quyền xem báo cáo tổng quan toàn hệ thống.")

    def action_open_hr_leave_analytics_dashboard(self):
        self.ensure_one()
        return self.env["hr.leave.analytics.dashboard"].action_open_for_user()
