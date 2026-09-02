/** @odoo-module **/
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";

const ACTION_KEYS = new Set([
    "schedule_lock",
    "schedule_unlock",
    "system_lock",
    "system_access",
    "schedule_symbol_add",
]);

const PERM_MAP = {
    perm_read: "can_read",
    perm_create: "can_create",
    perm_write: "can_write",
    perm_unlink: "can_unlink",
    perm_admin: "can_all",
};

export class LinkqMenuPermissionTree extends Component {
    static template = "linkq_erp.MenuPermissionTree";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            collapsed: {},
        });
        this.permKeys = ["perm_read", "perm_create", "perm_write", "perm_unlink", "perm_admin"];
    }

    rowId(rec) {
        return rec.resId || rec.id;
    }

    toggleRow(id) {
        this.state.collapsed[id] = !this.state.collapsed[id];
    }

    isChildRow(data) {
        return Boolean(this.parentId(data));
    }

    hasPermFlag(data, perm) {
        return Boolean(data["has_" + String(perm).replace("perm_", "")]);
    }

    cellClass(perm, itemType) {
        const classes = ["perm-checkbox"];
        if (perm === "perm_admin" && itemType === "action") {
            classes.push("cb-action");
        }
        if (perm === "perm_create") {
            classes.push("cb-add");
        }
        return classes.join(" ");
    }

    parentId(data) {
        const parent = data?.parent_id;
        if (!parent) {
            return false;
        }
        if (Array.isArray(parent)) {
            return parent[0];
        }
        if (typeof parent === "object") {
            return parent.id || parent.resId || false;
        }
        return parent;
    }

    itemType(data) {
        if (data.is_group || data.item_type === "folder") {
            return "folder";
        }
        if (data.item_type) {
            return data.item_type;
        }
        return ACTION_KEYS.has(data.menu_key) ? "action" : "file";
    }

    displayName(data) {
        return String(data.name || "")
            .replace(/^📁\s*/, "")
            .replace(/^\s*↳\s*/, "")
            .trim();
    }

    byId() {
        const map = {};
        for (const rec of this.rawRecords) {
            map[this.rowId(rec)] = rec.data;
        }
        return map;
    }

    get rawRecords() {
        const x2m = this.props.record?.data?.[this.props.name];
        return x2m?.records || [];
    }

    get records() {
        const parents = this.byId();
        return this.rawRecords.map((rec) => {
            const d = rec.data;
            const pid = this.parentId(d);
            const parent = pid ? parents[pid] : null;
            const custom = Boolean(d.is_custom);
            return {
                id: this.rowId(rec),
                origin: rec,
                data: {
                    ...d,
                    name: this.displayName(d),
                    item_type: this.itemType(d),
                    perm_read: d.perm_read ?? d.can_read,
                    perm_create: d.perm_create ?? d.can_create,
                    perm_write: d.perm_write ?? d.can_write,
                    perm_unlink: d.perm_unlink ?? d.can_unlink,
                    perm_admin: d.perm_admin ?? d.can_all,
                    has_read: !(parent && (parent.can_read || parent.perm_read) && !custom),
                    has_create: !(parent && (parent.can_create || parent.perm_create) && !custom),
                    has_write: !(parent && (parent.can_write || parent.perm_write) && !custom),
                    has_unlink: !(parent && (parent.can_unlink || parent.perm_unlink) && !custom),
                    has_admin: !(parent && (parent.can_all || parent.perm_admin) && !custom),
                },
            };
        });
    }

    async onCheckChange(record, fieldName, ev) {
        const checked = ev.target.checked;
        const origin = record.origin || record;
        const fname = PERM_MAP[fieldName] || fieldName;
        const vals = { [fname]: checked };
        if (origin.data?.parent_id) {
            vals.is_custom = true;
        }
        await origin.update(vals);
        if (fname === "can_all" && checked) {
            await origin.update({
                can_read: true,
                can_create: true,
                can_write: true,
                can_unlink: true,
            });
        }
    }
}

registry.category("fields").add("linkq_menu_permission_tree", {
    component: LinkqMenuPermissionTree,
});
