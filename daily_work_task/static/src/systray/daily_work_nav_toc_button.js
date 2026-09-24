/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * Nút "Mục lục" trên thanh tím (systray) — mở offcanvas menu Công việc.
 * Chỉ hiện khi DailyWorkDashboard đang active + mobile (d-lg-none).
 */
export class DailyWorkNavTocButton extends Component {
    static template = "daily_work_task.DailyWorkNavTocButton";
    static props = {};

    setup() {
        this.state = useState({ shellActive: false });
        useBus(this.env.bus, "daily_work_task:DASHBOARD_SHELL", ({ detail }) => {
            this.state.shellActive = !!(detail && detail.active);
        });
        onMounted(() => {
            this.state.shellActive = !!document.querySelector(".o_daily_work_dashboard");
        });
    }

    onClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.env.bus.trigger("daily_work_task:OPEN_WORK_NAV");
    }
}

registry.category("systray").add(
    "daily_work_task.WorkNavToc",
    { Component: DailyWorkNavTocButton },
    { sequence: 34 }
);
