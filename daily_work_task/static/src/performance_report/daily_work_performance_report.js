/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

export class DailyWorkPerformanceReport extends Component {
    static template = "daily_work_task.DailyWorkPerformanceReport";
    static props = { ...standardActionServiceProps };
    // Thanh menu bên trái / trên dùng chung như các trang Công việc khác
    static components = { DailyWorkAppShell };

    get shellActiveNav() {
        return "performance";
    }

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.stateChartRef = useRef("stateChart");
        this.deptChartRef = useRef("deptChart");
        this.trendChartRef = useRef("trendChart");
        this.charts = [];
        const now = new Date();
        this.state = useState({
            perfDraft: {},
            perfSaving: false,
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
            exporting: false,
            // Nhóm phòng ban đang thu gọn: { tên phòng: true }
            deptClosed: {},
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
            () => [this.state.loading, this.state.data, this.state.selectedEmployeeId]
        );
    }

    get kpi() {
        return this.state.data?.kpi || {};
    }

    /** 4 thẻ KPI kèm so sánh tháng trước. */
    get kpiCards() {
        const k = this.kpi;
        const p = this.state.data?.kpi_prev || {};
        const card = (key, label, cur, prev, unit, goodUp) => {
            const c = Number(cur) || 0;
            const pv = Number(prev) || 0;
            let delta;
            if (unit === "%") {
                delta = Math.round((c - pv) * 10) / 10;
            } else {
                delta = pv ? Math.round(((c - pv) / pv) * 1000) / 10 : c ? 100 : 0;
            }
            const up = delta > 0;
            const flat = delta === 0;
            const good = flat ? null : up === goodUp;
            return {
                key,
                label,
                value: unit === "%" ? `${c}%` : String(c),
                deltaText: `${up ? "+" : ""}${delta}${unit === "%" ? " điểm" : "%"}`,
                trendIcon: flat ? "fa-minus" : up ? "fa-arrow-up" : "fa-arrow-down",
                trendClass: good === null ? "is-flat" : good ? "is-good" : "is-bad",
            };
        };
        return [
            card("total", "Tổng công việc", k.total, p.total, "", true),
            card("done", "Hoàn thành", k.done, p.done, "", true),
            card("overdue", "Quá hạn", k.overdue, p.overdue, "", false),
            card("eff", "Hiệu suất TB (QL đánh giá)", k.efficiency, p.efficiency, "%", true),
        ];
    }

    toggleDept(g) {
        this.state.deptClosed[g.key] = this.isDeptOpen(g);
    }

    /** Mặc định: mở phòng có công việc, thu gọn phòng chưa có việc nào. */
    isDeptOpen(g) {
        if (g.key in this.state.deptClosed) {
            return !this.state.deptClosed[g.key];
        }
        return (Number(g.total) || 0) > 0;
    }

    initials(name) {
        const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
        if (!parts.length) {
            return "?";
        }
        return ((parts[0][0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
    }

    /** QL đánh giá tổng: nhập → giữ tạm (chưa áp dụng); bấm «Lưu» mới ghi. Để trống = dùng giá trị tự động. */
    onManagerPerf(r, ev) {
        const raw = String(ev.target.value || "").trim().replace(",", ".");
        const value = raw === "" ? null : Number(raw);
        if (value !== null && (Number.isNaN(value) || value < 0 || value > 100)) {
            this.notification.add(_t("% QL đánh giá tổng phải từ 0 đến 100."), { type: "warning" });
            ev.target.value = this.perfShown(r);
            return;
        }
        const saved = r.manager_perf === undefined ? null : r.manager_perf;
        if (value === saved) {
            delete this.state.perfDraft[r.id];
        } else {
            this.state.perfDraft[r.id] = { row: r, value };
        }
    }

    perfShown(r) {
        const d = this.state.perfDraft[r.id];
        const v = d ? d.value : r.manager_perf;
        return v === null || v === undefined ? "" : v;
    }

    isPerfDirty(r) {
        return Boolean(this.state.perfDraft[r.id]);
    }

    get perfDirtyCount() {
        return Object.keys(this.state.perfDraft).length;
    }

    /** Lưu: áp dụng mọi giá trị QL đánh giá tổng đang chờ. */
    async onSavePerf() {
        const items = Object.values(this.state.perfDraft);
        if (!items.length || this.state.perfSaving) {
            return;
        }
        this.state.perfSaving = true;
        let ok = 0;
        try {
            for (const { row, value } of items) {
                const res = await this.orm.call("daily.task.performance.report", "set_manager_perf", [
                    row.id, this.state.year, this.state.month, value,
                ]);
                row.manager_perf = res.percent;
                delete this.state.perfDraft[row.id];
                ok += 1;
            }
            this.notification.add(`Đã lưu QL đánh giá tổng cho ${ok} nhân sự.`, { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được QL đánh giá tổng."), { type: "danger" });
        } finally {
            this.state.perfSaving = false;
        }
    }

    onCancelPerf() {
        this.state.perfDraft = {};
    }

    effClass(v) {
        const n = Number(v) || 0;
        return n >= 85 ? "is-good" : n >= 70 ? "is-ok" : n >= 50 ? "is-mid" : "is-bad";
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
        this.state.perfDraft = {};
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

    async onExport() {
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task.performance.report", "export_excel", [], {
                year: this.state.year,
                month: this.state.month,
                department_id: this.state.departmentId || false,
            });
            const bin = atob(res.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const url = URL.createObjectURL(
                new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })
            );
            const a = document.createElement("a");
            a.href = url;
            a.download = res.filename || "Danh_gia_hieu_suat.xlsx";
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add(_t("Đã xuất Đánh giá hiệu suất tháng ra Excel."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
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

    renderOverviewCharts() {
        const grid = { color: "#eef2f7" };
        const dept = this.state.data?.dept_chart || [];
        if (this.deptChartRef.el && dept.length) {
            this.charts.push(
                new window.Chart(this.deptChartRef.el, {
                    type: "bar",
                    data: {
                        labels: dept.map((d) => d.name),
                        datasets: [
                            { label: "Hoàn thành", data: dept.map((d) => d.done), backgroundColor: "#22c55e", borderRadius: 4, maxBarThickness: 48 },
                            { label: "Đang làm", data: dept.map((d) => d.doing || 0), backgroundColor: "#f59e0b", borderRadius: 4, maxBarThickness: 48 },
                            { label: "Chưa làm", data: dept.map((d) => d.todo || 0), backgroundColor: "#94a3b8", borderRadius: 4, maxBarThickness: 48 },
                            { label: "Trễ hạn", data: dept.map((d) => d.overdue), backgroundColor: "#ef4444", borderRadius: 4, maxBarThickness: 48 },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 10 } } },
                        scales: {
                            x: { stacked: true, grid: { display: false } },
                            y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid },
                        },
                    },
                })
            );
        }
        const trend = this.state.data?.trend || [];
        if (this.trendChartRef.el && trend.length) {
            const ctx = this.trendChartRef.el.getContext("2d");
            const grad = (c1, c2) => {
                const g = ctx.createLinearGradient(0, 0, 0, 280);
                g.addColorStop(0, c1);
                g.addColorStop(1, c2);
                return g;
            };
            this.charts.push(
                new window.Chart(this.trendChartRef.el, {
                    type: "line",
                    data: {
                        labels: trend.map((t) => t.label),
                        datasets: [
                            {
                                label: "Tổng công việc",
                                data: trend.map((t) => t.total),
                                borderColor: "#5b7bd5",
                                backgroundColor: grad("rgba(91,123,213,0.35)", "rgba(91,123,213,0.02)"),
                                fill: true,
                                tension: 0.45,
                                pointRadius: 0,
                                borderWidth: 1.5,
                            },
                            {
                                label: "Hoàn thành",
                                data: trend.map((t) => t.done),
                                borderColor: "#8b3dff",
                                backgroundColor: grad("rgba(139,61,255,0.35)", "rgba(139,61,255,0.02)"),
                                fill: true,
                                tension: 0.45,
                                pointRadius: 0,
                                borderWidth: 1.5,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: "index", intersect: false },
                        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 10 } } },
                        scales: {
                            x: { grid: { display: false } },
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid },
                        },
                    },
                })
            );
        }
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
        if (!window.Chart) {
            return;
        }
        this.renderOverviewCharts();
        if (!this.stateChartRef.el) {
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
