/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState, useSubEnv } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";
import { PhanHeInternetShell } from "../internet_shell/phan_he_internet_shell";
import { PhanHeInternetListBoard, PhanHeMonthCostBoard, PhanHeQuarterCostBoard } from "../internet_list/phan_he_internet_list";
import { PhanHeYearCostBoard } from "./year_cost_board";
import { PhanHePaymentBoard } from "../payment_board/phan_he_payment_board";
import { PhanHeCostEstimateBoard } from "../cost_estimate/phan_he_cost_estimate";
import { PhanHeInternetEntryPopup } from "../internet_entry/phan_he_internet_entry_popup";
import { PhanHeItAssetEntryPopup } from "../it_entry/phan_he_it_asset_entry_popup";
import { PhanHeItCostEntryPopup } from "../it_entry/phan_he_it_cost_entry_popup";
import { PhanHeItCostReport } from "../it_report/phan_he_it_cost_report";
import {
    INTERNET_NAV_TO_CODE,
    filterInternetNavSections,
    firstAllowedInternetNav,
    internetMenuCan,
    internetNavCan,
} from "../access/internet_menu_nav";
import {
    filterServerNavSections,
    firstAllowedServerNav,
    serverNavCan,
    serverNavCreate,
} from "../access/server_menu_nav";

const IT_COST_REPORTS = {
    it_report_month: "month",
    it_report_quarter: "quarter",
    it_report_year: "year",
    it_report_by_asset: "asset",
    it_report_by_provider: "provider",
    it_cost_estimate: "estimate",
    it_cost_schedule: "schedule",
};

const IT_COST_POPUP_ACTIONS = new Set([
    "lug_phan_he.action_phan_he_it_cost",
    "lug_phan_he.action_phan_he_it_cost_overdue",
    "lug_phan_he.action_phan_he_it_cost_schedule",
    "lug_phan_he.action_phan_he_it_cost_estimate",
    "lug_phan_he.action_phan_he_it_cost_by_asset",
    "lug_phan_he.action_phan_he_it_cost_by_provider",
    "lug_phan_he.action_phan_he_it_cost_report_month",
    "lug_phan_he.action_phan_he_it_cost_report_quarter",
    "lug_phan_he.action_phan_he_it_cost_report_year",
]);

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

const SERVER_NAV_SECTIONS = [
    {
        id: "manage",
        label: "Quản lý tài sản",
        icon: "fa-server",
        iconTone: "manage",
        children: [
            {
                id: "it_asset_all",
                label: "Danh sách tài sản",
                icon: "fa-desktop",
                iconTone: "list",
                action: "lug_phan_he.action_phan_he_it_asset",
            },
            {
                id: "it_asset_physical",
                label: "Máy chủ vật lý",
                icon: "fa-hdd-o",
                iconTone: "physical",
                action: "lug_phan_he.action_phan_he_it_asset_physical",
            },
            {
                id: "it_asset_virtual",
                label: "Máy chủ ảo",
                icon: "fa-cubes",
                iconTone: "virtual",
                action: "lug_phan_he.action_phan_he_it_asset_virtual",
            },
            {
                id: "it_asset_network",
                label: "Thiết bị mạng & bảo mật",
                icon: "fa-sitemap",
                iconTone: "network",
                action: "lug_phan_he.action_phan_he_it_asset_network",
            },
            {
                id: "it_asset_new",
                label: "Thêm mới",
                icon: "fa-plus-circle",
                iconTone: "store",
                // Mở popup đóng khung (không embed form Odoo).
                popup: "it_asset",
            },
        ],
    },
    {
        id: "payment",
        label: "Chi phí & gia hạn",
        icon: "fa-credit-card",
        iconTone: "payment",
        children: [
            {
                id: "it_cost_new",
                label: "Thêm mới",
                icon: "fa-plus-circle",
                iconTone: "store",
                popup: "it_cost",
            },
            {
                id: "it_cost_list",
                label: "Danh sách chi phí",
                icon: "fa-list-alt",
                iconTone: "payment",
                action: "lug_phan_he.action_phan_he_it_cost",
            },
            {
                id: "it_cost_overdue",
                label: "Quá hạn",
                icon: "fa-times-circle",
                tone: "danger",
                iconTone: "overdue",
                action: "lug_phan_he.action_phan_he_it_cost_overdue",
            },
            {
                id: "it_cost_schedule",
                label: "Lịch gia hạn",
                icon: "fa-calendar",
                iconTone: "payment",
                action: "lug_phan_he.action_phan_he_it_cost_schedule",
            },
            {
                id: "it_cost_estimate",
                label: "Dự toán chi phí",
                icon: "fa-calculator",
                iconTone: "payment",
                action: "lug_phan_he.action_phan_he_it_cost_estimate",
            },
        ],
    },
    {
        id: "support",
        label: "Bảo trì & hỗ trợ",
        icon: "fa-wrench",
        iconTone: "alert",
        children: [
            {
                id: "it_ticket_maint",
                label: "Lịch sử bảo trì",
                icon: "fa-wrench",
                iconTone: "alert",
                action: "lug_phan_he.action_phan_he_it_ticket_maintenance",
            },
        ],
    },
    {
        id: "reports",
        label: "Báo cáo",
        icon: "fa-bar-chart",
        iconTone: "report",
        children: [
            {
                id: "it_report_month",
                label: "Chi phí tháng",
                icon: "fa-calendar",
                iconTone: "report",
                action: "lug_phan_he.action_phan_he_it_cost_report_month",
            },
            {
                id: "it_report_quarter",
                label: "Chi phí quý",
                icon: "fa-calendar-o",
                iconTone: "report",
                action: "lug_phan_he.action_phan_he_it_cost_report_quarter",
            },
            {
                id: "it_report_year",
                label: "Chi phí năm",
                icon: "fa-calendar-check-o",
                iconTone: "report",
                action: "lug_phan_he.action_phan_he_it_cost_report_year",
            },
            {
                id: "it_report_by_asset",
                label: "Chi phí theo tài sản",
                icon: "fa-server",
                iconTone: "report",
                action: "lug_phan_he.action_phan_he_it_cost_by_asset",
            },
            {
                id: "it_report_by_provider",
                label: "Chi phí theo nhà cung cấp",
                icon: "fa-building",
                iconTone: "report",
                action: "lug_phan_he.action_phan_he_it_cost_by_provider",
            },
        ],
    },
    {
        id: "settings",
        label: "Cài đặt",
        icon: "fa-cog",
        iconTone: "list",
        children: [
            {
                id: "it_settings_type",
                label: "Danh mục loại tài sản",
                icon: "fa-tags",
                iconTone: "list",
                action: "lug_phan_he.action_phan_he_it_asset_type",
            },
            {
                id: "it_settings_category",
                label: "Danh mục hạng mục chi phí",
                icon: "fa-list",
                iconTone: "list",
                action: "lug_phan_he.action_phan_he_it_cost_category",
            },
            {
                id: "settings_provider",
                label: "Nhà cung cấp",
                icon: "fa-building",
                iconTone: "list",
                action: "lug_phan_he.action_phan_he_provider",
            },
            {
                id: "it_settings_cycle",
                label: "Chu kỳ gia hạn",
                icon: "fa-refresh",
                iconTone: "payment",
                action: "lug_phan_he.action_phan_he_it_renewal_cycle",
            },
            {
                id: "it_settings_remind",
                label: "Cấu hình nhắc hạn",
                icon: "fa-bell",
                iconTone: "alert",
                action: "lug_phan_he.action_phan_he_it_reminder_config",
            },
        ],
    },
];

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
                label: "Thêm mới",
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
            {
                id: "cost_estimate",
                label: "Dự toán chi phí",
                icon: "fa-calculator",
                iconTone: "payment",
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
        PhanHeYearCostBoard,
        PhanHeCostEstimateBoard,
        PhanHePaymentBoard,
        PhanHeInternetEntryPopup,
        PhanHeItAssetEntryPopup,
        PhanHeItCostEntryPopup,
        PhanHeItCostReport,
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
                support: true,
                reports: true,
                settings: false,
                shifts: true,
                alerts: true,
            },
            activeNav: "overview",
            listFilter: "active",
            listReloadToken: 0,
            paymentBoardMode: "confirm",
            paymentBoardToken: 0,
            contentMode: "dashboard",
            itReportKey: "month",
            itReportToken: 0,
            embeddedViewProps: null,
            viewKey: 0,
            listActionXml: null,
            formReturn: null,
            reportPeriod: "year",
            trendHover: null,
            data: {},
            inet: {},
            it: {},
            internetMenus: {},
            moduleRights: {},
            serverMenus: {},
            paymentReport: { tables: [] },
            entryPopupOpen: false,
            entryPopupResId: false,
            entryCreateMenu: "internet_active",
            itAssetPopupOpen: false,
            itAssetPopupResId: false,
            itCostPopupOpen: false,
            itCostPopupResId: false,
            selectedMonth: `${year}-${pad2(new Date().getMonth() + 1)}`,
            selectedRegion: "all",
            selectedStore: "all",
            inetPeriod: "month",
            itAssetTypeId: "all",
            itAssetState: "all",
            itProviderId: "all",
            itAllocateMode: "cost",
            itPeriodMode: "year",
            itChartMode: "month",
            itDonutMode: "pct",
            monthChartMode: "line",
            filters: {
                year: year,
                date_from: yearStartDisplay(year),
                date_to: yearEndDisplay(year),
                mien_id: "",
                area_id: "",
                employee_id: "",
            },
        });
        this.inetDonutRef = useRef("inetDonut");
        this.inetRegionBarRef = useRef("inetRegionBar");
        this.inetYearLinesRef = useRef("inetYearLines");
        this.inetProvDonutRef = useRef("inetProvDonut");
        this.inetCashflowRef = useRef("inetCashflow");
        this.itMonthRef = useRef("itMonthChart");
        this.itRenewDonutRef = useRef("itRenewDonut");
        this.itKpiDonutRef = useRef("itKpiDonutChart");
        this.itByTypeDonutRef = useRef("itByTypeDonutChart");
        this.itQuarterRef = useRef("itQuarterChart");
        this.itCategoryRef = useRef("itCategoryChart");
        this.itBudgetGaugeRef = useRef("itBudgetGauge");
        this.itYearTrendRef = useRef("itYearTrendChart");
        this.itOpexDonutRef = useRef("itOpexDonut");
        this.itLifecycleRef = useRef("itLifecycleChart");
        this.inetCharts = {};
        this.itCharts = {};
        onWillStart(async () => {
            try {
                if (this.serviceTypeCode === "internet") {
                    const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
                    this.state.moduleRights = rights || {};
                    this.state.internetMenus = rights?.internet_menus || {};
                    // Badge sidebar không chặn mở list — chạy nền.
                    this.loadNavBadges();
                } else if (this.serviceTypeCode === "server") {
                    const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
                    this.state.moduleRights = rights || {};
                    this.state.serverMenus = rights?.server_menus || {};
                    this.loadNavBadges();
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
                if (this.serviceTypeCode === "server") {
                    const menus = this.state.serverMenus;
                    if (openNav && !serverNavCan(menus, openNav === "overview" ? "overview" : openNav)) {
                        openNav = false;
                    }
                    if ((!openNav || openNav === "overview") && !serverNavCan(menus, "overview")) {
                        const first = firstAllowedServerNav(
                            filterServerNavSections(SERVER_NAV_SECTIONS, menus)
                        );
                        openNav = first ? first.id : false;
                    }
                }
                if (openNav === "report_quarter" || openNav === "it_report_quarter") {
                    this.state.contentMode = "quarter_cost";
                    this.state.activeNav = openNav;
                    this._openGroupForNav(openNav);
                    this.state.loading = false;
                    return;
                }
                if (openNav === "report_month" || openNav === "it_report_month") {
                    this.state.contentMode = "month_cost";
                    this.state.activeNav = openNav;
                    this._openGroupForNav(openNav);
                    this.state.loading = false;
                    return;
                }
                if (openNav === "report_year" || openNav === "it_report_year") {
                    this.state.contentMode = "year_cost";
                    this.state.activeNav = openNav;
                    this._openGroupForNav(openNav);
                    this.state.loading = false;
                    return;
                }
                if (openNav === "cost_estimate") {
                    this.state.contentMode = "cost_estimate";
                    this.state.activeNav = "cost_estimate";
                    this._openGroupForNav("cost_estimate");
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
                if (this.serviceTypeCode === "internet" || this.serviceTypeCode === "server") {
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
                        // Dùng onNavChild để Dự toán / báo cáo IT mở đúng board OWL.
                        this.onNavChild(child);
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
                if (!this.isInternetDash || this.state.loading || this.state.contentMode === "owl_list" || this.state.contentMode === "month_cost" || this.state.contentMode === "quarter_cost" || this.state.contentMode === "year_cost" || this.state.contentMode === "cost_estimate" || this.state.contentMode === "payment_board") {
                    return () => {};
                }
                this.renderInetCharts();
                return () => this.destroyInetCharts();
            },
            () => [this.state.inet, this.state.loading, this.state.activeNav, this.state.monthChartMode]
        );
        useEffect(
            () => {
                if (!this.isServerItDash || this.state.loading) {
                    return () => {};
                }
                this.renderItCharts();
                return () => this.destroyItCharts();
            },
            () => [this.state.it, this.state.loading, this.state.activeNav, this.state.monthChartMode, this.state.itAllocateMode, this.state.itPeriodMode, this.state.itChartMode, this.state.itDonutMode]
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
            && this.state.contentMode !== "year_cost"
            && this.state.contentMode !== "cost_estimate"
        );
    }

    get isServerItDash() {
        return (
            this.serviceTypeCode === "server"
            && this.state.activeNav === "overview"
            && this.state.contentMode === "dashboard"
        );
    }

    get isInternetMaster() {
        return this.serviceTypeCode === "internet" || this.serviceTypeCode === "server";
    }

    get isServerDash() {
        return this.serviceTypeCode === "server";
    }

    get isRichCostDash() {
        return this.isInternetDash || this.isServerItDash;
    }

    get overviewTitle() {
        if (this.isServerDash) {
            return "Tổng quan máy chủ";
        }
        return "Tổng quan chi phí & sử dụng Internet";
    }

    get overviewSubtitle() {
        if (this.isServerDash) {
            return "Theo dõi chi phí, ngân sách và hiệu quả sử dụng tài sản máy chủ, thiết bị mạng và dịch vụ.";
        }
        return "Quản lý chi phí – Theo dõi xu hướng – Lập kế hoạch dòng tiền";
    }

    get overviewUsageTitle() {
        return this.isServerDash ? "Tình hình máy chủ" : "Tình hình sử dụng dịch vụ";
    }

    get detailColStore() {
        return this.isServerDash ? "Hostname" : "Cửa hàng";
    }

    get detailColProvider() {
        return this.isServerDash ? "Loại / NCC" : "Gói cước";
    }

    get detailColBandwidth() {
        return this.isServerDash ? "Cấu hình / IP" : "Băng thông";
    }

    get detailUnitLabel() {
        return this.isServerDash ? "máy chủ" : "hợp đồng";
    }

    get storeFilterLabel() {
        return this.isServerDash ? "Tất cả đơn vị" : "Tất cả cửa hàng";
    }

    get serverInventory() {
        return this.state.data.server_inventory || {
            total: 0,
            running: 0,
            suspend: 0,
            liquidated: 0,
            month_cost: 0,
            cpu: 0,
            ram: 0,
            storage: 0,
            unset: 0,
            kinds: [],
            top_servers: [],
        };
    }

    get trendChartTitle() {
        const titles = {
            internet: "Xu hướng chi phí Internet — 12 tháng",
            server: "Xu hướng chi phí máy chủ — 12 tháng",
            camera: "Xu hướng chi phí camera — 12 tháng",
            attendance: "Xu hướng chi phí máy chấm công — 12 tháng",
        };
        return titles[this.serviceTypeCode] || `Xu hướng chi phí — 12 tháng`;
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

    get inetOv() {
        return this.inet.ov || {};
    }

    get inetYear() {
        const parts = String(this.state.selectedMonth || "").split("-");
        return Number(parts[0]) || new Date().getFullYear();
    }

    get inetYearOptions() {
        const y = new Date().getFullYear();
        return [y - 1, y, y + 1, y + 2];
    }

    get it() {
        return this.state.it || {};
    }

    get itKpi() {
        return this.it.kpi || {
            asset_total: 0,
            asset_active: 0,
            asset_inactive: 0,
            asset_delta: 0,
            asset_active_pct: 0,
            expiring_pct: 0,
            month_cost: 0,
            month_delta: 0,
            year_cost: 0,
            year_budget: 0,
            expiring: 0,
            overdue: 0,
            confirm: 0,
        };
    }

    itTypeMeta(name) {
        const n = String(name || "").toLowerCase();
        if (n.includes("ảo") || n.includes("virtual")) {
            return { icon: "fa-cloud", color: "#3b82f6", tile: "#3b82f6" };
        }
        if (n.includes("cloud")) {
            return { icon: "fa-cloud", color: "#0ea5e9", tile: "#0ea5e9" };
        }
        if (n.includes("bảo mật") || n.includes("security")) {
            return { icon: "fa-shield", color: "#ef4444", tile: "#ef4444" };
        }
        if (n.includes("mạng") || n.includes("network")) {
            return { icon: "fa-sitemap", color: "#22c55e", tile: "#22c55e" };
        }
        if (n.includes("phần mềm") || n.includes("bản quyền")) {
            return { icon: "fa-key", color: "#f59e0b", tile: "#f59e0b" };
        }
        if (n.includes("vật lý") || n.includes("physical") || n.includes("máy chủ")) {
            return { icon: "fa-server", color: "#6366f1", tile: "#6366f1" };
        }
        return { icon: "fa-cube", color: "#64748b", tile: "#64748b" };
    }

    get itByTypeBars() {
        return (this.it.by_type || []).map((tp) => {
            const meta = this.itTypeMeta(tp.name);
            return {
                id: tp.id,
                name: tp.name || "—",
                color: meta.color,
                barColor: "#818cf8",
                icon: meta.icon,
                amount: Number(tp.amount || 0),
                pct: Math.max(Number(tp.pct || 0), 0),
                count: Number(tp.count || 0),
            };
        });
    }

    get itByTypeTotal() {
        return (this.it.by_type || []).reduce((s, r) => s + Number(r.amount || 0), 0);
    }

    get itRenewalStatus() {
        return this.it.renewal_status || [];
    }

    get itRenewalSchedule() {
        return this.it.renewal_schedule || [];
    }

    get itAllocateBlocks() {
        const mode = this.state.itAllocateMode || "cost";
        const rows = this.it.allocate || this.it.by_type || [];
        const mapped = rows.map((r) => {
            const meta = this.itTypeMeta(r.name);
            const amount = Number(r.amount || 0);
            const count = Number(r.count || 0);
            const weight = mode === "count" ? count : amount;
            return {
                id: r.id,
                name: r.name || "—",
                color: meta.tile,
                icon: meta.icon,
                amount,
                count,
                weight,
                display: mode === "count" ? `${count} tài sản` : this.formatMoney(amount),
            };
        });
        const sum = mapped.reduce((a, r) => a + Math.max(r.weight, 0), 0) || 1;
        return mapped.map((r) => ({
            ...r,
            pct: Math.round((Math.max(r.weight, 0) / sum) * 1000) / 10,
        }));
    }

    get itTodoRows() {
        const fmt = (d) => {
            const raw = String(d || "").trim();
            const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
            return m ? `${m[3]}/${m[2]}/${m[1]}` : raw || "—";
        };
        return (this.it.todo || []).map((row, idx) => ({
            ...row,
            stt: idx + 1,
            date_start: fmt(row.date_start),
            date_end: fmt(row.date_end || row.date),
        }));
    }

    get itTodoPageInfo() {
        const n = (this.it.todo || []).length;
        if (!n) {
            return "Hiển thị 0 trên 0 tài sản";
        }
        return `Hiển thị 1-${n} trên ${n} tài sản`;
    }

    pad2(n) {
        return pad2(n);
    }

    deltaClass(v) {
        const n = Number(v || 0);
        if (n > 0) {
            return "is-up";
        }
        if (n < 0) {
            return "is-down";
        }
        return "is-muted";
    }

    deltaText(v) {
        const n = Number(v || 0);
        const abs = Math.abs(n);
        const s = String(abs.toFixed(1)).replace(/\.0$/, "").replace(".", ",");
        if (n > 0) {
            return `↑ ${s}%`;
        }
        if (n < 0) {
            return `↓ ${s}%`;
        }
        return "0%";
    }

    setItAllocateMode(mode) {
        this.state.itAllocateMode = mode === "count" ? "count" : "cost";
    }

    setItPeriodMode(mode) {
        const next = ["year", "quarter", "month"].includes(mode) ? mode : "year";
        this.state.itPeriodMode = next;
        this.state.itChartMode = next === "year" ? "month" : next;
    }

    setItChartMode(mode) {
        const allowed = ["month", "quarter", "year", "category"];
        this.state.itChartMode = allowed.includes(mode) ? mode : "month";
    }

    setItDonutMode(mode) {
        this.state.itDonutMode = mode === "value" ? "value" : "pct";
    }

    get itHeaderYear() {
        return Number(String(this.state.selectedMonth || "").split("-")[0]) || new Date().getFullYear();
    }

    get itYearChoices() {
        const y = new Date().getFullYear();
        return [y - 1, y, y + 1, y + 2];
    }

    onItHeaderYearChange(ev) {
        const year = ev.target.value;
        const month = String(this.state.selectedMonth || "").split("-")[1] || pad2(new Date().getMonth() + 1);
        this.state.selectedMonth = `${year}-${month}`;
        this.loadItDash();
    }

    get itCategoryRows() {
        const palette = ["#3b82f6", "#22c55e", "#a855f7", "#f97316", "#14b8a6", "#94a3b8"];
        const rows = (this.it.by_category || []).slice(0, 6);
        const max = Math.max(...rows.map((r) => Number(r.amount || 0)), 1);
        return rows.map((r, i) => ({
            ...r,
            color: palette[i % palette.length],
            barPct: Math.max(8, Math.round((Number(r.amount || 0) / max) * 100)),
        }));
    }

    formatMoneyShort(v) {
        const n = Number(v || 0);
        if (Math.abs(n) >= 1e9) {
            return `${(n / 1e9).toFixed(1).replace(/\.0$/, "")} tỷ`;
        }
        if (Math.abs(n) >= 1e6) {
            return `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}Tr`;
        }
        if (Math.abs(n) >= 1e3) {
            return `${Math.round(n / 1e3)}K`;
        }
        return this.formatMoney(n);
    }

    openItSchedule(item) {
        if (!item?.id) {
            return;
        }
        this.openItTodo({ id: item.id, model: "phan.he.it.cost" });
    }

    openItScheduleAll() {
        const child = this.findNavChild("it_cost_schedule");
        if (child) {
            this.onNavChild(child);
        }
    }

    exportItOverview() {
        const rows = this.itTodoRows;
        const header = [
            "STT", "Tên tài sản", "Mã", "Hãng/Model", "Loại tài sản",
            "Ngày bắt đầu", "Ngày kết thúc", "Số tiền", "Trạng thái",
        ];
        const lines = [header.join(",")];
        rows.forEach((r) => {
            lines.push([
                r.stt,
                `"${String(r.asset || "").replace(/"/g, '""')}"`,
                r.asset_code || "",
                `"${String(r.brand || "").replace(/"/g, '""')}"`,
                `"${String(r.asset_type || r.category || "").replace(/"/g, '""')}"`,
                r.date_start || "",
                r.date_end || r.date || "",
                r.amount || 0,
                r.status_label || r.state || "",
            ].join(","));
        });
        const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Tong_quan_may_chu_${this.state.selectedMonth || "export"}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    get itBudgetPct() {
        const budget = Number(this.itKpi.year_budget || 0);
        if (!budget) {
            return 0;
        }
        return Math.round((Number(this.itKpi.year_cost || 0) / budget) * 1000) / 10;
    }

    get itMonthOptions() {
        const parts = String(this.state.selectedMonth || "").split("-");
        const y = Number(parts[0]) || new Date().getFullYear();
        const opts = [];
        for (let m = 1; m <= 12; m++) {
            opts.push({
                value: `${y}-${pad2(m)}`,
                label: `Tháng ${m}/${y}`,
            });
        }
        return opts;
    }

    /** 3 lát donut KPI — màu mẫu xanh / vàng / đỏ */
    get itKpiDonutSlices() {
        const k = this.itKpi;
        const renew = Number(k.overdue || 0) + Number(k.confirm || 0) + Number(k.expiring || 0);
        const rows = [
            {
                id: "month",
                label: "Chi phí tháng",
                color: "#22c55e",
                weight: Math.max(Number(k.month_cost || 0), 0),
                display: this.formatMoney(k.month_cost),
                action: "month",
            },
            {
                id: "year",
                label: "Chi phí năm",
                color: "#eab308",
                weight: Math.max(Number(k.year_cost || 0), 0),
                display: this.formatMoney(k.year_cost),
                action: "year",
            },
            {
                id: "renew",
                label: "Tình hình gia hạn",
                color: "#ef4444",
                weight: Math.max(renew, 0),
                display: String(renew),
                action: "expiring",
            },
        ];
        const sum = rows.reduce((a, r) => a + r.weight, 0);
        return rows.map((r) => ({
            ...r,
            pct: sum > 0 ? Math.round((r.weight / sum) * 1000) / 10 : 0,
        }));
    }

    onItKpiDonutClick(sl) {
        if (!sl?.action) {
            return;
        }
        if (sl.action === "expiring") {
            this.openItKpi("expiring");
            return;
        }
        if (sl.action === "month") {
            this.openReportPeriod("month");
            return;
        }
        if (sl.action === "year") {
            this.openReportPeriod("year");
        }
    }

    get itByTypeDonutSlices() {
        const palette = ["#3b82f6", "#22c55e", "#eab308", "#a855f7", "#94a3b8", "#fb923c"];
        const rows = (this.it.by_type || []).map((tp, i) => {
            const amount = Math.max(Number(tp.amount || 0), 0);
            const count = Number(tp.count || 0);
            return {
                id: tp.id || `type-${i}`,
                label: tp.name || "—",
                color: palette[i % palette.length],
                amount,
                count,
                weight: amount > 0 ? amount : count,
                display: this.formatMoney(amount),
                pct: Number(tp.pct || 0),
            };
        });
        const sumAmt = rows.reduce((a, r) => a + r.amount, 0);
        if (sumAmt > 0) {
            return rows.map((r) => ({
                ...r,
                pct: Math.round((r.amount / sumAmt) * 1000) / 10,
            }));
        }
        const sumW = rows.reduce((a, r) => a + r.weight, 0);
        return rows.map((r) => ({
            ...r,
            pct: sumW > 0 ? Math.round((r.weight / sumW) * 1000) / 10 : 0,
        }));
    }

    get itByTypeDonutTotal() {
        return (this.it.by_type || []).reduce((a, tp) => a + Number(tp.amount || 0), 0);
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
            server: "MÁY CHỦ",
        };
        return brands[this.serviceTypeCode] || String(this.appTitle || "").toUpperCase();
    }

    get navSections() {
        const code = this.serviceTypeCode;
        if (code === "internet") {
            return filterInternetNavSections(INTERNET_NAV_SECTIONS, this.state.internetMenus);
        }
        if (code === "server") {
            return filterServerNavSections(SERVER_NAV_SECTIONS, this.state.serverMenus);
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
        if (this.serviceTypeCode === "internet") {
            return internetNavCan(this.state.internetMenus, "overview");
        }
        if (this.serviceTypeCode === "server") {
            return serverNavCan(this.state.serverMenus, "overview");
        }
        return true;
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
        if (
            (this.serviceTypeCode === "internet" || this.serviceTypeCode === "server")
            && !this.canSeeInternetOverview
        ) {
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
        if (this.serviceTypeCode === "server" && !serverNavCan(this.state.serverMenus, child.id)) {
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
        // Dự toán chi phí T1–T12
        if (child.id === "cost_estimate") {
            this.state.activeNav = "cost_estimate";
            this._openGroupForNav("cost_estimate");
            this.state.contentMode = "cost_estimate";
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.entryPopupOpen = false;
            this.state.loading = false;
            return;
        }
        if (child.action && !child.reportPeriod) {
            this._rememberFormReturn();
        }
        this.state.activeNav = child.id;
        this._openGroupForNav(child.id);
        if (child.id === "store_declare") {
            if (this.serviceTypeCode === "server") {
                this.openEmbedded({
                    id: "store_declare",
                    action: "lug_phan_he.action_phan_he_service_entry_server",
                }, { type: "form", resId: false });
                return;
            }
            this.openEntryPopup(false);
            return;
        }
        if (child.id === "it_asset_new" || child.popup === "it_asset") {
            this.openItAssetPopup(false);
            return;
        }
        if (child.id === "it_cost_new" || child.popup === "it_cost") {
            this.openItCostPopup(false);
            return;
        }
        if (this.serviceTypeCode === "server" && child.id === "it_report_month") {
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "month_cost";
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "server" && child.id === "it_report_quarter") {
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "quarter_cost";
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "server" && child.id === "it_report_year") {
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "year_cost";
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "server" && IT_COST_REPORTS[child.id]) {
            this.state.activeNav = child.id;
            this._openGroupForNav(child.id);
            this.state.contentMode = "it_cost_report";
            this.state.itReportKey = IT_COST_REPORTS[child.id];
            this.state.itReportToken = (this.state.itReportToken || 0) + 1;
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
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
        if (
            ret.contentMode === "month_cost"
            || ret.activeNav === "report_month"
            || ret.activeNav === "it_report_month"
        ) {
            this.state.contentMode = "month_cost";
            this.state.activeNav = ret.activeNav
                || (this.serviceTypeCode === "server" ? "it_report_month" : "report_month");
            return;
        }
        if (
            ret.contentMode === "quarter_cost"
            || ret.activeNav === "report_quarter"
            || ret.activeNav === "it_report_quarter"
        ) {
            this.state.contentMode = "quarter_cost";
            this.state.activeNav = ret.activeNav
                || (this.serviceTypeCode === "server" ? "it_report_quarter" : "report_quarter");
            return;
        }
        if (
            ret.contentMode === "year_cost"
            || ret.activeNav === "report_year"
            || ret.activeNav === "it_report_year"
        ) {
            this.state.contentMode = "year_cost";
            this.state.activeNav = ret.activeNav
                || (this.serviceTypeCode === "server" ? "it_report_year" : "report_year");
            return;
        }
        if (ret.contentMode === "cost_estimate" || ret.activeNav === "cost_estimate") {
            this.state.contentMode = "cost_estimate";
            this.state.activeNav = "cost_estimate";
            return;
        }
        if (ret.contentMode === "it_cost_report") {
            this.state.contentMode = "it_cost_report";
            this.state.activeNav = ret.activeNav || this.state.activeNav;
            this.state.itReportKey = ret.itReportKey || this.state.itReportKey;
            this.state.itReportToken = (this.state.itReportToken || 0) + 1;
            return;
        }
        this.onOverview();
    }

    openItReportCost(resId) {
        if (!resId) {
            return;
        }
        this.state.formReturn = {
            contentMode: "it_cost_report",
            activeNav: this.state.activeNav,
            itReportKey: this.state.itReportKey,
        };
        this.openEmbedded(
            { id: this.state.activeNav, action: "lug_phan_he.action_phan_he_it_cost" },
            {
                type: "form",
                resId,
                action: "lug_phan_he.action_phan_he_it_cost",
                activeNav: this.state.activeNav,
            }
        );
    }

    openMonthCostEntry(resId = false) {
        if (this.serviceTypeCode === "server") {
            if (!resId) {
                this.openItCostPopup(false);
                return;
            }
            this.state.formReturn = {
                contentMode: "month_cost",
                activeNav: "it_report_month",
            };
            this.openEmbedded(
                { id: "it_report_month", action: "lug_phan_he.action_phan_he_it_cost" },
                {
                    type: "form",
                    resId,
                    action: "lug_phan_he.action_phan_he_it_cost",
                    activeNav: "it_report_month",
                }
            );
            return;
        }
        this.openEntryForm(resId);
    }

    openQuarterCostEntry(resId = false) {
        if (this.serviceTypeCode === "server") {
            if (!resId) {
                this.openItCostPopup(false);
                return;
            }
            this.state.formReturn = {
                contentMode: "quarter_cost",
                activeNav: "it_report_quarter",
            };
            this.openEmbedded(
                { id: "it_report_quarter", action: "lug_phan_he.action_phan_he_it_cost" },
                {
                    type: "form",
                    resId,
                    action: "lug_phan_he.action_phan_he_it_cost",
                    activeNav: "it_report_quarter",
                }
            );
            return;
        }
        this.openEntryForm(resId);
    }

    openYearCostEntry(resId = false) {
        if (this.serviceTypeCode === "server") {
            if (!resId) {
                this.openItCostPopup(false);
                return;
            }
            this.state.formReturn = {
                contentMode: "year_cost",
                activeNav: "it_report_year",
            };
            this.openEmbedded(
                { id: "it_report_year", action: "lug_phan_he.action_phan_he_it_cost" },
                {
                    type: "form",
                    resId,
                    action: "lug_phan_he.action_phan_he_it_cost",
                    activeNav: "it_report_year",
                }
            );
            return;
        }
        this.openEntryForm(resId);
    }

    async openEntryForm(resId = false) {
        const entryAction =
            this.serviceTypeCode === "server"
                ? "lug_phan_he.action_phan_he_service_entry_server"
                : "lug_phan_he.action_phan_he_service_entry";
        if (!resId && this.serviceTypeCode !== "server") {
            this.openEntryPopup(false);
            return;
        }
        this._rememberFormReturn();
        this.state.openGroups.manage = true;
        const nav =
            (this.state.activeNav && OWL_LIST_NAV[this.state.activeNav] && this.state.activeNav) ||
            "list_active";
        await this.openEmbedded(
            { id: nav, action: entryAction },
            {
                type: "form",
                resId: resId || false,
                action: entryAction,
                activeNav: nav,
            }
        );
    }

    internetAppCan(_op) {
        // Bảng 2 chỉ cần mở app Internet; CRUD theo bảng 3.
        const app = (this.state.moduleRights || {}).internet || {};
        if (app.admin) {
            return true;
        }
        return Boolean(app.view || app.create || app.edit || app.delete || app.admin);
    }

    resolveInternetCreateMenu() {
        const menus = this.state.internetMenus || {};
        const candidates = [
            INTERNET_NAV_TO_CODE[this.state.activeNav] || this.state.activeNav,
            "internet_active",
            "internet_entry",
            "group_manage_internet",
        ];
        for (const code of candidates) {
            if (code && internetMenuCan(menus, code, "create")) {
                return code;
            }
        }
        return "internet_active";
    }

    openEntryPopup(resId = false) {
        // Bảng 2 (app) AND bảng 3 (menu Đang sử dụng / Thêm mới / nhóm cha).
        const menus = this.state.internetMenus || {};
        const canCreate = this.internetAppCan("create") && (
            internetNavCan(menus, "store_declare", "create")
            || internetNavCan(menus, "manage", "create")
            || internetNavCan(menus, this.state.activeNav || "list_active", "create")
        );
        const canWrite = this.internetAppCan("edit") && (
            internetNavCan(menus, "store_declare", "write")
            || internetNavCan(menus, "manage", "write")
            || internetNavCan(menus, this.state.activeNav || "list_active", "write")
        );
        if (resId ? !canWrite : !canCreate) {
            this.notification.add(resId ? "Bạn không có quyền Sửa." : "Bạn không có quyền Thêm.", {
                type: "warning",
            });
            return;
        }
        // Giữ nav hiện tại (vd Đang sử dụng); không ép sang Thêm mới nếu chưa cấp quyền.
        if (internetNavCan(menus, "store_declare", "read") || internetNavCan(menus, "store_declare", "create")) {
            this.state.activeNav = "store_declare";
        }
        this.state.openGroups.manage = true;
        this.state.entryPopupResId = resId || false;
        this.state.entryCreateMenu = this.resolveInternetCreateMenu();
        this.state.entryPopupOpen = true;
    }

    closeEntryPopup() {
        this.state.entryPopupOpen = false;
        this.state.entryPopupResId = false;
        this.state.entryCreateMenu = "internet_active";
    }

    openItAssetPopup(resId = false) {
        if (this.serviceTypeCode === "server") {
            const allowed = resId
                ? serverNavCan(this.state.serverMenus, this.state.activeNav || "it_asset_all", "write")
                : serverNavCan(this.state.serverMenus, "it_asset_new", "create");
            if (!allowed) {
                this.notification.add(resId ? "Bạn không có quyền Sửa." : "Bạn không có quyền Thêm.", {
                    type: "warning",
                });
                return;
            }
        }
        this.state.activeNav = "it_asset_new";
        this.state.openGroups.manage = true;
        this.state.itAssetPopupResId = resId || false;
        this.state.itAssetPopupOpen = true;
    }

    closeItAssetPopup() {
        this.state.itAssetPopupOpen = false;
        this.state.itAssetPopupResId = false;
    }

    onItAssetPopupSaved() {
        this.closeItAssetPopup();
        if (this.state.activeNav === "overview" || this.isServerItDash) {
            this.loadItDash();
        }
        // Làm mới list tài sản nếu đang mở.
        if (this.state.contentMode === "view" && this.state.listActionXml) {
            this.state.viewKey += 1;
        }
        const listChild = this.findNavChild("it_asset_all");
        if (listChild) {
            this.openEmbedded(listChild);
        }
    }

    openItCostPopup(resId = false) {
        if (this.serviceTypeCode === "server") {
            const allowed = resId
                ? serverNavCan(this.state.serverMenus, this.state.activeNav || "it_cost_list", "write")
                : serverNavCan(this.state.serverMenus, "it_cost_new", "create");
            if (!allowed) {
                this.notification.add(resId ? "Bạn không có quyền Sửa." : "Bạn không có quyền Thêm.", {
                    type: "warning",
                });
                return;
            }
        }
        this.state.activeNav = "it_cost_new";
        this.state.openGroups.payment = true;
        this.state.itCostPopupResId = resId || false;
        this.state.itCostPopupOpen = true;
    }

    closeItCostPopup() {
        this.state.itCostPopupOpen = false;
        this.state.itCostPopupResId = false;
    }

    onItCostPopupSaved() {
        this.closeItCostPopup();
        if (this.state.activeNav === "overview" || this.isServerItDash) {
            this.loadItDash();
        }
        const listChild = this.findNavChild("it_cost_list");
        if (listChild) {
            this.openEmbedded(listChild);
        }
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
        // Dự toán / Lịch gia hạn Máy chủ → board lọc theo tháng (không dùng list Odoo cũ).
        const scheduleEstimateActions = {
            "lug_phan_he.action_phan_he_it_cost_estimate": {
                nav: "it_cost_estimate",
                key: "estimate",
            },
            "lug_phan_he.action_phan_he_it_cost_schedule": {
                nav: "it_cost_schedule",
                key: "schedule",
            },
        };
        const scheduleEstimateHit =
            scheduleEstimateActions[xmlid]
            || (navId === "it_cost_estimate" && scheduleEstimateActions["lug_phan_he.action_phan_he_it_cost_estimate"])
            || (navId === "it_cost_schedule" && scheduleEstimateActions["lug_phan_he.action_phan_he_it_cost_schedule"]);
        if (
            this.serviceTypeCode === "server"
            && extra.type !== "form"
            && scheduleEstimateHit
        ) {
            this.state.activeNav = scheduleEstimateHit.nav;
            this._openGroupForNav(scheduleEstimateHit.nav);
            this.state.contentMode = "it_cost_report";
            this.state.itReportKey = scheduleEstimateHit.key;
            this.state.itReportToken = (this.state.itReportToken || 0) + 1;
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.loading = false;
            this.state.viewKey += 1;
            return;
        }
        // Báo cáo IT (theo tài sản / NCC…) → board OWL.
        if (
            this.serviceTypeCode === "server"
            && extra.type !== "form"
            && IT_COST_REPORTS[navId]
        ) {
            this.state.activeNav = navId;
            this._openGroupForNav(navId);
            this.state.contentMode = "it_cost_report";
            this.state.itReportKey = IT_COST_REPORTS[navId];
            this.state.itReportToken = (this.state.itReportToken || 0) + 1;
            this.state.embeddedViewProps = null;
            this.state.listActionXml = null;
            this.state.loading = false;
            this.state.viewKey += 1;
            return;
        }
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
            const isInternetAcl = this.serviceTypeCode === "internet";
            const isServerAcl = this.serviceTypeCode === "server";
            const canWrite = isInternetAcl
                ? (this.internetAppCan("edit") && (
                    internetNavCan(this.state.internetMenus, menuKey, "write")
                    || (menuKey === "store_declare" && internetNavCan(this.state.internetMenus, "store_declare", "write"))
                ))
                : isServerAcl
                    ? serverNavCan(this.state.serverMenus, menuKey, "write")
                    : true;
            const canCreate = isInternetAcl
                ? (this.internetAppCan("create") && (
                    internetNavCan(this.state.internetMenus, menuKey, "create")
                    || internetNavCan(this.state.internetMenus, "store_declare", "create")
                ))
                : isServerAcl
                    ? serverNavCreate(this.state.serverMenus, menuKey)
                    : true;
            const viewContext = {
                ...this.parseActionContext(act.context),
                phan_he_service_type_code: this.serviceTypeCode,
                form_view_initial_mode:
                    (extra.resId === false || extra.resId === undefined
                        ? canCreate
                        : canWrite)
                        ? "edit"
                        : "readonly",
            };
            // Không áp mặc định chip "Đang sử dụng" trên mọi list tài sản IT.
            delete viewContext.search_default_filter_active_state;
            if (isInternetAcl) {
                viewContext.phan_he_internet_menu = menuCode || (extra.resId ? "internet_active" : "internet_entry");
            }
            const viewProps = {
                resModel: act.res_model,
                type: defaultType,
                domain: act.domain || [],
                context: viewContext,
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
                    if (this.serviceTypeCode === "server" && IT_COST_POPUP_ACTIONS.has(xmlid)) {
                        this.openItCostPopup(false);
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
            // Ép class đóng khung bảng IT — không phụ thuộc arch cache.
            if (
                defaultType === "list"
                && ["phan.he.it.cost", "phan.he.it.asset", "phan.he.it.ticket"].includes(act.res_model)
            ) {
                const classes = ["o_it_framed_list"];
                if (act.res_model === "phan.he.it.cost") {
                    classes.push("o_it_cost_list");
                }
                if (
                    act.res_model === "phan.he.it.asset"
                    && String(xmlid || "").includes("virtual")
                ) {
                    classes.push("o_it_virtual_list");
                }
                viewProps.className = classes.join(" ");
            }
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
                // Máy chủ: form tạo mới chi phí → popup đóng khung.
                if (
                    this.serviceTypeCode === "server"
                    && openingNew
                    && IT_COST_POPUP_ACTIONS.has(xmlid)
                ) {
                    this.openItCostPopup(false);
                    return;
                }
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
        if (period === "month" && this.serviceTypeCode === "server") {
            this.state.activeNav = "it_report_month";
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
        if (period === "quarter" && this.serviceTypeCode === "server") {
            this.state.activeNav = "it_report_quarter";
            this.state.contentMode = "quarter_cost";
            this.state.loading = false;
            return;
        }
        if (period === "year" && this.serviceTypeCode === "internet") {
            this.state.activeNav = "report_year";
            this.state.contentMode = "year_cost";
            this.state.loading = false;
            return;
        }
        if (period === "year" && this.serviceTypeCode === "server") {
            this.state.activeNav = "it_report_year";
            this.state.contentMode = "year_cost";
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

    openServerNav(navId) {
        const child = this.findNavChild(navId);
        if (child) {
            this.onNavChild(child);
        }
    }

    openServerRecord(row) {
        if (!row?.id) {
            return;
        }
        this.openEmbedded(
            { id: "it_asset_all", action: "lug_phan_he.action_phan_he_it_asset" },
            {
                type: "form",
                resId: row.id,
                action: "lug_phan_he.action_phan_he_it_asset",
                activeNav: "it_asset_all",
            }
        );
    }

    openItTodo(row) {
        if (!row?.id || !row?.model) {
            return;
        }
        const isCost = row.model === "phan.he.it.cost";
        const actionXml = isCost
            ? "lug_phan_he.action_phan_he_it_cost"
            : "lug_phan_he.action_phan_he_it_ticket_maintenance";
        const navId = isCost ? "it_cost_list" : "it_ticket_maint";
        this.openEmbedded(
            { id: navId, action: actionXml },
            {
                type: "form",
                resId: row.id,
                action: actionXml,
                activeNav: navId,
            }
        );
    }

    openItKpi(kind) {
        const map = {
            assets: "it_asset_all",
            overdue: "it_cost_overdue",
            expiring: "it_cost_schedule",
        };
        const navId = map[kind];
        if (!navId) {
            return;
        }
        this.openServerNav(navId);
    }

    onAlertClick(alert) {
        if (this.serviceTypeCode === "server" && alert?.id) {
            const navByCard = {
                expire_soon: "payment_overdue",
                expired: "payment_overdue",
                pay_due_soon: "payment_schedule",
            };
            const navId = navByCard[alert.id] || "payment_schedule";
            const child = this.findNavChild(navId);
            if (child) {
                this.onNavChild(child);
                return;
            }
        }
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
            const data = await this.orm.call(
                "phan.he.service",
                "get_dashboard_data",
                [month, year, region, store],
                { service_type_code: this.serviceTypeCode }
            );
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
                list_active: data?.list_active ?? this.state.data?.list_active ?? 0,
                list_suspend: data?.list_suspend ?? this.state.data?.list_suspend ?? 0,
                list_liquidated: data?.list_liquidated ?? this.state.data?.list_liquidated ?? 0,
                payment_schedule: data?.payment_schedule ?? this.state.data?.payment_schedule ?? 0,
                payment_confirm: data?.payment_confirm ?? this.state.data?.payment_confirm ?? 0,
                server_inventory: data?.server_inventory || this.state.data?.server_inventory || {},
            };
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được dashboard.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async loadItDash() {
        if (this.serviceTypeCode === "server" && !serverNavCan(this.state.serverMenus, "overview")) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const parts = String(this.state.selectedMonth || "").split("-");
            const year = Number(parts[0]) || new Date().getFullYear();
            const month = Number(parts[1]) || new Date().getMonth() + 1;
            const filters = {
                year,
                month,
                mien_id:
                    this.state.selectedRegion && this.state.selectedRegion !== "all"
                        ? Number(this.state.selectedRegion)
                        : false,
                asset_type_id:
                    this.state.itAssetTypeId && this.state.itAssetTypeId !== "all"
                        ? Number(this.state.itAssetTypeId)
                        : false,
                state:
                    this.state.itAssetState && this.state.itAssetState !== "all"
                        ? this.state.itAssetState
                        : false,
                provider_id:
                    this.state.itProviderId && this.state.itProviderId !== "all"
                        ? Number(this.state.itProviderId)
                        : false,
            };
            const data = await this.orm.call(
                "phan.he.it.dashboard",
                "get_it_dashboard_data",
                [filters]
            );
            this.state.it = data || {};
            // Giữ tháng đã chọn — tránh <select> reset về option đầu khi options re-render.
            this.state.selectedMonth = `${year}-${pad2(month)}`;
            this.state.data = {
                ...(this.state.data || {}),
                updated_at: data?.updated_at,
                app_title: "Máy chủ",
            };
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được dashboard máy chủ.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onInetMonthChange(ev) {
        this.state.selectedMonth = ev.target.value;
        if (this.isServerDash) {
            await this.loadItDash();
            return;
        }
        await this.loadInternetDash();
    }

    async onInetYearOnlyChange(ev) {
        const y = Number(ev.target.value) || new Date().getFullYear();
        const parts = String(this.state.selectedMonth || "").split("-");
        const m = Number(parts[1]) || new Date().getMonth() + 1;
        this.state.selectedMonth = `${y}-${pad2(m)}`;
        await this.loadInternetDash();
    }

    onInetPeriodChange(ev) {
        this.state.inetPeriod = ev.target.value || "month";
    }

    async reloadInetOverview() {
        await this.loadInternetDash();
    }

    async onInetRegionChange(ev) {
        this.state.selectedRegion = ev.target.value;
        this.state.selectedStore = "all";
        if (this.isServerDash) {
            await this.loadItDash();
            return;
        }
        await this.loadInternetDash();
    }

    async onInetStoreChange(ev) {
        this.state.selectedStore = ev.target.value;
        await this.loadInternetDash();
    }

    async onItAssetTypeChange(ev) {
        this.state.itAssetTypeId = ev.target.value;
        await this.loadItDash();
    }

    async onItAssetStateChange(ev) {
        this.state.itAssetState = ev.target.value;
        await this.loadItDash();
    }

    async onItProviderChange(ev) {
        this.state.itProviderId = ev.target.value;
        await this.loadItDash();
    }

    bindItChartBox() {
        this.unbindItChartBox();
        const root = this.itMonthRef?.el?.closest(".lq-it-ov");
        if (!root || typeof ResizeObserver === "undefined") {
            return;
        }
        const fit = () => {
            const w = root.clientWidth;
            const h = root.clientHeight;
            if (w === this._itBoxW && h === this._itBoxH) {
                return;
            }
            this._itBoxW = w;
            this._itBoxH = h;
            const dpr = window.devicePixelRatio || 1;
            Object.values(this.itCharts || {}).forEach((chart) => {
                try {
                    chart.options.devicePixelRatio = dpr;
                    chart.resize();
                } catch (e) {
                    /* ignore */
                }
            });
        };
        this._itChartFit = fit;
        this._itResizeObserver = new ResizeObserver(() => {
            if (this._itResizeFrame) {
                cancelAnimationFrame(this._itResizeFrame);
            }
            this._itResizeFrame = requestAnimationFrame(fit);
        });
        this._itResizeObserver.observe(root);
        window.visualViewport?.addEventListener("resize", fit);
    }

    unbindItChartBox() {
        if (this._itResizeFrame) {
            cancelAnimationFrame(this._itResizeFrame);
            this._itResizeFrame = 0;
        }
        if (this._itChartFit) {
            window.visualViewport?.removeEventListener("resize", this._itChartFit);
            this._itChartFit = null;
        }
        this._itResizeObserver?.disconnect();
        this._itResizeObserver = null;
        this._itBoxW = 0;
        this._itBoxH = 0;
    }

    destroyItCharts() {
        this.unbindItChartBox();
        Object.values(this.itCharts || {}).forEach((chart) => {
            try {
                chart.destroy();
            } catch (e) {
                /* ignore */
            }
        });
        this.itCharts = {};
        [
            this.itMonthRef,
            this.itRenewDonutRef,
            this.itKpiDonutRef,
            this.itByTypeDonutRef,
            this.itQuarterRef,
            this.itCategoryRef,
            this.itBudgetGaugeRef,
            this.itYearTrendRef,
            this.itOpexDonutRef,
            this.itLifecycleRef,
        ].forEach((ref) => {
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

    _renderItDonutChart(ref, chartKey, slices, tooltipFmt) {
        const el = ref && ref.el;
        if (!el || typeof Chart === "undefined") {
            return;
        }
        const ctx = el.getContext("2d");
        if (!ctx || !(slices || []).length) {
            return;
        }
        const weights = slices.map((s) => Number(s.weight || 0));
        const hasData = weights.some((w) => w > 0);
        const labelMode = this.state.itDonutMode;
        const moneyShort = (v) => this.formatMoneyShort(v);
        this.itCharts[chartKey] = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: slices.map((s) => s.label),
                datasets: [{
                    data: hasData ? weights : slices.map(() => 1),
                    backgroundColor: slices.map((s) => s.color),
                    borderWidth: 2,
                    borderColor: "#fff",
                    hoverOffset: 4,
                }],
            },
            plugins: [{
                id: `itSliceLabel-${chartKey}`,
                afterDraw(chart) {
                    const { ctx } = chart;
                    const meta = chart.getDatasetMeta(0);
                    const data = chart.data.datasets[0].data;
                    const total = data.reduce((a, b) => a + Number(b || 0), 0) || 1;
                    meta.data.forEach((arc, i) => {
                        const v = Number(data[i] || 0);
                        if (!v || v / total < 0.045 || !arc) {
                            return;
                        }
                        const ang = ((arc.startAngle || 0) + (arc.endAngle || 0)) / 2;
                        const r = ((arc.innerRadius || 0) + (arc.outerRadius || 0)) / 2;
                        const x = arc.x + Math.cos(ang) * r;
                        const y = arc.y + Math.sin(ang) * r;
                        const pct = String(Math.round((v / total) * 1000) / 10).replace(".", ",");
                        ctx.save();
                        ctx.fillStyle = "#fff";
                        ctx.font = "700 11px sans-serif";
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(labelMode === "value" ? moneyShort(v) : `${pct}%`, x, y);
                        ctx.restore();
                    });
                },
            }],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "72%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (c) => {
                                const sl = slices[c.dataIndex];
                                if (!sl) {
                                    return c.label;
                                }
                                if (tooltipFmt) {
                                    return tooltipFmt(sl);
                                }
                                return `${sl.label}: ${sl.display} (${sl.pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    renderItCharts() {
        if (typeof Chart === "undefined") {
            return;
        }
        this.destroyItCharts();
        const it = this.state.it || {};
        const series = it.month_series || [];
        const moneyTip = {
            callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${this.formatMoney(ctx.raw)}`,
            },
        };
        const axisY = {
            beginAtZero: true,
            ticks: { color: "#94a3b8", callback: (v) => this._formatAxisVnd(v) },
            grid: { color: "rgba(148,163,184,0.18)" },
            border: { display: false },
        };
        const monthCtx = this.itMonthRef?.el?.getContext("2d");
        const chartMode = this.state.itChartMode || "month";
        if (monthCtx && chartMode === "category") {
            const cats = this.itCategoryRows;
            this.itCharts.month = new Chart(monthCtx, {
                type: "bar",
                data: {
                    labels: cats.map((c) => c.name),
                    datasets: [{
                        label: "Chi phí",
                        data: cats.map((c) => Number(c.amount || 0)),
                        backgroundColor: cats.map((c) => c.color),
                        borderRadius: 6,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: axisY,
                        y: { grid: { display: false }, ticks: { color: "#475569" } },
                    },
                },
            });
        } else if (monthCtx && chartMode === "quarter") {
            const qs = it.quarter_series || [];
            this.itCharts.month = new Chart(monthCtx, {
                data: {
                    labels: qs.map((q) => q.label),
                    datasets: [
                        { type: "bar", label: "Thực tế", data: qs.map((q) => Number(q.actual || 0)), backgroundColor: "#3b82f6", borderRadius: 4 },
                        { type: "bar", label: "Ngân sách", data: qs.map((q) => Number(q.budget || 0)), backgroundColor: "#4ade80", borderRadius: 4 },
                        { type: "line", label: "Dự báo", data: qs.map((q) => Number(q.actual || 0)), borderColor: "#f59e0b", tension: 0.3, pointRadius: 3 },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
                        y: axisY,
                    },
                },
            });
        } else if (monthCtx && chartMode === "year") {
            const ys = it.year_trend || [];
            this.itCharts.month = new Chart(monthCtx, {
                type: "line",
                data: {
                    labels: ys.map((y) => y.label),
                    datasets: [
                        { label: "Thực tế", data: ys.map((y) => Number(y.amount || 0)), borderColor: "#3b82f6", tension: 0.35, pointRadius: 3 },
                        { label: "Dự báo", data: ys.map((y) => Number(y.forecast || 0)), borderColor: "#a78bfa", borderDash: [6, 4], tension: 0.35, pointRadius: 3 },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
                        y: axisY,
                    },
                },
            });
        } else if (monthCtx) {
            this.itCharts.month = new Chart(monthCtx, {
                data: {
                    labels: series.map((p) => p.label),
                    datasets: [
                        {
                            type: "bar",
                            label: "Thực tế",
                            data: series.map((p) => Number(p.amount || 0)),
                            backgroundColor: "#3b82f6",
                            borderRadius: 4,
                            order: 2,
                        },
                        {
                            type: "bar",
                            label: "Ngân sách",
                            data: series.map((p) => Number(p.budget || 0)),
                            backgroundColor: "#4ade80",
                            borderRadius: 4,
                            order: 3,
                        },
                        {
                            type: "line",
                            label: "Dự báo",
                            data: series.map((p) => Number(p.forecast || 0)),
                            borderColor: "#f59e0b",
                            backgroundColor: "transparent",
                            borderWidth: 2.4,
                            tension: 0.35,
                            pointRadius: 3,
                            pointBackgroundColor: "#fff",
                            pointBorderColor: "#f59e0b",
                            pointBorderWidth: 2,
                            order: 1,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 11 } } },
                        y: axisY,
                    },
                },
            });
        }

        const typeSlices = this.itByTypeDonutSlices.map((r) => ({
            ...r,
            weight: Number(r.amount || r.weight || 0),
            display: this.formatMoney(r.amount || 0),
        }));
        this._renderItDonutChart(this.itByTypeDonutRef, "byTypeDonut", typeSlices);

        const qSeries = it.quarter_series || [];
        const qCtx = this.itQuarterRef?.el?.getContext("2d");
        if (qCtx && qSeries.length) {
            this.itCharts.quarter = new Chart(qCtx, {
                data: {
                    labels: qSeries.map((q) => q.label),
                    datasets: [
                        {
                            type: "bar",
                            label: "Thực tế",
                            data: qSeries.map((q) => Number(q.actual || 0)),
                            backgroundColor: "#3b82f6",
                            borderRadius: 4,
                            yAxisID: "y",
                            barThickness: 14,
                            maxBarThickness: 14,
                        },
                        {
                            type: "bar",
                            label: "Ngân sách",
                            data: qSeries.map((q) => Number(q.budget || 0)),
                            backgroundColor: "#4ade80",
                            borderRadius: 4,
                            yAxisID: "y",
                            barThickness: 14,
                            maxBarThickness: 14,
                        },
                        {
                            type: "line",
                            label: "% sử dụng NS",
                            data: qSeries.map((q) => Number(q.usage_pct || 0)),
                            borderColor: "#f59e0b",
                            backgroundColor: "transparent",
                            borderWidth: 2.2,
                            tension: 0.3,
                            pointRadius: 3,
                            pointBackgroundColor: "#f59e0b",
                            yAxisID: "y1",
                        },
                    ],
                },
                plugins: [{
                    id: "itQuarterPct",
                    afterDatasetsDraw(chart) {
                        const { ctx } = chart;
                        const meta = chart.getDatasetMeta(0);
                        qSeries.forEach((q, i) => {
                            const bar = meta.data[i];
                            if (!bar) {
                                return;
                            }
                            ctx.save();
                            ctx.fillStyle = "#64748b";
                            ctx.font = "700 11px sans-serif";
                            ctx.textAlign = "center";
                            ctx.fillText(
                                `${String(q.usage_pct || 0).replace(".", ",")}%`,
                                bar.x,
                                bar.y - 8
                            );
                            ctx.restore();
                        });
                    },
                }],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { top: 16 } },
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
                        y: axisY,
                        y1: {
                            position: "right",
                            beginAtZero: true,
                            max: 100,
                            grid: { drawOnChartArea: false },
                            ticks: { color: "#f59e0b", callback: (v) => `${v}%` },
                        },
                    },
                },
            });
        }

        const cats = (it.by_category || []).slice(0, 8);
        const catColors = ["#3b82f6", "#22c55e", "#a855f7", "#f97316", "#14b8a6", "#94a3b8", "#eab308", "#60a5fa"];
        const catCtx = this.itCategoryRef?.el?.getContext("2d");
        if (catCtx) {
            this.itCharts.category = new Chart(catCtx, {
                type: "bar",
                data: {
                    labels: cats.map((c) => c.name),
                    datasets: [{
                        label: "Chi phí",
                        data: cats.map((c) => Number(c.amount || 0)),
                        backgroundColor: cats.map((_, i) => catColors[i % catColors.length]),
                        borderRadius: 6,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { ...axisY, grid: { color: "rgba(148,163,184,0.15)" } },
                        y: { grid: { display: false }, ticks: { color: "#475569", font: { size: 11 } } },
                    },
                },
            });
        }

        const usage = Math.min(100, Math.max(0, Number(it.kpi?.budget_usage_pct || 0)));
        const gaugeCtx = this.itBudgetGaugeRef?.el?.getContext("2d");
        if (gaugeCtx) {
            this.itCharts.gauge = new Chart(gaugeCtx, {
                type: "doughnut",
                data: {
                    labels: ["Đã dùng", "Còn lại"],
                    datasets: [{
                        data: [usage, Math.max(0, 100 - usage)],
                        backgroundColor: ["#22c55e", "#e8eef4"],
                        borderWidth: 0,
                        circumference: 180,
                        rotation: 270,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "78%",
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                },
            });
        }

        const yTrend = it.year_trend || [];
        const ytCtx = this.itYearTrendRef?.el?.getContext("2d");
        if (ytCtx && yTrend.length) {
            this.itCharts.yearTrend = new Chart(ytCtx, {
                type: "line",
                data: {
                    labels: yTrend.map((y) => y.label),
                    datasets: [
                        {
                            label: "Thực tế",
                            data: yTrend.map((y) => Number(y.amount || 0)),
                            borderColor: "#3b82f6",
                            backgroundColor: "rgba(59,130,246,0.12)",
                            fill: true,
                            tension: 0.35,
                            pointRadius: 4,
                        },
                        {
                            label: "Dự báo",
                            data: yTrend.map((y) => Number(y.forecast || 0)),
                            borderColor: "#a78bfa",
                            borderDash: [6, 4],
                            pointBackgroundColor: "#a78bfa",
                            fill: false,
                            tension: 0.35,
                            pointRadius: 3,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: moneyTip },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
                        y: axisY,
                    },
                },
            });
        }

        const opexColor = { opex: "#3b82f6", capex: "#22c55e" };
        const opexSlices = (it.opex_capex || []).map((r) => ({
            id: r.id,
            label: r.label,
            color: opexColor[r.id] || r.color || "#94a3b8",
            weight: Number(r.amount || 0),
            display: this.formatMoney(r.amount || 0),
            pct: Number(r.pct || 0),
        }));
        this._renderItDonutChart(this.itOpexDonutRef, "opexDonut", opexSlices);

        const life = it.lifecycle || [];
        const lifeCtx = this.itLifecycleRef?.el?.getContext("2d");
        if (lifeCtx && life.length) {
            this.itCharts.lifecycle = new Chart(lifeCtx, {
                type: "bar",
                data: {
                    labels: life.map((r) => r.name),
                    datasets: [
                        {
                            label: "Còn hiệu lực",
                            data: life.map((r) => Number(r.active || 0)),
                            backgroundColor: "#22c55e",
                            stack: "life",
                        },
                        {
                            label: "Sắp hết hạn ≤6 tháng",
                            data: life.map((r) => Number(r.expiring || 0)),
                            backgroundColor: "#facc15",
                            stack: "life",
                        },
                        {
                            label: "Đã quá hạn",
                            data: life.map((r) => Number(r.overdue || 0)),
                            backgroundColor: "#fb923c",
                            stack: "life",
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { stacked: true, grid: { display: false }, ticks: { color: "#64748b", font: { size: 10 } } },
                        y: {
                            stacked: true,
                            beginAtZero: true,
                            ticks: { color: "#94a3b8", stepSize: 1 },
                            grid: { color: "rgba(148,163,184,0.15)" },
                            border: { display: false },
                        },
                    },
                },
            });
        }
        this.bindItChartBox();
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
        [
            this.inetDonutRef,
            this.inetRegionBarRef,
            this.inetYearLinesRef,
            this.inetProvDonutRef,
            this.inetCashflowRef,
        ].forEach((ref) => {
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
        const ov = inet.ov || {};
        const axisMoney = {
            beginAtZero: true,
            ticks: {
                color: "#94a3b8",
                font: { size: 10 },
                callback: (v) => this.formatMoneyShort(v),
            },
            grid: { color: "rgba(148,163,184,0.15)" },
        };

        const regionBarCtx = this._inetChartOrNull(this.inetRegionBarRef);
        const rc = ov.region_compare || {};
        if (regionBarCtx && (rc.labels || []).length) {
            this.inetCharts.regionBar = new Chart(regionBarCtx, {
                type: "bar",
                data: {
                    labels: rc.labels || [],
                    datasets: [
                        {
                            label: "Tháng này",
                            data: (rc.this_month || []).map((v) => Number(v || 0)),
                            backgroundColor: "#2563eb",
                            borderRadius: 6,
                            maxBarThickness: 22,
                        },
                        {
                            label: "Tháng trước",
                            data: (rc.last_month || []).map((v) => Number(v || 0)),
                            backgroundColor: "#93c5fd",
                            borderRadius: 6,
                            maxBarThickness: 22,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    resizeDelay: 120,
                    animation: { duration: 0 },
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#64748b", font: { size: 11, weight: "600" } } },
                        y: axisMoney,
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
                        borderWidth: 3,
                        borderColor: "#fff",
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    resizeDelay: 120,
                    animation: { duration: 0 },
                    cutout: "70%",
                    plugins: { legend: { display: false } },
                },
            });
        }

        const yearLinesCtx = this._inetChartOrNull(this.inetYearLinesRef);
        const yl = ov.year_lines || {};
        if (yearLinesCtx && (yl.series || []).length) {
            this.inetCharts.yearLines = new Chart(yearLinesCtx, {
                type: "line",
                data: {
                    labels: yl.labels || [],
                    datasets: (yl.series || []).map((s) => ({
                        label: s.label,
                        data: (s.amounts || []).map((v) => Number(v || 0)),
                        borderColor: s.color,
                        backgroundColor: "transparent",
                        borderWidth: 2.2,
                        borderDash: s.dashed ? [6, 4] : [],
                        tension: 0.35,
                        pointRadius: 2.5,
                        pointBackgroundColor: s.color,
                    })),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    resizeDelay: 120,
                    animation: { duration: 0 },
                    interaction: { mode: "index", intersect: false },
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 10 } } },
                        y: axisMoney,
                    },
                },
            });
        }

        const provCtx = this._inetChartOrNull(this.inetProvDonutRef);
        const providers = ov.providers || [];
        if (provCtx && providers.length) {
            this.inetCharts.provDonut = new Chart(provCtx, {
                type: "doughnut",
                data: {
                    labels: providers.map((p) => p.name),
                    datasets: [{
                        data: providers.map((p) => Number(p.amount || 0)),
                        backgroundColor: providers.map((p) => p.color),
                        borderWidth: 2,
                        borderColor: "#fff",
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    resizeDelay: 120,
                    animation: { duration: 0 },
                    cutout: "62%",
                    plugins: { legend: { display: false } },
                },
            });
        }

        const cashCtx = this._inetChartOrNull(this.inetCashflowRef);
        const cf = ov.cashflow || {};
        if (cashCtx && (cf.labels || []).length) {
            this.inetCharts.cashflow = new Chart(cashCtx, {
                type: "bar",
                data: {
                    labels: cf.labels || [],
                    datasets: [
                        {
                            label: "Thực tế",
                            data: (cf.actual || []).map((v) => Number(v || 0)),
                            backgroundColor: "#2563eb",
                            borderRadius: 4,
                            maxBarThickness: 16,
                            stack: "cf",
                        },
                        {
                            label: "Dự kiến",
                            data: (cf.projected || []).map((v) => Number(v || 0)),
                            backgroundColor: "#93c5fd",
                            borderRadius: 4,
                            maxBarThickness: 16,
                            stack: "cf",
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    resizeDelay: 120,
                    animation: { duration: 0 },
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { stacked: true, grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 10 } } },
                        y: { ...axisMoney, stacked: true },
                    },
                },
            });
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
        this.onNavChild({ id: "list_active" });
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
            const counts = await this.orm.call(
                "phan.he.service",
                "get_internet_alert_counts",
                args,
                { service_type_code: this.serviceTypeCode }
            );
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
        if (
            (this.serviceTypeCode === "internet" || this.serviceTypeCode === "server")
            && this.state.contentMode === "owl_list"
        ) {
            this.state.loading = false;
            return;
        }
        if (
            (this.serviceTypeCode === "internet" || this.serviceTypeCode === "server")
            && this.state.contentMode === "payment_board"
        ) {
            this.state.loading = false;
            return;
        }
        if (
            (this.serviceTypeCode === "internet" || this.serviceTypeCode === "server")
            && (this.state.contentMode === "month_cost" || this.state.contentMode === "quarter_cost" || this.state.contentMode === "year_cost" || this.state.contentMode === "cost_estimate")
        ) {
            this.state.loading = false;
            return;
        }
        if (this.serviceTypeCode === "server" && this.state.activeNav !== "reports") {
            await this.loadItDash();
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
        const n = Math.round(Number(v || 0) * 10) / 10;
        return String(n.toFixed(1)).replace(/\.0$/, "").replace(".", ",");
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
