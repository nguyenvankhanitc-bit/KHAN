/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

const EMPTY_FORM = {
    id: 0,
    name: "",
    company: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
    note: "",
    color: 1,
};

export class DailyWorkNotebook extends Component {
    static template = "daily_work_task.DailyWorkNotebook";
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
            const data = await this.orm.call("daily.work.notebook", "get_notebook_data", [], {
                search: this.state.search || false,
            });
            this.state.rows = data.rows || [];
            this.state.total = data.total || 0;
            this.state.userName = data.user_name || "";
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được sổ tay."), {
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
        this.state.form = { ...EMPTY_FORM, color: (this.state.rows.length % 6) + 1 };
        this.state.showForm = true;
    }

    openEdit(row) {
        this.state.form = {
            id: row.id,
            name: row.name || "",
            company: row.company || "",
            contact_name: row.contact_name || "",
            phone: row.phone || "",
            email: row.email || "",
            address: row.address || "",
            note: row.note || "",
            color: row.color || 1,
        };
        this.state.showForm = true;
    }

    closeForm() {
        this.state.showForm = false;
        this.state.form = { ...EMPTY_FORM };
    }

    async onSave() {
        this.state.saving = true;
        try {
            await this.orm.call("daily.work.notebook", "save_notebook_row", [], {
                vals: { ...this.state.form },
            });
            this.notification.add(_t("Đã lưu sổ tay."), { type: "success" });
            this.closeForm();
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async onDelete(row) {
        if (!confirm(`Xóa khách hàng «${row.name}»?`)) {
            return;
        }
        try {
            await this.orm.call("daily.work.notebook", "delete_notebook_row", [[row.id]]);
            this.notification.add(_t("Đã xóa."), { type: "success" });
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xóa được."), { type: "danger" });
        }
    }

    async goDashboard() {
        await this.action.doAction({ type: "ir.actions.client", tag: "daily_work_dashboard" });
    }

    colorClass(n) {
        return `tone-${(Number(n) || 1) % 6 || 6}`;
    }
}

registry.category("actions").add("daily_work_notebook", DailyWorkNotebook);
