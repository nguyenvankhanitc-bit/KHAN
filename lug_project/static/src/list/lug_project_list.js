/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const PAGE_SIZE = 35;

const WORKFLOW_OPTIONS = [
    { key: "progress", label: "Đang làm" },
    { key: "pause", label: "Tạm dừng" },
    { key: "done", label: "Hoàn thành" },
    { key: "cancel", label: "Hủy" },
];

export class LugProjectList extends Component {
    static template = "lug_project.LugProjectList";
    static props = {
        onNew: { type: Function, optional: true },
        onGantt: { type: Function, optional: true },
        archived: { type: Boolean, optional: true },
        overdue: { type: Boolean, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.workflowOptions = WORKFLOW_OPTIONS;
        this.state = useState({
            loading: true,
            exporting: false,
            search: "",
            offset: 0,
            total: 0,
            rows: [],
            expandedId: false,
            detailLoading: false,
            details: {},
            selected: {},
            priority: "",
            typeId: "",
            status: "",
            managerId: "",
            datePreset: "",
            dateField: "deadline",
            dateFrom: "",
            dateTo: "",
            types: [],
            managers: [],
            statuses: WORKFLOW_OPTIONS,
        });
        this._loadDebounced = debounce(() => this.loadList(), 300);

        onWillStart(async () => {
            await this.loadMeta();
            await this.loadList();
        });
    }

    get pagerLabel() {
        const total = this.state.total || 0;
        if (!total) {
            return "0 / Tổng số 0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.rows.length, total);
        return `${from}-${to} / Tổng số ${total}`;
    }

    get canPrev() {
        return this.state.offset > 0;
    }

    get canNext() {
        return this.state.offset + this.state.rows.length < this.state.total;
    }

    get selectedIds() {
        return Object.entries(this.state.selected)
            .filter(([, on]) => on)
            .map(([id]) => Number(id));
    }

    get allPageSelected() {
        const rows = this.state.rows;
        return Boolean(rows.length) && rows.every((row) => this.state.selected[row.id]);
    }

    get filterParams() {
        return {
            search: this.state.search,
            priority: this.state.priority || null,
            type_id: this.state.typeId || null,
            status: this.state.status || null,
            manager_id: this.state.managerId || null,
            date_preset: this.state.datePreset || null,
            date_field: this.state.dateField || "deadline",
            date_from: this.state.dateFrom || null,
            date_to: this.state.dateTo || null,
            archived: Boolean(this.props.archived),
            overdue: Boolean(this.props.overdue),
        };
    }

    isExpanded(projectId) {
        return this.state.expandedId === projectId;
    }

    isSelected(projectId) {
        return Boolean(this.state.selected[projectId]);
    }

    progressLabel(detail) {
        const pct = detail.progress_pct || 0;
        const done = detail.progress_done || 0;
        const total = detail.progress_total || 0;
        return `${pct}% (${done}/${total} việc)`;
    }

    keepOpen() {
        return true;
    }

    decorateRow(row) {
        const pct = Math.max(0, Math.min(100, Number(row.progress_pct) || 0));
        const late = Boolean(row.deadline_late);
        const statusTone = late && row.status === "progress" ? "late" : row.status || "progress";
        const donutColor = late ? "#ef4444" : pct >= 50 ? "#22c55e" : "#f59e0b";
        const labels = ["Chuẩn bị", "Thực hiện", "Nghiệm thu", "Đóng DA"];
        const steps = (row.phase && row.phase.steps) || [];
        const type = row.type || {};
        const assignees = row.assignees && row.assignees.users ? row.assignees : { users: [], extra: 0 };
        return Object.assign(row, {
            progress_pct: pct,
            status_tone: statusTone,
            status_badge: statusTone === "late" ? "Trễ hạn" : row.status_label || "Đang làm",
            donut_style: "background: conic-gradient(" + donutColor + " " + pct * 3.6 + "deg, #e2e8f0 0deg);",
            bar_class: late ? "is-late" : pct >= 50 ? "is-high" : "is-mid",
            pills: labels.map((name, index) => ({
                index: index + 1,
                name: name,
                state: (steps[index] && steps[index].state) || "todo",
            })),
            type_tone: type.tone || "none",
            type_label: type.label || "",
            manager_name: row.manager && row.manager.name ? row.manager.name : "—",
            assignees: assignees,
            dl_state: row.deadline_state || "none",
            dl_badge: row.deadline_badge || "Chưa đặt hạn",
        });
    }

    donutStyle(row) {
        const pct = Math.max(0, Math.min(100, Number(row.progress_pct) || 0));
        const color = row.deadline_late ? "#ef4444" : pct >= 50 ? "#22c55e" : "#f59e0b";
        return `background: conic-gradient(${color} ${pct * 3.6}deg, #e2e8f0 0deg);`;
    }

    barClass(row) {
        if (row.deadline_late) {
            return "is-late";
        }
        return (Number(row.progress_pct) || 0) >= 50 ? "is-high" : "is-mid";
    }

    cardStatus(row) {
        if (row.deadline_late && row.status === "progress") {
            return { label: "Trễ hạn", tone: "late" };
        }
        return { label: row.status_label || "Đang làm", tone: row.status || "progress" };
    }

    phasePills(row) {
        const labels = ["Chuẩn bị", "Thực hiện", "Nghiệm thu", "Đóng DA"];
        const steps = row.phase?.steps || [];
        return labels.map((name, index) => {
            const step = steps[index] || {};
            return { index: index + 1, name, state: step.state || "todo" };
        });
    }

    async loadMeta() {
        try {
            const meta = await this.orm.call("project.project", "get_lug_project_list_meta", []);
            this.state.types = meta.types || [];
            this.state.managers = meta.managers || [];
            this.state.statuses = meta.statuses || WORKFLOW_OPTIONS;
        } catch (error) {
            console.error(error);
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.offset = 0;
        this._loadDebounced();
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.offset = 0;
        this.loadList();
    }

    onUrgentOnly() {
        this.state.priority = this.state.priority === "urgent" ? "" : "urgent";
        this.state.offset = 0;
        this.loadList();
    }

    async loadList() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("project.project", "get_lug_project_list_data", [], {
                ...this.filterParams,
                offset: this.state.offset,
                limit: PAGE_SIZE,
            });
            this.state.total = data.total || 0;
            this.state.rows = (data.rows || []).map((row) => this.decorateRow(row));
            if (
                this.state.expandedId &&
                !this.state.rows.some((row) => row.id === this.state.expandedId)
            ) {
                this.state.expandedId = false;
            }
        } catch (error) {
            console.error(error);
            this.state.rows = [];
            this.state.total = 0;
        } finally {
            this.state.loading = false;
        }
    }

    prevPage() {
        if (!this.canPrev) {
            return;
        }
        this.state.offset = Math.max(0, this.state.offset - PAGE_SIZE);
        this.loadList();
    }

    nextPage() {
        if (!this.canNext) {
            return;
        }
        this.state.offset += PAGE_SIZE;
        this.loadList();
    }

    toggleSelect(projectId, ev) {
        ev.stopPropagation();
        this.state.selected[projectId] = !this.state.selected[projectId];
    }

    toggleSelectAll(ev) {
        ev.stopPropagation();
        const next = !this.allPageSelected;
        for (const row of this.state.rows) {
            this.state.selected[row.id] = next;
        }
    }

    async toggleRow(projectId) {
        if (this.state.expandedId === projectId) {
            this.state.expandedId = false;
            return;
        }
        this.state.expandedId = projectId;
        if (!this.state.details[projectId]) {
            await this.loadDetail(projectId);
        }
    }

    async loadDetail(projectId) {
        this.state.detailLoading = projectId;
        try {
            const detail = await this.orm.call(
                "project.project",
                "get_lug_project_list_detail",
                [projectId]
            );
            if (detail) {
                this.state.details[projectId] = detail;
            }
        } catch (error) {
            console.error(error);
        } finally {
            this.state.detailLoading = false;
        }
    }

    async setWorkflow(projectId, state) {
        try {
            await this.orm.call("project.project", "lug_set_workflow_state", [[projectId], state]);
            if (this.state.details[projectId]) {
                this.state.details[projectId].workflow_state = state;
            }
            const row = this.state.rows.find((item) => item.id === projectId);
            if (row) {
                row.status = state;
                row.status_label =
                    WORKFLOW_OPTIONS.find((opt) => opt.key === state)?.label || state;
            }
        } catch (error) {
            console.error(error);
        }
    }

    async togglePriority(projectId, ev) {
        ev.stopPropagation();
        try {
            const urgent = await this.orm.call("project.project", "lug_toggle_priority", [
                [projectId],
            ]);
            const row = this.state.rows.find((item) => item.id === projectId);
            if (row) {
                row.urgent = Boolean(urgent);
            }
        } catch (error) {
            console.error(error);
            this.notification.add("Không đổi được độ ưu tiên.", { type: "danger" });
        }
    }

    onNew() {
        if (this.props.onNew) {
            this.props.onNew();
        }
    }

    async exportExcel() {
        this.state.exporting = true;
        try {
            const ids = this.selectedIds;
            const result = await this.orm.call(
                "project.project",
                "export_lug_project_list_xlsx",
                [],
                ids.length ? { ids } : this.filterParams
            );
            if (!result?.file_base64) {
                this.notification.add("Không có dữ liệu để xuất.", { type: "warning" });
                return;
            }
            this._downloadBase64Excel(result.file_base64, result.filename || "danh_sach_du_an.xlsx");
        } catch (error) {
            console.error(error);
            this.notification.add("Xuất Excel thất bại.", { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(String(b64).replace(/\s/g, ""));
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    async editProject(projectId) {
        const act = await this.orm.call("project.project", "lug_action_open_form", [[projectId]]);
        if (act) {
            await this.action.doAction(act, {
                onClose: async () => {
                    await this.loadList();
                    if (this.state.expandedId === projectId) {
                        delete this.state.details[projectId];
                        await this.loadDetail(projectId);
                    }
                },
            });
        }
    }

    async deleteProject(projectId, ev) {
        ev.stopPropagation();
        this.dialog.add(ConfirmationDialog, {
            title: "Xóa dự án",
            body: "Dự án sẽ được chuyển vào Thùng rác. Bạn có thể khôi phục trong 30 ngày.",
            confirmLabel: "Chuyển vào thùng rác",
            confirmClass: "btn-danger",
            confirm: async () => {
                try {
                    await this.orm.call("project.project", "lug_action_delete", [[projectId]]);
                    delete this.state.selected[projectId];
                    if (this.state.expandedId === projectId) {
                        this.state.expandedId = false;
                    }
                    this.notification.add("Đã chuyển vào Thùng rác.", { type: "success" });
                    await this.loadList();
                } catch (error) {
                    console.error(error);
                    this.notification.add(
                        error?.data?.message || error?.message || "Không xóa được dự án.",
                        { type: "danger" }
                    );
                }
            },
        });
    }

    async restoreProject(projectId, ev) {
        ev.stopPropagation();
        try {
            await this.orm.call("project.project", "lug_action_restore", [[projectId]]);
            delete this.state.selected[projectId];
            if (this.state.expandedId === projectId) {
                this.state.expandedId = false;
            }
            this.notification.add("Đã khôi phục dự án.", { type: "success" });
            await this.loadList();
        } catch (error) {
            console.error(error);
            this.notification.add("Không khôi phục được dự án.", { type: "danger" });
        }
    }

    async addTask(projectId) {
        const detail = this.state.details[projectId];
        const stageId = detail?.stages?.[0]?.id;
        if (!stageId) {
            await this.editProject(projectId);
            return;
        }
        const act = await this.orm.call("project.stage.line", "action_add_task_popup", [[stageId]]);
        if (act) {
            await this.action.doAction(act, {
                onClose: async () => {
                    delete this.state.details[projectId];
                    await this.loadList();
                    if (this.state.expandedId === projectId) {
                        await this.loadDetail(projectId);
                    }
                },
            });
        }
    }

    viewGantt(projectId) {
        if (this.props.onGantt) {
            this.props.onGantt(projectId);
        }
    }

    async openPdf(projectId) {
        const act = await this.orm.call("project.project", "lug_action_open_pdf", [[projectId]]);
        if (act) {
            await this.action.doAction(act);
        }
    }
}
