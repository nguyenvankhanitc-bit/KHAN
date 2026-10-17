/** @odoo-module **/

/**
 * Nhóm BÁO CÁO trên thanh bên + thanh tab đầu trang báo cáo.
 * nav: khóa openNav / activeNav · perm: nhóm Phân quyền báo cáo · need: cờ state bắt buộc.
 */
export const REPORT_GROUPS = [
    {
        key: "personal",
        title: "Báo cáo cá nhân",
        heading: "BÁO CÁO CÁ NHÂN",
        icon: "fa-user-o",
        items: [
            { nav: "overview", label: "Báo cáo cá nhân", icon: "fa-user-o", perm: "personal" },
            { nav: "monthly_report", label: "Báo cáo công việc tháng", icon: "fa-calendar", perm: "monthly" },
        ],
    },
    {
        key: "team",
        title: "Báo cáo team",
        heading: "BÁO CÁO TEAM",
        icon: "fa-users",
        items: [
            { nav: "team_report", label: "Báo cáo CV chi tiết team", icon: "fa-users", perm: "team" },
            { nav: "report", label: "Báo cáo tổng", icon: "fa-bar-chart", perm: "summary_report", need: "canViewOthers" },
            { nav: "performance", label: "Báo cáo hiệu suất", icon: "fa-line-chart", perm: "performance", need: "canSeePerformance" },
            { nav: "kpi", label: "Báo cáo KPI", icon: "fa-trophy", perm: "kpi", need: "isManager" },
        ],
    },
    {
        key: "other",
        title: "Báo cáo khác",
        heading: "BÁO CÁO KHÁC",
        icon: "fa-file-text-o",
        items: [
            { nav: "category_report", label: "Báo cáo CV theo hạng mục", icon: "fa-sitemap", perm: "catrep" },
            { nav: "user_summary", label: "Báo cáo tổng hợp theo hạng mục", icon: "fa-id-card-o", perm: "summary" },
        ],
    },
];

const REPORT_OPEN_KEY = "daily_work_sidebar_report_open";

/** Mục BÁO CÁO trên thanh bên đang mở (nhớ theo trình duyệt). */
export function readReportOpen() {
    try {
        return window.localStorage.getItem(REPORT_OPEN_KEY) !== "0";
    } catch (_e) {
        return true;
    }
}

/** Gắn các hàm nhóm báo cáo vào component có state + rv() + openNav() (shell / dashboard). */
export const reportGroupsMixin = {
    reportItems(group) {
        const reportView = this.state.reportView || {};
        return group.items.filter(
            (it) => reportView[it.perm] !== false && (!it.need || this.state[it.need])
        );
    },
    get reportGroups() {
        return REPORT_GROUPS.filter((g) => this.reportItems(g).length);
    },
    reportGroupOf(nav) {
        return this.reportGroups.find((g) => g.items.some((it) => it.nav === nav)) || null;
    },
    toggleReportSection() {
        this.state.reportOpen = !this.state.reportOpen;
        try {
            window.localStorage.setItem(REPORT_OPEN_KEY, this.state.reportOpen ? "1" : "0");
        } catch (_e) {
            /* ignore */
        }
    },
    openReportGroup(group) {
        const first = this.reportItems(group)[0];
        if (first) {
            this.openNav(first.nav);
        }
    },
};

export function applyReportGroups(Cls) {
    for (const name of Object.getOwnPropertyNames(reportGroupsMixin)) {
        Object.defineProperty(
            Cls.prototype,
            name,
            Object.getOwnPropertyDescriptor(reportGroupsMixin, name)
        );
    }
}
