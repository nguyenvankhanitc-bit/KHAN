/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

function normalizeText(text) {
    return String(text || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();
}

export class DailyWorkSummaryReport extends Component {
    static template = "daily_work_task.DailyWorkSummaryReport";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        const year = now.getFullYear();
        this.state = useState({
            loading: true,
            exporting: false,
            message: false,
            filterQuery: "",
            monthMonth: now.getMonth() + 1,
            monthYear: year,
            months: [
                { value: 1, label: "Tháng 1" },
                { value: 2, label: "Tháng 2" },
                { value: 3, label: "Tháng 3" },
                { value: 4, label: "Tháng 4" },
                { value: 5, label: "Tháng 5" },
                { value: 6, label: "Tháng 6" },
                { value: 7, label: "Tháng 7" },
                { value: 8, label: "Tháng 8" },
                { value: 9, label: "Tháng 9" },
                { value: 10, label: "Tháng 10" },
                { value: 11, label: "Tháng 11" },
                { value: 12, label: "Tháng 12" },
            ],
            years: this._buildYears(year),
            departments: [],
            openDepts: {},
            totals: {
                total: 0,
                done: 0,
                in_progress: 0,
                not_started: 0,
                overdue: 0,
                duration_hours: 0,
            },
        });
        onWillStart(async () => {
            await this.loadReport();
        });
    }

    get reportTitle() {
        const m = String(this.state.monthMonth).padStart(2, "0");
        return `Báo cáo tổng — Tháng ${m}/${this.state.monthYear}`;
    }

    get monthLabel() {
        return `${String(this.state.monthMonth).padStart(2, "0")}/${this.state.monthYear}`;
    }

    /** KPI luôn tính trên toàn bộ dữ liệu tháng (không phụ thuộc lọc nhanh). */
    get companyTotals() {
        const totals = {
            total: 0,
            done: 0,
            in_progress: 0,
            not_started: 0,
            overdue: 0,
            duration_minutes: 0,
            duration_hours: 0,
        };
        for (const dept of this.state.departments || []) {
            for (const emp of dept.employees || []) {
                totals.total += Number(emp.total) || 0;
                totals.done += Number(emp.done) || 0;
                totals.in_progress += Number(emp.in_progress) || 0;
                totals.not_started += Number(emp.not_started) || 0;
                totals.overdue += Number(emp.overdue) || 0;
                totals.duration_minutes += Number(emp.duration_minutes) || 0;
            }
        }
        totals.duration_hours = totals.duration_minutes
            ? Math.round((totals.duration_minutes / 60) * 100) / 100
            : 0;
        return totals;
    }

    get filteredDepartments() {
        const q = normalizeText(this.state.filterQuery);
        const source = this.state.departments || [];
        if (!q) {
            return source.map((d) => ({
                ...d,
                key: normalizeText(d.name) || String(d.id || "none"),
                employees: d.employees || [],
            }));
        }
        const result = [];
        for (const d of source) {
            const deptMatch = normalizeText(d.name).includes(q);
            const emps = (d.employees || []).filter((e) =>
                normalizeText(e.name).includes(q)
            );
            if (deptMatch || emps.length) {
                result.push({
                    ...d,
                    key: normalizeText(d.name) || String(d.id || "none"),
                    employees: deptMatch ? d.employees || [] : emps,
                });
            }
        }
        return result;
    }

    isDeptOpen(deptKey) {
        if (this.state.filterQuery) {
            return true;
        }
        return !!this.state.openDepts[deptKey];
    }

    toggleDept(deptKey) {
        if (this.state.filterQuery) {
            return;
        }
        this.state.openDepts[deptKey] = !this.state.openDepts[deptKey];
    }

    deptTaskTotal(dept) {
        return (dept.employees || []).reduce((sum, e) => sum + (Number(e.total) || 0), 0);
    }

    _buildYears(centerYear) {
        const years = [];
        for (let y = centerYear - 2; y <= centerYear + 1; y++) {
            years.push(y);
        }
        return years;
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_summary_report", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
            });
            this.state.departments = data.departments || [];
            this.state.totals = data.totals || this.state.totals;
            this.state.message = data.message || false;
            this.state.openDepts = {};
            if (data.year) {
                this.state.monthYear = data.year;
            }
            if (data.month) {
                this.state.monthMonth = data.month;
            }
        } catch (e) {
            this.state.departments = [];
            this.state.message = e?.data?.message || _t("Không tải được báo cáo tổng.");
        } finally {
            this.state.loading = false;
        }
    }

    async onApply() {
        await this.loadReport();
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Bao_cao_tong.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async onExportExcel() {
        this.state.exporting = true;
        try {
            const result = await this.orm.call(
                "daily.task",
                "export_summary_report_excel",
                [],
                {
                    year: Number(this.state.monthYear),
                    month: Number(this.state.monthMonth),
                }
            );
            if (!result?.file_base64) {
                throw new Error(_t("Không nhận được file Excel."));
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add(_t("Đã xuất Báo cáo tổng."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_summary_report", DailyWorkSummaryReport);
