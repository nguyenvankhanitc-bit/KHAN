/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";

// Ô điểm đánh giá: để trống khi dòng chưa chấm; nhập kể cả 0 cũng tính là đã chấm
export class StoreScoreField extends FloatField {
    get formattedValue() {
        return this.props.record.data.is_scored ? super.formattedValue : "";
    }

    parse(value) {
        const number = super.parse(value);
        if (!this.props.record.data.is_scored) {
            // cập nhật điểm và cờ "đã chấm" trong một lần để cột Kết quả không nháy "Không đạt" rồi mới nhảy đúng
            this.props.record.update({ [this.props.name]: number, is_scored: true });
        }
        return number;
    }
}

registry.category("fields").add("store_score", { ...floatField, component: StoreScoreField });
