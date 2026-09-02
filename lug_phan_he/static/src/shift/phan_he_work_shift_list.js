/** @odoo-module **/

import { onMounted, onWillStart, useEffect, useState, Component } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { RosterListBoard } from "./roster_list_board";
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { user } from "@web/core/user";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
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
                    const placeholder = this.sidebarActiveKey === "today_shift"
                        ? "Tìm nhân viên"
                        : this.sidebarActiveKey === "employees"
                        ? "Tìm theo tên, cửa hàng, ID..."
                        : ["north_schedule", "south_schedule", "dtt_schedule"].includes(this.sidebarActiveKey)
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

    setup() {
        super.setup();
        this.orm = useService("orm");
        onMounted(() => this._ensureGroupByStore());
    }

    _ensureGroupByStore() {
        const sm = this.env.searchModel;
        if (!sm) {
            return;
        }
        const grouped = (sm.groupBy || []).some((g) => String(g).split(":")[0] === "store_id");
        if (grouped) {
            return;
        }
        const item = Object.values(sm.searchItems || {}).find(
            (it) => it.type === "groupBy" && it.fieldName === "store_id"
        );
        if (item) {
            sm.toggleSearchItem(item.id);
        }
    }

    get sidebarActiveKey() {
        return "roster";
    }

    async openRecord(record) {
        const action = await this.orm.call(
            "linkq.monthly.roster",
            "action_open_schedule_popup",
            [record.resId]
        );
        await this.actionService.doAction(action);
    }

    onOpenLockSettings() {
        this.actionService.doAction("lug_phan_he.action_linkq_roster_lock_settings");
    }

    onClickCalendar() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Xem lịch",
            res_model: "linkq.monthly.roster",
            views: [[false, "calendar"], [false, "list"], [false, "form"]],
            target: "current",
        });
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
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.canUnlockRoster = false;
        onWillStart(async () => {
            this.canUnlockRoster = await user.hasGroup("lug_phan_he.group_linkq_manager")
                || await user.hasGroup("base.group_system")
                || await user.hasGroup("lug_phan_he.group_phan_he_admin");
        });
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

    get canUnlock() {
        const data = this.model.root.data;
        return Boolean(this.canUnlockRoster && data.is_locked);
    }

    async onRosterSave() {
        if (this.model.root.data.period_edit_blocked) {
            this.notification.add(
                "Kỳ xếp ca đã bị khóa. Không thể lưu lịch ca mới cho tháng này.",
                { type: "danger" }
            );
            return;
        }
        const saved = await this.saveButtonClicked();
        if (saved !== false && this.model.root.resId) {
            await this.model.root.switchMode("readonly");
        }
    }

    async onRosterDiscard() {
        await this.model.root.discard();
        if (this.model.root.resId) {
            await this.model.root.switchMode("readonly");
        }
    }

    async onRosterEdit() {
        if (this.model.root.data.state === "confirmed" || this.model.root.data.is_locked || this.model.root.data.period_edit_blocked) {
            return;
        }
        await this.model.root.switchMode("edit");
    }

    onRosterUnlock() {
        const rec = this.model.root;
        const name = rec.data.name || "";
        this.dialog.add(ConfirmationDialog, {
            title: "Mở khóa lịch ca?",
            body: `Lịch ca ${name} hiện đã bị khóa. Việc mở khóa sẽ cho phép nhân viên tiếp tục chỉnh sửa.`,
            confirmLabel: "Xác nhận mở khóa",
            cancelLabel: "Hủy",
            confirm: async () => {
                await this.orm.call("linkq.monthly.roster", "action_unlock_roster", [
                    [rec.resId],
                    "Quản lý mở khóa từ form",
                ]);
                this.notification.add("Đã mở khóa lịch ca.", { type: "success" });
                await rec.load();
            },
        });
    }
}

registry.category("views").add("phan_he_dtt_schedule_form", {
    ...formView,
    Controller: PhanHeDttScheduleFormController,
});

export class PhanHeRosterListRenderer extends ListRenderer {
    static groupRowTemplate = "lug_phan_he.RosterGroupRow";

    getRosterGroupTitle(group) {
        const name = group.displayName || "Chưa gán cửa hàng";
        const n = group.count || 0;
        return `CỬA HÀNG: ${name} (${n} bảng lịch)`;
    }
}

registry.category("views").add("phan_he_roster_list", {
    ...listView,
    Controller: PhanHeRosterListController,
    Renderer: PhanHeRosterListRenderer,
});

registry.category("views").add("phan_he_roster_form", {
    ...formView,
    Controller: PhanHeRosterFormController,
});

export class PhanHeAccessListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.AccessListView";

    get sidebarActiveKey() {
        return "access";
    }
}

export class PhanHeAccessFormController extends PhanHeWorkShiftFormController {
    static template = "lug_phan_he.AccessFormView";

    get sidebarActiveKey() {
        return "access";
    }
}

registry.category("views").add("phan_he_access_list", {
    ...listView,
    Controller: PhanHeAccessListController,
});

registry.category("views").add("phan_he_access_form", {
    ...formView,
    Controller: PhanHeAccessFormController,
});

export class PhanHeEmployeeListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.EmployeeListView";

    setup() {
        super.setup();
        this.isHrAdmin = false;
        onWillStart(async () => {
            this.isHrAdmin = await user.hasGroup("base.group_system");
        });
    }

    get className() {
        return `${super.className || ""} o_linkq_employee_list`;
    }

    get sidebarActiveKey() {
        return "employees";
    }

    onClickCreate() {
        this.actionService.doAction("lug_phan_he.action_linkq_employee_create");
    }

    async openRecord(record) {
        const name = record.data?.name || "";
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: name ? `Thông tin nhân sự - ${name}` : "Thông tin nhân sự",
            res_model: "linkq.employee",
            res_id: record.resId,
            views: [[false, "form"]],
            target: "new",
            context: { form_view_initial_mode: "readonly", dialog_size: "large" },
        });
    }

    onBulkHardDeleteEmployees() {
        if (!this.isHrAdmin) {
            return;
        }
        const ids = this.model.root.selection.map((r) => r.resId).filter(Boolean);
        if (!ids.length) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            title: "Xóa vĩnh viễn",
            body: `Bạn có chắc chắn muốn XÓA VĨNH VIỄN ${ids.length} nhân sự đã chọn? Dữ liệu không thể phục hồi!`,
            confirmLabel: "Xóa vĩnh viễn",
            confirm: async () => {
                await this.orm.call("linkq.employee", "action_hard_delete_permanent", [ids]);
                await this.model.root.load();
            },
        });
    }
}

export class LinkqEmpStateField extends Component {
    static template = "lug_phan_he.LinkqEmpStateField";
    static props = { ...standardFieldProps };

    get stateValue() {
        return this.props.record.data[this.props.name] || "";
    }

    get stateLabel() {
        const val = this.stateValue;
        const sel = this.props.record.fields[this.props.name]?.selection || [];
        const hit = sel.find((item) => item[0] === val);
        return hit ? hit[1] : val;
    }
}

registry.category("fields").add("linkq_emp_state", {
    component: LinkqEmpStateField,
    supportedTypes: ["selection"],
});

export class PhanHeEmployeeListRenderer extends ListRenderer {
    static groupRowTemplate = "lug_phan_he.EmployeeGroupRow";

    setup() {
        super.setup();
        onMounted(() => this._expandFirstEmployeeGroup());
    }

    async _expandFirstEmployeeGroup() {
        const list = this.props.list;
        if (!list?.isGrouped || !list.groups?.length) {
            return;
        }
        const first = list.groups[0];
        if (first.isFolded) {
            await first.toggle();
        }
    }

    getEmployeeGroupTitle(group) {
        return group.displayName || "Chưa gán cửa hàng";
    }

    getEmployeeGroupCount(group) {
        return `[ ${group.count || 0} nhân sự ]`;
    }
}

export class PhanHeEmployeeFormController extends FormController {
    static buttonTemplate = "lug_phan_he.EmployeeFormButtons";

    setup() {
        super.setup();
        this.isHrAdmin = false;
        onWillStart(async () => {
            this.isHrAdmin = await user.hasGroup("base.group_system");
        });
    }

    async onEmployeeEdit() {
        await this.model.root.switchMode("edit");
    }

    async onEmployeeSave() {
        const saved = await this.saveButtonClicked({ closable: false });
        if (saved === false) {
            return;
        }
        if (this.env.inDialog) {
            await this.env.dialogData.close();
        }
    }

    async onEmployeeCreate() {
        if (this.env.inDialog) {
            await this.env.dialogData.close();
        }
        await this.env.services.action.doAction("lug_phan_he.action_linkq_employee_create");
    }

    async onEmployeeClose() {
        if (this.env.inDialog) {
            await this.env.dialogData.close();
        }
    }

    async onEmployeeCancel() {
        if (this.model.root.resId) {
            await this.model.root.discard();
            await this.model.root.switchMode("readonly");
            return;
        }
        if (this.env.inDialog) {
            await this.env.dialogData.close();
        }
    }
}

registry.category("views").add("phan_he_employee_list", {
    ...listView,
    Controller: PhanHeEmployeeListController,
    Renderer: PhanHeEmployeeListRenderer,
});

registry.category("views").add("phan_he_employee_form", {
    ...formView,
    Controller: PhanHeEmployeeFormController,
    buttonTemplate: "lug_phan_he.EmployeeFormButtons",
});

export class PhanHeTodayShiftListController extends PhanHeWorkShiftListController {
    static template = "lug_phan_he.TodayShiftListView";

    get className() {
        return `${super.className || ""} o_linkq_today_shift_list`;
    }

    get sidebarActiveKey() {
        return "today_shift";
    }

    async openRecord() {
        return;
    }
}

registry.category("views").add("phan_he_today_shift_list", {
    ...listView,
    Controller: PhanHeTodayShiftListController,
});
