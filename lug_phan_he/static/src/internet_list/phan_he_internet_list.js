/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const PAGE_SIZE = 12;

const OPS_STATUS_META = {
    active: { label: "Đang hoạt động", className: "is-active" },
    suspend: { label: "Tạm ngưng", className: "is-suspend" },
    liquidated: { label: "Thanh lý", className: "is-liquidated" },
};

const INTERNET_NAV_SECTIONS = [
    {
        id: "declare",
        label: "Khai báo & nhập liệu",
        icon: "fa-download",
        children: [
            {
                id: "store_declare",
                label: "Khai báo cửa hàng",
                action: "lug_phan_he.action_phan_he_service_entry",
            },
        ],
    },
    {
        id: "manage",
        label: "Quản lý Internet",
        icon: "fa-sitemap",
        children: [
            {
                id: "list_all",
                label: "Danh sách Internet",
                icon: "fa-list-ul",
                action: "lug_phan_he.action_phan_he_internet_list",
            },
            {
                id: "list_active",
                label: "Internet đang sử dụng",
                icon: "fa-check-circle",
                action: "lug_phan_he.action_phan_he_internet_list_active",
            },
            {
                id: "list_suspend",
                label: "Internet tạm ngưng",
                icon: "fa-pause-circle",
                action: "lug_phan_he.action_phan_he_internet_list_suspend",
            },
            {
                id: "list_liquidated",
                label: "Internet chờ thanh lý",
                icon: "fa-times-circle",
                action: "lug_phan_he.action_phan_he_internet_list_liquidated",
            },
        ],
    },
    {
        id: "payment",
        label: "Chi phí & thanh toán",
        icon: "fa-money",
        children: [
            {
                id: "payment_schedule",
                label: "Lịch thanh toán",
                icon: "fa-calendar",
                action: "lug_phan_he.action_phan_he_payment",
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
                icon: "fa-exclamation-triangle",
                action: "lug_phan_he.action_phan_he_service_expire_soon",
            },
            {
                id: "expired",
                label: "Quá hạn",
                icon: "fa-times-circle",
                action: "lug_phan_he.action_phan_he_service_expired",
            },
        ],
    },
    {
        id: "reports",
        label: "Báo cáo",
        icon: "fa-bar-chart",
        children: [
            {
                id: "report_month",
                label: "Chi phí tháng",
                icon: "fa-calendar-o",
                reportPeriod: "month",
                action: "lug_phan_he.action_phan_he_dashboard",
            },
            {
                id: "report_quarter",
                label: "Chi phí quý",
                icon: "fa-calendar",
                reportPeriod: "quarter",
                action: "lug_phan_he.action_phan_he_dashboard",
            },
            {
                id: "report_year",
                label: "Chi phí năm",
                icon: "fa-calendar-check-o",
                reportPeriod: "year",
                action: "lug_phan_he.action_phan_he_dashboard",
            },
        ],
    },
];

function formatMoneyVn(amount) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(amount || 0)))} đ`;
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

const FILTER_TITLES = {
    all: {
        title: "Danh sách đường truyền Internet",
        subtitle: "Quản lý và theo dõi các đường truyền Internet trong hệ thống",
        activeNav: "list_all",
    },
    active: {
        title: "Internet đang sử dụng",
        subtitle: "Các đường truyền đang hoạt động",
        activeNav: "list_active",
    },
    suspend: {
        title: "Internet tạm ngưng",
        subtitle: "Các đường truyền đang tạm ngưng",
        activeNav: "list_suspend",
    },
    liquidated: {
        title: "Internet chờ thanh lý",
        subtitle: "Các đường truyền chờ thanh lý",
        activeNav: "list_liquidated",
    },
};

export class PhanHeInternetList extends Component {
    static template = "lug_phan_he.PhanHeInternetList";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            openGroups: {
                declare: true,
                manage: true,
                payment: true,
                alerts: true,
                reports: true,
            },
            activeNav: "list_all",
            records: [],
            selected: {},
            providers: [],
            bandwidths: [],
            stats: { total: 0, active: 0, suspend: 0, liquidated: 0 },
            page: 1,
            search: "",
            statusFilter: "",
            providerFilter: "",
            bandwidthFilter: "",
            openMenuId: null,
        });
        onWillStart(async () => {
            this.state.activeNav = this.pageMeta.activeNav;
            await this.load();
        });
    }

    get actionContext() {
        return this.props.action?.context || {};
    }

    get listFilter() {
        return this.actionContext.phan_he_list_filter || "all";
    }

    get pageMeta() {
        return FILTER_TITLES[this.listFilter] || FILTER_TITLES.all;
    }

    get navSections() {
        return INTERNET_NAV_SECTIONS;
    }

    get baseDomain() {
        const domain = [["service_type_id.code", "=", "internet"]];
        if (this.listFilter === "active") {
            domain.push(["ops_status", "=", "active"]);
        } else if (this.listFilter === "suspend") {
            domain.push(["ops_status", "=", "suspend"]);
        } else if (this.listFilter === "liquidated") {
            domain.push(["ops_status", "=", "liquidated"]);
        }
        return domain;
    }

    get filteredRecords() {
        const q = (this.state.search || "").trim().toLowerCase();
        return this.state.records.filter((rec) => {
            if (this.state.statusFilter && rec.ops_status !== this.state.statusFilter) {
                return false;
            }
            if (this.state.providerFilter) {
                const pid = Array.isArray(rec.provider_id) ? rec.provider_id[0] : rec.provider_id;
                if (String(pid) !== String(this.state.providerFilter)) {
                    return false;
                }
            }
            if (this.state.bandwidthFilter && (rec.bandwidth || "") !== this.state.bandwidthFilter) {
                return false;
            }
            if (!q) {
                return true;
            }
            const hay = [
                rec.name,
                rec.code,
                rec.customer_code,
                Array.isArray(rec.store_id) ? rec.store_id[1] : "",
                Array.isArray(rec.provider_id) ? rec.provider_id[1] : "",
            ]
                .join(" ")
                .toLowerCase();
            return hay.includes(q);
        });
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.filteredRecords.length / PAGE_SIZE));
    }

    get pageRecords() {
        const start = (this.state.page - 1) * PAGE_SIZE;
        return this.filteredRecords.slice(start, start + PAGE_SIZE).map((rec, idx) => ({
            ...rec,
            stt: start + idx + 1,
        }));
    }

    get pageInfo() {
        const total = this.filteredRecords.length;
        if (!total) {
            return "Hiển thị 0 bản ghi";
        }
        const start = (this.state.page - 1) * PAGE_SIZE + 1;
        const end = Math.min(this.state.page * PAGE_SIZE, total);
        return `Hiển thị ${start} đến ${end} trong tổng số ${total} bản ghi`;
    }

    get pageNumbers() {
        const pages = [];
        for (let i = 1; i <= this.totalPages; i++) {
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

    statusMeta(status) {
        return OPS_STATUS_META[status] || OPS_STATUS_META.active;
    }

    formatDate(value) {
        return formatDateVn(value);
    }

    formatMoney(value) {
        return formatMoneyVn(value);
    }

    storeName(rec) {
        return (Array.isArray(rec.store_id) && rec.store_id[1]) || rec.name || "—";
    }

    lineCode(rec) {
        return rec.customer_code || rec.code || `ID-${rec.id}`;
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

    async load() {
        this.state.loading = true;
        try {
            const domain = this.baseDomain;
            const [records, providers, allForStats] = await Promise.all([
                this.orm.searchRead(
                    "phan.he.service",
                    domain,
                    [
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
                        "remaining_days",
                        "remaining_time",
                        "alert_level",
                    ],
                    { order: "date_end desc, id desc", limit: 500 }
                ),
                this.orm.searchRead("phan.he.provider", [], ["name"], { order: "name asc" }),
                this.orm.searchRead(
                    "phan.he.service",
                    [["service_type_id.code", "=", "internet"]],
                    ["ops_status"],
                    { limit: 2000 }
                ),
            ]);
            this.state.records = records;
            this.state.providers = providers;
            const bandwidths = [...new Set(records.map((r) => r.bandwidth).filter(Boolean))];
            bandwidths.sort();
            this.state.bandwidths = bandwidths;
            const stats = { total: allForStats.length, active: 0, suspend: 0, liquidated: 0 };
            for (const r of allForStats) {
                if (r.ops_status === "active") {
                    stats.active += 1;
                } else if (r.ops_status === "suspend") {
                    stats.suspend += 1;
                } else if (r.ops_status === "liquidated") {
                    stats.liquidated += 1;
                }
            }
            this.state.stats = stats;
            this.state.page = 1;
            this.state.selected = {};
            this.state.openMenuId = null;
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được danh sách Internet.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.page = 1;
    }

    resetFilters() {
        this.state.search = "";
        this.state.statusFilter = "";
        this.state.providerFilter = "";
        this.state.bandwidthFilter = "";
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
        this.state.openMenuId = null;
    }

    toggleRowMenu(id, ev) {
        ev.stopPropagation();
        this.state.openMenuId = this.state.openMenuId === id ? null : id;
    }

    closeMenus() {
        this.state.openMenuId = null;
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
        if (child.action) {
            this.action.doAction(child.action);
        }
    }

    onAdd() {
        this.action.doAction("lug_phan_he.action_phan_he_service_entry");
    }

    openRecord(id) {
        this.state.openMenuId = null;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "phan.he.service",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("phan_he_internet_list", PhanHeInternetList, { force: true });
