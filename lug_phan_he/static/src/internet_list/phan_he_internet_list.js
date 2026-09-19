/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { formView } from "@web/views/form/form_view";
import { PhanHeInternetFormController } from "../internet_form/phan_he_internet_form";
import { INTERNET_NAV_TO_CODE, internetNavCan } from "../access/internet_menu_nav";

const WIDTH_KEY = "linkq_sidebar_width";
const MIN_W = 180;
const MAX_W = 450;
const DEFAULT_W = 260;

const OPS_STATUS_META = {
    active: { label: "Đang hoạt động", className: "is-active" },
    suspend: { label: "Tạm ngưng", className: "is-suspend" },
    liquidated: { label: "Thanh lý", className: "is-liquidated" },
};

const INTERNET_NAV_SECTIONS = [
    {
        id: "manage",
        label: "Quản lý Internet",
        icon: "fa-wifi",
        children: [
            {
                id: "list_active",
                label: "Đang sử dụng",
                icon: "fa-globe",
                action: "lug_phan_he.action_phan_he_internet_active_master",
            },
            {
                id: "list_suspend",
                label: "Tạm ngưng",
                icon: "fa-globe",
                action: "lug_phan_he.action_phan_he_internet_suspend_master",
            },
            {
                id: "list_liquidated",
                label: "Thanh lý",
                icon: "fa-globe",
                action: "lug_phan_he.action_phan_he_internet_liquidated_master",
            },
            {
                id: "store_declare",
                label: "Nhập thông tin",
                icon: "fa-globe",
                action: "lug_phan_he.action_phan_he_service_entry",
            },
        ],
    },
    {
        id: "payment",
        label: "Chi phí & thanh toán",
        icon: "fa-credit-card",
        children: [
            { id: "payment_schedule", label: "Lịch thanh toán", icon: "fa-calendar" },
            { id: "payment_confirm", label: "Xác nhận TT", icon: "fa-check-square-o" },
            { id: "payment_overdue", label: "Quá hạn", icon: "fa-times-circle" },
            { id: "payment_forecast", label: "Dự kiến thanh toán", icon: "fa-calendar-plus-o" },
        ],
    },
    {
        id: "reports",
        label: "Báo cáo",
        icon: "fa-bar-chart",
        children: [
            { id: "report_month", label: "Chi phí tháng", icon: "fa-calendar-o", reportPeriod: "month" },
            { id: "report_quarter", label: "Chi phí quý", icon: "fa-calendar", reportPeriod: "quarter" },
            { id: "report_year", label: "Chi phí năm", icon: "fa-calendar-check-o", reportPeriod: "year" },
        ],
    },
];

function formatMoneyVn(amount) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(amount || 0)))} đ`;
}

function pad2(n) {
    return String(n).padStart(2, "0");
}

function ymd(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function periodBounds(kind) {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth();
    if (kind === "month" || kind === "report_month") {
        return { from: ymd(new Date(y, m, 1)), to: ymd(new Date(y, m + 1, 0)) };
    }
    if (kind === "quarter" || kind === "report_quarter") {
        const q = Math.floor(m / 3) * 3;
        return { from: ymd(new Date(y, q, 1)), to: ymd(new Date(y, q + 3, 0)) };
    }
    return { from: `${y}-01-01`, to: `${y}-12-31` };
}

function formatDateVn(value) {
    if (!value) {
        return "—";
    }
    const raw = String(value);
    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) {
        return `${m[3]}/${m[2]}/${m[1]}`;
    }
    return raw;
}

function lastDayOfMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

/** Chiếu ngày neo (date_end / next_payment) vào tháng chọn. */
function projectDueInMonth(anchorYmd, year, month) {
    const last = lastDayOfMonth(year, month);
    let day = 1;
    const m = String(anchorYmd || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) {
        day = Math.min(Number(m[3]), last);
    }
    return `${year}-${pad2(month)}-${pad2(day)}`;
}

function nextMonthParts(offset = 1) {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() + offset);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function clampWidth(value) {
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n)) {
        return DEFAULT_W;
    }
    return Math.min(MAX_W, Math.max(MIN_W, n));
}

const FILTER_TITLES = {
    all: {
        title: "Danh sách Internet",
        subtitle: "Toàn bộ hợp đồng Internet. Quản lý, theo dõi và xử lý nhanh chóng.",
        activeNav: "list_all",
    },
    active: {
        title: "Đang sử dụng",
        subtitle: "Các đường truyền đang hoạt động",
        activeNav: "list_active",
    },
    suspend: {
        title: "Tạm ngưng",
        subtitle: "Các đường truyền đang tạm ngưng",
        activeNav: "list_suspend",
    },
    liquidated: {
        title: "Thanh lý",
        subtitle: "Các đường truyền đã thanh lý hoặc hủy",
        activeNav: "list_liquidated",
    },
    expire_soon: {
        title: "Sắp tới hạn thanh toán",
        subtitle: "Hợp đồng đang dùng, còn từ 0 đến 30 ngày",
        activeNav: "expire_soon",
    },
    payment_due: {
        title: "Lịch thanh toán",
        subtitle: "Internet cần thanh toán: còn ≤ 30 ngày, quá hạn hoặc trễ hạn",
        activeNav: "payment_schedule",
    },
    payment_forecast: {
        title: "Dự kiến thanh toán",
        subtitle: "HĐ đúng tháng/năm chọn + HĐ quá hạn",
        activeNav: "payment_forecast",
    },
    expired: {
        title: "Quá hạn",
        subtitle: "Hợp đồng Internet đang dùng đã quá ngày kết thúc",
        activeNav: "payment_overdue",
    },
    report_month: {
        title: "Chi phí tháng",
        subtitle: "Hợp đồng giao thoa tháng hiện tại",
        activeNav: "report_month",
    },
    report_quarter: {
        title: "Chi phí quý",
        subtitle: "Hợp đồng giao thoa quý hiện tại",
        activeNav: "report_quarter",
    },
    report_year: {
        title: "Chi phí năm",
        subtitle: "Hợp đồng giao thoa năm hiện tại",
        activeNav: "report_year",
    },
};

const REGION_LABELS = {
    "": "Tất cả khu vực",
    Nam: "Miền Nam",
    ĐTT: "Miền ĐTT",
    Bắc: "Miền Bắc",
    VP: "Văn phòng",
};

export class PhanHeInternetListBoard extends Component {
    static template = "lug_phan_he.PhanHeInternetListBoard";
    static props = {
        listFilter: { type: String, optional: true },
        listReloadToken: { type: Number, optional: true },
        internetMenus: { type: Object, optional: true },
        onOpenEntry: { type: Function, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.ui = useService("ui");
        this.state = useState({
            loading: true,
            records: [],
            selected: {},
            providers: [],
            bandwidths: [],
            stats: { total: 0, active: 0, suspend: 0, liquidated: 0, expireSoon: 0, expired: 0, monthlyFee: 0 },
            page: 1,
            currentPage: 1,
            pageSize: 10,
            limit: 10,
            totalCount: 0,
            search: "",
            statusFilter: "",
            providerFilter: "",
            bandwidthFilter: "",
            regionFilter: "",
            remainTab: "all",
            sectionOpen: true,
            openMenuId: null,
            detailOpen: false,
            detailEditing: false,
            detailSaving: false,
            detailRecord: null,
            detailForm: {},
            detailInvoicePending: null,
            internetMenus: this.props.internetMenus || {},
            exporting: false,
            forecastYear: nextMonthParts(1).year,
            forecastMonth: nextMonthParts(1).month,
            forecastGroupOpen: {},
        });
        this._loadSeq = 0;
        this._searchTimer = null;
        this._providersLoaded = false;
        this._internetTypeId = null;
        this._stickyRaf = null;
        this.tableScrollRef = useRef("tableScroll");
        this.monthOptions = Array.from({ length: 12 }, (_, i) => ({
            value: i + 1,
            label: `Tháng ${i + 1}`,
        }));
        this.yearOptions = (() => {
            const y = new Date().getFullYear();
            const years = [];
            for (let i = y - 1; i <= y + 2; i++) {
                years.push({ value: i, label: `Năm ${i}` });
            }
            return years;
        })();
        onMounted(() => this.syncStickyColumns());
        onPatched(() => this.syncStickyColumns());
        onWillStart(async () => {
            if (this.props.internetMenus && Object.keys(this.props.internetMenus).length) {
                this.state.internetMenus = this.props.internetMenus;
            } else {
                try {
                    const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
                    this.state.internetMenus = rights?.internet_menus || {};
                } catch {
                    this.state.internetMenus = {};
                }
            }
            await this.load();
        });
        onWillUpdateProps(async (next) => {
            if (next.internetMenus && next.internetMenus !== this.props.internetMenus) {
                this.state.internetMenus = next.internetMenus;
            }
            const nextFilter = next.listFilter || "active";
            const curFilter = this.props.listFilter || "active";
            const tokenChanged = (next.listReloadToken || 0) !== (this.props.listReloadToken || 0);
            if (nextFilter !== curFilter || tokenChanged) {
                // Reset ngay — tránh hiện data mục trước / loading treo khi bấm nhanh.
                this.state.page = 1;
                this.state.currentPage = 1;
                this.state.remainTab = "all";
                if (nextFilter !== curFilter) {
                    this.state.regionFilter = "";
                    this.state.search = "";
                    this.state.providerFilter = "";
                }
                this.state.records = [];
                this.state.totalCount = 0;
                this.state.selected = {};
                this.state.loading = true;
                this.state.sectionOpen = true;
                if (nextFilter === "payment_forecast" && nextFilter !== curFilter) {
                    const n = nextMonthParts(1);
                    this.state.forecastYear = n.year;
                    this.state.forecastMonth = n.month;
                }
                if (nextFilter === "payment_due" && nextFilter !== curFilter) {
                    const n = nextMonthParts(0);
                    this.state.forecastYear = n.year;
                    this.state.forecastMonth = n.month;
                }
                await this.load(nextFilter);
            }
        });
        onWillUnmount(() => {
            if (this._searchTimer) {
                clearTimeout(this._searchTimer);
                this._searchTimer = null;
            }
            if (this._stickyRaf) {
                cancelAnimationFrame(this._stickyRaf);
                this._stickyRaf = null;
            }
            if (this._stickyRo) {
                this._stickyRo.disconnect();
                this._stickyRo = null;
            }
        });
    }

    /** Căn left sticky đúng mép cột Cửa hàng / Mã KH (đo width thật). */
    syncStickyColumns() {
        if (this._stickyRaf) {
            cancelAnimationFrame(this._stickyRaf);
        }
        this._stickyRaf = requestAnimationFrame(() => {
            this._stickyRaf = null;
            const root = this.tableScrollRef?.el;
            if (!root) {
                return;
            }
            const table = root.querySelector("table.lq-inet-table");
            if (!table) {
                return;
            }
            const check = table.querySelector("thead th.col-check");
            const stt = table.querySelector("thead th.col-stt");
            const store = table.querySelector("thead th.col-store");
            if (!check || !stt || !store) {
                return;
            }
            const wCheck = Math.ceil(check.getBoundingClientRect().width);
            const wStt = Math.ceil(stt.getBoundingClientRect().width);
            const leftStt = `${wCheck}px`;
            const leftStore = `${wCheck + wStt}px`;
            // Đóng băng dừng đúng sau cột Cửa hàng (không kéo sang Nhà cung cấp).
            if (table.style.getPropertyValue("--lq-left-stt") !== leftStt
                || table.style.getPropertyValue("--lq-left-store") !== leftStore) {
                table.style.setProperty("--lq-left-check", "0px");
                table.style.setProperty("--lq-left-stt", leftStt);
                table.style.setProperty("--lq-left-store", leftStore);
            }
            if (!this._stickyRo && typeof ResizeObserver !== "undefined") {
                this._stickyRo = new ResizeObserver(() => this.syncStickyColumns());
                this._stickyRo.observe(check);
                this._stickyRo.observe(stt);
                this._stickyRo.observe(store);
            }
        });
    }

    get actionContext() {
        return this.props.action?.context || {};
    }

    get listFilter() {
        return this.props.listFilter || this.props.action?.context?.phan_he_list_filter || "active";
    }

    get listNavId() {
        const map = {
            all: "list_active",
            active: "list_active",
            suspend: "list_suspend",
            liquidated: "list_liquidated",
            expire_soon: "expire_soon",
            expired: "payment_overdue",
            payment_due: "payment_schedule",
            payment_forecast: "payment_forecast",
            report_month: "report_month",
            report_quarter: "report_quarter",
            report_year: "report_year",
        };
        return map[this.listFilter] || "list_active";
    }

    get isForecastList() {
        return this.listFilter === "payment_forecast";
    }

    /** Toolbar / table bar giống Dự kiến TT (Lịch TT + Dự kiến). */
    get isForecastStyleList() {
        return this.listFilter === "payment_forecast" || this.listFilter === "payment_due";
    }

    get emptyMessage() {
        const map = {
            suspend: "Không có hợp đồng tạm ngưng",
            paused: "Không có hợp đồng tạm ngưng",
            liquidated: "Không có hợp đồng thanh lý",
            active: "Không có hợp đồng đang sử dụng",
            payment_due: "Không có lịch thanh toán trong kỳ",
            payment_forecast: "Không có HĐ có kỳ TT / ngày kết thúc trong tháng này",
            expired: "Không có hợp đồng quá hạn",
        };
        return map[this.listFilter] || "Không có dữ liệu";
    }

    get canWriteNav() {
        return internetNavCan(this.state.internetMenus, this.listNavId, "write");
    }

    get canCreateNav() {
        return internetNavCan(this.state.internetMenus, "store_declare", "create")
            || internetNavCan(this.state.internetMenus, this.listNavId, "create");
    }

    get canUnlinkNav() {
        return internetNavCan(this.state.internetMenus, this.listNavId, "unlink");
    }

    get pageMeta() {
        const base = FILTER_TITLES[this.listFilter] || FILTER_TITLES.all;
        if (this.isForecastList) {
            return {
                ...base,
                subtitle: `Dự kiến tháng ${this.state.forecastMonth}/${this.state.forecastYear}`,
            };
        }
        return base;
    }

    get forecastRows() {
        if (!this.isForecastList) {
            return this.state.records;
        }
        const year = Number(this.state.forecastYear);
        const month = Number(this.state.forecastMonth);
        const ymPrefix = `${year}-${pad2(month)}`;
        return (this.state.records || []).map((rec) => {
            const nextDue = rec.next_payment_date ? String(rec.next_payment_date).slice(0, 10) : "";
            let due;
            if (nextDue && nextDue.startsWith(ymPrefix)) {
                due = nextDue;
            } else if (rec.date_end && String(rec.date_end).slice(0, 10).startsWith(ymPrefix)) {
                due = String(rec.date_end).slice(0, 10);
            } else {
                due = projectDueInMonth(rec.date_end || rec.date_start || nextDue, year, month);
            }
            return {
                ...rec,
                forecast_due: due,
                forecast_amount: Number(rec.next_payment_amount || 0) > 0
                    ? Number(rec.next_payment_amount)
                    : Number(rec.contract_amount || 0),
            };
        }).filter((rec) => {
            // Đúng tháng/năm đang chọn, hoặc đã quá hạn
            const end = rec.date_end ? String(rec.date_end).slice(0, 10) : "";
            const todayStr = ymd(new Date());
            if (end && end < todayStr) {
                return true;
            }
            const nextDue = rec.next_payment_date ? String(rec.next_payment_date).slice(0, 10) : "";
            if (nextDue && nextDue.startsWith(ymPrefix)) {
                return true;
            }
            return Boolean(end && end.startsWith(ymPrefix));
        }).sort((a, b) => {
            // Quá hạn lên trước, rồi theo ngày kết thúc
            const ae = a.date_end ? String(a.date_end).slice(0, 10) : "";
            const be = b.date_end ? String(b.date_end).slice(0, 10) : "";
            const todayStr = ymd(new Date());
            const ao = ae && ae < todayStr ? 0 : 1;
            const bo = be && be < todayStr ? 0 : 1;
            if (ao !== bo) {
                return ao - bo;
            }
            return String(a.forecast_due).localeCompare(String(b.forecast_due)) || a.id - b.id;
        });
    }

    get forecastGroups() {
        // Một nhóm tháng đang chọn (dùng cho header bảng).
        const rows = this.forecastRows;
        return [{
            key: `${this.state.forecastYear}-${this.state.forecastMonth}`,
            label: `Tháng ${this.state.forecastMonth}/${this.state.forecastYear}`,
            count: rows.length,
            records: rows,
        }];
    }

    get isMobile() {
        return Boolean(this.ui?.isSmall);
    }

    get isPaymentMobile() {
        return this.isMobile && (
            this.listFilter === "payment_due"
            || this.listFilter === "payment_forecast"
            || this.listFilter === "expired"
        );
    }

    get navSections() {
        return INTERNET_NAV_SECTIONS;
    }

    get regionLabel() {
        return REGION_LABELS[this.state.regionFilter] || REGION_LABELS[""];
    }

    get dateRangeLabel() {
        const f = this.listFilter;
        if (f === "report_month" || f === "report_quarter" || f === "report_year") {
            const { from, to } = periodBounds(f);
            return `${formatDateVn(from)} - ${formatDateVn(to)}`;
        }
        const dates = this.state.records
            .flatMap((r) => [r.date_start, r.date_end])
            .filter(Boolean)
            .map((d) => String(d).slice(0, 10))
            .sort();
        if (!dates.length) {
            return "Tất cả thời gian";
        }
        return `${formatDateVn(dates[0])} - ${formatDateVn(dates[dates.length - 1])}`;
    }

    get baseDomain() {
        return this.buildBaseDomain(this.listFilter);
    }

    buildBaseDomain(listFilter) {
        const domain = [
            ["active", "=", true],
        ];
        if (this._internetTypeId) {
            domain.push(["service_type_id", "=", this._internetTypeId]);
        } else {
            domain.push(["service_type_id.code", "=", "internet"]);
        }
        const today = ymd(new Date());
        const soon = new Date();
        soon.setDate(soon.getDate() + 30);
        const soon30 = ymd(soon);
        const f = listFilter || "active";
        if (f === "active") {
            domain.push(["state", "=", "active"]);
        } else if (f === "payment_forecast") {
            // Tháng/năm đang chọn + luôn gồm HĐ quá hạn (chưa thanh lý)
            const y = Number(this.state.forecastYear) || new Date().getFullYear();
            const m = Number(this.state.forecastMonth) || (new Date().getMonth() + 1);
            const from = `${y}-${pad2(m)}-01`;
            const last = new Date(y, m, 0).getDate();
            const to = `${y}-${pad2(m)}-${pad2(last)}`;
            domain.push(["state", "=", "active"]);
            domain.push("|", "|",
                "&", ["date_end", ">=", from], ["date_end", "<=", to],
                "&", ["next_payment_date", ">=", from], ["next_payment_date", "<=", to],
                "&", ["date_end", "!=", false], ["date_end", "<", today]
            );
        } else if (f === "suspend" || f === "paused") {
            // Đồng bộ state / ops_status (action cũ lọc ops_status)
            domain.push("|", ["state", "=", "suspend"], ["ops_status", "=", "suspend"]);
        } else if (f === "liquidated") {
            domain.push("|",
                ["state", "in", ["liquidated", "cancel"]],
                ["ops_status", "=", "liquidated"]);
        } else if (f === "expire_soon") {
            domain.push(["state", "=", "active"]);
            domain.push(["date_end", ">=", today]);
            domain.push(["date_end", "<=", soon30]);
        } else if (f === "expired") {
            domain.push(["state", "=", "active"]);
            domain.push(["date_end", "<", today]);
        } else if (f === "payment_due") {
            // Lịch TT: còn ≤30 ngày hoặc đã quá hạn
            domain.push(["ops_status", "=", "active"]);
            domain.push(["state", "=", "active"]);
            domain.push(["date_end", "!=", false]);
            domain.push(["date_end", "<=", soon30]);
        } else if (f === "report_month" || f === "report_quarter" || f === "report_year") {
            const { from, to } = periodBounds(f);
            domain.push("|", ["date_start", "=", false], ["date_start", "<=", to]);
            domain.push("|", ["date_end", "=", false], ["date_end", ">=", from]);
        }
        return domain;
    }

    async ensureInternetTypeId() {
        if (this._internetTypeId) {
            return this._internetTypeId;
        }
        try {
            const rows = await this.orm.searchRead(
                "phan.he.service.type",
                [["code", "=", "internet"]],
                ["id"],
                { limit: 1 }
            );
            this._internetTypeId = rows?.[0]?.id || null;
        } catch {
            this._internetTypeId = null;
        }
        return this._internetTypeId;
    }

    get queryDomain() {
        return this.buildQueryDomain(this.listFilter);
    }

    buildQueryDomain(listFilter) {
        const domain = [...this.buildBaseDomain(listFilter)];
        if (this.state.regionFilter) {
            domain.push(["store_mien", "=", this.state.regionFilter]);
        }
        if (this.state.providerFilter) {
            domain.push(["provider_id", "=", Number(this.state.providerFilter)]);
        }
        const q = (this.state.search || "").trim();
        if (q) {
            domain.push("|", "|", "|", ["name", "ilike", q], ["code", "ilike", q], ["customer_code", "ilike", q], [
                "store_id.name",
                "ilike",
                q,
            ]);
        }
        return domain;
    }

    get filteredRecords() {
        return this.state.records;
    }

    get totalPages() {
        const size = this.state.pageSize || 10;
        const total = this.isForecastList ? this.forecastRows.length : (this.state.totalCount || 0);
        return Math.max(1, Math.ceil(total / size));
    }

    get pageRecords() {
        const size = this.state.pageSize || 10;
        const start = (this.state.page - 1) * size;
        const source = this.isForecastList ? this.forecastRows : this.state.records;
        return source.slice(start, start + size).map((rec, idx) => ({
            ...rec,
            stt: start + idx + 1,
        }));
    }

    get tabCounts() {
        const rows = this.pageRecords;
        const counts = { all: rows.length, ok: 0, warn: 0, danger: 0 };
        for (const rec of rows) {
            const tone = this.remainTone(rec);
            if (tone === "danger") {
                counts.danger += 1;
            } else if (tone === "warning") {
                counts.warn += 1;
            } else {
                counts.ok += 1;
            }
        }
        return counts;
    }

    get cardRecords() {
        const tab = this.state.remainTab || "all";
        if (tab === "all") {
            return this.pageRecords;
        }
        const map = { ok: "ok", warn: "warning", danger: "danger" };
        const want = map[tab] || tab;
        return this.pageRecords.filter((rec) => this.remainTone(rec) === want);
    }

    get pageInfo() {
        const total = this.isForecastList ? this.forecastRows.length : (this.state.totalCount || 0);
        if (!total) {
            return "Hiển thị 0 trên 0 kết quả";
        }
        const size = this.state.pageSize || 10;
        const start = (this.state.page - 1) * size + 1;
        const end = Math.min(this.state.page * size, total);
        return `Hiển thị ${start} - ${end} trên ${total} kết quả`;
    }

    get pageNumbers() {
        const pages = [];
        const max = Math.min(this.totalPages, 8);
        for (let i = 1; i <= max; i++) {
            pages.push(i);
        }
        return pages;
    }

    get allSelectedOnPage() {
        const rows = this.pageRecords;
        return rows.length > 0 && rows.every((r) => this.state.selected[r.id]);
    }

    isGroupOpen(id) {
        return Boolean(this.state.openGroups[id]);
    }

    toggleGroup(id) {
        this.state.openGroups[id] = !this.state.openGroups[id];
    }

    toggleSidebar() {
        this.state.isSidebarCollapsed = !this.state.isSidebarCollapsed;
    }

    startResizing(e) {
        e.preventDefault();
        this.state.dragging = true;
        this._startX = e.clientX;
        this._startW = this.state.sidebarWidth;
        document.body.style.cursor = "col-resize";
        window.addEventListener("mousemove", this._onMove);
        window.addEventListener("mouseup", this._onUp);
    }

    _onMove(moveEvent) {
        if (!this.state.dragging) {
            return;
        }
        this.state.sidebarWidth = clampWidth(this._startW + (moveEvent.clientX - this._startX));
    }

    _onUp() {
        if (!this.state.dragging) {
            return;
        }
        this._stopResize();
        try {
            window.localStorage.setItem(WIDTH_KEY, String(this.state.sidebarWidth));
        } catch {
            /* ignore */
        }
    }

    _stopResize() {
        this.state.dragging = false;
        document.body.style.cursor = "default";
        window.removeEventListener("mousemove", this._onMove);
        window.removeEventListener("mouseup", this._onUp);
    }

    statusMeta(status) {
        return OPS_STATUS_META[status] || OPS_STATUS_META.active;
    }

    opsStatusCode(rec) {
        return rec.ops_status || rec.state || "active";
    }

    opsStatusLabel(rec) {
        const code = this.opsStatusCode(rec);
        if (code === "liquidated" || rec.state === "cancel") {
            return "Đã thanh lý";
        }
        return this.statusMeta(code === "suspend" ? "suspend" : code === "liquidated" ? "liquidated" : "active").label;
    }

    remainTone(rec) {
        const days = Number(rec.remaining_days);
        if (!Number.isFinite(days) && !rec.date_end) {
            return "ok";
        }
        if (days < 0 || rec.alert_level === "expired") {
            return "danger";
        }
        if (days <= 30 || rec.alert_level === "warn" || rec.alert_level === "danger") {
            return "warning";
        }
        return "ok";
    }

    cardAccent(rec) {
        const ops = this.opsStatusCode(rec);
        if (ops === "suspend") {
            return "suspend";
        }
        if (ops === "liquidated" || ops === "cancel") {
            return "liquidated";
        }
        const tone = this.remainTone(rec);
        if (tone === "danger") {
            return "danger";
        }
        if (tone === "warning") {
            return "warn";
        }
        return "ok";
    }

    setRemainTab(tab) {
        this.state.remainTab = tab || "all";
    }

    setForecastMonth(year, month) {
        this.state.forecastYear = Number(year);
        this.state.forecastMonth = Number(month);
        this.state.page = 1;
        this.state.currentPage = 1;
        this.load();
    }

    onForecastMonthChange(ev) {
        this.setForecastMonth(this.state.forecastYear, Number(ev.target.value) || 1);
    }

    onForecastYearChange(ev) {
        this.setForecastMonth(Number(ev.target.value) || new Date().getFullYear(), this.state.forecastMonth);
    }

    setRegionFilter(value) {
        this.state.regionFilter = value || "";
        this.state.page = 1;
        this.state.currentPage = 1;
        this.load();
    }

    toggleTodaySection() {
        this.state.sectionOpen = !this.state.sectionOpen;
    }

    statusCode(rec) {
        return this.remainTone(rec) === "ok" ? "active" : this.remainTone(rec);
    }

    formatDate(value) {
        return formatDateVn(value);
    }

    formatMoney(value) {
        return formatMoneyVn(value);
    }

    storeRecordOf(rec) {
        const s = rec?.store_id;
        if (!s) {
            return { id: false, name: "" };
        }
        if (Array.isArray(s)) {
            return { id: s[0], name: s[1] || "" };
        }
        if (typeof s === "object") {
            return { id: s.id, name: s.display_name || s.name || "" };
        }
        return { id: s, name: rec.name || "" };
    }

    storeName(rec) {
        return this.storeRecordOf(rec).name || rec.name || "—";
    }

    m2oName(value) {
        if (!value) {
            return "—";
        }
        if (Array.isArray(value)) {
            return value[1] || "—";
        }
        if (typeof value === "object") {
            return value.display_name || value.name || "—";
        }
        return String(value);
    }

    lineCode(rec) {
        return rec.customer_code || rec.code || `ID-${rec.id}`;
    }

    customerCodeLabel(rec) {
        // Giống workspace: hiện mã khách hàng thật, không sinh "Mã KH-000xxx"
        const code = String(rec.customer_code || "").trim();
        return code || "—";
    }

    contractCode(rec) {
        if (rec.code) {
            return rec.code;
        }
        return `HD${String(rec.id).padStart(5, "0")}`;
    }

    providerRecord(rec) {
        const p = rec.provider_id;
        if (!p) {
            return { id: false, name: "" };
        }
        if (Array.isArray(p)) {
            return { id: p[0], name: p[1] || "" };
        }
        if (typeof p === "object") {
            return { id: p.id, name: p.display_name || p.name || "" };
        }
        const found = (this.state.providers || []).find((x) => String(x.id) === String(p));
        return { id: p, name: found ? found.name : "" };
    }

    providerName(rec) {
        return this.providerRecord(rec).name || "—";
    }

    providerMark(rec) {
        const name = this.providerName(rec).toUpperCase();
        if (name.includes("FPT")) {
            return "F";
        }
        if (name.includes("VNPT")) {
            return "V";
        }
        if (name.includes("VIETTEL")) {
            return "VT";
        }
        return (name[0] || "•");
    }

    providerClass(rec) {
        const name = this.providerName(rec).toUpperCase();
        if (name.includes("FPT")) {
            return "is-fpt";
        }
        if (name.includes("VNPT")) {
            return "is-vnpt";
        }
        if (name.includes("VIETTEL")) {
            return "is-viettel";
        }
        return "";
    }

    remainLabel(rec) {
        if (rec.remaining_time) {
            return rec.remaining_time;
        }
        const days = Number(rec.remaining_days);
        if (!Number.isFinite(days) || rec.remaining_days === false || rec.remaining_days === undefined) {
            return "—";
        }
        if (days < 0) {
            return `Quá hạn ${Math.abs(days)} ngày`;
        }
        return `Còn ${days} ngày`;
    }

    remainIcon(rec) {
        const code = this.statusCode(rec);
        if (code === "danger") {
            return "fa fa-exclamation-circle";
        }
        if (code === "warning") {
            return "fa fa-clock-o";
        }
        return "fa fa-calendar";
    }

    storeAddr(rec) {
        return rec.name && rec.name !== this.storeName(rec) ? rec.name : this.lineCode(rec);
    }

    statusLabel(rec) {
        if (this.statusCode(rec) === "danger" && rec.ops_status !== "liquidated") {
            return Number(rec.remaining_days || 0) < 0 ? "Đã hết hạn" : this.statusMeta(rec.ops_status).label;
        }
        if (this.statusCode(rec) === "warning" && rec.ops_status === "active") {
            return "Sắp hết hạn";
        }
        return this.statusMeta(rec.ops_status).label;
    }

    statusIcon(rec) {
        const code = this.statusCode(rec);
        if (code === "danger") {
            return "fa fa-times-circle";
        }
        if (code === "warning") {
            return rec.ops_status === "suspend" ? "fa fa-pause-circle" : "fa fa-exclamation-circle";
        }
        return "fa fa-check-circle";
    }

    remainingClass(rec) {
        const days = Number(rec.remaining_days || 0);
        if (days < 0 || rec.alert_level === "danger" || rec.alert_level === "expired") {
            return "is-danger";
        }
        if (days <= 30 || rec.alert_level === "warn") {
            return "is-warn";
        }
        return "is-ok";
    }

    async load(filterOverride) {
        const seq = ++this._loadSeq;
        this.state.loading = true;
        try {
            await this.ensureInternetTypeId();
            const listFilter = filterOverride || this.listFilter;
            const domain = this.buildQueryDomain(listFilter);
            const isForecast = listFilter === "payment_forecast";
            const isLightList = listFilter === "suspend" || listFilter === "liquidated" || listFilter === "paused";
            const pageSize = isForecast ? 2000 : (this.state.pageSize || 10);
            const page = this.state.page || 1;
            const offset = isForecast ? 0 : (page - 1) * pageSize;
            const needProviders = !isLightList && (!this._providersLoaded || !(this.state.providers || []).length);
            const orderBy = (
                listFilter === "payment_due" || listFilter === "expired" || listFilter === "payment_forecast"
            )
                ? "date_end asc, id desc"
                : isLightList
                    ? "id desc"
                    : "store_mien_rank asc, store_name_sort asc, id asc";
            const listFields = [
                "name",
                "code",
                "customer_code",
                "store_id",
                "provider_id",
                "date_start",
                "date_end",
                "bandwidth",
                "contract_amount",
                "ops_status",
                "state",
                "remaining_days",
                "remaining_time",
                "alert_level",
                "store_mien",
                "usage_address",
                "note",
                "package_name",
                "next_payment_amount",
                "invoice_filename",
            ];
            if (isForecast) {
                listFields.push("next_payment_date");
            }
            const tasks = [
                this.orm.searchCount("phan.he.service", domain),
                this.orm.searchRead(
                    "phan.he.service",
                    domain,
                    listFields,
                    {
                        order: orderBy,
                        limit: pageSize,
                        offset,
                    }
                ),
            ];
            if (needProviders) {
                tasks.push(
                    this.orm.searchRead(
                        "phan.he.provider",
                        [["active", "=", true]],
                        ["name"],
                        { order: "name asc", limit: 300 }
                    )
                );
            }
            const results = await Promise.all(tasks);
            if (seq !== this._loadSeq) {
                return;
            }
            const totalCount = results[0];
            const records = results[1];
            if (needProviders) {
                this.state.providers = results[2] || [];
                this._providersLoaded = true;
            }
            const providers = this.state.providers || [];
            this.state.totalCount = isForecast ? (records || []).length : totalCount;
            const providerMap = Object.fromEntries((providers || []).map((p) => [String(p.id), p.name]));
            const pageRows = isForecast ? (records || []) : (records || []).slice(0, pageSize);
            this.state.records = pageRows.map((rec) => {
                const p = rec.provider_id;
                let pid = false;
                let pname = "";
                if (Array.isArray(p)) {
                    pid = p[0];
                    pname = p[1] || "";
                } else if (p && typeof p === "object") {
                    pid = p.id;
                    pname = p.display_name || p.name || "";
                } else if (p) {
                    pid = p;
                }
                if (pid && !pname) {
                    pname = providerMap[String(pid)] || "";
                }
                return { ...rec, provider_id: pid ? [pid, pname] : false };
            });
            const stats = {
                total: totalCount,
                active: 0,
                suspend: 0,
                liquidated: 0,
                expireSoon: 0,
                expired: 0,
                monthlyFee: 0,
            };
            for (const r of this.state.records) {
                if (r.ops_status === "active") {
                    stats.active += 1;
                    stats.monthlyFee += Number(r.contract_amount || 0);
                } else if (r.ops_status === "suspend") {
                    stats.suspend += 1;
                } else if (r.ops_status === "liquidated") {
                    stats.liquidated += 1;
                }
                const days = Number(r.remaining_days || 0);
                if (days < 0) {
                    stats.expired += 1;
                } else if (days <= 30) {
                    stats.expireSoon += 1;
                }
            }
            this.state.stats = stats;
            this.state.selected = {};
            this.state.openMenuId = null;
            const clientPageSize = this.state.pageSize || 10;
            const maxPage = isForecast
                ? Math.max(1, Math.ceil((this.state.records.length || 0) / clientPageSize))
                : Math.max(1, Math.ceil((totalCount || 0) / (pageSize || 10)) || 1);
            if (this.state.page > maxPage) {
                this.state.page = 1;
                this.state.currentPage = 1;
                this.state.loading = false;
                if (!isForecast) {
                    return this.load(listFilter);
                }
            }
            if (this.state.detailRecord) {
                const fresh = this.state.records.find((r) => r.id === this.state.detailRecord.id);
                if (fresh) {
                    this.state.detailRecord = fresh;
                    if (!this.state.detailEditing) {
                        this.state.detailForm = this._formFromRecord(fresh);
                    }
                }
            }
        } catch (error) {
            if (seq !== this._loadSeq) {
                return;
            }
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được danh sách Internet.",
                { type: "danger" }
            );
        } finally {
            if (seq === this._loadSeq) {
                this.state.loading = false;
            }
        }
    }

    async exportListExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const result = await this.orm.call("phan.he.service", "export_internet_list_excel", [
                this.listFilter,
                this.state.regionFilter || false,
                this.state.search || "",
            ]);
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            const bin = atob(result.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const blob = new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = result.filename || "Danh_sach_Internet.xlsx";
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add("Đã xuất file Excel.", { type: "success" });
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không xuất được Excel.", {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
        this.state.currentPage = 1;
        if (this._searchTimer) {
            clearTimeout(this._searchTimer);
        }
        this._searchTimer = setTimeout(() => {
            this._searchTimer = null;
            this.load();
        }, 320);
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.page = 1;
        this.state.currentPage = 1;
        this.load();
    }

    onPageSizeChange(ev) {
        const size = Number(ev.target.value) || 10;
        this.state.pageSize = size;
        this.state.limit = size;
        this.state.page = 1;
        this.state.currentPage = 1;
        this.load();
    }

    resetFilters() {
        this.state.search = "";
        this.state.statusFilter = "";
        this.state.providerFilter = "";
        this.state.bandwidthFilter = "";
        this.state.regionFilter = "";
        this.state.page = 1;
        this.load();
    }

    toggleSelectAll(ev) {
        const checked = ev.target.checked;
        const next = { ...this.state.selected };
        for (const row of this.pageRecords) {
            if (checked) {
                next[row.id] = true;
            } else {
                delete next[row.id];
            }
        }
        this.state.selected = next;
    }

    toggleSelect(id, ev) {
        const next = { ...this.state.selected };
        if (ev.target.checked) {
            next[id] = true;
        } else {
            delete next[id];
        }
        this.state.selected = next;
    }

    setPage(page) {
        const p = Math.min(Math.max(1, page), this.totalPages);
        this.state.page = p;
        this.state.currentPage = p;
        this.state.openMenuId = null;
        this.load();
    }

    toggleRowMenu(id, ev) {
        ev.stopPropagation();
        const rec = this.state.records.find((r) => r.id === id);
        if (rec) {
            this.openLineDetail(rec);
        }
    }

    closeMenus() {
        this.state.openMenuId = null;
    }

    _formFromRecord(rec) {
        const provider = this.providerRecord(rec);
        return {
            customer_code: rec.customer_code || "",
            bandwidth: rec.bandwidth || "",
            date_start: rec.date_start ? String(rec.date_start).slice(0, 10) : "",
            date_end: rec.date_end ? String(rec.date_end).slice(0, 10) : "",
            contract_amount: rec.contract_amount || 0,
            ops_status: rec.ops_status || "active",
            provider_id: provider.id || "",
            usage_address: rec.usage_address || "",
            note: rec.note || "",
            package_name: rec.package_name || "",
        };
    }

    get detailRec() {
        return this.state.detailRecord;
    }

    get detailInvoiceName() {
        if (this.state.detailInvoicePending?.filename) {
            return this.state.detailInvoicePending.filename;
        }
        return this.state.detailRecord?.invoice_filename || "";
    }

    openLineDetail(rec) {
        this.state.openMenuId = null;
        this.state.detailRecord = rec;
        this.state.detailForm = this._formFromRecord(rec);
        this.state.detailInvoicePending = null;
        this.state.detailEditing = false;
        this.state.detailOpen = true;
    }

    closeLineDetail() {
        this.state.detailOpen = false;
        this.state.detailEditing = false;
        this.state.detailSaving = false;
        this.state.detailRecord = null;
        this.state.detailForm = {};
        this.state.detailInvoicePending = null;
    }

    startEditDetail() {
        if (!this.canWriteNav || !this.state.detailRecord) {
            return;
        }
        this.state.detailForm = this._formFromRecord(this.state.detailRecord);
        this.state.detailInvoicePending = null;
        this.state.detailEditing = true;
    }

    cancelDetail() {
        if (this.state.detailEditing) {
            this.state.detailForm = this._formFromRecord(this.state.detailRecord);
            this.state.detailInvoicePending = null;
            this.state.detailEditing = false;
            return;
        }
        this.closeLineDetail();
    }

    onDetailField(field, ev) {
        this.state.detailForm[field] = ev.target.value;
    }

    clearDetailInvoicePending() {
        this.state.detailInvoicePending = null;
    }

    async onDetailInvoiceChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        try {
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const result = String(reader.result || "");
                    resolve(result.includes(",") ? result.split(",")[1] : result);
                };
                reader.onerror = () => reject(reader.error);
                reader.readAsDataURL(file);
            });
            this.state.detailInvoicePending = { filename: file.name, data };
        } catch (error) {
            this.notification.add(
                error?.message || "Không đọc được file hóa đơn.",
                { type: "danger" }
            );
        }
    }

    async saveLineDetail() {
        const rec = this.state.detailRecord;
        if (!rec || this.state.detailSaving) {
            return;
        }
        const form = this.state.detailForm;
        const vals = {
            customer_code: form.customer_code || false,
            bandwidth: form.bandwidth || false,
            date_start: form.date_start || false,
            date_end: form.date_end || false,
            contract_amount: Number(form.contract_amount || 0),
            ops_status: form.ops_status || "active",
            provider_id: form.provider_id ? Number(form.provider_id) : false,
            usage_address: form.usage_address || false,
            note: form.note || false,
            package_name: form.package_name || false,
        };
        if (this.state.detailInvoicePending?.data) {
            vals.invoice_file = this.state.detailInvoicePending.data;
            vals.invoice_filename = this.state.detailInvoicePending.filename || "hoa_don";
        }
        this.state.detailSaving = true;
        try {
            await this.orm.write("phan.he.service", [rec.id], vals);
            this.notification.add("Đã lưu thông tin đường truyền.", { type: "success" });
            this.state.detailEditing = false;
            this.state.detailInvoicePending = null;
            await this.load();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Không lưu được đường truyền.",
                { type: "danger" }
            );
        } finally {
            this.state.detailSaving = false;
        }
    }

    async archiveRecord(rec) {
        if (!window.confirm(`Xóa «${this.storeName(rec)}» khỏi danh sách? Có thể khôi phục trong kho lưu trữ.`)) {
            return;
        }
        try {
            await this.orm.write("phan.he.service", [rec.id], { active: false });
            this.notification.add("Đã xóa hợp đồng khỏi danh sách.", { type: "success" });
            this.closeLineDetail();
            await this.load();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Không xóa được hợp đồng.",
                { type: "danger" }
            );
        }
    }

    async purgeRecord(rec) {
        if (!window.confirm(`Xóa vĩnh viễn «${this.storeName(rec)}»? Không lưu, không hoàn tác.`)) {
            return;
        }
        try {
            await this.orm.unlink("phan.he.service", [rec.id]);
            this.notification.add("Đã xóa vĩnh viễn hợp đồng.", { type: "success" });
            this.closeLineDetail();
            await this.load();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Không xóa vĩnh viễn được hợp đồng.",
                { type: "danger" }
            );
        }
    }

    async deleteLineDetail() {
        if (!this.state.detailRecord) {
            return;
        }
        await this.purgeRecord(this.state.detailRecord);
    }

    openOverview() {
        this.action.doAction("lug_phan_he.action_phan_he_dashboard");
    }

    onNavChild(child) {
        if (!child) {
            return;
        }
        this.state.activeNav = child.id;
        if (child.reportPeriod) {
            this.action.doAction("lug_phan_he.action_phan_he_dashboard", {
                additionalContext: { phan_he_dash_view: "reports", phan_he_report_period: child.reportPeriod },
            });
            return;
        }
        if (child.id === "list_all" && this.listFilter === "all") {
            return;
        }
        // Đồng bộ filter qua props dashboard — không doAction (tránh reload cả client action).
        if (["list_active", "list_suspend", "list_liquidated", "list_all", "payment_schedule", "payment_overdue", "payment_forecast", "expire_soon", "expired"].includes(child.id)) {
            this.notification.add("Dùng menu bên trái để chuyển mục.", { type: "info" });
            return;
        }
        if (child.action) {
            this.action.doAction(child.action);
        }
    }

    onAdd() {
        if (!this.canCreateNav) {
            this.notification.add("Bạn không có quyền Thêm.", { type: "warning" });
            return;
        }
        this.openEntryForm(false);
    }

    openEntryForm(resId = false) {
        if (this.props.onOpenEntry) {
            this.props.onOpenEntry(resId || false);
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Khai báo cửa hàng",
            res_model: "phan.he.service",
            res_id: resId || false,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
            context: {
                form_view_initial_mode: (!resId ? this.canCreateNav : this.canWriteNav)
                    ? "edit"
                    : "readonly",
                default_ops_status: "active",
                default_state: "active",
                default_service_type_code: "internet",
                phan_he_service_type_code: "internet",
                phan_he_internet_menu:
                    INTERNET_NAV_TO_CODE[this.listNavId]
                    || (!resId ? "internet_entry" : "internet_active"),
            },
        });
    }

    openStore(rec) {
        this.openEntryForm(rec.id);
    }

    openRecord(id) {
        this.state.openMenuId = null;
        this.openEntryForm(id);
    }

    openProvider(rec) {
        const { id } = this.providerRecord(rec);
        if (id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: "Nhà cung cấp",
                res_model: "phan.he.provider",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
            return;
        }
        this.action.doAction("lug_phan_he.action_phan_he_provider");
    }

    hasInvoice(rec) {
        return Boolean(rec?.invoice_filename || rec?.invoice_file);
    }

    viewInvoice(rec) {
        if (!rec?.id || !this.hasInvoice(rec)) {
            return;
        }
        const filename = encodeURIComponent(rec.invoice_filename || "hoa_don");
        window.open(
            `/web/content/phan.he.service/${rec.id}/invoice_file?download=false&filename=${filename}`,
            "_blank",
            "noopener"
        );
    }
}

export class PhanHeInternetList extends Component {
    static template = "lug_phan_he.PhanHeInternetList";
    static components = { PhanHeInternetListBoard };
    static props = { ...standardActionServiceProps, "*": true };

    get boardFilter() {
        return this.props.action?.context?.phan_he_list_filter || "all";
    }
}

registry.category("actions").add("phan_he_internet_list", PhanHeInternetList);

const internetFormViews = registry.category("views");
if (!internetFormViews.contains("phan_he_internet_form")) {
    internetFormViews.add("phan_he_internet_form", {
        ...formView,
        Controller: PhanHeInternetFormController,
    });
}

const PAY_META = {
    paid: { label: "Đã thanh toán", className: "is-paid" },
    partial: { label: "Thanh toán 1 phần", className: "is-partial" },
    unpaid: { label: "Chưa thanh toán", className: "is-unpaid" },
    none: { label: "Không phát sinh", className: "is-none" },
};

const barValuePlugin = {
    id: "lqBarValue",
    afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        const ctx = chart.ctx;
        ctx.save();
        ctx.fillStyle = "#334155";
        ctx.font = "700 12px Segoe UI, sans-serif";
        ctx.textAlign = "center";
        meta.data.forEach((el, i) => {
            const v = chart.data.datasets[0].data[i];
            if (v == null) {
                return;
            }
            ctx.fillText(String(v), el.x, el.y - 8);
        });
        ctx.restore();
    },
};

export class PhanHeMonthCostBoard extends Component {
    static template = "lug_phan_he.PhanHeMonthCostBoard";
    static props = {
        onOpenEntry: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            region: "all",
            providerId: "",
            payStatus: "all",
            dueTab: "all",
            search: "",
            tableRegion: "all",
            tableProvider: "",
            tablePay: "all",
            page: 1,
            pageSize: 10,
            data: {},
            selected: {},
        });
        this.lineRef = useRef("costLine");
        this.barRef = useRef("dueBar");
        this.donutRef = useRef("payDonut");
        this.charts = {};
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                this.renderCharts();
                return () => this.destroyCharts();
            },
            () => [this.state.data, this.state.loading]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    get kpi() {
        return this.state.data.kpi || {};
    }

    get monthLabel() {
        return this.state.data.month_label || `Tháng ${pad2(this.state.month)}/${this.state.year}`;
    }

    get padMonth() {
        return `${pad2(this.state.month)}/${this.state.year}`;
    }

    get providers() {
        return this.state.data.providers || [];
    }

    get regions() {
        return this.state.data.regions || [];
    }

    get donutRows() {
        return (this.state.data.donut || []).map((d) => ({
            ...d,
            pctLabel: `(${d.pct}%)`,
        }));
    }

    kpiCountLabel(kind) {
        const kpi = this.kpi;
        const n = kind === "paid" ? kpi.paid_count : kind === "unpaid" ? kpi.unpaid_count : kpi.total_count;
        return `${n || 0} hợp đồng`;
    }

    get filteredRows() {
        const q = (this.state.search || "").trim().toLowerCase();
        return (this.state.data.rows || []).filter((row) => {
            if (this.state.dueTab !== "all" && row.due_key !== this.state.dueTab) {
                return false;
            }
            if (this.state.tableRegion !== "all" && row.region !== this.state.tableRegion) {
                return false;
            }
            if (this.state.tableProvider && String(row.provider_id) !== String(this.state.tableProvider)) {
                return false;
            }
            if (this.state.tablePay !== "all" && row.pay_status !== this.state.tablePay) {
                return false;
            }
            if (!q) {
                return true;
            }
            return `${row.store} ${row.code}`.toLowerCase().includes(q);
        });
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.filteredRows.length / this.state.pageSize));
    }

    get pageRows() {
        const start = (this.state.page - 1) * this.state.pageSize;
        return this.filteredRows.slice(start, start + this.state.pageSize).map((row, idx) => ({
            ...row,
            stt: start + idx + 1,
        }));
    }

    get pageInfo() {
        const total = this.filteredRows.length;
        if (!total) {
            return "Hiển thị 0 trên 0 bản ghi";
        }
        const start = (this.state.page - 1) * this.state.pageSize + 1;
        const end = Math.min(this.state.page * this.state.pageSize, total);
        return `Hiển thị ${start} - ${end} trên ${total} bản ghi`;
    }

    get pageNumbers() {
        const max = Math.min(this.totalPages, 8);
        return Array.from({ length: max }, (_, i) => i + 1);
    }

    remainClass(row) {
        const d = Number(row.remaining_days);
        if (d < 15) {
            return "is-hot";
        }
        if (d <= 30) {
            return "is-warm";
        }
        return "is-muted";
    }

    remainLabel(row) {
        const d = Number(row.remaining_days);
        if (!Number.isFinite(d)) {
            return "—";
        }
        if (d < 0) {
            return `Quá hạn ${Math.abs(d)} ngày`;
        }
        return `${d} ngày`;
    }

    payMeta(row) {
        return PAY_META[row.pay_status] || PAY_META.none;
    }

    payClass(row) {
        return "lq-mc-pay " + this.payMeta(row).className;
    }

    payLabel(row) {
        return this.payMeta(row).label;
    }

    formatMoney(v) {
        return formatMoneyVn(v);
    }

    formatDate(v) {
        return formatDateVn(v);
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("phan.he.dashboard", "get_month_cost_board", [{
                year: this.state.year,
                month: this.state.month,
                region: this.state.region,
                provider_id: this.state.providerId || false,
                pay_status: this.state.payStatus,
            }]);
            this.state.page = 1;
            this.state.selected = {};
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không tải được chi phí tháng.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    shiftMonth(delta) {
        let m = this.state.month + delta;
        let y = this.state.year;
        if (m < 1) {
            m = 12;
            y -= 1;
        } else if (m > 12) {
            m = 1;
            y += 1;
        }
        this.state.month = m;
        this.state.year = y;
        this.load();
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        this.load();
    }

    onTableFilter(field, ev) {
        this.state[field] = field === "search" ? ev.target.value : ev.target.value;
        this.state.page = 1;
    }

    setDueTab(tab) {
        this.state.dueTab = tab;
        this.state.page = 1;
    }

    setPage(page) {
        this.state.page = Math.min(Math.max(1, page), this.totalPages);
    }

    openRow(row) {
        if (this.props.onOpenEntry) {
            this.props.onOpenEntry(row.id);
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

    exportCsv() {
        const rows = this.filteredRows;
        const header = ["STT", "Cửa hàng", "Mã KH", "Nhà cung cấp", "Ngày bắt đầu", "Ngày kết thúc", "Còn lại", "Cước tháng", "Đã thanh toán", "Còn phải trả", "Trạng thái"];
        const lines = [header.join(",")];
        rows.forEach((r, i) => {
            const cells = [
                i + 1,
                `"${(r.store || "").replace(/"/g, '""')}"`,
                r.code,
                `"${(r.provider || "").replace(/"/g, '""')}"`,
                r.date_start || "",
                r.date_end || "",
                r.remaining_days,
                r.monthly,
                r.paid,
                r.remain,
                this.payMeta(r).label,
            ];
            lines.push(cells.join(","));
        });
        const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Chi_phi_thang_${this.state.year}_${pad2(this.state.month)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            try {
                this.charts[key].destroy();
            } catch {
                /* ignore */
            }
            delete this.charts[key];
        }
    }

    renderCharts() {
        this.destroyCharts();
        if (this.state.loading || typeof Chart === "undefined") {
            return;
        }
        const weeks = this.state.data.weeks || [];
        const lineEl = this.lineRef.el;
        if (lineEl) {
            this.charts.line = new Chart(lineEl, {
                type: "line",
                data: {
                    labels: weeks.map((w) => [w.label, w.sub]),
                    datasets: [
                        {
                            label: "Tổng chi phí",
                            data: weeks.map((w) => Number(w.total || 0) / 1e6),
                            borderColor: "#7c3aed",
                            backgroundColor: "rgba(124, 58, 237, 0.12)",
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: "#7c3aed",
                        },
                        {
                            label: "Đã thanh toán",
                            data: weeks.map((w) => Number(w.paid || 0) / 1e6),
                            borderColor: "#22c55e",
                            backgroundColor: "transparent",
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: "#22c55e",
                        },
                        {
                            label: "Còn phải trả",
                            data: weeks.map((w) => Number(w.remain || 0) / 1e6),
                            borderColor: "#f59e0b",
                            backgroundColor: "transparent",
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: "#f59e0b",
                        },
                    ],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: "#94a3b8", font: { size: 10 } },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: "#94a3b8",
                                callback: (v) => (v === 0 ? "0đ" : `${v} tr`),
                            },
                            grid: { color: "rgba(148,163,184,0.25)" },
                        },
                    },
                },
            });
        }
        const bars = this.state.data.due_bars || [];
        const barEl = this.barRef.el;
        if (barEl) {
            this.charts.bar = new Chart(barEl, {
                type: "bar",
                data: {
                    labels: bars.map((b) => b.label),
                    datasets: [{
                        data: bars.map((b) => b.count),
                        backgroundColor: bars.map((b) => b.color),
                        borderRadius: 8,
                        maxBarThickness: 48,
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    layout: { padding: { top: 22 } },
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#64748b" } },
                        y: { beginAtZero: true, ticks: { stepSize: 2, color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.2)" } },
                    },
                },
                plugins: [barValuePlugin],
            });
        }
        const donut = this.state.data.donut || [];
        const donutEl = this.donutRef.el;
        if (donutEl) {
            const total = this.kpi.total_count || 0;
            this.charts.donut = new Chart(donutEl, {
                type: "doughnut",
                data: {
                    labels: donut.map((d) => d.label),
                    datasets: [{
                        data: donut.map((d) => d.count),
                        backgroundColor: donut.map((d) => d.color),
                        borderWidth: 0,
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    cutout: "68%",
                    plugins: { legend: { display: false } },
                },
                plugins: [{
                    id: "lqDonutCenter",
                    afterDraw(chart) {
                        const { ctx, chartArea } = chart;
                        if (!chartArea) {
                            return;
                        }
                        const x = (chartArea.left + chartArea.right) / 2;
                        const y = (chartArea.top + chartArea.bottom) / 2;
                        ctx.save();
                        ctx.textAlign = "center";
                        ctx.fillStyle = "#0f172a";
                        ctx.font = "800 22px Segoe UI, sans-serif";
                        ctx.fillText(String(total), x, y - 4);
                        ctx.fillStyle = "#94a3b8";
                        ctx.font = "600 11px Segoe UI, sans-serif";
                        ctx.fillText("hợp đồng", x, y + 14);
                        ctx.restore();
                    },
                }],
            });
        }
    }
}

export class PhanHeQuarterCostBoard extends Component {
    static template = "lug_phan_he.PhanHeQuarterCostBoard";
    static props = {
        onOpenEntry: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            year: now.getFullYear(),
            quarter: Math.floor(now.getMonth() / 3) + 1,
            region: "all",
            providerId: "",
            payStatus: "all",
            search: "",
            tableRegion: "all",
            tableProvider: "",
            tablePay: "all",
            tableStatus: "all",
            exporting: false,
            page: 1,
            pageSize: 10,
            data: {},
        });
        this.lineRef = useRef("qLine");
        this.barRef = useRef("qBar");
        this.donutRef = useRef("qDonut");
        this.charts = {};
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                this.renderCharts();
                return () => this.destroyCharts();
            },
            () => [this.state.data, this.state.loading]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    get kpi() {
        return this.state.data.kpi || {};
    }

    get quarterLabel() {
        return this.state.data.quarter_label || `Quý ${this.state.quarter}/${this.state.year}`;
    }

    get quarterKpis() {
        return this.state.data.quarter_kpis || [];
    }

    get regionShares() {
        return this.state.data.by_region || [];
    }

    get providers() {
        return this.state.data.providers || [];
    }

    get regions() {
        return this.state.data.regions || [];
    }

    get filteredRows() {
        const q = (this.state.search || "").trim().toLowerCase();
        return (this.state.data.rows || []).filter((row) => {
            if (this.state.tableRegion !== "all" && row.region !== this.state.tableRegion) {
                return false;
            }
            if (this.state.tableProvider && String(row.provider_id) !== String(this.state.tableProvider)) {
                return false;
            }
            if (this.state.tablePay !== "all" && row.pay_status !== this.state.tablePay) {
                return false;
            }
            const days = Number(row.remaining_days || 0);
            const alert = row.alert_level || "";
            if (this.state.tableStatus === "active" && (days < 0 || alert === "expired" || alert === "danger")) {
                return false;
            }
            if (this.state.tableStatus === "expire_soon" && !(days >= 0 && days <= 30 || alert === "warn")) {
                return false;
            }
            if (this.state.tableStatus === "expired" && !(days < 0 || alert === "expired" || alert === "danger")) {
                return false;
            }
            if (!q) {
                return true;
            }
            return `${row.store} ${row.code} ${row.customer_code || ""} ${row.contract_code || ""} ${row.region || ""} ${row.provider || ""}`.toLowerCase().includes(q);
        });
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.filteredRows.length / this.state.pageSize));
    }

    get pageRows() {
        const start = (this.state.page - 1) * this.state.pageSize;
        return this.filteredRows.slice(start, start + this.state.pageSize).map((row, idx) => ({
            ...row,
            stt: start + idx + 1,
        }));
    }

    get pageInfo() {
        const total = this.filteredRows.length;
        if (!total) {
            return "Hiển thị 0 trên 0 bản ghi";
        }
        const start = (this.state.page - 1) * this.state.pageSize + 1;
        const end = Math.min(this.state.page * this.state.pageSize, total);
        return `Hiển thị ${start} - ${end} trên ${total} bản ghi`;
    }

    get pageNumbers() {
        const max = Math.min(this.totalPages, 8);
        return Array.from({ length: max }, (_, i) => i + 1);
    }

    payMeta(row) {
        return PAY_META[row.pay_status] || PAY_META.none;
    }

    payClass(row) {
        return "lq-mc-pay " + this.payMeta(row).className;
    }

    payLabel(row) {
        return this.payMeta(row).label;
    }

    customerCodeLabel(row) {
        const code = String(row.customer_code || "").trim();
        return code || "—";
    }

    providerMark(row) {
        const name = String(row.provider || "").toUpperCase();
        if (name.includes("FPT")) {
            return "F";
        }
        if (name.includes("VNPT")) {
            return "V";
        }
        if (name.includes("VIETTEL")) {
            return "VT";
        }
        return name[0] || "•";
    }

    providerClass(row) {
        const name = String(row.provider || "").toUpperCase();
        if (name.includes("FPT")) {
            return "is-fpt";
        }
        if (name.includes("VNPT")) {
            return "is-vnpt";
        }
        if (name.includes("VIETTEL")) {
            return "is-viettel";
        }
        return "";
    }

    opsStatusCode(row) {
        return row.ops_status || "active";
    }

    opsStatusLabel(row) {
        const code = this.opsStatusCode(row);
        return (OPS_STATUS_META[code] || OPS_STATUS_META.active).label;
    }

    opsPillClass(row) {
        const code = this.opsStatusCode(row);
        return `lq-ops-pill is-${code === "suspend" ? "suspend" : code === "liquidated" ? "liquidated" : "active"}`;
    }

    remainLabel(row) {
        if (row.remaining_time) {
            return row.remaining_time;
        }
        const days = Number(row.remaining_days);
        if (!Number.isFinite(days)) {
            return "—";
        }
        if (days < 0) {
            return `Quá hạn ${Math.abs(days)} ngày`;
        }
        return `Còn ${days} ngày`;
    }

    remainIcon(row) {
        const days = Number(row.remaining_days || 0);
        if (days < 0 || row.alert_level === "expired" || row.alert_level === "danger") {
            return "fa fa-exclamation-circle";
        }
        if (days <= 30 || row.alert_level === "warn") {
            return "fa fa-clock-o";
        }
        return "fa fa-calendar";
    }

    remainTone(row) {
        const days = Number(row.remaining_days);
        if (days < 0 || row.alert_level === "expired" || row.alert_level === "danger") {
            return "danger";
        }
        if (days <= 30 || row.alert_level === "warn") {
            return "warning";
        }
        return "active";
    }

    formatMoney(v) {
        return formatMoneyVn(v);
    }

    formatDate(v) {
        return formatDateVn(v);
    }

    kpiCardClass(item) {
        const active = item.quarter === this.state.quarter ? " is-active" : "";
        return `lq-q-kpi is-q${item.quarter}${active}`;
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("phan.he.dashboard", "get_quarter_cost_board", [{
                year: this.state.year,
                quarter: this.state.quarter,
                region: this.state.region,
                provider_id: this.state.providerId || false,
                pay_status: this.state.payStatus,
            }]);
            this.state.page = 1;
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không tải được chi phí quý.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    shiftQuarter(delta) {
        let q = this.state.quarter + delta;
        let y = this.state.year;
        if (q < 1) {
            q = 4;
            y -= 1;
        } else if (q > 4) {
            q = 1;
            y += 1;
        }
        this.state.quarter = q;
        this.state.year = y;
        this.load();
    }

    selectQuarter(q) {
        this.state.quarter = q;
        this.load();
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        this.load();
    }

    onTableFilter(field, ev) {
        this.state[field] = ev.target.value;
        this.state.page = 1;
    }

    setPage(page) {
        this.state.page = Math.min(Math.max(1, page), this.totalPages);
    }

    openRow(row) {
        if (this.props.onOpenEntry) {
            this.props.onOpenEntry(row.id);
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

    exportCsv() {
        this.exportExcel();
    }

    _downloadBase64Excel(b64, filename) {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
            bytes[i] = bin.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Chi_phi_quy.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async exportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const result = await this.orm.call("phan.he.dashboard", "export_quarter_cost_excel", [{
                year: this.state.year,
                quarter: this.state.quarter,
                region: this.state.region,
                provider_id: this.state.providerId || false,
                pay_status: this.state.payStatus,
                search: this.state.search,
                table_region: this.state.tableRegion,
                table_provider: this.state.tableProvider,
                table_status: this.state.tableStatus,
            }]);
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add("Đã xuất file Excel chi phí quý.", { type: "success" });
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không xuất được Excel.", {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }

    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            try {
                this.charts[key].destroy();
            } catch {
                /* ignore */
            }
            delete this.charts[key];
        }
    }

    renderCharts() {
        this.destroyCharts();
        if (this.state.loading || typeof Chart === "undefined") {
            return;
        }
        const months = this.state.data.monthly_trend || [];
        const lineEl = this.lineRef.el;
        if (lineEl) {
            this.charts.line = new Chart(lineEl, {
                type: "line",
                data: {
                    labels: months.map((m) => m.label),
                    datasets: [{
                        data: months.map((m) => Number(m.value || 0) / 1e6),
                        borderColor: "#6d4ee8",
                        backgroundColor: "rgba(109, 78, 232, 0.18)",
                        fill: true,
                        tension: 0.35,
                        pointRadius: 5,
                        pointBackgroundColor: "#6d4ee8",
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#64748b" } },
                        y: {
                            beginAtZero: true,
                            ticks: { color: "#94a3b8", callback: (v) => (v ? `${v} tr` : "0") },
                            grid: { color: "rgba(148,163,184,0.25)" },
                        },
                    },
                },
            });
        }
        const bars = this.state.data.by_provider || [];
        const barEl = this.barRef.el;
        if (barEl) {
            this.charts.bar = new Chart(barEl, {
                type: "bar",
                data: {
                    labels: bars.map((b) => b.label),
                    datasets: [{
                        data: bars.map((b) => Number(b.value || 0) / 1e6),
                        backgroundColor: bars.map((b) => b.color),
                        borderRadius: 8,
                        maxBarThickness: 52,
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: "#64748b" } },
                        y: {
                            beginAtZero: true,
                            ticks: { color: "#94a3b8", callback: (v) => (v ? `${v} tr` : "0") },
                            grid: { color: "rgba(148,163,184,0.2)" },
                        },
                    },
                },
            });
        }
        const donut = this.state.data.by_region || [];
        const donutEl = this.donutRef.el;
        const total = this.kpi.total_amount || 0;
        if (donutEl) {
            this.charts.donut = new Chart(donutEl, {
                type: "doughnut",
                data: {
                    labels: donut.map((d) => d.label),
                    datasets: [{
                        data: donut.map((d) => d.value),
                        backgroundColor: donut.map((d) => d.color),
                        borderWidth: 0,
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    cutout: "64%",
                    plugins: { legend: { display: false } },
                },
                plugins: [{
                    id: "lqQDonutCenter",
                    afterDraw(chart) {
                        const { ctx, chartArea } = chart;
                        if (!chartArea) {
                            return;
                        }
                        const x = (chartArea.left + chartArea.right) / 2;
                        const y = (chartArea.top + chartArea.bottom) / 2;
                        ctx.save();
                        ctx.textAlign = "center";
                        ctx.fillStyle = "#0f172a";
                        ctx.font = "700 12px Segoe UI, sans-serif";
                        ctx.fillText(formatMoneyVn(total), x, y - 2);
                        ctx.fillStyle = "#94a3b8";
                        ctx.font = "600 10px Segoe UI, sans-serif";
                        ctx.fillText("Tổng chi phí", x, y + 14);
                        ctx.restore();
                    },
                }],
            });
        }
    }
}
