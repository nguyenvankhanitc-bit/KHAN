/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { getFieldDomain } from "@web/model/relational_model/utils";
import { useSpecialData } from "@web/views/fields/relational_utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import {
    Many2ManyCheckboxesField,
    many2ManyCheckboxesField,
} from "@web/views/fields/many2many_checkboxes/many2many_checkboxes_field";

/**
 * Many2one «Hạng mục» dạng danh sách ô vuông tích chọn (có thanh trượt).
 * Mỗi tên hạng mục chỉ hiện 1 lần (dùng name_search với context work_group_unique_category).
 */
export class DwtCategoryChecklistField extends Component {
    static template = "daily_work_task.DwtCategoryChecklistField";
    static props = {
        ...standardFieldProps,
        domain: { type: [Array, Function], optional: true },
        context: { type: Object, optional: true },
    };

    setup() {
        this.state = useState({ query: "", open: false });
        this.specialData = useSpecialData(async (orm, props) => {
            const { relation } = props.record.fields[props.name];
            const domain = getFieldDomain(props.record, props.name, props.domain);
            const context = { ...(props.context || {}), work_group_unique_category: 1 };
            return orm.call(relation, "name_search", [], { name: "", domain, limit: 500, context });
        });
    }

    get items() {
        const q = (this.state.query || "").trim().toLowerCase();
        const all = this.specialData.data || [];
        return q ? all.filter((it) => String(it[1]).toLowerCase().includes(q)) : all;
    }

    get value() {
        const v = this.props.record.data[this.props.name];
        return v && v.id;
    }

    get selectedLabel() {
        const v = this.props.record.data[this.props.name];
        return v ? v.display_name : "";
    }

    toggleOpen() {
        if (!this.props.readonly) {
            this.state.open = !this.state.open;
        }
    }

    onToggle(item) {
        if (this.props.readonly) {
            return;
        }
        const checked = this.value === item[0];
        this.props.record.update({
            [this.props.name]: checked ? false : { id: item[0], display_name: item[1] },
        });
        if (!checked) {
            // Đã chọn → thu gọn danh sách
            this.state.open = false;
            this.state.query = "";
        }
    }

    onQuery(ev) {
        this.state.query = ev.target.value || "";
    }
}

export const dwtCategoryChecklistField = {
    component: DwtCategoryChecklistField,
    displayName: _t("Hạng mục (ô tích)"),
    supportedTypes: ["many2one"],
    extractProps: ({ context }, dynamicInfo) => ({
        domain: dynamicInfo.domain,
        context: dynamicInfo.context || context,
    }),
};

registry.category("fields").add("dwt_category_checklist", dwtCategoryChecklistField);

/** Many2many tích chọn, thu gọn: bấm để hiện danh sách (Tên công việc của hạng mục). */
export class DwtCollapsibleCheckboxesField extends Many2ManyCheckboxesField {
    static template = "daily_work_task.DwtCollapsibleCheckboxesField";
    static props = {
        ...Many2ManyCheckboxesField.props,
        unit: { type: String, optional: true },
        placeholder: { type: String, optional: true },
    };

    setup() {
        super.setup();
        this.state = useState({ open: false });
        this.rootRef = useRef("root");
        this._closeTimer = null;
        // Bấm ra ngoài danh sách → thu gọn
        const onDocClick = (ev) => {
            if (this.state.open && this.rootRef.el && !this.rootRef.el.contains(ev.target)) {
                this.state.open = false;
            }
        };
        onMounted(() => document.addEventListener("click", onDocClick, true));
        onWillUnmount(() => {
            document.removeEventListener("click", onDocClick, true);
            clearTimeout(this._closeTimer);
        });
    }

    /** Tích xong → tự thu gọn sau 1,2 giây (còn tích tiếp thì đợi tiếp). */
    onChange(resId, checked) {
        super.onChange(resId, checked);
        clearTimeout(this._closeTimer);
        this._closeTimer = setTimeout(() => {
            this.state.open = false;
        }, 1200);
    }

    /** Tên các mục đã chọn (hiện trên ô khi thu gọn). */
    get selectedNames() {
        const ids = this.props.record.data[this.props.name]?.currentIds || [];
        const map = new Map((this.items || []).map((it) => [it[0], it[1]]));
        return ids.map((id) => map.get(id)).filter(Boolean).join(", ");
    }

    get selectedCount() {
        return (this.props.record.data[this.props.name]?.currentIds || []).length;
    }

    toggleOpen() {
        this.state.open = !this.state.open;
    }
}

registry.category("fields").add("dwt_collapsible_checkboxes", {
    ...many2ManyCheckboxesField,
    component: DwtCollapsibleCheckboxesField,
    extractProps(fieldInfo, dynamicInfo) {
        return {
            ...many2ManyCheckboxesField.extractProps(fieldInfo, dynamicInfo),
            unit: fieldInfo.options?.unit || "công việc",
            placeholder: fieldInfo.placeholder || "",
        };
    },
});
