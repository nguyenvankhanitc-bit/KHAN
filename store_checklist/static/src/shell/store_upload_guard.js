/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

/**
 * Chống lỗi "Component is destroyed" khi thêm hình vào phiếu (vd. Chi tiết lỗi của Checklist giám sát):
 * ảnh chụp từ điện thoại tải lên chậm, người dùng bấm Lưu / nút trên phiếu trước khi tải xong -> form lưu và đóng
 * popup, ảnh tải xong gắn vào form đã bị hủy -> lỗi và ảnh bị mất.
 * Cách xử lý: widget ảnh ghi nhận các lượt tải đang chạy; form của model store.* chờ tải xong rồi mới lưu.
 */
const pending = new Set();
const MAX_WAIT_MS = 120000; // không chờ quá 2 phút (mạng rớt / tải lỗi)

export function startUpload() {
    let done;
    const promise = new Promise((resolve) => {
        done = resolve;
    });
    const timer = setTimeout(() => finish(), MAX_WAIT_MS);
    const finish = () => {
        clearTimeout(timer);
        pending.delete(promise);
        done();
    };
    pending.add(promise);
    return finish;
}

export function hasPendingUploads() {
    return pending.size > 0;
}

export async function waitUploads() {
    while (pending.size) {
        await Promise.all([...pending]);
    }
}

patch(FormController.prototype, {
    async save(params) {
        if (this.props.resModel?.startsWith("store.") && hasPendingUploads()) {
            this.env.services.notification.add("Đang tải hình ảnh lên, phiếu sẽ được lưu ngay khi tải xong...", { type: "info" });
            await waitUploads();
        }
        return super.save(...arguments);
    },
    async beforeExecuteActionButton(clickParams) {
        if (this.props.resModel?.startsWith("store.") && hasPendingUploads()) {
            await waitUploads();
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});
