/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Khung "Thêm công việc cho team" — dùng chung cho Plan tổng team và Plan CV cá nhân.
 * Tạo dòng phân công (team, hạng mục, miền, kiểm soát) → tự giao vào Plan cá nhân từng người.
 */
const ROLE_COLS = [
    { key: "south", label: "Miền Nam", field: "south_user_ids" },
    { key: "dtt", label: "Miền ĐTT", field: "dtt_user_ids" },
    { key: "north", label: "Miền Bắc", field: "north_user_ids" },
    { key: "office", label: "Văn phòng", field: "office_user_ids" },
    { key: "vptt", label: "VPTT", field: "vptt_user_ids" },
    { key: "vpmb", label: "VPMB", field: "vpmb_user_ids" },
    { key: "check", label: "Kiểm soát", field: "check_user_ids", title: "User kiểm tra" },
    { key: "assignee", label: "User phụ trách", field: "assignee_user_ids" },
    { key: "detail", label: "User chi tiết", field: "detail_user_ids" },
    { key: "detail_check", label: "User Kiểm chi tiết", field: "detail_check_user_ids" },
    { key: "total", label: "User tổng", field: "total_user_ids" },
    { key: "manager", label: "User quản lý hạng mục", field: "category_manager_ids", managerOnly: true },
];

export class TeamTaskDialog extends Component {
    static template = "daily_work_task.TeamTaskDialog";
    static props = {
        teamId: { optional: true },
        // Plan CV cá nhân: chọn sẵn team của người đang xem
        presetUserId: { optional: true },
        onClose: Function,
        onSaved: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ opts: null, newLine: null, picker: null, busy: false });
        onWillStart(() => this.loadOptions());
    }

    async loadOptions() {
        try {
            const opts = await this.orm.call("daily.task.assign", "get_team_plan_add_options", [], {});
            const teams = opts.teams || [];
            const uid = this.props.presetUserId;
            const current =
                teams.find((t) => t.id === this.props.teamId) ||
                (uid && teams.find((t) => (t.members || []).some((m) => m.id === uid))) ||
                teams[0];
            const inTeam = uid && current && (current.members || []).some((m) => m.id === uid);
            this.state.opts = opts;
            this.state.newLine = {
                name: "",
                team_id: current ? current.id : false,
                category: current?.categories?.[0]?.name || "",
                regions: {},
                extraUsers: uid && !inTeam ? [uid] : [],
                date_start: this._todayIso(),
                deadline: this._todayIso(),
                plan_daily: false,
                note: "",
            };
            this._presetManagers();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không mở được khung thêm công việc."), {
                type: "danger",
            });
            this.props.onClose();
        }
    }

    close() {
        this.state.picker = null;
        this.props.onClose();
    }

    /** Các cột user của bảng nhân sự (cột User quản lý hạng mục chỉ cho Quản lý). */
    get roleCols() {
        return ROLE_COLS.filter((c) => !c.managerOnly || this.state.opts?.can_set_manager);
    }

    get addCategory() {
        return (this.addTeam?.categories || []).find((c) => c.name === this.state.newLine?.category) || null;
    }

    /** Tích sẵn User quản lý hiện tại của hạng mục đang chọn. */
    _presetManagers() {
        const line = this.state.newLine;
        const managers = this.addCategory?.managers || [];
        const regions = {};
        for (const [uid, r] of Object.entries(line.regions || {})) {
            regions[uid] = { ...r, manager: false };
        }
        const extra = [...line.extraUsers];
        const memberIds = new Set((this.addTeam?.members || []).map((m) => m.id));
        for (const id of managers) {
            regions[id] = { ...(regions[id] || {}), manager: true };
            if (!memberIds.has(id) && !extra.includes(id)) {
                extra.push(id);
            }
        }
        line.regions = regions;
        line.extraUsers = extra;
    }

    get addTeam() {
        const teams = this.state.opts?.teams || [];
        return teams.find((t) => t.id === this.state.newLine?.team_id) || null;
    }

    /** Thành viên team + người ngoài team được thêm vào bảng chọn miền. */
    get addMembers() {
        const members = [...(this.addTeam?.members || [])];
        const all = this.state.opts?.users || [];
        for (const uid of this.state.newLine?.extraUsers || []) {
            const u = all.find((x) => x.id === uid);
            if (u && !members.find((m) => m.id === uid)) {
                members.push(u);
            }
        }
        return members;
    }

    get addOtherUsers() {
        const ids = new Set(this.addMembers.map((m) => m.id));
        return (this.state.opts?.users || []).filter((u) => !ids.has(u.id));
    }

    onAddField(field, ev) {
        const target = ev.target;
        let value = target.type === "checkbox" ? target.checked : target.value;
        if (field === "team_id") {
            value = parseInt(value) || false;
            const team = (this.state.opts?.teams || []).find((t) => t.id === value);
            this.state.newLine.category = team?.categories?.[0]?.name || "";
            this.state.newLine.regions = {};
        }
        this.state.newLine[field] = value;
        if (field === "team_id" || field === "category") {
            this._presetManagers();
        }
    }

    addExtraUser(ev) {
        const uid = parseInt(ev.target.value);
        if (uid && !this.state.newLine.extraUsers.includes(uid)) {
            this.state.newLine.extraUsers = [...this.state.newLine.extraUsers, uid];
        }
        ev.target.value = "";
    }

    hasRegion(uid, key) {
        return Boolean(this.state.newLine?.regions?.[uid]?.[key]);
    }

    toggleRegion(uid, key) {
        const regions = { ...(this.state.newLine.regions || {}) };
        regions[uid] = { ...(regions[uid] || {}), [key]: !regions[uid]?.[key] };
        this.state.newLine.regions = regions;
    }

    async save() {
        const v = this.state.newLine;
        const pick = (key) =>
            Object.entries(v.regions || {})
                .filter(([, r]) => r[key])
                .map(([uid]) => parseInt(uid));
        const payload = {
            name: (v.name || "").trim(),
            team_id: v.team_id,
            category: v.category,
            date_start: v.date_start || false,
            deadline: v.deadline || false,
            plan_daily: v.plan_daily,
            note: v.note,
        };
        for (const col of this.roleCols) {
            payload[col.field] = pick(col.key);
        }
        if (!payload.name) {
            this.notification.add(_t("Vui lòng nhập tên công việc."), { type: "warning" });
            return;
        }
        if (payload.date_start && payload.deadline && payload.deadline < payload.date_start) {
            this.notification.add(_t("Deadline không được trước Ngày bắt đầu."), { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("daily.task.assign", "team_plan_create_line", [payload]);
            this.notification.add(_t("Đã thêm công việc — đã giao vào Plan cá nhân của từng người."), {
                type: "success",
            });
            await this.props.onSaved();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thêm được công việc."), { type: "danger" });
        } finally {
            this.state.busy = false;
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

    formatDate(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.split("-");
        return `${d}/${m}/${y}`;
    }

    openPicker(field) {
        if (this.state.picker?.field === field) {
            this.state.picker = null;
            return;
        }
        const base = this.state.newLine?.[field] || this._todayIso();
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

    get pickerDays() {
        const p = this.state.picker;
        if (!p) {
            return [];
        }
        const first = new Date(p.year, p.month - 1, 1);
        const offset = (first.getDay() + 6) % 7;
        const start = new Date(p.year, p.month - 1, 1 - offset);
        const selected = this.state.newLine?.[p.field] || "";
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
        this.state.newLine[p.field] = iso || "";
        this.state.picker = null;
    }

    pickToday() {
        this.pickDate(this._todayIso());
    }
}

/**
 * Plan tổng: sửa Tên / Ngày bắt đầu / Deadline hoặc xóa 1 công việc chung (theo Phân quyền Plan tổng).
 * Dùng lại lịch chọn ngày tiếng Việt của khung Thêm công việc.
 */
export class TeamLineEditDialog extends TeamTaskDialog {
    static template = "daily_work_task.TeamLineEditDialog";
    static props = {
        line: Object,
        canWrite: { type: Boolean, optional: true },
        canUnlink: { type: Boolean, optional: true },
        onClose: Function,
        onSaved: Function,
    };

    /** 'personal' = sửa việc bổ sung của mình (thêm ở bảng cá nhân) · 'team' = việc Plan tổng. */
    get mode() {
        const line = this.props.line;
        return !line.line_id && line.own ? "personal" : "team";
    }

    get canEdit() {
        return this.mode === "team" ? Boolean(this.props.canWrite) : true;
    }

    async loadOptions() {
        const line = this.props.line;
        const personal = this.mode === "personal";
        this.state.newLine = {
            name: line.name || "",
            date_start: (personal ? line.task_start_iso : line.start_iso) || "",
            deadline: (personal ? line.task_deadline_iso : line.deadline_iso) || "",
        };
    }

    onAddField(field, ev) {
        this.state.newLine[field] = ev.target.value;
    }

    openPicker(field) {
        if (this.canEdit) {
            super.openPicker(field);
        }
    }

    async save() {
        const v = this.state.newLine;
        if (!(v.name || "").trim()) {
            this.notification.add(_t("Tên công việc không được để trống."), { type: "warning" });
            return;
        }
        if (v.date_start && v.deadline && v.deadline < v.date_start) {
            this.notification.add(_t("Deadline không được trước Ngày bắt đầu."), { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            const vals = { name: v.name.trim(), date_start: v.date_start || false, deadline: v.deadline || false };
            if (this.mode === "personal") {
                await this.orm.call("daily.task.assign", "plan_update_line", [
                    this.props.line.task_id, vals.date_start, vals.deadline, "task", vals.name,
                ]);
                this.notification.add(_t("Đã lưu việc bổ sung — đồng bộ Công việc cá nhân và Plan cá nhân."), {
                    type: "success",
                });
            } else {
                await this.orm.call("daily.task.assign", "team_plan_update_line", [this.props.line.line_id], { vals });
                this.notification.add(_t("Đã lưu — đồng bộ Plan cá nhân của từng người."), { type: "success" });
            }
            await this.props.onSaved();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được công việc."), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async remove() {
        if (!window.confirm(_t("Xóa công việc «%s» khỏi Plan tổng và Plan cá nhân của mọi người?", this.props.line.name))) {
            return;
        }
        this.state.busy = true;
        try {
            const res = await this.orm.call("daily.task.assign", "team_plan_delete_line", [this.props.line.line_id]);
            const kept = res?.kept || 0;
            this.notification.add(
                kept
                    ? _t("Đã xóa công việc. Giữ lại %s việc cá nhân đã làm để còn lịch sử.", kept)
                    : _t("Đã xóa công việc."),
                { type: "success" }
            );
            await this.props.onSaved();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xóa được công việc."), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}
