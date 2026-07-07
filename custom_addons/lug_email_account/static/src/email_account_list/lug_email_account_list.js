/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Domain } from "@web/core/domain";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onWillStart, useState } from "@odoo/owl";

export class LugEmailAccountListRenderer extends ListRenderer {
    isNumericColumn(column) {
        if (column.name === "stt") {
            return false;
        }
        return super.isNumericColumn(column);
    }

    getCellClass(column, record) {
        const classNames = super.getCellClass(column, record);
        if (column.name === "stt") {
            return classNames.replace(/\bo_list_number\b/g, "o_lug_email_stt_center");
        }
        return classNames;
    }
}

export class LugEmailAccountListController extends ListController {
    static template = "lug_email_account.ListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.filterState = useState({
            departmentId: "",
            state: "",
            query: "",
            loading: false,
            options: { departments: [], states: [] },
        });
        onWillStart(async () => {
            this.filterState.options = await this.orm.call(
                "lug.email.account",
                "get_list_filter_options",
                []
            );
        });
    }

    get departmentOptions() {
        return this.filterState.options.departments || [];
    }

    get stateOptions() {
        return this.filterState.options.states || [];
    }

    _buildFilterDomain() {
        const domain = [];
        const departmentId = Number(this.filterState.departmentId);
        const statusId = Number(this.filterState.state);
        const query = (this.filterState.query || "").trim();

        if (departmentId) {
            domain.push(["department_id", "=", departmentId]);
        }
        if (statusId) {
            domain.push(["status_id", "=", statusId]);
        }
        if (query) {
            domain.push("|", "|", "|",
                ["email", "ilike", query],
                ["employee_name", "ilike", query],
                ["function_name", "ilike", query],
                ["department", "ilike", query]
            );
        }
        return domain;
    }

    _getSearchDomain() {
        return this.env.searchModel?.domain || this.model.config.domain || [];
    }

    _getMergedDomain() {
        const filterDomain = this._buildFilterDomain();
        const searchDomain = this._getSearchDomain();
        if (!filterDomain.length) {
            return searchDomain;
        }
        return Domain.and([searchDomain, filterDomain]).toList();
    }

    async onFilterSearch(ev) {
        ev?.preventDefault();
        ev?.stopPropagation();
        this.filterState.loading = true;
        try {
            const domain = this._getMergedDomain();
            await this.model.root.load({ domain, offset: 0 });
        } catch (error) {
            console.error("LugEmailAccount filter error:", error);
        } finally {
            this.filterState.loading = false;
        }
    }

    async onFilterReset(ev) {
        ev?.preventDefault();
        ev?.stopPropagation();
        this.filterState.departmentId = "";
        this.filterState.state = "";
        this.filterState.query = "";
        this.filterState.loading = true;
        try {
            await this.model.root.load({
                domain: this._getSearchDomain(),
                offset: 0,
            });
        } finally {
            this.filterState.loading = false;
        }
    }

    onFilterKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onFilterSearch(ev);
        }
    }
}

export const lugEmailAccountListView = {
    ...listView,
    Controller: LugEmailAccountListController,
    Renderer: LugEmailAccountListRenderer,
};

registry.category("views").add("lug_email_account_list", lugEmailAccountListView);
