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

const EMPTY_KPI = {
    total: 0,
    done: 0,
    in_progress: 0,
    not_started: 0,
    overdue: 0,
    duration_minutes: 0,
    duration_hours: 0,
};

export class DailyWorkViewer extends Component {
    static template = "daily_work_task.DailyWorkViewer";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        const year = now.getFullYear();
        this.state = useState({
            loading: true,
            employees: [],
            states: [],
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
            openDepts: {},
            panels: {},
        });
        onWillStart(async () => {
            await this.loadBootstrap();
        });
    }

    get filteredEmployees() {
        const q = normalizeText(this.state.filterQuery);
        if (!q) {
            return this.state.employees;
        }
        return this.state.employees.filter((e) => {
            const hay = normalizeText(`${e.name} ${e.department} ${e.email}`);
            return hay.includes(q);
        });
    }

    get employeesByDepartment() {
        const map = new Map();
        for (const emp of this.filteredEmployees) {
            const name = String(emp.department || "").trim() || "Chưa có phòng ban";
            const key = normalizeText(name) || "__none__";
            if (!map.has(key)) {
                map.set(key, { id: key, name, employees: [] });
            }
            map.get(key).employees.push(emp);
        }
        const groups = [...map.values()];
        groups.sort((a, b) => {
            if (a.id === "__none__") {
                return 1;
            }
            if (b.id === "__none__") {
                return -1;
            }
            return a.name.localeCompare(b.name, "vi");
        });
        for (const g of groups) {
            g.employees.sort((a, b) => (a.name || "").localeCompare(b.name || "", "vi"));
        }
        return groups;
    }

    get monthLabel() {
        const m = String(this.state.monthMonth).padStart(2, "0");
        return `${m}/${this.state.monthYear}`;
    }

    isDeptOpen(deptId) {
        if (this.state.filterQuery) {
            return true;
        }
        return !!this.state.openDepts[deptId];
    }

    async toggleDept(dept) {
        if (this.state.filterQuery) {
            return;
        }
        const deptId = dept.id;
        const willOpen = !this.state.openDepts[deptId];
        this.state.openDepts[deptId] = willOpen;
        if (willOpen) {
            await this.prefetchDeptMonthCounts(dept.employees || []);
        }
    }

    panelOf(empId) {
        return (
            this.state.panels[empId] || {
                open: false,
                loading: false,
                tasks: [],
                kpi: { ...EMPTY_KPI },
                monthTotal: null,
                monthHours: null,
                countLoaded: false,
                canEdit: false,
                canDelete: false,
                error: false,
            }
        );
    }

    taskGroupsOf(empId) {
        const groups = [];
        const indexByKey = new Map();
        for (const row of this.panelOf(empId).tasks || []) {
            const key = row.work_group_id || 0;
            const label = (row.work_group_label || "").trim() || "Không có hạng mục";
            if (!indexByKey.has(key)) {
                indexByKey.set(key, groups.length);
                groups.push({
                    key,
                    label,
                    rows: [],
                    count: 0,
                    duration_minutes: 0,
                    duration_hours_display: "0",
                });
            }
            const g = groups[indexByKey.get(key)];
            g.rows.push({ ...row, stt: g.rows.length + 1 });
            g.count += 1;
            g.duration_minutes += Number(row.duration_minutes) || 0;
        }
        for (const g of groups) {
            g.duration_hours_display = this.formatHours(g.duration_minutes);
        }
        groups.sort((a, b) => {
            if (a.key === 0 && b.key !== 0) {
                return 1;
            }
            if (b.key === 0 && a.key !== 0) {
                return -1;
            }
            return String(a.label).localeCompare(String(b.label), "vi");
        });
        return groups;
    }

    formatHours(minutes) {
        const m = Number(minutes) || 0;
        if (m <= 0) {
            return "0";
        }
        return (m / 60).toFixed(2).replace(/\.?0+$/, "");
    }

    monthRowClass(row) {
        if (row.state === "done") {
            return "o_dwv_row_done";
        }
        if (row.is_overdue) {
            return "o_dwv_row_overdue";
        }
        return "";
    }

    empMonthHint(empId) {
        const panel = this.panelOf(empId);
        if (panel.open && !panel.loading) {
            const total = panel.kpi?.total ?? panel.tasks.length;
            const hours = panel.kpi?.duration_hours ?? 0;
            return `${total} việc · ${hours} giờ (tháng ${this.monthLabel})`;
        }
        if (panel.countLoaded && panel.monthTotal !== null) {
            return `${panel.monthTotal} việc · ${panel.monthHours || 0} giờ`;
        }
        return "";
    }

    _buildYears(centerYear) {
        const years = [];
        for (let y = centerYear - 2; y <= centerYear + 1; y++) {
            years.push(y);
        }
        return years;
    }

    async loadBootstrap() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_viewer_bootstrap", []);
            this.state.employees = data.employees || [];
            this.state.states = data.states || [];
            this.state.message = data.message || false;
            this.state.openDepts = {};
            this.state.panels = {};
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được quyền xem.");
        } finally {
            this.state.loading = false;
        }
    }

    async prefetchDeptMonthCounts(employees) {
        const ids = (employees || []).map((e) => e.id).filter(Boolean);
        if (!ids.length) {
            return;
        }
        try {
            const data = await this.orm.call("daily.task", "get_viewer_month_counts", [], {
                employee_ids: ids,
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
            });
            const counts = data.counts || {};
            for (const emp of employees) {
                const c = counts[String(emp.id)] || counts[emp.id] || {
                    total: 0,
                    duration_hours: 0,
                };
                const current = this.panelOf(emp.id);
                if (current.open) {
                    continue;
                }
                this.state.panels[emp.id] = {
                    ...current,
                    monthTotal: c.total || 0,
                    monthHours: c.duration_hours || 0,
                    countLoaded: true,
                };
            }
        } catch (_e) {
            // silent — expand emp vẫn tải được chi tiết
        }
    }

    async toggleEmployee(emp) {
        const current = this.panelOf(emp.id);
        if (current.open) {
            this.state.panels[emp.id] = { ...current, open: false };
            return;
        }
        this.state.panels[emp.id] = {
            ...current,
            open: true,
            loading: true,
            error: false,
        };
        await this.loadTasksFor(emp.id);
    }

    async loadTasksFor(empId) {
        const current = this.panelOf(empId);
        this.state.panels[empId] = { ...current, loading: true, error: false };
        try {
            const data = await this.orm.call("daily.task", "get_viewer_tasks", [], {
                employee_id: empId,
                filters: {
                    year: Number(this.state.monthYear),
                    month: Number(this.state.monthMonth),
                },
            });
            const kpi = { ...EMPTY_KPI, ...(data.kpi || {}) };
            this.state.panels[empId] = {
                open: true,
                loading: false,
                tasks: data.tasks || data.rows || [],
                kpi,
                monthTotal: kpi.total,
                monthHours: kpi.duration_hours,
                countLoaded: true,
                canEdit: !!data.can_edit,
                canDelete: !!data.can_delete,
                error: false,
            };
        } catch (e) {
            this.state.panels[empId] = {
                open: true,
                loading: false,
                tasks: [],
                kpi: { ...EMPTY_KPI },
                monthTotal: 0,
                monthHours: 0,
                countLoaded: true,
                canEdit: false,
                canDelete: false,
                error: e?.data?.message || _t("Không tải được công việc."),
            };
        }
    }

    async onApplyFilter() {
        const openDeptIds = Object.keys(this.state.openDepts).filter(
            (id) => this.state.openDepts[id]
        );
        for (const dept of this.employeesByDepartment) {
            if (openDeptIds.includes(dept.id) || this.state.filterQuery) {
                await this.prefetchDeptMonthCounts(dept.employees);
            }
        }
        const openIds = Object.keys(this.state.panels)
            .map((id) => Number(id))
            .filter((id) => this.panelOf(id).open);
        for (const id of openIds) {
            await this.loadTasksFor(id);
        }
    }

    async onStateChange(empId, task, ev) {
        const panel = this.panelOf(empId);
        if (!panel.canEdit) {
            this.notification.add(_t("Bạn chỉ được xem, không được sửa."), { type: "warning" });
            await this.loadTasksFor(empId);
            return;
        }
        const stateVal = ev.target.value;
        try {
            await this.orm.call("daily.task", "update_from_manager", [[task.id], { state: stateVal }]);
            await this.loadTasksFor(empId);
            this.notification.add(_t("Đã cập nhật trạng thái."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể cập nhật."), { type: "danger" });
            await this.loadTasksFor(empId);
        }
    }

    async onDelete(empId, task) {
        const panel = this.panelOf(empId);
        if (!panel.canDelete) {
            this.notification.add(_t("Bạn không có quyền xóa."), { type: "warning" });
            return;
        }
        if (!confirm(_t("Xóa công việc này?"))) {
            return;
        }
        try {
            await this.orm.call("daily.task", "delete_from_manager", [[task.id]]);
            await this.loadTasksFor(empId);
            this.notification.add(_t("Đã xóa."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể xóa."), { type: "danger" });
        }
    }

    priorityClass(priority) {
        return (
            {
                high: "o_dwv_badge_high",
                medium: "o_dwv_badge_medium",
                low: "o_dwv_badge_low",
            }[priority] || "o_dwv_badge_medium"
        );
    }

    stateSelectClass(state) {
        return (
            {
                done: "o_dwv_state_done",
                in_progress: "o_dwv_state_progress",
                not_started: "o_dwv_state_todo",
            }[state] || "o_dwv_state_todo"
        );
    }
}

registry.category("actions").add("daily_work_viewer", DailyWorkViewer);
