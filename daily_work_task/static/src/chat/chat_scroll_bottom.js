/** @odoo-module **/
/* Khung chat (popup): mở ra luôn hiển thị tin nhắn MỚI NHẤT ở dưới cùng,
 * thay vì cuộn tới tin chưa đọc đầu tiên (mặc định của Odoo). */

import { Thread } from "@mail/core/common/thread";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    applyScrollContextually(thread) {
        if (this.env.inChatWindow && thread.self_member_id && thread.scrollUnread && this.props.order === "asc") {
            const el = this.scrollableRef.el;
            this.setScroll(el.scrollHeight - el.clientHeight);
            thread.scrollUnread = false;
            if (this.isAtBottom && !thread.markedAsUnread && thread.isFocused) {
                thread.markAsRead();
            }
            return;
        }
        return super.applyScrollContextually(...arguments);
    },
});
