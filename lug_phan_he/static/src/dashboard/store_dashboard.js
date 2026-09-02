/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

const PURPLE = "#6f42c1";

function doughnutCenterPlugin(totalText, subText) {
    return {
        id: "doughnutCenter",
        afterDraw(chart) {
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data || !meta.data[0]) {
                return;
            }
            const { x, y } = meta.data[0];
            const { ctx } = chart;
            ctx.save();
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#111827";
            ctx.font = "700 22px Inter, sans-serif";
            ctx.fillText(String(totalText), x, y - 8);
            ctx.fillStyle = "#6b7280";
            ctx.font = "500 12px Inter, sans-serif";
            ctx.fillText(subText, x, y + 14);
            ctx.restore();
        },
    };
}

export class LinkqStoreDashboard extends Component {
    static template = "lug_phan_he.LinkqStoreDashboard";
    static components = { PhanHeAppSidebar };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.staffCanvas = useRef("staffCanvas");
        this.barCanvas = useRef("barCanvas");
        this.areaCanvas = useRef("areaCanvas");
        this.shiftCanvas = useRef("shiftCanvas");
        this.charts = {};
        this.state = useState({
            loading: true,
            month: 9,
            year: 2026,
            storeId: 0,
            data: {},
            page: 1,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            const today = new Date();
            this.state.month = today.getMonth() + 1;
            this.state.year = today.getFullYear();
            await this.loadData();
        });

        useEffect(
            () => {
                this.renderCharts();
                return () => this.destroyCharts();
            },
            () => [this.state.data, this.state.loading]
        );

        onWillUnmount(() => this.destroyCharts());
    }

    get data() {
        return this.state.data || {};
    }

    get kpis() {
        return this.data.kpis || {};
    }

    get monthLabel() {
        return this.data.month_label || `Tháng ${String(this.state.month).padStart(2, "0")}/${this.state.year}`;
    }

    get staffSlices() {
        return (this.data.staff_chart && this.data.staff_chart.slices) || [];
    }

    get shiftSlices() {
        return this.data.shift_chart || [];
    }

    get alerts() {
        return this.data.alerts || [];
    }

    get employees() {
        return this.data.employees || [];
    }

    get pageSize() {
        return this.data.page_size || 5;
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.employees.length / this.pageSize));
    }

    get pages() {
        return Array.from({ length: this.pageCount }, (_, i) => i + 1);
    }

    get pagedEmployees() {
        const start = (this.state.page - 1) * this.pageSize;
        return this.employees.slice(start, start + this.pageSize).map((row, idx) => ({
            ...row,
            stt: start + idx + 1,
        }));
    }

    get pageFrom() {
        if (!this.employees.length) {
            return 0;
        }
        return (this.state.page - 1) * this.pageSize + 1;
    }

    get pageTo() {
        return Math.min(this.state.page * this.pageSize, this.employees.length);
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("linkq.monthly.roster", "get_store_dashboard_data", [], {
                month: this.state.month,
                year: this.state.year,
                store_id: this.state.storeId || false,
            });
            this.state.data = data || {};
            this.state.storeId = data.store_id || 0;
            this.state.month = data.month || this.state.month;
            this.state.year = data.year || this.state.year;
            this.state.page = 1;
        } catch (error) {
            console.error(error);
            this.notification.add(error?.data?.message || "Không tải được dashboard cửa hàng.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    prevMonth() {
        let { month, year } = this.state;
        month -= 1;
        if (month < 1) {
            month = 12;
            year -= 1;
        }
        this.state.month = month;
        this.state.year = year;
        this.loadData();
    }

    nextMonth() {
        let { month, year } = this.state;
        month += 1;
        if (month > 12) {
            month = 1;
            year += 1;
        }
        this.state.month = month;
        this.state.year = year;
        this.loadData();
    }

    onMonthInput(ev) {
        const value = ev.target.value || "";
        const [y, m] = value.split("-").map((n) => parseInt(n, 10));
        if (y && m) {
            this.state.year = y;
            this.state.month = m;
            this.loadData();
        }
    }

    get monthInputValue() {
        return `${this.state.year}-${String(this.state.month).padStart(2, "0")}`;
    }

    onStoreChange(ev) {
        if (!this.data.can_switch_store) {
            return;
        }
        this.state.storeId = parseInt(ev.target.value, 10) || 0;
        this.loadData();
    }

    setPage(page) {
        const next = Math.min(Math.max(1, page), this.pageCount);
        this.state.page = next;
    }

    async refresh() {
        await this.loadData();
    }

    onSeeAll() {
        const rosterId = this.data.roster_id;
        const storeId = this.state.storeId;
        if (rosterId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "linkq.monthly.roster",
                res_id: rosterId,
                views: [[false, "form"]],
                target: "current",
                context: { default_store_id: storeId },
            });
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Lịch xếp ca",
            res_model: "linkq.monthly.roster",
            views: [[false, "list"], [false, "form"]],
            domain: storeId ? [["store_id", "=", storeId]] : [["id", "=", false]],
            context: { default_store_id: storeId },
            target: "current",
        });
    }

    onAlert(alert) {
        this.onWarningClick(alert);
    }

    onWarningClick(warning) {
        if (!warning) {
            return;
        }
        if (warning.res_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: warning.text || warning.message,
                res_model: warning.res_model || "linkq.monthly.roster",
                res_id: warning.res_id,
                views: [[false, "form"]],
                target: "current",
            });
            return;
        }
        if (!warning.action_domain) {
            this.onSeeAll();
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: warning.text || warning.message || "Lịch xếp ca",
            res_model: warning.res_model || "linkq.monthly.roster",
            views: [[false, "list"], [false, "form"]],
            domain: warning.action_domain,
            context: { default_store_id: this.state.storeId },
            target: "current",
        });
    }

    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            try {
                this.charts[key].destroy();
            } catch {
                // ignore
            }
            delete this.charts[key];
        }
    }

    renderCharts() {
        if (typeof Chart === "undefined" || this.state.loading) {
            return;
        }
        this.destroyCharts();
        this.renderStaffDonut();
        this.renderTopBar();
        this.renderArea();
        this.renderShiftDonut();
    }

    renderStaffDonut() {
        const el = this.staffCanvas.el;
        if (!el) {
            return;
        }
        const slices = this.staffSlices;
        this.charts.staff = new Chart(el, {
            type: "doughnut",
            data: {
                labels: slices.map((s) => s.label),
                datasets: [
                    {
                        data: slices.map((s) => s.count),
                        backgroundColor: slices.map((s) => s.color),
                        borderWidth: 0,
                        hoverOffset: 4,
                    },
                ],
            },
            options: {
                cutout: "72%",
                plugins: { legend: { display: false }, tooltip: { enabled: true } },
                maintainAspectRatio: false,
            },
            plugins: [doughnutCenterPlugin(this.data.staff_chart?.total || 0, "nhân viên")],
        });
    }

    renderTopBar() {
        const el = this.barCanvas.el;
        if (!el) {
            return;
        }
        const rows = this.data.top_employees || [];
        this.charts.bar = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.name),
                datasets: [
                    {
                        data: rows.map((r) => r.hours),
                        backgroundColor: PURPLE,
                        borderRadius: 6,
                        barThickness: 16,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x} giờ` } },
                },
                scales: {
                    x: {
                        min: 0,
                        max: 200,
                        title: { display: true, text: "Giờ", color: "#6b7280" },
                        grid: { color: "rgba(15,23,42,0.06)" },
                        ticks: { color: "#6b7280" },
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: "#374151", font: { size: 11 } },
                    },
                },
            },
        });
    }

    renderArea() {
        const el = this.areaCanvas.el;
        if (!el) {
            return;
        }
        const values = this.data.hours_by_day || [];
        const labels = values.map((_, i) => String(i + 1).padStart(2, "0"));
        const ctx = el.getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, 220);
        gradient.addColorStop(0, "rgba(111, 66, 193, 0.35)");
        gradient.addColorStop(1, "rgba(111, 66, 193, 0.02)");
        this.charts.area = new Chart(el, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        data: values,
                        borderColor: "#5b21b6",
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        borderWidth: 2.4,
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        min: 0,
                        max: 120,
                        title: { display: true, text: "Giờ", color: "#6b7280" },
                        grid: { color: "rgba(15,23,42,0.06)" },
                        ticks: { color: "#6b7280" },
                    },
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: "#6b7280",
                            maxRotation: 0,
                            callback(value, index) {
                                const n = index + 1;
                                return n === 1 || n % 5 === 0 ? String(n).padStart(2, "0") : "";
                            },
                        },
                    },
                },
            },
        });
    }

    renderShiftDonut() {
        const el = this.shiftCanvas.el;
        if (!el) {
            return;
        }
        const slices = this.shiftSlices;
        const total = slices.reduce((s, it) => s + (it.count || 0), 0);
        this.charts.shift = new Chart(el, {
            type: "doughnut",
            data: {
                labels: slices.map((s) => s.label),
                datasets: [
                    {
                        data: slices.map((s) => s.count),
                        backgroundColor: slices.map((s) => s.color),
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                cutout: "70%",
                plugins: { legend: { display: false } },
                maintainAspectRatio: false,
            },
            plugins: [doughnutCenterPlugin(total, "ca")],
        });
    }
}

registry.category("actions").add("linkq_store_dashboard", LinkqStoreDashboard);
