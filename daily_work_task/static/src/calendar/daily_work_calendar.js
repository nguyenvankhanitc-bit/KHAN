/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const MONTH_NAMES = [
    "",
    "Tháng 1",
    "Tháng 2",
    "Tháng 3",
    "Tháng 4",
    "Tháng 5",
    "Tháng 6",
    "Tháng 7",
    "Tháng 8",
    "Tháng 9",
    "Tháng 10",
    "Tháng 11",
    "Tháng 12",
];

export class DailyWorkCalendar extends Component {
    static template = "daily_work_task.DailyWorkCalendar";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            search: "",
            departmentId: 0,
            kpi: {},
            byDay: {},
            sidebar: { today: [], overdue: [], upcoming: [] },
            departments: [],
            firstWeekday: 0,
            daysInMonth: 31,
            today: "",
            monthLabel: "",
            canCreate: false,
            selectedTask: null,
            saving: false,
            hoverTask: null,
            hoverStyle: "",
            dayPanel: null,
            expandedDays: {},
        });
        this.weekdays = WEEKDAYS;
        this._hoverLeaveTimer = null;
        this._hoverShowTimer = null;
        this._panelGuardUntil = 0;
        onWillStart(() => this.load());
    }

    get weeks() {
        const cells = [];
        const pad = this.state.firstWeekday; // Mon=0
        const y = this.state.year;
        const m = this.state.month;
        // Ngày tháng trước (ô đệm đầu lưới) — để luôn đủ 7 cột / đủ tuần
        if (pad > 0) {
            const prev = m === 1 ? { y: y - 1, m: 12 } : { y, m: m - 1 };
            const prevLast = new Date(prev.y, prev.m, 0).getDate();
            for (let i = 0; i < pad; i++) {
                const day = prevLast - pad + 1 + i;
                cells.push({
                    empty: true,
                    otherMonth: true,
                    day,
                    key: `e-${i}`,
                });
            }
        }
        const today = this.state.today;
        for (let d = 1; d <= this.state.daysInMonth; d++) {
            const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
            const tasks = this.state.byDay[String(d)] || [];
            const expanded = Boolean(this.state.expandedDays[d] || this.state.expandedDays[String(d)]);
            const maxVisible = expanded ? tasks.length : 3;
            cells.push({
                empty: false,
                key: `d-${d}`,
                day: d,
                iso,
                isToday: iso === today,
                tasks,
                expanded,
                more: expanded ? 0 : Math.max(0, tasks.length - maxVisible),
                visible: tasks.slice(0, maxVisible),
            });
        }
        // Ngày tháng sau (ô đệm cuối) — luôn đủ số tuần (35 hoặc 42 ô)
        let trail = 0;
        while (cells.length % 7 !== 0) {
            trail += 1;
            cells.push({
                empty: true,
                otherMonth: true,
                day: trail,
                key: `t-${cells.length}`,
            });
        }
        // Đảm bảo tối thiểu 5 hàng (tháng ngắn vẫn đủ khung tháng)
        while (cells.length < 35) {
            trail += 1;
            cells.push({
                empty: true,
                otherMonth: true,
                day: trail,
                key: `t-${cells.length}`,
            });
        }
        const weeks = [];
        for (let i = 0; i < cells.length; i += 7) {
            weeks.push(cells.slice(i, i + 7));
        }
        return weeks;
    }

    get miniDays() {
        const days = [];
        const pad = this.state.firstWeekday;
        for (let i = 0; i < pad; i++) {
            days.push({ empty: true, key: `m-e-${i}` });
        }
        for (let d = 1; d <= this.state.daysInMonth; d++) {
            const has = Boolean((this.state.byDay[String(d)] || []).length);
            const iso = `${this.state.year}-${String(this.state.month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
            days.push({
                empty: false,
                key: `m-${d}`,
                day: d,
                has,
                isToday: iso === this.state.today,
            });
        }
        return days;
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_fluent_calendar_data", [], {
                year: this.state.year,
                month: this.state.month,
                department_id: this.state.departmentId || false,
                search: this.state.search || false,
            });
            this.state.kpi = data.kpi || {};
            this.state.byDay = data.by_day || {};
            this.state.sidebar = data.sidebar || { today: [], overdue: [], upcoming: [] };
            this.state.departments = data.departments || [];
            this.state.firstWeekday = data.first_weekday || 0;
            this.state.daysInMonth = data.days_in_month || 31;
            this.state.today = data.today || "";
            this.state.monthLabel =
                data.month_label || `${MONTH_NAMES[this.state.month]}, ${this.state.year}`;
            this.state.year = data.year;
            this.state.month = data.month;
            this.state.canCreate = Boolean(data.can_create);
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không tải được Calendar."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async shiftMonth(delta) {
        let y = this.state.year;
        let m = this.state.month + delta;
        if (m < 1) {
            m = 12;
            y -= 1;
        } else if (m > 12) {
            m = 1;
            y += 1;
        }
        this.state.year = y;
        this.state.month = m;
        await this.load();
    }

    async goToday() {
        const now = new Date();
        this.state.year = now.getFullYear();
        this.state.month = now.getMonth() + 1;
        await this.load();
    }

    onSearchKeyup(ev) {
        if (ev.key === "Enter") {
            this.load();
        }
    }

    setDepartment(id) {
        this.state.departmentId = Number(id) || 0;
        this.load();
    }

    openTask(task) {
        this.state.hoverTask = null;
        this.state.selectedTask = { ...task };
    }

    openTaskFromPanel(task) {
        this.state.dayPanel = null;
        this.openTask(task);
    }

    closeModal() {
        this.state.selectedTask = null;
    }

    onMoreClick(ev) {
        // Chỉ xử lý click (không dùng pointerdown — tránh mở rồi bị backdrop đóng ngay)
        if (ev.type && ev.type !== "click") {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        if (this._hoverLeaveTimer) {
            clearTimeout(this._hoverLeaveTimer);
            this._hoverLeaveTimer = null;
        }
        if (this._hoverShowTimer) {
            clearTimeout(this._hoverShowTimer);
            this._hoverShowTimer = null;
        }
        this.state.hoverTask = null;
        this.state.hoverStyle = "";

        const btn = ev.currentTarget;
        let day = Number(btn.value || btn.getAttribute("value") || 0);
        if (!day) {
            const numEl = btn.closest(".o_dwc_day")?.querySelector(".o_dwc_day_num");
            day = Number(numEl?.textContent || 0);
        }
        if (!day) {
            this.notification.add(_t("Không xác định được ngày."), { type: "warning" });
            return;
        }
        const tasks = this.state.byDay[String(day)] || [];
        if (!tasks.length) {
            this.notification.add(_t("Không có công việc trong ngày này."), {
                type: "info",
            });
            return;
        }
        // 1) Hiện hết ngay trong ô ngày
        this.state.expandedDays = { ...this.state.expandedDays, [day]: true, [String(day)]: true };
        // 2) Đồng thời mở panel danh sách (có chặn đóng nhầm trong 400ms)
        this._panelGuardUntil = Date.now() + 400;
        this.state.dayPanel = { day, tasks: tasks.slice() };
    }

    onDayPanelBackdropClick() {
        if (Date.now() < this._panelGuardUntil) {
            return;
        }
        this.closeDayPanel();
    }

    expandDay(day, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.state.hoverTask = null;
        const tasks = this.state.byDay[String(day)] || [];
        this.state.expandedDays = { ...this.state.expandedDays, [day]: true, [String(day)]: true };
        this._panelGuardUntil = Date.now() + 400;
        this.state.dayPanel = { day, tasks: tasks.slice() };
    }

    collapseDay(day, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        const next = { ...this.state.expandedDays };
        delete next[day];
        delete next[String(day)];
        this.state.expandedDays = next;
    }

    onCollapseClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const day = Number(ev.currentTarget.value || 0);
        if (day) {
            this.collapseDay(day, ev);
        }
    }

    closeDayPanel() {
        this.state.dayPanel = null;
    }

    onTaskHover(task, ev) {
        if (this.state.selectedTask || this.state.dayPanel) {
            return;
        }
        // Không hover khi đang trên nút +N
        if (ev?.relatedTarget?.closest?.(".o_dwc_more") || ev?.target?.closest?.(".o_dwc_more")) {
            return;
        }
        if (this._hoverLeaveTimer) {
            clearTimeout(this._hoverLeaveTimer);
            this._hoverLeaveTimer = null;
        }
        if (this._hoverShowTimer) {
            clearTimeout(this._hoverShowTimer);
        }
        const target = ev.currentTarget;
        const taskCopy = { ...task };
        this._hoverShowTimer = setTimeout(() => {
            if (this.state.dayPanel || this.state.selectedTask) {
                return;
            }
            const rect = target.getBoundingClientRect();
            const popW = 520;
            const popH = 440;
            let left = rect.right + 12;
            let top = rect.top;
            if (left + popW > window.innerWidth - 12) {
                left = Math.max(8, rect.left - popW - 12);
            }
            if (top + popH > window.innerHeight - 12) {
                top = Math.max(8, window.innerHeight - popH - 12);
            }
            if (top < 8) {
                top = 8;
            }
            this.state.hoverTask = taskCopy;
            this.state.hoverStyle = `left:${Math.round(left)}px;top:${Math.round(top)}px;`;
        }, 350);
    }

    onTaskHoverLeave() {
        if (this._hoverShowTimer) {
            clearTimeout(this._hoverShowTimer);
            this._hoverShowTimer = null;
        }
        this._hoverLeaveTimer = setTimeout(() => {
            this.state.hoverTask = null;
            this.state.hoverStyle = "";
        }, 200);
    }

    onPopoverEnter() {
        if (this._hoverLeaveTimer) {
            clearTimeout(this._hoverLeaveTimer);
            this._hoverLeaveTimer = null;
        }
    }

    onPopoverLeave() {
        this.onTaskHoverLeave();
    }

    closeHover() {
        this.state.hoverTask = null;
        this.state.hoverStyle = "";
    }

    deadlineLabel(task) {
        if (!task) {
            return "—";
        }
        const base = task.deadline_display || "";
        if (!task.deadline) {
            return base || "—";
        }
        const d = new Date(`${task.deadline}T00:00:00`);
        if (Number.isNaN(d.getTime())) {
            return base || "—";
        }
        const wd = ["Chủ nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"][
            d.getDay()
        ];
        return `${base} (${wd})`;
    }

    durationLabel(task) {
        if (!task) {
            return "—";
        }
        const h = task.duration_hours_display;
        if (h && h !== "0") {
            return `${h} giờ`;
        }
        const m = task.duration_minutes || 0;
        return m ? `${m} phút` : "—";
    }

    async markDone() {
        const task = this.state.selectedTask;
        if (!task) {
            return;
        }
        this.state.saving = true;
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { state: "done" },
            ]);
            this.notification.add(_t("Đã đánh dấu hoàn thành."), { type: "success" });
            await this.load();
            const refreshed = Object.values(this.state.byDay)
                .flat()
                .find((t) => t.id === task.id);
            this.state.selectedTask = { ...(refreshed || updated) };
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật được."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    async markInProgress() {
        const task = this.state.selectedTask;
        if (!task) {
            return;
        }
        this.state.saving = true;
        try {
            const updated = await this.orm.call("daily.task", "update_from_manager", [
                [task.id],
                { state: "in_progress" },
            ]);
            this.notification.add(_t("Đã chuyển sang đang xử lý."), { type: "success" });
            await this.load();
            const refreshed = Object.values(this.state.byDay)
                .flat()
                .find((t) => t.id === task.id);
            this.state.selectedTask = { ...(refreshed || updated) };
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không cập nhật được."), {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }

    openForm() {
        const task = this.state.selectedTask;
        if (!task) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "daily.task",
            res_id: task.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onCreate() {
        this.action.doAction("daily_work_task.action_daily_work_assign");
    }

    cardClass(task) {
        const token = task.color_token || task.state || "not_started";
        return `o_dwc_card o_dwc_card_${token}`;
    }

    taskIcon(task) {
        const token = task.color_token || task.state || "not_started";
        return (
            {
                done: "fa-check",
                in_progress: "fa-wrench",
                not_started: "fa-circle-o",
                overdue: "fa-exclamation",
            }[token] || "fa-tasks"
        );
    }

    shortDept(name) {
        const raw = (name || "").trim();
        if (!raw) {
            return "";
        }
        const cleaned = raw
            .replace(/^PHÒNG\s+/i, "")
            .replace(/^Phòng\s+/i, "")
            .trim();
        return cleaned.length > 18 ? `${cleaned.slice(0, 16)}…` : cleaned;
    }

    deptIcon(name) {
        const n = (name || "").toLowerCase();
        if (n.includes("it") || n.includes("kỹ thuật") || n.includes("ky thuat")) {
            return "fa-laptop";
        }
        if (n.includes("hành chính") || n.includes("nhân sự") || n.includes("hanh chinh")) {
            return "fa-building";
        }
        if (n.includes("kế toán") || n.includes("ke toan")) {
            return "fa-calculator";
        }
        if (n.includes("marketing") || n.includes("kinh doanh")) {
            return "fa-bullhorn";
        }
        if (n.includes("kho")) {
            return "fa-cubes";
        }
        if (n.includes("bảo trì") || n.includes("bao tri") || n.includes("thi công")) {
            return "fa-wrench";
        }
        return "fa-folder-o";
    }

    shortPriority(priority) {
        return { high: "Cao", medium: "TB", low: "Thấp" }[priority] || "TB";
    }

    priorityClass(priority) {
        return (
            {
                high: "o_dwc_prio_high",
                medium: "o_dwc_prio_med",
                low: "o_dwc_prio_low",
            }[priority] || "o_dwc_prio_med"
        );
    }

    stateClass(state) {
        return (
            {
                done: "o_dwc_state_done",
                in_progress: "o_dwc_state_progress",
                not_started: "o_dwc_state_todo",
            }[state] || "o_dwc_state_todo"
        );
    }
}

registry.category("actions").add("daily_work_calendar", DailyWorkCalendar);

// assets-bust 2026-07-13-toolbar-removed


// bust-more-click-20260713

