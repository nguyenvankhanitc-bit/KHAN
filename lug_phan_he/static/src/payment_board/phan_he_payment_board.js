/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function pad2(n) {
    return String(n).padStart(2, "0");
}

function ymd(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function formatMoneyVn(amount) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(amount || 0)))} đ`;
}

function formatDateVn(raw) {
    const s = String(raw || "").slice(0, 10);
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) {
        return raw || "—";
    }
    return `${m[3]}/${m[2]}/${m[1]}`;
}

function currentMonthParts() {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function lastDayOfMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

function projectDueInMonth(anchorYmd, year, month) {
    const last = lastDayOfMonth(year, month);
    let day = 1;
    const m = String(anchorYmd || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) {
        day = Math.min(Number(m[3]), last);
    }
    return `${year}-${pad2(month)}-${pad2(day)}`;
}

function inYearMonth(ymdStr, year, month) {
    const m = String(ymdStr || "").match(/^(\d{4})-(\d{2})-/);
    return Boolean(m && Number(m[1]) === year && Number(m[2]) === month);
}

function statusFromDue(dueYmd) {
    if (!dueYmd) {
        return "not_due";
    }
    const today = ymd(new Date());
    if (dueYmd < today) {
        return "overdue";
    }
    const soon = new Date();
    soon.setDate(soon.getDate() + 7);
    if (dueYmd <= ymd(soon)) {
        return "due_soon";
    }
    return "not_due";
}

const STATE_LABEL = {
    draft: "Nháp",
    not_due: "Chưa đến hạn",
    due_soon: "Sắp đến hạn",
    pending: "Chờ thanh toán",
    overdue: "Quá hạn",
    paid: "Đã thanh toán",
    cancel: "Đã hủy",
};

const OPS_STATUS_META = {
    active: { label: "Đang sử dụng", className: "is-active" },
    suspend: { label: "Tạm ngưng", className: "is-suspend" },
    liquidated: { label: "Thanh lý", className: "is-liquidated" },
};

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => ({
    value: i + 1,
    label: `Tháng ${i + 1}`,
}));

export class PhanHePaymentBoard extends Component {
    static template = "lug_phan_he.PhanHePaymentBoard";
    static props = {
        mode: { type: String, optional: true },
        reloadToken: { type: Number, optional: true },
        monthOffset: { type: Number, optional: true },
        onMonthOffsetChange: { type: Function, optional: true },
        onConfirmCountChange: { type: Function, optional: true },
        onAfterConfirm: { type: Function, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ui = useService("ui");
        const cur = currentMonthParts();
        this.state = useState({
            loading: true,
            exporting: false,
            records: [],
            totalCount: 0,
            selected: {},
            confirming: false,
            search: "",
            page: 1,
            pageSize: 15,
            year: cur.year,
            month: cur.month,
            statusTab: "all",
            sectionOpen: true,
        });
        this.monthOptions = MONTH_OPTIONS;
        this.yearOptions = this.buildYearOptions(cur.year);
        this._loadSeq = 0;
        this._stickyRaf = null;
        this.tableScrollRef = useRef("tableScroll");
        onMounted(() => this.syncStickyColumns());
        onPatched(() => this.syncStickyColumns());
        onWillStart(() => this.load());
        onWillUpdateProps((nextProps) => {
            const modeChanged = nextProps.mode !== this.props.mode;
            const tokenChanged = (nextProps.reloadToken || 0) !== (this.props.reloadToken || 0);
            if (modeChanged || tokenChanged) {
                this.state.page = 1;
                this.state.selected = {};
                this.state.statusTab = "all";
                this.state.records = [];
                this.state.loading = true;
                if (modeChanged && nextProps.mode === "forecast") {
                    const n = currentMonthParts();
                    this.state.year = n.year;
                    this.state.month = n.month;
                    this.yearOptions = this.buildYearOptions(n.year);
                }
                this.load(nextProps);
            }
        });
        onWillUnmount(() => {
            if (this._stickyRaf) {
                cancelAnimationFrame(this._stickyRaf);
                this._stickyRaf = null;
            }
            if (this._stickyRo) {
                this._stickyRo.disconnect();
                this._stickyRo = null;
            }
        });
    }

    /** OWL template không có global String — dùng helper này. */
    toStr(v) {
        return v == null ? "" : String(v);
    }

    isMonthSelected(v) {
        return Number(this.state.month) === Number(v);
    }

    isYearSelected(v) {
        return Number(this.state.year) === Number(v);
    }

    get periodSelectKey() {
        return `${this.state.year}-${this.state.month}`;
    }

    /** Căn sticky đúng mép cột Cửa hàng. */
    syncStickyColumns() {
        if (this._stickyRaf) {
            cancelAnimationFrame(this._stickyRaf);
        }
        this._stickyRaf = requestAnimationFrame(() => {
            this._stickyRaf = null;
            const root = this.tableScrollRef?.el;
            if (!root) {
                return;
            }
            const table = root.querySelector("table.lq-inet-table");
            if (!table) {
                return;
            }
            const check = table.querySelector("thead th.col-check");
            const stt = table.querySelector("thead th.col-stt");
            const store = table.querySelector("thead th.col-store");
            if (!stt || !store) {
                return;
            }
            const wCheck = check ? Math.ceil(check.getBoundingClientRect().width) : 0;
            const wStt = Math.ceil(stt.getBoundingClientRect().width);
            const leftStt = `${wCheck}px`;
            const leftStore = `${wCheck + wStt}px`;
            if (table.style.getPropertyValue("--lq-left-stt") !== leftStt
                || table.style.getPropertyValue("--lq-left-store") !== leftStore) {
                table.style.setProperty("--lq-left-check", "0px");
                table.style.setProperty("--lq-left-stt", leftStt);
                table.style.setProperty("--lq-left-store", leftStore);
            }
            if (!this._stickyRo && typeof ResizeObserver !== "undefined") {
                this._stickyRo = new ResizeObserver(() => this.syncStickyColumns());
                if (check) {
                    this._stickyRo.observe(check);
                }
                this._stickyRo.observe(stt);
                this._stickyRo.observe(store);
            }
        });
    }

    buildYearOptions(centerYear) {
        const y = Number(centerYear) || new Date().getFullYear();
        const years = [];
        for (let i = y - 2; i <= y + 3; i++) {
            years.push({ value: i, label: `Năm ${i}` });
        }
        return years;
    }

    get mode() {
        return this.props.mode || "confirm";
    }

    get isConfirm() {
        return this.mode === "confirm";
    }

    get isForecast() {
        return this.mode === "forecast";
    }

    get isMobile() {
        return Boolean(this.ui?.isSmall);
    }

    get pageMeta() {
        if (this.isForecast) {
            return {
                title: "Dự kiến thanh toán",
                subtitle: `Internet đang sử dụng · dự kiến tháng ${this.state.month}/${this.state.year}`,
            };
        }
        return {
            title: "Xác nhận thanh toán",
            subtitle: `Cùng tháng Danh sách TT ${this.state.month}/${this.state.year} · chưa xác nhận TT`,
        };
    }

    get countLabel() {
        return "hợp đồng";
    }

    get tabCounts() {
        const rows = this.state.records || [];
        const counts = { all: rows.length, pending: 0, due_soon: 0, overdue: 0, not_due: 0 };
        for (const r of rows) {
            const s = r.payment_state;
            if (s === "pending") {
                counts.pending += 1;
            } else if (s === "due_soon") {
                counts.due_soon += 1;
            } else if (s === "overdue") {
                counts.overdue += 1;
            } else if (s === "not_due") {
                counts.not_due += 1;
            }
        }
        return counts;
    }

    get filteredRecords() {
        const tab = this.state.statusTab || "all";
        const rows = this.state.records || [];
        if (tab === "all") {
            return rows;
        }
        return rows.filter((r) => r.payment_state === tab);
    }

    get pageRecords() {
        const rows = this.isMobile ? this.filteredRecords : this.state.records;
        const start = (this.state.page - 1) * this.state.pageSize;
        return rows.slice(start, start + this.state.pageSize).map((r, idx) => ({
            ...r,
            stt: start + idx + 1,
        }));
    }

    get cardRecords() {
        return this.pageRecords;
    }

    get totalPages() {
        const total = this.isMobile ? this.filteredRecords.length : this.state.totalCount;
        return Math.max(1, Math.ceil(total / this.state.pageSize));
    }

    payKey(rec) {
        return Number(rec?.payment_id || rec?.id || 0);
    }

    get selectedIds() {
        return Object.keys(this.state.selected)
            .filter((id) => this.state.selected[id])
            .map((id) => Number(id));
    }

    get allSelectedOnPage() {
        const rows = this.pageRecords;
        return rows.length > 0 && rows.every((r) => this.state.selected[this.payKey(r)]);
    }

    formatMoney(v) {
        return formatMoneyVn(v);
    }

    formatDate(v) {
        return formatDateVn(v);
    }

    payAmount(rec) {
        const n = Number(rec.forecast_amount || rec.amount || rec.next_payment_amount || 0);
        if (n > 0) {
            return n;
        }
        return Number(rec.contract_amount || 0);
    }

    stateLabel(rec) {
        return STATE_LABEL[rec.payment_state] || rec.payment_state || "—";
    }

    stateClass(rec) {
        const s = rec.payment_state;
        if (s === "paid") {
            return "is-ok";
        }
        if (s === "overdue") {
            return "is-danger";
        }
        if (s === "due_soon" || s === "pending") {
            return "is-warn";
        }
        return "is-muted";
    }

    cardAccent(rec) {
        if (this.isConfirm) {
            const tone = this.remainTone(rec);
            if (tone === "danger") {
                return "danger";
            }
            if (tone === "warning") {
                return "warn";
            }
            return "ok";
        }
        const s = rec.payment_state;
        if (s === "overdue") {
            return "danger";
        }
        if (s === "due_soon" || s === "pending") {
            return "warn";
        }
        return "ok";
    }

    storeName(rec) {
        if (Array.isArray(rec.store_id)) {
            return rec.store_id[1] || "—";
        }
        return rec.store_name || rec.name || "—";
    }

    serviceName(rec) {
        if (rec.name) {
            return rec.name;
        }
        if (rec.contract_name) {
            return rec.contract_name;
        }
        if (Array.isArray(rec.service_id)) {
            return rec.service_id[1] || "—";
        }
        return "—";
    }

    customerCodeLabel(rec) {
        const code = String(rec.customer_code || "").trim();
        return code || "—";
    }

    providerName(rec) {
        if (Array.isArray(rec.provider_id)) {
            return rec.provider_id[1] || "—";
        }
        return "—";
    }

    providerMark(rec) {
        const name = this.providerName(rec).toUpperCase();
        if (name.includes("FPT")) {
            return "F";
        }
        if (name.includes("VNPT")) {
            return "V";
        }
        if (name.includes("VIETTEL")) {
            return "VT";
        }
        return name[0] || "•";
    }

    providerClass(rec) {
        const name = this.providerName(rec).toUpperCase();
        if (name.includes("FPT")) {
            return "is-fpt";
        }
        if (name.includes("VNPT")) {
            return "is-vnpt";
        }
        if (name.includes("VIETTEL")) {
            return "is-viettel";
        }
        return "";
    }

    noteLabel(rec) {
        const text = (rec?.note || "").toString().trim();
        return text || "—";
    }

    hasInvoice(rec) {
        return Boolean(rec?.invoice_filename);
    }

    opsStatusCode(rec) {
        return rec.ops_status || rec.state || "active";
    }

    opsStatusLabel(rec) {
        const code = this.opsStatusCode(rec);
        if (code === "liquidated" || rec.state === "cancel") {
            return "Đã thanh lý";
        }
        return (OPS_STATUS_META[code] || OPS_STATUS_META.active).label;
    }

    remainTone(rec) {
        const ops = this.opsStatusCode(rec);
        if (ops === "liquidated" || ops === "cancel" || rec.state === "cancel") {
            return "ok";
        }
        const days = Number(rec.remaining_days);
        if (!Number.isFinite(days) && !rec.date_end) {
            return "ok";
        }
        if (days < 0 || rec.alert_level === "expired") {
            return "danger";
        }
        if (days <= 30 || rec.alert_level === "warn" || rec.alert_level === "danger") {
            return "warning";
        }
        return "ok";
    }

    statusCode(rec) {
        return this.remainTone(rec) === "ok" ? "active" : this.remainTone(rec);
    }

    remainLabel(rec) {
        const ops = this.opsStatusCode(rec);
        if (ops === "liquidated" || ops === "cancel" || rec.state === "cancel") {
            return "—";
        }
        if (rec.remaining_time) {
            return rec.remaining_time;
        }
        const days = Number(rec.remaining_days);
        if (!Number.isFinite(days)) {
            return "—";
        }
        if (days < 0) {
            return `Quá hạn ${Math.abs(days)} ngày`;
        }
        return `Còn ${days} ngày`;
    }

    remainIcon(rec) {
        const code = this.statusCode(rec);
        if (code === "danger") {
            return "fa fa-exclamation-circle";
        }
        if (code === "warning") {
            return "fa fa-clock-o";
        }
        return "fa fa-calendar";
    }

    /** Giống Lịch TT — tính remaining từ date_end. */
    enrichRemaining(rec) {
        const ops = rec.ops_status || rec.state || "active";
        if (ops === "liquidated" || ops === "cancel") {
            return { ...rec, remaining_days: false, remaining_time: false, alert_level: "ok" };
        }
        const end = rec.date_end ? String(rec.date_end).slice(0, 10) : "";
        if (!end) {
            return { ...rec, remaining_days: 0, remaining_time: false, alert_level: "ok" };
        }
        const today = ymd(new Date());
        const t0 = Date.parse(`${today}T00:00:00`);
        const t1 = Date.parse(`${end}T00:00:00`);
        const days = Number.isFinite(t0) && Number.isFinite(t1)
            ? Math.round((t1 - t0) / 86400000)
            : 0;
        let remaining_time;
        let alert_level;
        if (days >= 0) {
            remaining_time = `Còn ${days} ngày`;
            alert_level = days <= 7 ? "danger" : days <= 30 ? "warn" : "ok";
        } else {
            remaining_time = `Quá hạn ${Math.abs(days)} ngày`;
            alert_level = "expired";
        }
        return { ...rec, remaining_days: days, remaining_time, alert_level };
    }

    setStatusTab(tab) {
        this.state.statusTab = tab || "all";
        this.state.page = 1;
    }

    toggleTodaySection() {
        this.state.sectionOpen = !this.state.sectionOpen;
    }

    onCardCheck(rec, ev) {
        ev.stopPropagation();
        const key = this.payKey(rec);
        this.state.selected = {
            ...this.state.selected,
            [key]: Boolean(ev.target.checked),
        };
    }

    async load(props) {
        const seq = ++this._loadSeq;
        const mode = (props && props.mode) || this.mode;
        this.state.loading = true;
        try {
            if (mode === "forecast") {
                await this.loadForecastFromInternet();
            } else {
                await this.loadConfirmPayments();
            }
            if (seq !== this._loadSeq) {
                return;
            }
            if (this.state.page > this.totalPages) {
                this.state.page = 1;
            }
        } catch (err) {
            if (seq !== this._loadSeq) {
                return;
            }
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không tải được danh sách thanh toán.", {
                type: "danger",
            });
            this.state.records = [];
            this.state.totalCount = 0;
        } finally {
            if (seq === this._loadSeq) {
                this.state.loading = false;
            }
        }
    }

    async loadForecastFromInternet() {
        const year = Number(this.state.year);
        const month = Number(this.state.month);
        const domain = [
            ["active", "=", true],
            ["service_type_id.code", "=", "internet"],
            ["state", "=", "active"],
        ];
        const q = (this.state.search || "").trim();
        if (q) {
            domain.push(
                "|", "|", "|",
                ["name", "ilike", q],
                ["code", "ilike", q],
                ["customer_code", "ilike", q],
                ["store_id.name", "ilike", q]
            );
        }
        const fields = [
            "name", "code", "customer_code", "store_id", "provider_id",
            "date_end", "package_name", "contract_amount",
            "next_payment_amount", "next_payment_date",
        ];
        const rows = await this.orm.searchRead("phan.he.service", domain, fields, {
            order: "date_end asc, id desc",
            limit: 2000,
        });
        const mapped = [];
        for (const svc of rows || []) {
            const nextDue = svc.next_payment_date ? String(svc.next_payment_date).slice(0, 10) : "";
            let dateDue;
            if (nextDue && inYearMonth(nextDue, year, month)) {
                dateDue = nextDue;
            } else if (svc.date_end) {
                dateDue = projectDueInMonth(svc.date_end, year, month);
            } else if (nextDue) {
                continue;
            } else {
                dateDue = `${year}-${pad2(month)}-01`;
            }
            if (!inYearMonth(dateDue, year, month)) {
                continue;
            }
            const amount = Number(svc.next_payment_amount || 0) > 0
                ? Number(svc.next_payment_amount)
                : Number(svc.contract_amount || 0);
            mapped.push({
                id: svc.id,
                code: svc.customer_code || svc.code || "",
                store_id: svc.store_id,
                store_name: Array.isArray(svc.store_id) ? svc.store_id[1] : "",
                contract_name: svc.name || "",
                service_id: [svc.id, svc.name || ""],
                provider_id: svc.provider_id,
                period: (svc.package_name || "").trim() || "HĐ 001",
                date_due: dateDue,
                amount,
                payment_state: statusFromDue(dateDue),
            });
        }
        mapped.sort((a, b) => String(a.date_due).localeCompare(String(b.date_due)) || a.id - b.id);
        this.state.records = mapped;
        this.state.totalCount = mapped.length;
    }

    async loadConfirmPayments() {
        // Cùng API / cùng nội dung bảng Lịch thanh toán.
        const result = await this.orm.call("phan.he.service", "get_payment_confirm_board", [
            this.state.year,
            this.state.month,
            this.state.search || "",
        ]);
        let records = result?.records || [];
        records = records.map((r) => this.enrichRemaining(r));
        if (result?.year) {
            this.state.year = Number(result.year);
            this.yearOptions = this.buildYearOptions(this.state.year);
        }
        if (result?.month) {
            this.state.month = Number(result.month);
        }
        this.state.records = records;
        this.state.totalCount = result?.total ?? records.length;
        if (this.props.onConfirmCountChange) {
            this.props.onConfirmCountChange({
                count: this.state.totalCount,
                filter: "payment_confirm",
                year: this.state.year,
                month: this.state.month,
            });
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.load(), 280);
    }

    onMonthChange(ev) {
        const month = Number(ev.target.value) || 1;
        if (month === Number(this.state.month)) {
            return;
        }
        this.state.month = month;
        this.state.page = 1;
        this.load();
    }

    onYearChange(ev) {
        const year = Number(ev.target.value) || new Date().getFullYear();
        if (year === Number(this.state.year)) {
            return;
        }
        this.state.year = year;
        this.yearOptions = this.buildYearOptions(year);
        this.state.page = 1;
        this.load();
    }

    refresh() {
        this.state.page = 1;
        return this.load();
    }

    csvCell(value) {
        const s = String(value == null ? "" : value).replace(/"/g, '""');
        return `"${s}"`;
    }

    async exportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            if (!this.state.records.length) {
                this.notification.add("Không có dữ liệu để xuất.", { type: "warning" });
                return;
            }
            const header = [
                "STT", "Cửa hàng", "Mã KH", "Nhà cung cấp", "Băng thông",
                "Ngày bắt đầu", "Ngày kết thúc", "Cước tháng", "Số tiền thanh toán",
                "Ghi chú", "Thời gian còn lại", "Trạng thái",
            ];
            const lines = [header.map((h) => this.csvCell(h)).join(",")];
            this.state.records.forEach((rec, idx) => {
                lines.push([
                    idx + 1,
                    this.storeName(rec),
                    this.customerCodeLabel(rec),
                    this.providerName(rec),
                    rec.bandwidth || "",
                    this.formatDate(rec.date_start),
                    this.formatDate(rec.date_end),
                    Math.round(Number(rec.contract_amount || 0)),
                    Math.round(this.payAmount(rec)),
                    this.noteLabel(rec),
                    this.remainLabel(rec),
                    this.opsStatusLabel(rec),
                ].map((v) => this.csvCell(v)).join(","));
            });
            const blob = new Blob(["\ufeff" + lines.join("\r\n")], {
                type: "text/csv;charset=utf-8;",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `Xac_nhan_TT_T${this.state.month}_${this.state.year}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add("Đã xuất Excel.", { type: "success" });
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không xuất được Excel.", {
                type: "danger",
            });
        } finally {
            this.state.exporting = false;
        }
    }

    setPage(page) {
        this.state.page = Math.min(this.totalPages, Math.max(1, page));
    }

    onPageSizeChange(ev) {
        this.state.pageSize = Number(ev.target.value) || 15;
        this.state.page = 1;
    }

    toggleSelect(rec, ev) {
        const key = this.payKey(rec);
        this.state.selected = {
            ...this.state.selected,
            [key]: Boolean(ev.target.checked),
        };
    }

    toggleSelectAll(ev) {
        const on = Boolean(ev.target.checked);
        const next = { ...this.state.selected };
        for (const r of this.pageRecords) {
            next[this.payKey(r)] = on;
        }
        this.state.selected = next;
    }

    async confirmSelected() {
        const ids = this.selectedIds;
        if (!ids.length) {
            this.notification.add("Chọn ít nhất một phiếu để xác nhận.", { type: "warning" });
            return;
        }
        if (this.state.confirming) {
            return;
        }
        this.state.confirming = true;
        try {
            await this.orm.call("phan.he.payment", "action_mark_paid", [ids]);
            this.notification.add(
                `Đã xác nhận ${ids.length} phiếu. Hợp đồng vẫn ở Đang sử dụng.`,
                { type: "success" }
            );
            this.state.selected = {};
            await this.load();
            if (this.props.onAfterConfirm) {
                await this.props.onAfterConfirm(this.state.year, this.state.month);
            }
        } catch (err) {
            console.error(err);
            this.notification.add(err?.data?.message || err?.message || "Không xác nhận được.", {
                type: "danger",
            });
        } finally {
            this.state.confirming = false;
        }
    }

    async confirmOne(rec) {
        this.state.selected = { [this.payKey(rec)]: true };
        await this.confirmSelected();
    }
}
