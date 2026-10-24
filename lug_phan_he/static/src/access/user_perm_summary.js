/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

function cloneRows(rows) {
    return (rows || []).map((r) => ({
        ...r,
        apps: { ...(r.apps || {}) },
        selected: false,
    }));
}

export class PhanHeUserPermSummary extends Component {
    static template = "lug_phan_he.UserPermSummary";
    static components = { PhanHeAppSidebar };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            query: "",
            apps: [],
            rows: [],
            snapshot: [],
            selectAll: false,
        });
        onWillStart(() => this.load());
    }

    get sidebarActiveKey() {
        return "access_user";
    }

    get visibleRows() {
        const q = (this.state.query || "").trim().toLowerCase();
        if (!q) {
            return this.state.rows;
        }
        return this.state.rows.filter(
            (r) =>
                String(r.name || "").toLowerCase().includes(q)
                || String(r.login || "").toLowerCase().includes(q)
        );
    }

    get selectedRows() {
        return this.state.rows.filter((r) => r.selected && !r.is_admin);
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("phan.he.module.access", "get_user_app_summary", []);
            this.state.apps = data.apps || [];
            this.state.rows = cloneRows(data.rows);
            this.state.snapshot = cloneRows(data.rows);
            this.state.dirty = false;
            this.state.selectAll = false;
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Không tải được tổng hợp phân quyền.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    onQueryInput(ev) {
        this.state.query = ev.target.value || "";
    }

    onToggleSelectAll(ev) {
        const on = Boolean(ev.target.checked);
        this.state.selectAll = on;
        for (const row of this.visibleRows) {
            if (!row.is_admin) {
                row.selected = on;
            }
        }
    }

    onToggleSelect(row) {
        if (row.is_admin) {
            return;
        }
        row.selected = !row.selected;
        this.state.selectAll = this.visibleRows.every((r) => r.is_admin || r.selected);
    }

    markDirty(row) {
        row._dirty = true;
        this.state.dirty = true;
    }

    onToggleApp(row, appCode) {
        if (row.is_admin) {
            this.notification.add("Không sửa quyền tài khoản Quản trị tại đây.", {
                type: "warning",
            });
            return;
        }
        row.apps[appCode] = !row.apps[appCode];
        this.markDirty(row);
    }

    onBulkApp(appCode, enabled) {
        const targets = this.selectedRows;
        if (!targets.length) {
            this.notification.add("Hãy chọn ít nhất một user.", { type: "warning" });
            return;
        }
        for (const row of targets) {
            row.apps[appCode] = enabled;
            this.markDirty(row);
        }
        this.notification.add(
            `${enabled ? "Bật" : "Tắt"} «${appCode}» cho ${targets.length} user.`,
            { type: "info" }
        );
    }

    onCancel() {
        this.state.rows = cloneRows(this.state.snapshot);
        this.state.dirty = false;
        this.state.selectAll = false;
        this.notification.add("Đã hủy thay đổi.", { type: "info" });
    }

    async onSave() {
        this.state.saving = true;
        try {
            const changes = this.state.rows
                .filter((r) => !r.is_admin && r._dirty)
                .map((r) => ({
                    user_id: r.user_id,
                    apps: { ...r.apps },
                }));
            if (!changes.length) {
                this.notification.add("Không có thay đổi cần lưu.", { type: "info" });
                return;
            }
            await this.orm.call("phan.he.module.access", "save_user_app_summary", [changes]);
            await this.load();
            this.notification.add("Đã lưu tổng hợp phân quyền. User sẽ đăng nhập lại để áp dụng.", {
                type: "success",
            });
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Lưu thất bại.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    openMenuMatrix(row) {
        this.action.doAction("lug_phan_he.action_phan_he_user_perm_matrix", {
            additionalContext: { default_user_id: row.user_id },
        });
    }

    openMenuMatrixSelected() {
        const row = this.selectedRows[0] || this.visibleRows.find((r) => !r.is_admin);
        if (!row) {
            this.notification.add("Không có user để mở menu phân quyền.", { type: "warning" });
            return;
        }
        this.openMenuMatrix(row);
    }
}

registry.category("actions").add("phan_he_user_perm_summary", PhanHeUserPermSummary);
