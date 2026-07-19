/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";

/**
 * Khi mở /odoo (không có app trong URL), luôn vào App Center
 * thay vì app đầu tiên trong menu (thường là Discuss).
 */
patch(WebClient.prototype, {
    async _loadDefaultApp() {
        try {
            await this.actionService.doAction("lug_app_center.action_lug_app_center", {
                clearBreadcrumbs: true,
            });
            return;
        } catch {
            return super._loadDefaultApp(...arguments);
        }
    },
});
