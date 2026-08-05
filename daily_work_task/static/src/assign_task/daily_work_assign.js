/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

function normalizeText(text) {
    return String(text || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();
}

export class DailyWorkAssign extends Component {
    static template = "daily_work_task.DailyWorkAssign";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.assigneeBoxRef = useRef("assigneeBox");
        this.layoutBoxRef = useRef("layoutBox");
        this._onDocPointerDown = this._onDocPointerDown.bind(this);
        this._onSplitterMove = this._onSplitterMove.bind(this);
        this._onSplitterUp = this._onSplitterUp.bind(this);
        this._splitterDragging = false;
        this.state = useState({
            loading: true,
            saving: false,
            employees: [],
            departments: [],
            workGroups: [],
            priorities: [],
            states: [],
            tasks: [],
            filterAssignee: 0,
            leftWidth: this._loadLeftWidth(),
            form: this.emptyForm(),
            assigneeQuery: "",
            assigneeOpen: false,
            assigneeHighlight: -1,
        });
        onWillStart(async () => {
            await this.loadAll();
        });
        onMounted(() => {
            document.addEventListener("pointerdown", this._onDocPointerDown);
        });
        onWillUnmount(() => {
            document.removeEventListener("pointerdown", this._onDocPointerDown);
            this._stopSplitterDrag();
        });
    }

    _loadLeftWidth() {
        try {
            const raw = window.localStorage.getItem("daily_work_assign_left_width");
            const n = Number(raw);
            if (Number.isFinite(n) && n >= 240 && n <= 720) {
                return Math.round(n);
            }
        } catch {
            // ignore
        }
        return 340;
    }

    _saveLeftWidth(width) {
        try {
            window.localStorage.setItem("daily_work_assign_left_width", String(width));
        } catch {
            // ignore
        }
    }

    _clampLeftWidth(width) {
        const layout = this.layoutBoxRef.el;
        const maxByLayout = layout
            ? Math.max(280, Math.floor(layout.getBoundingClientRect().width - 320))
            : 720;
        const min = 240;
        const max = Math.min(720, maxByLayout);
        return Math.max(min, Math.min(max, Math.round(width)));
    }

    onSplitterPointerDown(ev) {
        if (ev.button !== undefined && ev.button !== 0) {
            return;
        }
        // Nút mũi tên dùng click riêng — không bắt đầu kéo
        if (ev.target.closest(".o_dwa_splitter_btn")) {
            return;
        }
        ev.preventDefault();
        this._splitterDragging = true;
        document.body.classList.add("o_dwa_resizing");
        document.addEventListener("pointermove", this._onSplitterMove);
        document.addEventListener("pointerup", this._onSplitterUp);
        document.addEventListener("pointercancel", this._onSplitterUp);
    }

    _onSplitterMove(ev) {
        if (!this._splitterDragging) {
            return;
        }
        const layout = this.layoutBoxRef.el;
        if (!layout) {
            return;
        }
        const left = layout.getBoundingClientRect().left;
        this.state.leftWidth = this._clampLeftWidth(ev.clientX - left);
    }

    _onSplitterUp() {
        if (!this._splitterDragging) {
            return;
        }
        this._stopSplitterDrag();
        this._saveLeftWidth(this.state.leftWidth);
    }

    _stopSplitterDrag() {
        this._splitterDragging = false;
        document.body.classList.remove("o_dwa_resizing");
        document.removeEventListener("pointermove", this._onSplitterMove);
        document.removeEventListener("pointerup", this._onSplitterUp);
        document.removeEventListener("pointercancel", this._onSplitterUp);
    }

    nudgeSplitter(delta) {
        this.state.leftWidth = this._clampLeftWidth(this.state.leftWidth + delta);
        this._saveLeftWidth(this.state.leftWidth);
    }

    emptyForm() {
        return {
            name: "",
            deadline: "",
            department_id: 0,
            assignee_id: 0,
            work_group_id: "",
            priority: "medium",
            state: "not_started",
            note: "",
        };
    }

    get filteredWorkGroups() {
        const deptId = Number(this.state.form.department_id) || 0;
        if (!deptId) {
            return [];
        }
        return this.state.workGroups.filter(
            (g) => Number(g.department_id) === deptId
        );
    }

    get filteredTasks() {
        const aid = Number(this.state.filterAssignee) || 0;
        const tasks = [...(this.state.tasks || [])].sort((a, b) => {
            const da = a.deadline || "9999-99-99";
            const db = b.deadline || "9999-99-99";
            if (da !== db) {
                return da < db ? -1 : 1;
            }
            return (a.id || 0) - (b.id || 0);
        });
        if (!aid) {
            return tasks;
        }
        return tasks.filter((t) => Number(t.hr_employee_id) === aid);
    }

    /** Nhóm việc theo nhân sự — mỗi nhóm là trình đơn thả xuống, việc sắp theo hạn tăng dần. */
    get taskGroups() {
        const map = new Map();
        for (const task of this.filteredTasks) {
            const key = Number(task.hr_employee_id) || 0;
            if (!map.has(key)) {
                map.set(key, {
                    key,
                    assignee_name: task.assignee_name || "Chưa gán",
                    department_label: task.department_label || "",
                    tasks: [],
                });
            }
            map.get(key).tasks.push(task);
        }
        const groups = [...map.values()];
        groups.sort((a, b) =>
            String(a.assignee_name || "").localeCompare(String(b.assignee_name || ""), "vi")
        );
        for (const g of groups) {
            g.tasks.sort((a, b) => {
                const da = a.deadline || "9999-99-99";
                const db = b.deadline || "9999-99-99";
                if (da !== db) {
                    return da < db ? -1 : 1;
                }
                return (a.id || 0) - (b.id || 0);
            });
        }
        return groups;
    }

    /** Dropdown lọc: chỉ nhân viên đang có việc chưa hoàn thành. */
    get assigneeFilterOptions() {
        const seen = new Map();
        for (const t of this.state.tasks || []) {
            const id = Number(t.hr_employee_id) || 0;
            if (!id || seen.has(id)) {
                continue;
            }
            seen.set(id, {
                id,
                name: t.assignee_name || `NV #${id}`,
            });
        }
        return [...seen.values()].sort((a, b) =>
            String(a.name).localeCompare(String(b.name), "vi")
        );
    }

    get selectedAssignee() {
        const id = Number(this.state.form.assignee_id) || 0;
        return this.state.employees.find((e) => e.id === id) || false;
    }

    get assigneeSuggestions() {
        const q = normalizeText(this.state.assigneeQuery);
        if (!q) {
            return this.state.employees.slice(0, 12);
        }
        const scored = [];
        for (const emp of this.state.employees) {
            const name = normalizeText(emp.name);
            const dept = normalizeText(emp.department);
            const email = normalizeText(emp.email);
            const hay = `${name} ${dept} ${email}`;
            if (!hay.includes(q)) {
                continue;
            }
            let score = 100;
            if (name.startsWith(q)) {
                score = 1;
            } else if (name.includes(q)) {
                score = 2;
            } else if (dept.includes(q)) {
                score = 3;
            } else {
                score = 4;
            }
            scored.push({ emp, score });
        }
        scored.sort((a, b) => a.score - b.score || a.emp.name.localeCompare(b.emp.name, "vi"));
        return scored.slice(0, 15).map((x) => x.emp);
    }

    async loadAll() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_assign_bootstrap", []);
            this.state.employees = data.employees || [];
            this.state.departments = data.departments || [];
            this.state.workGroups = data.work_groups || [];
            this.state.priorities = data.priorities || [];
            this.state.states = data.states || [];
            this.state.tasks = data.tasks || [];
        } finally {
            this.state.loading = false;
        }
    }

    _syncWorkGroupWithDepartment() {
        const deptId = Number(this.state.form.department_id) || 0;
        const wgId = Number(this.state.form.work_group_id) || 0;
        if (!wgId) {
            return;
        }
        const match = this.state.workGroups.find(
            (g) => Number(g.id) === wgId && Number(g.department_id) === deptId
        );
        if (!match) {
            this.state.form.work_group_id = "";
        }
    }

    _onDocPointerDown(ev) {
        const box = this.assigneeBoxRef.el;
        if (!box || !this.state.assigneeOpen) {
            return;
        }
        if (!box.contains(ev.target)) {
            this.state.assigneeOpen = false;
            this.state.assigneeHighlight = -1;
            // Nếu đã chọn rồi thì giữ label; nếu chưa chọn thì giữ query
            if (this.selectedAssignee) {
                this.state.assigneeQuery = this._assigneeLabel(this.selectedAssignee);
            }
        }
    }

    _assigneeLabel(emp) {
        if (!emp) {
            return "";
        }
        return emp.department ? `${emp.name} — ${emp.department}` : emp.name;
    }

    onAssigneeFocus() {
        this.state.assigneeOpen = true;
        if (this.selectedAssignee && !this.state.assigneeQuery) {
            this.state.assigneeQuery = this._assigneeLabel(this.selectedAssignee);
        }
    }

    onAssigneeInput() {
        this.state.form.assignee_id = 0;
        this.state.assigneeOpen = true;
        this.state.assigneeHighlight = this.assigneeSuggestions.length ? 0 : -1;
    }

    onAssigneeKeydown(ev) {
        const list = this.assigneeSuggestions;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.assigneeOpen = true;
            if (!list.length) {
                return;
            }
            this.state.assigneeHighlight =
                this.state.assigneeHighlight < list.length - 1
                    ? this.state.assigneeHighlight + 1
                    : 0;
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            if (!list.length) {
                return;
            }
            this.state.assigneeHighlight =
                this.state.assigneeHighlight > 0
                    ? this.state.assigneeHighlight - 1
                    : list.length - 1;
        } else if (ev.key === "Enter") {
            if (this.state.assigneeOpen && this.state.assigneeHighlight >= 0 && list[this.state.assigneeHighlight]) {
                ev.preventDefault();
                this.selectAssignee(list[this.state.assigneeHighlight]);
            }
        } else if (ev.key === "Escape") {
            this.state.assigneeOpen = false;
            this.state.assigneeHighlight = -1;
        }
    }

    selectAssignee(emp) {
        this.state.form.assignee_id = emp.id;
        this.state.assigneeQuery = this._assigneeLabel(emp);
        this.state.assigneeOpen = false;
        this.state.assigneeHighlight = -1;
        // Auto Bộ phận theo hồ sơ nhân viên
        this.state.form.department_id = emp.department_id ? Number(emp.department_id) : 0;
        this._syncWorkGroupWithDepartment();
    }

    clearAssignee() {
        this.state.form.assignee_id = 0;
        this.state.form.department_id = 0;
        this.state.form.work_group_id = "";
        this.state.assigneeQuery = "";
        this.state.assigneeOpen = false;
        this.state.assigneeHighlight = -1;
    }

    get autoDepartmentLabel() {
        const emp = this.selectedAssignee;
        if (!emp) {
            return "";
        }
        if (emp.department) {
            return emp.department;
        }
        const deptId = Number(emp.department_id || this.state.form.department_id) || 0;
        if (deptId) {
            const d = this.state.departments.find((x) => Number(x.id) === deptId);
            if (d?.name) {
                return d.name;
            }
        }
        return "";
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
        if (!Number(f.assignee_id)) {
            this.notification.add(_t("Vui lòng chọn người được giao từ danh sách gợi ý."), {
                type: "warning",
            });
            return;
        }
        this.state.saving = true;
        try {
            const created = await this.orm.call("daily.task", "create_from_assign", [
                {
                    name: f.name.trim(),
                    deadline: f.deadline,
                    department_id: Number(f.department_id) || false,
                    assignee_id: Number(f.assignee_id),
                    work_group_id: Number(f.work_group_id) || false,
                    priority: f.priority,
                    state: f.state || "not_started",
                    note: f.note,
                },
            ]);
            const assigneeName =
                (this.state.employees.find((e) => e.id === Number(f.assignee_id)) || {}).name ||
                "nhân viên";
            const keptAssigneeId = f.assignee_id;
            const keptDept = f.department_id;
            const keptWorkGroup = f.work_group_id;
            this.state.form = {
                ...this.emptyForm(),
                department_id: keptDept,
                assignee_id: keptAssigneeId,
                work_group_id: keptWorkGroup,
                priority: "medium",
                state: "not_started",
            };
            const kept = this.state.employees.find((e) => e.id === Number(keptAssigneeId));
            this.state.assigneeQuery = kept ? this._assigneeLabel(kept) : "";
            this.state.tasks = await this.orm.call("daily.task", "get_assign_tasks", []);
            this.notification.add(
                `Đã giao việc cho ${assigneeName}. Người nhận sẽ thấy thông báo trên Discuss.`,
                { type: "success" }
            );
            if (created?.id) {
                this.state.filterAssignee = Number(keptAssigneeId);
            }
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể giao việc."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onRefresh() {
        this.state.tasks = await this.orm.call("daily.task", "get_assign_tasks", []);
    }

    priorityClass(priority) {
        return (
            {
                high: "o_dwa_badge_high",
                medium: "o_dwa_badge_medium",
                low: "o_dwa_badge_low",
            }[priority] || "o_dwa_badge_medium"
        );
    }

    stateBadgeClass(state) {
        return (
            {
                done: "o_dwa_state_done",
                in_progress: "o_dwa_state_progress",
                not_started: "o_dwa_state_todo",
            }[state] || "o_dwa_state_todo"
        );
    }
}

registry.category("actions").add("daily_work_assign", DailyWorkAssign);
