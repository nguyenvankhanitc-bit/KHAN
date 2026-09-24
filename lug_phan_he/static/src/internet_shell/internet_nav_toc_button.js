/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * Nút "Mục lục" trên thanh tím (systray) — mở offcanvas sidebar Internet.
 * Chỉ hiện khi PhanHeInternetShell đang active + mobile (d-lg-none).
 */
export class InternetNavTocButton extends Component {
    static template = "lug_phan_he.InternetNavTocButton";
    static props = {};

    setup() {
        this.state = useState({ shellActive: false });
        useBus(this.env.bus, "lug_phan_he:INTERNET_SHELL", ({ detail }) => {
            this.state.shellActive = !!(detail && detail.active);
        });
        onMounted(() => {
            this.state.shellActive = !!document.querySelector(".o_internet_master");
        });
    }

    onClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.env.bus.trigger("lug_phan_he:OPEN_INTERNET_NAV");
    }
}

registry.category("systray").add(
    "lug_phan_he.InternetNavToc",
    { Component: InternetNavTocButton },
    { sequence: 35 }
);
