/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
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
    };

    setup() {
        this.action = useService("action");
        this.state = useState({
            erpOpen: true,
            width: loadSidebarWidth(),
            collapsed: loadSidebarCollapsed(),
            fullscreen: isFullscreen(),
        });
        applySidebarLayout(this.state.width, this.state.collapsed);

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
        return this.props.activeKey || "";
    }

    get erpOpen() {
        return this.state.erpOpen;
    }

    isActive(key) {
        return this.activeKey === key;
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

    onWorkShift() {
        this.open("lug_phan_he.action_linkq_shift_code");
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
