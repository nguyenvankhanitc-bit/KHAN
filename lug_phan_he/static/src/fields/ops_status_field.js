/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const OPS_META = {
    active: {
        label: "Đang hoạt động",
        icon: "fa-check-circle",
        className: "is-active",
    },
    suspend: {
        label: "Tạm dừng",
        icon: "fa-pause-circle",
        className: "is-suspend",
    },
    liquidated: {
        label: "Thanh lý",
        icon: "fa-times-circle",
        className: "is-liquidated",
    },
};

export class PhanHeOpsStatusField extends Component {
    static template = "lug_phan_he.OpsStatusField";
    static props = { ...standardFieldProps };

    get value() {
        return this.props.record.data[this.props.name] || "active";
    }

    get meta() {
        return OPS_META[this.value] || OPS_META.active;
    }

    get options() {
        return Object.entries(OPS_META).map(([value, meta]) => ({
            value,
            ...meta,
        }));
    }

    onChange(ev) {
        const value = ev.target.value;
        this.props.record.update({ [this.props.name]: value });
    }
}

export const phanHeOpsStatusField = {
    component: PhanHeOpsStatusField,
    supportedTypes: ["selection"],
};

registry.category("fields").add("phan_he_ops_status", phanHeOpsStatusField);
