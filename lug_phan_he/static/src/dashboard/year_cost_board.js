/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";

function pad2(n) {
    return String(n).padStart(2, "0");
}

function formatMoney(value) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(value || 0)))} đ`;
}

function formatPct(value) {
    const n = Number(value || 0);
    const s = String(Math.abs(n).toFixed(1)).replace(/\.0$/, "").replace(".", ",");
    return s;
}

export class PhanHeYearCostBoard extends Component {
    static template = "lug_phan_he.PhanHeYearCostBoard";
    static props = {
        serviceTypeCode: { type: String, optional: true },
        onOpenEntry: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            exporting: false,
            year: now.getFullYear(),
            region: "all",
            providerId: "",
            search: "",
            page: 1,
            pageSize: 8,
            data: {},
        });
        this.compareRef = useRef("yearCompare");
        this.structureRef = useRef("yearStructure");
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

    get isServer() {
        return (this.props.serviceTypeCode || "internet") === "server";
    }

    get entityLabel() {
        return this.state.data.entity_label || (this.isServer ? "thiết bị" : "hợp đồng");
    }

    get entityColumn() {
        return this.isServer ? "Thiết bị / Mã" : "Khách hàng / Mã hợp đồng";
    }

    get subtitle() {
        return (
            this.state.data.subtitle
            || (this.isServer
                ? "Phân tích và so sánh chi phí máy chủ, thiết bị theo năm"
                : "Phân tích và so sánh chi phí hợp đồng Internet theo năm")
        );
    }

    get kpi() {
        return this.state.data.kpi || {};
    }

    get prevYear() {
        return this.state.data.prev_year || this.state.year - 1;
    }

    get yearOptions() {
        const y = new Date().getFullYear();
        const opts = [];
        for (let i = y - 3; i <= y + 1; i++) {
            opts.push(i);
        }
        if (!opts.includes(this.state.year)) {
            opts.push(this.state.year);
            opts.sort((a, b) => a - b);
        }
        return opts;
    }

    get providers() {
        return this.state.data.providers || [];
    }

    get regions() {
        return this.state.data.regions || [];
    }

    get monthChange() {
        return this.state.data.month_change || [];
    }

    get monthChangeLeft() {
        return this.monthChange.slice(0, 6);
    }

    get monthChangeRight() {
        return this.monthChange.slice(6, 12);
    }

    get byProvider() {
        return this.state.data.by_provider || [];
    }

    get byStructure() {
        return this.state.data.by_structure || [];
    }

    get filteredRows() {
        const q = (this.state.search || "").trim().toLowerCase();
        return (this.state.data.rows || []).filter((row) => {
            if (!q) {
                return true;
            }
            const blob = `${row.name || ""} ${row.code || ""} ${row.provider || ""}`.toLowerCase();
            return blob.includes(q);
        });
    }

    get pageRows() {
        const start = (this.state.page - 1) * this.state.pageSize;
        return this.filteredRows.slice(start, start + this.state.pageSize).map((row, idx) => ({
            ...row,
            stt: start + idx + 1,
        }));
    }

    get pageInfo() {
        const n = this.filteredRows.length;
        if (!n) {
            return `Hiển thị 0 trong 0 ${this.entityLabel}`;
        }
        const from = (this.state.page - 1) * this.state.pageSize + 1;
        const to = Math.min(this.state.page * this.state.pageSize, n);
        return `Hiển thị ${from} - ${to} trong ${n} ${this.entityLabel}`;
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.filteredRows.length / this.state.pageSize));
    }

    maxAbsChange() {
        const vals = this.monthChange.map((r) => Math.abs(Number(r.delta_pct || 0)));
        return Math.max(...vals, 1);
    }

    changeBarWidth(row) {
        const max = this.maxAbsChange();
        return Math.min(100, Math.round((Math.abs(Number(row.delta_pct || 0)) / max) * 100));
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("phan.he.dashboard", "get_year_cost_board", [{
                year: this.state.year,
                region: this.state.region,
                provider_id: this.state.providerId || false,
                service_type_code: this.props.serviceTypeCode || "internet",
            }]);
            this.state.data = data || {};
            if (data?.year) {
                this.state.year = data.year;
            }
            this.state.page = 1;
        } catch (error) {
            console.error(error);
            this.state.data = {};
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được chi phí năm.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onYearChange(ev) {
        this.state.year = Number(ev.target.value) || new Date().getFullYear();
        await this.load();
    }

    async onRegionChange(ev) {
        this.state.region = ev.target.value || "all";
        await this.load();
    }

    async onProviderChange(ev) {
        this.state.providerId = ev.target.value || "";
        await this.load();
    }

    onSearch(ev) {
        this.state.search = ev.target.value || "";
        this.state.page = 1;
    }

    prevPage() {
        if (this.state.page > 1) {
            this.state.page -= 1;
        }
    }

    nextPage() {
        if (this.state.page < this.pageCount) {
            this.state.page += 1;
        }
    }

    openRow(row) {
        if (row?.id && this.props.onOpenEntry) {
            this.props.onOpenEntry(row.id);
        }
    }

    exportCsv() {
        const year = this.state.year;
        const prev = this.prevYear;
        const header = [
            "STT",
            this.isServer ? "Thiết bị / Mã" : "Khách hàng / Mã hợp đồng",
            "Nhà cung cấp",
            `Chi phí ${year}`,
            `Chi phí ${prev}`,
            "Chênh lệch",
            "Tỷ lệ thay đổi (%)",
        ];
        const lines = [header.join(",")];
        this.filteredRows.forEach((r, idx) => {
            lines.push([
                idx + 1,
                `"${String(r.name || "").replace(/"/g, '""')} (${String(r.code || "").replace(/"/g, '""')})"`,
                `"${String(r.provider || "").replace(/"/g, '""')}"`,
                r.amount || 0,
                r.prev_amount || 0,
                r.delta || 0,
                r.delta_pct || 0,
            ].join(","));
        });
        const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Chi_phi_nam_${year}.csv`;
        a.click();
        URL.revokeObjectURL(url);
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
    }

    renderCharts() {
        this.destroyCharts();
        if (this.state.loading || typeof Chart === "undefined") {
            return;
        }
        const series = this.state.data.month_compare || [];
        const year = this.state.year;
        const prev = this.prevYear;
        const compareEl = this.compareRef.el;
        if (compareEl) {
            const currentVals = series.map((p) => {
                const v = Number(p.current || 0);
                return v > 0 ? v : null;
            });
            const prevVals = series.map((p) => {
                const v = Number(p.prev || 0);
                return v > 0 ? v : null;
            });
            const formatBarTop = (n) => {
                const v = Number(n || 0);
                if (v <= 0) {
                    return "";
                }
                if (v >= 1e6) {
                    const tr = v / 1e6;
                    const text = tr >= 10 ? tr.toFixed(1) : tr.toFixed(2);
                    return `${text.replace(".", ",")} Tr`;
                }
                if (v >= 1e3) {
                    return `${new Intl.NumberFormat("vi-VN").format(Math.round(v / 1000))} N`;
                }
                return new Intl.NumberFormat("vi-VN").format(Math.round(v));
            };
            // Điểm tròn của đường xu hướng năm hiện tại → căn giữa cột bar năm hiện tại.
            const alignTrendToBar = (chart) => {
                const barMeta = chart.getDatasetMeta(0);
                const lineMeta = chart.getDatasetMeta(2);
                if (!barMeta?.data?.length || !lineMeta?.data?.length) {
                    return;
                }
                lineMeta.data.forEach((pt, i) => {
                    const bar = barMeta.data[i];
                    if (pt && bar && currentVals[i] != null && Number.isFinite(bar.x)) {
                        pt.x = bar.x;
                        if (Number.isFinite(bar.y)) {
                            pt.y = bar.y;
                        }
                    }
                });
            };
            const alignAndLabelPlugin = {
                id: "yearCompareAlignLabels",
                beforeDatasetsDraw(chart) {
                    alignTrendToBar(chart);
                },
                afterDatasetsDraw(chart) {
                    alignTrendToBar(chart);
                    const { ctx } = chart;
                    const barMeta = chart.getDatasetMeta(0);
                    const lineMeta = chart.getDatasetMeta(2);
                    if (!barMeta?.data?.length || barMeta.hidden) {
                        return;
                    }
                    ctx.save();
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillStyle = "#334155";
                    ctx.font = "700 11px system-ui, -apple-system, Segoe UI, sans-serif";
                    barMeta.data.forEach((bar, i) => {
                        const value = Number(currentVals[i] || 0);
                        if (!bar || value <= 0) {
                            return;
                        }
                        const label = formatBarTop(value);
                        if (!label) {
                            return;
                        }
                        const anchor = lineMeta?.data?.[i];
                        const x = anchor && Number.isFinite(anchor.x) ? anchor.x : bar.x;
                        const y = anchor && Number.isFinite(anchor.y) ? anchor.y : bar.y;
                        ctx.fillText(label, x, y - 10);
                    });
                    ctx.restore();
                },
            };
            this.charts.compare = new Chart(compareEl.getContext("2d"), {
                type: "bar",
                data: {
                    labels: series.map((p) => p.label),
                    datasets: [
                        {
                            type: "bar",
                            label: String(year),
                            data: currentVals,
                            backgroundColor: "#6366f1",
                            borderRadius: 4,
                            barPercentage: 0.5,
                            categoryPercentage: 0.65,
                            skipNull: true,
                            order: 3,
                        },
                        {
                            type: "bar",
                            label: String(prev),
                            data: prevVals,
                            backgroundColor: "#93c5fd",
                            borderRadius: 4,
                            barPercentage: 0.5,
                            categoryPercentage: 0.65,
                            skipNull: true,
                            order: 4,
                        },
                        {
                            type: "line",
                            label: `Xu hướng ${year}`,
                            data: currentVals,
                            borderColor: "#22c55e",
                            backgroundColor: "#22c55e",
                            borderWidth: 2,
                            pointRadius: (ctx) => (currentVals[ctx.dataIndex] != null ? 5 : 0),
                            pointHoverRadius: 6,
                            pointBackgroundColor: "#fff",
                            pointBorderColor: "#22c55e",
                            pointBorderWidth: 2,
                            tension: 0.25,
                            yAxisID: "y",
                            order: 1,
                            spanGaps: true,
                        },
                        {
                            type: "line",
                            label: "% thay đổi",
                            data: series.map((p) => Number(p.delta_pct || 0)),
                            borderColor: "rgba(34,197,94,0.35)",
                            backgroundColor: "rgba(34,197,94,0.35)",
                            borderWidth: 1.5,
                            borderDash: [4, 4],
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.25,
                            yAxisID: "y1",
                            order: 2,
                        },
                    ],
                },
                plugins: [alignAndLabelPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: { padding: { top: 28, right: 4, bottom: 0, left: 0 } },
                    interaction: { mode: "index", intersect: false },
                    plugins: {
                        legend: {
                            position: "top",
                            align: "end",
                            labels: { boxWidth: 10, usePointStyle: true, font: { size: 11 } },
                        },
                        tooltip: {
                            callbacks: {
                                title: (items) => {
                                    const mo = series[items[0]?.dataIndex]?.month;
                                    return `T${mo}/${year}`;
                                },
                                label: (ctx) => {
                                    if (ctx.dataset.yAxisID === "y1") {
                                        const sign = ctx.raw > 0 ? "+" : "";
                                        return ` ${ctx.dataset.label}: ${sign}${formatPct(ctx.raw)}%`;
                                    }
                                    return ` ${ctx.dataset.label}: ${formatMoney(ctx.raw)}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            offset: true,
                            grid: { display: false },
                            ticks: { color: "#94a3b8", font: { size: 11 } },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: "#94a3b8",
                                callback: (v) => new Intl.NumberFormat("vi-VN", {
                                    notation: "compact",
                                    compactDisplay: "short",
                                }).format(v),
                            },
                            grid: { color: "rgba(148,163,184,0.18)" },
                            border: { display: false },
                        },
                        y1: {
                            position: "right",
                            beginAtZero: false,
                            grid: { drawOnChartArea: false },
                            ticks: {
                                color: "#86efac",
                                callback: (v) => `${v}%`,
                            },
                            border: { display: false },
                        },
                    },
                },
            });
        }

        const slices = this.byStructure;
        const structEl = this.structureRef.el;
        if (structEl && slices.length) {
            const total = Number(this.kpi.year_total || 0);
            const centerPlugin = {
                id: "yearStructureCenter",
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
                    ctx.font = "700 15px Inter, system-ui, sans-serif";
                    ctx.fillText(new Intl.NumberFormat("vi-VN").format(Math.round(total)), x, y - 6);
                    ctx.fillStyle = "#94a3b8";
                    ctx.font = "600 10px Inter, system-ui, sans-serif";
                    ctx.fillText("đ", x, y + 12);
                    ctx.restore();
                },
            };
            this.charts.structure = new Chart(structEl.getContext("2d"), {
                type: "doughnut",
                data: {
                    labels: slices.map((s) => s.label),
                    datasets: [{
                        data: slices.map((s) => Number(s.amount || 0)),
                        backgroundColor: slices.map((s) => s.color),
                        borderWidth: 0,
                        hoverOffset: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "72%",
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (c) => {
                                    const s = slices[c.dataIndex];
                                    return ` ${s.label}: ${formatMoney(s.amount)} (${formatPct(s.pct)}%)`;
                                },
                            },
                        },
                    },
                },
                plugins: [centerPlugin],
            });
        }
    }

    formatMoney(v) {
        return formatMoney(v);
    }

    formatPct(v) {
        return formatPct(v);
    }

    deltaText(v) {
        const n = Number(v || 0);
        const sign = n > 0 ? "+" : n < 0 ? "−" : "";
        return `${sign}${formatPct(Math.abs(n))}%`;
    }

    moneyDeltaText(v) {
        const n = Number(v || 0);
        if (n < 0) {
            return `Giảm ${formatMoney(Math.abs(n))}`;
        }
        if (n > 0) {
            return `Tăng ${formatMoney(n)}`;
        }
        return "Không đổi";
    }

    avgHint() {
        const n = Number(this.kpi.avg_month_delta_pct || 0);
        if (n < 0) {
            return `Thấp hơn ${formatPct(Math.abs(n))}% so với năm ${this.prevYear}`;
        }
        if (n > 0) {
            return `Cao hơn ${formatPct(n)}% so với năm ${this.prevYear}`;
        }
        return `Bằng năm ${this.prevYear}`;
    }

    pad2(n) {
        return pad2(n);
    }

    deltaMoneyText(v) {
        const n = Number(v || 0);
        const body = new Intl.NumberFormat("vi-VN").format(Math.round(Math.abs(n)));
        if (n > 0) {
            return `+${body} đ`;
        }
        if (n < 0) {
            return `−${body} đ`;
        }
        return `${body} đ`;
    }

    pillClass(v) {
        const n = Number(v || 0);
        if (n < 0) {
            return "is-down";
        }
        if (n > 0) {
            return "is-up";
        }
        return "";
    }

    isProviderSelected(id) {
        return String(this.state.providerId || "") === String(id || "");
    }
}
