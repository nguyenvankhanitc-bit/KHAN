/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

const PERMS = [
    { key: "view", label: "Xem" },
    { key: "create", label: "Thêm" },
    { key: "write", label: "Chỉnh sửa" },
    { key: "unlink", label: "Xóa" },
];

function newRow() {
    return {
        key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        employee_id: false,
        query: "",
        open: false,
        view: false,
        create: false,
        write: false,
        unlink: false,
    };
}

/** Phân quyền Plan tổng: STT · User · Nhóm quyền · Thêm / Chỉnh sửa / Xóa / All. */
export class DailyWorkTeamPlanAccess extends Component {
    static template = "daily_work_task.DailyWorkTeamPlanAccess";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.PERMS = PERMS;
        this.state = useState({ loading: true, saving: false, dirty: false, rows: [], employees: [], empById: {} });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "team_plan_access";
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task.team.plan.access", "get_matrix", []);
            const empById = {};
            for (const e of data.employees || []) {
                empById[e.id] = e;
            }
            this.state.employees = data.employees || [];
            this.state.empById = empById;
            const rows = (data.rows || []).map((r) => ({ ...newRow(), key: `row-${r.id}`, ...r }));
            this.state.rows = rows.length ? rows : [newRow()];
            this.state.dirty = false;
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được phân quyền Plan tổng."), {
                type: "danger",
            });
            this.state.rows = [newRow()];
        } finally {
            this.state.loading = false;
        }
    }

    employeeOf(row) {
        return this.state.empById[row.employee_id] || null;
    }

    suggestions(row) {
        const q = (row.query || "").trim().toLowerCase();
        const taken = new Set(this.state.rows.filter((r) => r.key !== row.key).map((r) => r.employee_id));
        return this.state.employees
            .filter((e) => !taken.has(e.id) && e.id !== row.employee_id)
            .filter((e) => !q || `${e.name} ${e.department_name}`.toLowerCase().includes(q))
            .slice(0, 12);
    }

    onQueryInput(row, ev) {
        row.query = ev.target.value || "";
        row.open = true;
    }

    onQueryBlur(row) {
        setTimeout(() => {
            row.open = false;
        }, 180);
    }

    onQueryKeydown(row, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const list = this.suggestions(row);
            if (list.length) {
                this.pickEmployee(row, list[0].id);
            }
        } else if (ev.key === "Escape") {
            row.open = false;
        }
    }

    pickEmployee(row, empId) {
        row.employee_id = empId;
        row.query = "";
        row.open = false;
        this.state.dirty = true;
    }

    clearEmployee(row) {
        row.employee_id = false;
        this.state.dirty = true;
    }

    isAll(row) {
        return PERMS.every((p) => row[p.key]);
    }

    togglePerm(row, key, ev) {
        const on = Boolean(ev.target.checked);
        row[key] = on;
        if (on && key !== "view") {
            // Thêm / Chỉnh sửa / Xóa luôn kèm Xem
            row.view = true;
        }
        if (!on && key === "view") {
            row.create = row.write = row.unlink = false;
        }
        this.state.dirty = true;
    }

    toggleAll(row, ev) {
        const on = Boolean(ev.target.checked);
        for (const p of PERMS) {
            row[p.key] = on;
        }
        this.state.dirty = true;
    }

    addRow() {
        this.state.rows = [...this.state.rows, newRow()];
        this.state.dirty = true;
    }

    removeRow(row) {
        const rest = this.state.rows.filter((r) => r.key !== row.key);
        this.state.rows = rest.length ? rest : [newRow()];
        this.state.dirty = true;
    }

    async onSave() {
        const payload = this.state.rows
            .filter((r) => r.employee_id)
            .map((r) => ({
                employee_id: r.employee_id,
                view: r.view,
                create: r.create,
                write: r.write,
                unlink: r.unlink,
            }));
        this.state.saving = true;
        try {
            await this.orm.call("daily.task.team.plan.access", "save_matrix", [payload]);
            this.notification.add(_t("Đã lưu phân quyền Plan tổng."), { type: "success" });
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được phân quyền."), {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onCancel() {
        if (this.state.dirty && !window.confirm(_t("Hủy thay đổi chưa lưu và tải lại?"))) {
            return;
        }
        await this.load();
    }
}

registry.category("actions").add("daily_work_team_plan_access", DailyWorkTeamPlanAccess);
