/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

function shiftIso(iso, days) {
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

function todayIso() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

export class DailyWorkTeamChecklist extends Component {
    static template = "daily_work_task.DailyWorkTeamChecklist";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            date: todayIso(),
            employeeId: 0,
            workGroupId: 0,
            stateFilter: "",
            search: "",
            onlyOpen: false,
            stats: {},
            employees: [],
            verified: [],
            categories: [],
            filterEmployees: [],
            workGroups: [],
            canAssign: false,
            dateDisplay: "",
            toggling: {},
            confirming: {},
            confirmingAll: false,
            selectedConfirm: {},
            saving: false,
            openVerified: {},
            openUnchecked: {},
            openCats: {},
            catsOpen: false,
            openEmpGroups: {},
        });
        // Biểu đồ cột chồng theo nhân sự: Hoàn thành / Đang làm / Chưa bắt đầu / Trễ hạn
        this.chartRef = useRef("statusChart");
        this.chart = null;
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => {
                if (!this.state.loading) {
                    this.renderChart();
                }
                return () => this.destroyChart();
            },
            () => [this.state.loading, this.state.employees, this.state.verified]
        );
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_team_checklist_data", [], {
                filters: {
                    date: this.state.date,
                    employee_id: this.state.employeeId,
                    work_group_id: this.state.workGroupId,
                    state: this.state.stateFilter,
                    search: this.state.search,
                    only_open: this.state.onlyOpen,
                },
            });
            this.state.stats = data.stats || {};
            this.state.employees = data.employees || [];
            this.state.verified = data.verified || [];
            this.state.categories = data.categories || [];
            this.state.filterEmployees = data.filters?.employees || [];
            this.state.workGroups = data.filters?.work_groups || [];
            this.state.canAssign = Boolean(data.can_assign);
            this.state.dateDisplay = data.date_display || "";
            if (data.date) {
                this.state.date = data.date;
            }
            this.state.selectedConfirm = {};
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được checklist team."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    onDateInput(ev) {
        this.state.date = ev.target.value;
        this.load();
    }

    onPrevDay() {
        this.state.date = shiftIso(this.state.date, -1);
        this.load();
    }

    onNextDay() {
        this.state.date = shiftIso(this.state.date, 1);
        this.load();
    }

    onToday() {
        this.state.date = todayIso();
        this.load();
    }

    onFilterChange() {
        this.load();
    }

    async onToggle(task) {
        if (!task.can_edit || this.state.toggling[task.id]) {
            return;
        }
        this.state.toggling[task.id] = true;
        try {
            await this.orm.call("daily.task", "toggle_team_checklist_done", [
                [task.id],
                !task.is_done,
            ]);
            await this.load();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật được việc."), {
                type: "danger",
            });
        } finally {
            this.state.toggling[task.id] = false;
        }
    }

    canConfirmAll(emp) {
        return (emp.tasks || []).some((t) => t.can_confirm && !t.manager_confirmed);
    }

    isDraft(task) {
        return Boolean(this.state.selectedConfirm[task.id]);
    }

    hasDraft(emp) {
        return (emp.tasks || []).some((t) => this.state.selectedConfirm[t.id]);
    }

    isAllDraft(emp) {
        const tasks = (emp.tasks || []).filter((t) => t.can_confirm && !t.manager_confirmed);
        return tasks.length > 0 && tasks.every((t) => this.state.selectedConfirm[t.id]);
    }

    toggleDraft(task) {
        if (!task.can_confirm) {
            return;
        }
        this.state.selectedConfirm[task.id] = !this.state.selectedConfirm[task.id];
    }

    toggleDraftAll(emp) {
        const tasks = (emp.tasks || []).filter((t) => t.can_confirm && !t.manager_confirmed);
        const allOn = tasks.length > 0 && tasks.every((t) => this.state.selectedConfirm[t.id]);
        for (const t of tasks) {
            this.state.selectedConfirm[t.id] = !allOn;
        }
    }

    async onSaveConfirm(emp) {
        const ids = (emp.tasks || [])
            .filter((t) => t.can_confirm && this.state.selectedConfirm[t.id])
            .map((t) => t.id);
        if (!ids.length || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("daily.task", "toggle_manager_confirm", [ids, true]);
            await this.load();
            if (emp.assignee_id) {
                this.state.openVerified[emp.assignee_id] = true;
            }
            this.notification.add(_t("Đã lưu xác nhận QL."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xác nhận được việc."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onConfirm(task) {
        if (!task.can_confirm || this.state.confirming[task.id]) {
            return;
        }
        this.state.confirming[task.id] = true;
        try {
            await this.orm.call("daily.task", "toggle_manager_confirm", [
                [task.id],
                !task.manager_confirmed,
            ]);
            await this.load();
            if (!task.manager_confirmed && task.assignee_id) {
                this.state.openVerified[task.assignee_id] = true;
            }
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xác nhận được việc."), {
                type: "danger",
            });
        } finally {
            this.state.confirming[task.id] = false;
        }
    }

    async openAssign() {
        if (!this.state.canAssign) {
            this.notification.add(_t("Bạn không có quyền giao việc."), { type: "warning" });
            return;
        }
        await this.action.doAction("daily_work_task.action_daily_work_assign");
    }

    exportCsv() {
        const rows = [["Nhân viên", "Tên công việc", "Hạn hoàn thành", "Mức ưu tiên", "Trạng thái"]];
        for (const emp of this.state.employees) {
            for (const task of emp.tasks || []) {
                let st = this.stateLabel(task);
                rows.push([emp.name, task.name, task.deadline, task.priority_label, st]);
            }
        }
        const csv = rows
            .map((r) => r.map((c) => `"${String(c || "").replace(/"/g, '""')}"`).join(","))
            .join("\n");
        const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `checklist_team_${this.state.date}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    /** Số việc theo trạng thái của từng nhân sự (gộp chưa kiểm tra + đã kiểm tra). */
    get chartData() {
        const index = {};
        const people = [];
        const add = (key, name, task) => {
            if (!index[key]) {
                index[key] = { name: name || "—", done: 0, doing: 0, todo: 0, late: 0 };
                people.push(index[key]);
            }
            const p = index[key];
            if (task.is_done || task.state === "done") {
                p.done += 1;
            } else if (task.is_overdue) {
                p.late += 1;
            } else if (task.state === "in_progress") {
                p.doing += 1;
            } else {
                p.todo += 1;
            }
        };
        for (const emp of this.state.employees || []) {
            for (const t of emp.tasks || []) {
                add(emp.assignee_id || emp.name, emp.name, t);
            }
        }
        for (const t of this.state.verified || []) {
            add(t.assignee_id || t.assignee_name, t.assignee_name, t);
        }
        people.sort((a, b) => a.name.localeCompare(b.name, "vi"));
        const sum = (k) => people.reduce((acc, p) => acc + p[k], 0);
        return {
            people,
            totals: { done: sum("done"), doing: sum("doing"), todo: sum("todo"), late: sum("late") },
        };
    }

    get chartLegend() {
        const t = this.chartData.totals;
        return [
            { key: "done", label: "Hoàn thành", color: "#22c55e", value: t.done },
            { key: "doing", label: "Đang làm", color: "#f59e0b", value: t.doing },
            { key: "todo", label: "Chưa bắt đầu", color: "#94a3b8", value: t.todo },
            { key: "late", label: "Trễ hạn", color: "#ef4444", value: t.late },
        ];
    }

    get chartTotal() {
        const t = this.chartData.totals;
        return t.done + t.doing + t.todo + t.late;
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    renderChart() {
        this.destroyChart();
        const el = this.chartRef.el;
        if (!el || !window.Chart) {
            return;
        }
        const people = this.chartData.people;
        if (!people.length) {
            return;
        }
        const legend = this.chartLegend;
        // Ghi tổng số việc trên đầu mỗi cột
        const totalLabels = {
            id: "dwtTotals",
            afterDatasetsDraw(chart) {
                const ctx = chart.ctx;
                ctx.save();
                ctx.font = "700 12px sans-serif";
                ctx.fillStyle = "#0f172a";
                ctx.textAlign = "center";
                ctx.textBaseline = "bottom";
                people.forEach((p, i) => {
                    const total = p.done + p.doing + p.todo + p.late;
                    let top = Infinity;
                    let x = null;
                    for (let d = 0; d < chart.data.datasets.length; d++) {
                        const bar = chart.getDatasetMeta(d).data[i];
                        if (bar) {
                            x = bar.x;
                            if (chart.data.datasets[d].data[i]) {
                                top = Math.min(top, bar.y);
                            }
                        }
                    }
                    if (total && top !== Infinity && x !== null) {
                        ctx.fillText(String(total), x, top - 4);
                    }
                });
                ctx.restore();
            },
        };
        this.chart = new window.Chart(el, {
            type: "bar",
            data: {
                labels: people.map((p) => p.name),
                datasets: legend.map((l) => ({
                    label: l.label,
                    data: people.map((p) => p[l.key]),
                    backgroundColor: l.color,
                    borderWidth: 0,
                    maxBarThickness: 56,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { top: 18 } },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            footer: (items) => {
                                const p = people[items[0].dataIndex];
                                return "Tổng: " + (p.done + p.doing + p.todo + p.late) + " việc";
                            },
                        },
                    },
                },
                scales: {
                    x: { stacked: true, grid: { display: false } },
                    y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
                },
            },
            plugins: [totalLabels],
        });
    }

    get verifiedGroups() {
        const groups = [];
        const index = {};
        for (const task of this.state.verified || []) {
            const key = task.assignee_id || task.assignee_name || 0;
            if (!index[key]) {
                const name = task.assignee_name || "—";
                index[key] = {
                    key,
                    name,
                    initial: (name.trim()[0] || "?").toUpperCase(),
                    tasks: [],
                };
                groups.push(index[key]);
            }
            index[key].tasks.push(task);
        }
        groups.sort((a, b) => a.name.localeCompare(b.name, "vi"));
        return groups;
    }

    empGroups(emp) {
        const groups = [];
        const index = {};
        for (const task of emp.tasks || []) {
            const catName = String(task.category || "").replace(/^\d+\.\s*/, "").replace(/\s+/g, " ").trim();
            const key = catName ? catName.toLocaleLowerCase("vi") : "0";
            if (!index[key]) {
                index[key] = {
                    key,
                    name: catName || "Khác",
                    icon: task.category_icon || "fa-folder-open-o",
                    tasks: [],
                    minutes: 0,
                    done: 0,
                };
                groups.push(index[key]);
            }
            const g = index[key];
            g.tasks.push(task);
            g.minutes += Number(task.duration_minutes) || 0;
            if (task.is_done || task.state === "done") {
                g.done += 1;
            }
        }
        for (const g of groups) {
            g.count = g.tasks.length;
            const h = g.minutes / 60;
            g.hours = Number.isInteger(h) ? String(h) : String(Math.round(h * 10) / 10);
            g.percent = g.count ? Math.round((g.done / g.count) * 100) : 0;
        }
        groups.sort((a, b) => String(a.name).localeCompare(String(b.name), "vi"));
        return groups;
    }

    groupKey(emp, group) {
        return `${emp.assignee_id}:${group.key}`;
    }

    toggleEmpGroup(emp, group) {
        const key = this.groupKey(emp, group);
        this.state.openEmpGroups[key] = !this.state.openEmpGroups[key];
    }

    isEmpGroupOpen(emp, group) {
        return Boolean(this.state.openEmpGroups[this.groupKey(emp, group)]);
    }

    romanIndex(i) {
        const nums = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
        return nums[i] || String(i + 1);
    }

    toggleUnchecked(key) {
        this.state.openUnchecked[key] = !this.isUncheckedOpen(key);
    }

    /** Danh sách chưa kiểm tra: mặc định mở khi chỉ có 1 nhân viên. */
    isUncheckedOpen(key) {
        if (key in this.state.openUnchecked) {
            return Boolean(this.state.openUnchecked[key]);
        }
        return (this.state.employees || []).length === 1;
    }

    toggleVerified(key) {
        this.state.openVerified[key] = !this.state.openVerified[key];
    }

    isVerifiedOpen(key) {
        return Boolean(this.state.openVerified[key]);
    }

    toggleCats() {
        this.state.catsOpen = !this.state.catsOpen;
    }

    toggleCat(id) {
        this.state.openCats[id] = !this.state.openCats[id];
    }

    isCatOpen(id) {
        return Boolean(this.state.openCats[id]);
    }

    catPct(cat) {
        if (cat.percent != null) {
            return cat.percent;
        }
        if (!cat.total) {
            return 0;
        }
        return Math.round((cat.done / cat.total) * 100);
    }

    cardStateLabel(task) {
        if (task.state === "not_started") {
            return "Chưa hoàn thành";
        }
        return this.stateLabel(task);
    }

    stateLabel(task) {
        if (task.state_label) {
            return task.state_label;
        }
        if (task.state === "done") {
            return "Đã hoàn thành";
        }
        if (task.state === "in_progress") {
            return "Đang xử lý";
        }
        return "Chưa bắt đầu";
    }

    stateClass(task) {
        if (task.state === "done") {
            return "o_tcl_badge o_tcl_badge_done";
        }
        if (task.state === "in_progress") {
            return "o_tcl_badge o_tcl_badge_doing";
        }
        return "o_tcl_badge o_tcl_badge_todo";
    }

    priorityClass(priority) {
        if (priority === "high") {
            return "o_tcl_pri o_tcl_pri_high";
        }
        if (priority === "low") {
            return "o_tcl_pri o_tcl_pri_low";
        }
        return "o_tcl_pri o_tcl_pri_medium";
    }
}

registry.category("actions").add("daily_work_team_checklist", DailyWorkTeamChecklist);
