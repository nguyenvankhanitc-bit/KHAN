/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PhanHeStoreCardField extends Component {
    static template = "lug_phan_he.StoreCardField";
    static props = { ...standardFieldProps };

    get storeName() {
        const store = this.props.record.data.store_id;
        if (Array.isArray(store) && store[1]) {
            return store[1];
        }
        const name = this.props.record.data.name;
        if (name) {
            return String(name).replace(/^INTERNET\s*-\s*/i, "").trim() || name;
        }
        return "—";
    }

    get lineCode() {
        const data = this.props.record.data || {};
        const raw = data.customer_code || data.code || "";
        return String(raw || "").trim();
    }
}

export const phanHeStoreCardField = {
    component: PhanHeStoreCardField,
    supportedTypes: ["many2one", "char", "html"],
    fieldDependencies: [
        { name: "customer_code", type: "char" },
        { name: "code", type: "char" },
        { name: "name", type: "char" },
        { name: "store_id", type: "many2one" },
    ],
};

registry.category("fields").add("phan_he_store_card", phanHeStoreCardField);
