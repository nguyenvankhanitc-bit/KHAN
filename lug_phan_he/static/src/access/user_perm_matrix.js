/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

const PERMS = [
    { key: "can_view", label: "XEM" },
    { key: "can_create", label: "THÊM" },
    { key: "can_edit", label: "SỬA" },
    { key: "can_delete", label: "XÓA" },
    { key: "can_admin", label: "QUẢN TRỊ" },
];

function cloneRows(rows) {
    return (rows || []).map((r) => ({ ...r }));
}

export class PhanHeUserPermMatrix extends Component {
    static template = "lug_phan_he.UserPermMatrix";
    static components = { PhanHeAppSidebar };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.PERMS = PERMS;
        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            userId: 0,
            userName: "",
            users: [],
            apps: [],
            appFilter: "all",
            query: "",
            rows: [],
            collapsed: {},
            snapshot: [],
        });
        onWillStart(() => {
            const ctx = this.props.action?.context || {};
            const uid = Number(ctx.default_user_id || ctx.user_id || 0);
            if (uid) {
                this.state.userId = uid;
            }
            return this.load(uid || false);
        });
    }

    get sidebarActiveKey() {
        return "access_menu";
    }

    get visibleRows() {
        const q = (this.state.query || "").trim().toLowerCase();
        const collapsed = this.state.collapsed;
        const byParent = {};
        for (const row of this.state.rows) {
            const pid = row.parent_id || 0;
            (byParent[pid] || (byParent[pid] = [])).push(row);
        }
        const hidden = new Set();
        const markHidden = (parentId) => {
            for (const child of byParent[parentId] || []) {
                if (collapsed[parentId]) {
                    hidden.add(child.menu_id);
                }
                if (hidden.has(child.menu_id) || collapsed[child.menu_id]) {
                    markHidden(child.menu_id);
                } else {
                    markHidden(child.menu_id);
                }
            }
        };
        // Collapse: hide descendants of collapsed folders
        const walkHide = (id) => {
            for (const child of byParent[id] || []) {
                hidden.add(child.menu_id);
                walkHide(child.menu_id);
            }
        };
        for (const row of this.state.rows) {
            if (row.is_folder && collapsed[row.menu_id]) {
                walkHide(row.menu_id);
            }
        }
        return this.state.rows.filter((row) => {
            if (hidden.has(row.menu_id)) {
                return false;
            }
            if (!q) {
                return true;
            }
            return String(row.name || "").toLowerCase().includes(q)
                || String(row.code || "").toLowerCase().includes(q);
        });
    }

    async load(userId) {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "phan.he.module.access",
                "get_user_perm_matrix",
                [userId || this.state.userId || false, this.state.appFilter]
            );
            this.state.users = data.users || [];
            this.state.apps = data.apps || [];
            this.state.userId = data.user_id;
            this.state.userName = data.user_name;
            this.state.rows = cloneRows(data.rows);
            this.state.snapshot = cloneRows(data.rows);
            this.state.dirty = false;
            // Mặc định thu gọn app không có quyền xem
            const collapsed = {};
            for (const row of this.state.rows) {
                if (row.is_folder && row.depth === 0 && !row.can_view) {
                    collapsed[row.menu_id] = true;
                }
            }
            this.state.collapsed = collapsed;
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Không tải được ma trận phân quyền.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onUserChange(ev) {
        const uid = Number(ev.target.value || 0);
        if (this.state.dirty) {
            this.dialog.add(ConfirmationDialog, {
                title: "Chưa lưu",
                body: "Có thay đổi chưa lưu. Đổi người dùng sẽ hủy thay đổi. Tiếp tục?",
                confirm: () => this.load(uid),
                cancel: () => {
                    ev.target.value = String(this.state.userId);
                },
            });
            return;
        }
        await this.load(uid);
    }

    async onAppChange(ev) {
        this.state.appFilter = ev.target.value || "all";
        if (this.state.dirty) {
            this.dialog.add(ConfirmationDialog, {
                title: "Chưa lưu",
                body: "Có thay đổi chưa lưu. Đổi bộ lọc sẽ hủy thay đổi. Tiếp tục?",
                confirm: () => this.load(this.state.userId),
                cancel: () => {
                    ev.target.value = this.state.appFilter;
                },
            });
            return;
        }
        await this.load(this.state.userId);
    }

    onQueryInput(ev) {
        this.state.query = ev.target.value || "";
    }

    toggleFold(row) {
        if (!row.is_folder) {
            return;
        }
        this.state.collapsed[row.menu_id] = !this.state.collapsed[row.menu_id];
    }

    childrenOf(menuId) {
        const out = [];
        const walk = (pid) => {
            for (const row of this.state.rows) {
                if (row.parent_id === pid) {
                    out.push(row);
                    walk(row.menu_id);
                }
            }
        };
        walk(menuId);
        return out;
    }

    setPerm(row, key, value) {
        row[key] = value;
        if (value && key !== "can_view") {
            row.can_view = true;
        }
        if (key === "can_admin" && value) {
            row.can_view = row.can_create = row.can_edit = row.can_delete = true;
        }
        if (key === "can_view" && !value) {
            row.can_create = row.can_edit = row.can_delete = row.can_admin = false;
        }
        this.state.dirty = true;
    }

    onToggle(row, key) {
        this.setPerm(row, key, !row[key]);
    }

    columnState(key) {
        const rows = this.visibleRows.filter((r) => !r.is_folder || r.depth > 0);
        if (!rows.length) {
            return "is-off";
        }
        const on = rows.filter((r) => r[key]).length;
        if (on === 0) {
            return "is-off";
        }
        if (on === rows.length) {
            return "is-on";
        }
        return "is-mixed";
    }

    onToggleColumn(key) {
        const rows = this.visibleRows;
        const allOn = rows.length && rows.every((r) => r[key]);
        const next = !allOn;
        this.dialog.add(ConfirmationDialog, {
            title: "Cấp quyền hàng loạt",
            body: next
                ? `Bật «${PERMS.find((p) => p.key === key)?.label || key}» cho ${rows.length} mục đang hiện?`
                : `Tắt «${PERMS.find((p) => p.key === key)?.label || key}» cho ${rows.length} mục đang hiện?`,
            confirmLabel: "Áp dụng",
            confirm: () => {
                for (const row of rows) {
                    this.setPerm(row, key, next);
                }
            },
        });
    }

    onBulkChildren(row, mode) {
        const kids = this.childrenOf(row.menu_id);
        if (!kids.length) {
            this.notification.add("Menu này không có menu con.", { type: "warning" });
            return;
        }
        const labels = {
            view: "Xem toàn bộ menu con",
            create: "Thêm toàn bộ menu con",
            edit: "Sửa toàn bộ menu con",
            delete: "Xóa toàn bộ menu con",
            all: "Toàn quyền toàn bộ menu con",
            clear: "Thu hồi toàn bộ quyền menu con",
        };
        this.dialog.add(ConfirmationDialog, {
            title: "Cấp quyền hàng loạt",
            body: `${labels[mode] || mode} (${kids.length} mục) dưới «${row.name}»?`,
            confirmLabel: "Áp dụng",
            confirm: () => {
                for (const child of kids) {
                    if (mode === "clear") {
                        this.setPerm(child, "can_view", false);
                    } else if (mode === "all") {
                        this.setPerm(child, "can_admin", true);
                    } else if (mode === "view") {
                        this.setPerm(child, "can_view", true);
                    } else if (mode === "create") {
                        this.setPerm(child, "can_create", true);
                    } else if (mode === "edit") {
                        this.setPerm(child, "can_edit", true);
                    } else if (mode === "delete") {
                        this.setPerm(child, "can_delete", true);
                    }
                }
            },
        });
    }

    onCancel() {
        this.state.rows = cloneRows(this.state.snapshot);
        this.state.dirty = false;
        this.notification.add("Đã hủy thay đổi.", { type: "info" });
    }

    async onSave() {
        if (!this.state.userId) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("phan.he.module.access", "save_user_perm_matrix", [
                this.state.userId,
                this.state.rows.map((r) => ({
                    menu_id: r.menu_id,
                    can_view: r.can_view,
                    can_create: r.can_create,
                    can_edit: r.can_edit,
                    can_delete: r.can_delete,
                    can_admin: r.can_admin,
                })),
            ]);
            this.state.snapshot = cloneRows(this.state.rows);
            this.state.dirty = false;
            this.notification.add("Đã lưu phân quyền. User sẽ đăng nhập lại để áp dụng.", {
                type: "success",
            });
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Lưu phân quyền thất bại.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    onResetFilters() {
        this.state.appFilter = "all";
        this.state.query = "";
        this.load(this.state.userId);
    }

    padStyle(depth) {
        return `padding-left: ${8 + Number(depth || 0) * 22}px`;
    }
}

registry.category("actions").add("phan_he_user_perm_matrix", PhanHeUserPermMatrix);
