/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

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
        const grp = (name) => (["responsible_ids", "action_plan", "date_done", "state"].includes(name) ? "g1" : ["reviewer_ids", "control_done"].includes(name) ? "g2" : "");
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

registry.category("views").add("store_violation_list", { ...listView, Controller: StoreViolationController });
