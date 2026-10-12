/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";
import { TeamTaskDialog } from "@daily_work_task/team_plan/team_task_dialog";

const EMPTY_NEW_LINE = () => ({
    name: "",
    category: "",
    date_start: "",
    deadline: "",
    plan_daily: false,
});

/** Plan công việc theo ngày của từng user — lấy từ bảng phân công (giống file PLAN TEAM). */
export class DailyWorkPlan extends Component {
    static template = "daily_work_task.DailyWorkPlan";
    static components = { DailyWorkAppShell, TeamTaskDialog };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const today = new Date();
        this.state = useState({
            loading: true,
            busy: false,
            year: today.getFullYear(),
            month: today.getMonth() + 1,
            userId: false,
            data: null,
            closedGroups: {},
            adding: false,
            teamAdding: false,
            newLine: EMPTY_NEW_LINE(),
            edit: null,
            picker: null,
            exporting: false,
            filterState: "",
        });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "plan";
    }

    get summary() {
        return this.state.data?.summary || { lines: 0, daily: 0, planned: 0, done: 0 };
    }

    get donePercent() {
        const s = this.summary;
        return s.planned ? Math.round((100 * s.done) / s.planned) : 0;
    }

    /** Số việc theo trạng thái của user (Hoàn thành / Đang thực hiện / Chưa bắt đầu / Trễ hạn). */
    statusCount(key) {
        const summary = this.state.data?.summary || {};
        if (key === "total") {
            return summary.task_total || 0;
        }
        return (summary.status || {})[key] || 0;
    }

    /** Số ô "x" trên lưới theo màu trạng thái (khớp đúng số ô đếm được trên bảng). */
    xCount(key) {
        let n = 0;
        for (const g of this.state.data?.groups || []) {
            for (const line of g.lines || []) {
                for (const cell of line.cells || []) {
                    const cls = cell.cls.split(" ");
                    if (!cls.includes("is-plan")) {
                        continue;
                    }
                    if (key === "total" || cls.includes(`st-${key}`)) {
                        n += 1;
                    }
                }
            }
        }
        return n;
    }

    get doneTaskPercent() {
        const total = this.statusCount("total");
        return total ? Math.round((100 * this.statusCount("done")) / total) : 0;
    }

    setFilter(stateKey) {
        this.state.filterState = this.state.filterState === stateKey ? "" : stateKey;
    }

    _rowMatches(line, stateKey) {
        if (line.state) {
            return line.state === stateKey;
        }
        // Việc lặp: khớp nếu có ngày mang trạng thái đó
        return (line.cells || []).some((c) => c.cls.split(" ").includes(`st-${stateKey}`));
    }

    /** Nhóm hạng mục sau khi lọc theo thẻ trạng thái đang chọn. */
    get visibleGroups() {
        const groups = this.state.data?.groups || [];
        const stateKey = this.state.filterState;
        if (!stateKey) {
            return groups;
        }
        return groups
            .map((g) => ({ ...g, lines: g.lines.filter((l) => this._rowMatches(l, stateKey)) }))
            .filter((g) => g.lines.length);
    }

    get canEditCells() {
        return Boolean(this.state.data?.can_edit_cells);
    }

    groupOpen(group) {
        return !this.state.closedGroups[group.code];
    }

    toggleGroup(group) {
        this.state.closedGroups = {
            ...this.state.closedGroups,
            [group.code]: this.groupOpen(group),
        };
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

    async onUser(ev) {
        this.state.userId = parseInt(ev.target.value) || false;
        await this.load();
    }

    _notifyError(e, fallback) {
        this.notification.add(e?.data?.message || fallback, { type: "danger" });
    }

    // ---- Chế độ xem: bấm tên công việc → khung chỉnh sửa → chỉ ghi khi bấm Lưu ----
    canOpen(line) {
        // Đã hoàn thành (x xanh) → không được chỉnh sửa
        if (line.team_locked && !line.can_edit_dates) {
            // Việc Plan tổng đã áp xuống: cá nhân không sửa nội dung / ô x
            return false;
        }
        return !line.locked && !line.readonly && Boolean(line.can_edit_dates || this.canEditCells);
    }

    _plannedDays(line) {
        const days = {};
        for (const cell of line.cells || []) {
            if (cell.cls.split(" ").includes("is-plan")) {
                days[cell.day] = true;
            }
        }
        return days;
    }

    openEdit(line) {
        if (!this.canOpen(line)) {
            return;
        }
        const days = this._plannedDays(line);
        // Việc lặp: ngày đã hoàn thành thì khóa
        const lockedDays = {};
        for (const cell of line.cells || []) {
            if (cell.cls.split(" ").includes("st-done")) {
                lockedDays[cell.day] = true;
            }
        }
        this.state.edit = {
            line,
            code: line.code,
            personal: Boolean(line.personal),
            plan_daily: Boolean(line.plan_daily),
            recurring: line.kind === "recurring",
            canEditInfo: Boolean(line.can_edit_dates),
            // Việc lặp: ô x theo lịch lặp — không bật/tắt tay
            canEditDays: this.canEditCells && line.kind !== "recurring" && !line.team_locked,
            name: line.name || "",
            start: line.start_iso || "",
            deadline: line.deadline_iso || "",
            days,
            origDays: { ...days },
            lockedDays,
        };
    }

    closeEdit() {
        this.state.edit = null;
        this.state.picker = null;
    }

    onModalKey(ev) {
        if (ev.key === "Escape") {
            this.closeEdit();
        } else if (ev.key === "Enter" && ev.target.tagName === "INPUT" && this.isEditDirty) {
            ev.preventDefault();
            this.saveEdit();
        }
    }

    get _infoChanged() {
        const e = this.state.edit;
        if (!e) {
            return false;
        }
        const l = e.line;
        return (
            e.name.trim() !== (l.name || "") ||
            e.start !== (l.start_iso || "") ||
            e.deadline !== (l.deadline_iso || "")
        );
    }

    get _daysChanged() {
        const e = this.state.edit;
        if (!e) {
            return false;
        }
        const keys = new Set([...Object.keys(e.days), ...Object.keys(e.origDays)]);
        return [...keys].some((k) => Boolean(e.days[k]) !== Boolean(e.origDays[k]));
    }

    get isEditDirty() {
        return this._infoChanged || this._daysChanged;
    }

    /** Dải ngày Ngày bắt đầu → Deadline trong tháng đang xem (việc lặp bỏ Chủ nhật). */
    _rangeDays(startIso, endIso, skipSunday) {
        const days = {};
        if (!startIso && !endIso) {
            return days;
        }
        let start = startIso || endIso;
        let end = endIso || startIso;
        if (end < start) {
            [start, end] = [end, start];
        }
        for (const d of this.state.data.days) {
            const iso = `${this.state.year}-${String(this.state.month).padStart(2, "0")}-${String(d.day).padStart(2, "0")}`;
            if (iso >= start && iso <= end && !(skipSunday && d.sunday)) {
                days[d.day] = true;
            }
        }
        return days;
    }

    onEditField(field, ev) {
        this._setEditField(field, ev.target.value || "");
    }

    _setEditField(field, value) {
        const e = this.state.edit;
        e[field] = value || "";
        if (field === "start" || field === "deadline") {
            // Đổi ngày → tính lại dải 'x' (xem trước, chưa ghi)
            e.days = this._rangeDays(e.start, e.deadline, e.plan_daily);
        }
    }

    // ---- Lịch chọn ngày tiếng Việt ----
    _isoOf(y, m, d) {
        return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    }

    _todayIso() {
        const t = new Date();
        return this._isoOf(t.getFullYear(), t.getMonth() + 1, t.getDate());
    }

    openPicker(field) {
        if (!this.state.edit?.canEditInfo) {
            return;
        }
        if (this.state.picker?.field === field) {
            this.state.picker = null;
            return;
        }
        const base = this.state.edit[field] || this._todayIso();
        const [y, m] = base.split("-").map(Number);
        this.state.picker = { field, year: y, month: m };
    }

    closePicker() {
        if (this.state.picker) {
            this.state.picker = null;
        }
    }

    pickerShift(delta) {
        const p = this.state.picker;
        let m = p.month + delta;
        let y = p.year;
        if (m < 1) {
            m = 12;
            y -= 1;
        } else if (m > 12) {
            m = 1;
            y += 1;
        }
        this.state.picker = { ...p, year: y, month: m };
    }

    get pickerTitle() {
        const p = this.state.picker;
        return p ? `Tháng ${String(p.month).padStart(2, "0")}/${p.year}` : "";
    }

    get pickerWeekdays() {
        return ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
    }

    /** Lưới 6 tuần, bắt đầu Thứ 2. */
    get pickerDays() {
        const p = this.state.picker;
        if (!p) {
            return [];
        }
        const first = new Date(p.year, p.month - 1, 1);
        const offset = (first.getDay() + 6) % 7; // T2 = 0
        const start = new Date(p.year, p.month - 1, 1 - offset);
        const selected = this.state.edit?.[p.field] || "";
        const today = this._todayIso();
        const out = [];
        for (let i = 0; i < 42; i++) {
            const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
            const iso = this._isoOf(d.getFullYear(), d.getMonth() + 1, d.getDate());
            const cls = ["o_dwp_picker_day"];
            if (d.getMonth() + 1 !== p.month) {
                cls.push("is-out");
            }
            if (d.getDay() === 0) {
                cls.push("is-sun");
            }
            if (iso === today) {
                cls.push("is-today");
            }
            if (iso === selected) {
                cls.push("is-selected");
            }
            out.push({ iso, day: d.getDate(), cls: cls.join(" ") });
        }
        return out;
    }

    pickDate(iso) {
        const p = this.state.picker;
        if (!p) {
            return;
        }
        this._setEditField(p.field, iso);
        this.state.picker = null;
    }

    pickToday() {
        this.pickDate(this._todayIso());
    }

    toggleEditDay(day) {
        const e = this.state.edit;
        if (!e || !e.canEditDays || e.lockedDays[day]) {
            return;
        }
        e.days = { ...e.days, [day]: !e.days[day] };
    }

    /** yyyy-mm-dd → dd/mm/yyyy */
    formatDate(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.split("-");
        return `${d}/${m}/${y}`;
    }

    async saveEdit() {
        const e = this.state.edit;
        if (!e || !this.isEditDirty) {
            return;
        }
        const name = e.name.trim();
        if (!name) {
            this.notification.add(_t("Tên công việc không được để trống."), { type: "warning" });
            return;
        }
        if (e.start && e.deadline && e.deadline < e.start) {
            this.notification.add(_t("Deadline không được trước Ngày bắt đầu."), { type: "warning" });
            return;
        }
        const info = e.canEditInfo && this._infoChanged
            ? { name, date_start: e.start || false, deadline: e.deadline || false }
            : false;
        const days = Object.keys(e.days).filter((k) => e.days[k]).map(Number);
        this.state.busy = true;
        try {
            await this.orm.call("daily.task.assign", "plan_save_row", [e.line.id], {
                kind: e.line.kind,
                info,
                year: this.state.year,
                month: this.state.month,
                days: e.canEditDays ? days : null,
                user_id: this.state.userId,
                day_kind: e.line.day_kind || false,
                day_id: e.line.day_id || false,
            });
            this.closeEdit();
            await this.load(true);
            this.notification.add(_t("Đã lưu — đồng bộ với Quản lý công việc."), { type: "success" });
        } catch (err) {
            // Giữ khung mở để sửa tiếp
            this._notifyError(err, _t("Không lưu được công việc."));
        } finally {
            this.state.busy = false;
        }
    }

    /** Ngày hiện dd/mm/yyyy; bấm vào mở lịch chọn ngày của trình duyệt. */
    openDatePicker(ev) {
        const input = ev.currentTarget.querySelector("input[type=date]");
        if (!input || input.disabled || ev.target === input) {
            return;
        }
        try {
            input.showPicker();
        } catch {
            input.focus();
        }
    }
    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Plan_CV_ca_nhan.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    /** Xuất Excel Plan CV cá nhân của tháng / nhân sự đang xem. */
    async onExportExcel() {
        this.state.exporting = true;
        try {
            const result = await this.orm.call("daily.task.assign", "export_my_plan_excel", [], {
                year: this.state.year,
                month: this.state.month,
                user_id: this.state.userId,
            });
            if (!result?.file_base64) {
                throw new Error(_t("Không nhận được file Excel."));
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add(_t("Đã xuất Plan CV cá nhân ra Excel."), { type: "success" });
        } catch (e) {
            this._notifyError(e, _t("Không xuất được Excel."));
        } finally {
            this.state.exporting = false;
        }
    }

    /** Gửi duyệt lại Plan tháng sau khi bị trưởng nhóm từ chối. */
    async resubmitPlan() {
        this.state.busy = true;
        try {
            await this.orm.call("daily.task.plan.approval", "resubmit_plan", [this.state.year, this.state.month]);
            this.notification.add(_t("Đã gửi duyệt lại Plan tháng."), { type: "success" });
            await this.load(true);
        } catch (e) {
            this._notifyError(e, _t("Không gửi duyệt lại được."));
        } finally {
            this.state.busy = false;
        }
    }

    openAdd() {
        // Có quyền thêm việc cho team → dùng khung đầy đủ (team, hạng mục, miền, kiểm soát)
        if (this.state.data?.can_team_add) {
            this.state.teamAdding = true;
            return;
        }
        this.state.newLine = EMPTY_NEW_LINE();
        this.state.adding = true;
    }

    closeTeamAdd() {
        this.state.teamAdding = false;
    }

    async onTeamAddSaved() {
        this.state.teamAdding = false;
        await this.load(true);
    }

    cancelAdd() {
        this.state.adding = false;
    }

    onNewField(field, ev) {
        const target = ev.target;
        this.state.newLine[field] = target.type === "checkbox" ? target.checked : target.value;
    }

    async saveNewLine() {
        const vals = { ...this.state.newLine };
        if (!vals.name.trim()) {
            this.notification.add(_t("Vui lòng nhập tên công việc."), { type: "warning" });
            return;
        }
        if (vals.date_start && vals.deadline && vals.deadline < vals.date_start) {
            this.notification.add(_t("Deadline không được trước ngày Bắt đầu."), { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("daily.task.assign", "plan_create_line", [vals], {
                user_id: this.state.userId,
            });
            this.state.adding = false;
            this.notification.add(_t("Đã thêm công việc vào plan."), { type: "success" });
            await this.load(true);
        } catch (e) {
            this._notifyError(e, _t("Không thêm được công việc."));
        } finally {
            this.state.busy = false;
        }
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            this.state.data = await this.orm.call("daily.task.assign", "get_my_plan_data", [], {
                year: this.state.year,
                month: this.state.month,
                user_id: this.state.userId,
            });
        } catch (e) {
            if (!silent) {
                this.state.data = null;
            }
            this._notifyError(e, _t("Không tải được plan công việc."));
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("daily_work_plan", DailyWorkPlan);
