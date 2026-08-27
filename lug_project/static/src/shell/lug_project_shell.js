/** @odoo-module **/
/* lps-ui: gantt-compact-v5 trash-label-thung-rac-v2 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import {
    Component,
    onError,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
    useSubEnv,
} from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { View, getDefaultConfig } from "@web/views/view";
import { LugProjectList } from "../list/lug_project_list";

const SIDEBAR_WIDTH_KEY = "lug_project_sidebar_width";
const SIDEBAR_COLLAPSED_KEY = "lug_project_sidebar_collapsed";
const SIDEBAR_WIDTH_DEFAULT = 248;
const SIDEBAR_WIDTH_MIN = 200;
const SIDEBAR_WIDTH_MAX = 420;
const SIDEBAR_WIDTH_COLLAPSED = 72;
const RAIL_WIDTH_KEY = "lug_project_rail_width";
const RAIL_COLLAPSED_KEY = "lug_project_rail_collapsed";
const RAIL_WIDTH_DEFAULT = 196;
const RAIL_WIDTH_MIN = 72;
const RAIL_WIDTH_MAX = 280;

const RAIL_ORDER = [
    { xmlid: "mail.menu_root_discuss", icon: "fa-comments" },
    { xmlid: "project_todo.menu_todo_todos", icon: "fa-check-square-o" },
    { xmlid: "daily_work_task.menu_daily_work_root", icon: "fa-clipboard" },
    { xmlid: "spreadsheet_dashboard.spreadsheet_dashboard_menu_root", icon: "fa-bar-chart" },
    { xmlid: "hr.menu_hr_root", icon: "fa-users" },
    { xmlid: "hr_holidays.menu_hr_holidays_root", icon: "fa-plane" },
];

const NAV_SECTIONS = [
    {
        key: "project",
        label: "DỰ ÁN",
        emoji: "",
        items: [
            { code: "intake", label: "Nhập dự án mới", icon: "fa-plus", cta: true },
            { code: "list", label: "Danh sách dự án", icon: "fa-folder-open-o", badgeKey: "list" },
            { code: "track", label: "Theo dõi dự án", icon: "fa-eye" },
            { code: "gantt", label: "Gantt Chart", icon: "fa-align-left" },
            { code: "assign", label: "Phân công nhân sự", icon: "fa-users" },
            { code: "overdue", label: "Dự án trễ hạn", icon: "fa-exclamation-triangle", badgeKey: "overdue" },
            { code: "milestones", label: "Nhắc mốc dự án", icon: "fa-bell-o" },
        ],
    },
    {
        key: "report",
        label: "BÁO CÁO DỰ ÁN",
        emoji: "",
        items: [
            { code: "report_all", label: "Báo cáo tổng thể", icon: "fa-bar-chart" },
            { code: "people", label: "Báo cáo nhân sự", icon: "fa-user" },
            { code: "perf", label: "Báo cáo hiệu suất", icon: "fa-line-chart" },
            { code: "kpi", label: "Báo cáo KPI Dự án", icon: "fa-trophy" },
        ],
    },
    {
        key: "config",
        label: "CẤU HÌNH",
        emoji: "",
        items: [
            { code: "cfg_phase", label: "Giai đoạn", icon: "fa-sitemap" },
            { code: "archived", label: "Thùng rác", icon: "fa-trash", badgeKey: "archived" },
            { code: "types", label: "Loại dự án", icon: "fa-tags" },
            { code: "cfg_status", label: "Trạng thái", icon: "fa-flag-o" },
            { code: "cfg_priority", label: "Mức độ ưu tiên", icon: "fa-signal" },
            { code: "cfg_access", label: "Phân quyền", icon: "fa-lock" },
        ],
    },
    {
        key: "utils",
        label: "TIỆN ÍCH",
        emoji: "",
        items: [{ code: "contacts", label: "Danh bạ", icon: "fa-book" }],
    },
];

const TOP_NAV = [
    { code: "kpi", label: "Tổng quan" },
    { code: "list", label: "Dự án" },
    { code: "assign", label: "Nhiệm vụ" },
    { code: "report_all", label: "Báo cáo" },
    { code: "cfg_phase", label: "Cấu hình" },
];

const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);

function topNavActive(code, active) {
    if (code === "list") {
        return ["list", "intake", "track", "gantt", "overdue", "milestones", "templates"].includes(active);
    }
    if (code === "cfg_phase") {
        return ["cfg_phase", "archived", "types", "cfg_status", "cfg_priority", "cfg_access"].includes(active);
    }
    if (code === "assign") {
        return ["assign", "people"].includes(active);
    }
    if (code === "report_all") {
        return ["report_all", "perf", "kpi"].includes(active);
    }
    return active === code;
}

const STATUS_PIE_COLORS = ["#16a34a", "#f59e0b", "#dc2626", "#64748b"];

const PROJECT_CHIP_COLORS = [
    { bg: "#dbeafe", bd: "#2563eb", fg: "#1e3a8a" },
    { bg: "#dcfce7", bd: "#16a34a", fg: "#14532d" },
    { bg: "#fef3c7", bd: "#d97706", fg: "#92400e" },
    { bg: "#fce7f3", bd: "#db2777", fg: "#9d174d" },
    { bg: "#ede9fe", bd: "#7c3aed", fg: "#5b21b6" },
    { bg: "#cffafe", bd: "#0891b2", fg: "#155e75" },
    { bg: "#ffedd5", bd: "#ea580c", fg: "#9a3412" },
    { bg: "#e0e7ff", bd: "#4f46e5", fg: "#3730a3" },
    { bg: "#f1f5f9", bd: "#475569", fg: "#0f172a" },
    { bg: "#fee2e2", bd: "#dc2626", fg: "#991b1b" },
];

function readStoredSidebarWidth() {
    try {
        const n = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
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

function readStoredRailWidth() {
    try {
        const n = Number(window.localStorage.getItem(RAIL_WIDTH_KEY));
        if (Number.isFinite(n)) {
            return Math.min(RAIL_WIDTH_MAX, Math.max(RAIL_WIDTH_MIN, Math.round(n)));
        }
    } catch (_e) {
        /* ignore */
    }
    return RAIL_WIDTH_DEFAULT;
}

function readStoredRailCollapsed() {
    try {
        return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
    } catch (_e) {
        return false;
    }
}

function emptyDashboard() {
    return {
        kpis: [],
        months: [],
        upcoming: [],
        personnel: [],
        activities: [],
        overdue_count: 0,
        project_count: 0,
        archived_count: 0,
        featured_title: "Báo cáo KPI dự án",
        status: [],
        status_pie: [],
        gantt: [],
        gantt_axis: [],
        gantt_today: 0,
        gantt_cal: { months: [], days: [], count: 0, today: 0, day_px: 22 },
        progress: [],
        at_risk_tasks: [],
        heatmap: { months: [], rows: [] },
        filter_projects: [],
        filter_project_id: false,
        staff_load: [],
        cost_top: [],
        perf: [],
        project_types: [],
        period: "month",
        type_id: false,
    };
}

export class LugProjectShell extends Component {
    static template = "lug_project.LugProjectShell";
    static components = { View, LugProjectList };
    static props = { ...standardActionServiceProps, "*": true };
    static path = "project";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.navSections = NAV_SECTIONS;
        this.navItems = NAV_ITEMS;
        this.topNavItems = TOP_NAV;
        this._sidebarResize = null;
        this.staffChart = null;
        this.trendChart = null;
        this.costChart = null;
        this.perfChart = null;
        this.staffRef = useRef("staffChart");
        this.trendRef = useRef("trendChart");
        this.costRef = useRef("costChart");
        this.perfRef = useRef("perfChart");
        this.overviewScrollRef = useRef("overviewScroll");
        this.state = useState({
            active: "kpi",
            query: "",
            viewError: "",
            loading: true,
            sidebarCollapsed: readStoredSidebarCollapsed(),
            sidebarWidth: readStoredSidebarWidth(),
            sidebarResizing: false,
            railWidth: readStoredRailWidth(),
            railCollapsed: readStoredRailCollapsed(),
            railResizing: false,
            apps: [],
            companyName: "CÔNG TY TNHH SÁNG TÂM",
            companyAddress: "",
            companyLogoUrl: "/lug_app_center/static/src/img/sataco_logo.png",
            userName: "",
            userRole: "Người dùng",
            userInitial: "U",
            avatarUrl: false,
            greeting: {
                headline: "Xin chào!",
                today_label_full: "",
                primary_line: "",
            },
            dashboard: emptyDashboard(),
            ganttCollapsed: {},
            filterProjectId: 0,
            filterOpen: false,
            filterQuery: "",
            overviewPeriod: "month",
            overviewTypeId: 0,
            overviewExporting: false,
        });
        useSubEnv({ config: getDefaultConfig() });
        onMounted(() => {
            document.body.classList.add("o_lug_shell_active");
            this._injectOverviewScrollCss();
            this._lockOverviewScrollPane();
        });
        onWillUnmount(() => {
            document.body.classList.remove("o_lug_shell_active");
        });
        onWillStart(async () => {
            try {
                await this.loadShellData();
            } catch (error) {
                console.error(error);
                this.state.dashboard = emptyDashboard();
                this.state.loading = false;
            }
        });
        onError((error) => {
            console.error(error);
            this.state.viewError = error?.message || String(error);
            try {
                document.body.classList.remove("o_lug_shell_active");
            } catch (_e) {
                // ignore
            }
        });
        useEffect(
            () => {
                this._lockOverviewScrollPane();
                const timer = setTimeout(() => {
                    this.renderCharts().catch((error) => console.error(error));
                }, 80);
                return () => {
                    clearTimeout(timer);
                    this.destroyCharts();
                };
            },
            () => [
                this.state.active,
                this.state.loading,
                this.state.overviewPeriod,
                this.state.overviewTypeId,
                (this.state.dashboard.kpis || []).length,
                (this.state.dashboard.staff_load || []).length,
                (this.state.dashboard.months || []).length,
                (this.state.dashboard.cost_top || []).length,
                (this.state.dashboard.perf || []).length,
            ]
        );
        useEffect(
            () => {
                const close = () => {
                    if (this.state.filterOpen) {
                        this.state.filterOpen = false;
                    }
                };
                document.addEventListener("pointerdown", close);
                return () => document.removeEventListener("pointerdown", close);
            },
            () => [this.state.filterOpen]
        );
        onWillUnmount(() => {
            this._stopSidebarResize();
            this.destroyCharts();
        });
    }

    get activeItem() {
        return this.navItems.find((item) => item.code === this.state.active) || this.navItems[0];
    }

    get sidebarClass() {
        let cls = "o_lps_sidebar";
        if (this.state.sidebarCollapsed) {
            cls += " collapsed";
        }
        if (this.state.sidebarResizing) {
            cls += " is-resizing";
        }
        return cls;
    }

    get sidebarStyle() {
        const width = this.state.sidebarCollapsed
            ? SIDEBAR_WIDTH_COLLAPSED
            : this.state.sidebarWidth;
        return `width: ${width}px;position:relative;overflow:visible;`;
    }

    get isHome() {
        return this.state.active === "kpi";
    }

    get overviewTypes() {
        return this.state.dashboard.project_types || [];
    }

    get overviewKpis() {
        return (this.state.dashboard.kpis || []).map((kpi) => {
            const tone = kpi.tone || "blue";
            const alert = kpi.key === "overdue" && Number(kpi.value) > 0;
            return {
                ...kpi,
                hint: kpi.hint || "",
                cardClass: `o_lps_ov_kpi tone-${tone}${alert ? " is-alert" : ""}`,
                iconClass: `fa ${kpi.icon || "fa-folder-open"}`,
            };
        });
    }

    get overviewStaff() {
        return this.state.dashboard.staff_load || [];
    }

    get overviewMonths() {
        return this.state.dashboard.months || [];
    }

    get overviewCosts() {
        return this.state.dashboard.cost_top || [];
    }

    get overviewPerf() {
        return this.state.dashboard.perf || [];
    }

    get isProjectList() {
        return ["list", "archived", "overdue"].includes(this.state.active);
    }

    get isGantt() {
        return this.state.active === "gantt";
    }

    get kpiStatus() {
        return this.state.dashboard.status || [];
    }

    get kpiStatusTotal() {
        const rows = this.kpiStatus;
        const sum = rows.reduce((acc, row) => acc + (Number(row.pct) || 0), 0);
        return sum ? sum.toFixed(1) : "100.0";
    }

    get shellClass() {
        let cls = "o_lug_project_shell o_action";
        if (this.state.sidebarCollapsed) {
            cls += " is-collapsed";
        }
        if (this.state.railCollapsed) {
            cls += " rail-collapsed";
        }
        if (this.state.railResizing || this.state.sidebarResizing) {
            cls += " is-resizing";
        }
        if (this.state.railWidth < 100 || this.state.railCollapsed) {
            cls += " rail-narrow";
        }
        if (this.isProjectList) {
            cls += " is-plist-mode";
        }
        return cls;
    }

    isTopNavActive(code) {
        return topNavActive(code, this.state.active);
    }

    get railClass() {
        let cls = "o_lps_rail";
        if (this.state.railWidth < 100 || this.state.railCollapsed) {
            cls += " collapsed";
        }
        if (this.state.railResizing) {
            cls += " is-resizing";
        }
        return cls;
    }

    get railStyle() {
        if (this.state.railCollapsed) {
            return "width:0;min-width:0;padding:0;border:0;overflow:hidden;position:relative;";
        }
        return `width: ${this.state.railWidth}px;position:relative;overflow:visible;`;
    }

    get railResizerClass() {
        let cls = "o_lps_ruler o_lps_ruler--rail";
        if (this.state.railResizing) {
            cls += " active";
        }
        if (this.state.railCollapsed) {
            cls += " is-collapsed";
        }
        return cls;
    }

    get sidebarResizerClass() {
        let cls = "o_lps_ruler o_lps_ruler--side";
        if (this.state.sidebarResizing) {
            cls += " active";
        }
        if (this.state.sidebarCollapsed) {
            cls += " is-collapsed";
        }
        return cls;
    }

    get statusPie() {
        return this.state.dashboard.status_pie || [];
    }

    get ganttCal() {
        return (
            this.state.dashboard.gantt_cal || {
                months: [],
                days: [],
                count: 0,
                today: 0,
                day_px: 22,
            }
        );
    }

    get ganttCalWidth() {
        return "100%";
    }

    get ganttCalStyle() {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        return `width:100%;--lps-gantt-days:${count}`;
    }

    get ganttVisibleRows() {
        const collapsed = this.state.ganttCollapsed || {};
        const rows = this.state.dashboard.gantt || [];
        const out = [];
        let index = 0;
        for (const row of rows) {
            if (row.kind !== "project" && collapsed[row.project_id]) {
                continue;
            }
            index += 1;
            out.push({ ...row, index, ms: row.ms || [] });
        }
        return out;
    }

    get ganttTodayLeft() {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        const today = Number(this.ganttCal.today) || 0;
        return `${((today + 0.5) * 100) / count}%`;
    }

    get filterProjectLabel() {
        if (!this.state.filterProjectId) {
            return "[All Projects]";
        }
        const rows = this.state.dashboard.filter_projects || [];
        const match = rows.find((row) => row.id === this.state.filterProjectId);
        return (match && match.name) || "[All Projects]";
    }

    get visibleFilterProjects() {
        const q = (this.state.filterQuery || "").trim().toLowerCase();
        const rows = this.state.dashboard.filter_projects || [];
        if (!q) {
            return rows;
        }
        return rows.filter((row) => (row.name || "").toLowerCase().includes(q));
    }

    get overdueCount() {
        return Number(this.state.dashboard.overdue_count) || 0;
    }

    get projectCount() {
        return Number(this.state.dashboard.project_count) || 0;
    }

    get archivedCount() {
        return Number(this.state.dashboard.archived_count) || 0;
    }

    get filteredUpcoming() {
        const q = (this.state.query || "").trim().toLowerCase();
        const rows = this.state.dashboard.upcoming || [];
        if (!q) {
            return rows;
        }
        return rows.filter(
            (row) =>
                (row.name || "").toLowerCase().includes(q) ||
                (row.code || "").toLowerCase().includes(q)
        );
    }

    get filteredActivities() {
        const q = (this.state.query || "").trim().toLowerCase();
        const rows = this.state.dashboard.activities || [];
        if (!q) {
            return rows;
        }
        return rows.filter(
            (row) =>
                (row.text || "").toLowerCase().includes(q) ||
                (row.project || "").toLowerCase().includes(q) ||
                (row.author || "").toLowerCase().includes(q)
        );
    }

    get viewProps() {
        const projectDomain = [["is_template", "=", false]];
        const taskDomain = [
            ["has_template_ancestor", "=", false],
            ["has_project_template", "=", false],
        ];
        const map = {
            intake: {
                resModel: "project.project",
                type: "form",
                resId: false,
                resIds: [],
                domain: [["id", "=", 0]],
                context: {
                    default_allow_milestones: true,
                    form_view_ref: "lug_project.view_project_intake_form",
                    default_type: "form",
                },
                onSave: () => this.afterIntakeSave(),
            },
            list: {
                resModel: "project.project",
                type: "list",
                domain: projectDomain,
                context: { display_milestone_deadline: true },
            },
            track: {
                resModel: "project.project",
                type: "kanban",
                domain: projectDomain,
                context: { display_milestone_deadline: true },
                groupBy: ["last_update_status"],
            },
            timeline: {
                resModel: "project.project",
                type: "calendar",
                domain: projectDomain,
            },
            assign: {
                resModel: "project.task",
                type: "kanban",
                domain: taskDomain,
                context: { search_default_open_tasks: 1 },
                groupBy: ["user_ids"],
            },
            overdue: {
                resModel: "project.project",
                type: "list",
                domain: [
                    ["is_template", "=", false],
                    ["last_update_status", "!=", "done"],
                ],
                context: { search_default_lug_overdue: 1 },
            },
            people: {
                resModel: "project.task",
                type: "kanban",
                domain: taskDomain,
                context: { search_default_open_tasks: 1 },
                groupBy: ["user_ids"],
            },
            templates: {
                resModel: "project.project",
                type: "list",
                domain: [["is_template", "=", true]],
            },
            report_all: {
                resModel: "report.project.task.user",
                type: "pivot",
                domain: [
                    ["has_template_ancestor", "=", false],
                    ["project_id.is_template", "=", false],
                ],
                context: {
                    group_by: ["project_id"],
                },
            },
            perf: {
                resModel: "report.project.task.user",
                type: "pivot",
                domain: [
                    ["has_template_ancestor", "=", false],
                    ["project_id.is_template", "=", false],
                ],
                groupBy: ["user_ids"],
                context: {
                    group_by: ["user_ids"],
                },
            },
            milestones: {
                resModel: "project.milestone",
                type: "list",
                domain: [["project_id.is_template", "=", false]],
            },
        };
        const base = map[this.state.active] || map.list;
        return {
            ...base,
            views: [
                [false, base.type],
                [false, "search"],
            ],
            display: { controlPanel: this.state.active !== "intake" },
            loadIrFilters: false,
            loadActionMenus: true,
            className: "o_lps_embedded_view",
        };
    }

    async loadShellData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("project.project", "get_lug_shell_data", [], {
                project_id: this.state.filterProjectId || false,
                period: this.state.overviewPeriod || "month",
                type_id: this.state.overviewTypeId || false,
            });
            this.state.companyName = data.company_name || this.state.companyName;
            this.state.companyAddress = data.company_address || "";
            this.state.companyLogoUrl =
                data.company_logo_url || this.state.companyLogoUrl;
            this.state.userName = data.user_name || "";
            this.state.userRole = data.user_role || "Người dùng";
            this.state.userInitial = data.user_initial || "U";
            this.state.avatarUrl = data.avatar_url || false;
            const g = data.greeting || {};
            this.state.greeting = {
                headline: g.headline || `Xin chào, ${this.state.userName}!`,
                today_label_full: g.today_label_full || g.today_label || "",
                primary_line: g.primary_line || "Theo dõi tiến độ và hạn các dự án.",
            };
            this.state.dashboard = { ...emptyDashboard(), ...(data.dashboard || {}) };
            if (data.dashboard?.period) {
                this.state.overviewPeriod = data.dashboard.period;
            }
            if (data.dashboard?.type_id !== undefined) {
                this.state.overviewTypeId = data.dashboard.type_id || 0;
            }
            this.state.apps = this._collectRailApps();
        } catch (error) {
            console.error(error);
            this.state.dashboard = emptyDashboard();
            this.state.apps = this._collectRailApps();
        } finally {
            this.state.loading = false;
        }
    }

    _collectRailApps() {
        const apps = this.menu.getApps() || [];
        const byXml = {};
        for (const app of apps) {
            if (app?.xmlid) {
                byXml[app.xmlid] = app;
            }
        }
        return RAIL_ORDER.map((spec) => {
            const app = byXml[spec.xmlid];
            if (!app) {
                return null;
            }
            return {
                id: app.id,
                xmlid: spec.xmlid,
                name: app.name,
                actionID: app.actionID,
                icon: spec.icon,
            };
        }).filter(Boolean);
    }

    itemBadge(item) {
        if (item.badgeKey === "overdue") {
            return this.overdueCount;
        }
        if (item.badgeKey === "list") {
            return this.projectCount;
        }
        if (item.badgeKey === "archived") {
            return this.archivedCount;
        }
        return 0;
    }

    heatClass(value) {
        const n = Number(value) || 0;
        if (n >= 75) {
            return "h-red";
        }
        if (n >= 50) {
            return "h-orange";
        }
        if (n >= 25) {
            return "h-yellow";
        }
        return "h-green";
    }

    barStyle(row) {
        return `left:${row.left}%;width:${row.width}%;background:${row.color};`;
    }

    ganttMonthStyle(month) {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        return `width:${((Number(month.days) || 0) * 100) / count}%`;
    }

    ganttDayClass(day) {
        let cls = "";
        if (day.we) {
            cls += " is-we";
        }
        if (day.su) {
            cls += " is-sun";
        }
        if (day.t) {
            cls += " is-today";
        }
        return cls;
    }

    ganttDayStyle(day) {
        if (day.t) {
            return "background:#fef9c3;color:#854d0e;";
        }
        if (day.su) {
            return "background:#fecaca;color:#991b1b;";
        }
        if (day.we) {
            return "background:#e2e8f0;color:#64748b;";
        }
        return "";
    }

    _projectChip(projectId) {
        const n = Number(projectId) || 0;
        const mixed = ((n * 2654435761) >>> 0) % PROJECT_CHIP_COLORS.length;
        return PROJECT_CHIP_COLORS[mixed];
    }

    ganttNameRowStyle(row) {
        const taskLike = row.kind === "task" || row.kind === "milestone";
        const compact = taskLike
            ? "flex:0 0 28px;height:28px;min-height:28px;max-height:28px;"
            : "flex:0 0 32px;height:32px;min-height:32px;max-height:32px;";
        const box = "box-sizing:border-box;overflow:hidden;display:flex;align-items:center;";
        if (row.kind === "project") {
            const chip = this._projectChip(row.project_id);
            return `${compact}${box}background:${chip.bg};border:1.5px solid ${chip.bd};color:${chip.fg};font-weight:800;`;
        }
        if (row.kind === "task") {
            const color = row.color || "#3b82f6";
            return `${compact}${box}background:#fff;border:1px solid ${color};`;
        }
        return compact + box;
    }

    ganttTrackStyle(row) {
        if (row.kind === "task" || row.kind === "milestone") {
            return "flex:0 0 28px;height:28px;min-height:28px;max-height:28px;";
        }
        return "flex:0 0 32px;height:32px;min-height:32px;max-height:32px;";
    }

    ganttBarStyle(row) {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        const left = ((Number(row.start) || 0) * 100) / count;
        const width = (Math.max(Number(row.span) || 1, 1) * 100) / count;
        const color = row.color || (row.kind === "task" ? "#3b82f6" : "#334155");
        return `left:${left}%;width:${width}%;background:${color};`;
    }

    ganttLabelStyle(row) {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        const left =
            (((Number(row.start) || 0) + Math.max(Number(row.span) || 1, 1)) * 100) / count;
        return `left:calc(${left}% + 6px);`;
    }

    ganttMsStyle(ms) {
        const count = Math.max(Number(this.ganttCal.count) || 1, 1);
        return `left:${(((Number(ms) || 0) + 0.5) * 100) / count}%`;
    }

    isGanttCollapsed(projectId) {
        return Boolean(this.state.ganttCollapsed[projectId]);
    }

    toggleGanttGroup(projectId) {
        this.state.ganttCollapsed[projectId] = !this.state.ganttCollapsed[projectId];
    }

    toggleProjectFilter() {
        this.state.filterOpen = !this.state.filterOpen;
        if (!this.state.filterOpen) {
            this.state.filterQuery = "";
        }
    }

    onFilterSearch(ev) {
        this.state.filterQuery = ev.target.value || "";
    }

    onProjectFilterChange(projectId) {
        if (this.env.bus) {
            this.env.bus.trigger("LUG_PROJECT_FILTER", { project_id: projectId || false });
        }
    }

    async selectProjectFilter(projectId) {
        const nextId = projectId || 0;
        this.state.filterProjectId = nextId;
        this.state.filterOpen = false;
        this.state.filterQuery = "";
        this.state.ganttCollapsed = {};
        this.onProjectFilterChange(nextId);
        await this.loadShellData();
    }

    onGanttRowClick(row) {
        if (row.kind === "task") {
            this.openTask(row.res_id);
            return;
        }
        this.openProject(row.project_id || row.res_id);
    }

    async onOverviewPeriodChange(ev) {
        this.state.overviewPeriod = ev.target.value || "month";
        await this.loadShellData();
    }

    async onOverviewTypeChange(ev) {
        this.state.overviewTypeId = Number(ev.target.value) || 0;
        await this.loadShellData();
    }

    _downloadBase64Excel(b64, filename) {
        const link = document.createElement("a");
        link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${b64}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    async exportOverview() {
        this.state.overviewExporting = true;
        try {
            const result = await this.orm.call("project.project", "export_lug_overview_xlsx", [], {
                period: this.state.overviewPeriod || "month",
                type_id: this.state.overviewTypeId || false,
            });
            if (!result?.file_base64) {
                this.notification.add("Không có dữ liệu để xuất.", { type: "warning" });
                return;
            }
            this._downloadBase64Excel(result.file_base64, result.filename || "bao_cao_tong_quan.xlsx");
        } catch (error) {
            console.error(error);
            this.notification.add("Xuất báo cáo thất bại.", { type: "danger" });
        } finally {
            this.state.overviewExporting = false;
        }
    }

    _injectOverviewScrollCss() {
        const id = "lug-overview-scroll-css";
        let style = document.getElementById(id);
        if (!style) {
            style = document.createElement("style");
            style.id = id;
            document.head.appendChild(style);
        }
        style.textContent = `
.o_lug_project_shell .o_lps_content { position: relative !important; overflow: hidden !important; min-height: 0 !important; }
.o_lug_project_shell .o_lps_scroll {
  position: absolute !important;
  top: 0 !important; right: 0 !important; bottom: 0 !important; left: 0 !important;
  overflow-y: scroll !important;
  overflow-x: hidden !important;
  overscroll-behavior: contain !important;
  padding-right: 4px !important;
  scrollbar-gutter: stable both-edges;
  scrollbar-width: auto !important;
  scrollbar-color: #4c1d95 #c4b5fd !important;
}
.o_lug_project_shell .o_lps_scroll::-webkit-scrollbar { width: 18px !important; background: #c4b5fd !important; }
.o_lug_project_shell .o_lps_scroll::-webkit-scrollbar-track {
  background: #c4b5fd !important;
  border-left: 1px solid #7c3aed !important;
}
.o_lug_project_shell .o_lps_scroll::-webkit-scrollbar-thumb {
  background: #4c1d95 !important;
  border-radius: 9px !important;
  border: 3px solid #c4b5fd !important;
  min-height: 48px !important;
}
.o_lug_project_shell .o_lps_scroll::-webkit-scrollbar-thumb:hover { background: #2e1065 !important; }
.o_lug_project_shell .o_lps_overview { padding-bottom: 72px !important; box-sizing: border-box !important; }
.o_lug_project_shell .o_lps_scroll_spacer { height: 48px; width: 100%; }
.o_lug_project_shell .o_lps_scroll_controls {
  position: absolute !important;
  right: 22px !important;
  bottom: 18px !important;
  z-index: 40 !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 6px !important;
}
.o_lug_project_shell .o_lps_scroll_btn {
  width: 36px !important;
  height: 36px !important;
  border: 0 !important;
  border-radius: 10px !important;
  background: #4c1d95 !important;
  color: #fff !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  line-height: 36px !important;
  text-align: center !important;
  box-shadow: 0 8px 18px rgba(76, 29, 149, 0.35) !important;
  cursor: pointer !important;
}
.o_lug_project_shell .o_lps_scroll_btn:hover { background: #2e1065 !important; }
`;
    }

    _lockOverviewScrollPane() {
        if (this.state.active !== "kpi") {
            return;
        }
        const el = this.overviewScrollRef?.el || this.el?.querySelector?.(".o_lps_scroll");
        if (!el) {
            return;
        }
        el.style.setProperty("position", "absolute", "important");
        el.style.setProperty("top", "0", "important");
        el.style.setProperty("right", "0", "important");
        el.style.setProperty("bottom", "0", "important");
        el.style.setProperty("left", "0", "important");
        el.style.setProperty("overflow-y", "scroll", "important");
        el.style.setProperty("overflow-x", "hidden", "important");

        const overview = el.querySelector(".o_lps_overview");
        if (overview) {
            const need = Math.max(overview.scrollHeight, el.clientHeight + 220);
            overview.style.setProperty("min-height", `${need}px`, "important");
            overview.style.setProperty("padding-bottom", "72px", "important");
        }
    }

    scrollOverviewUp() {
        const el = this.overviewScrollRef?.el;
        if (!el) {
            return;
        }
        el.scrollTop = Math.max(0, el.scrollTop - 280);
    }

    scrollOverviewDown() {
        const el = this.overviewScrollRef?.el;
        if (!el) {
            return;
        }
        el.scrollTop = Math.min(el.scrollHeight - el.clientHeight, el.scrollTop + 280);
    }

    _makeChart(canvas, config) {
        if (!canvas || typeof Chart === "undefined") {
            return null;
        }
        try {
            const existing = typeof Chart.getChart === "function" ? Chart.getChart(canvas) : null;
            if (existing) {
                existing.destroy();
            }
            return new Chart(canvas, config);
        } catch (error) {
            console.error("Lug chart create failed", error);
            return null;
        }
    }

    async renderCharts() {
        this.destroyCharts();
        if (this.state.loading || this.state.active !== "kpi") {
            return;
        }
        try {
            if (typeof Chart === "undefined") {
                await loadBundle("web.chartjs_lib");
            }
        } catch (error) {
            console.error("Không tải được Chart.js", error);
            return;
        }
        if (typeof Chart === "undefined") {
            return;
        }
        const staff = this.overviewStaff;
        if (this.staffRef.el && staff.length) {
            this.staffChart = this._makeChart(this.staffRef.el, {
                type: "bar",
                data: {
                    labels: staff.map((row) => row.name),
                    datasets: [
                        {
                            label: "Số lượng dự án",
                            data: staff.map((row) => row.value),
                            backgroundColor: "#7c3aed",
                            borderRadius: 8,
                        },
                    ],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { precision: 0 } },
                        y: { grid: { display: false } },
                    },
                },
            });
        }
        const months = this.overviewMonths;
        if (this.trendRef.el && months.length) {
            this.trendChart = this._makeChart(this.trendRef.el, {
                type: "line",
                data: {
                    labels: months.map((m) => m.label),
                    datasets: [
                        {
                            label: "Mới tạo",
                            data: months.map((m) => m.created || m.ongoing || 0),
                            borderColor: "#3b82f6",
                            backgroundColor: "rgba(59, 130, 246, 0.12)",
                            fill: true,
                            tension: 0.4,
                        },
                        {
                            label: "Hoàn thành",
                            data: months.map((m) => m.done || 0),
                            borderColor: "#10b981",
                            tension: 0.4,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: { legend: { position: "bottom" } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                },
            });
        }
        const costs = this.overviewCosts;
        if (this.costRef.el && costs.length) {
            this.costChart = this._makeChart(this.costRef.el, {
                type: "bar",
                data: {
                    labels: costs.map((row) => row.name),
                    datasets: [
                        {
                            label: "Chi phí (Triệu VNĐ)",
                            data: costs.map((row) => row.value),
                            backgroundColor: "#10b981",
                            borderRadius: 8,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false } },
                        y: { beginAtZero: true },
                    },
                },
            });
        }
        const perf = this.overviewPerf;
        if (this.perfRef.el && perf.length) {
            this.perfChart = this._makeChart(this.perfRef.el, {
                type: "doughnut",
                data: {
                    labels: perf.map((row) => row.label),
                    datasets: [
                        {
                            data: perf.map((row) => row.count),
                            backgroundColor: perf.map((row) => row.color),
                            borderWidth: 2,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    cutout: "70%",
                    plugins: { legend: { position: "bottom" } },
                },
            });
        }
    }

    destroyCharts() {
        for (const key of ["staffChart", "trendChart", "costChart", "perfChart"]) {
            if (this[key]) {
                try {
                    this[key].destroy();
                } catch (_e) {
                    // canvas may already be detached by OWL
                }
                this[key] = null;
            }
        }
    }

    async setActive(code) {
        if (code === "contacts") {
            await this.openContacts();
            return;
        }
        if (code === "types") {
            await this.action.doAction("lug_project.action_lug_project_type");
            return;
        }
        if (code === "cfg_phase") {
            await this.action.doAction("lug_project.action_lug_project_phase");
            return;
        }
        const cfgNotes = {
            cfg_status: "Trạng thái công việc: Chưa bắt đầu, Đang thực hiện, Chờ duyệt, Hoàn thành, Hủy.",
            cfg_priority: "Mức độ ưu tiên nằm trên từng dự án (Cao / Trung bình / Thấp).",
            cfg_access: "Phân quyền dùng quyền Project chuẩn của Odoo. Không thay đổi ACL native.",
        };
        if (cfgNotes[code]) {
            this.notification.add(cfgNotes[code], { type: "info" });
            return;
        }
        this.state.viewError = "";
        this.state.active = code;
    }

    async afterIntakeSave() {
        await this.setActive("list");
        this.loadShellData();
    }

    onSearch(ev) {
        this.state.query = ev.target.value;
    }

    onKpiClick(key) {
        if (key === "overdue") {
            this.setActive("overdue");
        } else if (key === "ongoing") {
            this.setActive("list");
        } else if (key === "done" || key === "total") {
            this.setActive("list");
        }
    }

    pieColor(index) {
        const status = this.state.dashboard.status || [];
        return status[index]?.color || STATUS_PIE_COLORS[index % STATUS_PIE_COLORS.length];
    }

    deltaClass(delta) {
        if (delta > 0) {
            return "is-up";
        }
        if (delta < 0) {
            return "is-down";
        }
        return "is-flat";
    }

    deltaText(delta) {
        const n = Number(delta) || 0;
        const sign = n > 0 ? "+" : "";
        return `${sign}${n}% vs tháng trước`;
    }

    copyDashboardTitle() {
        const title = this.state.dashboard.featured_title || "Báo cáo KPI dự án";
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(title);
        }
    }

    formatPct(value) {
        const n = Number(value) || 0;
        return `${n.toFixed(2)}%`;
    }

    async viewGanttForProject(projectId) {
        this.state.filterProjectId = projectId || false;
        this.state.active = "gantt";
        await this.loadShellData();
    }

    async openProject(projectId) {
        if (!projectId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            res_id: projectId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openTask(taskId) {
        if (!taskId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async goHome() {
        try {
            await this.action.doAction("lug_app_center.action_lug_app_center", {
                clearBreadcrumbs: true,
            });
        } catch (_e) {
            window.location.href = "/odoo";
        }
    }

    async openApp(app) {
        try {
            const menu = this.menu.getMenu(app.id) || app;
            if (menu?.actionID || app.actionID) {
                await this.menu.selectMenu(menu.actionID ? menu : app.id);
                return;
            }
        } catch (error) {
            console.error(error);
        }
    }

    async openContacts() {
        try {
            await this.action.doAction("contacts.action_contacts");
        } catch (_e) {
            await this.action.doAction("base.action_partner_form");
        }
    }

    toggleRail() {
        this.state.railCollapsed = !this.state.railCollapsed;
        try {
            window.localStorage.setItem(
                RAIL_COLLAPSED_KEY,
                this.state.railCollapsed ? "1" : "0"
            );
        } catch (_e) {
            /* ignore */
        }
    }

    stopPointer(ev) {
        ev.stopPropagation();
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

    persistRailWidth(width) {
        const next = Math.min(RAIL_WIDTH_MAX, Math.max(RAIL_WIDTH_MIN, Math.round(width)));
        this.state.railWidth = next;
        try {
            window.localStorage.setItem(RAIL_WIDTH_KEY, String(next));
        } catch (_e) {
            /* ignore */
        }
        return next;
    }

    resetRailWidth() {
        this.persistRailWidth(RAIL_WIDTH_DEFAULT);
    }

    onRailResizeStart(ev) {
        if (ev.button !== 0) {
            return;
        }
        if (this.state.railCollapsed) {
            this.toggleRail();
            return;
        }
        ev.preventDefault();
        this._stopSidebarResize();
        const startX = ev.clientX;
        const startWidth = this.state.railWidth;
        this.state.railResizing = true;
        document.body.classList.add("o_lps_sidebar_resizing");
        try {
            ev.currentTarget.setPointerCapture(ev.pointerId);
        } catch (_e) {
            /* ignore */
        }
        const onMove = (e) => {
            this.state.railWidth = Math.min(
                RAIL_WIDTH_MAX,
                Math.max(RAIL_WIDTH_MIN, Math.round(startWidth + (e.clientX - startX)))
            );
        };
        const onUp = () => {
            this.persistRailWidth(this.state.railWidth);
            this._stopSidebarResize();
        };
        this._sidebarResize = { onMove, onUp };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onUp);
    }

    persistSidebarWidth(width) {
        const next = Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, Math.round(width)));
        this.state.sidebarWidth = next;
        try {
            window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(next));
        } catch (_e) {
            /* ignore */
        }
        return next;
    }

    resetSidebarWidth() {
        if (this.state.sidebarCollapsed) {
            return;
        }
        this.persistSidebarWidth(SIDEBAR_WIDTH_DEFAULT);
    }

    onSidebarResizeStart(ev) {
        if (ev.button !== 0) {
            return;
        }
        if (this.state.sidebarCollapsed) {
            this.toggleSidebar();
            return;
        }
        ev.preventDefault();
        this._stopSidebarResize();
        const startX = ev.clientX;
        const startWidth = this.state.sidebarWidth;
        this.state.sidebarResizing = true;
        document.body.classList.add("o_lps_sidebar_resizing");
        try {
            ev.currentTarget.setPointerCapture(ev.pointerId);
        } catch (_e) {
            /* ignore */
        }
        const onMove = (e) => {
            const next = startWidth + (e.clientX - startX);
            this.state.sidebarWidth = Math.min(
                SIDEBAR_WIDTH_MAX,
                Math.max(SIDEBAR_WIDTH_MIN, Math.round(next))
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
        this.state.railResizing = false;
        document.body.classList.remove("o_lps_sidebar_resizing");
    }
}

registry.category("actions").add("lug_project_shell", LugProjectShell, { force: true });
