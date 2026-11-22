/** @odoo-module **/
// Checklist NVBH › Checklist CV CHT: CHT tick công việc đến hạn trong ngày, gửi ASM đánh giá; tab vi phạm & mức phạt tháng.

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export class StoreChtPage extends Component {
    static template = "store_checklist.StoreChtPage";
    static props = { kind: { type: String, optional: true } };

    setup() {
        // kind = "asm": Checklist CV ASM (ASM tick, RSM đánh giá); mặc định CHT (CHT tick, ASM đánh giá)
        this.isAsm = this.props.kind === "asm";
        this.model = this.isAsm ? "store.asm.check" : "store.cht.check";
        this.doer = this.isAsm ? "ASM" : "CHT";
        this.reviewer = this.isAsm ? "RSM" : "ASM";
        this.orm = useService("orm");
        this.notification = useService("notification");
        const today = new Date();
        this.today = ymd(today);
        this.state = useState({
            tab: "day",
            stores: [],
            storeId: false,
            date: this.today,
            month: this.today.slice(0, 7),
            check: null,
            days: {},
            loading: false,
            report: null,
            reportStore: "",
            open: {},
        });
        onWillStart(async () => {
            this.state.stores = await this.orm.call("store.nvbh.check", "get_my_stores", []).catch(() => []);
            if (this.state.stores.length) {
                this.state.storeId = this.state.stores[0].id;
                await this.loadDay();
            }
        });
    }

    notifyError(error) {
        const msg = error?.data?.message || error?.message || String(error);
        this.notification.add(msg, { type: "danger" });
    }

    // ---------- Tab Check list ngày ----------
    async loadDay() {
        if (!this.state.storeId) {
            this.state.check = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.check = await this.orm.call(this.model, "cht_get_day", [this.state.storeId, this.state.date]);
            this.state.days = await this.orm.call(this.model, "cht_month_days", [this.state.storeId, this.state.date.slice(0, 7)]);
        } catch (error) {
            this.state.check = null;
            this.notifyError(error);
        } finally {
            this.state.loading = false;
        }
    }

    async refreshDays() {
        this.state.days = await this.orm.call(this.model, "cht_month_days", [this.state.storeId, this.state.date.slice(0, 7)]).catch(() => ({}));
    }

    onStore(ev) {
        this.state.storeId = Number(ev.target.value) || false;
        return this.state.tab === "day" ? this.loadDay() : this.loadReport();
    }

    onDate(ev) {
        if (!ev.target.value) {
            return;
        }
        this.state.date = ev.target.value > this.today ? this.today : ev.target.value;
        return this.loadDay();
    }

    shiftDay(delta) {
        const d = new Date(this.state.date + "T00:00:00");
        d.setDate(d.getDate() + delta);
        const v = ymd(d);
        if (v > this.today) {
            return;
        }
        this.state.date = v;
        return this.loadDay();
    }

    get calendar() {
        // lịch tháng của ngày đang chọn: ô trống đầu tuần + từng ngày
        const [y, m] = this.state.date.split("-").map(Number);
        const first = new Date(y, m - 1, 1);
        const last = new Date(y, m, 0).getDate();
        const lead = (first.getDay() + 6) % 7; // T2 = 0
        const cells = Array.from({ length: lead }, (_, i) => ({ key: `e${i}`, empty: true }));
        for (let d = 1; d <= last; d++) {
            const key = `${y}-${pad(m)}-${pad(d)}`;
            const info = this.state.days[key];
            let tone = "";
            if (info) {
                tone = info.violations ? "bad" : info.state === "evaluated" ? "ok" : info.state === "submitted" ? "wait" : "doing";
            }
            cells.push({ key, day: d, info, tone, future: key > this.today, active: key === this.state.date });
        }
        return cells;
    }

    pickDay(cell) {
        if (cell.empty || cell.future) {
            return;
        }
        this.state.date = cell.key;
        return this.loadDay();
    }

    async call(method, args) {
        try {
            this.state.check = Object.assign({}, this.state.check, await this.orm.call(this.model, method, args));
            await this.refreshDays();
        } catch (error) {
            this.notifyError(error);
        }
    }

    toggle(line) {
        return this.call("cht_toggle", [line.id, !line.done]);
    }

    toggleAll(done) {
        return this.call("cht_toggle_all", [this.state.check.id, done]);
    }

    async saveNote(line, ev) {
        const note = ev.target.value;
        if (note === line.note) {
            return;
        }
        try {
            await this.orm.call(this.model, "cht_note", [line.id, note]);
            line.note = note;
        } catch (error) {
            this.notifyError(error);
        }
    }

    async submit() {
        await this.call("cht_submit", [this.state.check.id]);
        this.notification.add(`Đã gửi check list ${this.doer} cho ${this.reviewer} đánh giá.`, { type: "success" });
    }

    evaluate(line, result) {
        return this.call("cht_eval", [line.id, line.eval_result === result ? "" : result]);
    }

    evalAll() {
        return this.call("cht_eval_all", [this.state.check.id, ""]);
    }

    async finishEval() {
        await this.call("cht_finish_eval", [this.state.check.id]);
        this.notification.add(`Đã xác nhận đánh giá check list ${this.doer}.`, { type: "success" });
    }

    reopen() {
        return this.call("cht_reopen", [this.state.check.id]);
    }

    get pct() {
        const c = this.state.check;
        return c && c.total ? Math.round((c.done_count * 100) / c.total) : 0;
    }

    fmtDate(v) {
        return v ? v.split("-").reverse().join("/") : "";
    }

    // ---------- Tab Vi phạm & mức phạt tháng ----------
    async setTab(tab) {
        this.state.tab = tab;
        if (tab === "report") {
            return this.loadReport();
        }
        return this.loadDay();
    }

    async loadReport() {
        this.state.loading = true;
        try {
            this.state.report = await this.orm.call(this.model, "cht_month_violations", [this.state.month, Number(this.state.reportStore) || false]);
            const open = {};
            for (const s of this.state.report.stores) {
                open[s.store_id] = true;
            }
            this.state.open = open;
        } catch (error) {
            this.state.report = null;
            this.notifyError(error);
        } finally {
            this.state.loading = false;
        }
    }

    onMonth(ev) {
        if (ev.target.value) {
            this.state.month = ev.target.value;
            return this.loadReport();
        }
    }

    onReportStore(ev) {
        this.state.reportStore = ev.target.value;
        return this.loadReport();
    }

    toggleStore(id) {
        this.state.open[id] = !this.state.open[id];
    }

    money(v) {
        return v ? Number(v).toLocaleString("vi-VN") + " đ" : "—";
    }

    async exportReport() {
        const r = this.state.report;
        if (!r) {
            return;
        }
        const rows = [];
        for (const s of r.stores) {
            for (const t of s.tasks) {
                rows.push([s.store, s.mien, t.task, t.count, t.items.map((i) => `${i.date} (L${i.nth}: ${i.fine})`).join("; "), t.money || "", t.percent.join(", ")]);
            }
        }
        try {
            const file = await this.orm.call("store.nvbh.check", "export_table_xlsx", [
                `VI PHẠM CHECK LIST CÔNG VIỆC ${this.doer}`, `Tháng ${r.month}`,
                ["Cửa hàng", "Miền", "Công việc", "Số lần VP", "Ngày vi phạm (lần: mức phạt)", "Tiền phạt (đ)", "Phạt theo % TN"],
                rows, ["Tổng", "", "", r.total_count, "", r.total_money, ""], `Vi_pham_${this.doer}`,
            ]);
            const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
            link.download = file.name;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            this.notifyError(error);
        }
    }
}
