/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Màu trạng thái (giống Báo cáo cá nhân). */
const STATE_META = [
    { key: "done", label: "Hoàn thành", color: "#22c55e" },
    { key: "in_progress", label: "Đang thực hiện", color: "#eab308" },
    { key: "overdue", label: "Quá hạn", color: "#ef4444" },
    { key: "not_started", label: "Chưa bắt đầu", color: "#94a3b8" },
];
const pct1 = (n, total) => (total ? Math.round((n * 1000) / total) / 10 : 0);

/** Báo cáo NV Kho (BÁO CÁO → Các loại báo cáo). */
export class DailyWorkKhoReport extends Component {
    static template = "daily_work_task.DailyWorkKhoReport";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            message: false,
            month: now.getMonth() + 1,
            year: now.getFullYear(),
            teamId: 0,
            teamName: "",
            teamDept: "",
            teams: [],
            employeeId: 0,
            employees: [],
            canPick: false,
            showEmployee: false,
            rows: [],
            closed: {},
            evalTiers: [],
            canExport: true,
            exporting: false,
        });
        this.months = Array.from({ length: 12 }, (_, i) => i + 1);
        this.years = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1];
        this.stateRef = useRef("stateChart");
        this.weeklyRef = useRef("weeklyChart");
        this.evalRef = useRef("evalChart");
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                this.renderCharts();
            },
            () => [this.state.loading, this.state.rows]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    // ------------------------------------------------------------ chỉ số (giống Báo cáo cá nhân)
    /** KPI: Tổng · Hoàn thành · Đang thực hiện · Quá hạn · Tổng thời gian · Hiệu suất · Tiến độ. */
    get kpi() {
        const rows = this.state.rows;
        const total = rows.length;
        const done = rows.filter((r) => r.state === "done").length;
        const inProgress = rows.filter((r) => r.state === "in_progress").length;
        const overdue = rows.filter((r) => r.is_overdue).length;
        // Tổng thời gian = phút của việc ĐÃ HOÀN THÀNH (như Báo cáo cá nhân)
        const doneMinutes = rows.filter((r) => r.state === "done").reduce((s, r) => s + (Number(r.minutes) || 0), 0);
        // Hiệu suất = TB % QL đánh giá trên mọi việc (chưa đánh giá = 0%)
        const evalSum = rows.reduce((s, r) => s + (r.evaluated ? Number(r.eval_percent) || 0 : 0), 0);
        const progSum = rows.reduce((s, r) => s + (Number(r.progress) || 0), 0);
        const efficiency = total ? Math.round((evalSum / total) * 10) / 10 : 0;
        return {
            total,
            done,
            inProgress,
            overdue,
            donePct: pct1(done, total),
            inProgressPct: pct1(inProgress, total),
            overduePct: pct1(overdue, total),
            hours: Math.round((doneMinutes / 60) * 10) / 10,
            efficiency,
            progress: total ? Math.round((progSum / total) * 10) / 10 : 0,
        };
    }

    get progressBarStyle() {
        return `width:${Math.max(0, Math.min(100, this.kpi.progress))}%`;
    }

    /** Donut trạng thái: Quá hạn ưu tiên hơn trạng thái chưa xong. */
    get stateLegend() {
        const rows = this.state.rows;
        const counts = {
            done: rows.filter((r) => r.state === "done").length,
            in_progress: rows.filter((r) => r.state === "in_progress" && !r.is_overdue).length,
            overdue: rows.filter((r) => r.is_overdue).length,
            not_started: rows.filter((r) => r.state === "not_started" && !r.is_overdue).length,
        };
        return STATE_META.map((m) => ({ ...m, count: counts[m.key], pct: pct1(counts[m.key], rows.length) }));
    }

    /** Xu hướng hoàn thành theo tuần: % hoàn thành TB của việc trong từng tuần (theo deadline). */
    get weekly() {
        const buckets = { 1: [], 2: [], 3: [], 4: [], 5: [] };
        for (const r of this.state.rows) {
            if (!r.day) {
                continue;
            }
            const w = Math.min(5, Math.max(1, Math.floor((r.day - 1) / 7) + 1));
            buckets[w].push(Number(r.progress) || 0);
        }
        return [1, 2, 3, 4, 5].map((w) =>
            buckets[w].length ? Math.round((buckets[w].reduce((s, v) => s + v, 0) / buckets[w].length) * 10) / 10 : 0
        );
    }

    /** Đánh giá hiệu suất tháng (giống Báo cáo cá nhân). */
    get evaluation() {
        const k = this.kpi;
        const score = k.efficiency;
        let rating = "Trung bình";
        if (score >= 85) {
            rating = "Tốt";
        } else if (score >= 70) {
            rating = "Khá";
        } else if (score < 50) {
            rating = "Cần cải thiện";
        }
        return {
            score,
            rating,
            stars: score ? Math.min(5, Math.round((score / 20) * 2) / 2) : 0,
            total: k.total,
            done: k.done,
            overdue: k.overdue,
            hours: k.hours,
        };
    }

    get starList() {
        const stars = this.evaluation.stars;
        return [1, 2, 3, 4, 5].map((i) => (stars >= i ? "full" : stars >= i - 0.5 ? "half" : "empty"));
    }

    destroyCharts() {
        for (const c of this.charts) {
            c.destroy();
        }
        this.charts = [];
    }

    renderCharts() {
        this.destroyCharts();
        const Chart = window.Chart;
        if (this.state.loading || !Chart) {
            return;
        }
        if (this.stateRef.el) {
            const legend = this.stateLegend.filter((l) => l.count);
            this.charts.push(new Chart(this.stateRef.el, {
                type: "doughnut",
                data: {
                    labels: legend.map((l) => l.label),
                    datasets: [{
                        data: legend.map((l) => l.count),
                        backgroundColor: legend.map((l) => l.color),
                        borderColor: "#ffffff",
                        borderWidth: 2,
                    }],
                },
                options: {
                    cutout: "70%",
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const l = legend[ctx.dataIndex];
                                    return ` ${l.label}: ${l.count} việc (${l.pct}%)`;
                                },
                            },
                        },
                    },
                },
            }));
        }
        if (this.weeklyRef.el) {
            this.charts.push(new Chart(this.weeklyRef.el, {
                type: "line",
                data: {
                    labels: ["Tuần 1", "Tuần 2", "Tuần 3", "Tuần 4", "Tuần 5"],
                    datasets: [{
                        label: "% hoàn thành",
                        data: this.weekly,
                        borderColor: "#16a34a",
                        backgroundColor: "rgba(34, 197, 94, 0.15)",
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 4,
                        pointBackgroundColor: "#16a34a",
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            ticks: { stepSize: 20, callback: (v) => `${v}%`, color: "#64748b" },
                            grid: { color: "#eef2f7" },
                        },
                        x: { ticks: { color: "#64748b" }, grid: { display: false } },
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: (ctx) => ` ${ctx.parsed.y}% hoàn thành` } },
                    },
                },
            }));
        }
        if (this.evalRef.el) {
            const score = Math.max(0, Math.min(100, this.evaluation.score));
            this.charts.push(new Chart(this.evalRef.el, {
                type: "doughnut",
                data: {
                    labels: ["Hiệu suất", ""],
                    datasets: [{
                        data: [score, 100 - score],
                        backgroundColor: ["#16a34a", "#e8efe9"],
                        borderWidth: 0,
                        cutout: "78%",
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                },
            }));
        }
    }

    get shellActiveNav() {
        return "kho_report";
    }

    get params() {
        return {
            year: Number(this.state.year),
            month: Number(this.state.month),
            team_id: Number(this.state.teamId) || false,
            employee_id: Number(this.state.employeeId) || false,
        };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_kho_report", [], this.params);
            this.state.message = data.message || false;
            this.state.teams = data.teams || [];
            this.state.teamId = data.team_id || 0;
            this.state.teamName = data.team_name || "";
            this.state.teamDept = data.team_dept || "";
            this.state.employees = data.employees || [];
            this.state.employeeId = data.employee_id || 0;
            this.state.canPick = Boolean(data.can_pick_employee);
            this.state.showEmployee = Boolean(data.show_employee);
            this.state.rows = data.rows || [];
            this.state.evalTiers = data.eval_tiers || [];
            this.state.canExport = !data.report_perm || data.report_perm.export !== false;
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được báo cáo.");
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    get title() {
        return "BÁO CÁO CÔNG VIỆC";
    }

    /** Dòng phụ: nhân viên đang xem · phòng ban của Team. */
    get subLine() {
        const emp = this.state.employees.find((e) => e.id === this.state.employeeId);
        const who = emp ? emp.name : "Tất cả nhân viên";
        return [who, this.state.teamDept].filter(Boolean).join(" · ");
    }

    /** Nhóm dòng theo hạng mục (giữ thứ tự I, II, III…). */
    get groups() {
        const out = [];
        const byKey = {};
        for (const r of this.state.rows) {
            const key = r.category || "—";
            if (!byKey[key]) {
                byKey[key] = { key, label: key, rows: [], minutes: 0, pass: 0, average: 0, fail: 0 };
                out.push(byKey[key]);
            }
            const g = byKey[key];
            g.rows.push(r);
            g.minutes += Number(r.minutes) || 0;
            const k = { "Đạt": "pass", "Trung bình": "average", "Không đạt": "fail" }[r.rating];
            if (k) {
                g[k] += 1;
            }
        }
        return out;
    }

    isOpen(group) {
        return !this.state.closed[group.key];
    }

    toggleGroup(group) {
        this.state.closed[group.key] = this.isOpen(group);
    }

    get allOpen() {
        return this.groups.every((g) => this.isOpen(g));
    }

    toggleAll() {
        const close = this.allOpen;
        const closed = {};
        if (close) {
            for (const g of this.groups) {
                closed[g.key] = true;
            }
        }
        this.state.closed = closed;
    }

    get totalMinutes() {
        return this.state.rows.reduce((s, r) => s + (Number(r.minutes) || 0), 0);
    }

    get ratingCount() {
        const out = { pass: 0, average: 0, fail: 0, none: 0 };
        for (const r of this.state.rows) {
            const k = { "Đạt": "pass", "Trung bình": "average", "Không đạt": "fail" }[r.rating] || "none";
            out[k] += 1;
        }
        return out;
    }

    ratingClass(label) {
        const k = { "Đạt": "is-pass", "Trung bình": "is-average", "Không đạt": "is-fail" }[label];
        return `o_dkr_rate ${k || ""}`;
    }

    async onFilter(field, ev) {
        this.state[field] = Number(ev.target.value) || 0;
        if (field === "teamId") {
            this.state.employeeId = 0;
        }
        await this.load();
    }

    async onExport() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task", "export_kho_report_excel", [], this.params);
            const bin = atob(res.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const url = URL.createObjectURL(new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }));
            const a = document.createElement("a");
            a.href = url;
            a.download = res.filename || "bao_cao_nv_kho.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_kho_report", DailyWorkKhoReport);
