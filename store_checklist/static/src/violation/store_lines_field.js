/** @odoo-module **/

import { useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

// Phiếu đánh giá: các dòng tiêu chí gom theo "Phân nhóm" (bấm tiêu đề nhóm để thu gọn / mở rộng, kèm điểm của nhóm).
// Chỉ thêm dòng tiêu đề nhóm; các cột và dữ liệu của dòng không đổi.
export class StoreLinesRenderer extends ListRenderer {
    static recordRowTemplate = "store_checklist.LineRow";

    setup() {
        super.setup();
        this.grp = useState({ closed: {} });
    }

    groupKey(record) {
        return record.data.sub_category || "";
    }

    groupTitle(record) {
        return this.groupKey(record) || "Khác";
    }

    isGroupStart(record) {
        const recs = this.props.list.records;
        const i = recs.indexOf(record);
        return i === 0 || this.groupKey(recs[i - 1]) !== this.groupKey(record);
    }

    groupInfo(record) {
        const key = this.groupKey(record);
        const rows = this.props.list.records.filter((r) => this.groupKey(r) === key);
        const num = (v) => Math.round((v || 0) * 100) / 100;
        return {
            count: rows.length,
            got: num(rows.reduce((s, r) => s + (r.data.actual_score || 0), 0)),
            max: num(rows.reduce((s, r) => s + (r.data.max_score || 0), 0)),
        };
    }

    toggleGroup(record) {
        const key = this.groupKey(record);
        this.grp.closed[key] = !this.grp.closed[key];
    }
}

export class StoreLinesField extends X2ManyField {
    static components = { ...X2ManyField.components, ListRenderer: StoreLinesRenderer };
}

registry.category("fields").add("store_lines", { ...x2ManyField, component: StoreLinesField });
