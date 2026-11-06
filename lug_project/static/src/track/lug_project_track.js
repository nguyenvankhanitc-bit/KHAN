/** @odoo-module **/

import { LugProjectList } from "../list/lug_project_list";

/**
 * "Theo dõi dự án" (LugProjectTrack):
 * Uses the same data authority (get_lug_project_list_data, get_lug_project_list_meta,
 * get_lug_project_list_detail) and row decoration (decorateRow) as "Danh sách dự án"
 * while rendering every project as an always-open 3-column Horizontal Dashboard Card.
 * Clicking a project card opens a centered interactive modal containing all tasks
 * of that project grouped by stage.
 */
export class LugProjectTrack extends LugProjectList {
    static template = "lug_project.LugProjectTrack";

    get permKwargs() {
        return { context: { lug_perm_group: this.props.perm?.group || "track" } };
    }

    get activeModalRow() {
        if (!this.state.expandedId) {
            return null;
        }
        return this.state.rows.find((row) => row.id === this.state.expandedId) || null;
    }

    get activeModalDetail() {
        if (!this.state.expandedId) {
            return null;
        }
        return this.state.details[this.state.expandedId] || null;
    }

    async openProjectModal(projectId) {
        if (!projectId) {
            return;
        }
        this.state.expandedId = projectId;
        await this.loadDetail(projectId);
    }

    closeProjectModal() {
        this.state.expandedId = false;
    }

    viewGanttFromModal(projectId) {
        this.closeProjectModal();
        this.viewGantt(projectId);
    }
}
