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
            chat: {
                open: false,
                loading: false,
                sending: false,
                taskId: 0,
                taskName: "",
                assigneeName: "",
                messages: [],
                draft: "",
            },
            viewMode: "list",
            detailLeftWidth: this._loadDetailLeftWidth(),
            detail: {
                loading: false,
                saving: false,
                taskId: 0,
                data: null,
                tab: "chat",
                chatDraft: "",
                checklistDraft: "",
                filterQuery: "",
                filterState: "",
                filterAssignee: 0,
            },
        });
        this.chatBodyRef = useRef("chatBody");
        this.detailChatBodyRef = useRef("detailChatBody");
        this.detailShellRef = useRef("detailShell");
        this._detailSplitterDragging = false;
        this._onDetailSplitterMove = this._onDetailSplitterMove.bind(this);
        this._onDetailSplitterUp = this._onDetailSplitterUp.bind(this);
        onWillStart(async () => {
            await this.loadAll();
        });
        onMounted(() => {
            document.addEventListener("pointerdown", this._onDocPointerDown);
        });
        onWillUnmount(() => {
            document.removeEventListener("pointerdown", this._onDocPointerDown);
            this._stopSplitterDrag();
            this._stopDetailSplitterDrag();
        });
    }

    _loadDetailLeftWidth() {
        try {
            const raw = window.localStorage.getItem("daily_work_assign_detail_left_width");
            const n = Number(raw);
            if (Number.isFinite(n) && n >= 200 && n <= 480) {
                return Math.round(n);
            }
        } catch {
            // ignore
        }
        return 280;
    }

    _saveDetailLeftWidth(width) {
        try {
            window.localStorage.setItem(
                "daily_work_assign_detail_left_width",
                String(width)
            );
        } catch {
            // ignore
        }
    }

    _clampDetailLeftWidth(width) {
        const shell = this.detailShellRef.el;
        const maxByShell = shell
            ? Math.max(220, Math.floor(shell.getBoundingClientRect().width - 520))
            : 480;
        return Math.max(200, Math.min(Math.min(480, maxByShell), Math.round(width)));
    }

    onDetailSplitterPointerDown(ev) {
        if (ev.button !== undefined && ev.button !== 0) {
            return;
        }
        if (ev.target.closest(".o_dwa_detail_splitter_btn")) {
            return;
        }
        ev.preventDefault();
        this._detailSplitterDragging = true;
        document.body.classList.add("o_dwa_resizing");
        document.addEventListener("pointermove", this._onDetailSplitterMove);
        document.addEventListener("pointerup", this._onDetailSplitterUp);
        document.addEventListener("pointercancel", this._onDetailSplitterUp);
    }

    _onDetailSplitterMove(ev) {
        if (!this._detailSplitterDragging) {
            return;
        }
        const shell = this.detailShellRef.el;
        if (!shell) {
            return;
        }
        const left = shell.getBoundingClientRect().left;
        this.state.detailLeftWidth = this._clampDetailLeftWidth(ev.clientX - left);
    }

    _onDetailSplitterUp() {
        if (!this._detailSplitterDragging) {
            return;
        }
        this._stopDetailSplitterDrag();
        this._saveDetailLeftWidth(this.state.detailLeftWidth);
    }

    _stopDetailSplitterDrag() {
        this._detailSplitterDragging = false;
        document.body.classList.remove("o_dwa_resizing");
        document.removeEventListener("pointermove", this._onDetailSplitterMove);
        document.removeEventListener("pointerup", this._onDetailSplitterUp);
        document.removeEventListener("pointercancel", this._onDetailSplitterUp);
    }

    nudgeDetailSplitter(delta) {
        this.state.detailLeftWidth = this._clampDetailLeftWidth(
            this.state.detailLeftWidth + delta
        );
        this._saveDetailLeftWidth(this.state.detailLeftWidth);
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
        const assignee = this.selectedAssignee;
        const assigneeUid = assignee ? Number(assignee.user_id) || 0 : 0;
        return this.state.workGroups
            .filter((g) => {
                if (Number(g.department_id) !== deptId) {
                    return false;
                }
                // Chưa chọn NV → chưa hiện hạng mục (cần biết User áp dụng của người nhận)
                if (!assignee) {
                    return false;
                }
                const allowed = Array.isArray(g.user_ids) ? g.user_ids : [];
                // Để trống User áp dụng = cả phòng ban
                if (!allowed.length) {
                    return true;
                }
                // Chỉ hạng mục mà người được giao nằm trong User áp dụng
                return assigneeUid && allowed.map(Number).includes(assigneeUid);
            })
            .slice()
            .sort((a, b) => {
                const sa = Number(a.sequence);
                const sb = Number(b.sequence);
                const seqA = Number.isFinite(sa) ? sa : 0;
                const seqB = Number.isFinite(sb) ? sb : 0;
                if (seqA !== seqB) {
                    return seqA - seqB;
                }
                const na = String(a.name || "");
                const nb = String(b.name || "");
                if (na !== nb) {
                    return na.localeCompare(nb, "vi");
                }
                return (Number(a.id) || 0) - (Number(b.id) || 0);
            });
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
        const match = this.filteredWorkGroups.find((g) => Number(g.id) === wgId);
        if (!match || Number(match.department_id) !== deptId) {
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

    async openDiscussion(task) {
        if (!task?.id) {
            return;
        }
        this.state.chat.open = true;
        this.state.chat.loading = true;
        this.state.chat.taskId = task.id;
        this.state.chat.taskName = task.name || "";
        this.state.chat.assigneeName = task.assignee_name || "";
        this.state.chat.draft = "";
        this.state.chat.messages = [];
        try {
            const data = await this.orm.call("daily.task", "get_task_discussion", [
                task.id,
            ]);
            this.state.chat.taskName = data.task_name || task.name || "";
            this.state.chat.assigneeName = data.assignee_name || task.assignee_name || "";
            this.state.chat.messages = data.messages || [];
            // Cập nhật badge trên dòng
            const row = this.state.tasks.find((t) => t.id === task.id);
            if (row) {
                row.discussion_count = data.discussion_count || 0;
                row.discussion_unread = 0;
            }
            this._scrollChatToEnd();
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không mở được thảo luận."),
                { type: "danger" }
            );
            this.state.chat.open = false;
        } finally {
            this.state.chat.loading = false;
        }
    }

    closeDiscussion() {
        this.state.chat.open = false;
        this.state.chat.draft = "";
        this.state.chat.messages = [];
        this.state.chat.taskId = 0;
    }

    _scrollChatToEnd() {
        requestAnimationFrame(() => {
            const el = this.chatBodyRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    onChatKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendDiscussion();
        }
    }

    async sendDiscussion() {
        const text = (this.state.chat.draft || "").trim();
        if (!text || !this.state.chat.taskId || this.state.chat.sending) {
            return;
        }
        this.state.chat.sending = true;
        try {
            const data = await this.orm.call("daily.task", "post_task_discussion", [
                this.state.chat.taskId,
                text,
            ]);
            this.state.chat.draft = "";
            this.state.chat.messages = data.messages || [];
            const row = this.state.tasks.find((t) => t.id === this.state.chat.taskId);
            if (row) {
                row.discussion_count = data.discussion_count || 0;
                row.discussion_unread = 0;
            }
            this._scrollChatToEnd();
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không gửi được tin nhắn."),
                { type: "danger" }
            );
        } finally {
            this.state.chat.sending = false;
        }
    }

    discussionBadge(task) {
        return Number(task.discussion_unread || 0) || Number(task.discussion_count || 0) || 0;
    }

    get detailSidebarTasks() {
        const q = normalizeText(this.state.detail.filterQuery);
        const st = this.state.detail.filterState;
        const aid = Number(this.state.detail.filterAssignee) || 0;
        return (this.state.tasks || []).filter((t) => {
            if (st && t.state !== st) {
                return false;
            }
            if (aid) {
                const emp = this.state.employees.find((e) => Number(e.id) === aid);
                const bridgeId = emp?.bridge_id ? Number(emp.bridge_id) : 0;
                const matchHr = Number(t.hr_employee_id) === aid;
                const matchBridge = bridgeId && Number(t.assignee_id) === bridgeId;
                if (!matchHr && !matchBridge) {
                    return false;
                }
            }
            if (!q) {
                return true;
            }
            return (
                normalizeText(t.name).includes(q) ||
                normalizeText(t.assignee_name).includes(q) ||
                normalizeText(t.work_group_label).includes(q)
            );
        });
    }

    async openTaskDetail(task) {
        if (!task?.id) {
            return;
        }
        this.state.viewMode = "detail";
        this.state.detail.taskId = task.id;
        this.state.detail.tab = "chat";
        this.state.detail.chatDraft = "";
        this.state.detail.checklistDraft = "";
        this.state.chat.open = false;
        await this.loadTaskDetail(task.id);
    }

    async loadTaskDetail(taskId) {
        this.state.detail.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_task_detail", [taskId]);
            this.state.detail.data = data;
            this.state.detail.taskId = data.id;
            this._scrollDetailChatToEnd();
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không mở được chi tiết công việc."),
                { type: "danger" }
            );
            this.state.viewMode = "list";
        } finally {
            this.state.detail.loading = false;
        }
    }

    closeTaskDetail() {
        this.state.viewMode = "list";
        this.state.detail.data = null;
        this.state.detail.taskId = 0;
        this.onRefresh();
    }

    async selectDetailTask(task) {
        if (!task?.id || task.id === this.state.detail.taskId) {
            return;
        }
        this.state.detail.taskId = task.id;
        this.state.detail.chatDraft = "";
        await this.loadTaskDetail(task.id);
    }

    setDetailTab(tab) {
        this.state.detail.tab = tab;
        if (tab === "chat") {
            this._scrollDetailChatToEnd();
        }
    }

    _scrollDetailChatToEnd() {
        requestAnimationFrame(() => {
            const el = this.detailChatBodyRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    onDetailChatKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendDetailDiscussion();
        }
    }

    async sendDetailDiscussion() {
        const text = (this.state.detail.chatDraft || "").trim();
        const taskId = this.state.detail.taskId;
        if (!text || !taskId || this.state.detail.saving) {
            return;
        }
        this.state.detail.saving = true;
        try {
            await this.orm.call("daily.task", "post_task_discussion", [taskId, text]);
            this.state.detail.chatDraft = "";
            await this.loadTaskDetail(taskId);
            const row = this.state.tasks.find((t) => t.id === taskId);
            if (row && this.state.detail.data) {
                row.discussion_count = this.state.detail.data.discussion_count || 0;
                row.discussion_unread = 0;
            }
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không gửi được tin nhắn."),
                { type: "danger" }
            );
        } finally {
            this.state.detail.saving = false;
        }
    }

    async onToggleChecklist(item) {
        try {
            const data = await this.orm.call("daily.task", "set_task_checklist_done", [
                item.id,
                !item.done,
            ]);
            this.state.detail.data = data;
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật checklist."), {
                type: "danger",
            });
        }
    }

    async onAddChecklist(ev) {
        ev?.preventDefault?.();
        const name = (this.state.detail.checklistDraft || "").trim();
        if (!name || !this.state.detail.taskId) {
            return;
        }
        try {
            const data = await this.orm.call("daily.task", "add_task_checklist_item", [
                this.state.detail.taskId,
                name,
            ]);
            this.state.detail.checklistDraft = "";
            this.state.detail.data = data;
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thêm checklist."), {
                type: "danger",
            });
        }
    }

    async onDetailStateChange(ev) {
        const state = ev.target.value;
        if (!this.state.detail.taskId) {
            return;
        }
        try {
            const data = await this.orm.call("daily.task", "update_task_detail_fields", [
                this.state.detail.taskId,
                { state },
            ]);
            this.state.detail.data = data;
            const row = this.state.tasks.find((t) => t.id === this.state.detail.taskId);
            if (row) {
                row.state = data.state;
                row.state_label = data.state_label;
            }
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật trạng thái."), {
                type: "danger",
            });
        }
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
