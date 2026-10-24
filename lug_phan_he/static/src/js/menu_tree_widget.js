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
    static props = {
        ...standardFieldProps,
        header: { type: String, optional: true },
        showAllChecks: { type: Boolean, optional: true },
    };

    get headerLabel() {
        return this.props.header || "MENU LINKQ ERP";
    }

    setup() {
        this.state = useState({
            collapsed: {},
        });
        this.permKeys = ["perm_read", "perm_create", "perm_write", "perm_unlink", "perm_admin"];
    }

    rowId(rec) {
        return rec.resId || rec.id;
    }

    /** Mặc định thu gọn nhóm cha (như dropdown hệ thống). */
    isCollapsed(id) {
        if (!id) {
            return false;
        }
        const val = this.state.collapsed[id];
        return val === undefined ? true : Boolean(val);
    }

    toggleRow(id) {
        this.state.collapsed[id] = !this.isCollapsed(id);
    }

    isChildRow(data) {
        return Boolean(this.parentId(data));
    }

    showsEveryCheck(data) {
        return this.isInternetRow(data) || this.props.showAllChecks;
    }

    hasPermFlag(data, perm) {
        // Internet / Máy chủ: luôn hiện ô tích. LinkQ ẩn khi kế thừa cha.
        if (this.showsEveryCheck(data)) {
            return true;
        }
        return Boolean(data["has_" + String(perm).replace("perm_", "")]);
    }

    relId(value) {
        if (!value) {
            return false;
        }
        if (Array.isArray(value)) {
            return value[0];
        }
        if (typeof value === "object") {
            return value.id || value.resId || false;
        }
        return value;
    }

    isInternetRow(data) {
        return Boolean(data?.menu_code || data?.is_folder || data?.menu_name);
    }

    adminFieldName(data) {
        if (Object.prototype.hasOwnProperty.call(data || {}, "can_admin")) {
            return "can_admin";
        }
        return "can_all";
    }

    parentId(data) {
        const fromField = this.relId(data?.parent_id);
        if (fromField) {
            return fromField;
        }
        const parentKey = data?.parent_key;
        if (!parentKey) {
            return false;
        }
        const parentRec = this.rawRecords.find(
            (rec) => rec.data?.menu_key === parentKey || rec.data?.menu_code === parentKey
        );
        return parentRec ? this.rowId(parentRec) : false;
    }

    itemType(data) {
        if (data.is_group || data.is_folder || data.item_type === "folder") {
            return "folder";
        }
        if (data.item_type) {
            return data.item_type;
        }
        const key = data.menu_key || data.menu_code;
        return ACTION_KEYS.has(key) ? "action" : "file";
    }

    displayName(data) {
        return String(data.name || data.menu_name || "")
            .replace(/^📁\s*/, "")
            .replace(/^\s*[└─↳]+\s*/u, "")
            .replace(/^\s*└─\s*/, "")
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

    isFolderData(d) {
        return Boolean(d?.is_folder || d?.is_group || d?.item_type === "folder");
    }

    childRecords(parentId) {
        return this.rawRecords.filter((rec) => this.parentId(rec.data) === parentId);
    }

    /** Ô của thư mục cha = tick khi TẤT CẢ menu con đều tick (Internet / Máy chủ / Camera). */
    folderAll(rec, field) {
        const kids = this.childRecords(this.rowId(rec));
        if (!kids.length) {
            return undefined;
        }
        return kids.every((k) => Boolean(k.data[field]));
    }

    get records() {
        const parents = this.byId();
        return this.rawRecords.map((rec) => {
            const raw = rec.data;
            let d = raw;
            if (this.showsEveryCheck(raw) && this.isFolderData(raw)) {
                const adminF = this.adminFieldName(raw);
                const fold = {};
                for (const f of ["can_read", "can_create", "can_write", "can_unlink", adminF]) {
                    if (Object.prototype.hasOwnProperty.call(raw, f)) {
                        const v = this.folderAll(rec, f);
                        if (v !== undefined) {
                            fold[f] = v;
                        }
                    }
                }
                d = { ...raw, ...fold };
            }
            const pid = this.parentId(d);
            const parent = pid ? parents[pid] : null;
            const custom = Boolean(d.is_custom);
            const internet = this.showsEveryCheck(d);
            const adminVal = d.perm_admin ?? d.can_admin ?? d.can_all;
            const inheritHide = (parentFlag) =>
                internet ? false : Boolean(parent && parentFlag && !custom);
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
                    perm_admin: adminVal,
                    has_read: !inheritHide(parent?.can_read || parent?.perm_read),
                    has_create: !inheritHide(parent?.can_create || parent?.perm_create),
                    has_write: !inheritHide(parent?.can_write || parent?.perm_write),
                    has_unlink: !inheritHide(parent?.can_unlink || parent?.perm_unlink),
                    has_admin: !inheritHide(parent?.can_all || parent?.can_admin || parent?.perm_admin),
                },
            };
        });
    }

    async onCheckChange(record, fieldName, ev) {
        const checked = ev.target.checked;
        const origin = record.origin || record;
        let fname = PERM_MAP[fieldName] || fieldName;
        if (fname === "can_all") {
            fname = this.adminFieldName(origin.data || {});
        }
        const vals = { [fname]: checked };
        if (checked && fname !== "can_read" && fname !== "perm_read") {
            vals.can_read = true;
            if (Object.prototype.hasOwnProperty.call(origin.data || {}, "perm_read")) {
                vals.perm_read = true;
            }
        }
        if (origin.data?.parent_id && Object.prototype.hasOwnProperty.call(origin.data, "is_custom")) {
            vals.is_custom = true;
        }
        await origin.update(vals);
        if ((fname === "can_all" || fname === "can_admin") && checked) {
            await origin.update({
                can_read: true,
                can_create: true,
                can_write: true,
                can_unlink: true,
                [fname]: true,
            });
        }
        // Folder → lan xuống menu con (OWL x2m)
        const isFolder =
            origin.data?.is_folder || origin.data?.is_group || origin.data?.item_type === "folder";
        if (isFolder) {
            const parentId = this.rowId(origin);
            for (const child of this.rawRecords) {
                if (this.parentId(child.data) !== parentId) {
                    continue;
                }
                const childVals = { [fname]: checked };
                if (checked) {
                    childVals.can_read = true;
                }
                if ((fname === "can_all" || fname === "can_admin") && checked) {
                    Object.assign(childVals, {
                        can_read: true,
                        can_create: true,
                        can_write: true,
                        can_unlink: true,
                        [fname]: true,
                    });
                }
                await child.update(childVals);
            }
        }
    }
}

registry.category("fields").add("linkq_menu_permission_tree", {
    component: LinkqMenuPermissionTree,
    extractProps: ({ options }) => ({
        header: options.header || "MENU LINKQ ERP",
        showAllChecks: Boolean(options.show_all_checks),
    }),
});
