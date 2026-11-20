/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";

// Tiêu đề popup "Xử lý sai phạm": tên biên bản, trạng thái và 4 thẻ số liệu, tự cập nhật khi sửa dòng trong bảng
export class StoreViolationHeader extends Component {
    static template = "store_checklist.ViolationHeader";
    static props = { auditId: { type: Number, optional: true }, bus: Object };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ d: null });
        onWillStart(() => this.load());
        useBus(this.props.bus, "update", () => {
            clearTimeout(this._timer);
            this._timer = setTimeout(() => this.load(), 400);
        });
    }

    async load() {
        if (this.props.auditId) {
            this.state.d = await this.orm.call("store.audit.action", "get_violation_header", [this.props.auditId]);
        }
    }

    async exportExcel() {
        const file = await this.orm.call("store.audit.action", "export_violation_xlsx", [this.props.auditId]);
        const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
        const link = document.createElement("a");
        link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
        link.download = file.name;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    // In bằng iframe riêng (chỉ gồm tiêu đề + bảng, khổ ngang) rồi mở hộp thoại in của trình duyệt để chọn máy in.
    // shortcut: dựng từ DOM đang hiển thị, chưa in im lặng thẳng ra một máy in cố định.
    print() {
        const table = document.querySelector(".o_store_violation_list table.o_list_table");
        const d = this.state.d;
        if (!table || !d) {
            return;
        }
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Biên bản xử lý sai phạm</title><style>
            @page { size: A4 landscape; margin: 8mm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: Arial, sans-serif; font-size: 11px; color: #111; }
            .top { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; }
            .top img { height: 60px; } h2 { margin: 0; font-size: 20px; color: #12285f; } p { margin: 2px 0 0; color: #475569; }
            .cards { display: flex; gap: 8px; margin: 6px 0 10px; }
            .card { flex: 1; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 9px; }
            .card span { display: block; font-size: 10px; font-weight: 700; color: #334155; } .card b { font-size: 16px; color: #12285f; }
            table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #64748b; padding: 4px 5px; vertical-align: top; }
            th { background: #1e3a6e; color: #fff; text-align: center; } th.g1 { background: #15803d; } th.g2 { background: #c2410c; }
            td.g2 { background: #fff1e0; } tr.grp td { background: #dce6f2; font-weight: 700; color: #1e3a8a; } td.n { text-align: center; }
        </style></head><body></body></html>`);
        doc.close();
        const el = (tag, cls, text) => {
            const e = doc.createElement(tag);
            if (cls) { e.className = cls; }
            if (text !== undefined) { e.textContent = text; }
            return e;
        };
        const top = el("div", "top");
        const img = doc.createElement("img");
        img.src = "/web/image/res.company/" + d.company_id + "/logo_web";
        top.appendChild(img);
        const t = el("div");
        t.appendChild(el("h2", "", "BIÊN BẢN XỬ LÝ SAI PHẠM"));
        t.appendChild(el("p", "", `Cửa hàng: ${d.store}  |  Ngày kiểm tra: ${d.date}`));
        top.appendChild(t);
        const cards = el("div", "cards");
        [["Tổng điểm đạt", `${this.fmt(d.got)} / ${this.fmt(d.max)}`], ["Tổng điểm trừ", this.fmt(d.deduct)],
         ["Số lỗi cần xử lý", `${d.total} tiêu chí`], ["Tiến độ khắc phục", `${d.done} / ${d.total} (${this.donePct}%)`]].forEach(([l, v]) => {
            const c = el("div", "card");
            c.appendChild(el("span", "", l));
            c.appendChild(el("b", "", v));
            cards.appendChild(c);
        });
        const out = el("table");
        const head = el("tr");
        const heads = [...table.querySelectorAll("thead th")].filter((th) => th.dataset.name);
        const grp = (name) => (["responsible_ids", "action_plan", "attachment_ids", "resp_note", "date_done", "state"].includes(name) ? "g1" : ["reviewer_ids", "control_done", "review_note"].includes(name) ? "g2" : "");
        heads.forEach((th) => head.appendChild(el("th", grp(th.dataset.name), th.innerText.trim())));
        out.appendChild(head);
        table.querySelectorAll("tbody tr").forEach((tr) => {
            const row = el("tr");
            if (tr.classList.contains("o_group_header")) {
                row.className = "grp";
                const td = el("td", "", tr.innerText.trim());
                td.colSpan = heads.length;
                row.appendChild(td);
            } else if (tr.classList.contains("o_data_row")) {
                tr.querySelectorAll("td[name]").forEach((td) => {
                    const box = td.querySelector("input[type=checkbox]");
                    const name = td.getAttribute("name");
                    const cell = el("td", (box || ["line_sequence", "line_max_score", "line_actual_score", "score_deduct", "date_done", "state"].includes(name) ? "n " : "") + grp(name),
                        box ? (box.checked ? "✔" : "") : td.innerText.trim());
                    row.appendChild(cell);
                });
            } else {
                return;
            }
            out.appendChild(row);
        });
        doc.body.append(top, cards, out);
        const go = () => {
            frame.contentWindow.focus();
            frame.contentWindow.print();
            setTimeout(() => frame.remove(), 60000);
        };
        if (img.complete) { go(); } else { img.onload = go; img.onerror = go; }
    }

    fmt(n) {
        return String(Math.round((n + Number.EPSILON) * 100) / 100);
    }

    get gotPct() {
        const d = this.state.d;
        return d && d.max ? Math.min(100, Math.round((d.got / d.max) * 100)) : 0;
    }

    get donePct() {
        const d = this.state.d;
        return d && d.total ? Math.round((d.done / d.total) * 100) : 0;
    }
}

// Điểm chuẩn đánh giá: sửa trong popup xong thì giữ nguyên các nhóm đang mở và vị trí cuộn của bảng
// Cột của bảng Điểm chuẩn được kéo copy như Excel (nắm ô vuông nhỏ góc dưới phải ô rồi kéo lên / xuống)
const FILL_FIELDS = ["sub_group_id", "responsible_ids", "controller_ids", "lug_group_ids", "max_score"];

function allListRecords(list) {
    if (!list) {
        return [];
    }
    if (list.groups) {
        return list.groups.flatMap((g) => allListRecords(g.list));
    }
    return list.records || [];
}

export class StoreBenchmarkController extends ListController {
    setup() {
        super.setup();
        this.fillNotify = useService("notification");
        this.fillOrm = useService("orm");
        onMounted(() => this.setupFillHandle());
        onWillUnmount(() => this.teardownFillHandle());
        let wasOpen = false;
        let keep = null;
        let timer;
        const observer = new MutationObserver(() => {
            const open = Boolean(document.querySelector(".modal .o_form_view"));
            if (!wasOpen && open) {
                keep = this.snapshot();
            } else if (wasOpen && !open && keep) {
                const saved = keep;
                clearTimeout(timer);
                timer = setTimeout(() => this.restore(saved), 700);
            }
            wasOpen = open;
        });
        onMounted(() => observer.observe(document.body, { childList: true, subtree: true }));
        onWillUnmount(() => {
            observer.disconnect();
            clearTimeout(timer);
        });
    }

    // ---------- Kéo copy kiểu Excel ----------
    setupFillHandle() {
        const root = this.rootRef?.el;
        if (!root) {
            return;
        }
        const handle = document.createElement("div");
        handle.className = "o_store_fill_handle";
        handle.title = _t("Kéo để copy sang các dòng khác");
        document.body.appendChild(handle);
        this._fill = { root, handle, drag: null, td: null };
        const hide = () => {
            handle.style.display = "none";
            this._fill.td?.classList.remove("o_store_fill_hover");
            this._fill.td = null;
        };
        this._fillHide = hide;
        this._fillOver = (ev) => {
            if (this._fill.drag || ev.target === handle) {
                return;
            }
            const td = ev.target.closest?.("td.o_data_cell");
            if (!(td && root.contains(td) && FILL_FIELDS.includes(td.getAttribute("name")))) {
                hide();
                return;
            }
            if (td !== this._fill.td) {
                hide();
                this._fill.td = td;
                td.classList.add("o_store_fill_hover");
            }
            const rect = td.getBoundingClientRect();
            handle.style.left = `${rect.right - 6}px`;
            handle.style.top = `${rect.bottom - 6}px`;
            handle.style.display = "block";
        };
        this._fillLeave = (ev) => {
            if (!this._fill.drag && ev.relatedTarget !== handle) {
                hide();
            }
        };
        this._fillDown = (ev) => {
            if (ev.button !== 0 || ev.target !== handle) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            const td = this._fill.td;
            const tr = td?.isConnected && td.closest("tr.o_data_row");
            if (!tr) {
                return;
            }
            this._fill.drag = { field: td.getAttribute("name"), srcRow: tr, rows: [tr] };
            document.body.classList.add("o_store_filling");
            td.classList.add("o_store_fill_src");
        };
        this._fillMove = (ev) => {
            const drag = this._fill.drag;
            if (!drag) {
                return;
            }
            ev.preventDefault();
            const el = document.elementFromPoint(ev.clientX, ev.clientY);
            const tr = el?.closest?.("tr.o_data_row");
            if (!tr || !root.contains(tr)) {
                return;
            }
            const all = [...root.querySelectorAll("tr.o_data_row")];
            const a = all.indexOf(drag.srcRow);
            const b = all.indexOf(tr);
            if (a < 0 || b < 0) {
                return;
            }
            drag.rows = all.slice(Math.min(a, b), Math.max(a, b) + 1);
            root.querySelectorAll("td.o_store_fill_target").forEach((c) => c.classList.remove("o_store_fill_target"));
            for (const row of drag.rows) {
                row.querySelector(`td[name="${drag.field}"]`)?.classList.add("o_store_fill_target");
            }
        };
        this._fillUp = async () => {
            const drag = this._fill.drag;
            if (!drag) {
                return;
            }
            this._fill.drag = null;
            this._fillSuppressClick = true;
            setTimeout(() => (this._fillSuppressClick = false), 300);
            document.body.classList.remove("o_store_filling");
            root.querySelectorAll(".o_store_fill_target, .o_store_fill_src").forEach((c) =>
                c.classList.remove("o_store_fill_target", "o_store_fill_src"));
            hide();
            await this.applyFill(drag);
        };
        this._fillClick = (ev) => {
            if (this._fillSuppressClick || ev.target === handle) {
                ev.preventDefault();
                ev.stopPropagation();
            }
        };
        root.addEventListener("mouseover", this._fillOver);
        root.addEventListener("mouseleave", this._fillLeave);
        root.addEventListener("click", this._fillClick, true);
        handle.addEventListener("mousedown", this._fillDown);
        document.addEventListener("mousemove", this._fillMove);
        document.addEventListener("mouseup", this._fillUp);
        document.addEventListener("scroll", this._fillLeave, true);
    }

    teardownFillHandle() {
        if (!this._fill) {
            return;
        }
        const { root, handle } = this._fill;
        root.removeEventListener("mouseover", this._fillOver);
        root.removeEventListener("mouseleave", this._fillLeave);
        root.removeEventListener("click", this._fillClick, true);
        document.removeEventListener("mousemove", this._fillMove);
        document.removeEventListener("mouseup", this._fillUp);
        document.removeEventListener("scroll", this._fillLeave, true);
        handle.remove();
        document.body.classList.remove("o_store_filling");
    }

    // copy giá trị ô nguồn sang cùng cột của các dòng đã kéo qua (ghi thẳng xuống server, quyền Sửa vẫn được kiểm tra)
    async applyFill({ field, srcRow, rows }) {
        const records = allListRecords(this.model.root);
        const byId = (tr) => records.find((r) => r.id === tr.dataset.id);
        const src = byId(srcRow);
        const targets = rows.filter((tr) => tr !== srcRow).map(byId).filter((r) => r && r.resId);
        if (!src || !targets.length) {
            return;
        }
        const value = src.data[field];
        let vals;
        if (value && typeof value === "object" && "currentIds" in value) {
            vals = { [field]: [[6, 0, [...value.currentIds]]] };
        } else if (value && typeof value === "object") {
            vals = { [field]: value.id || false };
        } else {
            vals = { [field]: value === undefined ? false : value };
        }
        try {
            await this.fillOrm.write(this.props.resModel, targets.map((r) => r.resId), vals);
            const saved = this.snapshot();
            await this.model.load();
            this.restore(saved);
            this.fillNotify.add(_t("Đã copy sang %s dòng.", targets.length), { type: "success" });
        } catch (error) {
            this.fillNotify.add(error?.data?.message || error?.message || _t("Không copy được."), { type: "danger" });
        }
    }

    snapshot() {
        const scrollers = [...document.querySelectorAll(".o_store_list_wrap, .o_list_renderer, .o_content")];
        return {
            open: (this.model.root.groups || []).filter((g) => !g.isFolded).map((g) => g.displayName),
            scroll: scrollers.map((el) => [el, el.scrollLeft, el.scrollTop]),
            page: [document.scrollingElement.scrollLeft, document.scrollingElement.scrollTop],
        };
    }

    async restore(saved) {
        for (const group of this.model.root.groups || []) {
            if (group.isFolded && saved.open.includes(group.displayName)) {
                await group.toggle();
            }
        }
        setTimeout(() => {
            saved.scroll.forEach(([el, left, top]) => {
                el.scrollLeft = left;
                el.scrollTop = top;
            });
            document.scrollingElement.scrollTo(saved.page[0], saved.page[1]);
        }, 150);
    }
}

// Dòng chỉ sửa được khi user là người phụ trách hoặc người kiểm soát; còn lại bấm vào không vào chế độ sửa (không hiện Lưu / Hủy)
export class StoreViolationRenderer extends ListRenderer {
    getCellClass(column, record) {
        const cls = super.getCellClass(column, record);
        // cột Trạng thái xử lý: Hoàn thành = xanh nhạt, chưa xử lý / đang làm = hồng nhạt
        return column.name === "state" ? `${cls} ${record.data.state === "done" ? "o_sv_done" : "o_sv_todo"}` : cls;
    }
    async onCellClicked(record, column, ev, newWindow) {
        if (!(record.data.can_edit_resp || record.data.can_edit_ctrl)) {
            return;
        }
        return super.onCellClicked(record, column, ev, newWindow);
    }
}

// Danh sách xử lý sai phạm chỉ để xem: bấm vào dòng không mở biểu mẫu (tránh lỗi owl khi user không đủ quyền)
export class StoreViolationReadonlyRenderer extends ListRenderer {
    async onCellClicked() {}
    getCellClass(column, record) {
        const cls = super.getCellClass(column, record);
        // cột Trạng thái xử lý: Hoàn thành = xanh nhạt, chưa xử lý / đang làm = hồng nhạt
        return column.name === "state" ? `${cls} ${record.data.state === "done" ? "o_sv_done" : "o_sv_todo"}` : cls;
    }
}

export class StoreViolationController extends ListController {
    static template = "store_checklist.ViolationListView";
    static components = { ...ListController.components, StoreViolationHeader };
}

// Chi tiết một quản lý: thẻ số liệu và danh sách cửa hàng phụ trách (Báo cáo theo quản lý)
export class StoreMgrDetailDialog extends Component {
    static template = "store_checklist.MgrDetailDialog";
    static components = { Dialog };
    static props = { row: Object, domain: Array, onView: Function, close: Function };

    setup() {
        this.state = useState({ tab: "all", page: 0 });
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async exportExcel() {
        try {
            const file = await this.orm.call("store.audit", "export_manager_xlsx", [this.props.domain], { manager_id: this.props.row.id });
            const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
            link.download = file.name;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (e) {
            this.notification.add(e?.data?.message || e?.message || "Không xuất được Excel", { type: "danger" });
        }
    }

    // In: sao chép nội dung popup + CSS của trang vào iframe ẩn rồi gọi print
    print() {
        const src = document.querySelector(".o_store_mgr_dlg");
        if (!src) {
            return;
        }
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        const css = [...document.querySelectorAll("link[rel=stylesheet], style")].map((n) => n.outerHTML).join("");
        doc.open();
        doc.write(`<html><head><base href="${location.origin}/">${css}<style>.o_store_mgr_dlg .acts{display:none}body{padding:16px;background:#fff}</style></head><body>${src.outerHTML}</body></html>`);
        doc.close();
        setTimeout(() => {
            frame.contentWindow.focus();
            frame.contentWindow.print();
            setTimeout(() => frame.remove(), 1500);
        }, 600);
    }

    // lọc Tất cả / Đạt chuẩn / Cần cải thiện + phân trang 8 dòng
    get view() {
        const size = 8;
        const all = this.props.row.stores;
        const rows = all.filter((s) => this.state.tab === "all" || (this.state.tab === "ok") === s.ok);
        return {
            rows, size, pages: Math.max(1, Math.ceil(rows.length / size)),
            page: rows.slice(this.state.page * size, (this.state.page + 1) * size),
            errors: all.reduce((t, s) => t + s.errors, 0),
        };
    }

    setTab(tab) {
        this.state.tab = tab;
        this.state.page = 0;
    }

    levelTone(tone) {
        return { green: "#16a34a", blue: "#2563eb", orange: "#f59e0b", red: "#dc2626", darkred: "#7f1d1d" }[tone] || "#64748b";
    }

    get levelColor() {
        return this.levelTone(this.props.row.tone);
    }

    get passPct() {
        const r = this.props.row;
        return r.audits ? Math.round((100 * r.passed) / r.audits) : 0;
    }
}

// Hộp chọn cửa hàng trước khi Xuất Excel / In "Danh sách xử lý sai phạm"
export class StoreViolPickDialog extends Component {
    static template = "store_checklist.ViolPickDialog";
    static components = { Dialog };
    static props = {
        title: String,
        confirmLabel: String,
        stores: Array,
        onConfirm: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ picked: Object.fromEntries(this.props.stores.map((s) => [s.id, true])) });
    }

    get pickedIds() {
        return this.props.stores.filter((s) => this.state.picked[s.id]).map((s) => s.id);
    }

    get allPicked() {
        return this.pickedIds.length === this.props.stores.length;
    }

    toggleAll() {
        const v = !this.allPicked;
        this.props.stores.forEach((s) => (this.state.picked[s.id] = v));
    }

    confirm() {
        const ids = this.pickedIds;
        if (!ids.length) {
            return;
        }
        this.props.close();
        this.props.onConfirm(ids);
    }
}

registry.category("views").add("store_benchmark_list", { ...listView, Controller: StoreBenchmarkController });
registry.category("views").add("store_violation_readonly", { ...listView, Renderer: StoreViolationReadonlyRenderer });
registry.category("views").add("store_violation_list", { ...listView, Controller: StoreViolationController, Renderer: StoreViolationRenderer });
