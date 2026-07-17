/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class DailyWorkReportOverview extends Component {
    static template = "daily_work_task.DailyWorkReportOverview";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.stateChartRef = useRef("stateChart");
        this.weeklyChartRef = useRef("weeklyChart");
        this.evalChartRef = useRef("evalChart");
        this.statePanelRef = useRef("statePanel");
        this.weeklyPanelRef = useRef("weeklyPanel");
        this.evalPanelRef = useRef("evalPanel");
        this.charts = [];
        const now = new Date();
        const year = now.getFullYear();
        this.state = useState({
            loading: true,
            message: false,
            monthMonth: now.getMonth() + 1,
            monthYear: year,
            months: Array.from({ length: 12 }, (_, i) => ({
                value: i + 1,
                label: `Tháng ${i + 1}`,
            })),
            years: [year - 1, year, year + 1],
            filterEmp: 0,
            search: "",
            page: 1,
            collapsed: {},
            nav: "overview",
            userName: "",
            profile: {},
            kpi: {},
            charts: {},
            today: { date_label: "", tasks: [], total_hours: 0 },
            deadlines: { in_1_day: [], in_2_3_days: [], this_week: [] },
            reminders: {
                overdue: 0,
                today: 0,
                tomorrow: 0,
                this_week: 0,
                upcoming: 0,
                overdue_tasks: [],
                upcoming_tasks: [],
            },
            evaluation: {},
            rows: [],
            groups: [],
            filterOptions: { employees: [], work_groups: [] },
            canDelete: false,
            canPickEmployee: false,
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                if (!this.state.loading && !this.state.message && this.state.nav === "overview") {
                    this.renderCharts();
                } else {
                    this.destroyCharts();
                }
                return () => this.destroyCharts();
            },
            () => [
                this.state.loading,
                this.state.message,
                this.state.charts,
                this.state.evaluation,
                this.state.nav,
            ]
        );
    }

    get satacoLogoUrl() {
        return "/daily_work_task/static/description/sataco_logo.png?v=5";
    }

    get monthLabel() {
        const m = String(this.state.monthMonth).padStart(2, "0");
        return `Tháng ${m}/${this.state.monthYear}`;
    }

    get visibleGroups() {
        return (this.state.groups || []).map((g) => {
            const key = String(g.key);
            return {
                ...g,
                collapsed: Boolean(this.state.collapsed[key]),
            };
        });
    }

    /** Nhóm dạng bảng Excel (có thu gọn/mở). */
    get excelGroups() {
        return (this.state.groups || []).map((g) => {
            const key = String(g.key);
            const hours = Number(g.duration_hours) || 0;
            const hoursDisplay =
                Number.isInteger(hours) ? String(hours) : String(hours).replace(/\.0+$/, "");
            const avg = Number(g.avg_progress);
            return {
                ...g,
                key,
                collapsed: Boolean(this.state.collapsed[key]),
                duration_hours_display: hoursDisplay || "0",
                completion_percent_avg: Number.isFinite(avg) ? avg : 0,
                has_overdue: (g.rows || []).some((r) => r.is_active_overdue),
            };
        });
    }

    formatGroupAvg(group) {
        const v = Number(group?.completion_percent_avg) || 0;
        return Number.isInteger(v) ? String(v) : v.toFixed(1);
    }

    formatMonthAvg() {
        const groups = this.excelGroups;
        if (!groups.length) {
            const fromKpi = Number(this.state.kpi?.avg_progress) || 0;
            return Number.isInteger(fromKpi) ? String(fromKpi) : fromKpi.toFixed(1);
        }
        const sum = groups.reduce((s, g) => s + (Number(g.completion_percent_avg) || 0), 0);
        const v = Math.round((sum / groups.length) * 10) / 10;
        return Number.isInteger(v) ? String(v) : v.toFixed(1);
    }

    excelPriorityClass(priority) {
        return (
            {
                high: "o_dro_excel_badge_high",
                medium: "o_dro_excel_badge_medium",
                low: "o_dro_excel_badge_low",
            }[priority] || "o_dro_excel_badge_medium"
        );
    }

    excelStateClass(state) {
        return (
            {
                done: "o_dro_excel_state_done",
                in_progress: "o_dro_excel_state_progress",
                not_started: "o_dro_excel_state_todo",
            }[state] || "o_dro_excel_state_todo"
        );
    }

    excelRowClass(row) {
        if (row.state === "done") {
            return "o_dro_excel_row_done";
        }
        if (row.is_active_overdue || (Number(row.overdue_days) || 0) > 0) {
            return "o_dro_excel_row_overdue";
        }
        return "";
    }

    excelGroupClass(group) {
        if (group.has_overdue) {
            return "o_dro_excel_group o_dro_excel_group_warn";
        }
        return "o_dro_excel_group";
    }

    get tableSummary() {
        const total = (this.state.rows || []).length;
        const gcount = (this.state.groups || []).length;
        if (!total) {
            return "0 công việc";
        }
        return `${total} công việc · ${gcount} hạng mục`;
    }

    get reminderSummary() {
        const overdue = (this.state.reminders.overdue_tasks || []).length;
        const upcoming = (this.state.reminders.upcoming_tasks || []).length;
        return `${overdue + upcoming} việc cần chú ý · ${overdue} quá hạn · ${upcoming} sắp tới hạn`;
    }

    /** Số việc sắp tới hạn (7 ngày) — badge chuông sidebar. */
    get reminderUpcomingCount() {
        const fromList = (this.state.reminders.upcoming_tasks || []).length;
        if (fromList) {
            return fromList;
        }
        return Number(this.state.reminders.upcoming) || 0;
    }

    get stateLegend() {
        return this.state.charts?.by_state?.legend || [];
    }

    get starList() {
        const stars = Number(this.state.evaluation.stars || 0);
        const items = [];
        for (let i = 1; i <= 5; i++) {
            if (stars >= i) {
                items.push("full");
            } else if (stars >= i - 0.5) {
                items.push("half");
            } else {
                items.push("empty");
            }
        }
        return items;
    }

    filtersPayload() {
        return {
            employee_id: Number(this.state.filterEmp) || false,
            search: this.state.search || false,
        };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_report_overview", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
                filters: this.filtersPayload(),
            });
            this.state.message = data.message || false;
            this.state.userName = data.user_name || "";
            this.state.profile = data.profile || {};
            this.state.kpi = data.kpi || {};
            this.state.charts = data.charts || {};
            this.state.today = data.today || { date_label: "", tasks: [], total_hours: 0 };
            this.state.deadlines = data.deadlines || {
                in_1_day: [],
                in_2_3_days: [],
                this_week: [],
            };
            this.state.reminders = data.reminders || {
                overdue: 0,
                today: 0,
                tomorrow: 0,
                this_week: 0,
                upcoming: 0,
                overdue_tasks: [],
                upcoming_tasks: [],
            };
            if (!Array.isArray(this.state.reminders.overdue_tasks)) {
                this.state.reminders.overdue_tasks = [];
            }
            if (!Array.isArray(this.state.reminders.upcoming_tasks)) {
                this.state.reminders.upcoming_tasks = [];
            }
            this.state.evaluation = data.evaluation || {};
            this.state.rows = data.rows || [];
            this.state.groups = data.groups || [];
            this.state.filterOptions = data.filters || { employees: [], work_groups: [] };
            this.state.canDelete = Boolean(data.can_delete);
            this.state.canPickEmployee = Boolean(data.can_pick_employee);
            this.state.filterEmp = Number(data.selected_employee_id || this.state.filterEmp) || 0;
            this.state.page = 1;
            this.state.collapsed = {};
            (this.state.groups || []).forEach((g, idx) => {
                this.state.collapsed[String(g.key)] = idx > 0;
            });
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được báo cáo.");
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    async onRefresh() {
        await this.load();
    }

    toggleGroup(key) {
        const k = String(key);
        this.state.collapsed[k] = !this.state.collapsed[k];
    }

    setPage(page) {
        this.state.page = Number(page) || 1;
    }

    progressBarClass(pct) {
        const n = Number(pct) || 0;
        if (n >= 80) {
            return "bar-green";
        }
        if (n >= 40) {
            return "bar-blue";
        }
        if (n > 0) {
            return "bar-red";
        }
        return "bar-gray";
    }

    deadlineClass(row) {
        if (row.is_active_overdue) {
            return "dl-overdue";
        }
        if (row.state === "done") {
            return "dl-done";
        }
        return "dl-ok";
    }

    noteClass(row) {
        const note = (row.note || "").toLowerCase();
        if (row.priority === "high" || note.includes("gấp") || note.includes("gap")) {
            return "note-urgent";
        }
        return "";
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
        if (!window.Chart) {
            return;
        }
        const charts = this.state.charts || {};

        if (this.stateChartRef.el && charts.by_state) {
            this.charts.push(
                new window.Chart(this.stateChartRef.el, {
                    type: "doughnut",
                    data: {
                        labels: charts.by_state.labels || [],
                        datasets: [
                            {
                                data: charts.by_state.values || [],
                                backgroundColor: charts.by_state.colors || [
                                    "#22c55e",
                                    "#eab308",
                                    "#ef4444",
                                    "#94a3b8",
                                ],
                                borderWidth: 0,
                                cutout: "72%",
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

        if (this.weeklyChartRef.el && charts.weekly) {
            this.charts.push(
                new window.Chart(this.weeklyChartRef.el, {
                    type: "line",
                    data: {
                        labels: charts.weekly.labels || [],
                        datasets: [
                            {
                                label: "% hoàn thành",
                                data: charts.weekly.values || [],
                                borderColor: "#16a34a",
                                backgroundColor: "rgba(22, 163, 74, 0.12)",
                                fill: true,
                                tension: 0.4,
                                pointRadius: 4,
                                pointBackgroundColor: "#16a34a",
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: {
                                min: 0,
                                max: 100,
                                ticks: { callback: (v) => `${v}%` },
                                grid: { color: "#eef2f0" },
                            },
                            x: { grid: { display: false } },
                        },
                    },
                })
            );
        }

        if (this.evalChartRef.el) {
            const score = Number(this.state.evaluation.score || 0);
            this.charts.push(
                new window.Chart(this.evalChartRef.el, {
                    type: "doughnut",
                    data: {
                        labels: ["Score", "Rest"],
                        datasets: [
                            {
                                data: [score, Math.max(0, 100 - score)],
                                backgroundColor: ["#16a34a", "#e8efe9"],
                                borderWidth: 0,
                                cutout: "78%",
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    },
                })
            );
        }
    }

    priorityClass(p) {
        return { high: "pri-high", medium: "pri-mid", low: "pri-low" }[p] || "pri-mid";
    }

    priorityIcon(p) {
        return { high: "fa-fire", medium: "fa-minus", low: "fa-arrow-down" }[p] || "fa-minus";
    }

    stateDotClass(row) {
        if (row.is_active_overdue) {
            return "dot-overdue";
        }
        return (
            {
                done: "dot-done",
                in_progress: "dot-progress",
                not_started: "dot-todo",
            }[row.state] || "dot-todo"
        );
    }

    stateLabel(row) {
        if (row.is_active_overdue && row.state !== "done") {
            return "Quá hạn";
        }
        return row.state_label || "";
    }

    async openNav(key) {
        this.state.nav = key;
        if (key === "overview" || key === "reminders") {
            return;
        }
        const map = {
            tasks: "daily_work_employee_ws",
            calendar: "daily_work_calendar",
            report: "daily_work_summary_report",
            manager: "daily_work_task_manager",
        };
        const tag = map[key];
        if (tag) {
            await this.action.doAction({ type: "ir.actions.client", tag });
        } else {
            this.notification.add(_t("Mục này sẽ bổ sung sau."), { type: "info" });
        }
    }

    async onView(row) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "daily.task",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onEdit(row) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "daily.task",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
            context: { form_view_initial_mode: "edit" },
        });
    }

    async onComplete(row) {
        try {
            await this.orm.call("daily.task", "action_set_done", [[row.id]]);
            this.notification.add(_t("Đã hoàn thành công việc."), { type: "success" });
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật được."), {
                type: "danger",
            });
        }
    }

    _downloadBase64File(result, fallbackName, mime) {
        if (!result?.file_base64) {
            throw new Error("empty");
        }
        const binary = atob(result.file_base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: mime || result.mimetype || "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = result.filename || fallbackName;
        a.click();
        URL.revokeObjectURL(url);
    }

    async _captureChartImages() {
        const grabCanvas = (ref) => {
            try {
                return ref?.el?.toDataURL?.("image/png") || false;
            } catch (_e) {
                return false;
            }
        };
        const grabPanel = async (ref) => {
            const el = ref?.el;
            if (!el || typeof window.html2canvas !== "function") {
                return false;
            }
            try {
                const canvas = await window.html2canvas(el, {
                    backgroundColor: "#ffffff",
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    allowTaint: true,
                });
                return canvas.toDataURL("image/png");
            } catch (_e) {
                return false;
            }
        };
        // Chụp cả khung thẻ (biểu đồ + chú thích) — giống ảnh xu hướng tuần
        const [state, weekly, evalImg] = await Promise.all([
            grabPanel(this.statePanelRef),
            grabPanel(this.weeklyPanelRef),
            grabPanel(this.evalPanelRef),
        ]);
        return {
            state: state || grabCanvas(this.stateChartRef),
            weekly: weekly || grabCanvas(this.weeklyChartRef),
            eval: evalImg || grabCanvas(this.evalChartRef),
        };
    }

    async onExportExcel() {
        try {
            const chart_images = await this._captureChartImages();
            const result = await this.orm.call("daily.task", "export_personal_report_excel", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
                filters: this.filtersPayload(),
                chart_images,
            });
            this._downloadBase64File(
                result,
                "bao_cao_ca_nhan.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            );
            this.notification.add(_t("Đã xuất Excel (ảnh khung biểu đồ)."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), {
                type: "danger",
            });
        }
    }

    async onExportPdf() {
        try {
            const chart_images = await this._captureChartImages();
            const result = await this.orm.call("daily.task", "export_personal_report_pdf", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
                filters: this.filtersPayload(),
                chart_images,
            });
            this._downloadBase64File(result, "bao_cao_ca_nhan.pdf", "application/pdf");
            this.notification.add(_t("Đã xuất PDF (ảnh khung biểu đồ)."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được PDF."), {
                type: "danger",
            });
        }
    }
}

registry.category("actions").add("daily_work_report_overview", DailyWorkReportOverview);
