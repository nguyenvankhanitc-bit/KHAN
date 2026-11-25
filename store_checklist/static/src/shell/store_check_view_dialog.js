/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

// Popup một checklist công việc đã lưu (Checklist NVBH > Danh sách checklist NV).
// Nội dung công việc chỉ đọc; các cấp đánh giá (CHT -> ASM -> RSM -> Admin, luồng động theo Sơ đồ tổ chức) lần lượt chấm
// KQ đánh giá (Đạt / T.Bình / Không đạt) và Chi tiết lỗi. Mỗi cấp một khối màu, chỉ cấp đang đến lượt mới sửa được.
export class StoreCheckViewDialog extends Component {
    static template = "store_checklist.CheckViewDialog";
    static components = { Dialog };
    static props = { payload: Object, onSaved: { type: Function, optional: true }, close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            lines: JSON.parse(JSON.stringify(this.props.payload.lines || [])),
            meta: this.metaOf(this.props.payload),
            saving: false,
        });
        this.lockUndone();
        this.snap = this.snapshot();
    }

    // cấp đang chấm: dòng chưa có làm hiện sẵn Không đạt (0đ), không sửa được
    lockUndone() {
        const k = this.editIdx;
        if (k < 0) {
            return;
        }
        for (const line of this.state.lines) {
            if (!line.is_done) {
                line.ev[k].result = "bad";
                line.ev[k].detail = "";
            }
        }
    }

    get steps() {
        return this.state.meta.steps || [];
    }

    // chỉ số (0-based) của bước mà người dùng hiện tại đang được phép đánh giá; -1 nếu không có
    get editIdx() {
        return this.steps.findIndex((s) => s.can_edit);
    }

    get canEval() {
        return this.editIdx >= 0;
    }

    get editStep() {
        return this.editIdx >= 0 ? this.steps[this.editIdx] : null;
    }

    stepClass(k) {
        return "sx-" + ((k % 4) + 1);
    }

    // Kết quả dùng để tính điểm: cấp cuối cùng đã hoàn tất (hoặc đang chấm) có kết quả cho dòng đó
    finalOf(line) {
        for (let k = this.steps.length - 1; k >= 0; k--) {
            const s = this.steps[k];
            const ev = line.ev[k];
            if ((s.done || s.can_edit) && ev && ev.result) {
                return ev;
            }
        }
        return { result: "", detail: "" };
    }

    countErrors(text) {
        return (text || "").split(/\r?\n/).filter((x) => x.trim()).length;
    }

    // Điểm đạt theo kết quả đánh giá: Đạt = điểm chuẩn; T.Bình = điểm chuẩn / 2; Không đạt hoặc chưa đánh giá = 0
    // Số lỗi = số dòng có nội dung trong Chi tiết lỗi (1 dòng = 1 lỗi); có lỗi thì điểm = 0
    lineErrors(line) {
        return this.countErrors(this.finalOf(line).detail);
    }

    get errorTotal() {
        return this.state.lines.reduce((sum, l) => sum + this.lineErrors(l), 0);
    }

    lineScore(line) {
        if (this.lineErrors(line)) {
            return 0;
        }
        const rate = { good: 1, avg: 0.5, bad: 0 }[this.finalOf(line).result] ?? 0;
        return Math.round((line.score || 0) * rate * 100) / 100;
    }

    get points() {
        return Math.round(this.state.lines.reduce((sum, l) => sum + this.lineScore(l), 0) * 100) / 100;
    }

    metaOf(p) {
        const { lines, ...meta } = p;
        return meta;
    }

    get allDone() {
        return this.state.lines.length > 0 && this.state.lines.every((l) => l.is_done);
    }

    get canSubmit() {
        return this.state.meta.can_submit === true && this.state.meta.state === "draft";
    }

    get stateText() {
        const m = this.state.meta;
        const who = `${m.staff_name} (${m.role_label || m.role_code})`;
        const flow = this.steps.length
            ? this.steps.map((s) => `${s.code}${s.name ? " (" + s.name + ")" : ""}`).join(" → ")
            : "Chưa có";
        if (m.state === "approved") {
            return `Đã hoàn tất đánh giá · Người thực hiện: ${who} · Luồng: ${flow}`;
        }
        if (m.state === "pending_review") {
            const cur = this.steps.find((s) => s.current);
            return `Người thực hiện: ${who} · Đang chờ: ${cur ? cur.code + (cur.name ? " (" + cur.name + ")" : "") : "cấp trên"} · Luồng: ${flow}`;
        }
        if (m.wait_staff) {
            return `Người thực hiện: ${who} · Chưa hoàn thành checklist (${m.staff_done || 0}/${m.staff_total || 0} công việc) — cấp trên chưa được đánh giá · Luồng đánh giá: ${flow}`;
        }
        return `Người thực hiện: ${who} · Luồng đánh giá: ${flow}`;
    }

    // Hạn / khóa theo thời hạn: NVBH đến hết D+4; mỗi cấp đánh giá 4 ngày kể từ khi đến lượt
    get deadlineText() {
        const m = this.state.meta;
        if (m.lock_msg) {
            return m.lock_msg;
        }
        const re = this.steps.find((s) => s.reedit);
        if (re) {
            return `${re.code} được sửa lại đánh giá đến ${re.reedit_until} (sau giờ này hệ thống tự khóa)`;
        }
        if (m.state === "approved") {
            return "";
        }
        if (m.state === "draft" && m.wait_staff) {
            return m.staff_deadline ? `Hạn NV check list: hết ngày ${m.staff_deadline}` : "";
        }
        const cur = this.steps.find((s) => s.current);
        return cur && cur.deadline ? `Hạn ${cur.code} đánh giá: hết ngày ${cur.deadline} (quá hạn hệ thống khóa, điểm ${cur.code} tính 0đ)` : "";
    }

    applyPayload(payload) {
        this.state.lines = JSON.parse(JSON.stringify(payload.lines));
        this.state.meta = this.metaOf(payload);
        this.lockUndone();
        this.snap = this.snapshot();
    }

    async submitToReviewer() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const payload = await this.orm.call("store.nvbh.check", "submit_to_reviewer", [this.props.payload.id]);
            this.applyPayload(payload);
            this.notification.add(`Đã gửi cấp trên đánh giá: ${payload.reviewer_name}`, { type: "success" });
            this.props.onSaved?.();
        } finally {
            this.state.saving = false;
        }
    }

    get results() {
        return [["good", "Đạt"], ["avg", "T.Bình"], ["bad", "Không đạt"]];
    }

    snapshot() {
        return JSON.stringify(this.state.lines.map((l) => [l.id, ...l.ev.map((e) => [e.result || "", (e.detail || "").trim()])]));
    }

    get dirty() {
        return this.snapshot() !== this.snap;
    }

    groupStart(index) {
        const lines = this.state.lines;
        return index === 0 || lines[index - 1].group !== lines[index].group;
    }

    groupInfo(group) {
        const rows = this.state.lines.filter((l) => l.group === group);
        return { count: rows.length, done: rows.filter((l) => l.is_done).length };
    }

    statusLabel(status) {
        return { todo: "Chưa làm", doing: "Đang làm", done: "Đã làm" }[status] || "";
    }

    sel(a, b) {
        return String(a) === String(b);
    }

    // ---- Đánh giá theo bước k (0-based) ----
    canEditStep(k) {
        return Boolean(this.steps[k] && this.steps[k].can_edit);
    }

    // dòng chưa tích "Có làm": cấp trên không đánh giá được, tự tính Không đạt (0đ)
    lineLocked(line) {
        return !line.is_done;
    }

    setResult(line, k, value) {
        if (!this.canEditStep(k) || this.lineLocked(line)) {
            return;
        }
        const ev = line.ev[k];
        ev.result = ev.result === value ? "" : value;
        if (ev.result) {
            ev.reviewer_id = this.steps[k].user_id || ev.reviewer_id;
        }
    }

    // tích chung cho cả hạng mục: mọi việc trong nhóm đều đang là kết quả này thì bỏ chọn, ngược lại đặt tất cả về kết quả này
    groupAll(group, k, value) {
        const rows = this.state.lines.filter((l) => l.group === group && !this.lineLocked(l));
        return rows.length > 0 && rows.every((l) => l.ev[k].result === value);
    }

    setGroupResult(group, k, value) {
        if (!this.canEditStep(k)) {
            return;
        }
        const rows = this.state.lines.filter((l) => l.group === group && !this.lineLocked(l));
        const clear = rows.every((l) => l.ev[k].result === value);
        for (const line of rows) {
            line.ev[k].result = clear ? "" : value;
            if (line.ev[k].result) {
                line.ev[k].reviewer_id = this.steps[k].user_id || line.ev[k].reviewer_id;
            }
        }
    }

    // 3 ô All ở tiêu đề KQ đánh giá (Đạt / T.Bình / Không đạt): tích = mọi hạng mục / mọi công việc nhận kết quả đó;
    // bỏ tích (đang là kết quả đó hết) = xóa kết quả của cấp này
    allResult(k, value) {
        const lines = this.state.lines.filter((l) => !this.lineLocked(l));
        return lines.length > 0 && lines.every((l) => l.ev[k].result === value);
    }

    setAllResult(k, value) {
        if (!this.canEditStep(k)) {
            return;
        }
        const clear = this.allResult(k, value);
        for (const line of this.state.lines.filter((l) => !this.lineLocked(l))) {
            line.ev[k].result = clear ? "" : value;
            if (!clear) {
                line.ev[k].reviewer_id = this.steps[k].user_id || line.ev[k].reviewer_id;
            }
        }
    }

    allGood(k) {
        return this.allResult(k, "good");
    }

    setAllGood(k) {
        return this.setAllResult(k, "good");
    }

    // nhập chi tiết lỗi thì KQ đánh giá tự chuyển về Không đạt
    setDetail(line, k, ev) {
        if (!this.canEditStep(k) || this.lineLocked(line)) {
            return;
        }
        const e = line.ev[k];
        e.detail = ev.target.value;
        if (this.countErrors(e.detail)) {
            e.result = "bad";
            e.reviewer_id = this.steps[k].user_id || e.reviewer_id;
        }
    }

    get allRated() {
        const k = this.editIdx;
        return k >= 0 && this.state.lines.length > 0 && this.state.lines.every((l) => l.ev[k].result);
    }

    // Bấm Lưu = lưu đánh giá của cấp đang đến lượt; chấm đủ mọi đầu việc thì hoàn tất cấp đó và chuyển cho cấp tiếp theo
    async save() {
        const k = this.editIdx;
        if (k < 0 || this.state.saving) {
            return;
        }
        if (!this.dirty && !this.allRated) {
            return;
        }
        this.state.saving = true;
        try {
            const step = this.steps[k];
            const changes = this.state.lines.map((l) => ({ id: l.id, result: l.ev[k].result || "", detail: (l.ev[k].detail || "").trim() }));
            const payload = await this.orm.call("store.nvbh.check", "save_step_evaluation", [this.props.payload.id, step.no, changes]);
            const finished = payload.step_done >= step.no;
            this.applyPayload(payload);
            if (step.reedit) {
                this.notification.add(`Đã lưu sửa lại đánh giá ${step.code}`, { type: "success" });
            } else if (!finished) {
                this.notification.add(`Đã lưu đánh giá ${step.code} (chưa chấm đủ nên chưa hoàn tất)`, { type: "success" });
            } else if (payload.state === "approved") {
                this.notification.add(`${step.code} đã đánh giá xong · phiếu hoàn tất và khóa`, { type: "success" });
            } else {
                const next = (payload.steps || []).find((s) => s.current);
                this.notification.add(`${step.code} đã đánh giá xong · đã gửi thông báo cho ${next ? next.code + (next.name ? " (" + next.name + ")" : "") : "cấp tiếp theo"}`, { type: "success" });
            }
            this.props.onSaved?.();
            this.props.close(); // lưu xong thì đóng popup
        } finally {
            this.state.saving = false;
        }
    }
}

// Hộp chọn nhân viên trước khi In / Xuất Excel Bảng checklist Tổng (mỗi nhân viên một sheet / một trang)
export class StoreStaffPickDialog extends Component {
    static template = "store_checklist.StaffPickDialog";
    static components = { Dialog };
    static props = { title: String, confirmLabel: String, items: Array, selected: { type: Array, optional: true }, onConfirm: Function, close: Function };

    setup() {
        const sel = new Set(this.props.selected || []);
        this.state = useState({ picked: Object.fromEntries(this.props.items.map((i) => [i.key, sel.has(i.key)])), q: "" });
    }

    get shown() {
        const q = this.state.q.trim().toLowerCase();
        return q ? this.props.items.filter((i) => i.label.toLowerCase().includes(q)) : this.props.items;
    }

    get pickedKeys() {
        return this.props.items.filter((i) => this.state.picked[i.key]).map((i) => i.key);
    }

    get allPicked() {
        return this.pickedKeys.length === this.props.items.length;
    }

    toggleAll() {
        const v = !this.allPicked;
        this.props.items.forEach((i) => (this.state.picked[i.key] = v));
    }

    confirm() {
        const keys = this.pickedKeys;
        if (keys.length) {
            this.props.close();
            this.props.onConfirm(keys);
        }
    }
}


// Hộp chọn Miền & nhiều Cửa hàng trước khi Xuất Excel BC Hiệu suất NVBH (mỗi cửa hàng 1 sheet)
export class StorePerfExportDialog extends Component {
    static template = "store_checklist.PerfExportDialog";
    static components = { Dialog };
    static props = {
        stores: Array,
        defaultMien: { type: String, optional: true },
        defaultSelected: { type: Array, optional: true },
        monthLabel: { type: String, optional: true },
        onConfirm: Function,
        close: Function,
    };

    setup() {
        const initMien = this.props.defaultMien || "";
        const sel = new Set(this.props.defaultSelected || []);
        const picked = {};
        for (const s of this.props.stores) {
            picked[s.id] = sel.size ? sel.has(s.id) : !initMien || (s.mien || "") === initMien;
        }
        this.state = useState({ mien: initMien, q: "", picked });
    }

    get mienStores() {
        const m = this.state.mien;
        return m ? this.props.stores.filter((s) => (s.mien || "") === m) : this.props.stores;
    }

    get shown() {
        const q = this.state.q.trim().toLowerCase();
        if (!q) {
            return this.mienStores;
        }
        return this.mienStores.filter((s) => `${s.name} ${s.asm || ""} ${s.mien || ""}`.toLowerCase().includes(q));
    }

    get pickedIds() {
        return this.props.stores.filter((s) => this.state.picked[s.id]).map((s) => s.id);
    }

    get allShownPicked() {
        return this.shown.length > 0 && this.shown.every((s) => this.state.picked[s.id]);
    }

    onChangeMien(ev) {
        const m = ev.target.value;
        this.state.mien = m;
        for (const s of this.props.stores) {
            this.state.picked[s.id] = !m || (s.mien || "") === m;
        }
    }

    toggleAllShown() {
        const v = !this.allShownPicked;
        for (const s of this.shown) {
            this.state.picked[s.id] = v;
        }
    }

    confirm() {
        const ids = this.pickedIds;
        if (ids.length) {
            this.props.close();
            this.props.onConfirm(ids);
        }
    }
}
