/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";

const PIE_COLORS = [
    "#2ecc71",
    "#f1c40f",
    "#e74c3c",
    "#95a5a6",
    "#3498db",
    "#9b59b6",
    "#e67e22",
    "#1abc9c",
    "#34495e",
    "#fd79a8",
];

const ASSET_COLORS = [
    "#2563eb",
    "#14b8a6",
    "#f59e0b",
    "#ef4444",
    "#0ea5e9",
    "#22c55e",
    "#f97316",
    "#6366f1",
];

const SLICE_FIELDS = {
    month: "Tên thiết bị",
    asset: "Tên thiết bị",
    estimate: "Tên thiết bị",
    schedule: "Tên thiết bị",
    quarter: "Tháng",
    year: "Tháng",
    provider: "Nhà cung cấp",
};

function formatMoney(value) {
    return new Intl.NumberFormat("vi-VN").format(Math.round(Number(value || 0)));
}

function pad2(n) {
    return String(n).padStart(2, "0");
}

export class PhanHeItCostReport extends Component {
    static template = "lug_phan_he.PhanHeItCostReport";
    static props = {
        reportKey: String,
        reloadToken: { type: Number, optional: true },
        onOpenCost: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pieRef = useRef("pie");
        this.barRef = useRef("bar");
        this.charts = {};
        const now = new Date();
        this.state = useState({
            loading: true,
            exporting: false,
            sliceField: "Tên thiết bị",
            title: "",
            subtitle: "",
            dimension: "",
            period: "",
            periodMode: "month",
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            quarter: Math.floor(now.getMonth() / 3) + 1,
            total: 0,
            prevTotal: 0,
            deltaPct: 0,
            prevLabel: "",
            assetCount: 0,
            topAssetName: "",
            topAssetAmount: 0,
            count: 0,
            slices: [],
            rows: [],
            search: "",
            page: 1,
            pageSize: 8,
        });
        onWillStart(async () => {
            await this.ensureChartLib();
            await this.load(this.props.reportKey);
        });
        onWillUpdateProps(async (next) => {
            if (next.reportKey !== this.props.reportKey || next.reloadToken !== this.props.reloadToken) {
                this.state.page = 1;
                this.state.search = "";
                await this.load(next.reportKey);
            }
        });
        useEffect(
            () => {
                this.renderCharts();
                return () => this.destroyCharts();
            },
            () => [
                this.state.loading,
                this.props.reportKey,
                this.state.slices.map((slice) => `${slice.label}:${slice.amount}`).join("|"),
            ]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    get isAssetReport() {
        return (
            this.props.reportKey === "asset"
            || this.props.reportKey === "estimate"
            || this.props.reportKey === "schedule"
        );
    }

    get filtersPayload() {
        return {
            period_mode: this.state.periodMode,
            year: this.state.year,
            month: this.state.month,
            quarter: this.state.quarter,
        };
    }

    get yearOptions() {
        const y = new Date().getFullYear();
        return [y - 2, y - 1, y, y + 1];
    }

    get monthOptions() {
        return Array.from({ length: 12 }, (_, i) => i + 1);
    }

    get filteredRows() {
        const q = String(this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.state.rows;
        }
        return this.state.rows.filter((row) => {
            const blob = [
                row.asset_name,
                row.provider,
                row.bandwidth,
                row.note,
                row.renewal_label,
                row.remaining_label,
            ]
                .join(" ")
                .toLowerCase();
            return blob.includes(q);
        });
    }

    get pageRows() {
        const start = (this.state.page - 1) * this.state.pageSize;
        return this.filteredRows.slice(start, start + this.state.pageSize);
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.filteredRows.length / this.state.pageSize));
    }

    get pagerPages() {
        const total = this.pageCount;
        const cur = this.state.page;
        const pages = [];
        for (let i = 1; i <= total; i++) {
            if (i === 1 || i === total || Math.abs(i - cur) <= 1) {
                pages.push(i);
            } else if (pages[pages.length - 1] !== "…") {
                pages.push("…");
            }
        }
        return pages;
    }

    get pageFrom() {
        if (!this.filteredRows.length) {
            return 0;
        }
        return (this.state.page - 1) * this.state.pageSize + 1;
    }

    get pageTo() {
        return Math.min(this.state.page * this.state.pageSize, this.filteredRows.length);
    }

    rowStt(index) {
        return (this.state.page - 1) * this.state.pageSize + Number(index || 0) + 1;
    }

    async ensureChartLib() {
        if (typeof Chart !== "undefined") {
            return;
        }
        try {
            await loadBundle("web.chartjs_lib");
        } catch (error) {
            console.warn("it cost chart", error);
        }
    }

    async load(reportKey) {
        const key = reportKey || this.props.reportKey;
        this.state.loading = true;
        this.destroyCharts();
        try {
            const args = key === "asset" || key === "estimate" || key === "schedule" || key === "provider"
                ? [key, this.filtersPayload]
                : [key];
            const data = await this.orm.call("phan.he.it.cost", "get_it_cost_pie_report", args);
            const palette = key === "asset" || key === "estimate" || key === "schedule"
                ? ASSET_COLORS
                : PIE_COLORS;
            this.state.title = data?.title || "";
            this.state.subtitle = data?.subtitle || data?.dimension || "";
            this.state.dimension = data?.dimension || "";
            this.state.period = data?.period || "";
            this.state.periodMode = data?.period_mode || this.state.periodMode;
            this.state.year = Number(data?.year || this.state.year);
            this.state.month = Number(data?.month || this.state.month);
            this.state.quarter = Number(data?.quarter || this.state.quarter);
            this.state.total = data?.total || 0;
            this.state.prevTotal = data?.prev_total || 0;
            this.state.deltaPct = data?.delta_pct || 0;
            this.state.prevLabel = data?.prev_label || "";
            this.state.assetCount = data?.asset_count || 0;
            this.state.topAssetName = data?.top_asset_name || "";
            this.state.topAssetAmount = data?.top_asset_amount || 0;
            this.state.count = data?.count || 0;
            this.state.sliceField = SLICE_FIELDS[key] || "Nội dung";
            this.state.slices = (data?.slices || []).map((slice, index) => ({
                ...slice,
                color: palette[index % palette.length],
            }));
            this.state.rows = data?.rows || [];
            this.state.page = 1;
        } catch (error) {
            console.error(error);
            this.state.slices = [];
            this.state.rows = [];
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được báo cáo.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    setPeriodMode(mode) {
        if (!["month", "quarter", "year"].includes(mode) || this.state.periodMode === mode) {
            return;
        }
        this.state.periodMode = mode;
        this.load(this.props.reportKey);
    }

    onYearChange(ev) {
        this.state.year = Number(ev.target.value) || new Date().getFullYear();
        this.load(this.props.reportKey);
    }

    onMonthChange(ev) {
        this.state.month = Number(ev.target.value) || 1;
        this.load(this.props.reportKey);
    }

    onQuarterChange(ev) {
        this.state.quarter = Number(ev.target.value) || 1;
        this.load(this.props.reportKey);
    }

    onSearch(ev) {
        this.state.search = ev.target.value || "";
        this.state.page = 1;
    }

    goPage(page) {
        if (page === "…" || page < 1 || page > this.pageCount) {
            return;
        }
        this.state.page = page;
    }

    destroyCharts() {
        Object.values(this.charts || {}).forEach((chart) => {
            try {
                chart.destroy();
            } catch (e) {
                /* ignore */
            }
        });
        this.charts = {};
        this.chart = null;
    }

    renderCharts() {
        this.destroyCharts();
        if (this.state.loading || typeof Chart === "undefined" || !this.state.slices.length) {
            return;
        }
        if (this.isAssetReport) {
            this.renderAssetBar();
            this.renderAssetDonut();
            return;
        }
        this.renderLegacyDonut();
    }

    renderAssetBar() {
        const el = this.barRef.el;
        if (!el) {
            return;
        }
        const slices = this.state.slices;
        this.charts.bar = new Chart(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: slices.map((s) => s.label),
                datasets: [
                    {
                        data: slices.map((s) => Number(s.amount || 0)),
                        backgroundColor: slices.map((s) => s.color),
                        borderRadius: 6,
                        borderSkipped: false,
                        barPercentage: 0.28,
                        categoryPercentage: 0.55,
                        maxBarThickness: 14,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                layout: { padding: { top: 4, bottom: 4 } },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const s = slices[ctx.dataIndex];
                                return ` ${formatMoney(s.amount)} đ (${s.percent}%)`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: "rgba(148,163,184,0.18)" },
                        ticks: {
                            color: "#94a3b8",
                            callback: (v) =>
                                new Intl.NumberFormat("vi-VN", {
                                    notation: "compact",
                                    compactDisplay: "short",
                                }).format(v),
                        },
                        border: { display: false },
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: "#475569", font: { weight: "600", size: 12 } },
                        border: { display: false },
                    },
                },
            },
        });
    }

    renderAssetDonut() {
        const canvas = this.pieRef.el;
        if (!canvas) {
            return;
        }
        const slices = this.state.slices;
        const total = Number(this.state.total || 0);
        const centerPlugin = {
            id: "itAssetDonutCenter",
            afterDraw: (chart) => {
                const meta = chart.getDatasetMeta(0);
                if (!meta?.data?.length) {
                    return;
                }
                const { x, y } = meta.data[0];
                const ctx = chart.ctx;
                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#0f172a";
                ctx.font = "700 18px system-ui, -apple-system, Segoe UI, sans-serif";
                ctx.fillText(formatMoney(total), x, y - 8);
                ctx.fillStyle = "#94a3b8";
                ctx.font = "600 11px system-ui, -apple-system, Segoe UI, sans-serif";
                ctx.fillText("Tổng chi phí", x, y + 12);
                ctx.restore();
            },
        };
        this.charts.pie = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: slices.map((s) => s.label),
                datasets: [
                    {
                        data: slices.map((s) => Number(s.amount || 0)),
                        backgroundColor: slices.map((s) => s.color),
                        borderWidth: 0,
                        hoverOffset: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "72%",
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => {
                                const s = slices[item.dataIndex];
                                return ` ${s.label}: ${formatMoney(s.amount)} đ (${s.percent}%)`;
                            },
                        },
                    },
                },
            },
            plugins: [centerPlugin],
        });
    }

    renderLegacyDonut() {
        const canvas = this.pieRef.el;
        if (!canvas) {
            return;
        }
        const slices = this.state.slices;
        const total = Number(this.state.total || 0);
        const centerPlugin = {
            id: "itCostDonutCenter",
            afterDraw: (chart) => {
                const meta = chart.getDatasetMeta(0);
                if (!meta?.data?.length) {
                    return;
                }
                const { x, y } = meta.data[0];
                const ctx = chart.ctx;
                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#1e293b";
                ctx.font = "700 28px Inter, system-ui, sans-serif";
                ctx.fillText(formatMoney(total), x, y - 10);
                ctx.fillStyle = "#94a3b8";
                ctx.font = "500 13px Inter, system-ui, sans-serif";
                ctx.fillText("Tổng chi phí", x, y + 16);
                ctx.restore();
            },
        };
        this.charts.pie = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: slices.map((slice) => slice.label),
                datasets: [
                    {
                        data: slices.map((slice) => Number(slice.amount || 0)),
                        backgroundColor: slices.map((slice) => slice.color),
                        borderColor: "#ffffff",
                        borderWidth: 4,
                        hoverOffset: 4,
                        spacing: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => {
                                const slice = slices[item.dataIndex];
                                return ` ${this.state.sliceField} - ${slice.label}: ${formatMoney(slice.amount)} đ (${slice.percent}%)`;
                            },
                        },
                    },
                },
            },
            plugins: [centerPlugin],
        });
        this.chart = this.charts.pie;
    }

    formatMoney(value) {
        return formatMoney(value);
    }

    formatPct(value) {
        const n = Number(value || 0);
        const s = String(Math.abs(n).toFixed(1)).replace(/\.0$/, "").replace(".", ",");
        return s;
    }

    deltaText() {
        const n = Number(this.state.deltaPct || 0);
        const arrow = n > 0 ? "↑" : n < 0 ? "↓" : "→";
        const sign = n > 0 ? "+" : n < 0 ? "−" : "";
        return `${arrow} ${sign}${this.formatPct(Math.abs(n))}% so với ${this.state.prevLabel || "kỳ trước"}`;
    }

    deltaClass() {
        const n = Number(this.state.deltaPct || 0);
        if (n > 0) {
            return "is-up";
        }
        if (n < 0) {
            return "is-down";
        }
        return "is-flat";
    }

    padCount(n) {
        return pad2(Number(n || 0));
    }

    monthLabel(m) {
        return `Tháng ${pad2(m)}/${this.state.year}`;
    }

    yearOptionLabel(y) {
        return this.state.periodMode === "year" ? `Năm ${y}` : String(y);
    }

    openRow(row) {
        if (row?.id && this.props.onOpenCost) {
            this.props.onOpenCost(row.id);
        }
    }

    async exportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const key = this.props.reportKey;
            const args = key === "asset" || key === "estimate" || key === "schedule" || key === "provider"
                ? [key, this.filtersPayload]
                : [key];
            const result = await this.orm.call("phan.he.it.cost", "export_it_cost_pie_excel", args);
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            const binary = atob(result.file_base64);
            const bytes = new Uint8Array(binary.length);
            for (let index = 0; index < binary.length; index++) {
                bytes[index] = binary.charCodeAt(index);
            }
            const blob = new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = result.filename || "Bao_cao_may_chu.xlsx";
            link.click();
            URL.revokeObjectURL(url);
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
}
