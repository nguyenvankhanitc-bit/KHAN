/** @odoo-module **/
// Danh sách công việc CHT: kéo xuống để chép (giống Excel) cho cột Admin / BP liên quan.
// Rê chuột vào ô -> hiện ô vuông xanh ở góc dưới phải; nhấn giữ ô vuông, kéo xuống các dòng bên dưới rồi thả:
// giá trị của ô nguồn được chép cho các dòng đã kéo qua.

import { onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

const FILL_MODEL = "store.cht.task";
const FILL_FIELDS = ["admin_user_ids", "related_user_ids"];
const HANDLE = 12; // vùng bấm (px) ở góc dưới phải ô

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.list?.resModel !== FILL_MODEL) {
            return;
        }
        this.chtFillOrm = useService("orm");
        this.chtFillNotify = useService("notification");
        const onDown = (ev) => this.chtFillStart(ev);
        const onClick = (ev) => {
            // vừa kéo xong: chặn cú click sinh ra sau khi thả chuột (không mở popup sửa dòng)
            if (this.chtFillJustDone) {
                ev.stopPropagation();
                ev.preventDefault();
                this.chtFillJustDone = false;
            }
        };
        onMounted(() => {
            this.rootRef.el?.addEventListener("mousedown", onDown, true);
            this.rootRef.el?.addEventListener("click", onClick, true);
        });
        onWillUnmount(() => {
            this.rootRef.el?.removeEventListener("mousedown", onDown, true);
            this.rootRef.el?.removeEventListener("click", onClick, true);
        });
    },

    chtFillFindRecord(datapointId, list = this.props.list) {
        for (const rec of list.records || []) {
            if (rec.id === datapointId) {
                return rec;
            }
        }
        for (const group of list.groups || []) {
            const found = group.list && this.chtFillFindRecord(datapointId, group.list);
            if (found) {
                return found;
            }
        }
        return null;
    },

    chtFillStart(ev) {
        if (ev.button !== 0) {
            return;
        }
        const td = ev.target.closest?.("td[name]");
        const field = td?.getAttribute("name");
        if (!td || !FILL_FIELDS.includes(field)) {
            return;
        }
        const rect = td.getBoundingClientRect();
        if (ev.clientX < rect.right - HANDLE || ev.clientY < rect.bottom - HANDLE) {
            return; // không bấm vào ô vuông ở góc: để Odoo xử lý bình thường
        }
        const srcTr = td.closest("tr.o_data_row");
        const table = td.closest("table");
        if (!srcTr || !table) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const rows = [...table.querySelectorAll("tbody tr.o_data_row")];
        const srcIdx = rows.indexOf(srcTr);
        const scroller = table.closest(".o_list_renderer");
        let endIdx = srcIdx;
        td.classList.add("o_cht_fill_src");
        document.body.classList.add("o_cht_filling");

        const mark = () => {
            rows.forEach((tr, i) => {
                tr.querySelector(`td[name="${field}"]`)?.classList.toggle("o_cht_fill_range", i > srcIdx && i <= endIdx);
            });
        };
        const onMove = (e) => {
            // tự cuộn khi kéo sát mép dưới / trên khung bảng
            if (scroller) {
                const box = scroller.getBoundingClientRect();
                if (e.clientY > box.bottom - 30) {
                    scroller.scrollTop += 20;
                } else if (e.clientY < box.top + 60) {
                    scroller.scrollTop -= 20;
                }
            }
            const el = document.elementFromPoint(e.clientX, e.clientY);
            const tr = el?.closest?.("tr.o_data_row");
            if (tr && rows.includes(tr)) {
                endIdx = Math.max(srcIdx, rows.indexOf(tr));
                mark();
            }
        };
        const cleanup = () => {
            document.removeEventListener("mousemove", onMove, true);
            document.removeEventListener("mouseup", onUp, true);
            document.body.classList.remove("o_cht_filling");
            td.classList.remove("o_cht_fill_src");
            rows.forEach((tr) => tr.querySelector(`td[name="${field}"]`)?.classList.remove("o_cht_fill_range"));
        };
        const onUp = async () => {
            cleanup();
            this.chtFillJustDone = true;
            setTimeout(() => (this.chtFillJustDone = false), 300);
            if (endIdx <= srcIdx) {
                return;
            }
            const resIdOf = (tr) => this.chtFillFindRecord(tr.dataset.id)?.resId;
            const srcId = resIdOf(srcTr);
            const targetIds = rows.slice(srcIdx + 1, endIdx + 1).map(resIdOf).filter(Boolean);
            if (!srcId || !targetIds.length) {
                return;
            }
            try {
                const n = await this.chtFillOrm.call(FILL_MODEL, "fill_from", [srcId, targetIds, field]);
                await this.props.list.model.load();
                this.chtFillNotify.add(`Đã chép xuống ${n} dòng.`, { type: "success" });
            } catch (error) {
                this.chtFillNotify.add(error?.data?.message || error?.message || String(error), { type: "danger" });
            }
        };
        document.addEventListener("mousemove", onMove, true);
        document.addEventListener("mouseup", onUp, true);
    },
});
