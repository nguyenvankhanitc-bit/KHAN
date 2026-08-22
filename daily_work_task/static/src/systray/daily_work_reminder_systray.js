/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Chuông Nhắc việc trên header: hiện số việc quá hạn + sắp tới hạn,
 * bấm → mở bảng Nhắc việc (quá hạn / sắp tới hạn).
 */
export class DailyWorkReminderSystray extends Component {
    static template = "daily_work_task.ReminderSystray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            total: 0,
            overdue: 0,
            upcoming: 0,
            loading: true,
        });
        this._timer = null;
        onWillStart(async () => {
            await this.refresh();
            // Làm mới định kỳ (2 phút)
            this._timer = setInterval(() => this.refresh(), 120000);
        });
        onWillUnmount(() => {
            if (this._timer) {
                clearInterval(this._timer);
                this._timer = null;
            }
        });
    }

    async refresh() {
        try {
            const data = await this.orm.call("daily.task", "get_reminder_systray", []);
            this.state.overdue = Number(data?.overdue) || 0;
            this.state.upcoming = Number(data?.upcoming) || 0;
            this.state.total = Number(data?.total) || this.state.overdue + this.state.upcoming;
        } catch {
            this.state.overdue = 0;
            this.state.upcoming = 0;
            this.state.total = 0;
        } finally {
            this.state.loading = false;
        }
    }

    get titleText() {
        return `Nhắc việc: ${this.state.overdue} quá hạn · ${this.state.upcoming} sắp tới hạn`;
    }

    async onClick() {
        await this.action.doAction("daily_work_task.action_daily_work_reminders");
        // Refresh count after opening (user may complete tasks)
        this.refresh();
    }
}

registry.category("systray").add(
    "daily_work_task.reminder_bell",
    { Component: DailyWorkReminderSystray },
    { sequence: 26 }
);
