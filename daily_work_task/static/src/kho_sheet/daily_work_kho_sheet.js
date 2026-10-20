/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useState } from "@odoo/owl";
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
            timePick: null,
            canWrite: false,
            message: false,
        });
        onWillStart(() => this.load());
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
        return this.state.editing ? 19 : 18;
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
