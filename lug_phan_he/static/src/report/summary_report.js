/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

const C = 2 * Math.PI * 54;

function commaNum(n) {
    return `${n}`.replace(".", ",");
}

function fmtInt(n) {
    return `${Math.round(Number(n) || 0)}`.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function fmtVnd(n) {
    return fmtInt(n) + " ₫";
}

function decorateRegion(r) {
    r = r || {};
    return {
        ...r,
        pctLabel: commaNum(r.pct) + "%",
        pctLegend: "(" + commaNum(r.pct) + "%)",
        fillLabel: commaNum(r.fill) + "%",
        deltaLabel: "▲ " + r.delta + " (+" + commaNum(r.delta_pct) + "%)",
        fillStyle: "height:" + r.fill + "%;background:" + r.color,
        dotStyle: "background:" + r.color,
    };
}

function donutArcs(items, valueKey) {
    const total = items.reduce((s, it) => s + Number(it[valueKey] || 0), 0) || 1;
    let offset = 0;
    return items.map((it) => {
        const val = Number(it[valueKey] || 0);
        const len = (val / total) * C;
        const arc = {
            key: it.key,
            color: it.color,
            dash: `${len} ${C}`,
            offset: `${offset}`,
        };
        offset -= len;
        return arc;
    });
}

function linePoints(series, w, h, pad) {
    const all = (series || []).flat().filter((n) => typeof n === "number");
    if (!all.length) {
        return (series || []).map(() => "");
    }
    const min = Math.min(...all) * 0.96;
    const max = Math.max(...all) * 1.04;
    const span = max - min || 1;
    return series.map((row) =>
        row
            .map((v, i) => {
                const x = pad + (i * (w - pad * 2)) / Math.max(row.length - 1, 1);
                const y = h - pad - ((v - min) / span) * (h - pad * 2);
                return `${x},${y}`;
            })
            .join(" ")
    );
}

export class KPICardGroup extends Component {
    static template = "lug_phan_he.KPICardGroup";
    static props = { kpis: { type: Array, optional: true } };

    get cards() {
        return this.props.kpis || [];
    }
}

export class RegionalDistributionChart extends Component {
    static template = "lug_phan_he.RegionalDistributionChart";
    static props = { data: { type: Object, optional: true } };

    get arcs() {
        return donutArcs((this.props.data && this.props.data.regions) || [], "staff");
    }

    get staffLabel() {
        return fmtInt((this.props.data && this.props.data.staff_total) || 0);
    }

    get regions() {
        return ((this.props.data && this.props.data.regions) || []).map(decorateRegion);
    }
}

export class StaffTrendChart extends Component {
    static template = "lug_phan_he.StaffTrendChart";
    static props = { data: { type: Object, optional: true } };

    get chart() {
        const t = (this.props.data && this.props.data.trend) || {
            labels: [],
            north: [],
            south: [],
            dtt: [],
        };
        const [north, south, dtt] = linePoints([t.north, t.south, t.dtt], 420, 210, 28);
        return {
            labels: (t.labels || []).map((label, i) => ({
                key: i,
                label,
                x: 28 + i * 91,
            })),
            north,
            south,
            dtt,
        };
    }
}

export class RegionalStatsTable extends Component {
    static template = "lug_phan_he.RegionalStatsTable";
    static props = { data: { type: Object, optional: true } };

    get regions() {
        return ((this.props.data && this.props.data.regions) || []).map(decorateRegion);
    }

    get staffDeltaLabel() {
        const d = this.props.data || {};
        return "▲ " + (d.staff_delta || 0) + " (+" + commaNum(d.staff_delta_pct || 0) + "%)";
    }
}

export class FillRateBarChart extends Component {
    static template = "lug_phan_he.FillRateBarChart";
    static props = { regions: { type: Array, optional: true } };

    get items() {
        return (this.props.regions || []).map(decorateRegion);
    }
}

export class MissingDonutChart extends Component {
    static template = "lug_phan_he.MissingDonutChart";
    static props = { regions: { type: Array, optional: true } };

    get arcs() {
        return donutArcs(this.props.regions || [], "missing");
    }

    get total() {
        return (this.props.regions || []).reduce((s, r) => s + Number(r.missing || 0), 0);
    }
}

export class ShiftStackBarChart extends Component {
    static template = "lug_phan_he.ShiftStackBarChart";
    static props = { regions: { type: Array, optional: true } };

    get rows() {
        const max = Math.max(
            ...(this.props.regions || []).map((r) => Number(r.hours_s || 0) + Number(r.hours_c || 0) + Number(r.hours_t || 0)),
            1
        );
        return (this.props.regions || []).map((r) => {
            const tot = r.hours_s + r.hours_c + r.hours_t;
            return {
                ...r,
                sStyle: "width:" + (r.hours_s / max) * 100 + "%",
                cStyle: "width:" + (r.hours_c / max) * 100 + "%",
                tStyle: "width:" + (r.hours_t / max) * 100 + "%",
                tot,
            };
        });
    }
}

export class AlertPanel extends Component {
    static template = "lug_phan_he.AlertPanel";
    static props = { alerts: { type: Array, optional: true }, onOpen: { type: Function } };

    get items() {
        return this.props.alerts || [];
    }
}

export class StoreSummaryTable extends Component {
    static template = "lug_phan_he.StoreSummaryTable";
    static props = {
        stores: { type: Array, optional: true },
        search: { type: String, optional: true },
        page: { type: Number, optional: true },
        onSearch: { type: Function },
        onPage: { type: Function },
        onExport: { type: Function },
    };

    get filtered() {
        const stores = this.props.stores || [];
        const q = (this.props.search || "").toLowerCase().trim();
        if (!q) {
            return stores;
        }
        return stores.filter(
            (s) =>
                s.name.toLowerCase().includes(q) ||
                (s.roster_id && String(s.roster_id).includes(q)) ||
                s.code.toLowerCase().includes(q) ||
                s.region.toLowerCase().includes(q)
        );
    }

    get pageSize() {
        return 10;
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.filtered.length / this.pageSize));
    }

    get pageRows() {
        const start = ((this.props.page || 1) - 1) * this.pageSize;
        return this.filtered.slice(start, start + this.pageSize).map((row) => ({
            ...row,
            fillClass:
                row.fill_rate < 90 ? "is-bad" : row.fill_rate < 95 ? "is-warn" : "is-ok",
            fillText: commaNum(row.fill_rate),
        }));
    }

    get fromN() {
        if (!this.filtered.length) {
            return 0;
        }
        return (this.props.page - 1) * this.pageSize + 1;
    }

    get toN() {
        return Math.min(this.props.page * this.pageSize, this.filtered.length);
    }

    get pages() {
        const n = this.pageCount;
        const cur = this.props.page;
        const out = [];
        for (let i = 1; i <= n; i++) {
            if (i === 1 || i === n || Math.abs(i - cur) <= 1) {
                out.push(i);
            } else if (out[out.length - 1] !== "…") {
                out.push("…");
            }
        }
        return out;
    }

    get totals() {
        const rows = this.filtered;
        const sum = (k) => rows.reduce((s, r) => s + Number(r[k] || 0), 0);
        const fill = rows.length
            ? rows.reduce((s, r) => s + r.fill_rate, 0) / rows.length
            : 0;
        return {
            staff_total: sum("staff_total"),
            staff_working: sum("staff_working"),
            staff_left: sum("staff_left"),
            hours_s: sum("hours_s"),
            hours_c: sum("hours_c"),
            hours_t: sum("hours_t"),
            hours_off: sum("hours_off"),
            hours_total: sum("hours_total"),
            fill: fill.toFixed(1).replace(".", ","),
            missing: sum("missing_shifts"),
        };
    }
}

export class ShiftSummaryReportPage extends Component {
    static template = "lug_phan_he.ShiftSummaryReportPage";
    static components = {
        PhanHeAppSidebar,
        RegionalDistributionChart,
        StaffTrendChart,
        RegionalStatsTable,
        FillRateBarChart,
        MissingDonutChart,
        ShiftStackBarChart,
        AlertPanel,
        StoreSummaryTable,
    };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            compare: "prev_month",
            search: "",
            page: 1,
            showFilters: false,
            data: {
                kpis: [],
                regions: [],
                trend: { labels: [], north: [], south: [], dtt: [] },
                alerts: [],
                stores: [],
                staff_total: 0,
                staff_delta: 0,
                staff_delta_pct: 0,
                period: { label: "01/08/2026 - 31/08/2026" },
            },
        });
        onWillStart(() => this.load());
    }

    get sidebarActiveKey() {
        return "report";
    }

    get kpiCards() {
        return (this.state.data && this.state.data.kpis) || [];
    }

    async load() {
        const data = await this.orm.call("linkq.monthly.roster", "get_shift_summary_dashboard", [
            { compare: this.state.compare },
        ]);
        this.state.data = {
            kpis: data.kpis || [],
            regions: data.regions || [],
            trend: data.trend || { labels: [], north: [], south: [], dtt: [] },
            alerts: data.alerts || [],
            stores: data.stores || [],
            staff_total: data.staff_total || 0,
            staff_delta: data.staff_delta || 0,
            staff_delta_pct: data.staff_delta_pct || 0,
            period: data.period || { label: "01/08/2026 - 31/08/2026" },
        };
        this.state.page = 1;
    }

    onCompare(ev) {
        this.state.compare = ev.target.value;
        this.load();
    }

    onToggleFilters() {
        this.state.showFilters = !this.state.showFilters;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
    }

    onPage(n) {
        if (n === "…") {
            return;
        }
        this.state.page = n;
    }

    onAlert(alert) {
        this.notification.add(alert.text, { type: "warning" });
        if (alert.href === "fill") {
            this.state.search = "";
        }
    }

    onExport() {
        const rows = this.state.data.stores || [];
        const header = [
            "STT",
            "Mã",
            "Tên cửa hàng",
            "Khu vực",
            "Tổng NS",
            "Đang làm",
            "Nghỉ việc",
            "S",
            "C",
            "T",
            "Nghỉ",
            "Tổng giờ",
            "Tỷ lệ đủ ca",
            "Ca thiếu",
        ];
        const lines = [header.join(",")];
        for (const r of rows) {
            lines.push(
                [
                    r.stt,
                    r.code,
                    `"${r.name}"`,
                    r.region,
                    r.staff_total,
                    r.staff_working,
                    r.staff_left,
                    r.hours_s,
                    r.hours_c,
                    r.hours_t,
                    r.hours_off,
                    r.hours_total,
                    r.fill_rate,
                    r.missing_shifts,
                ].join(",")
            );
        }
        const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "Bang_tong_hop_theo_cua_hang.csv";
        a.click();
        URL.revokeObjectURL(a.href);
    }
}

registry.category("actions").add("linkq_shift_summary_report", ShiftSummaryReportPage);
