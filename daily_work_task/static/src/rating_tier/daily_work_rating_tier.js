/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

let seq = 0;
const newKey = () => `new-${Date.now()}-${seq++}`;

/** Cài đặt → Xếp loại hiệu suất (trong khung ứng dụng, có thanh bên). */
export class DailyWorkRatingTier extends Component {
    static template = "daily_work_task.DailyWorkRatingTier";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true, saving: false, rows: [], deleted: [], canEdit: false, dirty: false, ratings: [],
        });
        onWillStart(() => this.load());
    }

    /** performance = Xếp loại hiệu suất · eval = Xếp loại đạt (Kiểm tra CV). */
    get kind() {
        return this.props.action?.context?.tier_kind === "eval" ? "eval" : "performance";
    }

    get isEval() {
        return this.kind === "eval";
    }

    get pageTitle() {
        return this.isEval ? "Xếp loại đạt" : "Xếp loại hiệu suất";
    }

    get shellActiveNav() {
        return this.isEval ? "eval_tier" : "rating_tier";
    }

    async load() {
        this.state.loading = true;
        const data = await this.orm.call("daily.task.rating.tier", "get_tiers", [], { kind: this.kind });
        this.state.ratings = data.ratings || [];
        this.state.rows = (data.tiers || []).map((t) => ({ ...t, key: `id-${t.id}` }));
        this.state.canEdit = Boolean(data.can_edit);
        this.state.deleted = [];
        this.state.dirty = false;
        this.state.loading = false;
    }

    /** Bảng hiển thị: sắp theo Từ %, Đến % tự tính theo các mức đang tích Áp dụng. */
    get viewRows() {
        const rows = [...this.state.rows].sort((a, b) => (Number(a.from_percent) || 0) - (Number(b.from_percent) || 0));
        const bounds = [...new Set(rows.filter((r) => r.apply).map((r) => Number(r.from_percent) || 0))].sort((a, b) => a - b);
        return rows.map((r) => {
            let to = "—";
            if (r.apply) {
                const from = Number(r.from_percent) || 0;
                const higher = bounds.filter((b) => b > from);
                to = `${Math.max(higher.length ? higher[0] - 1 : 100, from)}%`;
            }
            return { ...r, to };
        });
    }

    rowOf(key) {
        return this.state.rows.find((r) => r.key === key);
    }

    onApply(key, ev) {
        this.rowOf(key).apply = ev.target.checked;
        this.state.dirty = true;
    }

    onFrom(key, ev) {
        this.rowOf(key).from_percent = ev.target.value;
        this.state.dirty = true;
    }

    onName(key, ev) {
        this.rowOf(key).name = ev.target.value;
        this.state.dirty = true;
    }

    onRatingKey(key, ev) {
        const row = this.rowOf(key);
        row.rating_key = ev.target.value;
        row.name = (this.state.ratings.find((r) => r.key === row.rating_key) || {}).label || "";
        this.state.dirty = true;
    }

    ratingClass(rkey) {
        return rkey ? `o_drt_rk is-${rkey}` : "o_drt_rk";
    }

    onAdd() {
        const max = Math.max(0, ...this.state.rows.map((r) => Number(r.from_percent) || 0));
        this.state.rows.push({
            key: newKey(), id: false, apply: true, from_percent: Math.min(100, max + 1), name: "", rating_key: "",
        });
        this.state.dirty = true;
    }

    onRemove(key) {
        const row = this.rowOf(key);
        if (row?.id) {
            this.state.deleted.push(row.id);
        }
        this.state.rows = this.state.rows.filter((r) => r.key !== key);
        this.state.dirty = true;
    }

    async onCancel() {
        await this.load();
    }

    async onSave() {
        for (const r of this.state.rows) {
            const v = Number(r.from_percent);
            if (this.isEval && !r.rating_key) {
                this.notification.add(_t("Vui lòng chọn Xếp loại (Đạt / Trung bình / Không đạt) cho mọi dòng."), {
                    type: "warning",
                });
                return;
            }
            if (!(r.name || "").trim()) {
                this.notification.add(_t("Vui lòng nhập Xếp loại cho mọi dòng."), { type: "warning" });
                return;
            }
            if (Number.isNaN(v) || v < 0 || v > 100) {
                this.notification.add(_t("«Từ %» phải nằm trong khoảng 0 – 100."), { type: "warning" });
                return;
            }
        }
        this.state.saving = true;
        try {
            await this.orm.call("daily.task.rating.tier", "save_tiers", [
                this.state.rows.map((r) => ({
                    id: r.id || false,
                    apply: Boolean(r.apply),
                    from_percent: Number(r.from_percent) || 0,
                    name: (r.name || "").trim(),
                    rating_key: r.rating_key || false,
                })),
                this.state.deleted,
            ], { kind: this.kind });
            this.notification.add(_t("Đã lưu %s.", this.pageTitle.toLowerCase()), { type: "success" });
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("daily_work_rating_tier", DailyWorkRatingTier);
