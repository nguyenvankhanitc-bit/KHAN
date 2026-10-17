/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Báo cáo NV Kho (BÁO CÁO → Các loại báo cáo). */
export class DailyWorkKhoReport extends Component {
    static template = "daily_work_task.DailyWorkKhoReport";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            message: false,
            month: now.getMonth() + 1,
            year: now.getFullYear(),
            teamId: 0,
            teamName: "",
            teams: [],
            employeeId: 0,
            employees: [],
            canPick: false,
            showEmployee: false,
            rows: [],
            canExport: true,
            exporting: false,
        });
        this.months = Array.from({ length: 12 }, (_, i) => i + 1);
        this.years = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1];
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "kho_report";
    }

    get params() {
        return {
            year: Number(this.state.year),
            month: Number(this.state.month),
            team_id: Number(this.state.teamId) || false,
            employee_id: Number(this.state.employeeId) || false,
        };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_kho_report", [], this.params);
            this.state.message = data.message || false;
            this.state.teams = data.teams || [];
            this.state.teamId = data.team_id || 0;
            this.state.teamName = data.team_name || "";
            this.state.employees = data.employees || [];
            this.state.employeeId = data.employee_id || 0;
            this.state.canPick = Boolean(data.can_pick_employee);
            this.state.showEmployee = Boolean(data.show_employee);
            this.state.rows = data.rows || [];
            this.state.canExport = !data.report_perm || data.report_perm.export !== false;
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được báo cáo.");
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    get title() {
        return `BÁO CÁO CV NV ${(this.state.teamName || "").toUpperCase()}`.trim();
    }

    get totalMinutes() {
        return this.state.rows.reduce((s, r) => s + (Number(r.minutes) || 0), 0);
    }

    get ratingCount() {
        const out = { pass: 0, average: 0, fail: 0, none: 0 };
        for (const r of this.state.rows) {
            const k = { "Đạt": "pass", "Trung bình": "average", "Không đạt": "fail" }[r.rating] || "none";
            out[k] += 1;
        }
        return out;
    }

    ratingClass(label) {
        const k = { "Đạt": "is-pass", "Trung bình": "is-average", "Không đạt": "is-fail" }[label];
        return `o_dkr_rate ${k || ""}`;
    }

    async onFilter(field, ev) {
        this.state[field] = Number(ev.target.value) || 0;
        if (field === "teamId") {
            this.state.employeeId = 0;
        }
        await this.load();
    }

    async onExport() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task", "export_kho_report_excel", [], this.params);
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
            a.download = res.filename || "bao_cao_nv_kho.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_kho_report", DailyWorkKhoReport);
