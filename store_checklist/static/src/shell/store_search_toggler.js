/** @odoo-module **/

import { onMounted } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { SearchBarToggler } from "@web/search/search_bar/search_bar_toggler";

// Màn hình nhỏ: nút kính lúp thành chữ "Tìm"; trong hộp thoại chọn bản ghi (vd. chọn cửa hàng) thanh tìm kiếm hiện sẵn
SearchBarToggler.template = "store_checklist.SearchBarToggler";

patch(SearchBarToggler.prototype, {
    setup() {
        super.setup?.(...arguments);
        onMounted(() => {
            if (this.env.dialogData && this.props.isSmall && !this.props.showSearchBar) {
                this.props.toggleSearchBar();
            }
        });
    },

    // "Tìm": có chữ đã gõ thì chạy tìm kiếm ngay (gợi ý / áp dụng như nhấn Enter), chưa gõ thì đặt con trỏ vào ô tìm
    onSearchClick() {
        const modals = document.querySelectorAll(".modal");
        const input = modals[modals.length - 1]?.querySelector(".o_searchview_input");
        if (!input) {
            return this.props.toggleSearchBar();
        }
        input.focus();
        if (input.value) {
            input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        }
    },
});
