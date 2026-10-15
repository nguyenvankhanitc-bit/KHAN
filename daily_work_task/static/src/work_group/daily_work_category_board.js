/** @odoo-module **/
/* category-board-cache-bust: 2026-10-08-role-users */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

export class DailyWorkCategoryBoard extends Component {
    static template = "daily_work_task.DailyWorkCategoryBoard";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: true,
            search: "",
            departments: [],
            taskCount: 0,
            /** nodeId -> boolean */
            openMap: {},
            access: { view: true, create: false, write: false, unlink: false },
            editor: null,
        });
        onWillStart(() => this.load());
    }

    get canCreate() {
        return Boolean(this.state.access?.create);
    }

    get canWrite() {
        return Boolean(this.state.access?.write);
    }

    get canSetManager() {
        return Boolean(this.state.access?.set_manager);
    }

    /** Chọn User quản lý cho cả hạng mục (dùng chung bộ chọn user). */
    async openCatEditor(cat) {
        if (!this.canSetManager) {
            this.notification.add(_t("Chỉ Quản lý mới chọn được User quản lý hạng mục."), { type: "warning" });
            return;
        }
        if (this.editorOpen(cat.id, "manager")) {
            return;
        }
        const people = cat.managers || [];
        this.state.editor = {
            taskId: cat.id,
            groupId: cat.group_id,
            role: "manager",
            query: "",
            options: [],
            selectedIds: people.map((u) => u.id),
            selectedUsers: people.map((u) => ({ id: u.id, name: u.name })),
        };
        await this.searchRoleUsers("");
    }

    /** Chọn User quản lý team (dùng chung bộ chọn user). */
    async openTeamEditor(team) {
        if (!this.canSetManager) {
            this.notification.add(_t("Chỉ Quản lý mới chọn được User quản lý team."), { type: "warning" });
            return;
        }
        if (this.editorOpen(team.id, "team_manager")) {
            return;
        }
        const people = team.managers || [];
        this.state.editor = {
            taskId: team.id,
            teamId: team.team_id,
            role: "team_manager",
            query: "",
            options: [],
            selectedIds: people.map((u) => u.id),
            selectedUsers: people.map((u) => ({ id: u.id, name: u.name })),
        };
        await this.searchRoleUsers("");
    }

    _patchTeamManagers(teamNodeId, users) {
        this.state.departments = (this.state.departments || []).map((dept) => ({
            ...dept,
            teams: (dept.teams || []).map((team) =>
                team.id === teamNodeId ? { ...team, managers: users } : team
            ),
        }));
    }

    _patchCatManagers(catId, users) {
        this.state.departments = (this.state.departments || []).map((dept) => ({
            ...dept,
            teams: (dept.teams || []).map((team) => ({
                ...team,
                categories: (team.categories || []).map((cat) =>
                    cat.id === catId ? { ...cat, managers: users } : cat
                ),
            })),
        }));
    }

    get shellActiveNav() {
        return "work_group";
    }

    get pageTitle() {
        return _t("DANH SÁCH HẠNG MỤC CÔNG VIỆC");
    }

    _isOpen(id, defaultOpen = false) {
        if ((this.state.search || "").trim()) {
            return true;
        }
        if (!(id in this.state.openMap)) {
            return defaultOpen;
        }
        return Boolean(this.state.openMap[id]);
    }

    get visibleTree() {
        const q = (this.state.search || "").trim().toLowerCase();
        const searching = Boolean(q);
        let depts = this.state.departments || [];

        if (searching) {
            depts = depts
                .map((dept) => {
                    const deptHit = (dept.title || dept.name || "")
                        .toLowerCase()
                        .includes(q);
                    const teams = (dept.teams || [])
                        .map((team) => {
                            const teamHit =
                                deptHit ||
                                (team.title || team.name || "")
                                    .toLowerCase()
                                    .includes(q);
                            const categories = (team.categories || [])
                                .map((cat) => {
                                    const catHit =
                                        teamHit ||
                                        (cat.title || cat.name || "")
                                            .toLowerCase()
                                            .includes(q);
                                    const tasks = (cat.tasks || []).filter((t) => {
                                        if (catHit) {
                                            return true;
                                        }
                                        const blob = [
                                            t.display_stt,
                                            t.name,
                                            t.team,
                                            t.department,
                                            ...(t.assignees || []).map((u) => u.name),
                                            ...(t.checkers || []).map((u) => u.name),
                                        ]
                                            .filter(Boolean)
                                            .join(" ")
                                            .toLowerCase();
                                        return blob.includes(q);
                                    });
                                    return { ...cat, tasks };
                                })
                                .filter((c) => c.tasks.length);
                            return { ...team, categories };
                        })
                        .filter((t) => t.categories.length);
                    return { ...dept, teams };
                })
                .filter((d) => d.teams.length);
        }

        return depts.map((dept) => {
            const deptOpen = this._isOpen(dept.id, false);
            const teams = (dept.teams || []).map((team) => {
                const teamOpen = this._isOpen(team.id, false);
                const categories = (team.categories || []).map((cat) => {
                    const catOpen = this._isOpen(cat.id, false);
                    return {
                        ...cat,
                        isOpen: catOpen,
                        rowClass:
                            "o_dcb_cat" +
                            (cat.tone === "alt" ? " o_dcb_cat_alt" : "") +
                            (catOpen ? " is-open" : " is-closed"),
                        chevronClass: "o_dcb_chevron" + (catOpen ? " open" : ""),
                    };
                });
                return {
                    ...team,
                    isOpen: teamOpen,
                    categories,
                    rowClass: "o_dcb_team" + (teamOpen ? " is-open" : " is-closed"),
                    chevronClass: "o_dcb_chevron" + (teamOpen ? " open" : ""),
                };
            });
            return {
                ...dept,
                isOpen: deptOpen,
                teams,
                rowClass: "o_dcb_dept" + (deptOpen ? " is-open" : " is-closed"),
                chevronClass: "o_dcb_chevron" + (deptOpen ? " open" : ""),
            };
        });
    }

    _collectIds(departments) {
        const ids = [];
        for (const dept of departments || []) {
            ids.push(dept.id);
            for (const team of dept.teams || []) {
                ids.push(team.id);
                for (const cat of team.categories || []) {
                    ids.push(cat.id);
                }
            }
        }
        return ids;
    }

    _initOpenMap(departments) {
        // Mặc định mở sẵn Phòng ban + Team (chỉ cần bấm Hạng mục để xem công việc con);
        // giữ trạng thái đang mở/đóng khi tải lại (sau khi thêm / sửa)
        const prev = this.state.openMap || {};
        const map = {};
        for (const dept of departments || []) {
            map[dept.id] = dept.id in prev ? prev[dept.id] : true;
            for (const team of dept.teams || []) {
                map[team.id] = team.id in prev ? prev[team.id] : true;
                for (const cat of team.categories || []) {
                    map[cat.id] = cat.id in prev ? prev[cat.id] : false;
                }
            }
        }
        this.state.openMap = map;
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "daily.task.work.group",
                "get_category_board_view",
                [],
                { search: "" }
            );
            this.state.departments = data.departments || [];
            this.state.taskCount = data.task_count || 0;
            this.state.access = data.access || this.state.access;
            this._initOpenMap(this.state.departments);
        } catch (e) {
            this.state.departments = [];
            this.state.openMap = {};
            this.notification.add(
                e?.data?.message || _t("Không tải được bảng hạng mục."),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value || "";
    }

    onToggle(nodeId) {
        if (!nodeId || (this.state.search || "").trim()) {
            return;
        }
        // Chống bấm đúp / bấm nhanh 2 lần (mở rồi đóng ngay → tưởng «không ăn»)
        const now = Date.now();
        if (this._lastToggle && this._lastToggle.id === nodeId && now - this._lastToggle.at < 400) {
            return;
        }
        this._lastToggle = { id: nodeId, at: now };
        const cur =
            nodeId in this.state.openMap
                ? Boolean(this.state.openMap[nodeId])
                : false;
        this.state.openMap = { ...this.state.openMap, [nodeId]: !cur };
    }

    onExpandAll() {
        const map = { ...this.state.openMap };
        for (const id of this._collectIds(this.state.departments)) {
            map[id] = true;
        }
        this.state.openMap = map;
    }

    onCollapseAll() {
        const map = { ...this.state.openMap };
        for (const id of this._collectIds(this.state.departments)) {
            map[id] = false;
        }
        this.state.openMap = map;
    }

    async onCreate() {
        if (!this.canCreate) {
            this.notification.add(_t("Bạn không có quyền thêm hạng mục."), { type: "warning" });
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Thêm hạng mục"),
                res_model: "daily.task.work.group",
                views: [[false, "form"]],
                target: "new",
                context: {
                    form_view_initial_mode: "edit",
                },
            },
            {
                onClose: () => this.load(),
            }
        );
    }

    /** Thêm công việc con cho hạng mục đã có (điền sẵn Hạng mục / Phòng ban / Team / Quản lý). */
    get canUnlink() {
        return Boolean(this.state.access?.unlink);
    }

    /** Xoá được: Phân quyền phân công công việc → dòng «Hạng mục» có tick «Xóa». */
    canDeleteCat() {
        return this.canUnlink;
    }

    /** Xoá hạng mục (vd hạng mục bị trùng): công việc đã dùng → lưu trữ, chưa dùng → xoá hẳn. */
    onDeleteCategory(cat, ev) {
        ev?.stopPropagation?.();
        const ids = (cat.tasks || []).map((t) => t.id);
        if (!ids.length) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Xoá hạng mục"),
            body: `Xoá hạng mục «${cat.name || ""}» cùng ${ids.length} công việc con? Công việc con đã có dữ liệu sẽ được lưu trữ (ẩn), không mất lịch sử.`,
            confirmLabel: _t("Xoá"),
            cancelLabel: _t("Huỷ"),
            confirm: async () => {
                const res = await this.orm.call("daily.task.work.group", "delete_category", [ids]);
                this.notification.add(
                    `Đã xoá hạng mục «${cat.name || ""}»: xoá ${res.deleted}, lưu trữ ${res.archived} công việc con.`,
                    { type: "success" }
                );
                await this.load();
            },
            cancel: () => {},
        });
    }

    /** Xoá 1 công việc con (vd dòng bị trùng). */
    onDeleteTask(cat, task, ev) {
        ev?.stopPropagation?.();
        this.dialog.add(ConfirmationDialog, {
            title: _t("Xoá công việc con"),
            body: `Xoá «${task.name || ""}» khỏi hạng mục «${cat.name || ""}»? Nếu đã có dữ liệu sẽ được lưu trữ (ẩn), không mất lịch sử.`,
            confirmLabel: _t("Xoá"),
            cancelLabel: _t("Huỷ"),
            confirm: async () => {
                await this.orm.call("daily.task.work.group", "delete_category", [[task.id]]);
                this.notification.add(`Đã xoá «${task.name || ""}».`, { type: "success" });
                await this.load();
            },
            cancel: () => {},
        });
    }

    async onAddSubTask(dept, team, cat, ev) {
        ev?.stopPropagation?.();
        if (!this.canCreate) {
            this.notification.add(_t("Bạn không có quyền thêm hạng mục."), { type: "warning" });
            return;
        }
        const first = (cat.tasks || [])[0] || {};
        const deptId = parseInt(String(dept.id || "").replace("dept-", ""), 10) || false;
        const ctx = {
            form_view_initial_mode: "edit",
            default_name: cat.name || "",
        };
        if (deptId) {
            ctx.default_department_id = deptId;
        }
        if (first.team_id) {
            ctx.default_team_id = first.team_id;
        }
        const managers = (cat.managers || []).map((m) => m.id);
        if (managers.length) {
            ctx.default_category_manager_ids = [[6, 0, managers]];
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Thêm công việc con: ") + (cat.name || ""),
                res_model: "daily.task.work.group",
                views: [[false, "form"]],
                target: "new",
                context: ctx,
            },
            { onClose: () => this.load() }
        );
    }

    async onOpenList() {
        await this.action.doAction("daily_work_task.action_daily_task_work_group_list");
    }

    editorOpen(taskId, role) {
        const editor = this.state.editor;
        return Boolean(editor && editor.taskId === taskId && editor.role === role);
    }

    get editorOptions() {
        const editor = this.state.editor;
        if (!editor) {
            return [];
        }
        const seen = new Set();
        const options = [];
        for (const user of [...(editor.selectedUsers || []), ...(editor.options || [])]) {
            if (!user?.id || seen.has(user.id)) {
                continue;
            }
            seen.add(user.id);
            options.push(user);
        }
        return options;
    }

    isEditorSelected(userId) {
        return Boolean(this.state.editor?.selectedIds?.includes(userId));
    }

    async openEditor(task, role) {
        if (!this.canWrite) {
            this.notification.add(_t("Bạn không có quyền sửa hạng mục."), { type: "warning" });
            return;
        }
        if (this.editorOpen(task.id, role)) {
            return;
        }
        const people = role === "assignee" ? task.assignees || [] : task.checkers || [];
        this.state.editor = {
            taskId: task.id,
            role,
            query: "",
            options: [],
            selectedIds: people.map((user) => user.id),
            selectedUsers: people.map((user) => ({ id: user.id, name: user.name })),
        };
        await this.searchRoleUsers("");
    }

    closeEditor() {
        this.state.editor = null;
    }

    async onEditorSearch(ev) {
        if (!this.state.editor) {
            return;
        }
        const query = ev.target.value || "";
        this.state.editor.query = query;
        await this.searchRoleUsers(query);
    }

    async searchRoleUsers(query) {
        try {
            const options = await this.orm.call(
                "daily.task.work.group",
                "search_role_users",
                [query || ""]
            );
            if (this.state.editor) {
                this.state.editor.options = options || [];
            }
        } catch (e) {
            this.notification.add(
                e?.data?.message || _t("Không tải được danh sách user."),
                { type: "danger" }
            );
        }
    }

    async toggleRoleUser(user, ev) {
        const editor = this.state.editor;
        if (!editor || !user?.id) {
            return;
        }
        const checked = Boolean(ev?.target?.checked);
        const selectedIds = editor.selectedIds.filter((id) => id !== user.id);
        let selectedUsers = editor.selectedUsers.filter((item) => item.id !== user.id);
        if (checked) {
            selectedIds.push(user.id);
            selectedUsers = [...selectedUsers, { id: user.id, name: user.name }];
        }
        editor.selectedIds = selectedIds;
        editor.selectedUsers = selectedUsers;
        if (editor.role === "team_manager") {
            try {
                const saved = await this.orm.call("daily.task.team", "set_team_managers", [
                    [editor.teamId],
                    selectedIds,
                ]);
                this._patchTeamManagers(editor.taskId, saved || selectedUsers);
            } catch (e) {
                if (ev?.target) {
                    ev.target.checked = !checked;
                }
                this.notification.add(e?.data?.message || _t("Không lưu được User quản lý team."), {
                    type: "danger",
                });
            }
            return;
        }
        if (editor.role === "manager") {
            try {
                const saved = await this.orm.call("daily.task.work.group", "set_category_managers", [
                    [editor.groupId],
                    selectedIds,
                ]);
                this._patchCatManagers(editor.taskId, saved || selectedUsers);
            } catch (e) {
                if (ev?.target) {
                    ev.target.checked = !checked;
                }
                this.notification.add(e?.data?.message || _t("Không lưu được User quản lý."), {
                    type: "danger",
                });
            }
            return;
        }
        try {
            const saved = await this.orm.call(
                "daily.task.work.group",
                "set_role_users",
                [[editor.taskId], editor.role, selectedIds]
            );
            this._patchRoleUsers(editor.taskId, editor.role, saved || selectedUsers);
        } catch (e) {
            if (ev?.target) {
                ev.target.checked = !checked;
            }
            this.notification.add(
                e?.data?.message || _t("Không lưu được user."),
                { type: "danger" }
            );
        }
    }

    _patchRoleUsers(taskId, role, users) {
        const key = role === "assignee" ? "assignees" : "checkers";
        this.state.departments = (this.state.departments || []).map((dept) => ({
            ...dept,
            teams: (dept.teams || []).map((team) => ({
                ...team,
                categories: (team.categories || []).map((cat) => ({
                    ...cat,
                    tasks: (cat.tasks || []).map((task) =>
                        task.id === taskId ? { ...task, [key]: users } : task
                    ),
                })),
            })),
        }));
    }

    async onOpenTask(task) {
        if (!task?.id) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "daily.task.work.group",
            res_id: task.id,
            views: [[false, "form"]],
            target: "current",
            context: {
                form_view_initial_mode: this.canWrite ? "edit" : "readonly",
            },
        });
    }
}

registry.category("actions").add("daily_work_category_board", DailyWorkCategoryBoard);
