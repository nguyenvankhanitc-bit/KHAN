/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { Component, xml } from "@odoo/owl";
import { PhanHeItAssetEntryPopup } from "./phan_he_it_asset_entry_popup";

/** Bọc popup «Thêm / Chỉnh sửa tài sản» để mở qua dialog service. */
class PhanHeItAssetPopupHost extends Component {
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
