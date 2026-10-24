/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/** Cột file trong danh sách: có file → con mắt (mở xem ở tab mới), không có → «—». */
export class PhanHeFileEyeField extends Component {
    static template = "lug_phan_he.FileEyeField";
    static props = {
        ...standardFieldProps,
        fileNameField: { type: String, optional: true },
        title: { type: String, optional: true },
    };

    get hasFile() {
        return Boolean(this.props.record.data[this.props.name]);
    }

    get fileName() {
        const fname = this.props.fileNameField;
        return (fname && this.props.record.data[fname]) || this.props.title || "file";
    }

    get url() {
        const rec = this.props.record;
        return `/web/content/${rec.resModel}/${rec.resId}/${this.props.name}/${encodeURIComponent(this.fileName)}`;
    }

    onClick(ev) {
        ev.stopPropagation();
        window.open(this.url, "_blank");
    }
}

registry.category("fields").add("phan_he_file_eye", {
    component: PhanHeFileEyeField,
    supportedTypes: ["binary"],
    extractProps: ({ attrs, string }) => ({
        fileNameField: attrs.filename,
        title: string,
    }),
});
