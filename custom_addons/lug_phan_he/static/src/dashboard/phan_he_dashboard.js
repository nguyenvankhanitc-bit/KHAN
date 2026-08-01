/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

function formatNumber(n) {
    return new Intl.NumberFormat("vi-VN").format(Math.round(Number(n || 0)));
}

function pad2(n) {
    return String(n).padStart(2, "0");
}

function yearStartDisplay(year) {
    return `01/01/${year}`;
}

function yearEndDisplay(year) {
    return `31/12/${year}`;
}

function displayToIso(value) {
    const raw = String(value || "").trim();
    const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) {
        return false;
    }
    return `${m[3]}-${pad2(m[2])}-${pad2(m[1])}`;
}

function isoToDisplay(value) {
    const raw = String(value || "").trim();
    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) {
        return raw;
    }
    return `${m[3]}/${m[2]}/${m[1]}`;
}

export class PhanHeDashboard extends Component {
    static template = "lug_phan_he.PhanHeDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const year = new Date().getFullYear();
        this.state = useState({
            loading: true,
            exporting: false,
            alertsOpen: true,
            activeNav: "overview",
            data: {},
            paymentReport: { tables: [] },
            filters: {
                year: year,
                date_from: yearStartDisplay(year),
                date_to: yearEndDisplay(year),
                mien_id: "",
                area_id: "",
                employee_id: "",
            },
        });
        onWillStart(async () => {
            if (this.actionContext.phan_he_dash_view === "reports") {
                this.state.activeNav = "reports";
            }
            await this.load();
        });
    }

    get yearOptions() {
        const current = new Date().getFullYear();
        const years = [];
        for (let y = current - 3; y <= current + 1; y++) {
            years.push(y);
        }
        const selected = Number(this.state.filters.year || current);
        if (selected && !years.includes(selected)) {
            years.push(selected);
            years.sort((a, b) => a - b);
        }
        return years;
    }

    get actionContext() {
        return this.props.action?.context || {};
    }

    get serviceTypeCode() {
        return this.actionContext.phan_he_service_type_code || "internet";
    }

    get appTitle() {
        return this.actionContext.phan_he_app_title
            || this.state.data.app_title
            || "Quản lý dịch vụ";
    }

    get navItems() {
        const code = this.serviceTypeCode;
        const trackingByType = {
            internet: "lug_phan_he.action_phan_he_service_tracking",
            camera: "lug_phan_he.action_phan_he_service_tracking_camera",
            attendance: "lug_phan_he.action_phan_he_service_tracking_attendance",
            linkq_hrm: "lug_phan_he.action_phan_he_service_tracking_linkq_hrm",
            linkq_nb: "lug_phan_he.action_phan_he_service_tracking_linkq_nb",
            server: "lug_phan_he.action_phan_he_service_tracking_server",
        };
        const paymentByType = {
            internet: "lug_phan_he.action_phan_he_payment",
            camera: "lug_phan_he.action_phan_he_payment_camera",
            attendance: "lug_phan_he.action_phan_he_payment_attendance",
            linkq_hrm: "lug_phan_he.action_phan_he_payment_linkq_hrm",
            linkq_nb: "lug_phan_he.action_phan_he_payment_linkq_nb",
            server: "lug_phan_he.action_phan_he_payment_server",
        };
        const items = [
            { id: "overview", label: "Tổng quan", icon: "fa-th-large", action: false },
            {
                id: "contracts",
                label: "Danh sách",
                icon: "fa-file-text-o",
                action: trackingByType[code] || trackingByType.internet,
            },
            {
                id: "payments",
                label: "Thanh toán",
                icon: "fa-credit-card",
                action: paymentByType[code] || paymentByType.internet,
            },
            { id: "alerts", label: "Cảnh báo", icon: "fa-bell", action: false },
        ];
        if (code === "internet") {
            items.splice(1, 0, {
                id: "calendar",
                label: "Calendar",
                icon: "fa-calendar",
                action: "lug_phan_he.action_phan_he_calendar",
            });
            items.push(
                { id: "providers", label: "Nhà cung cấp", icon: "fa-users", action: "lug_phan_he.action_phan_he_provider" },
                { id: "invoices", label: "Hóa đơn", icon: "fa-list-alt", action: "lug_phan_he.action_phan_he_invoice" },
                { id: "reports", label: "Báo cáo", icon: "fa-bar-chart", action: false },
                { id: "config", label: "Cấu hình", icon: "fa-cog", action: "lug_phan_he.action_phan_he_mien" },
            );
        }
        return items;
    }

    get alertCount() {
        return Number(this.state.data.alert_count || 0);
    }

    onNav(item) {
        if (!item) {
            return;
        }
        if (item.id === "overview") {
            this.state.activeNav = "overview";
            return;
        }
        if (item.id === "reports") {
            this.state.activeNav = "reports";
            this.loadPaymentReport();
            return;
        }
        if (item.id === "alerts") {
            this.state.alertsOpen = !this.state.alertsOpen;
            return;
        }
        if (!item.action) {
            return;
        }
        this.openAction(item.action);
    }

    onAlertClick(alert) {
        if (alert && alert.action) {
            this.openAction(alert.action);
        }
    }

    async load() {
        const year = Number(this.state.filters.year || new Date().getFullYear());
        this.state.filters.year = year;
        this.state.filters.date_from = yearStartDisplay(year);
        this.state.filters.date_to = yearEndDisplay(year);
        const dateFrom = displayToIso(this.state.filters.date_from);
        const dateTo = displayToIso(this.state.filters.date_to);
        if (!dateFrom || !dateTo) {
            this.notification.add("Ngày phải theo định dạng dd/mm/yyyy (ví dụ 01/01/2026).", {
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const f = this.state.filters;
            this.state.data = await this.orm.call("phan.he.dashboard", "get_dashboard_data", [{
                date_from: dateFrom,
                date_to: dateTo,
                mien_id: f.mien_id || false,
                area_id: f.area_id || false,
                employee_id: f.employee_id || false,
                service_type_code: this.serviceTypeCode,
                app_title: this.actionContext.phan_he_app_title || false,
            }]);
            if (this.state.data.year) {
                this.state.filters.year = Number(this.state.data.year);
            }
            if (this.state.data.date_from) {
                this.state.filters.date_from = isoToDisplay(this.state.data.date_from);
            }
            if (this.state.data.date_to) {
                this.state.filters.date_to = isoToDisplay(this.state.data.date_to);
            }
            if (this.state.activeNav === "reports") {
                await this.loadPaymentReport({ silent: true });
            }
        } finally {
            this.state.loading = false;
        }
    }

    _filterPayload() {
        const f = this.state.filters;
        return {
            date_from: displayToIso(f.date_from),
            date_to: displayToIso(f.date_to),
            mien_id: f.mien_id || false,
            area_id: f.area_id || false,
            employee_id: f.employee_id || false,
            service_type_code: this.serviceTypeCode,
        };
    }

    async loadPaymentReport({ silent = false } = {}) {
        const payload = this._filterPayload();
        if (!payload.date_from || !payload.date_to) {
            this.notification.add("Ngày phải theo định dạng dd/mm/yyyy (ví dụ 01/01/2026).", {
                type: "warning",
            });
            return;
        }
        if (!silent) {
            this.state.loading = true;
        }
        try {
            this.state.paymentReport = await this.orm.call(
                "phan.he.dashboard",
                "get_payment_status_report",
                [payload]
            );
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được báo cáo thanh toán.",
                { type: "danger" }
            );
        } finally {
            if (!silent) {
                this.state.loading = false;
            }
        }
    }

    openPayment(row) {
        if (!row?.id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "phan.he.payment",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    formatIsoDate(value) {
        return isoToDisplay(value) || "—";
    }

    async onYearChange(ev) {
        const year = Number(ev.target.value || new Date().getFullYear());
        this.state.filters.year = year;
        await this.load();
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
        a.download = filename || "Bang_tong_hop_chi_phi.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async onExportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const year = Number(this.state.filters.year || new Date().getFullYear());
            const result = await this.orm.call(
                "phan.he.dashboard",
                "export_monthly_cost_excel",
                [{
                    date_from: `${year}-01-01`,
                    date_to: `${year}-12-31`,
                    mien_id: this.state.filters.mien_id || false,
                    area_id: this.state.filters.area_id || false,
                    employee_id: this.state.filters.employee_id || false,
                    service_type_code: this.serviceTypeCode,
                    app_title: this.actionContext.phan_he_app_title || false,
                }]
            );
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add("Đã xuất file Excel.", { type: "success" });
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không xuất được Excel.",
                { type: "danger" }
            );
        } finally {
            this.state.exporting = false;
        }
    }

    async onFilter() {
        // Đồng bộ năm từ date_from nếu user đổi khoảng ngày ở thanh lọc trên
        const iso = displayToIso(this.state.filters.date_from);
        if (iso) {
            this.state.filters.year = Number(iso.slice(0, 4));
        }
        await this.load();
    }

    async onRefresh() {
        const year = new Date().getFullYear();
        this.state.filters.year = year;
        this.state.filters.date_from = yearStartDisplay(year);
        this.state.filters.date_to = yearEndDisplay(year);
        this.state.filters.mien_id = "";
        this.state.filters.area_id = "";
        this.state.filters.employee_id = "";
        await this.load();
    }

    onMienChange() {
        this.state.filters.area_id = "";
    }

    formatMoney(amount) {
        const symbol = this.state.data.currency_symbol || "đ";
        return `${formatNumber(amount)} ${symbol}`;
    }

    formatMoneyVnd(amount) {
        return `${formatNumber(amount)} VNĐ`;
    }

    formatNumber(amount) {
        return formatNumber(amount);
    }

    formatPct(v) {
        return `${Number(v || 0).toFixed(1)}%`;
    }

    padCount(n) {
        return String(Number(n || 0)).padStart(2, "0");
    }

    regionTone(code, index) {
        const c = String(code || "").toUpperCase();
        if (c === "BAC") {
            return "is-bac";
        }
        if (c === "NAM") {
            return "is-nam";
        }
        if (c === "TRUNG" || c === "DTT") {
            return "is-trung";
        }
        return `is-tone-${index % 4}`;
    }

    pieStyle(rows) {
        // giữ để tương thích; donut dùng SVG
        const list = rows || [];
        const total = list.reduce((s, r) => s + Number(r.amount || 0), 0) || 1;
        let acc = 0;
        const parts = list.map((r) => {
            const start = (acc / total) * 360;
            acc += Number(r.amount || 0);
            const end = (acc / total) * 360;
            return `${r.color} ${start}deg ${end}deg`;
        });
        return parts.length
            ? `background: conic-gradient(${parts.join(", ")})`
            : "background: conic-gradient(#e5e7eb 0 360deg)";
    }

    /**
     * Donut SVG chuẩn — từng lát cung khép kín, không méo như conic-gradient.
     */
    donutSlices() {
        const rows = this.costStructureRows().filter((r) => Number(r.amount || 0) > 0);
        const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0) || 1;
        const cx = 90;
        const cy = 90;
        const rOut = 72;
        const rIn = 44;
        let angle = -Math.PI / 2;
        const slices = [];

        const polar = (radius, a) => ({
            x: cx + radius * Math.cos(a),
            y: cy + radius * Math.sin(a),
        });

        for (const row of rows) {
            const portion = Number(row.amount || 0) / total;
            if (portion <= 0) {
                continue;
            }
            // tránh cung 360° (SVG không vẽ được start===end)
            const sweep = Math.min(portion * 2 * Math.PI, 2 * Math.PI - 0.0001);
            const end = angle + sweep;
            const large = sweep > Math.PI ? 1 : 0;
            const p0 = polar(rOut, angle);
            const p1 = polar(rOut, end);
            const p2 = polar(rIn, end);
            const p3 = polar(rIn, angle);
            const d = [
                `M ${p0.x.toFixed(3)} ${p0.y.toFixed(3)}`,
                `A ${rOut} ${rOut} 0 ${large} 1 ${p1.x.toFixed(3)} ${p1.y.toFixed(3)}`,
                `L ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`,
                `A ${rIn} ${rIn} 0 ${large} 0 ${p3.x.toFixed(3)} ${p3.y.toFixed(3)}`,
                "Z",
            ].join(" ");
            slices.push({
                id: row.id,
                color: row.color,
                d,
                name: row.name,
                pct: row.pct,
            });
            angle = end;
        }
        return slices;
    }

    costStructureTotal() {
        return (this.state.data.cost_structure || []).reduce(
            (s, r) => s + Number(r.amount || 0),
            0
        );
    }

    costStructureRows() {
        return [...(this.state.data.cost_structure || [])].sort(
            (a, b) => Number(b.amount || 0) - Number(a.amount || 0)
        );
    }

    formatTrieu(amount) {
        const n = Number(amount || 0) / 1e6;
        if (n >= 10) {
            return `${n.toFixed(1)} Tr. VNĐ`;
        }
        return `${n.toFixed(1)} Tr. VNĐ`;
    }

    monthLabelPad() {
        const m = Number(this.state.data.current_month || 0);
        return m ? pad2(m) : "—";
    }

    /**
     * Stacked area chart: lớp chồng theo miền, trục Y = Triệu VNĐ.
     */
    stackedTrendChart() {
        // Nhỏ → lớn: lớp dưới cùng là miền nhỏ, trên cùng là miền lớn (giống stacked area)
        const series = [...(this.state.data.trend_series || [])].sort((a, b) => {
            const sa = (a.values || []).reduce((s, v) => s + Number(v || 0), 0);
            const sb = (b.values || []).reduce((s, v) => s + Number(v || 0), 0);
            return sa - sb;
        });
        const n = 12;
        const W = 560;
        const H = 230;
        const padL = 44;
        const padR = 14;
        const padT = 14;
        const padB = 30;
        const cw = W - padL - padR;
        const ch = H - padT - padB;

        const totals = Array.from({ length: n }, () => 0);
        for (const s of series) {
            (s.values || []).forEach((v, i) => {
                if (i < n) {
                    totals[i] += Number(v || 0);
                }
            });
        }
        const maxRaw = Math.max(...totals, 1);
        const maxTrieu = maxRaw / 1e6;
        const step = maxTrieu <= 100 ? 25 : maxTrieu <= 200 ? 50 : 100;
        const niceMax = Math.max(step, Math.ceil(maxTrieu / step) * step);
        const yMax = niceMax * 1e6;

        const grid = [];
        const ticks = Math.round(niceMax / step);
        for (let t = 0; t <= ticks; t++) {
            const val = step * t;
            const y = padT + ch - (val / niceMax) * ch;
            grid.push({ y, label: String(val) });
        }

        const layers = [];
        const cum = Array.from({ length: n }, () => 0);
        for (const s of series) {
            const tops = [];
            const bots = [];
            for (let i = 0; i < n; i++) {
                const v = Number((s.values || [])[i] || 0);
                const bottom = cum[i];
                const top = bottom + v;
                const x = padL + (i / Math.max(n - 1, 1)) * cw;
                const yTop = padT + ch - (top / yMax) * ch;
                const yBot = padT + ch - (bottom / yMax) * ch;
                tops.push({ x, y: yTop });
                bots.push({ x, y: yBot });
                cum[i] = top;
            }
            let area = `M ${tops[0].x} ${tops[0].y}`;
            for (const p of tops) {
                area += ` L ${p.x} ${p.y}`;
            }
            for (let i = bots.length - 1; i >= 0; i--) {
                area += ` L ${bots[i].x} ${bots[i].y}`;
            }
            area += " Z";
            layers.push({
                id: s.id,
                name: s.name,
                short: s.short,
                color: s.color,
                area,
                linePoints: tops.map((p) => `${p.x},${p.y}`).join(" "),
                dots: tops,
            });
        }

        const xLabels = Array.from({ length: n }, (_, i) => ({
            x: padL + (i / Math.max(n - 1, 1)) * cw,
            text: `Th ${i + 1}`,
        }));

        return {
            W,
            H,
            padL,
            padT,
            padB,
            cw,
            ch,
            grid,
            layers,
            xLabels,
            baselineY: padT + ch,
        };
    }

    filteredAreas() {
        const mid = this.state.filters.mien_id;
        const areas = this.state.data.areas || [];
        if (!mid) {
            return areas;
        }
        return areas.filter((a) => String(a.mien_id) === String(mid));
    }

    openAction(xmlid) {
        this.action.doAction(xmlid);
    }
}

registry.category("actions").add("phan_he_dashboard", PhanHeDashboard);
