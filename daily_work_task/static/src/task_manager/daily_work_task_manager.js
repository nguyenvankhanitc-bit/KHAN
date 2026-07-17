/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

const SIDEBAR_STORAGE_KEY = "daily_work_task.manager.sidebarWidth";
const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 560;
const SIDEBAR_DEFAULT = 320;

export class DailyWorkTaskManager extends Component {
    static template = "daily_work_task.DailyWorkTaskManager";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.layoutRef = useRef("layout");
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
        this.state = useState({
            loading: true,
            saving: false,
            employees: [],
            departments: [],
            priorities: [],
            states: [],
            tasks: [],
            canDelete: false,
            form: this.emptyForm(),
            sidebarWidth: this._loadSidebarWidth(),
            resizing: false,
        });
        onWillStart(async () => {
            await this.loadAll();
        });
        onMounted(() => {
            window.addEventListener("pointermove", this._onPointerMove);
            window.addEventListener("pointerup", this._onPointerUp);
        });
        onWillUnmount(() => {
            window.removeEventListener("pointermove", this._onPointerMove);
            window.removeEventListener("pointerup", this._onPointerUp);
            document.body.classList.remove("o_dtm_resizing");
        });
    }

    get layoutStyle() {
        return `grid-template-columns: ${this.state.sidebarWidth}px 8px minmax(0, 1fr);`;
    }

    /** Nhóm task theo bộ phận — mỗi nhóm 1 khung + thanh cuộn riêng. */
    get taskGroups() {
        const map = new Map();
        for (const task of this.state.tasks || []) {
            const deptId = task.department_id || 0;
            const key = String(deptId);
            if (!map.has(key)) {
                map.set(key, {
                    key,
                    id: deptId,
                    name: (task.department_label || "").trim() || "Chưa có bộ phận",
                    tasks: [],
                });
            }
            map.get(key).tasks.push(task);
        }
        const groups = Array.from(map.values());
        groups.sort((a, b) => {
            if (a.id === 0 && b.id !== 0) {
                return 1;
            }
            if (b.id === 0 && a.id !== 0) {
                return -1;
            }
            return (a.name || "").localeCompare(b.name || "", "vi");
        });
        return groups.map((group, index) => {
            const color = this.resolveDeptColor(group, index);
            return {
                ...group,
                colorClass: color.colorClass,
                colorStyle: color.colorStyle,
            };
        });
    }

    /** Bảng màu ổn định theo id bộ phận (xoay vòng palette). */
    deptColorPalette() {
        return [
            { bg: "#1e3a5f", border: "#152a45" }, // navy
            { bg: "#0f766e", border: "#0b5a54" }, // teal
            { bg: "#b45309", border: "#92400e" }, // amber
            { bg: "#7c3aed", border: "#6d28d9" }, // violet
            { bg: "#dc2626", border: "#b91c1c" }, // red
            { bg: "#0369a1", border: "#075985" }, // sky
            { bg: "#15803d", border: "#166534" }, // green
            { bg: "#c2410c", border: "#9a3412" }, // orange
            { bg: "#4f46e5", border: "#4338ca" }, // indigo
            { bg: "#0e7490", border: "#155e75" }, // cyan
            { bg: "#a16207", border: "#854d0e" }, // yellow-brown
            { bg: "#64748b", border: "#475569" }, // slate (fallback / chưa có PB)
        ];
    }

    /** Một số bộ phận cố định màu theo tên. */
    deptColorByName(name) {
        const n = (name || "").normalize("NFC").toLowerCase();
        if (n.includes("marketing") || n.includes("kinh doanh")) {
            return { bg: "#dc2626", border: "#b91c1c", index: 4 }; // đỏ
        }
        if (n.includes("hành chính") || n.includes("nhân sự") || n.includes("hcns")) {
            return { bg: "#0f766e", border: "#0b5a54", index: 1 }; // teal
        }
        if (n.includes("kế toán")) {
            return { bg: "#0369a1", border: "#075985", index: 5 }; // sky
        }
        if (n.includes("kho") || n.includes("vận")) {
            return { bg: "#b45309", border: "#92400e", index: 2 }; // amber
        }
        if (n.includes("thi công") || n.includes("kỹ thuật")) {
            return { bg: "#15803d", border: "#166534", index: 6 }; // green
        }
        return null;
    }

    resolveDeptColor(group, index) {
        const fixed = this.deptColorByName(group.name);
        const palette = this.deptColorPalette();
        let i;
        let c;
        if (fixed) {
            i = fixed.index;
            c = { bg: fixed.bg, border: fixed.border };
        } else if (group.id === 0) {
            i = palette.length - 1;
            c = palette[i];
        } else {
            i = Math.abs(Number(group.id) || index) % (palette.length - 1);
            c = palette[i];
        }
        return {
            colorClass: `o_dtm_dept_color_${i}`,
            colorStyle: `background: linear-gradient(180deg, ${c.bg} 0%, ${c.border} 100%); border-color: ${c.border};`,
        };
    }

    _loadSidebarWidth() {
        const saved = Number(localStorage.getItem(SIDEBAR_STORAGE_KEY));
        if (Number.isFinite(saved) && saved >= SIDEBAR_MIN && saved <= SIDEBAR_MAX) {
            return saved;
        }
        return SIDEBAR_DEFAULT;
    }

    _saveSidebarWidth(width) {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(width));
    }

    onSplitterPointerDown(ev) {
        ev.preventDefault();
        this.state.resizing = true;
        document.body.classList.add("o_dtm_resizing");
        if (ev.currentTarget?.setPointerCapture) {
            ev.currentTarget.setPointerCapture(ev.pointerId);
        }
    }

    _onPointerMove(ev) {
        if (!this.state.resizing || !this.layoutRef.el) {
            return;
        }
        const rect = this.layoutRef.el.getBoundingClientRect();
        let width = ev.clientX - rect.left;
        width = Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width));
        this.state.sidebarWidth = Math.round(width);
    }

    _onPointerUp() {
        if (!this.state.resizing) {
            return;
        }
        this.state.resizing = false;
        document.body.classList.remove("o_dtm_resizing");
        this._saveSidebarWidth(this.state.sidebarWidth);
    }

    onSplitterDblClick() {
        this.state.sidebarWidth = SIDEBAR_DEFAULT;
        this._saveSidebarWidth(SIDEBAR_DEFAULT);
    }

    emptyForm() {
        return {
            name: "",
            deadline: "",
            department_id: 0,
            assignee_id: 0,
            priority: "medium",
            state: "in_progress",
            note: "",
        };
    }

    async loadAll() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_manager_bootstrap", []);
            this.state.employees = data.employees || [];
            this.state.departments = data.departments || [];
            this.state.priorities = data.priorities || [];
            this.state.states = data.states || [];
            this.state.tasks = data.tasks || [];
            this.state.canDelete = Boolean(data.can_delete);
            if (!this.state.form.assignee_id && this.state.employees.length) {
                this.state.form.assignee_id = this.state.employees[0].id;
                this.onAssigneeChange();
            }
        } finally {
            this.state.loading = false;
        }
    }

    onAssigneeChange() {
        const emp = this.state.employees.find((e) => e.id === this.state.form.assignee_id);
        if (emp && emp.department_id) {
            this.state.form.department_id = emp.department_id;
        }
    }

    async onSubmit(ev) {
        ev.preventDefault();
        const f = this.state.form;
        if (!f.name?.trim()) {
            this.notification.add(_t("Vui lòng nhập tên công việc."), { type: "warning" });
            return;
        }
        if (!f.deadline) {
            this.notification.add(_t("Vui lòng chọn hạn hoàn thành."), { type: "warning" });
            return;
        }
        if (!f.assignee_id) {
            this.notification.add(_t("Vui lòng chọn người phụ trách."), { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("daily.task", "create_from_manager", [
                {
                    name: f.name.trim(),
                    deadline: f.deadline,
                    department_id: f.department_id || false,
                    assignee_id: f.assignee_id,
                    priority: f.priority,
                    state: f.state,
                    note: f.note,
                },
            ]);
            this.state.form = {
                ...this.emptyForm(),
                department_id: f.department_id,
                assignee_id: f.assignee_id,
                priority: "medium",
                state: "in_progress",
            };
            this.state.tasks = await this.orm.call("daily.task", "get_manager_tasks", []);
            this.notification.add(_t("Đã cập nhật công việc lên hệ thống."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể lưu công việc."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onNoteBlur(task, ev) {
        const note = ev.target.value;
        if ((task.note || "") === note) {
            return;
        }
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { note },
            ]);
            const idx = this.state.tasks.findIndex((t) => t.id === task.id);
            if (idx >= 0) {
                this.state.tasks[idx] = updated;
            }
        } catch (e) {
            this.notification.add(_t("Không thể cập nhật ghi chú."), { type: "danger" });
        }
    }

    async onDelete(task) {
        if (!this.state.canDelete) {
            this.notification.add(
                _t("Chỉ tài khoản Administrator mới được xóa công việc."),
                { type: "warning" }
            );
            return;
        }
        if (!confirm(`Xóa công việc "${task.name}"?`)) {
            return;
        }
        try {
            await this.orm.call("daily.task", "delete_from_manager", [[task.id]]);
            this.state.tasks = this.state.tasks.filter((t) => t.id !== task.id);
            this.notification.add(_t("Đã xóa công việc."), { type: "success" });
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không thể xóa công việc."),
                { type: "danger" }
            );
        }
    }

    async openHrEmployee(hrEmployeeId) {
        if (!hrEmployeeId) {
            this.notification.add(
                _t("Nhân viên này chưa liên kết hồ sơ HR. Vào Cấu hình → Danh sách nhân viên để gắn."),
                { type: "warning" }
            );
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Hồ sơ nhân viên"),
            res_model: "hr.employee",
            res_id: hrEmployeeId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    priorityClass(priority) {
        return {
            high: "o_dtm_badge_high",
            medium: "o_dtm_badge_medium",
            low: "o_dtm_badge_low",
        }[priority] || "o_dtm_badge_medium";
    }

    stateClass(state) {
        return {
            done: "o_dtm_badge_done",
            in_progress: "o_dtm_badge_progress",
            not_started: "o_dtm_badge_todo",
        }[state] || "o_dtm_badge_todo";
    }
}

registry.category("actions").add("daily_work_task_manager", DailyWorkTaskManager);
