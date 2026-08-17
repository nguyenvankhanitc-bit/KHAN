/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

function formatBandwidth(raw) {
    const value = String(raw || "").trim();
    if (!value) {
        return "";
    }
    if (/mbps|gbps|kbps|bps/i.test(value)) {
        return value.replace(/\s*(mbps)\b/i, " Mbps").replace(/\s+/g, " ").trim();
    }
    return `${value} Mbps`;
}

export class PhanHeBandwidthField extends Component {
    static template = "lug_phan_he.BandwidthField";
    static props = { ...standardFieldProps };

    get displayValue() {
        return formatBandwidth(this.props.record.data[this.props.name]);
    }
}

registry.category("fields").add("phan_he_bandwidth", {
    component: PhanHeBandwidthField,
    supportedTypes: ["char"],
});
