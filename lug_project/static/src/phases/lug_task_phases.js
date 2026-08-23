/** @odoo-module **/
/* lug-task-board-v7 */

import { onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const { DateTime } = luxon;

const PHASE_DEFAULTS = [
    { code: "1", name: "CHUẨN BỊ & KHẢO SÁT", sequence: 10 },
    { code: "2", name: "TRIỂN KHAI & BÁN HÀNG", sequence: 20 },
    { code: "3", name: "LẮP ĐẶT & HOÀN THIỆN", sequence: 30 },
    { code: "4", name: "NGHIỆM THU & BÀN GIAO", sequence: 40 },
    { code: "5", name: "BẢO HÀNH & HỖ TRỢ", sequence: 50 },
    { code: "6", name: "ĐÓNG DỰ ÁN", sequence: 60 },
];

const STATUS_LABEL = {
    todo: "Chưa làm",
    progress: "Đang làm",
    review: "Chờ duyệt",
    done: "Hoàn thành",
    cancel: "Hủy",
};

function toIsoDate(value) {
    if (!value) {
        return "";
    }
    if (typeof value.toFormat === "function") {
        return value.toFormat("yyyy-MM-dd");
    }
    const text = String(value);
    const iso = text.match(/^(\d{4}-\d{2}-\d{2})/);
    return iso ? iso[1] : "";
}

function toDateLabel(value) {
    const iso = toIsoDate(value);
    if (!iso) {
        return "";
    }
    if (typeof value?.toFormat === "function") {
        return value.toFormat("dd/MM/yyyy");
    }
    const [year, month, day] = iso.split("-");
    return `${day}/${month}/${year}`;
}

function timeleftMeta(raw) {
    const text = String(raw || "none|—");
    const sep = text.indexOf("|");
    const state = sep < 0 ? "none" : text.slice(0, sep) || "none";
    let label = sep < 0 ? text : text.slice(sep + 1) || "—";
    if (state === "ok") {
        const match = label.match(/(\d+)/);
        if (match) {
            label = `${match[1]} ngày`;
        }
    } else if (state === "late") {
        const match = label.match(/(\d+)/);
        if (match) {
            label = `Trễ ${match[1]} ngày`;
        }
    }
    return { state, label };
}

function many2oneId(value) {
    if (!value) {
        return false;
    }
    if (typeof value === "number") {
        return value;
    }
    return value.id || false;
}

function many2oneName(value) {
    if (!value) {
        return "";
    }
    return value.display_name || value.name || "";
}

export class LugTaskPhaseField extends X2ManyField {
    static template = "lug_project.LugTaskPhaseField";

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.state = useState({
            users: [],
            collapsed: {},
            lastKey: "",
        });
        onWillStart(() => this._loadUsers());
        this.canOpenRecord = false;
    }

    get canEdit() {
        return this.canCreate && !this.props.readonly;
    }

    _stageRecords() {
        const stages = this.props.record?.data?.lug_stage_ids;
        const records = stages?.records || [];
        return records.slice().sort((a, b) => {
            const seq = (a.data.sequence || 0) - (b.data.sequence || 0);
            if (seq) {
                return seq;
            }
            return String(a.resId || "").localeCompare(String(b.resId || ""));
        });
    }

    _stageKey(stage) {
        if (stage?.resId && typeof stage.resId === "number") {
            return `id:${stage.resId}`;
        }
        const code = String(stage?.data?.code || "");
        if (code) {
            return `code:${code}`;
        }
        return `tmp:${stage?.id || stage?.resId || "0"}`;
    }

    _taskStageKey(record) {
        const rel = record.data.lug_stage_id;
        const id = many2oneId(rel);
        if (id) {
            return `id:${id}`;
        }
        const code = String(record.data.lug_phase || "");
        if (code) {
            return `code:${code}`;
        }
        return "none";
    }

    get groups() {
        const stages = this._stageRecords();
        const tasks = this.list.records || [];
        const byKey = {};
        for (const record of tasks) {
            const key = this._taskStageKey(record);
            if (!byKey[key]) {
                byKey[key] = [];
            }
            byKey[key].push(record);
        }
        const groups = [];
        if (stages.length) {
            for (const stage of stages) {
                const key = this._stageKey(stage);
                const code = String(stage.data.code || groups.length + 1);
                groups.push(this._makeGroup(key, code, stage.data.name || "Giai đoạn", byKey[key] || [], stage));
                delete byKey[key];
                if (code) {
                    delete byKey[`code:${code}`];
                }
            }
        } else {
            for (const phase of PHASE_DEFAULTS) {
                const key = `code:${phase.code}`;
                groups.push(this._makeGroup(key, phase.code, phase.name, byKey[key] || [], null));
                delete byKey[key];
            }
        }
        const leftover = Object.values(byKey).flat();
        if (leftover.length) {
            groups.push(this._makeGroup("none", "?", "Chưa gán giai đoạn", leftover, null));
        }
        return groups;
    }

    _makeGroup(key, code, name, records, stageRecord) {
        const sorted = records.slice().sort((a, b) => {
            const seq = (a.data.sequence || 0) - (b.data.sequence || 0);
            if (seq) {
                return seq;
            }
            return (a.resId || 0) - (b.resId || 0);
        });
        return {
            key,
            code,
            stageRecord,
            title: `GIAI ĐOẠN ${code}: ${name}`,
            collapsed: Boolean(this.state.collapsed[key]),
            tasks: sorted.map((record, index) => this._makeRow(record, code, index + 1)),
        };
    }

    _makeRow(record, phaseCode, index) {
        const data = record.data || {};
        const status = data.lug_status || "todo";
        return {
            key: record.id || `${phaseCode}-${index}`,
            record,
            stt: `${phaseCode}.${index}`,
            name: data.name || "",
            picId: many2oneId(data.lug_pic_id),
            picName: many2oneName(data.lug_pic_id),
            supervisorId: many2oneId(data.lug_supervisor_id),
            supervisorName: many2oneName(data.lug_supervisor_id),
            deadlineIso: toIsoDate(data.date_deadline),
            deadlineLabel: toDateLabel(data.date_deadline),
            timeleft: timeleftMeta(data.lug_timeleft),
            status,
            statusLabel: STATUS_LABEL[status] || status,
        };
    }

    async _loadUsers() {
        try {
            this.state.users = await this.orm.searchRead(
                "res.users",
                [
                    ["share", "=", false],
                    ["active", "=", true],
                ],
                ["name"],
                { order: "name", limit: 80 }
            );
        } catch {
            this.state.users = [];
        }
    }

    toggle(key) {
        this.state.collapsed[key] = !this.state.collapsed[key];
        this.state.lastKey = key;
    }

    _taskContext(group) {
        const context = { default_name: "Công việc mới" };
        if (group?.code && group.code !== "?") {
            context.default_lug_phase = String(group.code);
        }
        const stageId = group?.stageRecord?.resId;
        if (typeof stageId === "number") {
            context.default_lug_stage_id = stageId;
        }
        return context;
    }

    async onAddTaskIn(group) {
        if (!this.canEdit) {
            return;
        }
        this.state.lastKey = group.key;
        this.state.collapsed[group.key] = false;
        await this.onAdd({
            context: this._taskContext(group),
            editable: "bottom",
        });
    }

    async onAddTask() {
        const group =
            this.groups.find((item) => item.key === this.state.lastKey) || this.groups[0];
        if (!group) {
            return;
        }
        await this.onAddTaskIn(group);
    }

    async onAddPhase() {
        if (!this.canEdit) {
            return;
        }
        const stages = this.props.record?.data?.lug_stage_ids;
        const next = this._stageRecords().length + 1;
        const vals = {
            name: "Giai đoạn mới",
            code: String(next),
            sequence: next * 10,
        };
        try {
            if (stages?.addNewRecord) {
                await stages.addNewRecord({
                    position: "bottom",
                    context: {
                        default_name: vals.name,
                        default_code: vals.code,
                        default_sequence: vals.sequence,
                    },
                });
                return;
            }
        } catch {
            /* fallback below */
        }
        await this.props.record.update({
            lug_stage_ids: [[0, 0, vals]],
        });
    }

    async onNameChange(record, ev) {
        await record.update({ name: (ev.target.value || "").trim() || "Công việc mới" });
    }

    async _prepareSave() {
        const project = this.props.record;
        const storeName = String(project.data.name || "").trim();
        const content = String(project.data.lug_content || "").trim();
        if (!storeName) {
            const title = (content.split("\n")[0] || "").trim() || "Dự án mới";
            await project.update({ name: title });
        }
        const root = this.rootRef.el;
        for (const record of this.list.records || []) {
            let name = String(record.data.name || "").trim();
            if (root) {
                const input = root.querySelector(`input[data-task-id="${record.id}"]`);
                if (input && input.value.trim()) {
                    name = input.value.trim();
                }
            }
            if (!name) {
                name = "Công việc mới";
            }
            if (name !== String(record.data.name || "").trim()) {
                await record.update({ name });
            }
        }
    }

    async onUserChange(record, fieldName, ev) {
        const id = parseInt(ev.target.value, 10);
        if (!id) {
            await record.update({ [fieldName]: false });
            return;
        }
        const user = this.state.users.find((item) => item.id === id);
        await record.update({
            [fieldName]: { id, display_name: user?.name || "" },
        });
    }

    async onDeadlineChange(record, ev) {
        const raw = ev.target.value;
        const value = raw ? DateTime.fromISO(raw).endOf("day") : false;
        await record.update({ date_deadline: value });
    }

    async onStatusChange(record, ev) {
        await record.update({ lug_status: ev.target.value || "todo" });
    }

    async onSave() {
        try {
            await this._prepareSave();
            const saved = await this.props.record.save();
            if (saved) {
                this.notification.add(_t("Đã lưu công việc."), { type: "success" });
                return;
            }
            this.notification.add(
                _t("Thiếu trường bắt buộc. Nhập Tên dự án ở dòng tiêu đề, rồi bấm Lưu lại."),
                { type: "danger" }
            );
        } catch {
            this.notification.add(_t("Không lưu được. Kiểm tra tên dự án và tên công việc."), {
                type: "danger",
            });
        }
    }

    async onCancel() {
        await this.props.record.discard();
    }
}

registry.category("fields").add("lug_task_phases", {
    ...x2ManyField,
    component: LugTaskPhaseField,
});
