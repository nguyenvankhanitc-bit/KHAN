/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";

// Điện thoại: trong hộp thoại chọn bản ghi (vd. chọn cửa hàng), gõ xong khoảng nửa giây thì tự áp dụng gợi ý đầu tiên
// ("Tìm kiếm Tên hoặc mã cửa hàng cho: ...") như bấm vào gợi ý, không cần chọn tay rồi bấm "Tìm".
const AUTO_SEARCH_DELAY = 500;

patch(SearchBar.prototype, {
    onSearchInput(ev) {
        super.onSearchInput(...arguments);
        if (!(this.env.dialogData && this.ui.isSmall) || ev.isComposing) {
            return;
        }
        clearTimeout(this._storeAutoSearchTimer);
        if (!ev.target.value.trim()) {
            return;
        }
        this._storeAutoSearchTimer = setTimeout(() => {
            const query = this.inputRef.el?.value.trim();
            if (!query || this.state.query.trim() !== query) {
                return;
            }
            const item = this.items.find((i) => !i.isAddCustomFilterButton && !i.unselectable && !i.isChild && !i.loadMore);
            if (item) {
                this.selectItem(item);
            }
        }, AUTO_SEARCH_DELAY);
    },
});
