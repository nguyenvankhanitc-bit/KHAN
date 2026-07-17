/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class DailyWorkPerformanceReport extends Component {
    static template = "daily_work_task.DailyWorkPerformanceReport";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.stateChartRef = useRef("stateChart");
        this.charts = [];
        const now = new Date();
        this.state = useState({
            loading: true,
            message: false,
            denied: false,
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            departmentId: 0,
            selectedEmployeeId: 0,
            data: {
                kpi: {},
                tree: [],
                detail: {},
                departments: [],
                month_label: "",
            },
            expanded: {},
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                if (!this.state.loading) {
                    this.renderChart();
                }
                return () => this.destroyCharts();
            },
            () => [this.state.loading, this.state.data?.detail, this.state.selectedEmployeeId]
        );
    }

    get kpi() {
        return this.state.data?.kpi || {};
    }

    get detail() {
        return this.state.data?.detail || {};
    }

    get years() {
        const y = new Date().getFullYear();
        return [y, y - 1, y - 2];
    }

    get months() {
        return Array.from({ length: 12 }, (_, i) => i + 1);
    }

    async load() {
        this.state.loading = true;
        this.state.denied = false;
        this.state.message = false;
        try {
            const data = await this.orm.call(
                "daily.task.performance.report",
                "get_performance_report",
                [],
                {
                    year: this.state.year,
                    month: this.state.month,
                    employee_id: this.state.selectedEmployeeId || false,
                    department_id: this.state.departmentId || false,
                }
            );
            this.state.data = data || {};
            this.state.message = data?.message || false;
            if (data?.selected_employee_id) {
                this.state.selectedEmployeeId = data.selected_employee_id;
            }
            // Expand parents of selected by default
            this._expandToSelected(data?.tree || [], data?.selected_employee_id);
        } catch (e) {
            const msg = e?.data?.message || e?.message || _t("Không tải được báo cáo hiệu suất.");
            this.state.denied = true;
            this.state.message = msg;
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    _expandToSelected(nodes, selectedId, parents = []) {
        for (const n of nodes) {
            if (n.id === selectedId) {
                for (const p of parents) {
                    this.state.expanded[p] = true;
                }
                return true;
            }
            if (n.children?.length && this._expandToSelected(n.children, selectedId, [...parents, n.id])) {
                this.state.expanded[n.id] = true;
                return true;
            }
        }
        return false;
    }

    async onFilter() {
        await this.load();
    }

    async selectEmployee(id) {
        this.state.selectedEmployeeId = id;
        await this.load();
    }

    toggleNode(id, ev) {
        ev?.stopPropagation?.();
        this.state.expanded[id] = !this.state.expanded[id];
    }

    isExpanded(id) {
        return Boolean(this.state.expanded[id]);
    }

    starIcons(stars) {
        const full = Math.floor(Number(stars) || 0);
        const half = (Number(stars) || 0) - full >= 0.5 ? 1 : 0;
        const empty = Math.max(0, 5 - full - half);
        return {
            full: Array.from({ length: full }, (_, i) => i),
            half: Boolean(half),
            empty: Array.from({ length: empty }, (_, i) => i),
        };
    }

    priorityClass(p) {
        return { high: "pri-high", medium: "pri-mid", low: "pri-low" }[p] || "pri-mid";
    }

    stateClass(row) {
        if (row.is_overdue) {
            return "st-overdue";
        }
        if (row.state === "done") {
            return "st-done";
        }
        return "st-progress";
    }

    destroyCharts() {
        for (const c of this.charts) {
            try {
                c.destroy();
            } catch (_e) {
                /* ignore */
            }
        }
        this.charts = [];
    }

    renderChart() {
        this.destroyCharts();
        if (!window.Chart || !this.stateChartRef.el) {
            return;
        }
        const sc = this.detail.state_chart || {};
        const done = Number(sc.done) || 0;
        const overdue = Number(sc.overdue) || 0;
        const other = Number(sc.other) || 0;
        this.charts.push(
            new window.Chart(this.stateChartRef.el, {
                type: "doughnut",
                data: {
                    labels: ["Hoàn thành", "Quá hạn", "Khác"],
                    datasets: [
                        {
                            data: [done, overdue, other],
                            backgroundColor: ["#22c55e", "#ef4444", "#cbd5e1"],
                            borderWidth: 0,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "68%",
                    plugins: { legend: { display: false } },
                },
            })
        );
    }
}

registry.category("actions").add("daily_work_performance_report", DailyWorkPerformanceReport);
