/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
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
        this.state = useState({
            erpOpen: true,
            width: loadSidebarWidth(),
            collapsed: loadSidebarCollapsed(),
            fullscreen: isFullscreen(),
            rights: {},
            showConfig: false,
            badges: { rosterCount: 0, missingCount: 0 },
            visible: {
                internet: false,
                camera: false,
                attendance: false,
                server: false,
                linkq_nb: false,
                linkq_hrm: false,
                linkqNorth: false,
                linkqSouth: false,
                linkqDtt: false,
                linkqRoster: false,
                linkqShiftCode: false,
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
            "north_schedule",
            "south_schedule",
            "dtt_schedule",
            "roster",
            "roster_new",
            "work_shift",
            "report",
            "missing",
        ].includes(this.activeKey);
    }

    get erpOpen() {
        return this.state.erpOpen;
    }

    get erpGroupActive() {
        return [
            "dashboard",
            "north_schedule",
            "south_schedule",
            "dtt_schedule",
            "roster",
            "roster_new",
            "work_shift",
        ].includes(this.activeKey);
    }

    isActive(key) {
        return this.activeKey === key;
    }

    canSee(code) {
        const right = this.state.rights[code];
        return Boolean(right && right.view);
    }

    async loadRights() {
        try {
            const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
            this.state.rights = rights || {};
            const menus = rights.linkq_menus || {};
            const manager = await user.hasGroup("lug_phan_he.group_phan_he_service_manager");
            const admin = await user.hasGroup("lug_phan_he.group_phan_he_admin");
            const settings = await user.hasGroup("base.group_system");
            this.state.visible = {
                internet: Boolean(rights?.internet?.view),
                camera: Boolean(rights?.camera?.view),
                attendance: Boolean(rights?.attendance?.view),
                server: Boolean(rights?.server?.view),
                linkq_nb: Boolean(rights?.linkq_nb?.view),
                linkq_hrm: Boolean(rights?.linkq_hrm?.view),
                linkqNorth: Boolean(
                    settings || admin || manager || (menus.schedule_north && menus.schedule_north.read)
                ),
                linkqSouth: Boolean(
                    settings || admin || manager || (menus.schedule_south && menus.schedule_south.read)
                ),
                linkqDtt: Boolean(
                    settings || admin || manager || (menus.schedule_dtt && menus.schedule_dtt.read)
                ),
                linkqRoster: Boolean(
                    settings || admin || manager || (menus.schedule_main && menus.schedule_main.read)
                ),
                linkqShiftCode: Boolean(
                    settings || admin || manager || (menus.schedule_symbol && menus.schedule_symbol.read)
                ),
            };
            this.state.showConfig =
                manager ||
                admin ||
                settings ||
                Object.values(this.state.rights).some((row) => row && row.admin);
            try {
                const stats = await this.orm.call("linkq.monthly.roster", "get_linkq_sidebar_stats", []);
                this.state.badges = {
                    rosterCount: stats?.roster_count || 0,
                    missingCount: stats?.missing_store_count || 0,
                };
            } catch {
                this.state.badges = { rosterCount: 0, missingCount: 0 };
            }
        } catch (error) {
            console.error(error);
            this.state.rights = {};
            this.state.showConfig = false;
            this.state.visible = {
                internet: false,
                camera: false,
                attendance: false,
                server: false,
                linkq_nb: false,
                linkq_hrm: false,
                linkqNorth: false,
                linkqSouth: false,
                linkqDtt: false,
                linkqRoster: false,
                linkqShiftCode: false,
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
        this.open("lug_phan_he.action_phan_he_dashboard_linkq_nb");
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

    onRoster() {
        this.open("lug_phan_he.action_linkq_monthly_roster");
    }

    onRosterNew() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Thêm lịch ca",
            res_model: "linkq.monthly.roster",
            views: [[false, "form"]],
            target: "current",
        });
    }

    onWorkShift() {
        this.open("lug_phan_he.action_linkq_shift_code");
    }

    onShiftReport() {
        this.open("lug_phan_he.action_phan_he_dashboard_linkq_nb");
    }

    onMissingShifts() {
        this.open("lug_phan_he.action_linkq_monthly_roster");
    }

    onHrm() {
        this.open("lug_phan_he.action_phan_he_dashboard_linkq_hrm");
    }

    onProvider() {
        this.open("lug_phan_he.action_phan_he_provider");
    }

    onConfig() {
        this.open("lug_phan_he.action_phan_he_mien");
    }
}
