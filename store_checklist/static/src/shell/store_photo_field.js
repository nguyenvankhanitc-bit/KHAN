/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useEffect, useRef } from "@odoo/owl";
import { Many2ManyBinaryField, many2ManyBinaryField } from "@web/views/fields/many2many_binary/many2many_binary_field";

// Cột Hình ảnh: chỉ nhận ảnh, trên điện thoại mở thẳng camera để chụp
export class StorePhotoField extends Many2ManyBinaryField {
    static template = "store_checklist.PhotoField";

    setup() {
        super.setup();
        this.rootRef = useRef("root");
        useEffect(() => {
            this.rootRef.el?.querySelectorAll("input[type=file]").forEach((input) => {
                input.setAttribute("accept", "image/*");
                input.setAttribute("capture", "environment");
            });
        });
    }

    get uploadText() {
        return "Chụp hình";
    }
}

registry.category("fields").add("store_photo", { ...many2ManyBinaryField, component: StorePhotoField });
