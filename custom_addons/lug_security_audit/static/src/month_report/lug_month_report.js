/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class LugMonthReport extends Component {
    static template = "lug_security_audit.LugMonthReport";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        const today = new Date();
        this.state = useState({
            loading: true,
            data: null,
            filterYear: today.getFullYear(),
            filterMonth: today.getMonth() + 1,
            searchText: "",
        });
        onWillStart(() => this.loadReport());
    }

    get filtersPayload() {
        return {
            year: this.state.filterYear,
            month: this.state.filterMonth,
            search: this.state.searchText.trim(),
        };
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "lug.security.dashboard",
                "get_month_report_data",
                [],
                { filters: this.filtersPayload }
            );
            this.state.data = data;
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange() {
        await this.loadReport();
    }

    async onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            await this.loadReport();
        }
    }

    async clearSearch() {
        this.state.searchText = "";
        await this.loadReport();
    }

    async resetFilters() {
        const today = new Date();
        this.state.filterYear = today.getFullYear();
        this.state.filterMonth = today.getMonth() + 1;
        this.state.searchText = "";
        await this.loadReport();
    }

    async exportExcel() {
        const action = await this.orm.call(
            "lug.security.dashboard",
            "action_export_month_report",
            [],
            { filters: this.filtersPayload }
        );
        this.actionService.doAction(action);
    }
}

registry.category("actions").add("lug_security_month_report", LugMonthReport);
