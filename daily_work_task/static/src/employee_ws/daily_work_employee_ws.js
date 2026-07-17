/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

const SIDEBAR_STORAGE_KEY = "daily_work_task.employee_ws.sidebarWidth";
const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 520;
const SIDEBAR_DEFAULT = 300;

function currentYearMonth() {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export class DailyWorkEmployeeWs extends Component {
    static template = "daily_work_task.DailyWorkEmployeeWs";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.layoutRef = useRef("layout");
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
        const ym = currentYearMonth();
        this.state = useState({
            loading: true,
            saving: false,
            exporting: false,
            employee: false,
            tasks: [],
            states: [],
            priorities: [],
            message: false,
            dateFrom: "",
            dateTo: "",
            form: this.emptyForm(),
            editingTaskId: false,
            sidebarWidth: this._loadSidebarWidth(),
            resizing: false,
            monthYear: ym.year,
            monthMonth: ym.month,
            monthLoading: false,
            monthKpi: {
                total: 0,
                done: 0,
                in_progress: 0,
                not_started: 0,
                overdue: 0,
                duration_minutes: 0,
                duration_hours: 0,
            },
            monthRows: [],
            monthMessage: false,
            workGroups: [],
            totalDurationMinutes: 0,
            totalDurationHours: 0,
            completionPercentAvg: 0,
            showMyList: true,
            recurringItems: [],
            recurringForm: this.emptyRecurringForm(),
            editingRecurringId: false,
            recurringSaving: false,
            recurrenceTypes: [
                { value: "daily", label: "Hằng ngày" },
                { value: "weekly", label: "Theo tuần" },
                { value: "monthly", label: "Theo tháng" },
                { value: "yearly", label: "Cố định ngày" },
            ],
            recurringFilters: {
                query: "",
                work_group_id: "",
                priority: "",
                active: "",
            },
            recurringPage: 1,
            recurringPageSize: 10,
            recurringSectionOpen: true,
            recurringListOpen: true,
            recurringFormOpen: true,
            workGroupFilterMenuOpen: false,
            workGroupFormMenuOpen: false,
            monthSectionOpen: true,
            monthTableOpen: true,
            monthCollapsedGroups: {},
            weekdays: [
                { value: 0, label: "Thứ 2" },
                { value: 1, label: "Thứ 3" },
                { value: 2, label: "Thứ 4" },
                { value: 3, label: "Thứ 5" },
                { value: 4, label: "Thứ 6" },
                { value: 5, label: "Thứ 7" },
                { value: 6, label: "Chủ nhật" },
            ],
            years: this._buildYears(ym.year),
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
        });
        onWillStart(async () => {
            await this.load();
            await this.loadRecurring();
            await this.loadMonthlySummary();
        });
        onMounted(() => {
            window.addEventListener("pointermove", this._onPointerMove);
            window.addEventListener("pointerup", this._onPointerUp);
        });
        onWillUnmount(() => {
            window.removeEventListener("pointermove", this._onPointerMove);
            window.removeEventListener("pointerup", this._onPointerUp);
            document.body.classList.remove("o_ews_resizing");
        });
    }

    get layoutStyle() {
        return "";
    }

    toggleMyList() {
        this.state.showMyList = !this.state.showMyList;
    }

    get monthTitle() {
        return `Tổng công việc tháng ${String(this.state.monthMonth).padStart(2, "0")}/${this.state.monthYear}`;
    }

    toggleMonthSection() {
        this.state.monthSectionOpen = !this.state.monthSectionOpen;
    }

    toggleMonthTable() {
        this.state.monthTableOpen = !this.state.monthTableOpen;
    }

    isMonthGroupOpen(groupKey) {
        return !this.state.monthCollapsedGroups[groupKey];
    }

    toggleMonthGroup(groupKey) {
        const key = String(groupKey);
        this.state.monthCollapsedGroups = {
            ...this.state.monthCollapsedGroups,
            [key]: !this.state.monthCollapsedGroups[key],
        };
    }

    get satacoLogoUrl() {
        // Cache-bust nhẹ để tránh browser giữ ảnh cũ / thiếu file
        return "/daily_work_task/static/description/sataco_logo.png?v=4";
    }

    /** Nhóm bảng tháng theo Nhóm công việc (Camera, Máy vi tính, …). */
    get monthGroups() {
        const groups = [];
        const indexByKey = new Map();
        for (const row of this.state.monthRows || []) {
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
                    completion_percent_avg: 0,
                });
            }
            const g = groups[indexByKey.get(key)];
            g.rows.push({ ...row, stt: g.rows.length + 1 });
            g.count += 1;
            g.duration_minutes += Number(row.duration_minutes) || 0;
        }
        for (const g of groups) {
            g.duration_hours_display = this.formatHours(g.duration_minutes);
            const sumPct = g.rows.reduce((s, row) => {
                let pct = Number(row.completion_percent) || 0;
                if (row.state === "done") {
                    pct = Math.max(pct, 100);
                }
                return s + pct;
            }, 0);
            g.completion_percent_avg = g.count
                ? Math.round((sumPct / g.count) * 10) / 10
                : 0;
        }
        // Nhóm có tên trước, «Không có nhóm» cuối
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

    /** Tổng % HT tháng = AVERAGE(% TB của các nhóm). */
    get monthAvgCompletionFromGroups() {
        const groups = this.monthGroups;
        if (!groups.length) {
            return 0;
        }
        const sum = groups.reduce((s, g) => s + (Number(g.completion_percent_avg) || 0), 0);
        return Math.round((sum / groups.length) * 10) / 10;
    }

    formatGroupAvgCompletion(group) {
        const v = Number(group?.completion_percent_avg) || 0;
        return Number.isInteger(v) ? String(v) : v.toFixed(1);
    }

    formatMonthAvgCompletion() {
        const fromKpi = Number(this.state.monthKpi?.completion_percent_avg);
        const v = Number.isFinite(fromKpi) ? fromKpi : this.monthAvgCompletionFromGroups;
        return Number.isInteger(v) ? String(v) : Number(v).toFixed(1);
    }

    _buildYears(centerYear) {
        const years = [];
        for (let y = centerYear - 2; y <= centerYear + 1; y++) {
            years.push(y);
        }
        return years;
    }

    _loadSidebarWidth() {
        const saved = Number(localStorage.getItem(SIDEBAR_STORAGE_KEY));
        if (Number.isFinite(saved) && saved >= SIDEBAR_MIN && saved <= SIDEBAR_MAX) {
            return saved;
        }
        return SIDEBAR_DEFAULT;
    }

    _saveSidebarWidth(width) {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(width));
    }

    onSplitterPointerDown(ev) {
        ev.preventDefault();
        this.state.resizing = true;
        document.body.classList.add("o_ews_resizing");
        if (ev.currentTarget?.setPointerCapture) {
            ev.currentTarget.setPointerCapture(ev.pointerId);
        }
    }

    _onPointerMove(ev) {
        if (!this.state.resizing || !this.layoutRef.el) {
            return;
        }
        const rect = this.layoutRef.el.getBoundingClientRect();
        let width = ev.clientX - rect.left;
        width = Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width));
        this.state.sidebarWidth = Math.round(width);
    }

    _onPointerUp() {
        if (!this.state.resizing) {
            return;
        }
        this.state.resizing = false;
        document.body.classList.remove("o_ews_resizing");
        this._saveSidebarWidth(this.state.sidebarWidth);
    }

    onSplitterDblClick() {
        this.state.sidebarWidth = SIDEBAR_DEFAULT;
        this._saveSidebarWidth(SIDEBAR_DEFAULT);
    }

    emptyForm() {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, "0");
        const dd = String(today.getDate()).padStart(2, "0");
        return {
            name: "",
            deadline: "",
            assign_date: `${yyyy}-${mm}-${dd}`,
            priority: "medium",
            state: "not_started",
            note: "",
            work_group_id: "",
            duration_minutes: "",
            completion_percent: 0,
        };
    }

    emptyRecurringForm() {
        return {
            name: "",
            work_group_id: "",
            duration_minutes: "",
            priority: "medium",
            recurrence_type: "daily",
            recurrence_weekdays: [0, 1, 2, 3, 4],
            recurrence_day: 1,
            recurrence_month: 1,
            active: true,
            note: "",
            skip_saturday: false,
            skip_sunday: false,
            deadline_offset_days: 0,
        };
    }

    get filteredRecurringItems() {
        const filters = this.state.recurringFilters;
        const query = (filters.query || "").trim().toLocaleLowerCase("vi");
        return (this.state.recurringItems || []).filter((item) => {
            const matchesQuery =
                !query ||
                (item.name || "").toLocaleLowerCase("vi").includes(query) ||
                (item.note || "").toLocaleLowerCase("vi").includes(query);
            const matchesGroup =
                !filters.work_group_id ||
                Number(item.work_group_id) === Number(filters.work_group_id);
            const matchesPriority = !filters.priority || item.priority === filters.priority;
            const matchesActive =
                filters.active === "" || String(Boolean(item.active)) === filters.active;
            return matchesQuery && matchesGroup && matchesPriority && matchesActive;
        });
    }

    get recurringPageCount() {
        return Math.max(
            1,
            Math.ceil(this.filteredRecurringItems.length / this.state.recurringPageSize)
        );
    }

    get pagedRecurringItems() {
        const page = Math.min(this.state.recurringPage, this.recurringPageCount);
        const start = (page - 1) * this.state.recurringPageSize;
        return this.filteredRecurringItems.slice(start, start + this.state.recurringPageSize);
    }

    get recurringPageNumbers() {
        return Array.from({ length: this.recurringPageCount }, (_, index) => index + 1);
    }

    onRecurringFilter() {
        this.state.recurringPage = 1;
    }

    onResetRecurringFilters() {
        this.state.recurringFilters = {
            query: "",
            work_group_id: "",
            priority: "",
            active: "",
        };
        this.state.recurringPage = 1;
        this.state.workGroupFilterMenuOpen = false;
    }

    toggleRecurringSection() {
        this.state.recurringSectionOpen = !this.state.recurringSectionOpen;
    }

    toggleRecurringList() {
        this.state.recurringListOpen = !this.state.recurringListOpen;
    }

    toggleRecurringFormPanel() {
        this.state.recurringFormOpen = !this.state.recurringFormOpen;
    }

    get selectedWorkGroupFilterLabel() {
        const id = this.state.recurringFilters.work_group_id;
        if (!id) {
            return "— Tất cả hạng mục —";
        }
        const group = (this.state.workGroups || []).find((g) => String(g.id) === String(id));
        return group?.name || "— Tất cả hạng mục —";
    }

    get selectedWorkGroupFormLabel() {
        const id = this.state.recurringForm.work_group_id;
        if (!id) {
            return "-- Chọn hạng mục --";
        }
        const group = (this.state.workGroups || []).find((g) => String(g.id) === String(id));
        return group?.name || "-- Chọn hạng mục --";
    }

    toggleWorkGroupFilterMenu(ev) {
        ev?.stopPropagation?.();
        this.state.workGroupFilterMenuOpen = !this.state.workGroupFilterMenuOpen;
        this.state.workGroupFormMenuOpen = false;
    }

    toggleWorkGroupFormMenu(ev) {
        ev?.stopPropagation?.();
        this.state.workGroupFormMenuOpen = !this.state.workGroupFormMenuOpen;
        this.state.workGroupFilterMenuOpen = false;
    }

    selectWorkGroupFilter(id) {
        this.state.recurringFilters.work_group_id = id ? String(id) : "";
        this.state.workGroupFilterMenuOpen = false;
        this.onRecurringFilter();
    }

    selectWorkGroupForm(id) {
        this.state.recurringForm.work_group_id = id ? String(id) : "";
        this.state.workGroupFormMenuOpen = false;
    }

    isSelectedWorkGroupFilter(id) {
        return String(this.state.recurringFilters.work_group_id || "") === String(id || "");
    }

    isSelectedWorkGroupForm(id) {
        return String(this.state.recurringForm.work_group_id || "") === String(id || "");
    }

    onRecurringPage(page) {
        this.state.recurringPage = Math.max(1, Math.min(Number(page), this.recurringPageCount));
    }

    onToggleRecurringWeekday(day) {
        const current = new Set(this.state.recurringForm.recurrence_weekdays || []);
        if (current.has(day)) {
            current.delete(day);
        } else {
            current.add(day);
        }
        this.state.recurringForm.recurrence_weekdays = [...current].sort((a, b) => a - b);
    }

    isRecurringWeekdaySelected(day) {
        return (this.state.recurringForm.recurrence_weekdays || []).includes(day);
    }

    onEditRecurring(item) {
        this.state.recurringSectionOpen = true;
        this.state.recurringFormOpen = true;
        this.state.recurringListOpen = true;
        this.state.editingRecurringId = item.id;
        this.state.recurringForm = {
            name: item.name || "",
            work_group_id: item.work_group_id ? String(item.work_group_id) : "",
            duration_minutes:
                item.duration_minutes === 0 || item.duration_minutes
                    ? String(item.duration_minutes)
                    : "",
            priority: item.priority || "medium",
            recurrence_type: item.recurrence_type || "daily",
            recurrence_weekdays: [...(item.recurrence_weekdays || [])],
            recurrence_day: Number(item.recurrence_day) || 1,
            recurrence_month: Number(item.recurrence_month) || 1,
            active: !!item.active,
            note: item.note || "",
            skip_saturday: !!item.skip_saturday,
            skip_sunday: !!item.skip_sunday,
            deadline_offset_days: Number(item.deadline_offset_days) || 0,
        };
        const panel = this.layoutRef.el?.closest(".o_ews_scroll")?.querySelector(".o_ews_recurring");
        if (panel) {
            panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }

    onCancelRecurringEdit() {
        this.state.editingRecurringId = false;
        this.state.recurringForm = this.emptyRecurringForm();
    }

    async loadRecurring() {
        try {
            const data = await this.orm.call("daily.task.recurring", "get_my_recurring", []);
            this.state.recurringItems = data.items || [];
            if (data.work_groups?.length && !this.state.workGroups.length) {
                this.state.workGroups = data.work_groups;
            }
            if (data.priorities?.length && !this.state.priorities.length) {
                this.state.priorities = data.priorities;
            }
            if (data.recurrence_types?.length) {
                this.state.recurrenceTypes = data.recurrence_types;
            }
        } catch (e) {
            this.state.recurringItems = [];
        }
    }

    async onSubmitRecurring(ev) {
        ev.preventDefault();
        const f = this.state.recurringForm;
        if (!f.name?.trim()) {
            this.notification.add(_t("Vui lòng nhập tên công việc lặp."), { type: "warning" });
            return;
        }
        let durationMinutes = 0;
        if (f.duration_minutes !== "" && f.duration_minutes !== null && f.duration_minutes !== undefined) {
            durationMinutes = parseInt(f.duration_minutes, 10);
            if (!Number.isFinite(durationMinutes) || durationMinutes < 0) {
                this.notification.add(_t("Thời gian thực hiện phải là số phút nguyên (≥ 0)."), {
                    type: "warning",
                });
                return;
            }
        }
        const offset = parseInt(f.deadline_offset_days, 10);
        if (!Number.isFinite(offset) || offset < 0) {
            this.notification.add(_t("Số ngày cộng hạn phải ≥ 0."), { type: "warning" });
            return;
        }
        this.state.recurringSaving = true;
        try {
            const payload = {
                name: f.name.trim(),
                work_group_id: f.work_group_id ? Number(f.work_group_id) : false,
                duration_minutes: durationMinutes,
                priority: f.priority || "medium",
                recurrence_type: f.recurrence_type || "daily",
                recurrence_weekdays: [...(f.recurrence_weekdays || [])],
                recurrence_day: Number(f.recurrence_day) || 1,
                recurrence_month: Number(f.recurrence_month) || 1,
                note: f.note || "",
                skip_saturday: !!f.skip_saturday,
                skip_sunday: !!f.skip_sunday,
                deadline_offset_days: offset,
                active: !!f.active,
            };
            if (this.state.editingRecurringId) {
                await this.orm.call("daily.task.recurring", "update_from_employee", [
                    [this.state.editingRecurringId],
                    payload,
                ]);
                this.notification.add(_t("Đã cập nhật mẫu công việc lặp."), { type: "success" });
            } else {
                await this.orm.call("daily.task.recurring", "create_from_employee", [payload]);
                this.notification.add(
                    _t("Đã lưu mẫu lặp. Việc hôm nay đã được tạo (nếu chưa có). Mỗi sáng ~5:00 sẽ tự tạo tiếp."),
                    { type: "success" }
                );
            }
            this.state.editingRecurringId = false;
            this.state.recurringForm = this.emptyRecurringForm();
            await this.loadRecurring();
            await this.load();
            await this.loadMonthlySummary();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể lưu mẫu lặp."), {
                type: "danger",
            });
        } finally {
            this.state.recurringSaving = false;
        }
    }

    async onToggleRecurring(item) {
        try {
            await this.orm.call("daily.task.recurring", "toggle_active_from_employee", [
                [item.id],
            ]);
            await this.loadRecurring();
            await this.load();
            this.notification.add(
                item.active ? _t("Đã tạm dừng lặp.") : _t("Đã bật lặp lại."),
                { type: "success" }
            );
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể bật/tắt mẫu."), {
                type: "danger",
            });
        }
    }

    async onGenerateRecurringToday(item) {
        try {
            const result = await this.orm.call(
                "daily.task.recurring",
                "generate_today_from_employee",
                [[item.id]]
            );
            await this.loadRecurring();
            await this.load();
            await this.loadMonthlySummary();
            if (result?.created) {
                this.notification.add(_t("Đã tạo công việc hôm nay từ mẫu."), {
                    type: "success",
                });
            } else {
                this.notification.add(_t("Hôm nay đã có việc từ mẫu này rồi."), {
                    type: "info",
                });
            }
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể tạo việc hôm nay."), {
                type: "danger",
            });
        }
    }

    async onDeleteRecurring(item) {
        if (!window.confirm(_t("Xóa mẫu công việc lặp này? Việc đã tạo trước đó vẫn giữ."))) {
            return;
        }
        try {
            await this.orm.call("daily.task.recurring", "unlink_from_employee", [[item.id]]);
            if (this.state.editingRecurringId === item.id) {
                this.onCancelRecurringEdit();
            }
            await this.loadRecurring();
            this.notification.add(_t("Đã xóa mẫu lặp."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể xóa mẫu."), {
                type: "danger",
            });
        }
    }

    onEditTask(task) {
        this.state.showMyList = true;
        this.state.editingTaskId = task.id;
        this.state.form = {
            name: task.name || "",
            deadline: task.deadline || "",
            assign_date: task.assign_date || "",
            priority: task.priority || "medium",
            state: task.state || "not_started",
            note: task.note || "",
            work_group_id: task.work_group_id ? String(task.work_group_id) : "",
            duration_minutes:
                task.duration_minutes === 0 || task.duration_minutes
                    ? String(task.duration_minutes)
                    : "",
            completion_percent: Number(task.completion_percent) || 0,
        };
        // Cuộn form chỉnh sửa vào tầm nhìn
        const panel = this.layoutRef.el?.querySelector(".o_ews_form_panel");
        if (panel) {
            panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        this.notification.add(_t("Đang chỉnh sửa — sửa bên trái rồi bấm Lưu thay đổi."), {
            type: "info",
        });
    }

    onCancelEdit() {
        this.state.editingTaskId = false;
        this.state.form = this.emptyForm();
    }

    formHoursPreview() {
        const minutes = Number(this.state.form.duration_minutes) || 0;
        if (minutes <= 0) {
            return "0 giờ";
        }
        const hours = minutes / 60;
        const text = hours.toFixed(2).replace(/\.?0+$/, "");
        return `${text} giờ`;
    }

    formatHours(minutes) {
        const m = Number(minutes) || 0;
        if (m <= 0) {
            return "0";
        }
        return (m / 60).toFixed(2).replace(/\.?0+$/, "");
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_employee_workspace", [], {
                filters: {
                    date_from: this.state.dateFrom || false,
                    date_to: this.state.dateTo || false,
                },
            });
            this.state.employee = data.employee || false;
            this.state.tasks = (data.tasks || []).map((t, i) => ({
                ...t,
                stt: i + 1,
            }));
            this.state.states = data.states || [];
            this.state.priorities = data.priorities || [];
            this.state.workGroups = data.work_groups || [];
            this.state.totalDurationMinutes = data.total_duration_minutes || 0;
            this.state.totalDurationHours = data.total_duration_hours || 0;
            this.state.completionPercentAvg = data.completion_percent_avg || 0;
            this.state.message = data.message || false;
        } finally {
            this.state.loading = false;
        }
    }

    async loadMonthlySummary() {
        this.state.monthLoading = true;
        try {
            const data = await this.orm.call("daily.task", "get_employee_monthly_summary", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
            });
            this.state.monthKpi = data.kpi || {
                total: 0,
                done: 0,
                in_progress: 0,
                not_started: 0,
                overdue: 0,
                duration_minutes: 0,
                duration_hours: 0,
            };
            this.state.monthRows = data.rows || [];
            this.state.monthMessage = data.message || false;
            if (data.year) {
                this.state.monthYear = data.year;
            }
            if (data.month) {
                this.state.monthMonth = data.month;
            }
        } catch (e) {
            this.state.monthRows = [];
            this.state.monthMessage = e?.data?.message || _t("Không tải được tổng hợp tháng.");
        } finally {
            this.state.monthLoading = false;
        }
    }

    async onFilter() {
        await this.load();
    }

    async onMonthFilter() {
        await this.loadMonthlySummary();
    }

    async onExportExcel() {
        this.state.exporting = true;
        try {
            const result = await this.orm.call("daily.task", "export_employee_monthly_excel", [], {
                year: Number(this.state.monthYear),
                month: Number(this.state.monthMonth),
            });
            if (!result?.file_base64) {
                throw new Error("Empty export");
            }
            this._downloadBase64Excel(result.file_base64, result.filename || "tong_cong_viec.xlsx");
            this.notification.add(_t("Đã xuất file Excel."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể xuất Excel."), {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    async onSubmit(ev) {
        ev.preventDefault();
        const f = this.state.form;
        if (!f.name?.trim()) {
            this.notification.add(_t("Vui lòng nhập tên công việc."), { type: "warning" });
            return;
        }
        if (!f.deadline) {
            this.notification.add(_t("Vui lòng chọn hạn hoàn thành."), { type: "warning" });
            return;
        }
        let durationMinutes = 0;
        if (f.duration_minutes !== "" && f.duration_minutes !== null && f.duration_minutes !== undefined) {
            durationMinutes = parseInt(f.duration_minutes, 10);
            if (!Number.isFinite(durationMinutes) || durationMinutes < 0) {
                this.notification.add(_t("Thời gian thực hiện phải là số phút nguyên (≥ 0)."), {
                    type: "warning",
                });
                return;
            }
        }
        this.state.saving = true;
        try {
            const payload = {
                name: f.name.trim(),
                deadline: f.deadline,
                assign_date: f.assign_date || false,
                priority: f.priority,
                state: f.state,
                note: f.note,
                work_group_id: f.work_group_id ? Number(f.work_group_id) : false,
                duration_minutes: durationMinutes,
            };
            if (this.state.editingTaskId) {
                const pctRaw = f.completion_percent;
                const pct =
                    pctRaw === "" || pctRaw === null || pctRaw === undefined
                        ? 0
                        : parseInt(pctRaw, 10);
                if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
                    this.notification.add(_t("% hoàn thành phải từ 0 đến 100."), {
                        type: "warning",
                    });
                    this.state.saving = false;
                    return;
                }
                payload.completion_percent = pct;
                await this.orm.call("daily.task", "update_from_manager", [
                    [this.state.editingTaskId],
                    payload,
                ]);
                this.state.editingTaskId = false;
                this.state.form = this.emptyForm();
                await this.load();
                await this.loadMonthlySummary();
                this.notification.add(_t("Đã cập nhật công việc."), { type: "success" });
            } else {
                await this.orm.call("daily.task", "create_from_employee", [payload]);
                this.state.form = this.emptyForm();
                await this.load();
                await this.loadMonthlySummary();
                this.notification.add(_t("Đã thêm công việc của bạn."), { type: "success" });
            }
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể lưu công việc."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    async onDurationChange(task, ev) {
        const raw = ev.target.value;
        const minutes = raw === "" ? 0 : parseInt(raw, 10);
        if (!Number.isFinite(minutes) || minutes < 0) {
            this.notification.add(_t("Thời gian phải là số phút nguyên (≥ 0)."), { type: "warning" });
            await this.load();
            return;
        }
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { duration_minutes: minutes },
            ]);
            const idx = this.state.tasks.findIndex((t) => t.id === task.id);
            if (idx >= 0) {
                this.state.tasks[idx] = {
                    ...updated,
                    stt: this.state.tasks[idx].stt || idx + 1,
                };
            }
            this.state.totalDurationMinutes = this.state.tasks.reduce(
                (sum, t) => sum + (Number(t.duration_minutes) || 0),
                0
            );
            this.state.totalDurationHours = Number(
                (this.state.totalDurationMinutes / 60).toFixed(2)
            );
            this._refreshCompletionAvg();
            await this.loadMonthlySummary();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể cập nhật thời gian."), {
                type: "danger",
            });
            await this.load();
        }
    }

    _refreshCompletionAvg() {
        const tasks = this.state.tasks || [];
        if (!tasks.length) {
            this.state.completionPercentAvg = 0;
            return;
        }
        const sum = tasks.reduce((s, t) => s + (Number(t.completion_percent) || 0), 0);
        this.state.completionPercentAvg = Math.round((sum / tasks.length) * 10) / 10;
    }

    formatAvgCompletion() {
        const v = Number(this.state.completionPercentAvg) || 0;
        return Number.isInteger(v) ? String(v) : v.toFixed(1);
    }

    async onCompletionChange(task, ev) {
        const raw = ev.target.value;
        const pct = raw === "" ? 0 : parseInt(raw, 10);
        if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
            this.notification.add(_t("% hoàn thành phải từ 0 đến 100."), { type: "warning" });
            await this.load();
            return;
        }
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { completion_percent: pct },
            ]);
            if (updated.state === "done") {
                this.state.tasks = this.state.tasks.filter((t) => t.id !== task.id);
                this._refreshCompletionAvg();
                await this.loadMonthlySummary();
                this.notification.add(_t("Đạt 100% — đã đánh dấu hoàn thành."), {
                    type: "success",
                });
                return;
            }
            const idx = this.state.tasks.findIndex((t) => t.id === task.id);
            if (idx >= 0) {
                this.state.tasks[idx] = {
                    ...updated,
                    stt: this.state.tasks[idx].stt || idx + 1,
                };
            }
            this._refreshCompletionAvg();
            await this.loadMonthlySummary();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể cập nhật % hoàn thành."), {
                type: "danger",
            });
            await this.load();
        }
    }

    async onWorkGroupChange(task, ev) {
        const wgId = ev.target.value ? Number(ev.target.value) : false;
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { work_group_id: wgId },
            ]);
            const idx = this.state.tasks.findIndex((t) => t.id === task.id);
            if (idx >= 0) {
                this.state.tasks[idx] = {
                    ...updated,
                    stt: this.state.tasks[idx].stt || idx + 1,
                };
            }
            // Đồng bộ cột Nhóm công việc ở bảng tổng tháng
            const mIdx = this.state.monthRows.findIndex((r) => r.id === task.id);
            if (mIdx >= 0) {
                this.state.monthRows[mIdx] = {
                    ...this.state.monthRows[mIdx],
                    work_group_id: updated.work_group_id,
                    work_group_label: updated.work_group_label || "",
                };
            }
            await this.loadMonthlySummary();
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thể cập nhật nhóm công việc."), {
                type: "danger",
            });
            await this.load();
            await this.loadMonthlySummary();
        }
    }

    async onStateChange(task, ev) {
        const stateVal = ev.target.value;
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { state: stateVal },
            ]);
            if (stateVal === "done") {
                // Chuyển xuống bảng tổng tháng
                this.state.tasks = this.state.tasks.filter((t) => t.id !== task.id);
                await this.loadMonthlySummary();
                this.notification.add(_t("Đã hoàn thành — chuyển xuống bảng tổng tháng."), {
                    type: "success",
                });
            } else {
                const idx = this.state.tasks.findIndex((t) => t.id === task.id);
                if (idx >= 0) {
                    this.state.tasks[idx] = {
                        ...updated,
                        stt: this.state.tasks[idx].stt || idx + 1,
                    };
                }
                await this.loadMonthlySummary();
                this.notification.add(_t("Đã cập nhật trạng thái."), { type: "success" });
            }
        } catch (e) {
            this.notification.add(_t("Không thể cập nhật trạng thái."), { type: "danger" });
            await this.load();
        }
    }

    stateSelectClass(state) {
        return (
            {
                done: "o_ews_state_done",
                in_progress: "o_ews_state_progress",
                not_started: "o_ews_state_todo",
            }[state] || "o_ews_state_todo"
        );
    }

    stateBadgeClass(state) {
        return (
            {
                done: "o_ews_state_badge_done",
                in_progress: "o_ews_state_badge_progress",
                not_started: "o_ews_state_badge_todo",
            }[state] || "o_ews_state_badge_todo"
        );
    }

    priorityClass(priority) {
        return (
            {
                high: "o_ews_badge_high",
                medium: "o_ews_badge_medium",
                low: "o_ews_badge_low",
            }[priority] || "o_ews_badge_medium"
        );
    }

    monthRowClass(row) {
        // Đã hoàn thành vẫn có thể hiện số ngày trễ — ưu tiên nền xanh
        if (row.state === "done") {
            return "o_ews_excel_row_done";
        }
        if (row.is_overdue) {
            return "o_ews_excel_row_overdue";
        }
        return "";
    }
}

registry.category("actions").add("daily_work_employee_ws", DailyWorkEmployeeWs);
