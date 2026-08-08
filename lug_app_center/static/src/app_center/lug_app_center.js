/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { user } from "@web/core/user";

const SELF_APP_XMLIDS = new Set([
    "lug_app_center.menu_lug_app_center_root",
]);

const SIDEBAR_ICON_FALLBACK = "fa-th-large";
const DEFAULT_APP_ICON = "/web/static/img/default_icon_app.png";

/** Map common Odoo app xmlids / names to Font Awesome icons for the sidebar. */
const SIDEBAR_ICONS = {
    "mail.menu_root_discuss": "fa-comments",
    "calendar.mail_menu_calendar": "fa-calendar",
    "hr.menu_hr_root": "fa-users",
    "hr_holidays.menu_hr_holidays_root": "fa-plane",
    "project.menu_main_pm": "fa-folder-open",
    "project_todo.menu_todo_todos": "fa-check-square-o",
    "daily_work_task.menu_daily_work_root": "fa-clipboard",
    "lug_task_assignment.menu_lug_task_root": "fa-tasks",
    "fleet.menu_root": "fa-truck",
    "stock.menu_stock_root": "fa-cubes",
    "lug_eam.menu_eam_root": "fa-building",
    "maintenance.menu_maintenance_title": "fa-wrench",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root": "fa-bar-chart",
    "base.menu_administration": "fa-cog",
    "account.menu_finance": "fa-money",
    "purchase.menu_purchase_root": "fa-shopping-cart",
    "crm.crm_menu_root": "fa-handshake-o",
    "point_of_sale.menu_point_root": "fa-shopping-basket",
    "lug_email_account.menu_lug_email_root": "fa-envelope",
    "lug_phan_he.menu_phan_he_root": "fa-th-large",
};

export class LugAppCenter extends Component {
    static template = "lug_app_center.LugAppCenter";
    static components = { Dropdown, DropdownItem };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.action = useService("action");
        this.notification = useService("notification");
        let sidebarCollapsed = false;
        try {
            sidebarCollapsed = window.localStorage.getItem("lug_app_center_sidebar_collapsed") === "1";
        } catch (_e) {
            sidebarCollapsed = false;
        }
        this.state = useState({
            loading: true,
            query: "",
            sidebarCollapsed,
            activeNav: "home",
            companyName: "",
            companySlogan: "",
            companyWebsite: "",
            companyAddress: "",
            companyLogoUrl: "/lug_app_center/static/src/img/sataco_logo.png",
            userName: "",
            userLogin: "",
            userEmail: "",
            userPhone: "",
            userRole: "",
            userInitial: "U",
            avatarUrl: false,
            welcome: "",
            greeting: {
                headline: "",
                today_label: "",
                today_label_full: "",
                today_count: 0,
                overdue_count: 0,
                has_task_module: false,
                primary_line: "",
                tip_line: "",
                show_overdue: false,
            },
            apps: [],
        });
        onWillStart(async () => {
            await this.loadPortal();
        });
    }

    _applyPortalData(data) {
        this.state.companyName = data.company_name || "";
        this.state.companySlogan = data.company_slogan || "";
        this.state.companyWebsite = data.company_website || "";
        this.state.companyAddress = data.company_address || "";
        this.state.companyLogoUrl =
            data.company_logo_url || "/lug_app_center/static/src/img/sataco_logo.png";
        this.state.userName = data.user_name || "";
        this.state.userLogin = data.user_login || "";
        this.state.userEmail = data.user_email || "";
        this.state.userPhone = data.user_phone || "";
        this.state.userRole = data.user_role || "";
        this.state.userInitial = data.user_initial || "U";
        this.state.avatarUrl = data.avatar_url || false;
        this.state.welcome = data.welcome || "";
        const g = data.greeting || {};
        this.state.greeting = {
            headline: g.headline || data.welcome || "",
            today_label: g.today_label || "",
            today_label_full: g.today_label_full || g.today_label || "",
            today_count: Number(g.today_count) || 0,
            overdue_count: Number(g.overdue_count) || 0,
            has_task_module: Boolean(g.has_task_module),
            primary_line: g.primary_line || "",
            tip_line: g.tip_line || "",
            show_overdue: Boolean(g.show_overdue),
        };
    }

    async loadPortal() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("lug.app.center", "get_portal_data", []);
            this._applyPortalData(data);
            this.state.apps = this._collectInstalledApps();
        } finally {
            this.state.loading = false;
        }
    }

    async refreshGreeting() {
        try {
            const data = await this.orm.call("lug.app.center", "get_portal_data", []);
            this._applyPortalData(data);
        } catch (_e) {
            /* ignore — giữ greeting cũ */
        }
    }

    /**
     * Resolve app icon for the grid.
     * Prefer known static icons (bypass stale webIconData session cache).
     */
    _resolveAppIcon(app) {
        const STATIC_APP_ICONS = {
            "lug_phan_he.menu_phan_he_root":
                "/lug_phan_he/static/description/icon.png?v=phanhe63",
        };
        if (app.xmlid && STATIC_APP_ICONS[app.xmlid]) {
            return { type: "img", src: STATIC_APP_ICONS[app.xmlid] };
        }

        const webIcon = app.webIcon;
        if (typeof webIcon === "string" && webIcon.includes(",")) {
            const parts = webIcon.split(",").map((p) => p.trim());
            if (parts.length === 2) {
                const [moduleName, iconPath] = parts;
                if (moduleName && iconPath && !moduleName.startsWith("fa") && !iconPath.startsWith("#")) {
                    return {
                        type: "img",
                        src: `/${moduleName}/${iconPath}`,
                    };
                }
            }
            if (parts.length >= 3) {
                return {
                    type: "fa",
                    iconClass: parts[0] || "fa fa-th-large",
                    color: parts[1] || "#FFFFFF",
                    backgroundColor: parts[2] || "#714B67",
                };
            }
        }
        if (webIcon && typeof webIcon === "object") {
            return {
                type: "fa",
                iconClass: webIcon.iconClass || "fa fa-th-large",
                color: webIcon.color || "#FFFFFF",
                backgroundColor: webIcon.backgroundColor || "#714B67",
            };
        }

        const rawData = app.webIconData || "";
        const hasRealImage =
            rawData &&
            rawData !== DEFAULT_APP_ICON &&
            !rawData.includes("default_icon_app.png");

        if (hasRealImage) {
            if (rawData.startsWith("data:image") || rawData.startsWith("/")) {
                return { type: "img", src: rawData };
            }
            const mime = app.webIconDataMimetype || "image/png";
            return {
                type: "img",
                src: `data:${mime};base64,${String(rawData).replace(/\s/g, "")}`,
            };
        }

        return { type: "img", src: DEFAULT_APP_ICON };
    }

    /**
     * All root apps visible to the current user (same source as Odoo Home Menu).
     */
    _collectInstalledApps() {
        const apps = this.menu.getApps() || [];
        return apps
            .filter((app) => app && app.id && !SELF_APP_XMLIDS.has(app.xmlid))
            .filter((app) => app.actionID)
            .map((app) => {
                const resolved = this._resolveAppIcon(app);
                return {
                    id: app.id,
                    key: `menu_${app.id}`,
                    name: app.name,
                    xmlid: app.xmlid || "",
                    actionID: app.actionID,
                    iconType: resolved.type,
                    webIconData: resolved.type === "img" ? resolved.src : DEFAULT_APP_ICON,
                    faIcon: resolved.type === "fa" ? resolved : null,
                    icon: SIDEBAR_ICONS[app.xmlid] || SIDEBAR_ICON_FALLBACK,
                    sidebar_label: app.name,
                };
            });
    }

    get filteredApps() {
        const q = (this.state.query || "").trim().toLowerCase();
        if (!q) {
            return this.state.apps;
        }
        return this.state.apps.filter((app) => (app.name || "").toLowerCase().includes(q));
    }

    onSearch(ev) {
        this.state.query = ev.target.value;
    }

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
        try {
            window.localStorage.setItem(
                "lug_app_center_sidebar_collapsed",
                this.state.sidebarCollapsed ? "1" : "0"
            );
        } catch (_e) {
            /* ignore */
        }
    }

    setHome() {
        this.state.activeNav = "home";
        this.refreshGreeting();
    }

    async onNavClick(app) {
        this.state.activeNav = app.key;
        await this.openApp(app);
    }

    /**
     * Open exactly like the Odoo app switcher / home menu.
     */
    async openApp(app) {
        if (!app?.id || !app?.actionID) {
            this.notification.add("Không mở được ứng dụng.", { type: "warning" });
            return;
        }
        try {
            await this.menu.selectMenu(app.id);
        } catch (error) {
            console.error(error);
            this.notification.add("Không mở được ứng dụng.", { type: "danger" });
        }
    }

    async openPreferences() {
        try {
            const actionDescription = await this.orm.call("res.users", "action_get");
            actionDescription.res_id = user.userId;
            await this.action.doAction(actionDescription);
        } catch (error) {
            console.error(error);
            this.notification.add("Không mở được thông tin tài khoản.", { type: "danger" });
        }
    }

    logout() {
        window.location.href = "/web/session/logout";
    }
}

registry.category("actions").add("lug_app_center", LugAppCenter);
