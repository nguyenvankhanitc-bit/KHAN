/** @odoo-module **/
/* Phân quyền ứng dụng Dự án — cùng giao diện Phân quyền báo cáo (Công việc hằng ngày) */

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

const NO_DEPT_KEY = "0";
const NO_DEPT_LABEL = "Chưa có phòng ban";
const LUG_GROUP_KEY = "lug-groups";
const LUG_GROUP_LABEL = "Theo nhóm quyền (LUG Permission)";
const GROUP_ICONS = {
    kpi: "fa-tachometer",
    intake: "fa-plus-square-o",
    list: "fa-folder-open-o",
    track: "fa-eye",
    gantt: "fa-align-left",
    assign: "fa-users",
    overdue: "fa-exclamation-triangle",
    milestones: "fa-bell-o",
    report_all: "fa-bar-chart",
    people: "fa-user-circle-o",
    perf: "fa-line-chart",
    config: "fa-cog",
    archived: "fa-trash-o",
    contacts: "fa-address-book-o",
};

export class LugProjectAppPerm extends Component {
    static template = "lug_project.LugProjectAppPerm";
    static props = {
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            groups: [],
            perms: [],
            rows: [],
            users: [],
            userById: {},
            lugGroups: [],
            lugGroupById: {},
            collapsed: {},
        });
        onWillStart(() => this.load());
    }

    get GROUPS() {
        return this.state.groups;
    }

    get PERMS() {
        return this.state.perms;
    }

    get colspan() {
        return 5;
    }

    selectedGroups(row) {
        return (row.group_ids || []).map((id) => this.state.lugGroupById[id]).filter(Boolean);
    }

    previewGroup(row) {
        return this.selectedGroups(row)[0] || null;
    }

    groupNamesText(group) {
        return (group.user_names || []).join(", ");
    }

    groupMemberNames(row) {
        const names = [];
        for (const g of this.selectedGroups(row)) {
            for (const n of g.user_names || []) {
                if (n && !names.includes(n)) {
                    names.push(n);
                }
            }
        }
        return names;
    }

    filteredGroupSuggestions(row) {
        const q = (row.gquery || "").trim().toLowerCase();
        const taken = new Set();
        for (const r of this.state.rows) {
            for (const id of r.group_ids || []) {
                taken.add(Number(id));
            }
        }
        return (this.state.lugGroups || [])
            .filter((g) => !taken.has(g.id))
            .filter((g) => {
                if (!q) {
                    return true;
                }
                const blob = `${g.name || ""} ${g.code || ""} ${(g.user_names || []).join(" ")}`.toLowerCase();
                return blob.includes(q);
            })
            .slice(0, 12);
    }

    onGroupQueryInput(row, ev) {
        row.gquery = ev.target.value || "";
        row.gopen = true;
    }

    onGroupQueryFocus(row) {
        row.gopen = true;
    }

    onGroupHover(row, groupId) {
        row.ghover = Number(groupId) || 0;
    }

    onGroupLeave(row) {
        row.ghover = 0;
    }

    onGroupQueryBlur(row) {
        setTimeout(() => {
            if (this._holdSuggest) {
                return;
            }
            row.gopen = false;
            row.ghover = 0;
        }, 250);
    }

    onSuggestPointerDown() {
        this._holdSuggest = true;
        setTimeout(() => {
            this._holdSuggest = false;
        }, 400);
    }

    onPickGroup(row, groupId) {
        const id = Number(groupId);
        if (id && !(row.group_ids || []).includes(id)) {
            row.group_ids = [...(row.group_ids || []), id];
            this._markDirty();
        }
        row.gquery = "";
        row.gopen = false;
        row.ghover = 0;
    }

    onRemoveGroup(row, groupId) {
        const id = Number(groupId);
        row.group_ids = (row.group_ids || []).filter((x) => Number(x) !== id);
        this._markDirty();
    }

    onGroupQueryKeydown(row, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const list = this.filteredGroupSuggestions(row);
            if (list.length) {
                this.onPickGroup(row, list[0].id);
            }
        } else if (ev.key === "Backspace" && !(row.gquery || "").trim()) {
            const ids = row.group_ids || [];
            if (ids.length) {
                this.onRemoveGroup(row, ids[ids.length - 1]);
            }
        } else if (ev.key === "Escape") {
            row.gopen = false;
        }
    }

    groupIcon(key) {
        return GROUP_ICONS[key] || "fa-circle-o";
    }

    columnState(row, permKey) {
        const groups = this.state.groups;
        const on = groups.filter((g) => row[g.key]?.[permKey]).length;
        if (!on) {
            return "";
        }
        return on === groups.length ? "is-on" : "is-mixed";
    }

    onToggleColumn(row, permKey) {
        const next = this.columnState(row, permKey) !== "is-on";
        for (const g of this.state.groups) {
            this.setPerm(row, g.key, permKey, next);
        }
    }

    emptyPerms() {
        return Object.fromEntries(this.state.perms.map((p) => [p.key, false]));
    }

    clonePerms(src) {
        return Object.fromEntries(this.state.perms.map((p) => [p.key, Boolean(src?.[p.key])]));
    }

    permSignature(row) {
        return this.state.groups
            .map((g) => this.state.perms.map((p) => (row[g.key]?.[p.key] ? "1" : "0")).join(""))
            .join("|");
    }

    emptyRow() {
        const row = {
            key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            stt: 0,
            user_ids: [],
            group_ids: [],
            record_ids: {},
            query: "",
            open: false,
            gquery: "",
            gopen: false,
            ghover: 0,
        };
        for (const g of this.state.groups) {
            row[g.key] = Object.fromEntries(this.state.perms.map((p) => [p.key, true]));
        }
        return row;
    }

    get sections() {
        const map = new Map();
        for (const row of this.state.rows) {
            const info = this._rowDept(row);
            if (!map.has(info.key)) {
                map.set(info.key, { key: info.key, label: info.label, rows: [] });
            }
            map.get(info.key).rows.push(row);
        }
        const sections = [...map.values()].sort((a, b) => {
            if (a.key === LUG_GROUP_KEY || b.key === LUG_GROUP_KEY) {
                return a.key === LUG_GROUP_KEY ? -1 : 1;
            }
            if (a.key === NO_DEPT_KEY) {
                return 1;
            }
            if (b.key === NO_DEPT_KEY) {
                return -1;
            }
            return (a.label || "").localeCompare(b.label || "", "vi");
        });
        let stt = 1;
        for (const sec of sections) {
            for (const row of sec.rows) {
                row.stt = stt++;
            }
            sec.userCount = sec.rows.reduce((n, r) => n + (r.user_ids || []).length, 0);
            sec.collapsed = Boolean(this.state.collapsed[sec.key]);
        }
        return sections;
    }

    _rowDept(row) {
        const ids = row.user_ids || [];
        if (!ids.length) {
            if ((row.group_ids || []).length) {
                return { key: LUG_GROUP_KEY, label: LUG_GROUP_LABEL };
            }
            return { key: NO_DEPT_KEY, label: NO_DEPT_LABEL };
        }
        const deptIds = new Set();
        const names = [];
        for (const id of ids) {
            const user = this.state.userById[id];
            const did = String(user?.department_id || 0);
            const dname = (user?.department_name || "").trim() || NO_DEPT_LABEL;
            deptIds.add(did);
            if (!names.includes(dname)) {
                names.push(dname);
            }
        }
        if (deptIds.size === 1) {
            const key = [...deptIds][0];
            return { key, label: key === NO_DEPT_KEY ? NO_DEPT_LABEL : names[0] };
        }
        return { key: `mixed-${[...deptIds].sort().join("-")}`, label: names.join(" · ") };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("lug.project.app.perm", "get_app_perm_matrix", []);
            this.state.groups = data.groups || [];
            this.state.perms = data.perms || [];
            const userById = {};
            for (const u of data.users || []) {
                userById[u.id] = u;
            }
            this.state.users = data.users || [];
            this.state.userById = userById;
            const lugGroupById = {};
            for (const g of data.lug_groups || []) {
                lugGroupById[g.id] = g;
            }
            this.state.lugGroups = data.lug_groups || [];
            this.state.lugGroupById = lugGroupById;

            // 1 dòng ma trận = các bản ghi cùng row_key (user + nhóm quyền);
            // bản ghi cũ chưa có row_key: gộp theo phòng ban + cùng quyền
            const merged = new Map();
            for (const r of data.rows || []) {
                const userId = Number(r.user_id);
                const groupIds = (r.group_ids || []).map(Number).filter(Boolean);
                if (!userId && !groupIds.length) {
                    continue;
                }
                const perms = Object.fromEntries(
                    this.state.groups.map((g) => [g.key, this.clonePerms(r[g.key])])
                );
                const key = r.row_key
                    ? `key::${r.row_key}`
                    : `${String(r.department_id || 0)}::${this.permSignature(perms)}`;
                if (!merged.has(key)) {
                    merged.set(key, {
                        key: r.row_key || `grp-${key}`,
                        stt: 0,
                        user_ids: [],
                        group_ids: [],
                        record_ids: {},
                        query: "",
                        open: false,
                        gquery: "",
                        gopen: false,
                        ghover: 0,
                        ...perms,
                    });
                }
                const row = merged.get(key);
                if (userId) {
                    row.user_ids.push(userId);
                    row.record_ids[userId] = r.id;
                }
                for (const gid of groupIds) {
                    if (!row.group_ids.includes(gid)) {
                        row.group_ids.push(gid);
                    }
                }
            }
            const rows = [...merged.values()];
            if (!rows.length) {
                rows.push(this.emptyRow());
            }
            this.state.rows = rows;
            this.state.dirty = false;
        } catch (e) {
            this.notification.add(
                e?.data?.message || e?.message || "Không tải được ma trận phân quyền.",
                { type: "danger" }
            );
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    _markDirty() {
        this.state.dirty = true;
    }

    toggleSection(secKey) {
        this.state.collapsed = { ...this.state.collapsed, [secKey]: !this.state.collapsed[secKey] };
    }

    selectedUsers(row) {
        return (row.user_ids || []).map((id) => this.state.userById[id]).filter(Boolean);
    }

    _takenUserIds(exceptKey) {
        const taken = new Set();
        for (const r of this.state.rows) {
            if (r.key === exceptKey) {
                continue;
            }
            for (const id of r.user_ids || []) {
                taken.add(Number(id));
            }
        }
        return taken;
    }

    filteredSuggestions(row) {
        const q = (row.query || "").trim().toLowerCase();
        const taken = this._takenUserIds(row.key);
        const selected = new Set((row.user_ids || []).map(Number));
        return (this.state.users || [])
            .filter((u) => !taken.has(u.id) && !selected.has(u.id))
            .filter((u) => {
                if (!q) {
                    return true;
                }
                const blob = `${u.name || ""} ${u.login || ""} ${u.department_name || ""}`.toLowerCase();
                return blob.includes(q);
            })
            .slice(0, 12);
    }

    onAddRow() {
        this.state.rows = [...this.state.rows, this.emptyRow()];
        this._markDirty();
    }

    onRemoveRow(row) {
        this.state.rows = this.state.rows.filter((r) => r.key !== row.key);
        if (!this.state.rows.length) {
            this.state.rows = [this.emptyRow()];
        }
        this._markDirty();
    }

    onQueryInput(row, ev) {
        row.query = ev.target.value || "";
        row.open = true;
    }

    onQueryFocus(row) {
        row.open = true;
    }

    onQueryBlur(row) {
        setTimeout(() => {
            if (this._holdSuggest) {
                return;
            }
            row.open = false;
        }, 250);
    }

    onPickUser(row, userId) {
        const id = Number(userId);
        if (!id) {
            return;
        }
        if (!(row.user_ids || []).includes(id)) {
            row.user_ids = [...(row.user_ids || []), id];
        }
        row.query = "";
        row.open = false;
        this._markDirty();
    }

    onRemoveUser(row, userId) {
        const id = Number(userId);
        row.user_ids = (row.user_ids || []).filter((x) => Number(x) !== id);
        this._markDirty();
    }

    onQueryKeydown(row, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const list = this.filteredSuggestions(row);
            if (list.length) {
                this.onPickUser(row, list[0].id);
            }
        } else if (ev.key === "Backspace" && !(row.query || "").trim()) {
            const ids = row.user_ids || [];
            if (ids.length) {
                this.onRemoveUser(row, ids[ids.length - 1]);
            }
        } else if (ev.key === "Escape") {
            row.open = false;
        }
    }

    setPerm(row, groupKey, permKey, value) {
        const group = { ...this.emptyPerms(), ...this.clonePerms(row[groupKey]) };
        const next = Boolean(value);
        group[permKey] = next;
        if (next && permKey !== "view") {
            group.view = true;
        }
        if (!next && permKey === "view") {
            for (const p of this.state.perms) {
                group[p.key] = false;
            }
        }
        row[groupKey] = group;
        this._markDirty();
    }

    async onSave() {
        if (this.state.saving) {
            return;
        }
        const payload = [];
        const used = new Set();
        for (const row of this.state.rows) {
            const ids = [...new Set((row.user_ids || []).map(Number).filter(Boolean))];
            const groupIds = [...new Set((row.group_ids || []).map(Number).filter(Boolean))];
            if (!ids.length && !groupIds.length) {
                this.notification.add("Mỗi dòng cần chọn user hoặc nhóm quyền (LUG Permission).", {
                    type: "warning",
                });
                return;
            }
            for (const userId of ids) {
                if (used.has(userId)) {
                    this.notification.add("Có user bị chọn trùng trên nhiều dòng. Kiểm tra lại.", {
                        type: "warning",
                    });
                    return;
                }
                used.add(userId);
            }
            payload.push({
                row_key: row.key,
                user_ids: ids,
                group_ids: groupIds,
                ...Object.fromEntries(
                    this.state.groups.map((g) => [g.key, this.clonePerms(row[g.key])])
                ),
            });
        }
        this.state.saving = true;
        try {
            await this.orm.call("lug.project.app.perm", "save_app_perm_matrix", [payload]);
            this.notification.add("Đã lưu phân quyền ứng dụng dự án.", { type: "success" });
            await this.load();
            this.props.onSaved?.();
        } catch (e) {
            this.notification.add(e?.data?.message || e?.message || "Không lưu được phân quyền.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onCancel() {
        if (this.state.dirty && !window.confirm("Hủy thay đổi chưa lưu và tải lại ma trận?")) {
            return;
        }
        await this.load();
    }
}
