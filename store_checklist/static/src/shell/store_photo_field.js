/** @odoo-module **/

import { registry } from "@web/core/registry";
import { onWillDestroy, status, useEffect, useRef } from "@odoo/owl";
import { Many2ManyBinaryField, many2ManyBinaryField } from "@web/views/fields/many2many_binary/many2many_binary_field";
import { startUpload } from "./store_upload_guard";

// Cột Hình ảnh: chỉ nhận ảnh, trên điện thoại mở thẳng camera để chụp
export class StorePhotoField extends Many2ManyBinaryField {
    static template = "store_checklist.PhotoField";

    setup() {
        super.setup();
        this.rootRef = useRef("root");
        this._finishUploads = [];
        // ô ảnh bị hủy giữa chừng (lượt tải cũng dừng theo): không bắt form chờ nữa
        onWillDestroy(() => this._finishUploads.splice(0).forEach((finish) => finish()));
        useEffect(() => {
            const inputs = this.rootRef.el ? [...this.rootRef.el.querySelectorAll("input[type=file]")] : [];
            const onChange = (ev) => {
                if (ev.target.files?.length) {
                    this._finishUploads.push(startUpload()); // form chờ lượt tải này xong mới lưu
                }
            };
            inputs.forEach((input) => {
                input.setAttribute("accept", "image/*");
                // nút "Chụp hình" mở thẳng camera; nút "Chọn ảnh" mở thư viện ảnh (không gắn capture)
                if (input.closest(".o_store_photo_pick")) {
                    input.removeAttribute("capture");
                } else {
                    input.setAttribute("capture", "environment");
                }
                input.addEventListener("change", onChange, true);
            });
            return () => inputs.forEach((input) => input.removeEventListener("change", onChange, true));
        });
    }

    get uploadText() {
        return "Chụp hình";
    }

    async onFileUploaded(files) {
        try {
            if (status(this) !== "destroyed") {
                await super.onFileUploaded(files);
            }
        } catch (error) {
            // popup phiếu đã đóng trong lúc ảnh đang tải: bỏ qua thay vì hiện lỗi "Component is destroyed"
            if (status(this) !== "destroyed" && error?.message !== "Component is destroyed") {
                throw error;
            }
        } finally {
            this._finishUploads.splice(0).forEach((finish) => finish());
        }
    }
}

registry.category("fields").add("store_photo", { ...many2ManyBinaryField, component: StorePhotoField });
