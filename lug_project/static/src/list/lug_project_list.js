/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

const PAGE_SIZE = 35;

const WORKFLOW_OPTIONS = [
    { key: "todo", label: "Chưa bắt đầu" },
    { key: "progress", label: "Đang thực hiện" },
    { key: "done", label: "Hoàn thành" },
    { key: "closed", label: "Đóng" },
];

export class LugProjectList extends Component {
    static template = "lug_project.LugProjectList";
    static props = {
        onNew: { type: Function, optional: true },
        onGantt: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.workflowOptions = WORKFLOW_OPTIONS;
        this.state = useState({
            loading: true,
            search: "",
            offset: 0,
            total: 0,
            rows: [],
            expandedId: false,
            detailLoading: false,
            details: {},
        });
        this._loadDebounced = debounce(() => this.loadList(), 300);

        onWillStart(async () => {
            await this.loadList();
        });
    }

    get pagerLabel() {
        const total = this.state.total || 0;
        if (!total) {
            return "0 / 0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.rows.length, total);
        return `${from}-${to} / ${total}`;
    }

    get canPrev() {
        return this.state.offset > 0;
    }

    get canNext() {
        return this.state.offset + this.state.rows.length < this.state.total;
    }

    isExpanded(projectId) {
        return this.state.expandedId === projectId;
    }

    progressLabel(detail) {
        const pct = detail.progress_pct || 0;
        const done = detail.progress_done || 0;
        const total = detail.progress_total || 0;
        return `${pct}% (${done}/${total} việc)`;
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.offset = 0;
        this._loadDebounced();
    }

    async loadList() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("project.project", "get_lug_project_list_data", [], {
                search: this.state.search,
                offset: this.state.offset,
                limit: PAGE_SIZE,
            });
            this.state.total = data.total || 0;
            this.state.rows = data.rows || [];
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

    onNew() {
        if (this.props.onNew) {
            this.props.onNew();
        }
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
