/** @odoo-module **/
/* assign-board-cache-bust: 2026-10-08-v9-add-popup-white */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

export class DailyWorkAssignBoard extends Component {
    static template = "daily_work_task.DailyWorkAssignBoard";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.isEditMode = Boolean(
            this.props.action?.context?.daily_work_assign_edit
            || this.props.action?.context?.params?.daily_work_assign_edit
        );
        this.assignFeature =
            this.props.action?.context?.daily_work_assign_feature
            || this.props.action?.context?.params?.daily_work_assign_feature
            || (this.isEditMode ? "add" : "list");
        this.state = useState({
            loading: true,
            exporting: false,
            search: "",
            monthLabel: "",
            sections: [],
            taskCount: 0,
            access: { view: true, create: false, write: false, unlink: false },
        });
        this._onOpenCreate = () => this.onCreateTask();
        onWillStart(() => this.load());
        onMounted(() => {
            window.addEventListener("daily-work-open-assign-create", this._onOpenCreate);
            if (this.isEditMode) {
                this.onCreateTask();
            }
        });
        onWillUnmount(() => {
            window.removeEventListener("daily-work-open-assign-create", this._onOpenCreate);
        });
    }

    get canCreate() {
        return Boolean(this.state.access?.create);
    }

    get canWrite() {
        return Boolean(this.state.access?.write);
    }

    get shellActiveNav() {
        return this.isEditMode ? "team_assign_add" : "team_assign_list";
    }

    get pageTitle() {
        return _t("BẢNG PHÂN CÔNG CÔNG VIỆC TEAM");
    }

    get modeBadge() {
        return this.isEditMode ? _t("Chế độ: Nhập / Sửa") : _t("Chế độ: Chỉ xem");
    }

    get visibleSections() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.state.sections;
        }
        return (this.state.sections || [])
            .map((sec) => {
                const tasks = (sec.tasks || []).filter((t) => this._taskMatch(t, q));
                return { ...sec, tasks };
            })
            .filter((sec) => sec.tasks.length);
    }

    _taskMatch(task, q) {
        const blob = [
            task.display_stt,
            task.category,
            task.name,
            task.note,
            ...(task.south || []).map((u) => u.name),
            ...(task.dtt || []).map((u) => u.name),
            ...(task.north || []).map((u) => u.name),
            ...(task.office || []).map((u) => u.name),
            ...(task.assignee || []).map((u) => u.name),
            ...(task.checker || []).map((u) => u.name),
            ...(task.collab || []).map((u) => u.name),
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
        return blob.includes(q);
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "daily.task.assign",
                "get_assign_board_data",
                [],
                {
                    search: "",
                    context: { daily_work_assign_feature: this.assignFeature },
                }
            );
            this.state.monthLabel = data.month_label || "";
            this.state.sections = data.sections || [];
            this.state.taskCount = data.task_count || 0;
            this.state.access = data.access || this.state.access;
        } catch (e) {
            this.state.sections = [];
            this.notification.add(e?.data?.message || _t("Không tải được bảng phân công."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value || "";
    }

    async onCreateTask() {
        if (!this.canCreate) {
            this.notification.add(_t("Bạn không có quyền thêm phân công."), { type: "warning" });
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Thêm phân công công việc"),
                res_model: "daily.task.assign",
                views: [[false, "form"]],
                target: "new",
                context: {
                    form_view_initial_mode: "edit",
                    daily_work_assign_feature: this.assignFeature,
                },
            },
            {
                onClose: () => this.load(),
            }
        );
    }

    async onOpenTask(task, ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        if (!task?.id) {
            return;
        }
        const editable = this.isEditMode && this.canWrite;
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: task.name || _t("Phân công công việc"),
                res_model: "daily.task.assign",
                res_id: task.id,
                views: [[false, "form"]],
                target: "new",
                context: {
                    form_view_initial_mode: editable ? "edit" : "readonly",
                    daily_work_assign_feature: this.assignFeature,
                },
            },
            {
                onClose: () => this.load(),
            }
        );
    }

    onPrint() {
        window.print();
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Bang_Phan_Cong.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async onExportExcel() {
        this.state.exporting = true;
        try {
            const result = await this.orm.call(
                "daily.task.assign",
                "export_assign_board_excel",
                [],
                { search: this.state.search || "" }
            );
            if (!result?.file_base64) {
                throw new Error(_t("Không nhận được file Excel."));
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add(_t("Đã xuất bảng phân công."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_assign_board", DailyWorkAssignBoard);
