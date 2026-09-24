/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function formatMoneyVn(amount) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(amount || 0)))} đ`;
}

export class PhanHeCostEstimateBoard extends Component {
    static template = "lug_phan_he.PhanHeCostEstimateBoard";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            exporting: false,
            year: now.getFullYear(),
            region: "all",
            search: "",
            tableRegion: "all",
            viewMode: "months",
            selectedMonth: 0,
            data: {},
        });
        onWillStart(() => this.load());
    }

    get kpi() {
        return this.state.data.kpi || {};
    }

    get months() {
        return this.state.data.months || [];
    }

    get regions() {
        return this.state.data.regions || [];
    }

    get yearLabel() {
        return `Năm ${this.state.year}`;
    }

    get filteredStores() {
        const q = (this.state.search || "").trim().toLowerCase();
        const region = this.state.tableRegion;
        return (this.state.data.stores || []).filter((row) => {
            if (region && region !== "all" && row.region !== region) {
                return false;
            }
            if (!q) {
                return true;
            }
            return `${row.store} ${row.code} ${row.provider} ${row.region}`
                .toLowerCase()
                .includes(q);
        });
    }

    get storePageRows() {
        return this.filteredStores.map((row, idx) => ({
            ...row,
            stt: idx + 1,
        }));
    }

    get monthDetailRows() {
        const m = this.state.selectedMonth;
        if (!m) {
            return [];
        }
        const idx = m - 1;
        return this.filteredStores
            .filter((row) => Number((row.amounts || [])[idx] || 0) > 0)
            .map((row, i) => ({
                stt: i + 1,
                store: row.store,
                code: row.code,
                provider: row.provider,
                region: row.region,
                amount: Number((row.amounts || [])[idx] || 0),
            }));
    }

    formatMoney(v) {
        return formatMoneyVn(v);
    }

    monthCell(row, monthIndex) {
        const v = Number((row.amounts || [])[monthIndex] || 0);
        return v > 0 ? formatMoneyVn(v) : "—";
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("phan.he.dashboard", "get_cost_estimate_board", [{
                year: this.state.year,
                region: this.state.region,
            }]);
        } catch (err) {
            this.notification.add(
                err?.data?.message || err?.message || "Không tải được dự toán chi phí.",
                { type: "danger" }
            );
            this.state.data = {};
        } finally {
            this.state.loading = false;
        }
    }

    shiftYear(delta) {
        this.state.year = Number(this.state.year) + Number(delta);
        this.load();
    }

    onRegionChange(ev) {
        this.state.region = ev.target.value || "all";
        this.load();
    }

    onSearch(ev) {
        this.state.search = ev.target.value || "";
    }

    onTableRegion(ev) {
        this.state.tableRegion = ev.target.value || "all";
    }

    setViewMode(mode) {
        this.state.viewMode = mode;
        if (mode === "months") {
            this.state.selectedMonth = 0;
        }
    }

    selectMonth(month) {
        this.state.selectedMonth = month === this.state.selectedMonth ? 0 : month;
        if (this.state.selectedMonth) {
            this.state.viewMode = "months";
        }
    }

    monthRowClass(mo) {
        const now = new Date();
        const isCurrent =
            Number(this.state.year) === now.getFullYear()
            && Number(mo.month) === now.getMonth() + 1;
        const on = mo.month === this.state.selectedMonth ? " is-on" : "";
        const cur = isCurrent ? " is-current" : "";
        const empty = !(mo.amount > 0) ? " is-empty" : "";
        return `lq-ce-month-row${cur}${on}${empty}`;
    }

    async exportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const result = await this.orm.call("phan.he.dashboard", "export_cost_estimate_excel", [{
                year: this.state.year,
                region: this.state.region,
                search: this.state.search,
                table_region: this.state.tableRegion,
            }]);
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            const bin = atob(result.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const blob = new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = result.filename || `Du_toan_chi_phi_${this.state.year}.xlsx`;
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add("Đã xuất file Excel.", { type: "success" });
        } catch (err) {
            console.error(err);
            this.notification.add(
                err?.data?.message || err?.message || "Không xuất được Excel.",
                { type: "danger" }
            );
        } finally {
            this.state.exporting = false;
        }
    }
}
