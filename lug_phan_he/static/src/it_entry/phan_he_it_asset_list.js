/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { Component, xml } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { PhanHeItAssetEntryPopup } from "./phan_he_it_asset_entry_popup";

/** Bọc popup «Thêm / Chỉnh sửa tài sản» để mở qua dialog service. */
export class PhanHeItAssetPopupHost extends Component {
    static template = xml`<PhanHeItAssetEntryPopup resId="props.resId" onClose="props.close" onSaved="props.onSaved"/>`;
    static components = { PhanHeItAssetEntryPopup };
    static props = ["*"];
}

/** Danh sách tài sản Máy chủ: bấm dòng / «Mới» → popup nhập giống «Thêm mới» (thay form chuẩn). */
export class PhanHeItAssetListController extends ListController {
    _openAssetPopup(resId) {
        this.env.services.dialog.add(PhanHeItAssetPopupHost, {
            resId: resId || false,
            onSaved: () => this.model.load(),
        });
    }

    async openRecord(record) {
        this._openAssetPopup(record.resId);
    }

    async createRecord() {
        this._openAssetPopup(false);
    }
}

registry.category("views").add("phan_he_it_asset_list", {
    ...listView,
    Controller: PhanHeItAssetListController,
});


/** Cột «Thao tác» (chỉ tài khoản quản trị): ✏️ sửa bằng popup · 🗑 xóa (có xác nhận). */
export class PhanHeItAssetActionsField extends Component {
    static template = xml`
        <div class="ph-asset-actions" t-on-click.stop="">
            <button type="button" class="ph-asset-act is-edit" title="Sửa tài sản" t-on-click.stop="onEdit">
                <i class="fa fa-pencil"/>
            </button>
            <button type="button" class="ph-asset-act is-del" title="Xóa tài sản" t-on-click.stop="onDelete">
                <i class="fa fa-trash"/>
            </button>
        </div>`;
    static props = { ...standardFieldProps };

    get resId() {
        return this.props.record.resId;
    }

    _reload() {
        return this.props.record.model.load();
    }

    onEdit() {
        this.env.services.dialog.add(PhanHeItAssetPopupHost, {
            resId: this.resId,
            onSaved: () => this._reload(),
        });
    }

    onDelete() {
        const name = this.props.record.data.name || this.props.record.data.code || "";
        this.env.services.dialog.add(ConfirmationDialog, {
            title: "Xóa tài sản",
            body: `Xóa tài sản «${name}»? Thao tác này không hoàn tác được.`,
            confirmLabel: "Xóa",
            cancelLabel: "Hủy",
            confirm: async () => {
                try {
                    await this.env.services.orm.unlink("phan.he.it.asset", [this.resId]);
                    this.env.services.notification.add("Đã xóa tài sản.", { type: "success" });
                    await this._reload();
                } catch (error) {
                    this.env.services.notification.add(
                        error?.data?.message || "Không xóa được tài sản.",
                        { type: "danger" }
                    );
                }
            },
            cancel: () => {},
        });
    }
}

registry.category("fields").add("phan_he_it_asset_actions", {
    component: PhanHeItAssetActionsField,
    supportedTypes: ["integer"],
});
