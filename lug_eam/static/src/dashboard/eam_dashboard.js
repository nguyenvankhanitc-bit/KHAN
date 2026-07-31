/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const PALETTE = [
    "#0f766e",
    "#0369a1",
    "#b45309",
    "#be123c",
    "#4d7c0f",
    "#6d28d9",
    "#0e7490",
    "#a16207",
];

function formatNumber(n) {
    const v = Number(n || 0);
    return new Intl.NumberFormat("vi-VN").format(v);
}

function formatMoney(n, symbol) {
    const v = Number(n || 0);
    return `${formatNumber(Math.round(v))} ${symbol || ""}`.trim();
}

export class EamDashboard extends Component {
    static template = "lug_eam.EamDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.stateChartRef = useRef("stateChart");
        this.costChartRef = useRef("costChart");
        this.siteChartRef = useRef("siteChart");
        this.deptChartRef = useRef("deptChart");
        this.ownerChartRef = useRef("ownerChart");
        this.charts = [];
        this.state = useState({
            loading: true,
            companyName: "",
            asOf: "",
            currencySymbol: "",
            kpi: {},
            charts: {},
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadDashboard();
        });

        useEffect(
            () => {
                if (!this.state.loading) {
                    this.renderCharts();
                }
                return () => this.destroyCharts();
            },
            () => [this.state.loading, this.state.charts]
        );
    }

    get kpiCards() {
        const k = this.state.kpi || {};
        const sym = this.state.currencySymbol;
        return [
            { key: "total", label: "Tổng tài sản", value: formatNumber(k.total) },
            { key: "in_use", label: "Đang sử dụng", value: formatNumber(k.in_use) },
            { key: "in_stock", label: "Trong kho", value: formatNumber(k.in_stock) },
            {
                key: "maintenance",
                label: "Bảo trì / Hỏng",
                value: formatNumber(k.maintenance),
                hint: k.broken ? `${formatNumber(k.broken)} hỏng` : "",
            },
            {
                key: "warranty_expired",
                label: "Hết bảo hành",
                value: formatNumber(k.warranty_expired),
                hint: k.warranty_expiring
                    ? `${formatNumber(k.warranty_expiring)} sắp hết`
                    : "",
            },
            {
                key: "cost_month",
                label: "Chi phí BT tháng này",
                value: formatMoney(k.cost_month, sym),
                hint: `YTD: ${formatMoney(k.cost_ytd, sym)}`,
            },
        ];
    }

    async loadDashboard() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("eam.dashboard", "get_dashboard_data", []);
            this.state.companyName = data.company_name || "";
            this.state.asOf = data.as_of || "";
            this.state.currencySymbol = data.currency_symbol || "";
            this.state.kpi = data.kpi || {};
            this.state.charts = data.charts || {};
        } finally {
            this.state.loading = false;
        }
    }

    async onRefresh() {
        await this.loadDashboard();
    }

    async openKpi(key) {
        const act = await this.orm.call("eam.dashboard", "action_open_kpi", [key]);
        if (act) {
            this.action.doAction(act);
        }
    }

    destroyCharts() {
        for (const c of this.charts) {
            try {
                c.destroy();
            } catch {
                /* ignore */
            }
        }
        this.charts = [];
    }

    _barOrEmpty(canvas, chartData, options = {}) {
        if (!canvas || !window.Chart) {
            return;
        }
        const labels = chartData?.labels || [];
        const values = chartData?.values || [];
        const horizontal = Boolean(options.horizontal);
        const chart = new window.Chart(canvas, {
            type: options.type || "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: options.datasetLabel || "",
                        data: values,
                        backgroundColor:
                            options.type === "doughnut"
                                ? labels.map((_, i) => PALETTE[i % PALETTE.length])
                                : options.color || PALETTE[0],
                        borderWidth: 0,
                        borderRadius: options.type === "doughnut" ? 0 : 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: horizontal ? "y" : "x",
                plugins: {
                    legend: {
                        display: options.type === "doughnut",
                        position: "bottom",
                    },
                },
                scales:
                    options.type === "doughnut"
                        ? {}
                        : {
                              x: { grid: { display: false } },
                              y: {
                                  beginAtZero: true,
                                  ticks: { precision: 0 },
                                  grid: { color: "rgba(15, 23, 42, 0.06)" },
                              },
                          },
            },
        });
        this.charts.push(chart);
    }

    renderCharts() {
        this.destroyCharts();
        const c = this.state.charts || {};
        this._barOrEmpty(this.stateChartRef.el, c.by_state, {
            type: "doughnut",
            datasetLabel: "Tài sản",
        });
        this._barOrEmpty(this.costChartRef.el, c.cost_by_month, {
            color: PALETTE[1],
            datasetLabel: "Chi phí",
        });
        this._barOrEmpty(this.siteChartRef.el, c.by_site, {
            horizontal: true,
            color: PALETTE[0],
        });
        this._barOrEmpty(this.deptChartRef.el, c.by_department, {
            horizontal: true,
            color: PALETTE[2],
        });
        this._barOrEmpty(this.ownerChartRef.el, c.by_owner, {
            horizontal: true,
            color: PALETTE[4],
        });
    }
}

registry.category("actions").add("eam_dashboard", EamDashboard);
