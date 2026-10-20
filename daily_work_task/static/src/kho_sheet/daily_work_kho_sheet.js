/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

const WEEKDAYS = ["CN", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"];
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
            canWrite: false,
            message: false,
        });
        onWillStart(() => this.load());
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
        return `${fmtDate(iso)} (${WEEKDAYS[parseIso(iso).getDay()]})`;
    }

    fmt(iso) {
        return fmtDate(iso);
    }

    // ------------------------------------------------------------ chỉ số
    get kpi() {
        const rows = this.state.rows;
        const total = rows.length;
        const count = (k) => rows.filter((r) => r.state === k).length;
        const pct = (n) => (total ? Math.round((n * 1000) / total) / 10 : 0);
        const done = count("done");
        const doing = count("in_progress");
        const todo = count("not_started");
        const hours = rows.reduce((s, r) => s + this.hoursOf(r), 0);
        return {
            total,
            done,
            doing,
            todo,
            donePct: pct(done),
            doingPct: pct(doing),
            todoPct: pct(todo),
            hours: Math.round(hours * 10) / 10,
        };
    }

    /** Tổng TG (giờ) = Giờ ra − Giờ vào (qua nửa đêm → +24h). */
    hoursOf(row) {
        if (!row.time_in || !row.time_out) {
            return 0;
        }
        const toH = (t) => {
            const [h, m] = t.split(":").map(Number);
            return h + m / 60;
        };
        let diff = toH(row.time_out) - toH(row.time_in);
        if (diff < 0) {
            diff += 24;
        }
        return Math.round(diff * 100) / 100;
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
        this.state.kinds = data.kinds || [];
        this.state.categories = data.categories || [];
        this.state.me = data.me || "";
        this.state.states = data.states || [];
        this.state.canWrite = Boolean(data.can_write);
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
            time_in: "",
            time_out: "",
            hours: 0,
            state: "not_started",
            controller: "",
            note: "",
        });
        this.state.editing = true;
        this.state.dirty = true;
    }

    onField(row, field, ev) {
        let value = ev.target.value;
        if (field === "work_group_id") {
            value = Number(value) || false;
            row.category = (this.state.categories.find((c) => c.id === value) || {}).name || "";
        }
        row[field] = value;
        if (field === "time_in" || field === "time_out") {
            row.hours = this.hoursOf(row);
        }
        this.state.dirty = true;
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
                    time_in: r.time_in || false,
                    time_out: r.time_out || false,
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
