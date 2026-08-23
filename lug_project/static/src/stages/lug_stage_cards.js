/** @odoo-module **/
/* stage-multi-assignee-v1 */

import { onWillStart, useEffect, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const HEADER_COLORS = ["#7c3aed", "#2563eb", "#059669", "#d97706", "#db2777", "#0891b2"];

const DEFAULT_STAGE_NAMES = new Set([
    "CHUẨN BỊ & KHẢO SÁT",
    "TRIỂN KHAI & BÁN HÀNG",
    "LẮP ĐẶT & HOÀN THIỆN",
    "NGHIỆM THU & BÀN GIAO",
    "BẢO HÀNH & HỖ TRỢ",
    "ĐÓNG DỰ ÁN",
    "Giai đoạn mới",
]);

const STATE_LABEL = {
    draft: "Chưa bắt đầu",
    in_progress: "Đang làm",
    done: "Hoàn thành",
};

function formatDate(value) {
    if (!value) {
        return "—";
    }
    const text = String(value);
    const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!iso) {
        return text;
    }
    return `${iso[3]}/${iso[2]}/${iso[1]}`;
}

function formatMoney(value) {
    const number = Number(value || 0);
    return number.toLocaleString("vi-VN");
}

function many2oneName(value) {
    if (!value) {
        return "—";
    }
    if (Array.isArray(value)) {
        return value[1] || "—";
    }
    return value.display_name || value.name || "—";
}

function many2oneId(value) {
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0] || false;
    }
    return value.id || false;
}

export class LugStageCardsField extends X2ManyField {
    static template = "lug_project.LugStageCardsField";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            tasksByStage: {},
            collapsed: {},
        });
        this.canOpenRecord = false;
        onWillStart(() => this._refreshTasks());
        useEffect(
            () => {
                this._refreshTasks();
            },
            () => [this._stageIdKey()]
        );
    }

    get canEdit() {
        return this.canCreate && !this.props.readonly;
    }

    get stages() {
        return (this.list.records || []).slice().sort((a, b) => {
            const seq = (a.data.sequence || 0) - (b.data.sequence || 0);
            if (seq) {
                return seq;
            }
            return (a.resId || 0) - (b.resId || 0);
        });
    }

    get cards() {
        return this.stages.map((stage, index) => {
            const stageId = typeof stage.resId === "number" ? stage.resId : false;
            const tasks = (this.state.tasksByStage[stageId] || []).map((task) => ({
                ...task,
                deadlineLabel: formatDate(task.deadline),
                userName: task.user_display || "—",
                supervisorName: task.supervisor_display || "—",
                stateLabel: STATE_LABEL[task.state] || task.state,
                costLabel: formatMoney(task.cost),
                timeleftLabel: task.timeleft || "—",
                timeleftClass: this._timeleftClass(task),
            }));
            const total = tasks.reduce((sum, task) => sum + Number(task.cost || 0), 0);
            const key = stage.id || stage.resId || index;
            return {
                key,
                record: stage,
                stageId,
                number: index + 1,
                name: DEFAULT_STAGE_NAMES.has(String(stage.data.name || "").trim())
                    ? ""
                    : (stage.data.name || ""),
                color: HEADER_COLORS[index % HEADER_COLORS.length],
                tasks,
                totalCost: formatMoney(total),
                collapsed: this.isCollapsed(key, index),
            };
        });
    }

    isCollapsed(key, index) {
        const value = this.state.collapsed[key];
        if (value === undefined) {
            return index !== 0;
        }
        return Boolean(value);
    }

    toggle(card, ev) {
        if (ev?.target?.closest("input, button, a, .o_lug_sc_name_input, .o_lug_sc_add")) {
            return;
        }
        this.state.collapsed[card.key] = !card.collapsed;
    }

    _timeleftClass(task) {
        const text = String(task.timeleft || "");
        if (task.state === "done") {
            return "is-done";
        }
        if (text.startsWith("Trễ")) {
            return "is-late";
        }
        if (text.includes("ngày")) {
            return "is-ok";
        }
        return "is-none";
    }

    _stageIdKey() {
        return this.stages.map((stage) => stage.resId || stage.id).join(",");
    }

    async _refreshTasks() {
        const ids = this.stages
            .map((stage) => stage.resId)
            .filter((id) => typeof id === "number");
        if (!ids.length) {
            this.state.tasksByStage = {};
            return;
        }
        try {
            const rows = await this.orm.searchRead(
                "project.stage.task",
                [["stage_id", "in", ids]],
                [
                    "stt",
                    "name",
                    "user_display",
                    "supervisor_display",
                    "deadline",
                    "state",
                    "timeleft",
                    "notes",
                    "cost",
                    "stage_id",
                    "sequence",
                ],
                { order: "sequence, id" }
            );
            const map = {};
            for (const row of rows) {
                const stageId = many2oneId(row.stage_id);
                if (!map[stageId]) {
                    map[stageId] = [];
                }
                map[stageId].push(row);
            }
            this.state.tasksByStage = map;
        } catch {
            this.state.tasksByStage = {};
        }
    }

    async _reload() {
        if (this.props.record.resId) {
            await this.props.record.load();
        }
        await this._refreshTasks();
    }

    async _ensureSaved() {
        if (this.props.record.resId) {
            return true;
        }
        const saved = await this.props.record.save();
        if (!saved) {
            this.notification.add(_t("Vui lòng nhập thông tin dự án rồi bấm Lưu trước."), {
                type: "warning",
            });
            return false;
        }
        return true;
    }

    async onNameChange(card, ev) {
        const name = (ev.target.value || "").trim();
        await card.record.update({ name: name || false });
    }

    async onAddTask(card) {
        if (!this.canEdit) {
            return;
        }
        if (!(await this._ensureSaved())) {
            return;
        }
        let stageId = card.stageId;
        if (typeof stageId !== "number") {
            await this._reload();
            const match = this.cards.find((item) => item.number === card.number);
            stageId = match?.stageId;
        }
        if (typeof stageId !== "number") {
            this.notification.add(_t("Không tìm thấy giai đoạn. Hãy lưu dự án rồi thử lại."), {
                type: "danger",
            });
            return;
        }
        this.state.collapsed[card.key] = false;
        const action = await this.orm.call("project.stage.line", "action_add_task_popup", [
            [stageId],
        ]);
        await this.action.doAction(action, {
            onClose: () => this._reload(),
        });
    }

    async onOpenTask(taskId) {
        if (!taskId) {
            return;
        }
        const action = await this.orm.call("project.stage.task", "action_open_popup", [[taskId]]);
        await this.action.doAction(action, {
            onClose: () => this._reload(),
        });
    }

    onDeleteTask(taskId) {
        if (!this.canEdit || !taskId) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Xóa công việc"),
            body: _t("Bạn có chắc muốn xóa công việc này?"),
            confirm: async () => {
                await this.orm.unlink("project.stage.task", [taskId]);
                await this._reload();
            },
        });
    }

    async onAddStage() {
        if (!this.canEdit) {
            return;
        }
        const next = this.stages.length + 1;
        const vals = {
            name: false,
            sequence: next * 10,
        };
        try {
            if (this.list.addNewRecord) {
                await this.list.addNewRecord({
                    position: "bottom",
                    context: {
                        default_name: false,
                        default_sequence: vals.sequence,
                    },
                });
                return;
            }
        } catch {
            /* fallback */
        }
        await this.props.record.update({
            stage_line_ids: [[0, 0, vals]],
        });
    }
}

registry.category("fields").add("lug_stage_cards", {
    ...x2ManyField,
    component: LugStageCardsField,
});
