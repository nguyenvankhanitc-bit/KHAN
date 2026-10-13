/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Báo cáo công việc tháng — theo mẫu Excel "BÁO CÁO CÔNG VIỆC THÁNG" (nhóm hạng mục I, II…). */
export class DailyWorkMonthlyReport extends Component {
    static template = "daily_work_task.DailyWorkMonthlyReport";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const today = new Date();
        this.state = useState({
            loading: true,
            exporting: false,
            year: today.getFullYear(),
            month: today.getMonth() + 1,
            employeeId: false,
            data: null,
        });
        // Dashboard (giống Báo cáo cá nhân): donut trạng thái, xu hướng theo tuần, đánh giá hiệu suất
        this.stateChartRef = useRef("stateChart");
        this.weeklyChartRef = useRef("weeklyChart");
        this.evalChartRef = useRef("evalChart");
        // Khung bảng cao đúng bằng vùng nội dung → thanh cuộn ngang nằm sát đáy màn hình
        this.tableWrapRef = useRef("tableWrap");
        this._fitTableWrap = () => this.fitTableWrap();
        useEffect(
            () => {
                this.fitTableWrap();
                window.addEventListener("resize", this._fitTableWrap);
                return () => window.removeEventListener("resize", this._fitTableWrap);
            },
            () => [this.state.loading, this.state.data]
        );
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                if (!this.state.loading && this.state.data && !this.state.data.message) {
                    this.renderCharts();
                }
                return () => this.destroyCharts();
            },
            () => [this.state.loading, this.state.data]
        );
    }

    /** Chiều cao khung bảng = phần nhìn thấy của vùng cuộn trang (dưới thanh menu tới đáy cửa sổ). */
    fitTableWrap() {
        const wrap = this.tableWrapRef.el;
        if (!wrap) {
            return;
        }
        let scroller = wrap.parentElement;
        while (scroller && scroller !== document.body) {
            const oy = getComputedStyle(scroller).overflowY;
            if ((oy === "auto" || oy === "scroll") && scroller.clientHeight < scroller.scrollHeight + 1) {
                break;
            }
            scroller = scroller.parentElement;
        }
        const top = scroller && scroller !== document.body ? scroller.getBoundingClientRect().top : 0;
        const bottom = Math.min(
            window.innerHeight,
            scroller && scroller !== document.body ? scroller.getBoundingClientRect().bottom : window.innerHeight
        );
        const h = Math.max(320, Math.floor(bottom - Math.max(0, top) - 4));
        wrap.style.maxHeight = h + "px";
    }

    get kpi() {
        return this.state.data?.kpi || {};
    }

    get evaluation() {
        return this.state.data?.evaluation || {};
    }

    get stateLegend() {
        return this.state.data?.charts?.by_state?.legend || [];
    }

    get stars() {
        const score = Number(this.evaluation.stars || 0);
        return [1, 2, 3, 4, 5].map((i) =>
            score >= i ? "fa fa-star" : score >= i - 0.5 ? "fa fa-star-half-o" : "fa fa-star-o"
        );
    }

    pct(n) {
        const total = Number(this.kpi.total || 0);
        return total ? `${((100 * Number(n || 0)) / total).toFixed(1)}%` : "0%";
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

    renderCharts() {
        this.destroyCharts();
        if (!window.Chart) {
            return;
        }
        const charts = this.state.data?.charts || {};
        if (this.stateChartRef.el && charts.by_state) {
            this.charts.push(
                new window.Chart(this.stateChartRef.el, {
                    type: "doughnut",
                    data: {
                        labels: charts.by_state.labels || [],
                        datasets: [
                            {
                                data: charts.by_state.values || [],
                                backgroundColor: charts.by_state.colors || [],
                                borderWidth: 0,
                                cutout: "72%",
                            },
                        ],
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
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
                            y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` }, grid: { color: "#eef2f0" } },
                            x: { grid: { display: false } },
                        },
                    },
                })
            );
        }
        if (this.evalChartRef.el) {
            const score = Number(this.evaluation.score || 0);
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

    get shellActiveNav() {
        return "monthly_report";
    }

    get monthLabel() {
        return `Tháng ${String(this.state.month).padStart(2, "0")}/${this.state.year}`;
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("daily.task.monthly.report", "get_report", [], {
                year: this.state.year,
                month: this.state.month,
                employee_id: this.state.employeeId,
            });
            this.state.employeeId = this.state.data?.employee?.id || this.state.employeeId;
        } catch (e) {
            this.state.data = null;
            this.notification.add(e?.data?.message || _t("Không tải được báo cáo tháng."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async shiftMonth(delta) {
        let month = this.state.month + delta;
        let year = this.state.year;
        if (month < 1) {
            month = 12;
            year -= 1;
        } else if (month > 12) {
            month = 1;
            year += 1;
        }
        this.state.month = month;
        this.state.year = year;
        await this.load();
    }

    get monthOptions() {
        return Array.from({ length: 12 }, (_, i) => i + 1);
    }

    get initial() {
        return ((this.state.data?.employee?.name || "?").trim().split(/\s+/).pop() || "?").charAt(0).toUpperCase();
    }

    async onMonthSelect(ev) {
        this.state.month = parseInt(ev.target.value) || this.state.month;
        await this.load();
    }

    async onYearInput(ev) {
        const y = parseInt(ev.target.value);
        if (y >= 2000 && y <= 2100) {
            this.state.year = y;
            await this.load();
        }
    }

    async onEmployee(ev) {
        this.state.employeeId = parseInt(ev.target.value) || false;
        await this.load();
    }

    fmt(value) {
        const n = Number(value || 0);
        return n ? n.toLocaleString("vi-VN", { maximumFractionDigits: 1 }) : "0";
    }

    async onExport() {
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task.monthly.report", "export_excel", [], {
                year: this.state.year,
                month: this.state.month,
                employee_id: this.state.employeeId,
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
            a.download = res.filename || "Bao_cao_cong_viec_thang.xlsx";
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add(_t("Đã xuất Báo cáo công việc tháng ra Excel."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_monthly_report", DailyWorkMonthlyReport);
