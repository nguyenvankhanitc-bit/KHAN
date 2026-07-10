/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

const BUSINESS_BOT_NAMES = new Set([
    "OdooBot Bàn giao việc",
    "OdooBot Duyệt đơn",
    "OdooBot Ra cổng",
    "OdooBot CTKM",
]);

patch(Thread.prototype, {
    get allowCalls() {
        const correspondentName = this.correspondent?.persona?.name || this.correspondent?.persona?.displayName;
        if (this.channel_type === "chat" && BUSINESS_BOT_NAMES.has(correspondentName)) {
            return false;
        }
        return super.allowCalls;
    },
});
