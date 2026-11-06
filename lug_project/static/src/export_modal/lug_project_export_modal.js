/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class LugProjectExportModal extends Component {
    static template = "lug_project.LugProjectExportModal";
    static props = {
        close: { type: Function },
        onExport: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            exporting: false,
            projects: [],
            selectedIds: new Set(),
            searchTerm: "",
        });

        onWillStart(async () => {
            await this.loadProjects();
        });
    }

    async loadProjects() {
        this.state.loading = true;
        try {
            const projects = await this.orm.search_read(
                "project.project",
                [["active", "=", true]],
                ["id", "name", "code", "date_start", "date_end"],
                { order: "lug_stt, id", limit: 1000 }
            );
            this.state.projects = projects;
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Không thể tải danh sách dự án.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    get filteredProjects() {
        const term = (this.state.searchTerm || "").trim().toLowerCase();
        if (!term) {
            return this.state.projects;
        }
        return this.state.projects.filter((p) => {
            const name = (p.name || "").toLowerCase();
            const code = (p.code || "").toLowerCase();
            return name.includes(term) || code.includes(term);
        });
    }

    get isAllSelected() {
        const list = this.filteredProjects;
        return list.length > 0 && list.every((p) => this.state.selectedIds.has(p.id));
    }

    get selectedCount() {
        return this.state.selectedIds.size;
    }

    toggleProject(id) {
        if (this.state.selectedIds.has(id)) {
            this.state.selectedIds.delete(id);
        } else {
            this.state.selectedIds.add(id);
        }
    }

    toggleSelectAll() {
        const list = this.filteredProjects;
        if (this.isAllSelected) {
            for (const p of list) {
                this.state.selectedIds.delete(p.id);
            }
        } else {
            for (const p of list) {
                this.state.selectedIds.add(p.id);
            }
        }
    }

    async onConfirmExport() {
        if (this.state.selectedIds.size === 0) {
            this.notification.add("Vui lòng chọn ít nhất 1 dự án để xuất báo cáo.", {
                type: "warning",
            });
            return;
        }
        this.state.exporting = true;
        try {
            await this.props.onExport(Array.from(this.state.selectedIds));
            this.props.close();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Xuất báo cáo thất bại.",
                { type: "danger" }
            );
        } finally {
            this.state.exporting = false;
        }
    }

    onClose() {
        if (!this.state.exporting) {
            this.props.close();
        }
    }
}
