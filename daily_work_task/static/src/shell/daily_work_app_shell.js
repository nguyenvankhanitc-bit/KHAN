/** @odoo-module **/

import { useBus, useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const SIDEBAR_WIDTH_KEY = "daily_work_sidebar_width";
const SIDEBAR_COLLAPSED_KEY = "daily_work_sidebar_collapsed";
const SIDEBAR_WIDTH_DEFAULT = 250;
const SIDEBAR_WIDTH_MIN = 180;
const SIDEBAR_WIDTH_MAX = 420;
const SIDEBAR_WIDTH_COLLAPSED = 68;

function readStoredSidebarWidth() {
    try {
        const raw = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
        const n = Number(raw);
        if (Number.isFinite(n)) {
            return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, Math.round(n)));
        }
    } catch (_e) {
        /* ignore */
    }
    return SIDEBAR_WIDTH_DEFAULT;
}

function readStoredSidebarCollapsed() {
    try {
        return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    } catch (_e) {
        return false;
    }
}

/**
 * Shell chung: topbar + sidebar trái (giống Báo cáo KPI admin).
 * Bọc nội dung các màn client action (Nhập công việc, …).
 */
export class DailyWorkAppShell extends Component {
    static template = "daily_work_task.DailyWorkAppShell";
    static props = {
        activeNav: { type: String, optional: true },
        slots: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this._sidebarResize = null;
        this.state = useState({
            loading: true,
            isManager: false,
            canAssign: false,
            canViewOthers: false,
            canViewChecklist: false,
            canSeePerformance: false,
            canAssignAdd: false,
            canAssignList: false,
            canAssignPersonnel: false,
            canAssignCategory: false,
            canAssignSection: false,
            assignAccess: {},
            userName: "",
            companyName: "",
            kpi: { today: 0, overdue: 0, upcoming: 0 },
            sidebarCollapsed: readStoredSidebarCollapsed(),
            sidebarWidth: readStoredSidebarWidth(),
            sidebarResizing: false,
            mobileNavOpen: false,
            isMobile: false,
            configOpen: false,
        });
        this._onMqChange = this._onMqChange.bind(this);
        useBus(this.env.bus, "daily_work_task:OPEN_WORK_NAV", () => {
            if (this.state.isMobile) {
                this.openMobileNav();
            } else {
                this.state.sidebarCollapsed = false;
            }
        });
        onWillStart(async () => {
            try {
                const ctx = await this.orm.call(
                    "daily.task.dashboard",
                    "get_nav_shell_context",
                    []
                );
                const opts = ctx?.options || {};
                this.state.isManager = Boolean(opts.is_manager);
                this.state.canAssign = Boolean(opts.can_assign);
                this.state.canViewOthers = Boolean(opts.can_view_others);
                this.state.canViewChecklist = Boolean(opts.can_view_checklist);
                this.state.canSeePerformance = Boolean(opts.can_see_performance);
                this.state.canAssignAdd = Boolean(opts.can_assign_add);
                this.state.canAssignList = Boolean(opts.can_assign_list);
                this.state.canAssignPersonnel = Boolean(opts.can_assign_personnel);
                this.state.canAssignCategory = Boolean(opts.can_assign_category);
                this.state.canAssignSection = Boolean(opts.can_assign_section);
                this.state.assignAccess = opts.assign_access || {};
                this.state.userName = opts.user_name || "";
                this.state.companyName = opts.company_name || "";
                this.state.kpi = ctx?.kpi || this.state.kpi;
            } catch (_e) {
                /* sidebar vẫn hiện, badge/ quyền mặc định */
            } finally {
                this.state.loading = false;
            }
        });
        onMounted(() => {
            this._mq = window.matchMedia("(max-width: 991.98px)");
            this._onMqChange();
            if (this._mq.addEventListener) {
                this._mq.addEventListener("change", this._onMqChange);
            } else if (this._mq.addListener) {
                this._mq.addListener(this._onMqChange);
            }
            this.env.bus.trigger("daily_work_task:DASHBOARD_SHELL", { active: true });
        });
        onWillUnmount(() => {
            this._stopSidebarResize();
            if (this._mq) {
                if (this._mq.removeEventListener) {
                    this._mq.removeEventListener("change", this._onMqChange);
                } else if (this._mq.removeListener) {
                    this._mq.removeListener(this._onMqChange);
                }
            }
            document.body.classList.remove("o_dwd_mobile_nav_lock");
            this.env.bus.trigger("daily_work_task:DASHBOARD_SHELL", { active: false });
        });
    }

    get activeNav() {
        return this.props.activeNav || "";
    }

    isActive(key) {
        return this.activeNav === key;
    }

    get kpi() {
        return this.state.kpi || {};
    }

    get reminderCount() {
        return (Number(this.kpi.overdue) || 0) + (Number(this.kpi.upcoming) || 0);
    }

    get shellClassName() {
        const parts = [];
        if (this.state.isMobile) {
            parts.push("is-mobile-layout");
        }
        if (this.state.mobileNavOpen) {
            parts.push("is-mobile-nav-open");
        }
        return parts.join(" ");
    }

    get sidebarClass() {
        let cls = "o_dwd_sidebar";
        if (this.state.sidebarCollapsed && !this.state.isMobile) {
            cls += " is-collapsed";
        }
        if (this.state.sidebarResizing) {
            cls += " is-resizing";
        }
        if (this.state.mobileNavOpen) {
            cls += " is-mobile-open";
        }
        return cls;
    }

    get sidebarStyle() {
        const width = this.state.sidebarCollapsed
            ? SIDEBAR_WIDTH_COLLAPSED
            : this.state.sidebarWidth;
        return `width: ${width}px; flex: 0 0 ${width}px;`;
    }

    _onMqChange() {
        const isMobile = !!(this._mq && this._mq.matches);
        this.state.isMobile = isMobile;
        if (!isMobile) {
            this.closeMobileNav();
        }
    }

    openMobileNav() {
        this.state.mobileNavOpen = true;
        this.state.sidebarCollapsed = false;
        document.body.classList.add("o_dwd_mobile_nav_lock");
    }

    closeMobileNav() {
        this.state.mobileNavOpen = false;
        document.body.classList.remove("o_dwd_mobile_nav_lock");
    }

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
        try {
            window.localStorage.setItem(
                SIDEBAR_COLLAPSED_KEY,
                this.state.sidebarCollapsed ? "1" : "0"
            );
        } catch (_e) {
            /* ignore */
        }
    }

    persistSidebarWidth(width) {
        try {
            window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
        } catch (_e) {
            /* ignore */
        }
    }

    resetSidebarWidth() {
        this.state.sidebarWidth = SIDEBAR_WIDTH_DEFAULT;
        this.persistSidebarWidth(SIDEBAR_WIDTH_DEFAULT);
    }

    onSidebarResizeStart(ev) {
        if (this.state.sidebarCollapsed || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        const startX = ev.clientX;
        const startWidth = this.state.sidebarWidth;
        this.state.sidebarResizing = true;
        document.body.classList.add("o_dwd_sidebar_resizing");
        const onMove = (e) => {
            const delta = e.clientX - startX;
            this.state.sidebarWidth = Math.min(
                SIDEBAR_WIDTH_MAX,
                Math.max(SIDEBAR_WIDTH_MIN, startWidth + delta)
            );
        };
        const onUp = () => {
            this.persistSidebarWidth(this.state.sidebarWidth);
            this._stopSidebarResize();
        };
        this._sidebarResize = { onMove, onUp };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onUp);
    }

    _stopSidebarResize() {
        if (this._sidebarResize) {
            window.removeEventListener("pointermove", this._sidebarResize.onMove);
            window.removeEventListener("pointerup", this._sidebarResize.onUp);
            window.removeEventListener("pointercancel", this._sidebarResize.onUp);
            this._sidebarResize = null;
        }
        this.state.sidebarResizing = false;
        document.body.classList.remove("o_dwd_sidebar_resizing");
    }

    async openNav(key) {
        if (key === "assign" && !this.state.canAssign) {
            this.notification.add(_t("Bạn không có quyền Giao việc."), { type: "warning" });
            return;
        }
        if ((key === "viewer" || key === "report") && !this.state.canViewOthers) {
            this.notification.add(_t("Bạn không có quyền xem công việc nhân viên khác."), {
                type: "warning",
            });
            return;
        }
        if (key === "team_checklist" && !this.state.canViewChecklist) {
            this.notification.add(_t("Bạn không có quyền xem Checklist CV nhân viên."), {
                type: "warning",
            });
            return;
        }
        if (key === this.activeNav) {
            this.closeMobileNav();
            if (key === "team_assign_add") {
                window.dispatchEvent(new CustomEvent("daily-work-open-assign-create"));
            }
            return;
        }
        this.closeMobileNav();
        const asPopup = this.state.isMobile;
        const map = {
            assign: "daily_work_assign",
            report: "daily_work_summary_report",
            overview: "daily_work_report_overview",
            performance: "daily_work_performance_report",
            calendar: "daily_work_calendar",
            notebook: "daily_work_notebook",
            work_note: "daily_work_note",
            employee_ws: "daily_work_employee_ws",
            viewer: "daily_work_viewer",
            team_checklist: "daily_work_team_checklist",
        };
        if (key === "team_report") {
            await this._doNavAction("daily_work_task.action_task_team_report", asPopup);
            return;
        }
        if (key === "team_assign" || key === "team_assign_list") {
            await this._doNavAction("daily_work_task.action_daily_work_assign_board", asPopup);
            return;
        }
        if (key === "personnel_work") {
            await this._doNavAction("daily_work_task.action_daily_work_personnel", asPopup);
            return;
        }
        if (key === "team_assign_add") {
            await this._doNavAction("daily_work_task.action_daily_work_assign_board_edit", asPopup);
            return;
        }
        if (key === "kpi") {
            if (!this.state.isManager) {
                this.notification.add(_t("Bạn không có quyền xem Báo cáo KPI."), {
                    type: "warning",
                });
                return;
            }
            await this._doNavAction("daily_work_task.action_daily_work_dashboard", asPopup);
            return;
        }
        if (key === "kanban") {
            await this._doNavAction("daily_work_task.action_daily_task_kanban", asPopup);
            return;
        }
        if (key === "today") {
            await this._doNavAction("daily_work_task.action_daily_work_today", asPopup);
            return;
        }
        if (key === "reminders") {
            await this._doNavAction("daily_work_task.action_daily_work_reminders", asPopup);
            return;
        }
        if (key === "overdue") {
            await this._doNavAction(
                {
                    type: "ir.actions.act_window",
                    name: "Công việc quá hạn",
                    res_model: "daily.task",
                    views: [
                        [false, "list"],
                        [false, "form"],
                    ],
                    domain: [["is_overdue", "=", true]],
                    target: asPopup ? "new" : "current",
                },
                asPopup
            );
            return;
        }
        if (key === "send_mail") {
            await this._doNavAction("daily_work_task.action_daily_task_send_overdue", asPopup);
            return;
        }
        if (key === "team") {
            await this._doNavAction("daily_work_task.action_daily_task_team", asPopup);
            return;
        }
        if (key === "work_group" || key === "config") {
            await this._doNavAction("daily_work_task.action_daily_work_category_board", asPopup);
            return;
        }
        if (key === "recurring") {
            await this._doNavAction("daily_work_task.action_daily_task_recurring", asPopup);
            return;
        }
        if (key === "employees") {
            await this._doNavAction("daily_work_task.action_daily_task_employee", asPopup);
            return;
        }
        if (key === "access") {
            await this._doNavAction("daily_work_task.action_daily_task_access", asPopup);
            return;
        }
        if (key === "assign_access") {
            await this._doNavAction(
                "daily_work_task.action_daily_task_assign_access_matrix",
                asPopup
            );
            return;
        }
        if (key === "report_access") {
            await this._doNavAction("daily_work_task.action_daily_task_report_access", asPopup);
            return;
        }
        if (key === "performance_access") {
            await this._doNavAction(
                "daily_work_task.action_daily_task_performance_access",
                asPopup
            );
            return;
        }
        const tag = map[key];
        if (tag) {
            await this._doNavAction(
                {
                    type: "ir.actions.client",
                    tag,
                    target: asPopup ? "new" : "current",
                },
                asPopup
            );
        } else {
            this.notification.add(_t("Mục này sẽ bổ sung sau."), { type: "info" });
        }
    }

    async _doNavAction(action, asPopup) {
        if (typeof action === "string") {
            if (asPopup) {
                try {
                    const loaded = await this.action.loadAction(action);
                    await this.action.doAction({ ...loaded, target: "new" });
                    return;
                } catch (_e) {
                    /* fallback */
                }
            }
            await this.action.doAction(action);
            return;
        }
        await this.action.doAction(action);
    }
}
