/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class DailyWorkDashboard extends Component {
    static template = "daily_work_task.DailyWorkDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.priorityChartRef = useRef("priorityChart");
        this.stateChartRef = useRef("stateChart");
        this.weeklyChartRef = useRef("weeklyChart");
        this.deptChartRef = useRef("deptChart");
        this.charts = [];
        this.state = useState({
            loading: true,
            data: {
                kpi: {},
                priority_chart: {},
                state_chart: {},
                weekly_chart: {},
                department_chart: { legend: [] },
                dept_performance: [],
                kpi_rank: [],
                kpi_rank_dept: "",
                top_employees: [],
                alerts: [],
                overdue_list: [],
                done_list: [],
                in_progress_list: [],
                not_started_list: [],
                recent_tasks: [],
                today_schedule: [],
            },
            employees: [],
            departments: [],
            dateFrom: "",
            dateTo: "",
            assigneeId: 0,
            departmentId: 0,
            stateFilter: "",
            isManager: false,
            canSeePerformance: false,
            userName: "",
            companyName: "",
            sidebarCollapsed: false,
            configOpen: true,
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            const opts = await this.orm.call("daily.task.dashboard", "get_filter_options", []);
            this.state.employees = opts.employees || [];
            this.state.departments = opts.departments || [];
            this.state.dateFrom = opts.default_date_from || "";
            this.state.dateTo = opts.default_date_to || "";
            this.state.isManager = Boolean(opts.is_manager);
            this.state.canSeePerformance = Boolean(opts.can_see_performance);
            this.state.userName = opts.user_name || "";
            this.state.companyName = opts.company_name || "";
            await this.loadDashboard();
        });
        useEffect(
            () => {
                if (!this.state.loading && this.state.data) {
                    this.renderCharts();
                }
                return () => this.destroyCharts();
            },
            () => [this.state.loading, this.state.data]
        );
    }

    get filtersPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            assignee_id: this.state.assigneeId || false,
            department_id: this.state.departmentId || false,
            state: this.state.stateFilter || false,
        };
    }

    get kpi() {
        return this.state.data?.kpi || {};
    }

    get greeting() {
        const name = this.state.userName || "Administrator";
        return `Xin chào, ${name}`;
    }

    get deptLegend() {
        return this.state.data?.department_chart?.legend || [];
    }

    /** 3 thẻ cảnh báo cố định (layout ngang) cho user không phải manager/admin. */
    get personalAlertCards() {
        const kpi = this.kpi;
        const overdue = Number(kpi.overdue) || 0;
        const upcoming = Number(kpi.upcoming) || 0;
        const missing = Math.max(0, (Number(kpi.emp_total) || 0) - (Number(kpi.emp_active) || 0));
        return [
            {
                type: "danger",
                icon: "fa-exclamation",
                title: `${overdue} công việc quá hạn`,
                subtitle: "Cần xử lý ngay",
                action: "overdue",
            },
            {
                type: "warning",
                icon: "fa-clock-o",
                title: `${upcoming} công việc sắp đến hạn`,
                subtitle: "Trong 7 ngày tới",
                action: "overview",
            },
            {
                type: "amber",
                icon: "fa-user",
                title: `${missing} nhân viên chưa có công việc`,
                subtitle: "Nhắc nhở nhập công việc",
                action: "viewer",
            },
        ];
    }

    /** Xếp hạng KPI phòng ban — 3 tháng gần nhất (user nhân viên). */
    get kpiRankRows() {
        const rows = this.state.data?.kpi_rank || [];
        return rows.map((r, i) => ({
            id: r.id ?? i,
            name: r.name || "Khác",
            total: Number(r.total) || 0,
            overdue: Number(r.overdue) || 0,
            efficiency: Number(r.efficiency) || 0,
            rank: i + 1,
        }));
    }

    medalLabel(rank) {
        return { 1: "🥇", 2: "🥈", 3: "🥉" }[rank] || String(rank);
    }

    onAlertClick(action) {
        if (action) {
            this.openNav(action);
        }
    }

    async loadDashboard() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "daily.task.dashboard",
                "get_dashboard_data",
                [],
                { filters: this.filtersPayload }
            );
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được dashboard."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async onFilter() {
        await this.loadDashboard();
    }

    async onRefresh() {
        await this.loadDashboard();
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

    renderCharts() {
        this.destroyCharts();
        if (!window.Chart || !this.state.data) {
            return;
        }
        const d = this.state.data;

        if (this.priorityChartRef.el && d.priority_chart) {
            this.charts.push(
                new window.Chart(this.priorityChartRef.el, {
                    type: "bar",
                    data: {
                        labels: d.priority_chart.labels || [],
                        datasets: [
                            {
                                data: d.priority_chart.values || [],
                                backgroundColor: d.priority_chart.colors || [],
                                borderRadius: 8,
                                maxBarThickness: 48,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#f1f5f9" } },
                            x: { grid: { display: false } },
                        },
                    },
                })
            );
        }

        if (this.stateChartRef.el && d.state_chart) {
            this.charts.push(
                new window.Chart(this.stateChartRef.el, {
                    type: "doughnut",
                    data: {
                        labels: d.state_chart.labels || [],
                        datasets: [
                            {
                                data: d.state_chart.values || [],
                                backgroundColor: d.state_chart.colors || [],
                                borderWidth: 0,
                                cutout: "68%",
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                    },
                })
            );
        }

        if (this.weeklyChartRef.el && d.weekly_chart) {
            this.charts.push(
                new window.Chart(this.weeklyChartRef.el, {
                    type: "line",
                    data: {
                        labels: d.weekly_chart.labels || [],
                        datasets: [
                            {
                                data: d.weekly_chart.values || [],
                                borderColor: "#7c3aed",
                                backgroundColor: "rgba(124, 58, 237, 0.15)",
                                fill: true,
                                tension: 0.35,
                                pointRadius: 4,
                                pointBackgroundColor: "#7c3aed",
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
                                max: 100,
                                ticks: { callback: (v) => `${v}%` },
                                grid: { color: "#f1f5f9" },
                            },
                            x: { grid: { display: false } },
                        },
                    },
                })
            );
        }

        if (this.deptChartRef.el && d.department_chart) {
            this.charts.push(
                new window.Chart(this.deptChartRef.el, {
                    type: "doughnut",
                    data: {
                        labels: d.department_chart.labels || [],
                        datasets: [
                            {
                                data: d.department_chart.values || [],
                                backgroundColor: d.department_chart.colors || [],
                                borderWidth: 2,
                                borderColor: "#fff",
                                cutout: "55%",
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                    },
                })
            );
        }
    }

    growthClass(v) {
        const n = Number(v) || 0;
        if (n > 0) {
            return "up";
        }
        if (n < 0) {
            return "down";
        }
        return "";
    }

    growthLabel(v) {
        const n = Number(v) || 0;
        const sign = n > 0 ? "+" : "";
        return `${sign}${n}%`;
    }

    stateBadgeClass(state) {
        return (
            {
                done: "badge-done",
                in_progress: "badge-progress",
                not_started: "badge-todo",
            }[state] || "badge-todo"
        );
    }

    priorityClass(p) {
        return (
            {
                high: "pri-high",
                medium: "pri-mid",
                low: "pri-low",
            }[p] || "pri-mid"
        );
    }

    alertClass(type) {
        return (
            {
                danger: "alert-danger",
                warning: "alert-warning",
                amber: "alert-amber",
                info: "alert-info",
            }[type] || "alert-info"
        );
    }

    async openTask(taskId) {
        if (!taskId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "daily.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openNav(key) {
        const map = {
            dashboard: "daily_work_dashboard",
            tasks: "daily_work_task_manager",
            assign: "daily_work_assign",
            report: "daily_work_summary_report",
            overview: "daily_work_report_overview",
            performance: "daily_work_performance_report",
            calendar: "daily_work_calendar",
            notebook: "daily_work_notebook",
            employee_ws: "daily_work_employee_ws",
            overdue: null,
            viewer: "daily_work_viewer",
            send_mail: null,
            config: null,
        };
        if (key === "dashboard") {
            await this.loadDashboard();
            return;
        }
        if (key === "overdue") {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Công việc quá hạn",
                res_model: "daily.task",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: [["is_overdue", "=", true]],
            });
            return;
        }
        if (key === "send_mail") {
            await this.action.doAction("daily_work_task.action_daily_task_send_overdue");
            return;
        }
        if (key === "config") {
            await this.action.doAction("daily_work_task.action_daily_task_work_group");
            return;
        }
        if (key === "recurring") {
            await this.action.doAction("daily_work_task.action_daily_task_recurring");
            return;
        }
        if (key === "employees") {
            await this.action.doAction("daily_work_task.action_daily_task_employee");
            return;
        }
        if (key === "access") {
            await this.action.doAction("daily_work_task.action_daily_task_access");
            return;
        }
        if (key === "report_access") {
            await this.action.doAction("daily_work_task.action_daily_task_report_access");
            return;
        }
        if (key === "performance_access") {
            await this.action.doAction("daily_work_task.action_daily_task_performance_access");
            return;
        }
        const tag = map[key];
        if (tag) {
            await this.action.doAction({ type: "ir.actions.client", tag });
        } else {
            this.notification.add(_t("Mục này sẽ bổ sung sau."), { type: "info" });
        }
    }

    async onExportExcel() {
        this.notification.add(_t("Đang mở Báo cáo tổng để xuất Excel…"), { type: "info" });
        await this.action.doAction({ type: "ir.actions.client", tag: "daily_work_summary_report" });
    }
}

registry.category("actions").add("daily_work_dashboard", DailyWorkDashboard);
