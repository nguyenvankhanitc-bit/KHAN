# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models

from .lug_constants import (
    LUG_DATA_SCOPES,
    LUG_DISCUSS_ADMIN_MENU_PERMISSIONS,
    LUG_DISCUSS_EMPLOYEE_HIDDEN_MENU_XMLIDS,
    LUG_HR_VIEW_ONLY_HIDDEN_MENU_XMLIDS,
    LUG_SCOPE_TO_VISIBILITY,
    ROLE_TO_LUG_SCOPE,
    VISIBILITY_TO_LUG_SCOPE,
)
from .lug_odoo_groups import (
    LUG_ALWAYS_HIDDEN_MENU_XMLIDS,
    LUG_APP_ODOO_GROUPS,
    ROLE_MANAGED_GROUP_XMLIDS,
)

LUG_TIME_OFF_ROLE_XMLIDS = {
    "officer": "hr_holidays.group_hr_holidays_user",
    "manager": "hr_holidays.group_hr_holidays_manager",
}

LUG_LEAVE_MIEN_SCOPE_GROUP_XMLIDS = [
    "hr_leave_type_mien.group_leave_mien_vp",
    "hr_leave_type_mien.group_leave_mien_store",
]


class ResUsers(models.Model):
    _inherit = "res.users"

    lug_group_ids = fields.Many2many(
        "lug.group",
        "lug_user_groups",
        "user_id",
        "group_id",
        string="Nhóm quyền LUG",
    )
    lug_data_scope = fields.Selection(
        selection=LUG_DATA_SCOPES,
        string="Phạm vi dữ liệu LUG",
        default="self",
        help="Giới hạn phạm vi dữ liệu theo mô hình LUG Permission Center.",
    )
    lug_user_permission_ids = fields.One2many(
        "lug.user.permission",
        "user_id",
        string="Quyền bổ sung riêng",
    )
    lug_permission_enforced = fields.Boolean(
        compute="_compute_lug_permission_enforced",
        string="Áp dụng LUG Permission",
    )

    lug_hr_employee_edit_policy = fields.Selection(
        selection=[
            ("none", "Không giới hạn (mặc định)"),
            ("zones", "Giới hạn theo Miền"),
        ],
        string="Quyền sửa hồ sơ nhân viên",
        default="none",
        help=(
            "Chỉ áp dụng cho thao tác sửa/tạo hồ sơ nhân viên (hr.employee). "
            "Không ảnh hưởng các chức năng khác."
        ),
    )
    lug_hr_employee_edit_mien_zone_ids = fields.Many2many(
        "hr.mien.zone",
        "lug_user_hr_employee_edit_mien_zone_rel",
        "user_id",
        "mien_zone_id",
        string="Miền được sửa hồ sơ",
        help="Chỉ áp dụng khi 'Quyền sửa hồ sơ nhân viên' = 'Giới hạn theo Miền'.",
    )
    lug_leave_full_activity_report = fields.Boolean(
        string="Báo cáo toàn bộ hoạt động nghỉ phép",
        default=False,
        help=(
            "Khi bật, biểu tượng hoạt động (đồng hồ) sẽ hiển thị TẤT CẢ đơn nghỉ phép "
            "đang chờ mà user này có mặt trong bất kỳ bước duyệt nào — kể cả khi hiện tại "
            "chưa tới lượt duyệt của họ. Giúp người quản lý nắm được có bao nhiêu đơn đang "
            "chờ và đang ở bước nào để nhắc người phụ trách bước đó."
        ),
    )
    lug_time_off_role = fields.Selection(
        selection=[
            ("none", "Không"),
            (
                "officer",
                "Người phụ trách: Quản lý tất cả đơn",
            ),
            ("manager", "Quản trị viên"),
        ],
        string="Ngày nghỉ",
        default="none",
        help="Vai trò Ngày nghỉ tương đương mục Nhân sự trên tab Quyền truy cập.",
    )
    lug_leave_mien_scope_group_ids = fields.Many2many(
        "res.groups",
        "lug_user_leave_mien_scope_group_rel",
        "user_id",
        "group_id",
        string="Phạm vi Ngày nghỉ",
        compute="_compute_lug_leave_mien_scope_group_ids",
        inverse="_inverse_lug_leave_mien_scope_group_ids",
        domain=lambda self: [
            ("id", "in", self._lug_leave_mien_scope_managed_group_ids()),
        ],
        help="Giới hạn Miền được xem trên đơn nghỉ phép.",
    )

    def lug_allowed_employee_edit_legacy_miens(self):
        """Return a set of allowed legacy_mien strings for employee profile edits."""
        self.ensure_one()
        user = self.sudo()
        if user.has_group("base.group_system") or user.has_group("hr.group_hr_manager"):
            return None  # unrestricted
        if (user.lug_hr_employee_edit_policy or "none") != "zones":
            return None
        zones = set(
            (z.legacy_mien or "").strip()
            for z in user.lug_hr_employee_edit_mien_zone_ids
            if (z.legacy_mien or "").strip()
        )
        return zones or None

    @api.model
    def _lug_set_default_employee_edit_scopes(self):
        """Apply requested defaults; safe to rerun on upgrades."""
        Zone = self.env["hr.mien.zone"].sudo()
        zone_map = {z.legacy_mien: z for z in Zone.search([]) if z.legacy_mien}

        scope_defaults = {
            "admin.lug@sangtam.com": "region",
            "anh.trinh@sangtam.com": "region",
        }

        def _set_user_zones(login, legacy_miens):
            user = self.sudo().search([("login", "=", login)], limit=1)
            if not user:
                return
            zones = Zone.browse([zone_map[m].id for m in legacy_miens if m in zone_map])
            if not zones:
                return
            edit_group = self.env.ref(
                "hr_employee_self_only.group_hr_employee_edit_allowed",
                raise_if_not_found=False,
            )
            view_group = self.env.ref(
                "hr_employee_self_only.group_hr_employee_view_personal_allowed",
                raise_if_not_found=False,
            )
            extra_groups = [g for g in (edit_group, view_group) if g]
            vals = {
                "lug_hr_employee_edit_policy": "zones",
                "lug_hr_employee_edit_mien_zone_ids": [(6, 0, zones.ids)],
            }
            scope = scope_defaults.get(login)
            if scope:
                vals["lug_data_scope"] = scope
            if extra_groups:
                vals["group_ids"] = [(4, g.id) for g in extra_groups]
            user.with_context(skip_lug_sync=False).write(vals)
            if user._lug_permission_is_enforced():
                user._sync_lug_visibility_policy()

        _set_user_zones("admin.lug@sangtam.com", ["Nam", "ĐTT", "Bắc"])
        _set_user_zones("anh.trinh@sangtam.com", ["VP"])

    @api.depends("lug_group_ids", "lug_user_permission_ids")
    def _compute_lug_permission_enforced(self):
        for user in self:
            user.lug_permission_enforced = user._lug_permission_is_enforced()

    @api.model
    def _lug_leave_mien_scope_managed_group_ids(self):
        ids = []
        for xmlid in LUG_LEAVE_MIEN_SCOPE_GROUP_XMLIDS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                ids.append(group.id)
        return ids

    @api.depends("group_ids")
    def _compute_lug_leave_mien_scope_group_ids(self):
        managed = self.env["res.groups"].browse(self._lug_leave_mien_scope_managed_group_ids())
        for user in self:
            user.lug_leave_mien_scope_group_ids = user.group_ids & managed

    def _inverse_lug_leave_mien_scope_group_ids(self):
        managed = self.env["res.groups"].browse(self._lug_leave_mien_scope_managed_group_ids())
        for user in self:
            user.group_ids = (user.group_ids - managed) | user.lug_leave_mien_scope_group_ids

    @api.model
    def _lug_time_off_role_from_group_ids(self, group_ids):
        manager = self.env.ref(
            "hr_holidays.group_hr_holidays_manager", raise_if_not_found=False
        )
        officer = self.env.ref(
            "hr_holidays.group_hr_holidays_user", raise_if_not_found=False
        )
        group_ids = set(group_ids)
        if manager and manager.id in group_ids:
            return "manager"
        if officer and officer.id in group_ids:
            return "officer"
        return "none"

    def _lug_time_off_role_managed_group_ids(self):
        ids = set()
        for xmlid in LUG_TIME_OFF_ROLE_XMLIDS.values():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                ids.add(group.id)
        return ids

    def _lug_time_off_role_group_ids(self):
        self.ensure_one()
        role = self.lug_time_off_role or "none"
        xmlid = LUG_TIME_OFF_ROLE_XMLIDS.get(role)
        if not xmlid:
            return set()
        group = self.env.ref(xmlid, raise_if_not_found=False)
        return {group.id} if group else set()

    def _apply_lug_time_off_role_to_groups(self):
        managed = self._lug_time_off_role_managed_group_ids()
        for user in self:
            keep = user.group_ids.filtered(lambda group: group.id not in managed)
            role_groups = self.env["res.groups"].browse(list(user._lug_time_off_role_group_ids()))
            target = keep | role_groups
            if set(target.ids) != set(user.group_ids.ids):
                super(
                    ResUsers,
                    user.with_context(skip_lug_sync=True, skip_role_apply=True),
                ).write({"group_ids": [(6, 0, target.ids)]})

    def _lug_permission_bypass(self):
        self.ensure_one()
        return self.has_group("base.group_system")

    def _lug_sudo(self):
        self.ensure_one()
        return self.sudo()

    def _lug_permission_is_enforced(self):
        self.ensure_one()
        user = self._lug_sudo()
        if user._lug_permission_bypass():
            return False
        return bool(
            user.lug_group_ids
            or user.lug_user_permission_ids.filtered(
                lambda line: line._active_permission_codes()
            )
        )

    @api.model
    def _lug_managed_group_ids(self):
        xmlids = set(ROLE_MANAGED_GROUP_XMLIDS)
        for app_groups in LUG_APP_ODOO_GROUPS.values():
            for perm_groups in app_groups.values():
                xmlids.update(perm_groups)
        ids = set()
        for xmlid in xmlids:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                ids.add(group.id)
        for xmlid in (
            "hr_leave_type_mien.group_leave_mien_vp",
            "hr_leave_type_mien.group_leave_mien_store",
        ):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                ids.add(group.id)
        return ids

    def _lug_effective_permission_map(self):
        """Return {app_code: set(permission_code)} for the current user."""
        self.ensure_one()
        user = self._lug_sudo()
        result = defaultdict(set)
        for group in user.lug_group_ids:
            for line in group.permission_line_ids:
                if not line.app_id.code:
                    continue
                result[line.app_id.code].update(line._active_permission_codes())
        for line in user.lug_user_permission_ids:
            if not line.app_id.code:
                continue
            result[line.app_id.code].update(line._active_permission_codes())
        return result

    def _lug_leave_mien_scope_target_group_ids(self):
        """Miền scope groups granted by LUG sync."""
        self.ensure_one()
        user = self._lug_sudo()
        explicit = set(user.lug_leave_mien_scope_group_ids.ids)
        if explicit:
            return explicit
        if (user.lug_hr_employee_edit_policy or "none") != "zones":
            return set()
        zones = {
            (z.legacy_mien or "").strip()
            for z in user.lug_hr_employee_edit_mien_zone_ids
            if (z.legacy_mien or "").strip()
        }
        ids = set()
        vp = self.env.ref("hr_leave_type_mien.group_leave_mien_vp", raise_if_not_found=False)
        store = self.env.ref(
            "hr_leave_type_mien.group_leave_mien_store", raise_if_not_found=False
        )
        if zones == {"VP"} and vp:
            ids.add(vp.id)
        elif zones and zones <= {"Bắc", "Nam", "ĐTT"} and store:
            ids.add(store.id)
        return ids

    def _lug_target_group_ids(self):
        self.ensure_one()
        user = self._lug_sudo()
        target = set()
        base_user = self.env.ref("base.group_user", raise_if_not_found=False)
        if base_user:
            target.add(base_user.id)
        permission_map = self._lug_effective_permission_map()
        for app_code, perms in permission_map.items():
            app_groups = LUG_APP_ODOO_GROUPS.get(app_code, {})
            for perm_code in perms:
                for xmlid in app_groups.get(perm_code, []):
                    group = self.env.ref(xmlid, raise_if_not_found=False)
                    if group:
                        target.add(group.id)
        target.update(user._lug_time_off_role_group_ids())
        target.update(user._lug_leave_mien_scope_target_group_ids())
        return target

    def _sync_lug_odoo_groups(self):
        managed = self._lug_managed_group_ids()
        holidays_user = self.env.ref(
            "hr_holidays.group_hr_holidays_user", raise_if_not_found=False
        )
        for user in self:
            if not user._lug_permission_is_enforced():
                continue
            target = user._lug_target_group_ids()
            keep = user.group_ids.filtered(lambda g: g.id not in managed)
            new_groups = keep | self.env["res.groups"].browse(list(target))
            if holidays_user and (user.lug_time_off_role or "none") not in (
                "officer",
                "manager",
            ):
                new_groups -= holidays_user
            if set(new_groups.ids) != set(user.group_ids.ids):
                super(
                    ResUsers,
                    user.with_context(skip_lug_sync=True, skip_role_apply=True),
                ).write({"group_ids": [(6, 0, new_groups.ids)]})

    def _apply_user_role(self, set_scope=True):
        role_users = self.filtered(lambda u: not u._lug_permission_is_enforced())
        if role_users:
            super(ResUsers, role_users)._apply_user_role(set_scope=set_scope)
            if set_scope:
                for user in role_users:
                    lug_scope = ROLE_TO_LUG_SCOPE.get(user.user_role)
                    if lug_scope and user.lug_data_scope != lug_scope:
                        super(
                            ResUsers,
                            user.with_context(skip_lug_sync=True, skip_role_apply=True),
                        ).write({"lug_data_scope": lug_scope})
                role_users._sync_lug_visibility_policy()
        return True

    def has_lug_permission(self, app_code, permission_code="view"):
        """Check effective LUG permission for an application action."""
        self.ensure_one()
        if not self._lug_permission_is_enforced():
            return True
        permission_map = self._lug_effective_permission_map()
        return permission_code in permission_map.get(app_code, set())

    def get_lug_data_scope(self):
        self.ensure_one()
        return self.lug_data_scope or "self"

    def _lug_visibility_policy_from_scope(self):
        """Map LUG data scope to hr_employee_hrm_detail visibility_policy."""
        self.ensure_one()
        user = self._lug_sudo()
        scope = user.lug_data_scope or "self"
        if scope == "store":
            if user.assigned_ma_bo_phan_ids:
                return "assigned"
            return "ma_bo_phan"
        return LUG_SCOPE_TO_VISIBILITY.get(scope, "self")

    def _sync_lug_visibility_policy(self):
        for user in self:
            policy = user._lug_visibility_policy_from_scope()
            if user.visibility_policy != policy:
                super(
                    ResUsers,
                    user.with_context(skip_lug_sync=True, skip_role_apply=True),
                ).write({"visibility_policy": policy})

    @api.model
    def _lug_backfill_data_scope_from_visibility(self):
        """One-time alignment: map legacy visibility_policy to lug_data_scope."""
        all_users = self.sudo().search([])
        for user in all_users:
            if user._lug_permission_bypass():
                continue
            expected = VISIBILITY_TO_LUG_SCOPE.get(user.visibility_policy or "self", "self")
            if user.lug_data_scope == expected:
                continue
            if user.lug_data_scope == "self" or user._lug_permission_is_enforced():
                super(
                    ResUsers,
                    user.with_context(skip_lug_sync=True, skip_role_apply=True),
                ).write({"lug_data_scope": expected})
        all_users._sync_lug_visibility_policy()

    def _lug_ui_systray_flags(self):
        self.ensure_one()
        if not self._lug_permission_is_enforced():
            return {
                "hide_messaging": False,
                "hide_activities": False,
                "hide_help": False,
            }
        perm_map = self._lug_effective_permission_map()
        hide_messaging = "view" not in perm_map.get("discuss", set())
        return {
            "hide_messaging": hide_messaging,
            "hide_activities": hide_messaging,
            "hide_help": True,
        }

    def _lug_hidden_discuss_config_menu_ids(self):
        """Hide Discuss > Kênh and Cấu hình for all regular users.

        Visible only for Administrator or LUG Discuss Edit (or stronger).
        """
        self.ensure_one()
        if self.has_group("base.group_system"):
            return []
        if self._lug_permission_is_enforced():
            discuss_perms = self._lug_effective_permission_map().get("discuss", set())
            if discuss_perms & LUG_DISCUSS_ADMIN_MENU_PERMISSIONS:
                return []
        hidden = []
        for xmlid in LUG_DISCUSS_EMPLOYEE_HIDDEN_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden

    def _lug_hidden_hr_submenu_ids(self):
        self.ensure_one()
        perm_map = self._lug_effective_permission_map()
        hr_perms = perm_map.get("hr", set())
        if "view" not in hr_perms:
            return []
        if hr_perms - {"view"}:
            return []
        hidden = []
        for xmlid in LUG_HR_VIEW_ONLY_HIDDEN_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden

    def _lug_granted_root_menu_ids(self):
        self.ensure_one()
        permission_map = self._lug_effective_permission_map()
        installed = self.env["lug.app"]._get_installed_module_names()
        granted = set()
        for app in self.env["lug.app"].sudo().search([("active", "=", True)]):
            if not app._is_module_available(installed):
                continue
            if "view" in permission_map.get(app.code, set()):
                granted.update(app._resolve_menu_ids())
        return granted

    def _lug_hidden_menu_ids(self):
        self.ensure_one()
        user = self._lug_sudo()
        if not user._lug_permission_is_enforced():
            return []
        granted_roots = user._lug_granted_root_menu_ids()
        hidden = []
        for root in self.env["ir.ui.menu"].sudo().search([("parent_id", "=", False)]):
            if root.id in granted_roots:
                continue
            hidden.append(root.id)
        for xmlid in LUG_ALWAYS_HIDDEN_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.id not in hidden:
                hidden.append(menu.id)
        hidden.extend(self._lug_hidden_hr_submenu_ids())
        return hidden

    @api.model
    def _lug_clear_menu_cache_global(cls, env):
        env.registry.clear_cache()

    def _lug_clear_menu_cache(self):
        self.env.registry.clear_cache()

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_lug_sync"):
            return res
        lug_fields = {
            "lug_group_ids",
            "lug_user_permission_ids",
            "lug_data_scope",
            "user_role",
            "assigned_ma_bo_phan_ids",
            "lug_hr_employee_edit_policy",
            "lug_hr_employee_edit_mien_zone_ids",
            "lug_time_off_role",
            "lug_leave_mien_scope_group_ids",
        }
        scope_fields = {"lug_data_scope", "assigned_ma_bo_phan_ids"}
        should_sync = bool(lug_fields & set(vals))
        if "lug_time_off_role" in vals:
            non_enforced = self.filtered(lambda u: not u._lug_permission_is_enforced())
            if non_enforced:
                non_enforced._apply_lug_time_off_role_to_groups()
        if scope_fields & set(vals):
            self._sync_lug_visibility_policy()
        if "group_ids" in vals:
            should_sync = should_sync or bool(
                self.filtered(lambda u: u._lug_permission_is_enforced())
            )
        if should_sync:
            enforced = self.filtered(lambda u: u._lug_permission_is_enforced())
            if enforced:
                enforced._sync_lug_odoo_groups()
            self._lug_clear_menu_cache()
        if "lug_leave_full_activity_report" in vals:
            self.env["hr.leave"]._lug_resync_full_activities_for_users(self)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        enforced = users.filtered(lambda u: u._lug_permission_is_enforced())
        if enforced:
            enforced._sync_lug_odoo_groups()
        users._sync_lug_visibility_policy()
        if any(
            {"lug_group_ids", "lug_user_permission_ids", "lug_data_scope", "user_role"}
            & set(vals)
            for vals in vals_list
        ):
            users._lug_clear_menu_cache()
        return users

    @api.model
    def _lug_backfill_time_off_role_from_groups(self):
        """Align lug_time_off_role with existing Time Off groups after upgrade."""
        users = self.sudo().search([])
        for user in users:
            role = self._lug_time_off_role_from_group_ids(user.group_ids.ids)
            if user.lug_time_off_role != role:
                super(
                    ResUsers,
                    user.with_context(skip_lug_sync=True, skip_role_apply=True),
                ).write({"lug_time_off_role": role})

    @api.model
    def _lug_cleanup_legacy_visibility_views(self):
        """Remove stale 'Phạm vi xem nhân viên' tab views from the database."""
        legacy = self.env["ir.ui.view"].search([("model", "=", "res.users")]).filtered(
            lambda view: 'name="employee_visibility"' in (view.arch_db or view.arch or "")
        )
        if legacy:
            legacy.unlink()
            self.env.registry.clear_cache()
