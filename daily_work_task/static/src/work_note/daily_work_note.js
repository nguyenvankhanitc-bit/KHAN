/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

function todayIso() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
}

const EMPTY_FORM = {
    id: 0,
    name: "",
    note_date: todayIso(),
};

export class DailyWorkNote extends Component {
    static template = "daily_work_task.DailyWorkNote";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            search: "",
            rows: [],
            total: 0,
            userName: "",
            showForm: false,
            form: { ...EMPTY_FORM },
            saving: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.work.note", "get_work_note_data", [], {
                search: this.state.search || false,
            });
            this.state.rows = data.rows || [];
            this.state.total = data.total || 0;
            this.state.userName = data.user_name || "";
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được ghi chú."), {
                type: "danger",
            });
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    async onSearch() {
        await this.load();
    }

    onSearchKey(ev) {
        if (ev.key === "Enter") {
            this.onSearch();
        }
    }

    openCreate() {
        this.state.form = { ...EMPTY_FORM, note_date: todayIso() };
        this.state.showForm = true;
    }

    openEdit(row) {
        this.state.form = {
            id: row.id,
            name: row.name || "",
            note_date: row.note_date || todayIso(),
        };
        this.state.showForm = true;
    }

    closeForm() {
        this.state.showForm = false;
        this.state.form = { ...EMPTY_FORM, note_date: todayIso() };
    }

    async onSave() {
        this.state.saving = true;
        try {
            await this.orm.call("daily.work.note", "save_work_note", [], {
                vals: { ...this.state.form },
            });
            this.notification.add(_t("Đã lưu ghi chú."), { type: "success" });
            this.closeForm();
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async onDelete(row) {
        if (!confirm(`Xóa ghi chú này?`)) {
            return;
        }
        try {
            await this.orm.call("daily.work.note", "delete_work_note", [[row.id]]);
            this.notification.add(_t("Đã xóa."), { type: "success" });
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xóa được."), { type: "danger" });
        }
    }

    async goDashboard() {
        await this.action.doAction({ type: "ir.actions.client", tag: "daily_work_dashboard" });
    }
}

registry.category("actions").add("daily_work_note", DailyWorkNote);
