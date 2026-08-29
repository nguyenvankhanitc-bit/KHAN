/** @odoo-module **/

import { onMounted, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

const SEARCH_PLACEHOLDER = "Tìm kiếm theo mã, nhóm ca, giờ...";
// roster form: cancel button next to save

export class PhanHeWorkShiftListController extends ListController {
    static template = "lug_phan_he.WorkShiftListView";
    static components = {
        ...ListController.components,
        PhanHeAppSidebar,
    };

    setup() {
        super.setup();
        useEffect(
            () => {
                const input = this.rootRef.el?.querySelector(".o_searchview_input");
                if (input) {
                    const placeholder = ["north_schedule", "south_schedule", "dtt_schedule"].includes(this.sidebarActiveKey)
                        ? "Tìm theo cửa hàng, ngày áp dụng..."
                        : SEARCH_PLACEHOLDER;
                    input.setAttribute("placeholder", placeholder);
                }
            },
            () => [this.rootRef.el, this.model.root.count]
        );
    }

    get className() {
        return `${super.className || ""} o_phan_he_app_shell`;
    }

    get sidebarActiveKey() {
        return "work_shift";
    }

    onClickImport() {
        const { context, resModel } = this.env.searchModel;
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { active_model: resModel, context },
        });
    }
}

export class PhanHeWorkShiftFormController extends FormController {
    static template = "lug_phan_he.WorkShiftFormView";
    static components = {
        ...FormController.components,
        PhanHeAppSidebar,
    };

    get className() {
        const result = { ...(super.className || {}) };
        // Odoo XXL form uses flex + container width:1px. App shell is CSS grid,
        // so that class collapses the form to a blank white column.
        delete result["o_xxl_form_view h-100"];
        delete result.o_xxl_form_view;
        result.o_phan_he_app_shell = true;
        result.o_field_highlight = true;
        result["h-100"] = true;
        return result;
    }

    get sidebarActiveKey() {
        return "work_shift";
    }
}

export class PhanHeNorthScheduleListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.NorthScheduleListView";

    get sidebarActiveKey() {
        return "north_schedule";
    }
}

export class PhanHeNorthScheduleFormController extends PhanHeWorkShiftFormController {
    static template = "lug_phan_he.NorthScheduleFormView";

    get sidebarActiveKey() {
        return "north_schedule";
    }
}

export class PhanHeStoreScheduleListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.StoreScheduleListView";

    get sidebarActiveKey() {
        const region = this.props.context?.default_region
            || this.env.searchModel?.context?.default_region;
        if (region === "south") {
            return "south_schedule";
        }
        if (region === "dtt") {
            return "dtt_schedule";
        }
        return "north_schedule";
    }
}

export class PhanHeStoreScheduleFormController extends PhanHeWorkShiftFormController {
    static template = "lug_phan_he.StoreScheduleFormView";

    get sidebarActiveKey() {
        const region = this.props.context?.default_region
            || this.env.searchModel?.context?.default_region;
        if (region === "south") {
            return "south_schedule";
        }
        if (region === "dtt") {
            return "dtt_schedule";
        }
        return "north_schedule";
    }
}

export class PhanHeDttScheduleListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.DttScheduleListView";

    get sidebarActiveKey() {
        return "dtt_schedule";
    }
}

export class PhanHeDttScheduleFormController extends PhanHeWorkShiftFormController {
    static template = "lug_phan_he.DttScheduleFormView";

    get sidebarActiveKey() {
        return "dtt_schedule";
    }
}

registry.category("views").add("phan_he_work_shift_list", {
    ...listView,
    Controller: PhanHeWorkShiftListController,
});

registry.category("views").add("phan_he_work_shift_form", {
    ...formView,
    Controller: PhanHeWorkShiftFormController,
});

registry.category("views").add("phan_he_north_schedule_list", {
    ...listView,
    Controller: PhanHeNorthScheduleListController,
});

registry.category("views").add("phan_he_north_schedule_form", {
    ...formView,
    Controller: PhanHeNorthScheduleFormController,
});

registry.category("views").add("phan_he_store_schedule_list", {
    ...listView,
    Controller: PhanHeStoreScheduleListController,
});

registry.category("views").add("phan_he_store_schedule_form", {
    ...formView,
    Controller: PhanHeStoreScheduleFormController,
});

registry.category("views").add("phan_he_dtt_schedule_list", {
    ...listView,
    Controller: PhanHeDttScheduleListController,
});

export class PhanHeRosterListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.RosterListView";

    get sidebarActiveKey() {
        return "roster";
    }

    async onRosterListSave() {
        if (this.editedRecord) {
            await this.editedRecord.save();
        }
    }

    async onRosterListDiscard() {
        await this.onClickDiscard();
    }

    async onRosterListEdit() {
        const list = this.model.root;
        const selected = (list.selection && list.selection[0]) || list.records[0];
        if (!selected) {
            await this.onClickCreate();
            return;
        }
        await this.openRecord(selected);
    }
}

export class PhanHeRosterFormController extends PhanHeWorkShiftFormController {
    static template = "lug_phan_he.RosterFormView";

    setup() {
        super.setup();
        onMounted(() => {
            const record = this.model.root;
            if (record.resId && record.isInEdition) {
                record.switchMode("readonly");
            }
        });
    }

    get sidebarActiveKey() {
        return this.model?.root?.resId ? "roster" : "roster_new";
    }

    async onRosterSave() {
        const saved = await this.saveButtonClicked();
        if (saved !== false && this.model.root.resId) {
            await this.model.root.switchMode("readonly");
        }
    }

    async discard() {
        if (this.model.root.resId) {
            if (this.model.root.isInEdition) {
                await this.model.root.switchMode("readonly");
            }
            return;
        }
        return;
    }

    async onRosterDiscard() {
        return this.discard();
    }

    async onRosterEdit() {
        await this.model.root.switchMode("edit");
    }
}

registry.category("views").add("phan_he_dtt_schedule_form", {
    ...formView,
    Controller: PhanHeDttScheduleFormController,
});

registry.category("views").add("phan_he_roster_list", {
    ...listView,
    Controller: PhanHeRosterListController,
});

registry.category("views").add("phan_he_roster_form", {
    ...formView,
    Controller: PhanHeRosterFormController,
});
