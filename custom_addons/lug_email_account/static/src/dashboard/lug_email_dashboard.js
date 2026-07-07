/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CHART_COLORS = [
    "#ef4444", "#3b82f6", "#22c55e", "#f97316", "#eab308",
    "#a855f7", "#06b6d4", "#ec4899", "#64748b", "#14b8a6",
];

const STATUS_COLORS = {
    "Đang sử dụng": "#22c55e",
    "Tạm khóa": "#f59e0b",
    "Hủy": "#ef4444",
};

const KPI_STATUS_CHARTS = [
    { key: "active", ref: "activeChartRef", chartKey: "active", label: "Đang hoạt động", color: "#22c55e" },
    { key: "cancel", ref: "cancelChartRef", chartKey: "cancel", label: "Đang hủy", color: "#ef4444" },
    { key: "lock", ref: "lockChartRef", chartKey: "lock", label: "Tạm dừng", color: "#f59e0b" },
];

export class LugEmailDashboard extends Component {
    static template = "lug_email_account.LugEmailDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.departmentChartRef = useRef("departmentChart");
        this.statusChartRef = useRef("statusChart");
        this.monthChartRef = useRef("monthChart");
        this.activeChartRef = useRef("activeChart");
        this.cancelChartRef = useRef("cancelChart");
        this.lockChartRef = useRef("lockChart");
        this.charts = {
            department: null,
            status: null,
            month: null,
            active: null,
            cancel: null,
            lock: null,
        };
        this.state = useState({
            loading: true,
            data: null,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadDashboard();
        });

        useEffect(() => {
            if (!this.state.loading && this.state.data) {
                this.renderCharts();
            }
            return () => this.destroyCharts();
        });
    }

    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            if (this.charts[key]) {
                this.charts[key].destroy();
                this.charts[key] = null;
            }
        }
    }

    async loadDashboard() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "lug.email.dashboard",
                "get_dashboard_data",
                []
            );
        } finally {
            this.state.loading = false;
        }
    }

    _colorsForLabels(labels, palette = CHART_COLORS) {
        return labels.map((label, index) => STATUS_COLORS[label] || palette[index % palette.length]);
    }

    _legendLabel(row) {
        return `${row.label} (${row.count} - ${row.percent || 0}%)`;
    }

    renderDoughnutChart(refName, chartKey, rows, title, { withCounts = false } = {}) {
        const canvas = this[refName].el;
        if (!canvas || !window.Chart) {
            return;
        }
        if (this.charts[chartKey]) {
            this.charts[chartKey].destroy();
        }
        const labels = withCounts
            ? rows.map((row) => this._legendLabel(row))
            : rows.map((row) => row.label);
        const data = rows.map((row) => row.count);
        this.charts[chartKey] = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels,
                datasets: [
                    {
                        label: title,
                        data,
                        backgroundColor: this._colorsForLabels(rows.map((row) => row.label)),
                        borderWidth: 1,
                        borderColor: "#fff",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const row = rows[context.dataIndex];
                                return `${row.label}: ${row.count} (${row.percent || 0}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    renderStatusKpiChart(card) {
        const canvas = this[card.ref].el;
        if (!canvas || !window.Chart) {
            return;
        }
        if (this.charts[card.chartKey]) {
            this.charts[card.chartKey].destroy();
        }
        const total = this.state.data?.kpi?.total || 0;
        const value = this.state.data?.kpi?.[card.key] || 0;
        const rest = Math.max(total - value, 0);
        this.charts[card.chartKey] = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: [card.label, "Khác"],
                datasets: [
                    {
                        data: [value, rest],
                        backgroundColor: [card.color, "#e5e7eb"],
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "72%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                if (context.dataIndex !== 0) {
                                    return null;
                                }
                                return `${card.label}: ${value}`;
                            },
                        },
                    },
                },
            },
        });
    }

    renderMonthChart() {
        const canvas = this.monthChartRef.el;
        if (!canvas || !window.Chart) {
            return;
        }
        if (this.charts.month) {
            this.charts.month.destroy();
        }
        const series = this.state.data?.by_month || { labels: [], counts: [] };
        this.charts.month = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: series.labels,
                datasets: [
                    {
                        label: "Số email tạo mới",
                        data: series.counts,
                        backgroundColor: "#714b67",
                        borderRadius: 6,
                        maxBarThickness: 42,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { precision: 0 },
                    },
                },
            },
        });
    }

    renderCharts() {
        const data = this.state.data || {};
        this.renderDoughnutChart(
            "departmentChartRef",
            "department",
            data.by_department || [],
            "Email theo phòng ban",
            { withCounts: true }
        );
        this.renderDoughnutChart(
            "statusChartRef",
            "status",
            data.by_status || [],
            "Trạng thái email",
            { withCounts: true }
        );
        for (const card of KPI_STATUS_CHARTS) {
            this.renderStatusKpiChart(card);
        }
        this.renderMonthChart();
    }

    async openEmail(recordId) {
        if (!recordId) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "lug.email.account",
            res_id: recordId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAllEmails() {
        await this.actionService.doAction("lug_email_account.action_lug_email_list_all");
    }
}

registry.category("actions").add("lug_email_dashboard", LugEmailDashboard);
