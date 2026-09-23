/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState, useSubEnv } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";
import { PhanHeInternetShell } from "../internet_shell/phan_he_internet_shell";
import { PhanHeInternetListBoard, PhanHeMonthCostBoard, PhanHeQuarterCostBoard } from "../internet_list/phan_he_internet_list";
import { PhanHePaymentBoard } from "../payment_board/phan_he_payment_board";
import { PhanHeInternetEntryPopup } from "../internet_entry/phan_he_internet_entry_popup";
import {
    INTERNET_NAV_TO_CODE,
    filterInternetNavSections,
    firstAllowedInternetNav,
    internetNavCan,
} from "../access/internet_menu_nav";

const OWL_LIST_NAV = {
    list_all: "all",
    list_active: "active",
    list_suspend: "suspend",
    list_liquidated: "liquidated",
    expire_soon: "expire_soon",
    expired: "expired",
    payment_schedule: "payment_due",
    payment_overdue: "expired",
    payment_forecast: "payment_forecast",
    report_year: "report_year",
};

/** Board danh sách phan.he.payment (Xác nhận TT). */
const PAYMENT_BOARD_NAV = {
    payment_confirm: "confirm",
};

const INTERNET_NAV_SECTIONS = [
    {
        id: "manage",
        label: "Quản lý Internet",
        icon: "fa-sitemap",
        iconTone: "manage",
        children: [
            {
                id: "list_active",
                label: "Đang sử dụng",
                icon: "fa-globe",
                statusTone: "active",
                iconTone: "active",
                tone: "danger",
                badgeKey: "list_active",
                action: "lug_phan_he.action_phan_he_internet_active_master",
            },
            {
                id: "list_suspend",
                label: "Tạm ngưng",
                icon: "fa-globe",
                statusTone: "suspend",
                iconTone: "suspend",
                tone: "danger",
                badgeKey: "list_suspend",
                action: "lug_phan_he.action_phan_he_service_internet_suspend",
            },
            {
                id: "list_liquidated",
                label: "Thanh lý",
                icon: "fa-globe",
                statusTone: "liquidated",
                iconTone: "liquidated",
                tone: "danger",
                badgeKey: "list_liquidated",
                action: "lug_phan_he.action_phan_he_service_internet_liquidated",
            },
            {
                id: "store_declare",
                label: "Nhập thông tin",
                icon: "fa-globe",
                iconTone: "store",
                action: "lug_phan_he.action_phan_he_service_entry",
            },
        ],
    },
    {
        id: "payment",
        label: "Chi phí & thanh toán",
        icon: "fa-credit-card",
        iconTone: "payment",
        children: [
            {
                id: "payment_schedule",
                label: "Danh sách thanh toán",
                icon: "fa-calendar",
                iconTone: "payment",
                tone: "danger",
                badgeKey: "payment_schedule",
            },
            {
                id: "payment_confirm",
                label: "Xác nhận TT",
                icon: "fa-check-square-o",
                iconTone: "payment",
                tone: "danger",
                badgeKey: "payment_confirm",
            },
            {
                id: "payment_overdue",
                label: "Quá hạn",
                icon: "fa-times-circle",
                tone: "danger",
                iconTone: "overdue",
                badgeKey: "overdue_contract",
            },
            {
                id: "payment_forecast",
                label: "Lịch dự kiến TT",
                icon: "fa-calendar-plus-o",
                iconTone: "payment",
                tone: "danger",
                badgeKey: "payment_forecast",
            },
        ],
    },
    {
        id: "reports",
        label: "Báo cáo",
        icon: "fa-bar-chart",
        iconTone: "report",
        children: [
            { id: "report_month", label: "Chi phí tháng", icon: "fa-line-chart", iconTone: "report", reportPeriod: "month" },
            { id: "report_quarter", label: "Chi phí quý", icon: "fa-area-chart", iconTone: "report", reportPeriod: "quarter" },
            { id: "report_year", label: "Chi phí năm", icon: "fa-pie-chart", iconTone: "report", reportPeriod: "year" },
        ],
    },
    {
        id: "settings",
        label: "Cài đặt",
        icon: "fa-cog",
        children: [
            {
                id: "settings_provider",
                label: "Nhà cung cấp",
                icon: "fa-building",
                action: "lug_phan_he.action_phan_he_provider",
            },
        ],
    },
];

function formatNumber(n) {
    return new Intl.NumberFormat("vi-VN").format(Math.round(Number(n || 0)));
}

function pad2(n) {
    return String(n).padStart(2, "0");
}

function yearStartDisplay(year) {
    return `01/01/${year}`;
}

function yearEndDisplay(year) {
    return `31/12/${year}`;
}

function displayToIso(value) {
    const raw = String(value || "").trim();
    const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) {
        return false;
    }
    return `${m[3]}-${pad2(m[2])}-${pad2(m[1])}`;
}

function isoToDisplay(value) {
    const raw = String(value || "").trim();
    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) {
        return raw;
    }
    return `${m[3]}/${m[2]}/${m[1]}`;
}

export class PhanHeDashboard extends Component {
    static template = "lug_phan_he.PhanHeDashboard";
    static props = { ...standardActionServiceProps, "*": true };
    static components = {
        PhanHeAppSidebar,
        PhanHeInternetShell,
        PhanHeInternetListBoard,
        PhanHeMonthCostBoard,
        PhanHeQuarterCostBoard,
        PhanHePaymentBoard,
        PhanHeInternetEntryPopup,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        useSubEnv({
            config: {
                ...(this.env.config || {}),
                historyBack: () => this.closeEmbeddedView(),
            },
        });
        const year = new Date().getFullYear();
        this.state = useState({
            loading: true,
            exporting: false,
            openGroups: {
                manage: true,
                payment: true,
                reports: true,
                settings: false,
                shifts: true,
            },
            activeNav: "overview",
            listFilter: "active",
            listReloadToken: 0,
            paymentBoardMode: "confirm",
            paymentBoardToken: 0,
            contentMode: "dashboard",
            embeddedViewProps: null,
            viewKey: 0,
            listActionXml: null,
            formReturn: null,
            reportPeriod: "year",
            trendHover: null,
            data: {},
            inet: {},
            internetMenus: {},
            paymentReport: { tables: [] },
            entryPopupOpen: false,
            entryPopupResId: false,
            selectedMonth: `${year}-${pad2(new Date().getMonth() + 1)}`,
            selectedRegion: "all",
            selectedStore: "all",
            monthChartMode: "bar",
            filters: {
                year: year,
                date_from: yearStartDisplay(year),
                date_to: yearEndDisplay(year),
                mien_id: "",
                area_id: "",
                employee_id: "",
            },
        });
        this.inetSparkRef = useRef("inetSpark");
        this.inetDonutRef = useRef("inetDonut");
        this.inetYearRef = useRef("inetYear");
        this.inetMonthTrendRef = useRef("inetMonthTrend");
        this.inetCharts = {};
        onWillStart(async () => {
            try {
                if (this.serviceTypeCode === "internet") {
                    const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
                    this.state.internetMenus = rights?.internet_menus || {};
                    await this.loadNavBadges();
                }
                let openNav = this.actionContext.phan_he_open_nav;
                if (this.serviceTypeCode === "internet") {
                    const menus = this.state.internetMenus;
                    if (openNav && !internetNavCan(menus, openNav === "overview" ? "overview" : openNav)) {
                        openNav = false;
                    }
                    if ((!openNav || openNav === "overview") && !internetNavCan(menus, "overview")) {
                        const first = firstAllowedInternetNav(
                            filterInternetNavSections(INTERNET_NAV_SECTIONS, menus)
                        );
                        openNav = first ? first.id : false;
                    }
                }
                if (openNav === "report_quarter") {
                    this.state.contentMode = "quarter_cost";
                    this.state.activeNav = "report_quarter";
                    this._openGroupForNav("report_quarter");
                    this.state.loading = false;
                    return;
                }
                if (openNav === "report_month") {
                    this.state.contentMode = "month_cost";
                    this.state.activeNav = "report_month";
                    this._openGroupForNav("report_month");
                    this.state.loading = false;
                    return;
                }
                const openList = Boolean(openNav && OWL_LIST_NAV[openNav]);
                if (openList) {
                    this.state.contentMode = "owl_list";
                    this.state.listFilter = OWL_LIST_NAV[openNav];
                    this.state.activeNav = openNav;
                    this._openGroupForNav(openNav);
                    this.state.loading = false;
                    return;
                }
                if (openNav && PAYMENT_BOARD_NAV[openNav]) {
                    this.state.contentMode = "payment_board";
                    this.state.paymentBoardMode = PAYMENT_BOARD_NAV[openNav];
                    this.state.activeNav = openNav;
                    this._openGroupForNav(openNav);
                    this.state.loading = false;
                    return;
                }
                if (this.serviceTypeCode === "internet") {
                    await loadBundle("web.chartjs_lib");
                }
                if (this.actionContext.phan_he_dash_view === "reports") {
                    this.state.activeNav = "reports";
                    this._openGroupForNav("reports");
                }
                await this.load();
                if (openNav && openNav !== "overview") {
                    const child = this.findNavChild(openNav);
                    if (child) {
                        if (child.id === "store_declare") {
                            this.openEntryPopup(false);
                        } else {
                            await this.openEmbedded(child);
                        }
                    }
                    this._openGroupForNav(openNav);
                }
            } catch (err) {
                console.error(err);
                this.state.loading = false;
            }
        });
        useEffect(
            () => {
                if (!this.isInternetDash || this.state.loading || this.state.contentMode === "owl_list" || this.state.contentMode === "month_cost" || this.state.contentMode === "quarter_cost" || this.state.contentMode === "payment_board") {
                    return () => {};
                }
                this.renderInetCharts();
                return () => this.destroyInetCharts();
            },
            () => [this.state.inet, this.state.loading, this.state.activeNav, this.state.monthChartMode]
        );
        onWillUnmount(() => this.destroyInetCharts());
        onWillUpdateProps((next) => {
            // Đổi action client (menu Odoo xếp chồng) → mở đúng nav + load API mới.
            const prevCtx = this.props.action?.context || {};
            const nextCtx = next.action?.context || {};
            const prevNav = prevCtx.phan_he_open_nav || "";
            const nextNav = nextCtx.phan_he_open_nav || "";
            if (nextNav && nextNav !== prevNav && nextNav !== this.state.activeNav) {
                const child = this.findNavChild(nextNav);
                if (child) {
                    this.onNavChild(child);
                }
            }
        });
    }

    get yearOptions() {
        const current = new Date().getFullYear();
        const years = [];
        for (let y = current - 3; y <= current + 1; y++) {
            years.push(y);
        }
        const selected = Number(this.state.filters.year || current);
        if (selected && !years.includes(selected)) {
            years.push(selected);
            years.sort((a, b) => a - b);
        }
        return years;
    }

    get actionContext() {
        return this.props.action?.context || {};
    }

    get serviceTypeCode() {
        return this.actionContext.phan_he_service_type_code || "internet";
    }

    get appTitle() {
        if (this.serviceTypeCode === "internet") {
            return this.actionContext.phan_he_app_title
                || this.state.data.app_title
                || "Dịch vụ Internet";
        }
        return this.actionContext.phan_he_app_title
            || this.state.data.app_title
            || "Quản lý dịch vụ";
    }

    get isInternetDash() {
        return (
            this.serviceTypeCode === "internet"
            && this.state.activeNav !== "reports"
            && this.state.contentMode !== "view"
            && this.state.contentMode !== "month_cost"
            && this.state.contentMode !== "quarter_cost"
        );
    }

    get isInternetMaster() {
        return this.serviceTypeCode === "internet";
    }

    get embeddedViewProps() {
        return this.state.embeddedViewProps;
    }

    get isLinkqErp() {
        return this.serviceTypeCode === "linkq_nb";
    }

    get inet() {
        return this.state.inet || {};
    }

    get inetUsage() {
        return this.inet.usage || { active: 0, suspend: 0, liquidated: 0, active_pct: 0 };
    }

    get inetUsagePct() {
        return this.inetUsage.active_pct || 0;
    }

    get inetUsageDash() {
        const pct = Math.min(100, Math.max(0, Number(this.inetUsagePct || 0)));
        return `${pct} 100`;
    }

    get inetLineChart() {
        const pts = this.inet.trend || [];
        const w = 360;
        const h = 148;
        const left = 40;
        const right = 8;
        const top = 12;
        const bottom = 22;
        if (!pts.length) {
            return { line: "", area: "", dots: [], yTicks: [], xLabels: [], tip: null };
        }
        const vals = pts.map((p) => Number(p.amount || 0));
        const max = Math.max(...vals, 1);
        const innerW = w - left - right;
        const innerH = h - top - bottom;
        const coords = vals.map((v, i) => {
            const x = left + (i * innerW) / Math.max(pts.length - 1, 1);
            const y = top + innerH - (v / max) * innerH;
            return {
                x,
                y,
                amount: v,
                label: pts[i].full || pts[i].label || "",
                key: pts[i].key,
            };
        });
        const line = coords.map((c, i) => `${i ? "L" : "M"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
        const last = coords[coords.length - 1];
        const first = coords[0];
        const area = `${line} L${last.x.toFixed(1)},${top + innerH} L${first.x.toFixed(1)},${top + innerH} Z`;
        const yTicks = [1, 0.75, 0.5, 0.25, 0].map((ratio) => ({
            y: top + innerH - ratio * innerH,
            label: this.formatTrieu(max * ratio),
        }));
        return {
            line,
            area,
            dots: coords,
            yTicks,
            xLabels: coords.map((c, i) => ({ x: c.x, label: pts[i].label || "" })),
            tip: null,
            gridY: top + innerH,
        };
    }

    formatTrieu(amount) {
        const n = Number(amount || 0);
        if (n >= 1e6) {
            return `${(n / 1e6).toFixed(1)} Tr`;
        }
        if (n >= 1e3) {
            return `${Math.round(n / 1e3)}k`;
        }
        return `${Math.round(n)}`;
    }

    formatTrieuVnd(amount) {
        const n = Number(amount || 0);
        return `${(n / 1e6).toFixed(1)} Tr. VNĐ`;
    }

    sparkPct(sp) {
        return Number(sp?.pct || 8);
    }

    regionToneClass(code) {
        const c = String(code || "").toUpperCase();
        if (c === "NAM") {
            return "is-nam";
        }
        if (c === "DTT" || c === "TRUNG") {
            return "is-dtt";
        }
        if (c === "BAC") {
            return "is-bac";
        }
        if (c === "VP") {
            return "is-vp";
        }
        return "is-nam";
    }

    get inetDonutBg() {
        const regions = this.inet.regions || [];
        if (!regions.length) {
            return "#eef2f7";
        }
        let acc = 0;
        const parts = [];
        for (const r of regions) {
            const start = acc;
            acc += Number(r.pct || 0);
            parts.push(`${r.color || "#94a3b8"} ${start}% ${acc}%`);
        }
        return `conic-gradient(${parts.join(",")})`;
    }

    get inetYearMax() {
        const ys = this.inet.year_bars || [];
        return Math.max(...ys.map((y) => Number(y.amount || 0)), 1);
    }

    yearBarPct(yb) {
        return Math.round((Number(yb?.amount || 0) / this.inetYearMax) * 100);
    }

    get linkqSidebarKey() {
        return "dashboard";
    }

    get sidebarBrand() {
        const brands = {
            internet: "DỊCH VỤ INTERNET",
            camera: "DỊCH VỤ CAMERA",
            attendance: "MÁY CHẤM CÔNG",
            linkq_hrm: "LINKQ HRM",
            linkq_nb: "LINKQ ERP",
            server: "MÁY CHỦ & CLOUD",
        };
        return brands[this.serviceTypeCode] || String(this.appTitle || "").toUpperCase();
    }

    get navSections() {
        const code = this.serviceTypeCode;
        if (code === "internet") {
            return filterInternetNavSections(INTERNET_NAV_SECTIONS, this.state.internetMenus);
        }
        if (code === "linkq_nb") {
            return [
                {
                    id: "shifts",
                    label: "Xếp ca",
                    icon: "fa-calendar",
                    children: [
                        {
                            id: "shift_codes",
                            label: "Ký hiệu công",
                            icon: "fa-tags",
                            iconColor: "#7c3aed",
                            action: "lug_phan_he.action_linkq_shift_code",
                        },
                        {
                            id: "roster",
                            label: "Bản xếp ca",
                            icon: "fa-th",
                            iconColor: "#2563eb",
                            action: "lug_phan_he.action_phan_he_shift_roster",
                        },
                    ],
                },
            ];
        }

        const trackingByType = {
            camera: "lug_phan_he.action_phan_he_service_tracking_camera",
            attendance: "lug_phan_he.action_phan_he_service_tracking_attendance",
            linkq_hrm: "lug_phan_he.action_phan_he_service_tracking_linkq_hrm",
            linkq_nb: "lug_phan_he.action_phan_he_service_tracking_linkq_nb",
            server: "lug_phan_he.action_phan_he_service_tracking_server",
        };
        const paymentByType = {
            camera: "lug_phan_he.action_phan_he_payment_camera",
            attendance: "lug_phan_he.action_phan_he_payment_attendance",
            linkq_hrm: "lug_phan_he.action_phan_he_payment_linkq_hrm",
            linkq_nb: "lug_phan_he.action_phan_he_payment_linkq_nb",
            server: "lug_phan_he.action_phan_he_payment_server",
        };
        return [
            {
                id: "manage",
                label: "Quản lý",
                icon: "fa-list-alt",
                children: [
                    {
                        id: "list_all",
                        label: "Danh sách",
                        action: trackingByType[code] || trackingByType.camera,
                    },
                    {
                        id: "payment_schedule",
                        label: "Thanh toán",
                        action: paymentByType[code] || paymentByType.camera,
                    },
                ],
            },
            {
                id: "alerts",
                label: "Cảnh báo",
                icon: "fa-bell",
                children: [
                    {
                        id: "expire_soon",
                        label: "Sắp hết hạn",
                        badgeKey: "expire_soon",
                        tone: "warn",
                        action: "lug_phan_he.action_phan_he_service_expire_soon",
                    },
                    {
                        id: "expired",
                        label: "Quá hạn",
                        badgeKey: "overdue_contract",
                        tone: "danger",
                        action: "lug_phan_he.action_phan_he_service_expired",
                    },
                ],
            },
        ];
    }

    get canSeeInternetOverview() {
        if (this.serviceTypeCode !== "internet") {
            return true;
        }
        return internetNavCan(this.state.internetMenus, "overview");
    }

    get alertCount() {
        return Number(this.state.data.alert_count || 0);
    }

    isGroupOpen(groupId) {
        return Boolean(this.state.openGroups[groupId]);
    }

    navChildClass(child) {
        const classes = [];
        const isActive =
            this.state.activeNav === child.id ||
            (child.reportPeriod &&
                this.state.activeNav === "reports" &&
                this.state.reportPeriod === child.reportPeriod);
        if (isActive) {
            classes.push("is-active");
        }
        if (child.iconTone) {
            classes.push("is-icon-" + child.iconTone);
        }
        if (child.tone) {
            classes.push("is-tone-" + child.tone);
        }
        return classes.join(" ");
    }

    _openGroupForNav(navId) {
        if (!navId || navId === "overview") {
            return;
        }
        if (navId === "reports") {
            this.state.openGroups.reports = true;
            return;
        }
        for (const section of this.navSections || []) {
            if ((section.children || []).some((c) => c.id === navId)) {
                this.state.openGroups[section.id] = true;
            }
        }
    }

    toggleGroup(groupId) {
        this.state.openGroups[groupId] = !this.state.openGroups[groupId];
    }

    onOverview() {
        if (this.serviceTypeCode === "internet" && !this.canSeeInternetOverview) {
            const first = firstAllowedInternetNav(this.navSections);
            if (first) {
                this.onNavChild(first);
            }
            return;
        }
        this.state.activeNav = "overview";
        this.state.contentMode = "dashboard";
        this.state.embeddedViewProps = null;
        this.state.listActionXml = null;
        this.state.formReturn = null;
        this.load();
    }

    findNavChild(navId) {
        for (const section of this.navSections || []) {
            const child = (section.children || []).find((c) => c.id === navId);
            if (child) {
                return child;
            }
        }
        return null;
    }

    onNavChild(child) {
        if (!child) {
            return;
        }
        if (this.serviceTypeCode === "internet" && !internetNavCan(this.state.internetMenus, child.id)) {
            this.notification.add("Bạn không có quyền xem mục này.", { type: "warning" });
            return;
        }
        // Lịch thanh toán / Quá hạn / Dự kiến TT / list Internet → board OWL hợp đồng.
        if (OWL_LIST_NAV[child.id]) {
            const nextFilter = OWL_LIST_NAV[child.id];
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "owl_list";
            this.state.listFilter = nextFilter;
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.entryPopupOpen = false;
            // Luôn tăng token → ép ListBoard load lại qua onWillUpdateProps.
            this.state.listReloadToken = (this.state.listReloadToken || 0) + 1;
            return;
        }
        // Xác nhận TT → board OWL phiếu thanh toán (get_payment_confirm_board).
        if (PAYMENT_BOARD_NAV[child.id]) {
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "payment_board";
            this.state.paymentBoardMode = PAYMENT_BOARD_NAV[child.id];
            this.state.paymentBoardToken = (this.state.paymentBoardToken || 0) + 1;
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.entryPopupOpen = false;
            return;
        }
        if (child.action && !child.reportPeriod) {
            this._rememberFormReturn();
        }
        this.state.activeNav = child.id;
        this._openGroupForNav(child.id);
        if (child.id === "store_declare") {
            this.openEntryPopup(false);
            return;
        }
        if (child.reportPeriod) {
            this.openReportPeriod(child.reportPeriod);
            return;
        }
        if (child.action) {
            this.openEmbedded(child);
        }
    }

    asViewDisplay(display) {
        const d = display && typeof display === "object" ? { ...display } : {};
        if (!d.controlPanel || typeof d.controlPanel !== "object") {
            d.controlPanel = {};
        }
        return d;
    }

    parseActionContext(context) {
        if (!context) {
            return {};
        }
        if (typeof context === "object" && !Array.isArray(context)) {
            return { ...context };
        }
        return {};
    }

    normalizeActionViews(act, preferredType) {
        const views = Array.isArray(act.views) ? act.views.map((v) => [...v]) : [];
        if (!views.some((v) => v[1] === "form")) {
            views.push([false, "form"]);
        }
        if (preferredType !== "form" && !views.some((v) => v[1] === "list")) {
            views.push([false, "list"]);
        }
        if (!views.some((v) => v[1] === "search")) {
            views.push([false, "search"]);
        }
        return views;
    }

    _rememberFormReturn() {
        if (this.state.contentMode === "view") {
            return;
        }
        this.state.formReturn = {
            contentMode: this.state.contentMode,
            listFilter: this.state.listFilter,
            activeNav: this.state.activeNav,
        };
    }

    closeEmbeddedView() {
        const ret = this.state.formReturn || {};
        this.state.embeddedViewProps = null;
        this.state.formReturn = null;
        this.state.listActionXml = null;
        if (ret.contentMode === "owl_list" || OWL_LIST_NAV[ret.activeNav]) {
            this.state.contentMode = "owl_list";
            this.state.listFilter = ret.listFilter || OWL_LIST_NAV[ret.activeNav] || "active";
            this.state.activeNav = OWL_LIST_NAV[ret.activeNav]
                ? ret.activeNav
                : Object.entries(OWL_LIST_NAV).find(([, v]) => v === ret.listFilter)?.[0] || "list_active";
            return;
        }
        if (ret.contentMode === "month_cost" || ret.activeNav === "report_month") {
            this.state.contentMode = "month_cost";
            this.state.activeNav = "report_month";
            return;
        }
        if (ret.contentMode === "quarter_cost" || ret.activeNav === "report_quarter") {
            this.state.contentMode = "quarter_cost";
            this.state.activeNav = "report_quarter";
            return;
        }
        this.onOverview();
    }

    async openEntryForm(resId = false) {
        if (!resId) {
            this.openEntryPopup(false);
            return;
        }
        this._rememberFormReturn();
        this.state.openGroups.manage = true;
        const nav =
            (this.state.activeNav && OWL_LIST_NAV[this.state.activeNav] && this.state.activeNav) ||
            "list_active";
        await this.openEmbedded(
            { id: nav, action: "lug_phan_he.action_phan_he_service_entry" },
            {
                type: "form",
                resId,
                action: "lug_phan_he.action_phan_he_service_entry",
                activeNav: nav,
            }
        );
    }

    openEntryPopup(resId = false) {
        // Cho phép mở nếu có quyền create/write, hoặc chưa có bảng quyền (admin / chưa load).
        const menus = this.state.internetMenus || {};
        const hasMenuAcl = Object.keys(menus).length > 0;
        const canCreate = !hasMenuAcl
            || internetNavCan(menus, "store_declare", "create")
            || internetNavCan(menus, this.state.activeNav || "list_active", "create");
        const canWrite = !hasMenuAcl
            || internetNavCan(menus, "store_declare", "write")
            || internetNavCan(menus, this.state.activeNav || "list_active", "write");
        if (resId ? !canWrite : !canCreate) {
            this.notification.add(resId ? "Bạn không có quyền Sửa." : "Bạn không có quyền Thêm.", {
                type: "warning",
            });
            return;
        }
        this.state.activeNav = "store_declare";
        this.state.openGroups.manage = true;
        this.state.entryPopupResId = resId || false;
        this.state.entryPopupOpen = true;
    }

    closeEntryPopup() {
        this.state.entryPopupOpen = false;
        this.state.entryPopupResId = false;
    }

    onEntryPopupSaved() {
        this.closeEntryPopup();
        this.state.contentMode = "owl_list";
        this.state.listFilter = "active";
        this.state.activeNav = "list_active";
        this.state.embeddedViewProps = null;
        this.state.listActionXml = null;
        this.state.viewKey += 1;
    }

    async openEmbedded(child, extra = {}) {
        const navId = extra.activeNav || child.id;
        const xmlid = extra.action || child.action;
        // Chặn mọi đường mở list phan.he.payment khi đang ở Lịch thanh toán Internet.
        const paymentListActions = new Set([
            "lug_phan_he.action_phan_he_payment",
            "lug_phan_he.action_phan_he_payment_due_soon",
        ]);
        if (
            this.serviceTypeCode === "internet"
            && extra.type !== "form"
            && (OWL_LIST_NAV[navId] || paymentListActions.has(xmlid) || navId === "payment_schedule")
        ) {
            this.state.contentMode = "owl_list";
            this.state.listFilter = OWL_LIST_NAV[navId] || "payment_due";
            this.state.activeNav = OWL_LIST_NAV[navId] ? navId : "payment_schedule";
            this._openGroupForNav(this.state.activeNav);
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.viewKey += 1;
            return;
        }
        const isEntry =
            navId === "store_declare"
            || xmlid === "lug_phan_he.action_phan_he_service_entry";
        if (isEntry && (extra.resId === false || extra.resId === undefined) && extra.type !== "form") {
            // Mở form mới → popup, không embed trang form rộng hẹp.
            this.openEntryPopup(false);
            return;
        }
        if (isEntry && !extra.resId && extra.type === "form") {
            this.openEntryPopup(false);
            return;
        }
        // Chỉ chuyển sang board OWL khi không phải mở form chi tiết.
        if (OWL_LIST_NAV[navId] && extra.type !== "form") {
            this.state.contentMode = "owl_list";
            this.state.listFilter = OWL_LIST_NAV[navId];
            this.state.activeNav = navId;
            this._openGroupForNav(navId);
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.viewKey += 1;
            return;
        }
        if (!xmlid) {
            return;
        }
        this.state.activeNav = extra.activeNav || child.id || this.state.activeNav;
        this._openGroupForNav(this.state.activeNav);
        if (!extra.type || extra.type === "list") {
            this.state.listActionXml = xmlid;
        }
        try {
            const act = await this.action.loadAction(xmlid);
            if (!act || act.type === "ir.actions.client") {
                this.action.doAction(xmlid);
                return;
            }
            const viewMode = String(act.view_mode || "list,form");
            const defaultType = extra.type || (viewMode.split(",")[0] === "form" ? "form" : "list");
            const views = this.normalizeActionViews(act, defaultType);
            const typedView = views.find((v) => v[1] === defaultType);
            this.state.viewKey += 1;
            this.state.contentMode = "view";
            const menuKey = this.state.activeNav || navId;
            const menuCode = INTERNET_NAV_TO_CODE[menuKey] || false;
            const canWrite = internetNavCan(this.state.internetMenus, menuKey, "write")
                || (menuKey === "store_declare" && internetNavCan(this.state.internetMenus, "store_declare", "write"));
            const canCreate = internetNavCan(this.state.internetMenus, menuKey, "create")
                || internetNavCan(this.state.internetMenus, "store_declare", "create");
            const viewProps = {
                resModel: act.res_model,
                type: defaultType,
                domain: act.domain || [],
                context: {
                    ...this.parseActionContext(act.context),
                    phan_he_service_type_code: "internet",
                    phan_he_internet_menu: menuCode || (extra.resId ? "internet_active" : "internet_entry"),
                    form_view_initial_mode:
                        (extra.resId === false || extra.resId === undefined
                            ? canCreate
                            : canWrite)
                            ? "edit"
                            : "readonly",
                },
                views,
                display: this.asViewDisplay({ controlPanel: {} }),
                loadActionMenus: true,
                loadIrFilters: false,
                selectRecord: (resId) => {
                    this.openEmbedded(child, {
                        type: "form",
                        resId,
                        action: xmlid,
                        activeNav: this.state.activeNav,
                    });
                },
                createRecord: () => {
                    if (!canCreate && !internetNavCan(this.state.internetMenus, "store_declare", "create")) {
                        this.notification.add("Bạn không có quyền Thêm.", { type: "warning" });
                        return;
                    }
                    this.openEmbedded(child, {
                        type: "form",
                        resId: false,
                        action: xmlid,
                        activeNav: this.state.activeNav,
                    });
                },
            };
            if (defaultType === "form") {
                // onDiscard chỉ hợp lệ với FormController — list (Lịch thanh toán…) sẽ lỗi nếu truyền.
                viewProps.onDiscard = () => this.closeEmbeddedView();
            }
            if (typedView && typedView[0]) {
                viewProps.viewId = typedView[0];
            }
            if (defaultType === "form") {
                viewProps.resId = extra.resId === undefined ? false : extra.resId;
                const openingNew = !viewProps.resId;
                viewProps.readonly = openingNew ? !canCreate : !canWrite;
                viewProps.preventEdit = !canWrite;
                viewProps.preventCreate = !canCreate;
            }
            this.state.embeddedViewProps = viewProps;
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Không mở được form khai báo.",
                { type: "danger" }
            );
        }
    }

    openReportPeriod(period) {
        const now = new Date();
        const year = now.getFullYear();
        const month = now.getMonth(); // 0-11
        let from;
        let to;
        if (period === "month") {
            from = new Date(year, month, 1);
            to = new Date(year, month + 1, 0);
        } else if (period === "quarter") {
            const qStart = Math.floor(month / 3) * 3;
            from = new Date(year, qStart, 1);
            to = new Date(year, qStart + 3, 0);
        } else {
            from = new Date(year, 0, 1);
            to = new Date(year, 11, 31);
        }
        this.state.reportPeriod = period;
        this.state.filters.year = year;
        this.state.filters.date_from = `${pad2(from.getDate())}/${pad2(from.getMonth() + 1)}/${from.getFullYear()}`;
        this.state.filters.date_to = `${pad2(to.getDate())}/${pad2(to.getMonth() + 1)}/${to.getFullYear()}`;
        this._openGroupForNav("reports");
        this.state.embeddedViewProps = null;
        if (period === "month" && this.serviceTypeCode === "internet") {
            this.state.activeNav = "report_month";
            this.state.contentMode = "month_cost";
            this.state.loading = false;
            return;
        }
        if (period === "quarter" && this.serviceTypeCode === "internet") {
            this.state.activeNav = "report_quarter";
            this.state.contentMode = "quarter_cost";
            this.state.loading = false;
            return;
        }
        this.state.activeNav = "reports";
        this.state.contentMode = "dashboard";
        this.loadPaymentReport();
    }

    onNav(item) {
        if (!item) {
            return;
        }
        if (item.id === "overview") {
            this.state.activeNav = "overview";
            return;
        }
        if (item.id === "reports") {
            this.state.activeNav = "reports";
            this.loadPaymentReport();
            return;
        }
        if (item.id === "alerts") {
            this.toggleGroup("alerts");
            return;
        }
        if (!item.action) {
            return;
        }
        this.openAction(item.action);
    }

    onAlertClick(alert) {
        if (alert && alert.action) {
            this.openAction(alert.action);
        }
    }

    async loadInternetDash() {
        this.state.loading = true;
        try {
            const parts = String(this.state.selectedMonth || "").split("-");
            const year = Number(parts[0]) || new Date().getFullYear();
            const month = Number(parts[1]) || new Date().getMonth() + 1;
            const region =
                this.state.selectedRegion && this.state.selectedRegion !== "all"
                    ? this.state.selectedRegion
                    : false;
            const store =
                this.state.selectedStore && this.state.selectedStore !== "all"
                    ? this.state.selectedStore
                    : false;
            const data = await this.orm.call("phan.he.service", "get_dashboard_data", [
                month,
                year,
                region,
                store,
            ]);
            this.state.inet = data || {};
            if (data?.selected_month) {
                this.state.selectedMonth = data.selected_month;
            }
            this.state.data = {
                ...(this.state.data || {}),
                ...(data || {}),
                expire_soon: data?.expire_soon ?? this.state.data?.expire_soon ?? 0,
                overdue_contract: data?.overdue_contract ?? this.state.data?.overdue_contract ?? 0,
                payment_forecast: data?.payment_forecast ?? this.state.data?.payment_forecast ?? 0,
            };
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được dashboard Internet.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onInetMonthChange(ev) {
        this.state.selectedMonth = ev.target.value;
        await this.loadInternetDash();
    }

    async onInetRegionChange(ev) {
        this.state.selectedRegion = ev.target.value;
        this.state.selectedStore = "all";
        await this.loadInternetDash();
    }

    async onInetStoreChange(ev) {
        this.state.selectedStore = ev.target.value;
        await this.loadInternetDash();
    }

    destroyInetCharts() {
        Object.values(this.inetCharts || {}).forEach((chart) => {
            try {
                chart.destroy();
            } catch (e) {
                /* ignore */
            }
        });
        this.inetCharts = {};
        [this.inetSparkRef, this.inetDonutRef, this.inetYearRef, this.inetMonthTrendRef].forEach((ref) => {
            const el = ref && ref.el;
            if (!el || typeof Chart === "undefined" || !Chart.getChart) {
                return;
            }
            const existing = Chart.getChart(el);
            if (existing) {
                existing.destroy();
            }
        });
    }

    _inetChartOrNull(ref) {
        return ref && ref.el ? ref.el.getContext("2d") : null;
    }

    renderInetCharts() {
        if (typeof Chart === "undefined") {
            return;
        }
        this.destroyInetCharts();
        const inet = this.state.inet || {};
        const money = (v) => this.formatMoney(v);
        const spark = inet.trend && inet.trend.length ? inet.trend : inet.month_weeks || [];
        const sparkCtx = this._inetChartOrNull(this.inetSparkRef);
        if (sparkCtx) {
            this.inetCharts.spark = new Chart(sparkCtx, {
                type: "line",
                data: {
                    labels: spark.map((p) => p.label || p.full),
                    datasets: [{
                        data: spark.map((p) => Number(p.amount || 0)),
                        borderColor: "#6b7cff",
                        backgroundColor: "rgba(107, 124, 255, 0.16)",
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                        pointBackgroundColor: "#fff",
                        pointBorderColor: "#6b7cff",
                        borderWidth: 2.4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    layout: { padding: { top: 8, right: 6, left: 2, bottom: 0 } },
                    scales: {
                        x: { grid: { display: false }, ticks: { font: { size: 10 }, color: "#94a3b8" } },
                        y: { display: false, beginAtZero: true },
                    },
                },
            });
        }
        const donutCtx = this._inetChartOrNull(this.inetDonutRef);
        if (donutCtx) {
            const regions = inet.regions || [];
            this.inetCharts.donut = new Chart(donutCtx, {
                type: "doughnut",
                data: {
                    labels: regions.map((r) => r.name),
                    datasets: [{
                        data: regions.map((r) => Number(r.amount || 0)),
                        backgroundColor: regions.map((r) => r.color || "#94a3b8"),
                        borderWidth: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "68%",
                    plugins: { legend: { display: false } },
                },
            });
        }
        const yearCtx = this._inetChartOrNull(this.inetYearRef);
        if (yearCtx) {
            const bars = inet.year_bars || [];
            this.inetCharts.year = new Chart(yearCtx, {
                type: "bar",
                data: {
                    labels: bars.map((b) => String(b.year)),
                    datasets: [{
                        data: bars.map((b) => Number(b.amount || 0)),
                        backgroundColor: bars.map((b) => (b.is_current ? "#5b4cf5" : "#d6dcff")),
                        borderRadius: 6,
                        barPercentage: 0.55,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 10 } } },
                        y: { display: false },
                    },
                },
            });
        }
        const trendCtx = this._inetChartOrNull(this.inetMonthTrendRef);
        if (trendCtx) {
            this.inetCharts.monthTrend = this._buildMonthDayChart(trendCtx, inet);
        }
    }

    setMonthChartMode(mode) {
        const next = mode === "line" ? "line" : "bar";
        if (this.state.monthChartMode === next) {
            return;
        }
        this.state.monthChartMode = next;
    }

    _formatAxisVnd(v) {
        const n = Number(v || 0);
        if (n >= 1e6) {
            return `${formatNumber(Math.round(n))} đ`;
        }
        return `${formatNumber(n)} đ`;
    }

    _formatBarTopAmount(v) {
        const n = Number(v || 0);
        if (n <= 0) {
            return "";
        }
        if (n >= 1e6) {
            const tr = n / 1e6;
            const text = tr >= 10 ? tr.toFixed(1) : tr.toFixed(2);
            return `${text.replace(".", ",")} Tr`;
        }
        if (n >= 1e3) {
            return `${formatNumber(Math.round(n / 1000))} N`;
        }
        return formatNumber(n);
    }

    _monthChartValueLabelsPlugin(totals) {
        const formatTop = (v) => this._formatBarTopAmount(v);
        return {
            id: "lqMonthValueLabels",
            afterDatasetsDraw(chart) {
                const { ctx } = chart;
                const metaBars = chart.data.datasets
                    .map((ds, i) => ({ ds, i, meta: chart.getDatasetMeta(i) }))
                    .filter((x) => x.ds.type === "bar" || (!x.ds.type && chart.config.type === "bar"));
                const metaLine = chart.data.datasets
                    .map((ds, i) => ({ ds, i, meta: chart.getDatasetMeta(i) }))
                    .find((x) => x.ds.label === "Tổng chi phí");

                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "bottom";
                ctx.fillStyle = "#334155";
                ctx.font = "700 11px system-ui, -apple-system, Segoe UI, sans-serif";

                const n = (totals || []).length;
                for (let i = 0; i < n; i++) {
                    const value = Number(totals[i] || 0);
                    if (value <= 0) {
                        continue;
                    }
                    let x = null;
                    let y = null;
                    if (metaLine && metaLine.meta?.data?.[i] && !metaLine.meta.hidden) {
                        const pt = metaLine.meta.data[i];
                        x = pt.x;
                        y = pt.y;
                    } else if (metaBars.length) {
                        // đỉnh cột xếp chồng = dataset bar trên cùng có giá trị
                        for (let b = metaBars.length - 1; b >= 0; b--) {
                            const bar = metaBars[b].meta?.data?.[i];
                            if (bar && Number(metaBars[b].ds.data?.[i] || 0) > 0) {
                                x = bar.x;
                                y = bar.y;
                                break;
                            }
                        }
                    }
                    if (x == null || y == null) {
                        continue;
                    }
                    ctx.fillText(formatTop(value), x, y - 6);
                }
                ctx.restore();
            },
        };
    }

    _buildMonthDayChart(ctx, inet) {
        const chart = inet.month_day_chart || {};
        const labels = chart.days || [];
        const regions = chart.regions || [];
        const totals = (chart.totals || []).map((v) => Number(v || 0));
        const mode = this.state.monthChartMode === "line" ? "line" : "bar";
        const money = (v) => this.formatMoney(v);
        const peak = Math.max(...totals, 0);
        const yMax = peak > 0 ? peak * 1.22 : 1000000;
        const sampleColors = {
            NAM: "#3b82f6",
            DTT: "#22c55e",
            BAC: "#f59e0b",
            VP: "#8b5cf6",
            TRUNG: "#f59e0b",
        };
        const regionDatasets = regions.map((r, idx) => {
            const code = String(r.code || "").toUpperCase();
            const color = sampleColors[code] || r.color || "#94a3b8";
            const base = {
                label: r.name || r.short || r.code,
                data: (r.amounts || []).map((v) => Number(v || 0)),
                backgroundColor: color,
                borderColor: color,
                borderWidth: mode === "line" ? 2.5 : 0,
                fill: false,
                tension: 0.35,
                pointRadius: mode === "line" ? 3.5 : 0,
                pointHoverRadius: 5,
                order: 2 + idx,
                yAxisID: "y",
            };
            if (mode === "bar") {
                return {
                    ...base,
                    type: "bar",
                    stack: "regions",
                    borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
                    borderSkipped: false,
                    barPercentage: 0.65,
                    categoryPercentage: 0.75,
                    maxBarThickness: 42,
                };
            }
            return { ...base, type: "line" };
        });
        const totalDataset = {
            type: "line",
            label: "Tổng chi phí",
            data: totals,
            borderColor: "#7c3aed",
            backgroundColor: "#7c3aed",
            borderWidth: 2.75,
            pointRadius: 4.5,
            pointHoverRadius: 6,
            pointBackgroundColor: "#7c3aed",
            pointBorderColor: "#fff",
            pointBorderWidth: 2,
            fill: false,
            tension: 0.35,
            order: 0,
            yAxisID: mode === "bar" ? "y1" : "y",
        };
        return new Chart(ctx, {
            type: mode,
            data: {
                labels,
                datasets: [...regionDatasets, totalDataset],
            },
            plugins: [this._monthChartValueLabelsPlugin(totals)],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { top: 22, right: 8, bottom: 0, left: 4 } },
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: "bottom",
                        align: "center",
                        labels: {
                            usePointStyle: true,
                            pointStyle: "circle",
                            boxWidth: 9,
                            boxHeight: 9,
                            padding: 18,
                            color: "#64748b",
                            font: { size: 12, weight: "600" },
                        },
                    },
                    tooltip: {
                        backgroundColor: "rgba(15, 23, 42, 0.92)",
                        titleFont: { size: 12, weight: "700" },
                        bodyFont: { size: 12 },
                        padding: 10,
                        cornerRadius: 10,
                        callbacks: {
                            title: (items) => {
                                const idx = items?.[0]?.dataIndex;
                                const monthNo = Number(idx) + 1;
                                return `Tháng ${monthNo}/${chart.year || ""}`;
                            },
                            label: (c) => ` ${c.dataset.label}: ${money(c.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: {
                        stacked: mode === "bar",
                        grid: { display: false, drawBorder: false },
                        border: { display: false },
                        ticks: {
                            color: "#94a3b8",
                            font: { size: 11, weight: "600" },
                            maxRotation: 0,
                            autoSkip: false,
                        },
                        title: {
                            display: true,
                            text: chart.label || "",
                            color: "#475569",
                            font: { size: 13, weight: "700" },
                            padding: { top: 10, bottom: 2 },
                        },
                    },
                    y: {
                        stacked: mode === "bar",
                        beginAtZero: true,
                        suggestedMax: yMax,
                        grid: { color: "#eef2f7", drawBorder: false },
                        border: { display: false },
                        ticks: {
                            color: "#94a3b8",
                            font: { size: 11 },
                            padding: 8,
                            callback: (v) => this._formatAxisVnd(v),
                        },
                    },
                    y1: {
                        display: false,
                        beginAtZero: true,
                        suggestedMax: yMax,
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    formatDelta(delta) {
        const n = Number(delta || 0);
        const sign = n > 0 ? "+" : "";
        return `${sign}${n}%`;
    }

    deltaClass(delta) {
        return Number(delta || 0) >= 0 ? "is-up" : "is-down";
    }

    formatBillion(amount) {
        const n = Number(amount || 0);
        if (n >= 1e9) {
            return `${(n / 1e9).toFixed(2)} tỷ`;
        }
        return this.formatMoney(n);
    }

    openInetRecord(row) {
        if (!row?.id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "phan.he.service",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openInetListActive() {
        this.openInetList("active");
    }

    openInetList(opsStatus) {
        const xml = {
            active: "lug_phan_he.action_phan_he_service_internet_active",
            suspend: "lug_phan_he.action_phan_he_service_internet_suspend",
            liquidated: "lug_phan_he.action_phan_he_service_internet_liquidated",
        }[opsStatus] || "lug_phan_he.action_phan_he_service_tracking";
        this.action.doAction(xml);
    }

    async loadNavBadges(year = null, month = null) {
        try {
            const args = [];
            if (year && month) {
                args.push(Number(year), Number(month));
            }
            const counts = await this.orm.call("phan.he.service", "get_internet_alert_counts", args);
            this.state.data = {
                ...(this.state.data || {}),
                ...(counts || {}),
            };
        } catch (error) {
            console.warn("loadNavBadges", error);
        }
    }

    /** Badge Lịch TT / Dự kiến theo đúng tháng đang chọn trên danh sách. */
    onPeriodPaymentCountChange({ count, filter, year, month }) {
        const n = Number(count) || 0;
        const y = year ? Number(year) : 0;
        const m = month ? Number(month) : 0;
        const data = this.state.data || {};
        const same =
            Number(data.payment_period_year || 0) === y
            && Number(data.payment_period_month || 0) === m
            && (
                (filter === "payment_due" && Number(data.payment_schedule) === n)
                || (filter === "payment_forecast" && Number(data.payment_forecast) === n)
                || (filter === "payment_confirm" && Number(data.payment_confirm) === n)
                || (!filter && Number(data.payment_schedule) === n)
            );
        if (same) {
            return;
        }
        const patch = {};
        if (y) {
            patch.payment_period_year = y;
        }
        if (m) {
            patch.payment_period_month = m;
        }
        if (filter === "payment_due") {
            patch.payment_schedule = n;
        } else if (filter === "payment_forecast") {
            patch.payment_forecast = n;
        } else if (filter === "payment_confirm") {
            patch.payment_confirm = n;
        } else {
            patch.payment_schedule = n;
            patch.payment_forecast = n;
        }
        this.state.data = {
            ...(this.state.data || {}),
            ...patch,
        };
    }

    async load() {
        if (this.isLinkqErp) {
            this.state.loading = false;
            this.state.data = this.state.data || {};
            return;
        }
        if (this.serviceTypeCode === "internet" && this.state.contentMode === "owl_list") {
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "internet" && this.state.contentMode === "payment_board") {
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "internet" && (this.state.contentMode === "month_cost" || this.state.contentMode === "quarter_cost")) {
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "internet" && this.state.activeNav !== "reports") {
            await this.loadInternetDash();
            return;
        }
        const year = Number(this.state.filters.year || new Date().getFullYear());
        this.state.filters.year = year;
        this.state.filters.date_from = yearStartDisplay(year);
        this.state.filters.date_to = yearEndDisplay(year);
        const dateFrom = displayToIso(this.state.filters.date_from);
        const dateTo = displayToIso(this.state.filters.date_to);
        if (!dateFrom || !dateTo) {
            this.notification.add("Ngày phải theo định dạng dd/mm/yyyy (ví dụ 01/01/2026).", {
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const f = this.state.filters;
            this.state.data = await this.orm.call("phan.he.dashboard", "get_dashboard_data", [{
                date_from: dateFrom,
                date_to: dateTo,
                mien_id: f.mien_id || false,
                area_id: f.area_id || false,
                employee_id: f.employee_id || false,
                service_type_code: this.serviceTypeCode,
                app_title: this.actionContext.phan_he_app_title || false,
            }]);
            if (this.state.data.year) {
                this.state.filters.year = Number(this.state.data.year);
            }
            if (this.state.data.date_from) {
                this.state.filters.date_from = isoToDisplay(this.state.data.date_from);
            }
            if (this.state.data.date_to) {
                this.state.filters.date_to = isoToDisplay(this.state.data.date_to);
            }
            if (this.state.activeNav === "reports") {
                await this.loadPaymentReport({ silent: true });
            }
        } finally {
            this.state.loading = false;
        }
    }

    _filterPayload() {
        const f = this.state.filters;
        return {
            date_from: displayToIso(f.date_from),
            date_to: displayToIso(f.date_to),
            mien_id: f.mien_id || false,
            area_id: f.area_id || false,
            employee_id: f.employee_id || false,
            service_type_code: this.serviceTypeCode,
        };
    }

    async loadPaymentReport({ silent = false } = {}) {
        const payload = this._filterPayload();
        if (!payload.date_from || !payload.date_to) {
            this.notification.add("Ngày phải theo định dạng dd/mm/yyyy (ví dụ 01/01/2026).", {
                type: "warning",
            });
            return;
        }
        if (!silent) {
            this.state.loading = true;
        }
        try {
            this.state.paymentReport = await this.orm.call(
                "phan.he.dashboard",
                "get_payment_status_report",
                [payload]
            );
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được báo cáo thanh toán.",
                { type: "danger" }
            );
        } finally {
            if (!silent) {
                this.state.loading = false;
            }
        }
    }

    openPayment(row) {
        if (!row?.id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "phan.he.payment",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    formatIsoDate(value) {
        return isoToDisplay(value) || "—";
    }

    async onYearChange(ev) {
        const year = Number(ev.target.value || new Date().getFullYear());
        this.state.filters.year = year;
        await this.load();
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Bang_tong_hop_chi_phi.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async onExportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const year = Number(this.state.filters.year || new Date().getFullYear());
            const result = await this.orm.call(
                "phan.he.dashboard",
                "export_monthly_cost_excel",
                [{
                    date_from: `${year}-01-01`,
                    date_to: `${year}-12-31`,
                    mien_id: this.state.filters.mien_id || false,
                    area_id: this.state.filters.area_id || false,
                    employee_id: this.state.filters.employee_id || false,
                    service_type_code: this.serviceTypeCode,
                    app_title: this.actionContext.phan_he_app_title || false,
                }]
            );
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add("Đã xuất file Excel.", { type: "success" });
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không xuất được Excel.",
                { type: "danger" }
            );
        } finally {
            this.state.exporting = false;
        }
    }

    async onFilter() {
        // Đồng bộ năm từ date_from nếu user đổi khoảng ngày ở thanh lọc trên
        const iso = displayToIso(this.state.filters.date_from);
        if (iso) {
            this.state.filters.year = Number(iso.slice(0, 4));
        }
        await this.load();
    }

    async onRefresh() {
        const year = new Date().getFullYear();
        this.state.filters.year = year;
        this.state.filters.date_from = yearStartDisplay(year);
        this.state.filters.date_to = yearEndDisplay(year);
        this.state.filters.mien_id = "";
        this.state.filters.area_id = "";
        this.state.filters.employee_id = "";
        await this.load();
    }

    onMienChange() {
        this.state.filters.area_id = "";
    }

    formatMoney(amount) {
        const symbol = this.state.data.currency_symbol || "đ";
        return `${formatNumber(amount)} ${symbol}`;
    }

    formatMoneyVnd(amount) {
        return `${formatNumber(amount)} VNĐ`;
    }

    formatNumber(amount) {
        return formatNumber(amount);
    }

    formatPct(v) {
        return `${Number(v || 0).toFixed(1)}%`;
    }

    padCount(n) {
        return String(Number(n || 0)).padStart(2, "0");
    }

    regionTone(code, index) {
        const c = String(code || "").toUpperCase();
        if (c === "BAC") {
            return "is-bac";
        }
        if (c === "NAM") {
            return "is-nam";
        }
        if (c === "TRUNG" || c === "DTT") {
            return "is-trung";
        }
        return `is-tone-${index % 4}`;
    }

    pieStyle(rows) {
        // giữ để tương thích; donut dùng SVG
        const list = rows || [];
        const total = list.reduce((s, r) => s + Number(r.amount || 0), 0) || 1;
        let acc = 0;
        const parts = list.map((r) => {
            const start = (acc / total) * 360;
            acc += Number(r.amount || 0);
            const end = (acc / total) * 360;
            return `${r.color} ${start}deg ${end}deg`;
        });
        return parts.length
            ? `background: conic-gradient(${parts.join(", ")})`
            : "background: conic-gradient(#e5e7eb 0 360deg)";
    }

    /**
     * Donut SVG chuẩn — từng lát cung khép kín, không méo như conic-gradient.
     */
    donutSlices() {
        const rows = this.costStructureRows().filter((r) => Number(r.amount || 0) > 0);
        const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0) || 1;
        const cx = 90;
        const cy = 90;
        const rOut = 72;
        const rIn = 44;
        let angle = -Math.PI / 2;
        const slices = [];

        const polar = (radius, a) => ({
            x: cx + radius * Math.cos(a),
            y: cy + radius * Math.sin(a),
        });

        for (const row of rows) {
            const portion = Number(row.amount || 0) / total;
            if (portion <= 0) {
                continue;
            }
            // tránh cung 360° (SVG không vẽ được start===end)
            const sweep = Math.min(portion * 2 * Math.PI, 2 * Math.PI - 0.0001);
            const end = angle + sweep;
            const large = sweep > Math.PI ? 1 : 0;
            const p0 = polar(rOut, angle);
            const p1 = polar(rOut, end);
            const p2 = polar(rIn, end);
            const p3 = polar(rIn, angle);
            const d = [
                `M ${p0.x.toFixed(3)} ${p0.y.toFixed(3)}`,
                `A ${rOut} ${rOut} 0 ${large} 1 ${p1.x.toFixed(3)} ${p1.y.toFixed(3)}`,
                `L ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`,
                `A ${rIn} ${rIn} 0 ${large} 0 ${p3.x.toFixed(3)} ${p3.y.toFixed(3)}`,
                "Z",
            ].join(" ");
            slices.push({
                id: row.id,
                color: row.color,
                d,
                name: row.name,
                pct: row.pct,
            });
            angle = end;
        }
        return slices;
    }

    costStructureTotal() {
        return (this.state.data.cost_structure || []).reduce(
            (s, r) => s + Number(r.amount || 0),
            0
        );
    }

    costStructureRows() {
        return [...(this.state.data.cost_structure || [])].sort(
            (a, b) => Number(b.amount || 0) - Number(a.amount || 0)
        );
    }

    formatTrieu(amount) {
        const n = Number(amount || 0) / 1e6;
        if (n >= 10) {
            return `${n.toFixed(1)} Tr. VNĐ`;
        }
        return `${n.toFixed(1)} Tr. VNĐ`;
    }

    monthLabelPad() {
        const m = Number(this.state.data.current_month || 0);
        return m ? pad2(m) : "—";
    }

    /**
     * Multi-line chart (không stack): Tổng + từng miền, trục Y = Triệu VNĐ.
     * Hover theo tháng → tooltip.
     */
    multiLineTrendChart() {
        const series = this.state.data.trend_series || [];
        const months = this.state.data.trend_months || [];
        const n = 12;
        const W = 720;
        const H = 280;
        const padL = 48;
        const padR = 18;
        const padT = 18;
        const padB = 36;
        const cw = W - padL - padR;
        const ch = H - padT - padB;

        const allVals = series.flatMap((s) => (s.values || []).map((v) => Number(v || 0)));
        const maxRaw = Math.max(...allVals, 1);
        const maxTrieu = maxRaw / 1e6;
        const step = maxTrieu <= 10 ? 2 : maxTrieu <= 30 ? 5 : maxTrieu <= 100 ? 25 : 50;
        const niceMax = Math.max(step, Math.ceil(maxTrieu / step) * step) || step;
        const yMax = niceMax * 1e6;

        const grid = [];
        const ticks = Math.round(niceMax / step);
        for (let t = 0; t <= ticks; t++) {
            const val = step * t;
            const y = padT + ch - (val / niceMax) * ch;
            grid.push({ y, label: `${val}M` });
        }

        const xAt = (i) => padL + (i / Math.max(n - 1, 1)) * cw;
        const yAt = (v) => padT + ch - (Number(v || 0) / yMax) * ch;

        const lines = series.map((s) => {
            const points = [];
            for (let i = 0; i < n; i++) {
                const v = Number((s.values || [])[i] || 0);
                points.push({ x: xAt(i), y: yAt(v), value: v, monthIndex: i });
            }
            return {
                id: s.id,
                name: s.name,
                short: s.short,
                color: s.color,
                isTotal: !!s.is_total,
                linePoints: points.map((p) => `${p.x},${p.y}`).join(" "),
                dots: points,
            };
        });

        const xLabels = Array.from({ length: n }, (_, i) => ({
            x: xAt(i),
            text: months[i] || `T${i + 1}`,
        }));

        const hover = this.state.trendHover;
        let tooltip = null;
        if (hover != null && hover >= 0 && hover < n) {
            const x = xAt(hover);
            tooltip = {
                monthIndex: hover,
                label: months[hover] || `T${hover + 1}`,
                x,
                items: lines.map((line) => ({
                    id: line.id,
                    name: line.name,
                    color: line.color,
                    value: line.dots[hover]?.value || 0,
                    y: line.dots[hover]?.y,
                })),
            };
        }

        return {
            W,
            H,
            padL,
            padT,
            padB,
            cw,
            ch,
            grid,
            lines,
            xLabels,
            tooltip,
            baselineY: padT + ch,
            hitZones: Array.from({ length: n }, (_, i) => {
                const x = xAt(i);
                const half = cw / Math.max(n - 1, 1) / 2;
                return {
                    index: i,
                    x: Math.max(padL, x - half),
                    width: Math.min(padL + cw, x + half) - Math.max(padL, x - half),
                };
            }),
        };
    }

    onTrendHover(index) {
        this.state.trendHover = index;
    }

    onTrendLeave() {
        this.state.trendHover = null;
    }

    /** @deprecated giữ tên cũ để tránh vỡ nếu template cũ còn cache */
    stackedTrendChart() {
        return this.multiLineTrendChart();
    }

    topBranchRows() {
        return this.state.data.top_branches || [];
    }

    filteredAreas() {
        const mid = this.state.filters.mien_id;
        const areas = this.state.data.areas || [];
        if (!mid) {
            return areas;
        }
        return areas.filter((a) => String(a.mien_id) === String(mid));
    }

    openAction(xmlid) {
        const child = this.findNavChildByAction(xmlid) || { id: this.state.activeNav, action: xmlid };
        this.openEmbedded(child);
    }

    findNavChildByAction(xmlid) {
        for (const section of this.navSections || []) {
            const child = (section.children || []).find((c) => c.action === xmlid);
            if (child) {
                return child;
            }
        }
        return null;
    }
}

registry.category("actions").add("phan_he_dashboard", PhanHeDashboard);
