/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const SERVICE_APPS = [
    {
        code: "internet",
        name: "Dịch vụ Internet",
        icon: "/lug_phan_he/static/description/icon_hub_internet.png",
        action: "lug_phan_he.action_phan_he_dashboard",
        enabled: true,
    },
    {
        code: "camera",
        name: "Dịch vụ Camera",
        icon: "/lug_phan_he/static/description/icon_hub_camera.png",
        action: "lug_phan_he.action_phan_he_dashboard_camera",
        enabled: true,
    },
    {
        code: "attendance",
        name: "Máy chấm công",
        icon: "/lug_phan_he/static/description/icon_hub_attendance.png",
        action: "lug_phan_he.action_phan_he_dashboard_attendance",
        enabled: true,
    },
    {
        code: "server",
        name: "Máy chủ & Cloud",
        icon: "/lug_phan_he/static/description/icon_hub_server.png",
        action: "lug_phan_he.action_phan_he_dashboard_server",
        enabled: true,
    },
    {
        code: "linkq_nb",
        name: "LinkQ ERP",
        icon: "/lug_phan_he/static/description/icon_hub_erp.png",
        action: "lug_phan_he.action_phan_he_dashboard_linkq_nb",
        enabled: true,
    },
    {
        code: "linkq_hrm",
        name: "LinkQ HRM",
        icon: "/lug_phan_he/static/description/icon_hub_hrm.png",
        action: "lug_phan_he.action_phan_he_dashboard_linkq_hrm",
        enabled: true,
    },
];

const CONFIG_ITEMS = [
    {
        code: "provider",
        name: "Nhà cung cấp",
        fa: "fa-building",
        action: "lug_phan_he.action_phan_he_provider",
    },
    {
        code: "config",
        name: "Cấu hình chung",
        fa: "fa-cog",
        action: "lug_phan_he.action_phan_he_mien",
    },
    {
        code: "access",
        name: "Phân quyền",
        fa: "fa-key",
        action: "lug_phan_he.action_phan_he_module_access",
    },
];

export class PhanHeHub extends Component {
    static template = "lug_phan_he.PhanHeHub";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.configItems = CONFIG_ITEMS;
        this.state = useState({
            query: "",
            activeNav: "home",
            sidebarCollapsed: false,
            apps: SERVICE_APPS.filter((app) => app.enabled),
            rights: {},
        });
        onWillStart(async () => {
            await this.loadRights();
        });
    }

    async loadRights() {
        try {
            const rights = await this.orm.call(
                "phan.he.module.access",
                "get_user_module_rights",
                []
            );
            this.state.rights = rights || {};
            this.state.apps = SERVICE_APPS.filter((app) => {
                if (!app.enabled) {
                    return false;
                }
                const right = this.state.rights[app.code];
                return !right || right.view;
            });
        } catch (error) {
            console.error(error);
            this.state.apps = SERVICE_APPS.filter((app) => app.enabled);
        }
    }

    get filteredApps() {
        const q = (this.state.query || "").trim().toLowerCase();
        const apps = this.state.apps || [];
        if (!q) {
            return apps;
        }
        return apps.filter((app) => (app.name || "").toLowerCase().includes(q));
    }

    onSearch(ev) {
        this.state.query = ev.target.value;
    }

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
    }

    async goToAppCenter() {
        try {
            await this.action.doAction("lug_app_center.action_lug_app_center", {
                clearBreadcrumbs: true,
            });
        } catch (error) {
            console.error(error);
            // Fallback: về home Odoo
            window.location.href = "/odoo";
        }
    }

    setHome() {
        this.state.activeNav = "home";
    }

    async openConfig(item) {
        if (!item?.action) {
            return;
        }
        this.state.activeNav = item.code;
        try {
            await this.action.doAction(item.action, { clearBreadcrumbs: false });
        } catch (error) {
            console.error(error);
            const msg =
                error?.data?.message ||
                error?.message ||
                "Không mở được cấu hình.";
            this.notification.add(msg, { type: "danger" });
        }
    }

    async openService(app) {
        if (!app?.action) {
            return;
        }
        const right = this.state.rights[app.code];
        if (right && !right.view) {
            this.notification.add("Bạn không có quyền xem phân hệ này.", { type: "warning" });
            return;
        }
        this.state.activeNav = app.code;
        try {
            await this.action.doAction(app.action);
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không mở được dịch vụ.",
                { type: "danger" }
            );
        }
    }
}

registry.category("actions").add("phan_he_hub", PhanHeHub);
