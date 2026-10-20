/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const pad = (n) => String(n).padStart(2, "0");
const fmtDate = (iso) => {
    if (!iso) {
        return "";
    }
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
};
const parseIso = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
};
let newSeq = 0;

/** Báo cáo CV NV Kho — bảng nhập tay theo tháng (giống mẫu Excel). */
export class DailyWorkKhoSheet extends Component {
    static template = "daily_work_task.DailyWorkKhoSheet";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            saving: false,
            editing: false,
            dirty: false,
            weekNo: 0, // 0 = cả tháng; bấm ô Tuần để lọc
            openGroups: {}, // hạng mục đang mở (group giống Danh sách công việc)
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            teamId: 0,
            teamName: "",
            teams: [],
            rows: [],
            deleted: [],
            people: [],
            kinds: [],
            states: [],
            categories: [],
            me: "",
            meJob: "",
            wholeTeam: false,
            canExport: false,
            exporting: false,
            meDept: "",
            timePick: null,
            canWrite: false,
            message: false,
        });
        // 3 biểu đồ xếp loại QL đánh giá: Đạt / Trung bình / Không đạt (số lượng việc)
        this.stateChartRef = useRef("stateChart");
        this.rateChartRef = useRef("rateChart");
        this.perfChartRef = useRef("perfChart");
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                this.renderRateCharts();
            },
            () => {
                const r = this.rateStats;
                const t = this.stateStats;
                return [this.state.loading, r.pass, r.average, r.fail, r.rated,
                    t.done, t.doing, t.todo, t.overdue,
                    this.perfStats.hours, this.perfStats.self, this.perfStats.manager];
            }
        );
        onWillUnmount(() => this.destroyCharts());
        // Mở danh sách giờ → cuộn tới mốc đang chọn / gần nhất
        useEffect(
            () => {
                if (this.state.timePick) {
                    const near = document.querySelector(".o_dks_time_list .is-near");
                    near?.scrollIntoView({ block: "center" });
                }
            },
            () => [this.state.timePick && this.state.timePick.key]
        );
        // Tiêu đề 2 hàng cố định: hàng 2 (% Hoàn thành…) dính ngay dưới hàng «QUẢN LÝ ĐÁNH GIÁ»
        useEffect(() => {
            const wrap = document.querySelector(".o_daily_work_kho_sheet .o_dks_table_wrap");
            const th = wrap?.querySelector("th.o_dks_th_eval_group");
            if (th) {
                wrap.style.setProperty("--dks-head1", `${th.getBoundingClientRect().height}px`);
            }
        });
    }

    /** Số lượng việc theo xếp loại QL (Kiểm tra CV) — theo Tuần đang lọc. */
    get rateStats() {
        const out = { pass: 0, average: 0, fail: 0 };
        let unrated = 0;
        for (const r of this.visibleRows) {
            const k = r.eval && r.eval.rating;
            if (k && k in out) {
                out[k] += 1;
            } else if (r.linked) {
                unrated += 1;
            }
        }
        const rated = out.pass + out.average + out.fail;
        const pct = (n) => (rated ? Math.round((n * 1000) / rated) / 10 : 0);
        return { ...out, rated, unrated, passPct: pct(out.pass), averagePct: pct(out.average), failPct: pct(out.fail) };
    }

    /** Bảng xếp loại (bên phải biểu đồ 2). */
    get rateRows() {
        const s = this.rateStats;
        return [
            { key: "pass", label: "Đạt", count: s.pass, pct: s.passPct },
            { key: "average", label: "Trung bình", count: s.average, pct: s.averagePct },
            { key: "fail", label: "Không đạt", count: s.fail, pct: s.failPct },
        ];
    }

    /** Biểu đồ 1: Hoàn thành / Đang thực hiện / Chưa bắt đầu / Quá hạn (chưa xong & quá Deadline). */
    get stateStats() {
        const today = new Date();
        const todayIso = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
        const out = { done: 0, doing: 0, todo: 0, overdue: 0 };
        for (const r of this.visibleRows) {
            if (r.state === "done") {
                out.done += 1;
            } else if (r.deadline && r.deadline < todayIso) {
                out.overdue += 1;
            } else if (r.state === "in_progress") {
                out.doing += 1;
            } else {
                out.todo += 1;
            }
        }
        out.total = out.done + out.doing + out.todo + out.overdue;
        return out;
    }

    get stateLegend() {
        const s = this.stateStats;
        const pct = (n) => (s.total ? Math.round((n * 1000) / s.total) / 10 : 0);
        return [
            { key: "done", label: "Hoàn thành", count: s.done, pct: pct(s.done), color: "#16a34a" },
            { key: "doing", label: "Đang thực hiện", count: s.doing, pct: pct(s.doing), color: "#f59e0b" },
            { key: "todo", label: "Chưa bắt đầu", count: s.todo, pct: pct(s.todo), color: "#94a3b8" },
            { key: "overdue", label: "Quá hạn", count: s.overdue, pct: pct(s.overdue), color: "#dc2626" },
        ];
    }

    /** Biểu đồ 3: Tổng thời gian · Hiệu suất NV tự đánh giá · Hiệu suất QL đánh giá (theo Tuần đang lọc). */
    get perfStats() {
        const rows = this.visibleRows;
        const round1 = (v) => Math.round(v * 10) / 10;
        const hours = round1(rows.reduce((s, r) => s + this.hoursOf(r), 0));
        // NV tự đánh giá = TB «% hoàn thành CV» nhân viên nhập ở Danh sách công việc
        const self = rows.length ? round1(rows.reduce((s, r) => s + (Number(r.completion) || 0), 0) / rows.length) : 0;
        // QL đánh giá = TB % Hoàn thành QL chấm trên Kiểm tra CV (việc chưa đánh giá = 0%) — giống Hiệu suất
        const manager = this.kpi.efficiency || 0;
        return { hours, self, manager, gap: round1(manager - self) };
    }

    get perfRows() {
        const s = this.perfStats;
        return [
            { key: "hours", label: "Tổng thời gian (giờ)", value: `${String(s.hours).replace(".", ",")} giờ`,
              note: "Tổng số giờ nhân viên đã ghi nhận" },
            { key: "self", label: "Hiệu suất (NV tự đánh giá)", value: this.fmtPct(s.self),
              note: "TB % hoàn thành CV nhân viên nhập" },
            { key: "manager", label: "Quản lý đánh giá hiệu suất", value: this.fmtPct(s.manager),
              note: "TB % hoàn thành QL chấm (Kiểm tra CV)" },
        ];
    }

    get perfHoursLabel() {
        return String(this.perfStats.hours).replace(".", ",");
    }

    get perfGapText() {
        const g = this.perfStats.gap;
        if (!g) {
            return "Quản lý đánh giá bằng mức nhân viên tự đánh giá";
        }
        const v = String(Math.abs(g)).replace(".", ",");
        return g < 0
            ? `Quản lý đánh giá thấp hơn nhân viên tự đánh giá ${v} điểm %`
            : `Quản lý đánh giá cao hơn nhân viên tự đánh giá ${v} điểm %`;
    }

    _perfChart(el) {
        const Chart = window.Chart;
        const s = this.perfStats;
        const ring = (v, color) => ({
            data: [v, Math.max(100 - v, 0)],
            backgroundColor: [color, "#e5e7eb"],
            borderWidth: 0,
        });
        return new Chart(el, {
            type: "doughnut",
            data: {
                labels: ["Đạt được", "Còn lại"],
                datasets: [ring(s.self, "#2563eb"), ring(s.manager, "#16a34a")],
            },
            options: {
                cutout: "56%",
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 300 },
                layout: { padding: 6 },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (c) => `${c.datasetIndex ? "QL đánh giá" : "NV tự đánh giá"}: ${c.raw}%`,
                        },
                        filter: (c) => c.dataIndex === 0,
                    },
                },
            },
        });
    }

    fmtPct(v) {
        return `${String(v).replace(".", ",")}%`;
    }

    destroyCharts() {
        for (const c of this.charts || []) {
            c.destroy();
        }
        this.charts = [];
    }

    /** Plugin vẽ nhãn ngoài vòng (số lượng + %) có đường chỉ — giống hình mẫu. */
    _calloutPlugin(items) {
        return {
            id: "dksCallout",
            afterDraw(chart) {
                const meta = chart.getDatasetMeta(0);
                const ctx = chart.ctx;
                const total = items.reduce((s, it) => s + it.count, 0);
                if (!total) {
                    return;
                }
                ctx.save();
                meta.data.forEach((arc, i) => {
                    const it = items[i];
                    if (!it || !it.count) {
                        return;
                    }
                    const angle = (arc.startAngle + arc.endAngle) / 2;
                    const cos = Math.cos(angle);
                    const sin = Math.sin(angle);
                    const r = arc.outerRadius;
                    const x0 = arc.x + cos * r;
                    const y0 = arc.y + sin * r;
                    const x1 = arc.x + cos * (r + 14);
                    const y1 = arc.y + sin * (r + 14);
                    const right = cos >= 0;
                    const x2 = x1 + (right ? 16 : -16);
                    ctx.strokeStyle = it.color;
                    ctx.fillStyle = it.color;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(x0, y0);
                    ctx.lineTo(x1, y1);
                    ctx.lineTo(x2, y1);
                    ctx.stroke();
                    ctx.beginPath();
                    ctx.arc(x2, y1, 2, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.textAlign = right ? "left" : "right";
                    ctx.textBaseline = "bottom";
                    ctx.font = "800 17px sans-serif";
                    const tx = x2 + (right ? 4 : -4);
                    ctx.fillText(String(it.count), tx, y1 + 2);
                    ctx.font = "600 11px sans-serif";
                    ctx.textBaseline = "top";
                    ctx.fillText(`(${String(it.pct).replace(".", ",")}%)`, tx, y1 + 4);
                });
                ctx.restore();
            },
        };
    }

    _doughnut(el, items) {
        const Chart = window.Chart;
        const total = items.reduce((s, it) => s + it.count, 0);
        return new Chart(el, {
            type: "doughnut",
            data: {
                labels: items.map((it) => it.label),
                datasets: [{
                    data: total ? items.map((it) => it.count) : [1],
                    backgroundColor: total ? items.map((it) => it.color) : ["#e5e7eb"],
                    borderWidth: total ? 1 : 0,
                    borderColor: "#ffffff",
                }],
            },
            options: {
                cutout: "62%",
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 300 },
                layout: { padding: { top: 26, bottom: 26, left: 52, right: 52 } },
                plugins: { legend: { display: false }, tooltip: { enabled: Boolean(total) } },
            },
            plugins: [this._calloutPlugin(items)],
        });
    }

    renderRateCharts() {
        this.destroyCharts();
        if (!window.Chart || this.state.loading) {
            return;
        }
        if (this.stateChartRef.el) {
            this.charts.push(this._doughnut(this.stateChartRef.el, this.stateLegend));
        }
        if (this.rateChartRef.el) {
            const colors = { pass: "#16a34a", average: "#f59e0b", fail: "#dc2626" };
            const items = this.rateRows.map((r) => ({ ...r, color: colors[r.key] }));
            this.charts.push(this._doughnut(this.rateChartRef.el, items));
        }
        if (this.perfChartRef.el) {
            this.charts.push(this._perfChart(this.perfChartRef.el));
        }
    }

    get shellActiveNav() {
        return "kho_sheet";
    }

    // ------------------------------------------------------------ tháng
    get monthOptions() {
        const out = [];
        const now = new Date();
        for (let y = now.getFullYear() - 1; y <= now.getFullYear() + 1; y++) {
            for (let m = 1; m <= 12; m++) {
                out.push({ key: `${y}-${m}`, label: `${pad(m)}/${y}`, year: y, month: m });
            }
        }
        return out;
    }

    get monthNums() {
        return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    }

    get yearNums() {
        const y = new Date().getFullYear();
        return [y - 1, y, y + 1];
    }

    /** Dòng phụ dưới «Họ và tên»: chức danh · phòng ban. */
    get meSub() {
        return [this.state.meJob, this.state.meDept].filter(Boolean).join(" · ");
    }

    /** Đổi Tháng / Năm trên thanh công cụ (giống Báo cáo cá nhân). */
    async onPeriod(field, ev) {
        const value = Number(ev.target.value);
        if (!this._confirmDiscard()) {
            ev.target.value = String(this.state[field]);
            return;
        }
        this.state[field] = value;
        this.state.weekNo = 0;
        await this.load();
    }

    /** Xuất Excel (A4 ngang, tự canh lề) — theo tháng / Team / Tuần đang lọc. */
    async onExport() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task.kho.sheet.line", "export_kho_sheet_excel", [], {
                year: this.state.year,
                month: this.state.month,
                team_id: this.state.teamId || false,
                week_no: this.state.weekNo || 0,
            });
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
            a.download = res.filename || "bao_cao_cv_nv_kho.xlsx";
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

    async onRefresh() {
        if (!this._confirmDiscard()) {
            return;
        }
        await this.load();
    }

    get monthKey() {
        return `${this.state.year}-${this.state.month}`;
    }

    get monthLabel() {
        return `${pad(this.state.month)}/${this.state.year}`;
    }

    /** Tuần trong tháng: Thứ 2 → Chủ nhật (tuần đầu / cuối cắt theo tháng). */
    get weeks() {
        const { year, month } = this.state;
        const last = new Date(year, month, 0).getDate();
        const weeks = [];
        let start = 1;
        while (start <= last) {
            const dow = new Date(year, month - 1, start).getDay(); // 0 = CN
            const toSunday = dow === 0 ? 0 : 7 - dow;
            const end = Math.min(last, start + toSunday);
            weeks.push({
                no: weeks.length + 1,
                start,
                end,
                label: `${pad(start)}/${pad(month)} – ${pad(end)}/${pad(month)}/${year}`,
                days: end - start + 1,
            });
            start = end + 1;
        }
        return weeks;
    }

    weekOf(iso) {
        if (!iso) {
            return "";
        }
        const day = parseIso(iso).getDate();
        const w = this.weeks.find((x) => day >= x.start && day <= x.end);
        return w ? `Tuần ${w.no}` : "";
    }

    dayLabel(iso) {
        if (!iso) {
            return "";
        }
        return `${fmtDate(iso)} ${WEEKDAYS[parseIso(iso).getDay()]}`;
    }

    fmt(iso) {
        return fmtDate(iso);
    }

    /** Bấm ô Tuần → lọc danh sách theo tuần; bấm lại → cả tháng. */
    onWeek(no) {
        this.state.weekNo = this.state.weekNo === no ? 0 : no;
    }

    /** Group theo Hạng mục (giống Danh sách công việc): số việc · giờ · % hoàn thành TB. */
    get groups() {
        const map = new Map();
        for (const r of this.visibleRows) {
            const label = this.categoryLabel(r) || "";
            const key = label || "__none__";
            if (!map.has(key)) {
                map.set(key, { key, label: label || "Chưa có hạng mục", rows: [] });
            }
            map.get(key).rows.push(r);
        }
        const out = [...map.values()].map((g) => {
            const hours = g.rows.reduce((s, r) => s + this.hoursOf(r), 0);
            const pct = g.rows.reduce((s, r) => s + (Number(r.completion) || 0), 0);
            return {
                ...g,
                count: g.rows.length,
                hours: Math.round(hours * 10) / 10,
                avg: g.rows.length ? Math.round((pct * 10) / g.rows.length) / 10 : 0,
            };
        });
        out.sort((a, b) => {
            if (a.key === "__none__" || b.key === "__none__") {
                return a.key === "__none__" ? 1 : -1;
            }
            return a.label.localeCompare(b.label, "vi");
        });
        return out;
    }

    /** Tổng % hoàn thành công việc trong tháng (AVERAGE các hạng mục). */
    get groupsAvg() {
        const gs = this.groups;
        if (!gs.length) {
            return 0;
        }
        return Math.round((gs.reduce((s, g) => s + g.avg, 0) * 10) / gs.length) / 10;
    }

    isGroupOpen(g) {
        return this.state.editing || Boolean(this.state.openGroups[g.key]);
    }

    toggleGroup(g) {
        this.state.openGroups[g.key] = !this.state.openGroups[g.key];
    }

    get colCount() {
        return this.state.editing ? 16 : 15;
    }

    /** Dòng hiển thị theo tuần đang lọc (dòng mới chưa lưu luôn hiện để nhập). */
    get visibleRows() {
        const w = this.state.weekNo && this.weeks.find((x) => x.no === this.state.weekNo);
        if (!w) {
            return this.state.rows;
        }
        return this.state.rows.filter((r) => {
            if (!r.id) {
                return true;
            }
            if (!r.date) {
                return false;
            }
            const day = parseIso(r.date).getDate();
            return day >= w.start && day <= w.end;
        });
    }

    // ------------------------------------------------------------ chỉ số
    get kpi() {
        const rows = this.visibleRows;
        const total = rows.length;
        const count = (k) => rows.filter((r) => r.state === k).length;
        const pct = (n) => (total ? Math.round((n * 1000) / total) / 10 : 0);
        const done = count("done");
        const doing = count("in_progress");
        const todo = count("not_started");
        const hours = rows.reduce((s, r) => s + this.hoursOf(r), 0);
        // HIỆU SUẤT (giống Báo cáo cá nhân): TB % Hoàn thành do QL đánh giá trên Kiểm tra CV,
        // tính trên các công việc (dòng liên kết); việc chưa đánh giá = 0%
        const tasks = rows.filter((r) => r.linked);
        const evalSum = tasks.reduce((s, r) => s + (Number(r.eval && r.eval.percent) || 0), 0);
        const efficiency = tasks.length ? Math.round((evalSum * 10) / tasks.length) / 10 : 0;
        return {
            total,
            efficiency,
            done,
            doing,
            todo,
            donePct: pct(done),
            doingPct: pct(doing),
            todoPct: pct(todo),
            hours: Math.round(hours * 10) / 10,
        };
    }

    /** Tổng TG (giờ): dòng phân công lấy theo Danh sách công việc, dòng nhập tay gõ trực tiếp. */
    hoursOf(row) {
        return Math.round((Number(row.hours) || 0) * 100) / 100;
    }

    categoryLabel(row) {
        const c = this.state.categories.find((x) => x.id === row.work_group_id);
        return c ? c.name : row.category || "";
    }

    /** Ô chọn Hạng mục: hạng mục đã phân cho user + hạng mục đang lưu trên dòng (nếu khác). */
    categoryOptions(row) {
        const opts = [...this.state.categories];
        if (row.work_group_id && !opts.some((c) => c.id === row.work_group_id)) {
            opts.push({ id: row.work_group_id, name: row.category || "" });
        }
        return opts;
    }

    stateLabel(key) {
        return (this.state.states.find((k) => k.key === key) || {}).label || "";
    }

    stateIcon(key) {
        return { done: "fa-check-circle", in_progress: "fa-clock-o", not_started: "fa-pause-circle" }[key] || "fa-circle-o";
    }

    // ------------------------------------------------------------ dữ liệu
    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task.kho.sheet.line", "get_kho_sheet", [], {
                year: this.state.year,
                month: this.state.month,
                team_id: this.state.teamId || false,
            });
            this.applyData(data);
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được báo cáo.");
        } finally {
            this.state.loading = false;
        }
    }

    applyData(data) {
        this.state.message = false;
        this.state.year = data.year;
        this.state.month = data.month;
        this.state.teams = data.teams || [];
        this.state.teamId = data.team_id || 0;
        this.state.teamName = data.team_name || "";
        this.state.rows = (data.rows || []).map((r) => ({ ...r, key: `id-${r.id}` }));
        this.state.people = data.people || [];
        this.state.meJob = data.me_job || "";
        this.state.wholeTeam = Boolean(data.whole_team);
        this.state.meDept = data.me_dept || "";
        this.state.kinds = data.kinds || [];
        this.state.categories = data.categories || [];
        this.state.me = data.me || "";
        this.state.states = data.states || [];
        this.state.canWrite = Boolean(data.can_write);
        this.state.canExport = Boolean(data.can_export);
        this.state.deleted = [];
        this.state.dirty = false;
        this.state.editing = false;
    }

    _confirmDiscard() {
        return !this.state.dirty || window.confirm(_t("Có thay đổi chưa lưu. Bỏ thay đổi?"));
    }

    async onMonth(ev) {
        if (!this._confirmDiscard()) {
            ev.target.value = this.monthKey;
            return;
        }
        const [y, m] = ev.target.value.split("-").map(Number);
        this.state.year = y;
        this.state.month = m;
        this.state.weekNo = 0;
        await this.load();
    }

    async onTeam(ev) {
        if (!this._confirmDiscard()) {
            ev.target.value = String(this.state.teamId);
            return;
        }
        this.state.teamId = Number(ev.target.value) || 0;
        await this.load();
    }

    // ------------------------------------------------------------ sửa
    onEdit() {
        this.state.editing = true;
    }

    async onCancel() {
        if (!this._confirmDiscard()) {
            return;
        }
        await this.load();
    }

    onAdd() {
        const today = new Date();
        const inMonth = today.getFullYear() === this.state.year && today.getMonth() + 1 === this.state.month;
        const day = inMonth ? today.getDate() : 1;
        const iso = `${this.state.year}-${pad(this.state.month)}-${pad(day)}`;
        this.state.rows.push({
            key: `new-${Date.now()}-${newSeq++}`,
            id: false,
            date: iso,
            kind: "daily",
            work_group_id: (this.state.categories[0] || {}).id || false,
            category: (this.state.categories[0] || {}).name || "",
            name: "",
            responsible: this.state.me,
            date_start: iso,
            deadline: iso,
            hours: 0,
            state: "not_started",
            controller: "",
            note: "",
        });
        this.state.editing = true;
        this.state.dirty = true;
    }

    /** Ngày gõ tay dd/mm/yyyy (chấp nhận d/m/yyyy, d-m-yyyy, ddmmyyyy). */
    onDateText(row, ev, field = "date") {
        const raw = (ev.target.value || "").trim();
        if (!raw) {
            row[field] = "";
            this.state.dirty = true;
            return;
        }
        let m = raw.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/);
        if (!m && /^\d{8}$/.test(raw)) {
            m = [raw, raw.slice(0, 2), raw.slice(2, 4), raw.slice(4)];
        }
        const d = m && Number(m[1]);
        const mo = m && Number(m[2]);
        const y = m && Number(m[3]);
        const valid = m && mo >= 1 && mo <= 12 && d >= 1 && d <= new Date(y, mo, 0).getDate();
        if (!valid) {
            this.notification.add(_t("Ngày không hợp lệ — nhập theo dạng dd/mm/yyyy."), { type: "warning" });
            ev.target.value = fmtDate(row[field]);
            return;
        }
        if (field === "date" && (y !== this.state.year || mo !== this.state.month)) {
            this.notification.add(`Ngày phải thuộc tháng ${this.monthLabel}.`, { type: "warning" });
            ev.target.value = fmtDate(row.date);
            return;
        }
        row[field] = `${y}-${pad(mo)}-${pad(d)}`;
        ev.target.value = fmtDate(row[field]);
        this._syncDay(row, field);
        this.state.dirty = true;
    }

    openPicker(ev) {
        const picker = ev.currentTarget.parentElement.querySelector(".o_dks_date_picker");
        if (picker?.showPicker) {
            picker.showPicker();
        } else {
            picker?.click();
        }
    }

    // ---- Chọn giờ (combobox: danh sách mốc 30 phút + gõ tay) ----
    get timeSlots() {
        const out = [];
        for (let h = 0; h < 24; h++) {
            out.push(`${pad(h)}:00`, `${pad(h)}:30`);
        }
        return out;
    }

    get timePickValue() {
        const tp = this.state.timePick;
        if (!tp) {
            return "";
        }
        const row = this.state.rows.find((r) => r.key === tp.rowKey);
        return (row && row[tp.field]) || "";
    }

    /** Mốc gần nhất với giờ đang có (chưa có → giờ hiện tại). */
    get timePickNear() {
        let v = this.timePickValue;
        if (!v) {
            const now = new Date();
            v = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
        }
        const [h, m] = v.split(":").map(Number);
        const mins = Math.round((h * 60 + m) / 30) * 30;
        const n = Math.min(mins, 23 * 60 + 30);
        return `${pad(Math.floor(n / 60))}:${pad(n % 60)}`;
    }

    get timeListStyle() {
        const tp = this.state.timePick;
        return tp ? `top:${tp.top}px;left:${tp.left}px;width:${tp.width}px;` : "";
    }

    openTime(ev, row, field) {
        const rect = ev.target.getBoundingClientRect();
        const below = window.innerHeight - rect.bottom;
        const height = 260;
        this.state.timePick = {
            key: `${row.key}-${field}`,
            rowKey: row.key,
            field,
            left: rect.left,
            width: Math.max(rect.width, 110),
            top: below < height + 8 ? Math.max(8, rect.top - height - 2) : rect.bottom + 2,
        };
    }

    closeTime() {
        this.state.timePick = null;
    }

    pickTime(slot) {
        const tp = this.state.timePick;
        const row = tp && this.state.rows.find((r) => r.key === tp.rowKey);
        if (row) {
            row[tp.field] = slot;
            row.hours = this.hoursOf(row);
            this.state.dirty = true;
        }
        this.closeTime();
    }

    /** Esc đóng danh sách; Enter / Tab chấp nhận giờ đang gõ. */
    onTimeKey(ev, row, field) {
        if (ev.key === "Escape") {
            this.closeTime();
        } else if (ev.key === "Enter") {
            ev.target.blur();
        }
    }

    /** Giờ 24h gõ tay: 8 → 08:00 · 830 → 08:30 · 8h30 / 8.30 / 8:30 → 08:30. */
    onTimeText(row, field, ev) {
        const raw = (ev.target.value || "").trim().toLowerCase();
        let value = "";
        if (raw) {
            let h;
            let mi = 0;
            const m = raw.match(/^(\d{1,2})\s*[:h.]\s*(\d{1,2})?$/);
            if (m) {
                h = Number(m[1]);
                mi = Number(m[2] || 0);
            } else if (/^\d{1,4}$/.test(raw)) {
                if (raw.length <= 2) {
                    h = Number(raw);
                } else {
                    h = Number(raw.slice(0, raw.length - 2));
                    mi = Number(raw.slice(-2));
                }
            }
            if (h === undefined || h > 23 || mi > 59) {
                this.notification.add(_t("Giờ không hợp lệ — nhập dạng 24h HH:MM (vd 08:00, 17:30)."), { type: "warning" });
                ev.target.value = row[field] || "";
                return;
            }
            value = `${pad(h)}:${pad(mi)}`;
        }
        row[field] = value;
        ev.target.value = value;
        row.hours = this.hoursOf(row);
        this.state.dirty = true;
    }

    onField(row, field, ev) {
        let value = ev.target.value;
        if (field === "work_group_id") {
            value = Number(value) || false;
            row.category = (this.state.categories.find((c) => c.id === value) || {}).name || "";
        }
        if (field === "hours") {
            value = Math.max(Number(String(value).replace(",", ".")) || 0, 0);
        }
        row[field] = value;
        this._syncDay(row, field);
        this.state.dirty = true;
    }

    /** Bỏ cột «Ngày»: Ngày bắt đầu (thuộc tháng đang xem) quyết định Ngày / Tuần của dòng nhập tay. */
    _syncDay(row, field) {
        if (field !== "date_start" || !row.date_start) {
            return;
        }
        const d = parseIso(row.date_start);
        if (d.getFullYear() === this.state.year && d.getMonth() + 1 === this.state.month) {
            row.date = row.date_start;
        }
    }

    onRemove(row) {
        if (row.id) {
            this.state.deleted.push(row.id);
        }
        this.state.rows = this.state.rows.filter((r) => r.key !== row.key);
        this.state.dirty = true;
    }

    async onSave() {
        for (const r of this.state.rows) {
            if (!(r.name || "").trim()) {
                this.notification.add(_t("Vui lòng nhập Nội dung công việc cho mọi dòng."), { type: "warning" });
                return;
            }
        }
        this.state.saving = true;
        try {
            const data = await this.orm.call("daily.task.kho.sheet.line", "save_kho_sheet", [
                this.state.year,
                this.state.month,
                this.state.teamId || false,
                this.state.rows.map((r) => ({
                    id: r.id || false,
                    date: r.date || false,
                    kind: r.kind,
                    work_group_id: r.work_group_id || false,
                    name: r.name,
                    responsible: r.responsible,
                    date_start: r.date_start || false,
                    deadline: r.deadline || false,
                    hours: Number(r.hours) || 0,
                    state: r.state,
                    controller: r.controller,
                    note: r.note,
                })),
                this.state.deleted,
            ]);
            this.applyData(data);
            this.notification.add(_t("Đã lưu báo cáo công việc kho."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("daily_work_kho_sheet", DailyWorkKhoSheet);
