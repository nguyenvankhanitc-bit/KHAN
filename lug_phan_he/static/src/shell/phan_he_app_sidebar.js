/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { StoreNotifDialog } from "../shift/store_notif_popup";
import { GuideDocsDialog } from "../js/guide_docs_dialog";
import {
    SIDEBAR_DEFAULT,
    applySidebarLayout,
    clampWidth,
    goBack,
    isFullscreen,
    loadSidebarCollapsed,
    loadSidebarWidth,
    saveSidebarCollapsed,
    saveSidebarWidth,
    toggleFullscreen,
} from "../js/sidebar_controller";

export class PhanHeAppSidebar extends Component {
    static template = "lug_phan_he.PhanHeAppSidebar";
    static props = {
        activeKey: { type: String, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({
            erpOpen: true,
            width: loadSidebarWidth(),
            collapsed: loadSidebarCollapsed(),
            fullscreen: isFullscreen(),
            rights: {},
            showConfig: false,
            showSystemSettings: false,
            badges: { rosterCount: 0, missingCount: 0, notifyExpiring: 0, notifyLocked: 0, notifyReminder: 0, notifyNeed: 0, notifyInfo: 0 },
            visible: {
                internet: false,
                camera: false,
                attendance: false,
                server: false,
                linkq_nb: false,
                linkqNorth: false,
                linkqSouth: false,
                linkqDtt: false,
                linkqRoster: false,
                linkqRosterCreate: false,
                linkqShiftCode: false,
                linkqHrAdd: false,
                linkqHrList: false,
            },
        });
        applySidebarLayout(this.state.width, this.state.collapsed);

        onWillStart(async () => {
            await this.loadRights();
        });

        this._onFullscreenChange = () => {
            this.state.fullscreen = isFullscreen();
        };
        onMounted(() => {
            document.addEventListener("fullscreenchange", this._onFullscreenChange);
            document.addEventListener("webkitfullscreenchange", this._onFullscreenChange);
            applySidebarLayout(this.state.width, this.state.collapsed);
        });
        onWillUnmount(() => {
            this._stopResize();
            document.removeEventListener("fullscreenchange", this._onFullscreenChange);
            document.removeEventListener("webkitfullscreenchange", this._onFullscreenChange);
        });
    }

    get activeKey() {
        const raw = this.props.activeKey;
        if (raw == null || raw === "") {
            return "";
        }
        return String(raw).replace(/^['"]+|['"]+$/g, "");
    }

    get showLinkqPanel() {
        return [
            "dashboard",
            "store_dash",
            "today_shift",
            "north_schedule",
            "south_schedule",
            "dtt_schedule",
            "roster",
            "roster_new",
            "work_shift",
            "report",
            "missing",
            "lock_settings",
            "access",
            "audit_log",
            "employees",
            "employee_new",
        ].includes(this.activeKey);
    }

    get erpOpen() {
        return this.state.erpOpen;
    }

    get erpGroupActive() {
        return [
            "dashboard",
            "today_shift",
            "north_schedule",
            "south_schedule",
            "dtt_schedule",
            "roster",
            "roster_new",
            "work_shift",
            "employees",
            "employee_new",
        ].includes(this.activeKey);
    }

    isActive(key) {
        return this.activeKey === key;
    }

    canSee(code) {
        const right = this.state.rights[code];
        return Boolean(right && right.view);
    }

    menuCan(key) {
        const row = (this.state.rights.linkq_menus || {})[key];
        return Boolean(row && row.read);
    }

    menuCanCreate(key) {
        const row = (this.state.rights.linkq_menus || {})[key];
        return Boolean(row && row.create);
    }

    async loadRights() {
        try {
            const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
            this.state.rights = rights || {};
            this.state.visible = {
                internet: Boolean(rights?.internet?.view),
                camera: Boolean(rights?.camera?.view),
                attendance: Boolean(rights?.attendance?.view),
                server: Boolean(rights?.server?.view),
                linkq_nb: Boolean(rights?.linkq_nb?.view),
                linkqNorth: this.menuCan("schedule_north"),
                linkqSouth: this.menuCan("schedule_south"),
                linkqDtt: this.menuCan("schedule_dtt"),
                linkqRoster: this.menuCan("schedule_list") || this.menuCan("schedule_main"),
                linkqRosterCreate: this.menuCanCreate("schedule_add") || this.menuCan("schedule_add"),
                linkqShiftCode: this.menuCan("schedule_symbol") || this.menuCan("schedule_symbol_list"),
                linkqHrAdd: this.menuCan("hr_add") || this.menuCanCreate("hr_add"),
                linkqHrList: this.menuCan("hr_list") || this.menuCan("hr_group"),
            };
            this.state.showConfig = ["internet", "camera", "attendance", "server", "linkq_nb"].some(
                (code) => Boolean(rights?.[code]?.admin)
            );
            this.state.showSystemSettings =
                this.menuCan("system_group") || this.menuCan("system_lock") || this.menuCan("system_access");
            try {
                const stats = await this.orm.call("linkq.monthly.roster", "get_linkq_sidebar_stats", []);
                this.state.badges = {
                    rosterCount: stats?.roster_count || 0,
                    missingCount: stats?.missing_store_count || 0,
                    notifyExpiring: stats?.notify_expiring || 0,
                    notifyLocked: stats?.notify_locked || 0,
                    notifyReminder: stats?.notify_reminder || 0,
                    notifyNeed: stats?.notify_need || 0,
                    notifyInfo: stats?.notify_info || 0,
                };
            } catch {
                this.state.badges = {
                    rosterCount: 0,
                    missingCount: 0,
                    notifyExpiring: 0,
                    notifyLocked: 0,
                    notifyReminder: 0,
                    notifyNeed: 0,
                    notifyInfo: 0,
                };
            }
        } catch (error) {
            console.error(error);
            this.state.rights = {};
            this.state.showConfig = false;
            this.state.showSystemSettings = false;
            this.state.visible = {
                internet: false,
                camera: false,
                attendance: false,
                server: false,
                linkq_nb: false,
                linkqNorth: false,
                linkqSouth: false,
                linkqDtt: false,
                linkqRoster: false,
                linkqRosterCreate: false,
                linkqShiftCode: false,
                linkqHrAdd: false,
                linkqHrList: false,
            };
        }
    }

    toggleErp() {
        this.state.erpOpen = !this.erpOpen;
    }

    onBack() {
        goBack();
    }

    onToggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        saveSidebarCollapsed(this.state.collapsed);
        applySidebarLayout(this.state.width, this.state.collapsed);
    }

    onResizePointerDown(ev) {
        if (this.state.collapsed || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const aside = ev.currentTarget.closest("aside");
        const left = aside.getBoundingClientRect().left;
        document.documentElement.classList.add("o_phan_he_sidebar_resizing");

        this._onResizeMove = (moveEv) => {
            const width = clampWidth(moveEv.clientX - left);
            this.state.width = width;
            applySidebarLayout(width, false);
        };
        this._onResizeUp = () => this._stopResize();
        window.addEventListener("pointermove", this._onResizeMove);
        window.addEventListener("pointerup", this._onResizeUp);
        window.addEventListener("pointercancel", this._onResizeUp);
    }

    _stopResize() {
        if (this._onResizeMove) {
            window.removeEventListener("pointermove", this._onResizeMove);
            window.removeEventListener("pointerup", this._onResizeUp);
            window.removeEventListener("pointercancel", this._onResizeUp);
            this._onResizeMove = null;
            this._onResizeUp = null;
            saveSidebarWidth(this.state.width);
        }
        document.documentElement.classList.remove("o_phan_he_sidebar_resizing");
    }

    onResizeReset() {
        this.state.width = SIDEBAR_DEFAULT;
        saveSidebarWidth(SIDEBAR_DEFAULT);
        applySidebarLayout(SIDEBAR_DEFAULT, this.state.collapsed);
    }

    async onToggleFullscreen() {
        await toggleFullscreen();
        this.state.fullscreen = isFullscreen();
    }

    open(xmlid) {
        this.action.doAction(xmlid, { clearBreadcrumbs: true });
    }

    onHome() {
        this.open("lug_phan_he.action_phan_he_hub");
    }

    onInternet() {
        this.open("lug_phan_he.action_phan_he_dashboard");
    }

    onCamera() {
        this.open("lug_phan_he.action_phan_he_dashboard_camera");
    }

    onAttendance() {
        this.open("lug_phan_he.action_phan_he_dashboard_attendance");
    }

    onServer() {
        this.open("lug_phan_he.action_phan_he_dashboard_server");
    }

    onDashboard() {
        this.open("lug_phan_he.action_linkq_store_dashboard");
    }

    onStoreDashboard() {
        this.open("lug_phan_he.action_linkq_store_dashboard");
    }

    onNorthSchedule() {
        this.open("lug_phan_he.action_linkq_store_schedule_north");
    }

    onSouthSchedule() {
        this.open("lug_phan_he.action_linkq_store_schedule_south");
    }

    onDttSchedule() {
        this.open("lug_phan_he.action_linkq_shift_schedule_dtt");
    }

    onTodayShift() {
        this.open("lug_phan_he.action_linkq_today_shift");
    }

    onRoster() {
        this.action.doAction("lug_phan_he.action_linkq_monthly_roster", {
            clearBreadcrumbs: true,
            additionalContext: {
                search_default_group_by_store: 1,
                group_by: ["store_id"],
            },
        });
    }

    onRosterNew() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Thêm lịch ca",
            res_model: "linkq.monthly.roster",
            views: [[false, "form"]],
            target: "current",
            context: { form_view_initial_mode: "edit" },
        });
    }

    onWorkShift() {
        this.open("lug_phan_he.action_linkq_shift_code");
    }

    onEmployees() {
        this.open("lug_phan_he.action_linkq_employee_list");
    }

    onEmployeeNew() {
        this.open("lug_phan_he.action_linkq_employee_create");
    }

    onShiftReport() {
        this.open("lug_phan_he.action_linkq_shift_summary_report");
    }

    onMissingShifts() {
        this.onRoster();
    }

    onLockSettings() {
        this.open("lug_phan_he.action_linkq_roster_lock_settings");
    }

    onAccessRoles() {
        this.open("lug_phan_he.action_phan_he_module_access");
    }

    onAuditLog() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Nhật ký hệ thống (Audit Log)",
            res_model: "linkq.roster.lock.event",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    onOpenGuideDocuments() {
        this.dialog.add(GuideDocsDialog, {});
    }

    onNotifyGuide() {
        this.onOpenGuideDocuments();
    }

    onNotifyExpiring() {
        this.openNotificationPopup("expiring");
    }

    onNotifyReminder() {
        this.openNotificationPopup("reminder");
    }

    onNotifyLocked() {
        this.openNotificationPopup("locked");
    }

    onNotifyInfo() {
        this.openNotificationPopup("info");
    }

    openNotificationPopup(kind) {
        try {
            this.dialog.add(StoreNotifDialog, { kind: kind || "expiring" });
        } catch (error) {
            console.error(error);
            this.notification.add("Không mở được thông báo cửa hàng.", { type: "danger" });
        }
    }

    onProvider() {
        this.open("lug_phan_he.action_phan_he_provider");
    }

    onConfig() {
        this.open("lug_phan_he.action_phan_he_mien");
    }
}
