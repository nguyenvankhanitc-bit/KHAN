/** @odoo-module **/
/* assign-access-matrix: 19.0.1.39.47-personnel */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

const GROUPS = [
    { key: "add", label: "Thêm phân công công việc" },
    { key: "list", label: "Danh sách công việc" },
    { key: "category", label: "Hạng mục" },
    { key: "personnel", label: "Công việc theo nhân sự" },
];

const PERMS = [
    { key: "view", label: "Xem" },
    { key: "create", label: "Thêm" },
    { key: "write", label: "Chỉnh sửa" },
    { key: "unlink", label: "Xóa" },
];

const NO_DEPT_KEY = "0";
const NO_DEPT_LABEL = "Chưa có phòng ban";

function emptyPerms() {
    return { view: false, create: false, write: false, unlink: false };
}

function clonePerms(src) {
    return {
        view: Boolean(src?.view),
        create: Boolean(src?.create),
        write: Boolean(src?.write),
        unlink: Boolean(src?.unlink),
    };
}

function emptyRow(stt = 1) {
    return {
        key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        id: false,
        stt,
        employee_ids: [],
        /** empId -> id bản ghi daily.task.assign.access */
        record_ids: {},
        query: "",
        open: false,
        add: emptyPerms(),
        list: emptyPerms(),
        category: emptyPerms(),
        personnel: emptyPerms(),
        dirty: true,
    };
}

function permSignature(add, list, category, personnel) {
    const pack = (g) =>
        [g?.view, g?.create, g?.write, g?.unlink]
            .map((v) => (v ? "1" : "0"))
            .join("");
    return `${pack(add)}|${pack(list)}|${pack(category)}|${pack(personnel)}`;
}

export class DailyWorkAssignAccessMatrix extends Component {
    static template = "daily_work_task.DailyWorkAssignAccessMatrix";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.GROUPS = GROUPS;
        this.PERMS = PERMS;
        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            rows: [],
            employees: [],
            empById: {},
            collapsed: {},
        });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "assign_access";
    }

    /** Nhóm dòng theo phòng ban (header section). */
    get sections() {
        const map = new Map();
        for (const row of this.state.rows) {
            const info = this._rowDept(row);
            if (!map.has(info.key)) {
                map.set(info.key, {
                    key: info.key,
                    label: info.label,
                    rows: [],
                });
            }
            map.get(info.key).rows.push(row);
        }
        const sections = [...map.values()].sort((a, b) => {
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
            sec.userCount = sec.rows.reduce(
                (n, r) => n + (r.employee_ids || []).length,
                0
            );
            sec.collapsed = Boolean(this.state.collapsed[sec.key]);
        }
        return sections;
    }

    _rowDept(row) {
        const ids = row.employee_ids || [];
        if (!ids.length) {
            return { key: NO_DEPT_KEY, label: NO_DEPT_LABEL };
        }
        const deptIds = new Set();
        const names = [];
        for (const id of ids) {
            const emp = this.state.empById[id];
            const did = String(emp?.department_id || 0);
            const dname = (emp?.department_name || "").trim() || NO_DEPT_LABEL;
            deptIds.add(did);
            if (!names.includes(dname)) {
                names.push(dname);
            }
        }
        if (deptIds.size === 1) {
            const key = [...deptIds][0];
            return {
                key,
                label: key === NO_DEPT_KEY ? NO_DEPT_LABEL : names[0],
            };
        }
        return { key: `mixed-${[...deptIds].sort().join("-")}`, label: names.join(" · ") };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "daily.task.assign.access",
                "get_assign_access_matrix",
                []
            );
            const employees = data.employees || [];
            const empById = {};
            for (const e of employees) {
                empById[e.id] = e;
            }
            this.state.employees = employees;
            this.state.empById = empById;

            // Server đã gộp cùng phòng ban + cùng quyền → employee_ids[]
            // Vẫn merge thêm phía client phòng khi server cũ / bản ghi lẻ
            const merged = new Map();
            for (const r of data.rows || []) {
                const add = { ...emptyPerms(), ...clonePerms(r.add) };
                const list = { ...emptyPerms(), ...clonePerms(r.list) };
                const category = { ...emptyPerms(), ...clonePerms(r.category) };
                const personnel = { ...emptyPerms(), ...clonePerms(r.personnel) };
                let ids = (r.employee_ids || [])
                    .map(Number)
                    .filter(Boolean);
                if (!ids.length && r.employee_id) {
                    ids = [Number(r.employee_id)];
                }
                if (!ids.length) {
                    continue;
                }
                const deptKey = String(
                    r.department_id ||
                        this.state.empById[ids[0]]?.department_id ||
                        0
                );
                const key = `${deptKey}::${permSignature(add, list, category, personnel)}`;
                if (!merged.has(key)) {
                    merged.set(key, {
                        key: `grp-${key}`,
                        id: r.id || false,
                        stt: 0,
                        employee_ids: [],
                        record_ids: {},
                        query: "",
                        open: false,
                        add,
                        list,
                        category,
                        personnel,
                        dirty: false,
                    });
                }
                const row = merged.get(key);
                const recMap = r.record_ids || {};
                for (const empId of ids) {
                    if (!row.employee_ids.includes(empId)) {
                        row.employee_ids.push(empId);
                    }
                    const rid = Number(
                        recMap[empId] || recMap[String(empId)] || 0
                    );
                    if (rid) {
                        row.record_ids[empId] = rid;
                        if (!row.id) {
                            row.id = rid;
                        }
                    } else if (r.id && ids.length === 1) {
                        row.record_ids[empId] = r.id;
                        row.id = r.id;
                    }
                }
            }
            const rows = [...merged.values()];
            if (!rows.length) {
                rows.push(emptyRow(1));
            }
            this.state.rows = rows;
            this.state.dirty = false;
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không tải được ma trận phân quyền."),
                { type: "danger" }
            );
            this.state.rows = [emptyRow(1)];
        } finally {
            this.state.loading = false;
        }
    }

    _markDirty() {
        this.state.dirty = true;
    }

    toggleSection(secKey) {
        this.state.collapsed = {
            ...this.state.collapsed,
            [secKey]: !this.state.collapsed[secKey],
        };
    }

    selectedEmployees(row) {
        return (row.employee_ids || [])
            .map((id) => this.state.empById[id])
            .filter(Boolean);
    }

    _takenEmployeeIds(exceptKey) {
        const taken = new Set();
        for (const r of this.state.rows) {
            if (r.key === exceptKey) {
                continue;
            }
            for (const id of r.employee_ids || []) {
                taken.add(Number(id));
            }
        }
        return taken;
    }

    filteredSuggestions(row) {
        const q = (row.query || "").trim().toLowerCase();
        const taken = this._takenEmployeeIds(row.key);
        const selected = new Set((row.employee_ids || []).map(Number));
        return (this.state.employees || [])
            .filter((e) => !taken.has(e.id) && !selected.has(e.id))
            .filter((e) => {
                if (!q) {
                    return true;
                }
                const blob = `${e.name || ""} ${e.department_name || ""}`.toLowerCase();
                return blob.includes(q);
            })
            .slice(0, 12);
    }

    onAddRow() {
        this.state.rows = [...this.state.rows, emptyRow(this.state.rows.length + 1)];
        this._markDirty();
    }

    onRemoveRow(row) {
        if (this.state.rows.length <= 1) {
            this.state.rows = [emptyRow(1)];
            this._markDirty();
            return;
        }
        this.state.rows = this.state.rows.filter((r) => r.key !== row.key);
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
            row.open = false;
        }, 180);
    }

    onPickEmployee(row, empId) {
        const id = Number(empId);
        if (!id) {
            return;
        }
        if (!(row.employee_ids || []).includes(id)) {
            row.employee_ids = [...(row.employee_ids || []), id];
        }
        row.query = "";
        row.open = false;
        row.dirty = true;
        this._markDirty();
    }

    onRemoveEmployee(row, empId) {
        const id = Number(empId);
        row.employee_ids = (row.employee_ids || []).filter((x) => Number(x) !== id);
        row.dirty = true;
        this._markDirty();
    }

    onQueryKeydown(row, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const list = this.filteredSuggestions(row);
            if (list.length) {
                this.onPickEmployee(row, list[0].id);
            }
        } else if (ev.key === "Backspace" && !(row.query || "").trim()) {
            const ids = row.employee_ids || [];
            if (ids.length) {
                this.onRemoveEmployee(row, ids[ids.length - 1]);
            }
        } else if (ev.key === "Escape") {
            row.open = false;
        }
    }

    onToggle(row, groupKey, permKey, ev) {
        const group = { ...emptyPerms(), ...clonePerms(row[groupKey]) };
        const next = Boolean(ev?.target?.checked);
        group[permKey] = next;
        if (next && permKey !== "view") {
            group.view = true;
        }
        if (!next && permKey === "view") {
            group.create = false;
            group.write = false;
            group.unlink = false;
        }
        row[groupKey] = group;
        row.dirty = true;
        this._markDirty();
    }

    async onSave() {
        if (this.state.saving) {
            return;
        }
        const payload = [];
        const used = new Set();
        for (const row of this.state.rows) {
            const ids = [
                ...new Set((row.employee_ids || []).map(Number).filter(Boolean)),
            ];
            if (!ids.length) {
                continue;
            }
            const recMap = row.record_ids || {};
            for (const empId of ids) {
                if (used.has(empId)) {
                    this.notification.add(
                        _t("Có user bị chọn trùng trên nhiều dòng. Kiểm tra lại."),
                        { type: "warning" }
                    );
                    return;
                }
                used.add(empId);
                // DB vẫn 1 bản ghi / user; UI giữ chung 1 dòng nhiều tag
                payload.push({
                    id: recMap[empId] || false,
                    employee_id: empId,
                    add: clonePerms(row.add),
                    list: clonePerms(row.list),
                    category: clonePerms(row.category),
                    personnel: clonePerms(row.personnel),
                });
            }
        }
        this.state.saving = true;
        try {
            await this.orm.call(
                "daily.task.assign.access",
                "save_assign_access_matrix",
                [payload]
            );
            this.notification.add(_t("Đã lưu phân quyền phân công."), {
                type: "success",
            });
            await this.load();
        } catch (e) {
            const msg =
                e?.data?.message ||
                e?.message ||
                _t("Không lưu được phân quyền.");
            this.notification.add(msg, { type: "danger", sticky: true });
        } finally {
            this.state.saving = false;
        }
    }

    async onCancel() {
        if (this.state.dirty) {
            const ok = window.confirm(
                _t("Hủy thay đổi chưa lưu và tải lại ma trận?")
            );
            if (!ok) {
                return;
            }
        }
        await this.load();
    }
}

registry
    .category("actions")
    .add("daily_work_assign_access_matrix", DailyWorkAssignAccessMatrix);
