/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MIEN_COLORS = {
    Nam: "#2563eb",
    Bắc: "#dc2626",
    ĐTT: "#16a34a",
    VP: "#9333ea",
};

export class LeaveAnalyticsDashboard extends Component {
    static template = "hr_leave_analytics.LeaveAnalyticsDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.mienChartRef = useRef("mienPieChart");
        this.mienChart = null;
        const actionContext = this.props.action.context || {};
        this.fixedMien = actionContext.dashboard_mien || false;
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
                this.renderMienPieChart();
            }
            return () => {
                if (this.mienChart) {
                    this.mienChart.destroy();
                    this.mienChart = null;
                }
            };
        });
    }

    get filtersPayload() {
        return {
            employee_mien: this.fixedMien || false,
        };
    }

    get mienTotalDays() {
        if (!this.state.data?.mien_comparison) {
            return 0;
        }
        return this.state.data.mien_comparison.reduce((sum, item) => sum + (item.leave_days || 0), 0);
    }

    getMienColor(mien) {
        return MIEN_COLORS[mien] || "#6b7280";
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "hr.leave.analytics.dashboard",
            "get_dashboard_data",
            [],
            { filters: this.filtersPayload }
        );
        this.state.loading = false;
    }

    renderMienPieChart() {
        const canvas = this.mienChartRef.el;
        const items = this.state.data?.mien_comparison || [];
        if (!canvas || !items.length) {
            return;
        }
        if (this.mienChart) {
            this.mienChart.destroy();
            this.mienChart = null;
        }
        const labels = items.map((item) => item.label);
        const data = items.map((item) => item.leave_days || 0);
        const backgroundColor = items.map((item) => this.getMienColor(item.mien));
        const hasData = data.some((value) => value > 0);

        this.mienChart = new Chart(canvas, {
            type: "pie",
            data: {
                labels,
                datasets: [
                    {
                        data: hasData ? data : [1].slice(0, items.length),
                        backgroundColor: hasData
                            ? backgroundColor
                            : items.map(() => "#e9ecef"),
                        borderWidth: 2,
                        borderColor: "#ffffff",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: hasData,
                        callbacks: {
                            label: (context) => {
                                const value = items[context.dataIndex]?.leave_days || 0;
                                return `${context.label}: ${value} ngày`;
                            },
                        },
                    },
                },
            },
        });
    }

    async openList(exportType) {
        const action = await this.orm.call(
            "hr.leave.analytics.dashboard",
            "action_export_excel",
            [],
            { export_type: exportType, filters: this.filtersPayload }
        );
        this.actionService.doAction(action);
    }

    async drillDown(type, recordId) {
        const action = await this.orm.call(
            "hr.leave.analytics.dashboard",
            "action_drill_down",
            [],
            {
                drill_type: type,
                filters: this.filtersPayload,
                record_id: recordId || false,
            }
        );
        this.actionService.doAction(action);
    }
}

registry.category("actions").add("hr_leave_analytics_dashboard", LeaveAnalyticsDashboard);
