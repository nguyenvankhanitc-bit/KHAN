/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Báo cáo tổng hợp theo hạng mục (mục BÁO CÁO). */
export class DailyWorkUserSummary extends Component {
    static template = "daily_work_task.DailyWorkUserSummary";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            message: false,
            month: now.getMonth() + 1,
            year: now.getFullYear(),
            employeeId: 0,
            employees: [],
            canPick: false,
            profile: {},
            rows: [],
            total: {},
            pending: [],
            highlights: "",
            solutions: "",
            canEditSelf: false,
            canEditManager: false,
            reportDate: "",
        });
        this.months = Array.from({ length: 12 }, (_, i) => i + 1);
        this.years = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1];
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "user_summary";
    }

    async load() {
        this.state.loading = true;
        const data = await this.orm.call("daily.task", "get_user_summary", [], {
            year: Number(this.state.year),
            month: Number(this.state.month),
            employee_id: Number(this.state.employeeId) || false,
        });
        this.state.message = data.message || false;
        this.state.profile = data.profile || {};
        this.state.rows = data.summary_rows || [];
        this.state.total = data.summary_total || {};
        this.state.pending = data.pending || [];
        this.state.highlights = data.highlights || "";
        this.state.solutions = data.solutions || "";
        this.state.canEditSelf = Boolean(data.can_edit_self);
        this.state.canEditManager = Boolean(data.can_edit_manager);
        this.state.reportDate = data.report_date || "";
        this.state.canExport = !data.report_perm || data.report_perm.export !== false;
        this.state.employees = (data.filters && data.filters.employees) || [];
        this.state.canPick = Boolean(data.can_pick_employee);
        this.state.employeeId = Number(data.selected_employee_id || this.state.employeeId) || 0;
        this.state.dirty = false;
        this.state.loading = false;
    }

    async onFilter(field, ev) {
        this.state[field] = Number(ev.target.value) || 0;
        await this.load();
    }

    barStyle(v) {
        return `width:${Math.max(0, Math.min(100, Number(v) || 0))}%`;
    }

    fmtPct(v) {
        return `${(Number(v) || 0).toFixed(1).replace(".", ",")}%`;
    }

    fmt1(v) {
        return (Number(v) || 0).toFixed(1).replace(".", ",");
    }

    ratingClass(rating) {
        return { "Xuất sắc": "is-excellent", "Tốt": "is-good", "Đạt": "is-ok" }[rating] || "is-weak";
    }

    onText(field, ev) {
        this.state[field] = ev.target.value;
        this.state.dirty = true;
    }

    onNote(row, ev) {
        row.note = ev.target.value;
        this.state.dirty = true;
    }

    onCause(item, ev) {
        item.cause = ev.target.value;
        this.state.dirty = true;
    }

    get signDate() {
        const d = new Date();
        return `TP.HCM, ngày ${d.getDate()} tháng ${d.getMonth() + 1} năm ${d.getFullYear()}`;
    }

    async onSave() {
        this.state.saving = true;
        try {
            const vals = {
                highlights: this.state.highlights,
                solutions: this.state.solutions,
                causes: Object.fromEntries(this.state.pending.map((p) => [p.id, p.cause || ""])),
            };
            if (this.state.canEditManager) {
                vals.cat_notes = Object.fromEntries(this.state.rows.map((r) => [r.key, r.note || ""]));
            }
            await this.orm.call("daily.task", "save_user_summary", [
                Number(this.state.year),
                Number(this.state.month),
                Number(this.state.employeeId) || false,
                vals,
            ]);
            this.state.dirty = false;
            this.notification.add(_t("Đã lưu báo cáo tổng hợp."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async onExport() {
        try {
            if (this.state.dirty && (this.state.canEditSelf || this.state.canEditManager)) {
                await this.onSave();
            }
            const res = await this.orm.call("daily.task", "export_user_summary_excel", [], {
                year: Number(this.state.year),
                month: Number(this.state.month),
                employee_id: Number(this.state.employeeId) || false,
            });
            const bin = atob(res.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const url = URL.createObjectURL(new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }));
            const a = document.createElement("a");
            a.href = url;
            a.download = res.filename || "bao_cao_tong_hop.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        }
    }
}

registry.category("actions").add("daily_work_user_summary", DailyWorkUserSummary);
