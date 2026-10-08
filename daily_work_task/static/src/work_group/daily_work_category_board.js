/** @odoo-module **/
/* category-board-cache-bust: 2026-10-08-role-users */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
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

    get shellActiveNav() {
        return "work_group";
    }

    get pageTitle() {
        return _t("BẢNG HẠNG MỤC CÔNG VIỆC");
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
        const map = {};
        for (const id of this._collectIds(departments)) {
            map[id] = false;
        }
        this.state.openMap = map;
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "daily.task.work.group",
                "get_category_board_data",
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
