/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Màu xếp loại (cùng quy ước Kiểm tra CV): Đạt · Trung bình · Không đạt · Chưa đánh giá. */
const RATING_META = [
    { key: "pass", label: "Đạt", color: "#22c55e" },
    { key: "average", label: "Trung bình", color: "#f59e0b" },
    { key: "fail", label: "Không đạt", color: "#ef4444" },
    { key: "none", label: "Chưa đánh giá", color: "#94a3b8" },
];
const LABEL_TO_KEY = { "Đạt": "pass", "Trung bình": "average", "Không đạt": "fail" };

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
        this.ratingRef = useRef("ratingChart");
        this.perfRef = useRef("perfChart");
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

    // ------------------------------------------------------------ biểu đồ
    /** Đếm theo xếp loại (Đạt / Trung bình / Không đạt / Chưa đánh giá). */
    get ratingLegend() {
        const counts = { pass: 0, average: 0, fail: 0, none: 0 };
        for (const r of this.state.rows) {
            counts[LABEL_TO_KEY[r.rating] || "none"] += 1;
        }
        const total = this.state.rows.length || 0;
        return RATING_META.map((m) => ({
            ...m,
            count: counts[m.key],
            pct: total ? Math.round((counts[m.key] * 1000) / total) / 10 : 0,
        }));
    }

    /** Đánh giá hiệu suất tháng — giống Báo cáo cá nhân: % QL đánh giá TB trên MỌI việc
     * (việc chưa đánh giá tính 0%); xếp loại theo Cài đặt → Xếp loại đạt. */
    get perf() {
        const rows = this.state.rows;
        const total = rows.length;
        const sum = rows.reduce((s, r) => s + (r.evaluated ? Number(r.eval_percent) || 0 : 0), 0);
        const score = total ? Math.round((sum / total) * 10) / 10 : 0;
        return {
            score,
            total,
            done: rows.filter((r) => r.is_done).length,
            overdue: rows.filter((r) => r.is_overdue).length,
            hours: Math.round((this.totalMinutes / 60) * 10) / 10,
            label: total ? this.rateEval(score) : "—",
            stars: score ? Math.min(5, Math.round((score / 20) * 2) / 2) : 0,
        };
    }

    get starList() {
        const stars = this.perf.stars;
        return [1, 2, 3, 4, 5].map((i) => (stars >= i ? "full" : stars >= i - 0.5 ? "half" : "empty"));
    }

    rateEval(pct) {
        const tiers = [...(this.state.evalTiers || [])].sort((a, b) => b.from_percent - a.from_percent);
        const hit = tiers.find((t) => pct >= t.from_percent) || tiers[tiers.length - 1];
        return hit ? hit.name : "";
    }

    perfClass(label) {
        const k = { "Đạt": "is-pass", "Trung bình": "is-average", "Không đạt": "is-fail" }[label];
        return `o_dkr_perf_label ${k || ""}`;
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
        if (this.ratingRef.el) {
            const data = this.ratingLegend.filter((l) => l.count);
            this.charts.push(new Chart(this.ratingRef.el, {
                type: "doughnut",
                data: {
                    labels: data.map((l) => l.label),
                    datasets: [{
                        data: data.map((l) => l.count),
                        backgroundColor: data.map((l) => l.color),
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
                                    const l = data[ctx.dataIndex];
                                    return ` ${l.label}: ${l.count} việc (${l.pct}%)`;
                                },
                            },
                        },
                    },
                },
            }));
        }
        if (this.perfRef.el) {
            const score = Math.max(0, Math.min(100, this.perf.score));
            this.charts.push(new Chart(this.perfRef.el, {
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
