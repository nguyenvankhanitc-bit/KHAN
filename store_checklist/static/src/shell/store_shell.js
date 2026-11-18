/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { evaluateExpr } from "@web/core/py_js/py";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { View } from "@web/views/view";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { StoreMgrDetailDialog, StoreViolPickDialog } from "@store_checklist/violation/violation_header";
import { PhanHeInternetShell } from "@lug_phan_he/internet_shell/phan_he_internet_shell";
import { StoreCheckViewDialog, StoreStaffPickDialog } from "@store_checklist/shell/store_check_view_dialog";

function normalizeViews(act, preferredType) {
    const views = Array.isArray(act.views) ? act.views.map((view) => [...view]) : [];
    if (!views.some((view) => view[1] === "form")) {
        views.push([false, "form"]);
    }
    if (preferredType !== "form" && !views.some((view) => view[1] === "list")) {
        views.push([false, "list"]);
    }
    if (!views.some((view) => view[1] === "search")) {
        views.push([false, "search"]);
    }
    return views;
}

export class StoreChecklistShell extends Component {
    static template = "store_checklist.Shell";
    static components = { PhanHeInternetShell, View, DateTimeInput };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            badges: {},
            isManager: false,
            isSupervisor: false,
            activeNav: "overview",
            contentMode: "dashboard",
            shiftTab: "morning", shiftStats: { total: 0, types: 0 },
            job: { date: "", storeId: "", stores: [], staff: [], off: [], storeStaff: 0, lineId: "", check: null, snap: "", closed: {} },
            done: { month: "", storeId: "", mien: "", q: "", today: false, errors: false, rows: [], open: {}, all: {}, popup: "", dayPick: "", tab: "list", staff: "", monthly: null, onlyWork: true },
            mg: { month: "", date: "", storeId: "", q: "", errors: false, active: true, evalMode: "day", name: "", names: [], rows: [], evalRows: [], week: { days: [], rows: [], week_label: "" }, busy: false },
            openGroups: { audit: true, nvbh_jobs_folder: true, evaluation: false, supervision: false, nvbh_work: false, settings: true },
            embeddedViewProps: null,
            viewKey: 1,
            dash: null,
            filters: { month: "", mien: "", store: "" },
            showAllTodo: false,
            listFilters: { month: new Date().toISOString().slice(0, 7), mien: "", store: "", auditor: "" },
            canBack: false,
            report: null,
            storeReport: null,
            rankReport: null,
            rankStore: null,
            rankStoreTotal: 0,
            managerReport: null,
            mgrLevels: [],
            mgrTab: "rank",
            flowStats: null,
            mgrFilter: "",
            mgrPage: 0,
            supQ: "",
            supStores: [],
            supPage: 0,
            personal: null,
            canCreate: false,
            sched: { ndays: 30, rows: [], loading: false },
            personalTab: "activity",
            reportOpen: {},
            rights: null,
            perm: null,
            permQ: "",
            permClosed: {},
            permEdit: null,
        });
        this.history = [{ home: true }];
        // Popup "Xử lý sai phạm" nằm bên phải thanh menu và co giãn theo bề rộng thanh menu (biến CSS --store-sidebar-w)
        const syncSidebarWidth = () => {
            const side = document.querySelector(".o_internet_sidebar");
            const w = side && window.innerWidth > 767 ? Math.round(side.getBoundingClientRect().right) : 0;
            document.documentElement.style.setProperty("--store-sidebar-w", `${w}px`);
        };
        let sideObserver;
        // Kéo mép trái của popup = kéo thanh chia của menu (menu đổi bề rộng, popup đổi theo cả hai chiều)
        const gripSidebar = (ev) => {
            const dlg = ev.target;
            if (!dlg.classList?.contains("modal-dialog") || !dlg.querySelector(".o_store_violation_list")) {
                return;
            }
            const handle = document.querySelector(".o_sidebar_resizer");
            if (handle) {
                ev.preventDefault();
                handle.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, clientX: ev.clientX, clientY: ev.clientY }));
            }
        };
        onMounted(() => {
            document.addEventListener("mousedown", gripSidebar, true);
            const side = document.querySelector(".o_internet_sidebar");
            if (side && window.ResizeObserver) {
                sideObserver = new ResizeObserver(syncSidebarWidth);
                sideObserver.observe(side);
            }
            window.addEventListener("resize", syncSidebarWidth);
            syncSidebarWidth();
            if (this._deepCheckId) {
                const id = this._deepCheckId;
                this._deepCheckId = 0;
                this.onDoneDay({ id });
            }
        });
        onWillUnmount(() => {
            sideObserver?.disconnect();
            window.removeEventListener("resize", syncSidebarWidth);
            document.removeEventListener("mousedown", gripSidebar, true);
            document.documentElement.style.removeProperty("--store-sidebar-w");
        });
        // liên kết từ tin nhắn OdooBot (?store_check=ID): mở thẳng phiếu cần đánh giá sau khi màn hình tải xong
        try {
            const raw = new URLSearchParams(window.location.search).get("store_check");
            this._deepCheckId = raw ? Number(raw) || 0 : 0;
        } catch {
            this._deepCheckId = 0;
        }
        onWillStart(async () => {
            this.state.isManager = await user.hasGroup("store_checklist.group_store_manager");
            this.state.canCreate = await user.hasGroup("store_checklist.group_store_user");
            this.state.isSupervisor = await this.orm.call("store.audit", "is_gs_supervisor", []);
            this.state.rights = await this.orm.call("store.perm.rule", "get_my_rights", []);
            await this.loadOverview();
            this.loadBadges();
        });
    }

    // Số phiếu có lỗi đã ghi nhận (hiện trên mục "Cửa hàng sai phạm"); lỗi quyền đọc thì bỏ qua, không chặn giao diện
    async loadBadges() {
        try {
            const scope = await this.orm.call("store.audit", "get_violation_scope", []);
            this.state.badges.violation_stores = await this.orm.searchCount("store.audit", [["state", "!=", "draft"], ["error_count", ">", 0], ...scope]);
        } catch {
            this.state.badges.violation_stores = 0;
        }
    }

    get brand() {
        return "CHECKLIST AUDIT";
    }

    get navSections() {
        const sections = [
            {
                id: "audit",
                label: "Checklist Audit",
                icon: "fa-check-square-o",
                iconTone: "audit",
                children: [
                    { id: "nvbh", label: "Checklist NVBH", icon: "fa-user", action: "store_checklist.action_store_audit_nvbh" },
                    // Mục con của Checklist NVBH: bấm là mở popup nhập thông tin nhân sự (không đổi màn hình), dùng quyền của mục NVBH
                    { id: "nvbh_staff", label: "Nhân sự", icon: "fa-id-badge", sub: true, permId: "nvbh", action: "store_checklist.action_store_nvbh_staff" },
                    // Mục con "Công việc" của Checklist NVBH: màn hình có 2 tab (Check list công việc / Lịch làm việc)
                    { id: "nvbh_jobs", label: "Công việc check list", icon: "fa-tasks", sub: true, permId: "nvbh", action: "store_checklist.action_store_nvbh_jobs" },
                    // Danh sách nhân viên đã check list (đã bấm Lưu); bấm vào tên để xem nội dung
                    { id: "nvbh_done", label: "Danh sách checklist NV", icon: "fa-check-square-o", sub: true, permId: "nvbh", action: "store_checklist.action_store_nvbh_done" },
                    // Quản lý & đánh giá checklist NVBH: 2 tab Bảng Nhân viên (theo tháng) / Bảng Đánh giá (theo ngày)
                    { id: "nvbh_mg_staff", label: "Quản lý & đánh giá", icon: "fa-th-list", sub: true, permId: "nvbh", action: "store_checklist.action_store_nvbh_done" },
                ],
            },
            {
                id: "report",
                label: "Báo cáo",
                icon: "fa-bar-chart",
                iconTone: "report",
                children: [
                    { id: "report_gs", label: "Báo cáo GS", icon: "fa-file-text", action: "store_checklist.action_store_report_gs" },
                    { id: "report_store", label: "Báo cáo theo cửa hàng", icon: "fa-building" },
                    { id: "report_rank", label: "Báo cáo xếp loại", icon: "fa-trophy" },
                    { id: "report_manager", label: "Báo cáo theo quản lý", icon: "fa-user" },
                    { id: "report_flow", label: "Sơ đồ quy trình vận hành giám sát", icon: "fa-sitemap" },
                ],
            },
            {
                // Thư mục trống, các mục con sẽ bổ sung sau
                id: "violation",
                label: "Xử lý sai phạm",
                icon: "fa-exclamation-triangle",
                iconTone: "violation",
                children: [
                    // Cửa hàng đã có biên bản do giám sát kiểm tra (phiếu GS không còn ở trạng thái nháp)
                    { id: "violation_stores", label: "Cửa hàng sai phạm", icon: "fa-ban", badgeKey: "violation_stores", tone: "danger", action: "store_checklist.action_store_violation_stores" },
                    { id: "violation_all", label: "Danh sách xử lý sai phạm", icon: "fa-wrench", action: "store_checklist.action_store_violation_all" },
                ],
            },
        ];
        const rights = this.state.rights; // ma trận quyền: ẩn mục không có quyền Xem
        if (rights) {
            for (const sec of sections) {
                sec.children = sec.children.filter((c) => rights[c.permId || c.id]?.read);
            }
            sections.splice(0, sections.length, ...sections.filter((sec) => sec.children.length || sec.id === "violation"));
        }
        if (this.state.isManager || rights) {
            // Thư mục "Công việc đánh giá" nằm trong Cài đặt (shell chỉ có 2 cấp nên tự dựng cấp con, thụt lề bằng CSS)
            const evaluation = [
                { id: "subgroup", label: "Phân nhóm đánh giá", icon: "fa-sitemap", action: "store_checklist.action_store_sub_group", sub: true },
                { id: "benchmark", label: "Điểm chuẩn đánh giá", icon: "fa-list-ol", action: "store_checklist.action_store_benchmark", sub: true },
                { id: "level", label: "Mức Đánh giá", icon: "fa-star", action: "store_checklist.action_store_level", sub: true },
            ];
            const supervision = [
                { id: "gs_subgroup", label: "Phân nhóm đánh giá", icon: "fa-sitemap", action: "store_checklist.action_store_sub_group_gs", sub: true },
                { id: "gs_benchmark", label: "Điểm chuẩn đánh giá", icon: "fa-list-ol", action: "store_checklist.action_store_benchmark_gs", sub: true },
                { id: "gs_level", label: "Mức độ đánh giá", icon: "fa-star", action: "store_checklist.action_store_level_gs", sub: true },
            ];
            const nvbhWork = [
                { id: "shift", label: "Danh mục ca", icon: "fa-clock-o", action: "store_checklist.action_store_shift", sub: true },
                { id: "nvbh_task", label: "Danh sách công việc NVBH", icon: "fa-list-ul", action: "store_checklist.action_store_nvbh_task", sub: true },
                { id: "nvbh_rating", label: "Xếp loại", icon: "fa-trophy", action: "store_checklist.action_store_nvbh_rating", sub: true },
            ];
            const vis = (list) => (rights ? list.filter((c) => rights[c.id]?.read) : list);
            const evalVis = vis(evaluation), supVis = vis(supervision), nvbhVis = vis(nvbhWork);
            sections.push({
                id: "settings",
                label: "Cài đặt",
                icon: "fa-cog",
                iconTone: "settings",
                children: [
                    ...(this.state.isManager ? [{ id: "access", label: "Phân quyền", icon: "fa-shield", action: "store_checklist.action_store_groups" }] : []),
                    ...(evalVis.length ? [{ id: "evaluation", label: "Công việc đánh giá", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.evaluation ? evalVis : []),
                    ...(supVis.length ? [{ id: "supervision", label: "Công việc giám sát", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.supervision ? supVis : []),
                    ...(nvbhVis.length ? [{ id: "nvbh_work", label: "Công việc checklist NVBH", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.nvbh_work ? nvbhVis : []),
                ],
            });
        }
        return sections;
    }

    isGroupOpen(groupId) {
        return Boolean(this.state.openGroups[groupId]);
    }

    toggleGroup(groupId) {
        this.state.openGroups[groupId] = !this.state.openGroups[groupId];
    }

    // 2 tab của màn Công việc (Checklist NVBH > Công việc)
    get jobTabs() {
        return [
            { id: "nvbh_jobs", label: "Check list công việc", action: "store_checklist.action_store_nvbh_jobs" },
            { id: "nvbh_schedule", label: "Lịch xếp ca", action: "store_checklist.action_store_nvbh_schedule" },
        ];
    }

    get isJobTabs() {
        return ["nvbh_jobs", "nvbh_schedule"].includes(this.state.activeNav);
    }

    // ---- In (chọn máy in trong hộp thoại in của trình duyệt) và Xuất Excel cho các bảng: Bảng checklist Tổng / Bảng Nhân viên / Bảng Đánh giá ----
    tableMeta() {
        const nav = this.state.activeNav;
        const dmy = (ymd) => (ymd ? ymd.split("-").reverse().join("/") : "");
        if (nav === "nvbh_done") {
            return {
                selector: ".o_store_total_table", title: "BẢNG CHECKLIST TỔNG", file: "Bang_checklist_tong",
                sub: `Nhân viên: ${this.state.done.staff} | Tháng: ${this.doneMonthLabel}`,
            };
        }
        const mg = this.state.mg;
        if (nav === "nvbh_mg_eval") {
            const week = mg.evalMode === "week";
            return {
                selector: ".o_store_mg_page .o_store_mg_table", file: week ? "Bang_danh_gia_tuan" : "Bang_danh_gia_ngay",
                title: "BẢNG ĐÁNH GIÁ CHECKLIST NVBH", sub: week ? `Tuần: ${mg.week.week_label}` : `Ngày: ${dmy(mg.date)}`,
            };
        }
        return {
            selector: ".o_store_mg_page .o_store_mg_table", file: "Bang_nhan_vien", title: "BẢNG NHÂN VIÊN CHECKLIST NVBH",
            sub: `Tháng: ${mg.month ? mg.month.slice(5) + "/" + mg.month.slice(0, 4) : ""}`,
        };
    }

    // đọc bảng đang hiển thị: tiêu đề cột, các dòng, dòng tổng (bỏ cột Thao tác)
    readTable(selector) {
        const table = document.querySelector(selector);
        if (!table) {
            return null;
        }
        const cellText = (td) => {
            const wk = td.querySelector(".wk");
            if (wk) {
                return wk.classList.contains("ok") ? "✓" : wk.classList.contains("bad") ? "✗" : wk.classList.contains("wait") ? "…" : "OFF";
            }
            const text = td.textContent.replace(/\s+/g, " ").trim();
            // số kiểu Việt Nam (1.234,5) -> số để Excel tính được
            if (/^-?\d+$/.test(text)) {
                return Number(text);
            }
            if (/^-?\d{1,3}(\.\d{3})*(,\d+)?$/.test(text) || /^-?\d+,\d+$/.test(text)) {
                return Number(text.replace(/\./g, "").replace(",", "."));
            }
            return text;
        };
        const expand = (tr) => {
            const out = [];
            for (const td of tr.children) {
                out.push(cellText(td));
                for (let i = 1; i < (td.colSpan || 1); i++) {
                    out.push("");
                }
            }
            return out;
        };
        const headers = [...table.querySelectorAll("thead th")].map((th) => th.textContent.replace(/\s+/g, " ").trim());
        const drop = headers.indexOf("Thao tác");
        const keep = (arr) => (drop < 0 ? arr : arr.filter((_v, i) => i !== drop));
        const rows = [...table.querySelectorAll("tbody tr")].map((tr) => keep(expand(tr)));
        const footTr = table.querySelector("tfoot tr");
        return { headers: keep(headers), rows, foot: footTr ? keep(expand(footTr)) : null };
    }

    async onTableExport() {
        if (this.state.activeNav === "nvbh_done") {
            return this.pickStaff("Xuất Excel", (names) => this.exportDoneStaff(names));
        }
        try {
            const meta = this.tableMeta();
            const data = this.readTable(meta.selector);
            if (!data || !data.rows.length) {
                this.notification.add("Không có dữ liệu để xuất", { type: "warning" });
                return;
            }
            const file = await this.orm.call("store.nvbh.check", "export_table_xlsx", [], {
                title: meta.title, subtitle: meta.sub, headers: data.headers, rows: data.rows, foot: data.foot, filename: meta.file,
            });
            const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
            link.download = file.name;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            this.notifyError(error);
        }
    }

    onTablePrint() {
        if (this.state.activeNav === "nvbh_done") {
            return this.pickStaff("In", (names) => this.printDoneStaff(names));
        }
        const meta = this.tableMeta();
        const data = this.readTable(meta.selector);
        if (!data || !data.rows.length) {
            this.notification.add("Không có dữ liệu để in", { type: "warning" });
            return;
        }
        this.printPages([{ title: meta.title, sub: meta.sub, headers: data.headers, rows: data.rows, foot: data.foot }]);
    }

    // mỗi phần tử của pages (title, sub, headers, rows, foot) là một trang in; mở hộp thoại in để chọn máy in
    printPages(pages) {
        const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
        const fmt = (v) => (typeof v === "number" ? this.fmtNum(v) : esc(v));
        const tr = (cells, tag = "td") => `<tr>${cells.map((v) => `<${tag}>${fmt(v)}</${tag}>`).join("")}</tr>`;
        const section = (p, i) => `<section class="${i ? "brk" : ""}">
            <div class="head"><img src="/web/binary/company_logo" alt=""/><div><h1>${esc(p.title)}</h1><div class="sub">${esc(p.sub)}</div></div></div>
            <table><thead>${tr(p.headers, "th")}</thead><tbody>${p.rows.map((r) => tr(r)).join("")}</tbody>
            ${p.foot ? `<tfoot>${tr(p.foot)}</tfoot>` : ""}</table>
            <div class="foot">In ngày ${new Date().toLocaleDateString("vi-VN")}</div></section>`;
        const html = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(pages[0].title)}</title><style>
            @page { size: A4 landscape; margin: 8mm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: Arial, sans-serif; font-size: 11px; color: #0f172a; margin: 0; }
            .brk { page-break-before: always; }
            .head { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #1e3a6e; padding-bottom: 8px; margin-bottom: 10px; }
            .head img { height: 42px; } h1 { font-size: 18px; margin: 0; color: #1e3a6e; } .sub { color: #475569; margin-top: 3px; }
            table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #94a3b8; padding: 4px 6px; text-align: center; }
            th { background: #dbeafe; font-weight: 700; } tfoot td { background: #dbe7f5; font-weight: 700; }
            thead { display: table-header-group; } tr { page-break-inside: avoid; }
            .foot { margin-top: 10px; color: #64748b; font-size: 10px; text-align: right; }
        </style></head><body>${pages.map(section).join("")}</body></html>`;
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(html);
        doc.close();
        let started = false;
        const go = () => {
            if (started) { return; }
            started = true;
            frame.contentWindow.focus();
            frame.contentWindow.print();
            setTimeout(() => frame.remove(), 60000);
        };
        const imgs = [...doc.querySelectorAll("img")].filter((i) => !i.complete);
        if (imgs.length) {
            let left = imgs.length;
            imgs.forEach((i) => (i.onload = i.onerror = () => { if (!--left) { go(); } }));
            setTimeout(go, 3000);
        } else {
            go();
        }
    }

    // ---- Bảng checklist Tổng: chọn nhân viên rồi in / xuất (mỗi nhân viên một trang / một sheet) ----
    pickStaff(confirmLabel, onConfirm) {
        const items = this.doneStaffOptions.map((o) => ({ key: o.name, label: o.label }));
        if (!items.length) {
            this.notification.add("Không có nhân viên nào để chọn", { type: "warning" });
            return;
        }
        this.dialog.add(StoreStaffPickDialog, {
            title: `${confirmLabel} Bảng checklist Tổng`, confirmLabel, items, selected: [this.state.done.staff], onConfirm,
        });
    }

    async exportDoneStaff(names) {
        try {
            const d = this.state.done;
            const file = await this.orm.call("store.nvbh.check", "export_done_monthly_xlsx", [], {
                month: d.month || false, staff_names: names, store_id: d.storeId ? Number(d.storeId) : false, only_work: d.onlyWork,
            });
            const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
            link.download = file.name;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            this.notifyError(error);
        }
    }

    async printDoneStaff(names) {
        try {
            const d = this.state.done;
            const pages = [];
            for (const name of names) {
                const data = await this.orm.call("store.nvbh.check", "get_done_monthly", [], {
                    month: d.month || false, staff_name: name, store_id: d.storeId ? Number(d.storeId) : false,
                });
                const t = data.total || {};
                const pct = (v) => `${this.fmtNum(v)}%`;
                pages.push({
                    title: "BẢNG CHECKLIST TỔNG",
                    sub: `Nhân viên: ${name} | Tháng: ${this.doneMonthLabel}`,
                    headers: ["Ngày", "Cửa hàng", "Mã ca", "Trạng thái ngày", "Tổng việc ca", "Đã làm", "Số lỗi", "Điểm đạt", "Điểm chuẩn ca", "Điểm CHT đánh giá", "Điểm ASM đánh giá", "Tỷ lệ đạt (%)", "Kết quả", "Ghi chú / Tóm tắt công việc"],
                    rows: data.rows.filter((r) => !d.onlyWork || r.kind !== "off").map((r) => [
                        r.date, r.store || "-", r.kind === "off" ? "OFF" : r.shift, r.status, r.total, r.done, r.errors,
                        r.kind === "off" || r.evaluated ? r.points : "-", r.max_points, r.pts_cht == null ? "-" : r.pts_cht, r.pts_asm == null ? "-" : r.pts_asm,
                        r.kind === "off" || r.evaluated ? pct(r.pct) : "-", r.control, r.note || "-",
                    ]),
                    foot: [`TỔNG CỘNG KỲ ${this.doneMonthLabel} (${t.days || 0} ngày công thực tế)`, "", "", "", t.total || 0, t.done || 0, t.errors || 0,
                        t.avg_points == null ? "-" : t.avg_points, t.max_points || 0, t.avg_cht == null ? "-" : t.avg_cht, t.avg_asm == null ? "-" : t.avg_asm,
                        t.avg_pct == null ? "-" : pct(t.avg_pct), `${t.valid || 0}/${t.days || 0} công hợp lệ`, "Tự động liên kết sang dữ liệu Odoo"],
                });
            }
            this.printPages(pages);
        } catch (error) {
            this.notifyError(error);
        }
    }

    // 2 tab của màn Quản lý & đánh giá checklist NVBH
    get mgTabs() {
        return [
            { id: "nvbh_mg_staff", label: "Bảng Nhân viên" },
            { id: "nvbh_mg_eval", label: "Bảng Đánh giá" },
        ];
    }

    get isMgTabs() {
        return ["nvbh_mg_staff", "nvbh_mg_eval"].includes(this.state.activeNav);
    }

    // ---- Quản lý & đánh giá checklist NVBH ----
    async openManagePage(tab = "nvbh_mg_staff") {
        try {
            this.state.activeNav = tab;
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            const mg = this.state.mg;
            if (!mg.date) {
                mg.date = this.jobToday();
            }
            if (!mg.month) {
                mg.month = mg.date.slice(0, 7);
            }
            if (!this.state.job.stores.length) {
                this.state.job.stores = await this.orm.call("store.nvbh.check", "get_my_stores", []);
            }
            await this.loadManage();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async loadManage() {
        const mg = this.state.mg;
        const store_id = mg.storeId ? Number(mg.storeId) : false;
        const search = mg.q.trim() || false;
        // ô chọn nhân viên: lọc theo đúng tên đã chọn
        const name = mg.name || false;
        const pick = (rows) => (name ? rows.filter((r) => r.name === name) : rows);
        if (this.state.activeNav === "nvbh_mg_eval" && mg.evalMode === "week") {
            const w = await this.orm.call("store.nvbh.check", "get_manage_week", [], { work_date: mg.date || false, store_id, search });
            w.rows = pick(w.rows);
            mg.week = w;
            if (!search && !name) {
                mg.names = [...new Set(w.rows.map((r) => r.name))];
            }
        } else if (this.state.activeNav === "nvbh_mg_eval") {
            mg.evalRows = pick(await this.orm.call("store.nvbh.check", "get_manage_eval", [], { work_date: mg.date || false, store_id, search }));
            mg.evalRows.forEach((r, i) => (r.stt = i + 1));
            if (!search && !name) {
                mg.names = [...new Set(mg.evalRows.map((r) => r.name))];
            }
        } else {
            mg.rows = pick(await this.orm.call("store.nvbh.check", "get_manage_staff", [], {
                month: mg.month || false, store_id, search, errors_only: mg.errors, active_only: mg.active,
            }));
            mg.rows.forEach((r, i) => (r.stt = i + 1));
            if (!search && !name) {
                mg.names = [...new Set(mg.rows.map((r) => r.name))];
            }
        }
    }

    onMgName(ev) {
        this.state.mg.name = ev.target.value;
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    onMgActive(ev) {
        this.state.mg.active = ev.target.checked;
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    onMgEvalMode(mode) {
        if (this.state.mg.evalMode !== mode) {
            this.state.mg.evalMode = mode;
            return this.loadManage().catch((e) => this.notifyError(e));
        }
    }

    onMgAddStaff() {
        return this.openStaffForm(false, () => this.loadManage());
    }

    mgWeekIcon(st) {
        return { ok: "fa-check", bad: "fa-times", wait: "fa-circle-o", off: "" }[st] || "";
    }

    mgShiftWeek(delta) {
        return this.onMgShiftDate(delta * 7);
    }

    onMgTab(tab) {
        return this.state.activeNav === tab.id ? null : this.openManagePage(tab.id);
    }

    onMgFilter(key, ev) {
        const mg = this.state.mg;
        mg[key] = ev.target.value;
        if (key === "storeId") {
            mg.name = "";
        }
        if (key === "date" && mg.date) {
            mg.month = mg.date.slice(0, 7);
        }
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    onMgShiftDate(delta) {
        const mg = this.state.mg;
        const d = new Date(`${mg.date || this.jobToday()}T00:00:00`);
        d.setDate(d.getDate() + delta);
        mg.date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        mg.month = mg.date.slice(0, 7);
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    onMgSearch(ev) {
        this.state.mg.q = ev.target.value;
        clearTimeout(this._mgTimer);
        this._mgTimer = setTimeout(() => this.loadManage().catch((e) => this.notifyError(e)), 300);
    }

    onMgErrors() {
        this.state.mg.errors = !this.state.mg.errors;
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    // "Chấm điểm" / "Xem": mở popup checklist của nhân viên trong ngày (tạo phiếu nếu ngày đó chưa có)
    async onMgOpen(row) {
        try {
            const payload = await this.orm.call("store.nvbh.check", "get_checklist", [row.line_id]);
            if (payload) {
                this.dialog.add(StoreCheckViewDialog, { payload, onSaved: () => this.loadManage() });
            }
        } catch (error) {
            this.notifyError(error);
        }
    }

    // "Chi tiết" ở Bảng Nhân viên: sang Bảng Đánh giá, lọc theo tên nhân viên đó
    onMgStaffDetail(row) {
        this.state.mg.q = row.name;
        this.state.mg.evalMode = "day";
        return this.openManagePage("nvbh_mg_eval");
    }

    get mgCount() {
        const mg = this.state.mg;
        if (this.state.activeNav !== "nvbh_mg_eval") {
            return mg.rows.length;
        }
        return mg.evalMode === "week" ? mg.week.rows.length : mg.evalRows.length;
    }

    mgScore(row) {
        return `${this.fmtNum(row.points)} / ${this.fmtNum(row.max_points)}`;
    }

    // ---- Danh sách checklist nhân viên: tổng hợp theo nhân viên trong tháng, bấm tên để xem từng ngày ----
    async openDonePage() {
        try {
            this.state.activeNav = "nvbh_done";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            const d = this.state.done;
            if (!d.month) {
                const now = new Date();
                d.month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
            }
            if (!this.state.job.stores.length) {
                this.state.job.stores = await this.orm.call("store.nvbh.check", "get_my_stores", []);
            }
            await this.loadDone();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async loadDone() {
        const d = this.state.done;
        d.rows = await this.orm.call("store.nvbh.check", "get_done_summary", [], {
            month: d.month || false,
            store_id: d.storeId ? Number(d.storeId) : false,
            mien: d.mien || false,
            search: d.q.trim() || false,
            today: d.today,
            errors: d.errors,
        });
        if (d.rows.length && !d.rows.some((r) => d.open[r.key])) {
            d.open[d.rows[0].key] = true; // mở sẵn nhân viên đầu tiên
        }
        if (d.tab === "total") {
            d.storeStaff = await this.orm.call("store.nvbh.check", "get_store_staff_options", [], {
                month: d.month || false, store_id: d.storeId ? Number(d.storeId) : false,
            });
            await this.loadDoneMonthly();
        }
    }

    // 2 tab của màn Danh sách checklist NV: DS Nhân viên check list / Bảng checklist Tổng
    get doneTabs() {
        return [
            { id: "list", label: "DS Nhân viên check list" },
            { id: "total", label: "Bảng checklist Tổng" },
        ];
    }

    get doneStaffNames() {
        return this.doneStaffOptions.map((o) => o.name);
    }

    // danh sách chọn nhân viên: "Họ tên (ID: mã)" - gồm toàn bộ nhân viên của cửa hàng, không chỉ người đã có checklist
    get doneStaffOptions() {
        const seen = new Map();
        for (const r of [...(this.state.done.storeStaff || []), ...this.state.done.rows]) {
            if (!seen.has(r.name) || (!seen.get(r.name).code && r.code)) {
                seen.set(r.name, { name: r.name, code: r.code || "" });
            }
        }
        return [...seen.values()].map((o) => ({ name: o.name, label: o.code ? `${o.name} (ID: ${o.code})` : o.name }));
    }

    async onDoneTab(tab) {
        if (this.state.done.tab !== tab.id) {
            this.state.done.tab = tab.id;
            await this.loadDone().catch((e) => this.notifyError(e));
        }
    }

    async loadDoneMonthly() {
        const d = this.state.done;
        const names = this.doneStaffNames;
        if (!names.includes(d.staff)) {
            d.staff = names[0] || "";
        }
        d.monthly = d.staff
            ? await this.orm.call("store.nvbh.check", "get_done_monthly", [], {
                month: d.month || false, staff_name: d.staff, store_id: d.storeId ? Number(d.storeId) : false,
            })
            : null;
    }

    onDoneStaff(ev) {
        this.state.done.staff = ev.target.value;
        return this.loadDoneMonthly().catch((e) => this.notifyError(e));
    }

    // "Chỉ hiện ngày đi làm" / "Tất cả N ngày"
    get doneMonthlyRows() {
        const rows = this.state.done.monthly?.rows || [];
        return this.state.done.onlyWork ? rows.filter((r) => r.kind !== "off") : rows;
    }

    get doneWorkCount() {
        return (this.state.done.monthly?.rows || []).filter((r) => r.kind !== "off").length;
    }

    get doneMonthLabel() {
        const m = this.state.done.month || "";
        return m ? `${m.slice(5)}/${m.slice(0, 4)}` : "";
    }

    onDoneOnlyWork(flag) {
        this.state.done.onlyWork = flag;
    }

    onDoneMonthlyRow(row) {
        return row.id ? this.onDoneDay({ id: row.id }) : null;
    }

    onDoneFilter(key, ev) {
        this.state.done[key] = ev.target.value;
        return this.loadDone().catch((e) => this.notifyError(e));
    }

    onDoneToggle(key) {
        this.state.done[key] = !this.state.done[key];
        return this.loadDone().catch((e) => this.notifyError(e));
    }

    onDoneSearch(ev) {
        this.state.done.q = ev.target.value;
        clearTimeout(this._doneTimer);
        this._doneTimer = setTimeout(() => this.loadDone().catch((e) => this.notifyError(e)), 300);
    }

    // bấm Xem chi tiết: mở popup công việc theo ngày của đúng nhân viên đó
    toggleDoneEmp(key) {
        this.state.done.popup = key;
        this.state.done.dayPick = "";
    }

    closeDonePopup() {
        this.state.done.popup = "";
    }

    get donePopupEmp() {
        const key = this.state.done.popup;
        return key ? this.state.done.rows.find((r) => r.key === key) || null : null;
    }

    // ngày ASM đã đánh giá xong thì ẩn khỏi bảng chi tiết (bật "Hiện cả ngày ASM đã đánh giá" để xem lại)
    // dayPick: "" = tất cả các ngày nhân viên đã check list (mặc định); "todo" = chỉ ngày ASM chưa đánh giá xong; còn lại = đúng ngày được chọn
    visibleDays(emp) {
        const pick = this.state.done.dayPick;
        if (pick === "todo") {
            return emp.days.filter((d) => !d.asm_done);
        }
        if (pick) {
            return emp.days.filter((d) => d.date === pick);
        }
        return emp.days;
    }

    onDonePickDay(ev) {
        this.state.done.dayPick = ev.target.value;
        this.state.done.all = {};
    }

    doneDays(emp) {
        return this.visibleDays(emp);
    }

    // 3 ngày gần nhất theo lịch: hôm kia, hôm qua, hôm nay (từ cũ đến mới); ngày không có phiếu hiện ô trống "Chưa có"
    recentDays(emp) {
        const out = [];
        const pad = (n) => String(n).padStart(2, "0");
        for (let back = 2; back >= 0; back--) {
            const d = new Date();
            d.setDate(d.getDate() - back);
            const key = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
            out.push(emp.days.find((x) => x.date === key) || { id: 0, date: key, empty: true, pct: null, errors: 0 });
        }
        return out;
    }

    // thống kê trạng thái các ngày của nhân viên: chờ đánh giá (chưa đánh giá xong) / đã đánh giá xong
    pendingCount(emp) {
        return emp.days.filter((d) => !d.evaluated).length;
    }

    evaluatedCount(emp) {
        return emp.days.filter((d) => d.evaluated).length;
    }

    onRecentDay(day) {
        if (day.id) {
            return this.onDoneDay(day);
        }
    }

    dayTone(day) {
        if (day.empty) {
            return "is-empty";
        }
        return day.errors > 0 ? "is-bad" : day.evaluated ? "is-ok" : "is-wait";
    }

    dayIcon(day) {
        if (day.empty) {
            return "fa-minus-circle";
        }
        return day.errors > 0 ? "fa-exclamation-circle" : day.evaluated ? "fa-check-circle" : "fa-clock-o";
    }

    dayLabel(day) {
        if (day.empty) {
            return "Chưa có";
        }
        if (day.state === "draft") {
            return "Đang làm";
        }
        return day.errors > 0 ? "Lỗi" : day.evaluated ? "Đạt" : "Chờ";
    }

    showAllDoneDays(emp) {
        this.state.done.all[emp.key] = true;
    }

    fmtNum(n) {
        return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(n || 0);
    }

    get isAdminUser() {
        return Boolean(user.isSystem || user.isAdmin);
    }

    // Quản trị viên: xóa checklist đã lưu (một ngày hoặc toàn bộ ngày của nhân viên trong khoảng đang xem)
    onDoneDelete(days, label) {
        const ids = (days || []).map((d) => d.id).filter(Boolean);
        if (!ids.length) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: "Xóa checklist",
            body: `Xóa ${ids.length} checklist của "${label}"? Thao tác này không hoàn tác được.`,
            confirmLabel: "Xóa",
            confirm: async () => {
                try {
                    await this.orm.call("store.nvbh.check", "delete_checks", [ids]);
                    this.notification.add(`Đã xóa ${ids.length} checklist`, { type: "success" });
                    await this.loadDone();
                } catch (error) {
                    this.notifyError(error);
                }
            },
            cancel: () => {},
        });
    }

    async onDoneDay(day) {
        try {
            const payload = await this.orm.call("store.nvbh.check", "read_checklist", [day.id]);
            if (payload) {
                this.dialog.add(StoreCheckViewDialog, { payload, onSaved: () => this.loadDone() });
            }
        } catch (error) {
            this.notifyError(error);
        }
    }

    // ---- Trang "Check list công việc": Ngày + Cửa hàng + Nhân viên (từ Lịch làm việc), tích là lưu ngay ----
    jobToday() {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    }

    async openJobsPage() {
        try {
            this.state.activeNav = "nvbh_jobs";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            const job = this.state.job;
            if (!job.date) {
                job.date = this.jobToday();
            }
            if (!job.stores.length) {
                job.stores = await this.orm.call("store.nvbh.check", "get_my_stores", []);
            }
            if (!job.storeId && job.stores.length === 1) {
                job.storeId = String(job.stores[0].id);
            }
            if (!job.storeId) {
                // tự chọn cửa hàng của người dùng đang đăng nhập; không tra được thì để trống như cũ
                const sid = await this.orm.call("store.nvbh.check", "get_user_store", []).catch(() => false);
                if (sid && job.stores.some((st) => st.id === sid)) {
                    job.storeId = String(sid);
                }
            }
            await this.loadJobStaff();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async loadJobStaff() {
        const job = this.state.job;
        await this.refreshJobStaff();
        if (!job.staff.some((st) => String(st.id) === String(job.lineId))) {
            // mặc định chọn nhân viên đầu tiên chưa check list xong
            const first = job.staff.find((st) => !st.finished) || job.staff[0];
            job.lineId = first ? String(first.id) : "";
        }
        await this.loadJobChecklist();
    }

    // danh sách nhân viên có lịch trong ngày (thẻ nhân viên), kèm tiến độ; nhân viên đã check list xong sẽ mờ đi
    async refreshJobStaff() {
        const job = this.state.job;
        const ov = job.storeId && job.date
            ? await this.orm.call("store.nvbh.check", "get_job_overview", [Number(job.storeId), job.date])
            : { staff: [], off: [], store_staff: 0 };
        job.staff = ov.staff;
        job.off = ov.off;
        job.storeStaff = ov.store_staff;
    }

    onJobPick(sf) {
        if (String(sf.id) === String(this.state.job.lineId)) {
            return;
        }
        if (!this.jobConfirmLeave()) {
            return;
        }
        this.state.job.lineId = String(sf.id);
        return this.loadJobChecklist().catch((e) => this.notifyError(e));
    }

    jobStaffNum(n) {
        return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(n || 0);
    }

    async loadJobChecklist() {
        const job = this.state.job;
        job.check = job.lineId ? await this.orm.call("store.nvbh.check", "get_checklist", [Number(job.lineId)]) : null;
        job.snap = this.jobSnapshot();
    }

    // ảnh chụp trạng thái đã lưu của các dòng, để biết có thay đổi chưa lưu hay không
    jobSnapshot() {
        return JSON.stringify((this.state.job.check?.lines || []).map((l) => [l.id, l.is_done, (l.note || "").trim()]));
    }

    get jobDirty() {
        return Boolean(this.state.job.check) && this.jobSnapshot() !== this.state.job.snap;
    }

    // KPI và trạng thái tính ngay trên màn hình theo ô tích / ghi chú đang nhập (chưa lưu)
    jobLineStatus(line) {
        return line.is_done ? "done" : (line.note || "").trim() ? "doing" : "todo";
    }

    get jobKpi() {
        const lines = this.state.job.check?.lines || [];
        const count = (st) => lines.filter((l) => this.jobLineStatus(l) === st).length;
        const num = (v) => Math.round((v || 0) * 100) / 100;
        return {
            total: lines.length, doing: count("doing"), done: count("done"), todo: count("todo"),
            // điểm đạt = điểm quản lý đã đánh giá (Đạt = điểm chuẩn, T.Bình = điểm chuẩn / 2, Không đạt = 0); điểm tối đa = tổng Điểm chuẩn
            points: num(lines.reduce((sum, l) => sum + (l.actual_score || 0), 0)),
            maxPoints: num(lines.reduce((sum, l) => sum + (l.score || 0), 0)),
        };
    }

    // đổi ngày / cửa hàng / nhân viên khi còn thay đổi chưa lưu: hỏi trước
    jobConfirmLeave() {
        return !this.jobDirty || window.confirm("Có thay đổi chưa lưu, nếu tiếp tục sẽ bị mất. Tiếp tục?");
    }

    // ô chọn ngày hiển thị dd/mm/yyyy (không phụ thuộc ngôn ngữ trình duyệt)
    ymdToDt(ymd) {
        return ymd ? luxon.DateTime.fromISO(ymd) : false;
    }

    dtToYmd(dt) {
        return dt && dt.isValid ? dt.toFormat("yyyy-MM-dd") : "";
    }

    onJobDatePick(dt) {
        const ymd = this.dtToYmd(dt);
        if (!ymd || ymd === this.state.job.date) {
            return;
        }
        if (!this.jobConfirmLeave()) {
            this.state.job.dateKey = (this.state.job.dateKey || 0) + 1; // dựng lại ô ngày về giá trị cũ
            return;
        }
        this.state.job.date = ymd;
        return this.loadJobStaff().catch((e) => this.notifyError(e));
    }

    onMgDatePick(dt) {
        const ymd = this.dtToYmd(dt);
        if (!ymd || ymd === this.state.mg.date) {
            return;
        }
        this.state.mg.date = ymd;
        this.state.mg.month = ymd.slice(0, 7);
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    onJobDate(ev) {
        if (!this.jobConfirmLeave()) {
            ev.target.value = this.state.job.date;
            return;
        }
        this.state.job.date = ev.target.value;
        return this.loadJobStaff().catch((e) => this.notifyError(e));
    }

    onJobStore(ev) {
        if (!this.jobConfirmLeave()) {
            ev.target.value = this.state.job.storeId;
            return;
        }
        this.state.job.storeId = ev.target.value;
        this.state.job.lineId = "";
        return this.loadJobStaff().catch((e) => this.notifyError(e));
    }

    onJobStaff(ev) {
        if (!this.jobConfirmLeave()) {
            ev.target.value = this.state.job.lineId;
            return;
        }
        this.state.job.lineId = ev.target.value;
        return this.loadJobChecklist().catch((e) => this.notifyError(e));
    }

    get jobLocked() {
        return Boolean(this.state.job.check) && this.state.job.check.can_execute === false;
    }

    onJobToggle(line) {
        if (this.jobLocked) {
            return;
        }
        line.is_done = !line.is_done;
    }

    onJobNote(line, ev) {
        line.note = ev.target.value;
    }

    onJobAll(ev) {
        if (this.jobLocked) {
            ev.target.checked = this.jobAllDone;
            return;
        }
        for (const line of this.state.job.check?.lines || []) {
            line.is_done = ev.target.checked;
        }
    }

    async onJobSave() {
        const check = this.state.job.check;
        if (!check || !this.jobDirty) {
            return;
        }
        try {
            const changes = check.lines.map((l) => ({ id: l.id, is_done: l.is_done, note: (l.note || "").trim() }));
            this.state.job.check = await this.orm.call("store.nvbh.check", "save_checklist", [check.id, changes]);
            this.state.job.snap = this.jobSnapshot();
            await this.refreshJobStaff(); // cập nhật thẻ nhân viên: nhân viên đã xong sẽ mờ đi
            this.notification.add("Đã lưu checklist công việc", { type: "success" });
        } catch (error) {
            this.notifyError(error);
            return;
        }
        // lưu xong mà đã làm đủ mọi công việc: tự gửi phiếu cho người đánh giá tiếp theo
        if (this.jobCanSubmit && this.jobAllDone) {
            try {
                this.state.job.check = await this.orm.call("store.nvbh.check", "submit_to_reviewer", [this.state.job.check.id]);
                this.state.job.snap = this.jobSnapshot();
                await this.refreshJobStaff();
                this.notification.add(`Đã tự động gửi cấp trên đánh giá: ${this.state.job.check.reviewer_name}`, { type: "success" });
            } catch (error) {
                this.notifyError(error); // đã lưu rồi; không gửi được (vd. chưa có quản lý) thì báo lý do, vẫn có nút gửi tay
            }
        }
    }

    // Gửi cấp trên đánh giá: chốt phần làm của nhân viên, khóa tick và thông báo cho người đánh giá
    async onJobSubmit() {
        const check = this.state.job.check;
        if (!check || this.jobDirty) {
            return;
        }
        try {
            this.state.job.check = await this.orm.call("store.nvbh.check", "submit_to_reviewer", [check.id]);
            this.state.job.snap = this.jobSnapshot();
            await this.refreshJobStaff();
            this.notification.add(`Đã gửi cấp trên đánh giá: ${this.state.job.check.reviewer_name}`, { type: "success" });
        } catch (error) {
            this.notifyError(error);
        }
    }

    get jobCanSubmit() {
        const c = this.state.job.check;
        return Boolean(c) && c.can_submit === true && c.state === "draft";
    }

    async onJobCancel() {
        try {
            await this.loadJobChecklist();
        } catch (error) {
            this.notifyError(error);
        }
    }

    get jobAllDone() {
        const lines = this.state.job.check?.lines || [];
        return lines.length > 0 && lines.every((l) => l.is_done);
    }

    // gom công việc theo Nhóm công việc: dòng đầu mỗi nhóm hiện tiêu đề (thu gọn / mở rộng)
    jobGroupStart(index) {
        const lines = this.state.job.check?.lines || [];
        return index === 0 || lines[index - 1].group !== lines[index].group;
    }

    jobGroupInfo(group) {
        const rows = (this.state.job.check?.lines || []).filter((l) => l.group === group);
        return { count: rows.length, done: rows.filter((l) => l.is_done).length };
    }

    toggleJobGroup(group) {
        this.state.job.closed[group] = !this.state.job.closed[group];
    }

    jobSel(a, b) {
        return String(a) === String(b);
    }

    jobStatusLabel(status) {
        return { todo: "Chưa làm", doing: "Đang làm", done: "Đã làm" }[status] || "";
    }

    async onJobTab(tab) {
        if (this.state.activeNav !== tab.id) {
            await this.openAction(tab.action, tab.id);
        }
    }

    navChildClass(child) {
        const cls = ["store-tn-" + child.id];
        // mục "Công việc" vẫn sáng khi đang ở tab Lịch làm việc
        if (this.state.activeNav === child.id || (child.id === "nvbh_jobs" && this.state.activeNav === "nvbh_schedule") || (child.id === "nvbh_mg_staff" && this.state.activeNav === "nvbh_mg_eval")) {
            cls.push("is-active");
        }
        if (child.sub) {
            cls.push("is-sub");
        }
        if (child.folder) {
            cls.push("is-folder", this.state.openGroups[child.id] ? "is-open" : "is-closed");
        }
        return cls.join(" ");
    }

    async loadOverview() {
        const f = this.state.filters;
        const dash = await this.orm.call("store.audit", "get_dashboard_data", [], {
            month: f.month || false,
            mien: f.mien || false,
            store_id: f.store ? Number(f.store) : false,
        });
        f.month = dash.month;
        if (!Array.isArray(dash.done_rows)) {
            if (dash.done > 0) {
                const [y, m] = dash.month.split("-").map(Number);
                const ny = m === 12 ? y + 1 : y;
                const nm = m === 12 ? 1 : m + 1;
                const dom = [
                    ["audit_date", ">=", `${y}-${String(m).padStart(2, "0")}-01 00:00:00`],
                    ["audit_date", "<", `${ny}-${String(nm).padStart(2, "0")}-01 00:00:00`],
                ];
                if (f.store) {
                    dom.push(["store_id", "=", Number(f.store)]);
                }
                const audits = await this.orm.searchRead("store.audit", dom, ["store_id", "mien", "audit_date"], { order: "audit_date desc" });
                const map = new Map();
                const labels = { Nam: "Miền Nam", "ĐTT": "Miền ĐTT", "Bắc": "Miền Bắc", other: "Khác" };
                for (const a of audits) {
                    if (!a.store_id) continue;
                    const sid = a.store_id[0];
                    const key = ["Nam", "ĐTT", "Bắc"].includes(a.mien) ? a.mien : "other";
                    if (f.mien && key !== f.mien) continue;
                    if (!map.has(sid)) {
                        const dt = a.audit_date ? a.audit_date.slice(0, 10).split("-").reverse().join("/") : "";
                        map.set(sid, { id: sid, store: a.store_id[1], mien: labels[key], key, last: dt });
                    }
                }
                dash.done_rows = [...map.values()].sort((a, b) => a.store.localeCompare(b.store));
            } else {
                dash.done_rows = [];
            }
        }
        this.state.dash = dash;
    }

    // Các danh sách phiếu (Checklist NVBH / ASM / GS và Danh Sách Đánh Giá) có thanh lọc tháng / cửa hàng / miền
    get filterNavs() {
        return ["review", "review_list", "nvbh", "nvbh_staff", "nvbh_schedule", "asm", "gs", "violation_stores", "violation_all", ...this.reportNavs];
    }

    get reportNavs() {
        return ["report_gs", "report_store", "report_rank", "report_manager", "report_sup", "report_flow"];
    }

    // Nút "Thêm mới" riêng của module (thanh bộ lọc), không phụ thuộc nút mặc định của Odoo ở thanh điều khiển
    get showOwnAdd() {
        return Boolean(
            this.showListFilters
            && !this.reportNavs.includes(this.state.activeNav)
            && !["violation_stores", "violation_all", "nvbh_done", "nvbh_staff"].includes(this.state.activeNav)
            && this.state.canCreate
            && (!this.state.rights || this.state.rights[this.permKey]?.create)
            && (this.state.embeddedViewProps || this.isScheduleNav)
        );
    }

    // Điểm chuẩn / Mức đánh giá (Cài đặt, chỉ Quản lý): các màn mở phiếu trong hộp thoại, cũng dùng nút riêng
    get showSettingsAdd() {
        return Boolean(
            (this.state.isManager || this.state.rights?.[this.state.activeNav]?.create)
            && this.state.embeddedViewProps
            && ["benchmark", "level", "gs_benchmark", "gs_level", "shift", "nvbh_task", "nvbh_rating"].includes(this.state.activeNav)
        );
    }

    onAddNew() {
        if (this.isScheduleNav) {
            return this.openScheduleForm();
        }
        this.state.embeddedViewProps?.createRecord?.();
    }

    // Điểm chuẩn đánh giá: xuất / nhập Excel (giám sát = gs_benchmark, NVBH + ASM = benchmark)
    get isBenchmarkNav() {
        return ["benchmark", "gs_benchmark", "nvbh_task"].includes(this.state.activeNav);
    }

    // model + tham số của hàm export_xlsx / import_xlsx (Công việc NVBH không có scope)
    get excelModel() {
        if (this.state.activeNav === "nvbh_schedule") {
            return "store.nvbh.schedule.line";
        }
        return this.state.activeNav === "nvbh_task" ? "store.nvbh.task" : "store.audit.template.line";
    }

    excelArgs(extra = []) {
        if (this.state.activeNav === "nvbh_schedule") {
            // xuất theo bộ lọc đang chọn (tháng / cửa hàng / miền); nhập chỉ gửi file
            const month = this.state.listFilters.month;
            return extra.length ? [...extra, month] : [this.listDomain(this.listBase || []), month];
        }
        return this.state.activeNav === "nvbh_task" ? extra : [this.benchmarkScope, ...extra];
    }

    get isScheduleNav() {
        return this.state.activeNav === "nvbh_schedule";
    }

    get canImportSchedule() {
        return !this.state.rights || Boolean(this.state.rights.nvbh?.create);
    }

    get canExportSchedule() {
        return !this.state.rights || Boolean(this.state.rights.nvbh?.export);
    }

    get benchmarkScope() {
        return this.state.activeNav === "gs_benchmark" ? "gs" : "other";
    }

    async onExportBenchmark() {
        try {
            const file = await this.orm.call(this.excelModel, "export_xlsx", this.excelArgs());
            const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
            link.download = file.name;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            this.notifyError(error);
        }
    }

    onImportBenchmark() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".xlsx";
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) {
                return;
            }
            try {
                const bytes = new Uint8Array(await file.arrayBuffer());
                let bin = "";
                for (let i = 0; i < bytes.length; i += 0x8000) {
                    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                }
                const res = await this.orm.call(this.excelModel, "import_xlsx", this.excelArgs([btoa(bin)]));
                const warn = res.error_count ? ` · ${res.error_count} dòng lỗi: ${res.errors.slice(0, 3).join("; ")}${res.error_count > 3 ? "…" : ""}` : "";
                this.notification.add(`Đã nhập lịch ca: thêm ${res.created}, cập nhật ${res.updated}${res.removed ? `, xóa ${res.removed} ca không còn trong file` : ""} · Nhân sự: thêm ${res.staff_created || 0}, cập nhật ${res.staff_updated || 0}${warn}`, { type: res.error_count ? "warning" : "success", sticky: Boolean(res.error_count) });
                this.state.viewKey += 1;
                if (this.isScheduleNav) {
                    await this.loadSchedule();
                }
            } catch (error) {
                this.notifyError(error);
            }
        };
        input.click();
    }

    // Danh mục ca làm việc (Cài đặt > Mã ca): tab theo loại ca
    get shiftTabs() {
        return [
            { id: "morning", label: "SÁNG" },
            { id: "afternoon", label: "CHIỀU" },
            { id: "full", label: "FULL" },
            { id: "split_am", label: "GÃY SÁNG" },
            { id: "split_pm", label: "GÃY CHIỀU" },
        ];
    }

    shiftDomain() {
        return [...(this.listBase || []), ["shift_type", "=", this.state.shiftTab]];
    }

    async loadShiftStats() {
        try {
            const rows = await this.orm.searchRead("store.shift", [], ["shift_type"]);
            this.state.shiftStats = { total: rows.length, types: new Set(rows.map((r) => r.shift_type)).size };
        } catch {
            this.state.shiftStats = { total: 0, types: 0 };
        }
    }

    onShiftTab(tab) {
        this.state.shiftTab = tab.id;
        this.state.embeddedViewProps = { ...this.state.embeddedViewProps, domain: this.shiftDomain() };
        this.state.viewKey += 1;
        this.loadShiftStats();
    }

    // Mục con Nhân sự dùng quyền của Checklist NVBH
    get permKey() {
        return ["nvbh_staff", "nvbh_jobs", "nvbh_schedule", "nvbh_done", "nvbh_mg_staff", "nvbh_mg_eval"].includes(this.state.activeNav) ? "nvbh" : this.state.activeNav;
    }

    get canExport() {
        return !["report_flow", "nvbh_staff", "nvbh_jobs", "nvbh_schedule", "nvbh_done", "nvbh_mg_staff", "nvbh_mg_eval"].includes(this.state.activeNav) && (!this.state.rights || Boolean(this.state.rights[this.permKey]?.export));
    }

    get showListFilters() {
        return this.filterNavs.includes(this.state.activeNav);
    }

    get shellMode() {
        return this.state.contentMode === "list" ? "dashboard" : this.state.contentMode;
    }

    listDomain(base, monthOverride) {
        const { mien, store, auditor } = this.state.listFilters;
        const month = monthOverride === undefined ? this.state.listFilters.month : monthOverride;
        const domain = [...base];
        if (auditor) {
            domain.push(["auditor_id", "=", Number(auditor)]);
        }
        if (month && ["nvbh_jobs", "nvbh_schedule", "nvbh_done"].includes(this.state.activeNav)) {
            const [y, m] = month.split("-").map(Number);
            const ymd = (yy, mm) => `${yy}-${String(mm).padStart(2, "0")}-01`;
            domain.push(["work_date", ">=", ymd(y, m)], ["work_date", "<", m === 12 ? ymd(y + 1, 1) : ymd(y, m + 1)]);
        } else if (month) {
            const [y, m] = month.split("-").map(Number);
            const fmt = (d) => d.toISOString().slice(0, 19).replace("T", " ");
            domain.push(["audit_date", ">=", fmt(new Date(y, m - 1, 1))], ["audit_date", "<", fmt(new Date(y, m, 1))]);
        }
        if (store) {
            domain.push(["store_id", "=", Number(store)]);
        }
        if (mien === "other") {
            domain.push("|", ["mien", "=", false], ["mien", "not in", ["Nam", "ĐTT", "Bắc"]]);
        } else if (mien) {
            domain.push(["mien", "=", mien]);
        }
        return domain;
    }

    get listTitle() {
        return {
            gs: "DANH SÁCH CHECK LIST GIÁM SÁT CỬA HÀNG",
            nvbh_staff: "DANH SÁCH NHÂN SỰ",
            nvbh_jobs: "CHECKLIST CÔNG VIỆC NVBH",
            nvbh_schedule: "LỊCH XẾP CA",
            nvbh_done: this.state.done.tab === "total" ? "BẢNG CHECKLIST TỔNG" : "DANH SÁCH CHECKLIST NHÂN VIÊN",
            nvbh_mg_staff: "QUẢN LÝ & ĐÁNH GIÁ CHECKLIST NVBH",
            nvbh_mg_eval: "QUẢN LÝ & ĐÁNH GIÁ CHECKLIST NVBH",
            review: "DANH SÁCH PHIẾU ĐÁNH GIÁ CỬA HÀNG",
            report_gs: "BÁO CÁO GIÁM SÁT CỬA HÀNG",
            violation_stores: "XỬ LÝ LỖI SAI PHẠM CỬA HÀNG",
            violation_all: "DANH SÁCH XỬ LÝ SAI PHẠM",
            report_rank: "Báo cáo xếp loại",
            report_manager: "BÁO CÁO THEO QUẢN LÝ",
            report_sup: "BÁO CÁO GIÁM SÁT",
            report_flow: "SƠ ĐỒ QUY TRÌNH VẬN HÀNH GIÁM SÁT",
        }[this.state.activeNav] || "";
    }

    // In trang báo cáo (thẻ số liệu, biểu đồ, bảng): sao chép vùng báo cáo + CSS của trang vào iframe, biểu đồ canvas đổi thành ảnh.
    printReport() {
        const wrap = document.querySelector(".o_store_list_wrap");
        if (!wrap) {
            return;
        }
        const clone = wrap.cloneNode(true);
        const src = wrap.querySelectorAll("canvas");
        clone.querySelectorAll("canvas").forEach((cv, i) => {
            const img = document.createElement("img");
            try {
                img.src = src[i].toDataURL("image/png");
            } catch {
                return;
            }
            img.style.cssText = `width:${src[i].clientWidth}px;height:${src[i].clientHeight}px`;
            cv.replaceWith(img);
        });
        clone.querySelectorAll(".o_store_list_filters, .o_store_export_btn, .o_store_print_btn").forEach((e) => e.remove());
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${this.listTitle || "Báo cáo"}</title><style>
            @page { size: A4 landscape; margin: 8mm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { background: #fff; } .o_store_list_wrap { overflow: visible !important; height: auto !important; max-height: none !important; }
        </style></head><body></body></html>`);
        let pending = 0;
        let started = false;
        const go = () => {
            if (started) { return; }
            started = true;
            frame.contentWindow.focus();
            frame.contentWindow.print();
            setTimeout(() => frame.remove(), 60000);
        };
        document.querySelectorAll('link[rel="stylesheet"]').forEach((l) => {
            const n = doc.createElement("link");
            n.rel = "stylesheet";
            n.href = l.href;
            pending++;
            n.onload = n.onerror = () => { if (!--pending) { go(); } };
            doc.head.appendChild(n);
        });
        doc.body.appendChild(doc.importNode(clone, true));
        doc.close();
        setTimeout(go, 4000); // phòng khi CSS tải chậm
    }

    // In danh sách đang xem: dựng trang riêng (tiêu đề + bảng) trong iframe rồi mở hộp thoại in để chọn máy in.
    // shortcut: dựng từ DOM đang hiển thị (đúng bộ lọc / trang hiện tại), chưa in im lặng thẳng ra một máy in cố định.
    async printList() {
        let table = document.querySelector(".o_store_list_wrap table.o_list_table");
        if (!table) {
            return this.printReport();
        }
        // có dòng được tích thì chỉ in các dòng đó; nếu không thì mở hết các nhóm đang thu gọn để bảng in có đủ dòng
        const ticked = (tr) => tr.querySelector(".o_list_record_selector input:checked");
        const anyTicked = [...table.querySelectorAll("tr.o_data_row")].some(ticked);
        const closed = anyTicked ? [] : [...table.querySelectorAll("tr.o_group_header:not(.o_group_open)")];
        if (closed.length) {
            closed.forEach((tr) => (tr.querySelector("th") || tr).click());
            await new Promise((r) => setTimeout(r, 1200));
            table = document.querySelector(".o_store_list_wrap table.o_list_table") || table;
        }
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${this.listTitle || "Danh sách"}</title><style>
            @page { size: A4 landscape; margin: 8mm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: Arial, sans-serif; font-size: 11px; color: #111; }
            h2 { margin: 0 0 8px; font-size: 18px; color: #12285f; }
            table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #64748b; padding: 4px 6px; }
            th { background: #1e3a6e; color: #fff; text-align: center; } tr.grp td { background: #dce6f2; font-weight: 700; color: #1e3a8a; }
            td.n { text-align: center; }
        </style></head><body></body></html>`);
        doc.close();
        const el = (tag, cls, text) => {
            const e = doc.createElement(tag);
            if (cls) { e.className = cls; }
            if (text !== undefined) { e.textContent = text; }
            return e;
        };
        const out = el("table");
        const head = el("tr");
        const heads = [...table.querySelectorAll("thead th")].filter((th) => th.dataset.name);
        heads.forEach((th) => head.appendChild(el("th", "", th.innerText.trim())));
        out.appendChild(head);
        let pendingGroup = null;
        table.querySelectorAll("tbody tr").forEach((tr) => {
            const row = el("tr");
            if (tr.classList.contains("o_group_header")) {
                row.className = "grp";
                const td = el("td", "", tr.innerText.trim());
                td.colSpan = heads.length;
                row.appendChild(td);
                if (anyTicked) {
                    pendingGroup = row; // nhóm chỉ in khi có dòng đã tích bên trong
                    return;
                }
            } else if (tr.classList.contains("o_data_row")) {
                if (anyTicked && !ticked(tr)) {
                    return;
                }
                if (pendingGroup) {
                    out.appendChild(pendingGroup);
                    pendingGroup = null;
                }
                tr.querySelectorAll("td[name]").forEach((td) => row.appendChild(el("td", "n", td.innerText.trim())));
            } else {
                return;
            }
            out.appendChild(row);
        });
        doc.body.append(el("h2", "", this.listTitle || "Danh sách"), out);
        frame.contentWindow.focus();
        frame.contentWindow.print();
        setTimeout(() => frame.remove(), 60000);
    }

    // Danh sách xử lý sai phạm: bấm Xuất Excel / In thì hỏi chọn cửa hàng trước (các cửa hàng đang có trong danh sách)
    async pickStores(confirmLabel, onConfirm) {
        const domain = this.state.embeddedViewProps?.domain || [];
        const groups = await this.orm.formattedReadGroup("store.audit.action", [...domain, ["line_id.error_count", ">", 0]], ["store_id"], ["__count"]);
        const stores = groups
            .filter((g) => g.store_id)
            .map((g) => ({ id: g.store_id[0], name: g.store_id[1], count: g.__count || 0 }));
        if (!stores.length) {
            this.notification.add("Không có cửa hàng nào để chọn", { type: "warning" });
            return;
        }
        this.dialog.add(StoreViolPickDialog, { title: confirmLabel + " danh sách xử lý sai phạm", confirmLabel, stores, onConfirm });
    }

    // Lỗi khi xuất / in được báo ra thông báo (không im lặng)
    async onExport() {
        try {
            if (this.state.activeNav === "violation_all") {
                return await this.pickStores("Xuất Excel", (ids) => this.exportExcel(ids).catch((e) => this.notifyError(e)));
            }
            return await this.exportExcel();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async onPrint() {
        try {
            if (this.state.activeNav === "violation_all") {
                return await this.pickStores("In", (ids) => this.printViolationAll(ids).catch((e) => this.notifyError(e)));
            }
            return await this.printList();
        } catch (error) {
            this.notifyError(error);
        }
    }

    // In danh sách xử lý sai phạm của các cửa hàng đã chọn: dữ liệu lấy từ máy chủ (không phụ thuộc nhóm đang mở)
    async printViolationAll(storeIds) {
        const domain = [...(this.state.embeddedViewProps?.domain || []), ["store_id", "in", storeIds]];
        const data = await this.orm.call("store.audit.action", "violation_all_print_data", [domain]);
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Danh sách xử lý sai phạm</title><style>
            @page { size: A4 landscape; margin: 8mm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: Arial, sans-serif; font-size: 10px; color: #111; }
            h2 { margin: 0 0 8px; font-size: 18px; color: #12285f; }
            table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #64748b; padding: 3px 4px; vertical-align: top; }
            th { background: #1e3a6e; color: #fff; text-align: center; } th.g1 { background: #15803d; } th.g2 { background: #c2410c; }
            td.g2 { background: #fff1e0; } tr.grp td { background: #dce6f2; font-weight: 700; color: #1e3a8a; } td.n { text-align: center; }
            td img { width: 70px; height: auto; } tr { page-break-inside: avoid; }
        </style></head><body></body></html>`);
        doc.close();
        const el = (tag, cls, text) => {
            const e = doc.createElement(tag);
            if (cls) { e.className = cls; }
            if (text !== undefined) { e.textContent = text; }
            return e;
        };
        const table = el("table");
        const head = el("tr");
        data.headers.forEach(([name, grp]) => head.appendChild(el("th", grp ? `g${grp}` : "", name)));
        table.appendChild(head);
        data.groups.forEach((g) => {
            const gr = el("tr", "grp");
            const gt = el("td", "", g.title);
            gt.colSpan = data.headers.length;
            gr.appendChild(gt);
            table.appendChild(gr);
            g.rows.forEach((r) => {
                const tr = el("tr");
                r.cells.forEach((v, i) => {
                    const grp = data.headers[i][1];
                    const td = el("td", ([0, 3, 4, 7, 12, 13].includes(i) ? "n " : "") + (grp === 2 ? "g2" : ""), i === 6 ? "" : String(v));
                    if (i === 6 && r.photo) {
                        const img = doc.createElement("img");
                        img.src = `/web/image/${r.photo}`;
                        td.appendChild(img);
                    }
                    tr.appendChild(td);
                });
                table.appendChild(tr);
            });
        });
        doc.body.append(el("h2", "", "DANH SÁCH XỬ LÝ SAI PHẠM"), table);
        const imgs = [...doc.images];
        await Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
        frame.contentWindow.focus();
        frame.contentWindow.print();
        setTimeout(() => frame.remove(), 60000);
    }

    // Kết xuất Excel đúng theo bộ lọc tháng / cửa hàng / miền đang chọn
    async exportExcel(storeIds) {
        let domain = this.reportNavs.includes(this.state.activeNav)
            ? this.listDomain(this.reportBase)
            : this.state.embeddedViewProps?.domain || [];
        if (this.isPersonal) {
            domain = this.listDomain([["audit_type", "=", "gs"], ["auditor_id", "=", user.userId]]);
        }
        if (Array.isArray(storeIds)) {
            domain = [...domain, ["store_id", "in", storeIds]];
        }
        const file = this.state.activeNav === "violation_all"
            ? await this.orm.call("store.audit.action", "export_violation_all_xlsx", [domain])
            : this.state.activeNav === "report_manager"
            ? await this.orm.call("store.audit", "export_manager_xlsx", [this.listDomain([["state", "!=", "draft"]])])
            : this.state.activeNav === "report_rank"
            ? await this.orm.call("store.audit", "export_rank_xlsx", [domain])
            : await this.orm.call("store.audit", "export_list_xlsx", [domain], {
                  title: this.listTitle || "DANH SÁCH PHIẾU ĐÁNH GIÁ",
              });
        const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = file.name;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    get reportBase() {
        const base = [["audit_type", "=", "gs"], ["state", "!=", "draft"]];
        // người dùng giám sát thường chỉ xem phiếu do chính mình đánh giá
        return this.isPersonal ? [...base, ["auditor_id", "=", user.userId]] : base;
    }

    // Báo cáo GS (người xem toàn bộ) dùng giao diện "Báo cáo giám sát" theo mẫu
    get isSupLayout() {
        return ["report_sup", "report_gs"].includes(this.state.activeNav);
    }

    // Phiếu đang mở trong khung chính (bấm Xem): phiếu có tiêu đề riêng nên ẩn banner danh sách phía trên cho khỏi trùng
    get isFormOpen() {
        return this.state.embeddedViewProps?.type === "form";
    }

    get isPersonal() {
        // Báo cáo GS: chỉ người có chức danh Giám sát thấy báo cáo cá nhân (lọc theo người đánh giá); người khác thấy toàn bộ
        return this.state.activeNav === "report_gs" && !this.state.isManager && this.state.isSupervisor;
    }

    toneColor(tone) {
        return { green: "#16a34a", blue: "#2563eb", orange: "#f59e0b", red: "#dc2626", darkred: "#7f1d1d" }[tone] || "#94a3b8";
    }

    get personalDiff() {
        const p = this.state.personal;
        const d = Math.round(Math.abs(p.avg - p.chain_avg) * 10) / 10;
        return `${p.avg < p.chain_avg ? "Thấp hơn" : "Cao hơn"} ${d}% so với trung bình chuỗi`;
    }

    // Phiếu giám sát đã chốt (không còn nháp) của người dùng trong tháng
    get personalDone() {
        return this.state.personal.rows.filter((r) => !r.draft);
    }

    get personalStoreCount() {
        return new Set(this.personalDone.map((r) => r.store)).size;
    }

    levelAvg(lv) {
        return Math.round((10 * lv.rows.reduce((a, r) => a + r.rate, 0)) / lv.rows.length) / 10;
    }

    levelPassed(lv) {
        return lv.rows.filter((r) => r.passed).length;
    }

    personalDonut() {
        return this.donutFrom(this.state.personal.levels);
    }

    reportDonut() {
        return this.donutFrom(this.state.report.levels.filter((l) => l.count));
    }

    get reportTitle() {
        const m = this.state.listFilters.month;
        return "DASHBOARD QUẢN TRỊ & HOẠT ĐỘNG GIÁM SÁT" + (m ? ` THÁNG ${m.slice(5)}/${m.slice(0, 4)}` : "");
    }

    get reportSubtitle() {
        const f = this.state.listFilters;
        const mien = { Nam: "Miền Nam", "ĐTT": "Miền ĐTT", "Bắc": "Miền Bắc", other: "Khác" }[f.mien] || "Tất cả miền";
        const au = this.state.report?.auditor_options.find((a) => String(a.id) === f.auditor);
        return [f.month ? `Tháng ${f.month.slice(5)}/${f.month.slice(0, 4)}` : "Tất cả tháng", mien, au ? au.name : "Tất cả giám sát"].join(" | ");
    }

    get reportDiff() {
        const r = this.state.report;
        if (r.prev_avg === null) {
            return "Chưa có dữ liệu tháng trước";
        }
        const d = Math.round((r.avg - r.prev_avg) * 10) / 10;
        return `${d > 0 ? "+" : ""}${d}% so với tháng trước`;
    }

    // Cột: số phiếu mỗi giám sát (trục trái); đường cam: điểm TB % (trục phải 0-100)
    reportCombo() {
        const rows = this.state.report.rows;
        const max = Math.max(4, ...rows.map((r) => r.audited));
        const step = Math.ceil(max / 4), top = step * 4;
        const W = 560, H = 240, L = 34, R = 40, B = 46, T = 16;
        const slot = (W - L - R) / Math.max(rows.length, 1);
        const y = (v, t) => T + (H - T - B) * (1 - v / t);
        return {
            W, H, R, ticks: [0, 1, 2, 3, 4].map((i) => ({ y: y(i * step, top), left: i * step, right: i * 25 })),
            bars: rows.map((r, i) => ({
                id: r.id, x: L + slot * i + slot * 0.2, w: slot * 0.6, y: y(r.audited, top), h: (H - T - B) * (r.audited / top),
                cx: L + slot * (i + 0.5), cy: y(r.avg, 100), value: r.audited, avg: r.avg,
                label: r.name.length > 14 ? r.name.slice(0, 13) + "…" : r.name,
            })),
            line: rows.map((r, i) => `${i ? "L" : "M"}${L + slot * (i + 0.5)},${y(r.avg, 100)}`).join(" "),
        };
    }

    statusColor(tone) {
        return { green: "#16a34a", yellow: "#f59e0b", orange: "#ea580c", red: "#dc2626", gray: "#94a3b8" }[tone] || "#94a3b8";
    }

    donutFrom(items, base) {
        const total = base || items.reduce((a, i) => a + i.count, 0);
        const R = 62, C = 2 * Math.PI * R;
        let offset = 0;
        return {
            R, total,
            segments: items.map((it) => {
                const len = (it.count / total) * C;
                const mid = ((offset + len / 2) / C) * 2 * Math.PI - Math.PI / 2;
                const seg = { dash: `${len} ${C - len}`, offset: -offset, color: it.color || this.toneColor(it.tone), name: it.name,
                    value: it.count, pct: Math.round((100 * it.count) / total), tx: 80 + R * Math.cos(mid), ty: 84 + R * Math.sin(mid) };
                offset += len;
                return seg;
            }),
        };
    }

    // Cột: số phiếu mỗi tuần; đường cam: mức trung bình kế hoạch / tuần
    personalBars() {
        const p = this.state.personal;
        const target = p.plan / 4;
        const max = Math.max(4, ...p.weeks, Math.ceil(target));
        const step = Math.ceil(max / 4), top = step * 4;
        const W = 360, H = 190, L = 30, B = 26, T = 14;
        const slot = (W - L) / 4;
        const y = (v) => T + (H - T - B) * (1 - v / top);
        return {
            W, H, ly: y(target),
            ticks: [0, 1, 2, 3, 4].map((i) => ({ y: y(i * step), label: i * step })),
            bars: p.weeks.map((v, i) => ({ x: L + slot * i + slot * 0.2, w: slot * 0.6, y: y(v), h: (H - T - B) * (v / top), value: v, label: `Tuần ${i + 1}`, cx: L + slot * (i + 0.5) })),
        };
    }

    toneBg(tone) {
        return { green: "#dcfce7", blue: "#dbeafe", orange: "#fef3c7", red: "#fee2e2", darkred: "#fecaca" }[tone] || "#f1f5f9";
    }

    storeDonut() {
        return this.donutFrom(this.state.storeReport.levels.filter((l) => l.count));
    }

    // Cột chồng: số cửa hàng theo xếp loại của từng miền
    storeStacked() {
        const rep = this.state.storeReport;
        const totals = rep.by_mien.map((m) => m.counts.reduce((a, b) => a + b, 0));
        const max = Math.max(4, ...totals);
        const step = Math.ceil(max / 4), top = step * 4;
        const W = 560, H = 250, L = 44, B = 30, T = 12;
        const slot = (W - L) / Math.max(rep.by_mien.length, 1);
        const y = (v) => T + (H - T - B) * (1 - v / top);
        return {
            W, H,
            ticks: [0, 1, 2, 3, 4].map((i) => ({ y: y(i * step), label: `${i * step} CH` })),
            cols: rep.by_mien.map((m, i) => {
                let acc = 0;
                return {
                    label: m.label, cx: L + slot * (i + 0.5),
                    segs: m.counts.map((n, k) => {
                        const w = Math.min(slot * 0.6, 70); // giới hạn bề rộng cột khi chỉ có ít miền
                        const seg = { x: L + slot * (i + 0.5) - w / 2, w, y: y(acc + n), h: (H - T - B) * (n / top), n,
                            color: this.toneColor(rep.levels[k].tone), key: k };
                        acc += n;
                        return seg;
                    }),
                };
            }),
        };
    }

    // màu từng xếp loại lấy từ "Màu hiển thị" của bảng Xếp loại trong Cài đặt
    rankColor(i) {
        return this.toneColor(this.state.rankStore.levels[i].tone);
    }

    rankLevelColor(name) {
        const i = this.state.rankStore.levels.findIndex((l) => l.name === name);
        return i < 0 ? "#94a3b8" : this.rankColor(i);
    }

    rankIcon(tone) {
        return { green: "fa-star", blue: "fa-trophy", orange: "fa-bar-chart", red: "fa-times", darkred: "fa-times" }[tone] || "fa-circle";
    }

    rankDonut() {
        // Đủ mọi xếp loại trong bảng Xếp loại (kể cả 0 cửa hàng); tỷ lệ = số cửa hàng / tổng cửa hàng trong hồ sơ
        const items = this.state.rankStore.levels.map((l, i) => ({ ...l, color: this.rankColor(i) }));
        const sum = items.reduce((a, l) => a + l.count, 0);
        return this.donutFrom(items, Math.max(this.state.rankStoreTotal, sum));
    }

    // Cột nhóm: mỗi miền một cụm, mỗi xếp loại một cột
    rankGrouped() {
        const { levels, by_mien: groups } = this.state.rankStore;
        const max = Math.max(4, ...groups.flatMap((g) => g.counts));
        const step = Math.ceil(max / 4), top = step * 4;
        const W = 560, H = 250, L = 36, B = 30, T = 16;
        const slot = (W - L) / Math.max(groups.length, 1);
        const bw = Math.min((slot * 0.8) / levels.length, 36);
        const y = (v) => T + (H - T - B) * (1 - v / top);
        return {
            W, H, ticks: [0, 1, 2, 3, 4].map((i) => ({ y: y(i * step), label: i * step })),
            groups: groups.map((g, i) => {
                const cx = L + slot * (i + 0.5);
                return {
                    label: /^(Miền|Khác)/.test(g.label) ? g.label : `Miền ${g.label}`, cx,
                    bars: g.counts.map((n, k) => ({
                        k, n, x: cx - (bw * levels.length) / 2 + bw * k, w: bw - 4, y: y(n),
                        h: (H - T - B) * (n / top), color: this.rankColor(k),
                    })),
                };
            }),
        };
    }

    async loadStoreReport() {
        this.state.storeReport = await this.orm.call("store.audit", "get_report_store", [this.listDomain(this.reportBase)]);
    }

    async loadReport() {
        if (this.state.activeNav === "report_rank") {
            const domain = this.listDomain(this.reportBase);
            // Tổng cửa hàng = số cửa hàng trong hồ sơ nhân viên / cửa hàng (hr.store), theo bộ lọc miền
            const mien = this.state.listFilters.mien;
            const storeDomain = mien === "other"
                ? ["|", ["mien", "=", false], ["mien", "not in", ["Nam", "ĐTT", "Bắc"]]]
                : mien ? [["mien", "=", mien]] : [];
            [this.state.rankReport, this.state.rankStore, this.state.rankStoreTotal] = await Promise.all([
                this.orm.call("store.audit", "get_report_rank", [domain]),
                this.orm.call("store.audit", "get_report_store", [domain]),
                this.orm.searchCount("hr.store", storeDomain),
            ]);
            return;
        }
        if (["report_manager", "report_flow"].includes(this.state.activeNav)) {
            // cả phiếu GS lẫn ASM (không dùng reportBase chỉ có GS); kèm tháng trước để tính chênh lệch
            const month = this.state.listFilters.month;
            const base = [["state", "!=", "draft"]];
            let prev = false;
            if (month) {
                const [y, m] = month.split("-").map(Number);
                prev = this.listDomain(base, `${m === 1 ? y - 1 : y}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}`);
            }
            this.state.mgrPage = 0;
            this.state.mgrLevels = await this.orm.searchRead("store.audit.level", [["audit_type", "=", "gs"]], ["name", "tone", "score_range"], { order: "min_score desc" });
            this.state.managerReport = await this.orm.call("store.audit", "get_report_manager", [this.listDomain(base), prev]);
            if (this.state.activeNav === "report_flow") {
                this.state.flowStats = await this.orm.call("store.audit", "get_flow_stats", [this.listDomain(base)]);
            }
            return;
        }
        if (this.state.activeNav === "report_store") {
            return this.loadStoreReport();
        }
        const month = this.state.listFilters.month;
        let prev = false;
        if (month) {
            const [y, m] = month.split("-").map(Number);
            prev = this.listDomain(this.reportBase, `${m === 1 ? y - 1 : y}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}`);
        }
        if (this.isSupLayout && !this.state.supStores.length) {
            try {
                this.state.supStores = (await this.orm.call("store.nvbh.check", "get_my_stores", [])).map((s) => ({ id: s.id, name: s.display_name }));
            } catch {
                this.state.supStores = []; // user không đọc được danh sách cửa hàng: bỏ qua bộ lọc cửa hàng
            }
        }
        this.state.report = await this.orm.call("store.audit", "get_report_gs", [this.listDomain(this.reportBase), prev]);
    }

    // Báo cáo theo quản lý: lọc quản lý, thẻ số liệu và phân trang tính trên dữ liệu đã tải
    get mgrView() {
        const all = this.state.managerReport || [];
        const rows = this.state.mgrFilter ? all.filter((r) => String(r.id) === this.state.mgrFilter) : all;
        const size = 10;
        // Đạt KPI >= 80, Cần cải thiện 60-79, Không đạt < 60 (điểm TB của quản lý)
        // Xếp loại + màu lấy từ bảng Mức đánh giá (GS); chưa tải được thì dùng ngưỡng mặc định
        const lvls = this.state.mgrLevels;
        const kinds = lvls.length
            ? lvls.map((l) => ({ key: l.name, name: l.name, hint: `(${l.score_range})`, color: this.toneColor(l.tone), test: (v, r) => r.level === l.name }))
            : [
                { key: "ok", name: "Đạt KPI", hint: "(≥ 80%)", color: "#3b82f6", test: (v) => v >= 80 },
                { key: "mid", name: "Cần cải thiện", hint: "(60% – 79%)", color: "#f59e0b", test: (v) => v >= 60 && v < 80 },
                { key: "bad", name: "Không đạt", hint: "(< 60%)", color: "#ef4444", test: (v) => v < 60 },
            ];
        const split = (list) => {
            const total = list.length;
            return kinds.map((k) => {
                const count = list.filter((r) => k.test(r.avg, r)).length;
                return { ...k, count, pct: total ? ((100 * count) / total).toFixed(1) : "0.0" };
            });
        };
        const donut = (list) => {
            const parts = split(list);
            return { parts, d: this.donutFrom(parts.filter((p) => p.count), list.length || 1), ok: parts[0].pct };
        };
        const regions = [["Nam", "Miền Nam"], ["ĐTT", "Miền ĐTT"], ["Bắc", "Miền Bắc"]]
            .map(([key, label]) => ({ label, ...donut(rows.filter((r) => r.mien === key)), n: rows.filter((r) => r.mien === key).length }))
            .filter((g) => g.n);
        const sorted = [...rows].sort((a, b) => b.avg - a.avg);
        // Phân bố theo khu vực: số quản lý đạt (điểm TB >= 80) / tổng quản lý của khu vực
        const known = ["Nam", "ĐTT", "Bắc"];
        const areas = [["Nam", "Miền Nam", "#3b82f6"], ["ĐTT", "Miền ĐTT", "#fbbf24"], ["Bắc", "Miền Bắc", "#34d399"]]
            .map(([key, label, color]) => ({ label, color, list: rows.filter((r) => r.mien === key) }));
        const other = rows.filter((r) => !known.includes(r.mien));
        if (other.length) {
            areas.push({ label: "Khác", color: "#8b5cf6", list: other });
        }
        const areaList = areas.map((a) => {
            const ok = a.list.filter((r) => r.avg >= 80).length;
            return { label: a.label, color: a.color, ok, n: a.list.length, pct: a.list.length ? Math.round((100 * ok) / a.list.length) : 0 };
        });
        const deltas = rows.map((r) => r.delta).filter((d) => d !== null && d !== undefined);
        const mean = (xs) => (xs.length ? Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10 : 0);
        return {
            areas: areaList, top: sorted.slice(0, 3), avg: mean(rows.map((r) => r.avg)), delta: deltas.length ? mean(deltas) : null,
            needN: rows.filter((r) => r.avg < 80).length,
            bars: sorted.slice(0, 20).map((r) => ({ id: r.id, name: r.name, avg: r.avg, color: this.toneColor(r.tone), level: r.level, errors: r.errors, errColor: r.errors > 0 ? "#ef4444" : "#16a34a" })),
            kinds: split(rows), all: donut(rows), regions,
            rows, size, pages: Math.max(1, Math.ceil(rows.length / size)),
            page: rows.slice(this.state.mgrPage * size, (this.state.mgrPage + 1) * size),
        };
    }

    // Báo cáo giám sát: mọi tổng là công thức cộng từ dữ liệu get_report_gs (state.report), tự đổi theo bộ lọc
    get supView() {
        const r = this.state.report;
        const levels = r.levels;
        const done = r.rows.filter((x) => x.done).sort((a, b) => b.done - a.done);
        // phiếu mới nhất của mỗi cửa hàng (r.stores đã xếp mới → cũ)
        const latest = new Map();
        r.stores.forEach((s) => latest.has(s.store) || latest.set(s.store, s));
        const good = levels.find((l) => l.name.toLowerCase() === "tốt");
        const axis = (max) => {
            const raw = Math.max(1, Math.ceil(max / 4));
            const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000].find((s) => s >= raw) || raw;
            return { top: step * 4, ticks: [0, 1, 2, 3, 4].map((i) => i * step) };
        };
        const ax = axis(Math.max(1, ...done.map((x) => x.done)));
        const q = (this.state.supQ || "").trim().toLowerCase();
        const list = r.stores.filter((s) => !q || `${s.store} ${s.auditor}`.toLowerCase().includes(q));
        const size = 10;
        const pages = Math.max(1, Math.ceil(list.length / size));
        const page = Math.min(this.state.supPage, pages - 1);
        return {
            kpi: { stores: latest.size, auditors: done.length, avg: r.avg, good: good ? [...latest.values()].filter((s) => s.level === good.name).length : 0 },
            ticks: ax.ticks,
            bars: done.map((x) => ({ id: x.id, name: x.name, n: x.done, pct: (100 * x.done) / ax.top })),
            legend: levels.map((l) => ({ name: l.name, color: this.toneColor(l.tone) })),
            stacks: done.map((x) => ({
                id: x.id, name: x.name, total: x.by_level.reduce((a, b) => a + b, 0),
                segs: x.by_level.map((n, i) => ({ n, color: this.toneColor(levels[i].tone), name: levels[i].name })).filter((s) => s.n),
            })).map((s, _i, all) => ({ ...s, pct: (100 * s.total) / Math.max(1, ...all.map((a) => a.total)) })),
            rows: list.slice(page * size, (page + 1) * size).map((s, i) => ({ ...s, no: page * size + i + 1 })),
            total: list.length, from: list.length ? page * size + 1 : 0, to: Math.min(list.length, (page + 1) * size),
            page, pages,
            // số trang gần trang hiện tại + trang đầu/cuối; -1 = dấu "…"
            nums: Array.from({ length: pages }, (_, i) => i).filter((i) => i === 0 || i === pages - 1 || Math.abs(i - page) <= 1)
                .flatMap((i, k, a) => (k && i - a[k - 1] > 1 ? [-1, i] : [i])),
        };
    }

    onSupSearch(ev) {
        this.state.supQ = ev.target.value;
        this.state.supPage = 0;
    }

    levelTone(name) {
        return this.state.report?.levels.find((l) => l.name === name)?.tone || "orange";
    }

    showMgr(row) {
        this.dialog.add(StoreMgrDetailDialog, {
            row,
            domain: this.listDomain([["state", "!=", "draft"]]),
            onView: (id) => this.action.doAction({ type: "ir.actions.act_window", res_model: "store.audit", res_id: id, views: [[false, "form"]], target: "new" }),
        });
    }

    onMgrFilter(ev) {
        this.state.mgrFilter = ev.target.value;
        this.state.mgrPage = 0;
    }

    toggleReportRow(id) {
        this.state.reportOpen[id] = !this.state.reportOpen[id];
    }

    onListFilter(key, ev) {
        this.state.listFilters[key] = ev.target.value;
        if (this.reportNavs.includes(this.state.activeNav)) {
            return this.loadReport();
        }
        if (this.isScheduleNav) {
            return this.loadSchedule();
        }
        const props = this.state.embeddedViewProps;
        this.state.embeddedViewProps = { ...props, domain: this.listDomain(this.listBase) };
        this.state.viewKey += 1;
    }

    onFilter(key, ev) {
        this.state.filters[key] = ev.target.value;
        this.loadOverview();
    }

    get monthOptions() {
        const now = new Date();
        return Array.from({ length: 12 }, (_, i) => {
            const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
            const mm = String(d.getMonth() + 1).padStart(2, "0");
            return { value: `${d.getFullYear()}-${mm}`, label: `Tháng ${mm}/${d.getFullYear()}` };
        });
    }

    get todoRows() {
        return this.state.dash?.todo_rows || [];
    }

    get doneRows() {
        return this.state.dash?.done_rows || [];
    }

    miencolor(key) {
        return { Nam: "#2f80ed", "ĐTT": "#27ae60", "Bắc": "#7c4dff" }[key] || "#94a3b8";
    }

    // Biểu đồ cột SVG: items = by_mien, field = "total" | "todo"
    barData(field) {
        const items = this.state.dash?.by_mien || [];
        const max = Math.max(4, ...items.map((i) => i[field]));
        const step = Math.ceil(max / 4);
        const top = step * 4;
        const W = 320, H = 190, L = 30, B = 26, T = 14;
        const slot = (W - L) / Math.max(items.length, 1);
        return {
            W, H,
            ticks: [0, 1, 2, 3, 4].map((i) => ({ y: T + (H - T - B) * (1 - i / 4), label: i * step })),
            bars: items.map((it, i) => {
                const h = (H - T - B) * (it[field] / top);
                return {
                    x: L + slot * i + slot * 0.2, w: slot * 0.6, y: H - B - h, h,
                    value: it[field], label: it.label, color: this.miencolor(it.key),
                };
            }),
        };
    }

    // Biểu đồ vành khuyên: số cửa hàng đã audit theo miền
    donutData() {
        const items = (this.state.dash?.by_mien || []).filter((i) => i.done > 0);
        const total = items.reduce((a, i) => a + i.done, 0);
        const R = 62, C = 2 * Math.PI * R;
        let offset = 0;
        return {
            R, total,
            segments: items.map((it) => {
                const len = (it.done / total) * C;
                const seg = { dash: `${len} ${C - len}`, offset: -offset, color: this.miencolor(it.key),
                    label: it.label, value: it.done, pct: Math.round((100 * it.done) / total) };
                offset += len;
                return seg;
            }),
        };
    }

    // Biểu đồ đường: tỷ lệ cửa hàng đã / chưa audit theo tháng
    lineData() {
        const trend = this.state.dash?.trend || [];
        const W = 920, H = 190, L = 40, R = 16, T = 16, B = 28;
        const x = (i) => L + ((W - L - R) * i) / Math.max(trend.length - 1, 1);
        const y = (v) => T + (H - T - B) * (1 - v / 100);
        const pts = (k) => trend.map((t, i) => ({ x: x(i), y: y(t[k]), v: t[k], label: t.label }));
        const done = pts("done"), todo = pts("todo");
        const path = (ps) => ps.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
        return {
            W, H, done, todo, donePath: path(done), todoPath: path(todo),
            ticks: [0, 25, 50, 75, 100].map((v) => ({ y: y(v), label: `${v}%` })),
        };
    }

    // Lịch sử các màn đã mở để nút "Quay lại" trả về đúng nội dung trước đó
    track(entry) {
        if (this._goingBack) {
            return;
        }
        const last = this.history[this.history.length - 1];
        if (!(last?.home && entry.home) && last?.child?.id !== entry.child?.id) {
            this.history.push(entry);
        }
        this.state.canBack = this.history.length > 1;
    }

    async goBack() {
        if (this.history.length < 2) {
            return;
        }
        this.history.pop();
        const prev = this.history[this.history.length - 1];
        this._goingBack = true;
        try {
            if (prev.home) {
                this.onOverview();
            } else {
                await this.onNavChild(prev.child);
            }
        } finally {
            this._goingBack = false;
            this.state.canBack = this.history.length > 1;
        }
    }

    onOverview() {
        this.track({ home: true });
        this.state.activeNav = "overview";
        this.state.contentMode = "dashboard";
        this.state.embeddedViewProps = null;
        this.loadOverview();
    }

    async onNavChild(child) {
        this.loadBadges();
        if (child?.folder) {
            this.state.openGroups[child.id] = !this.state.openGroups[child.id];
            return;
        }
        // popup đang mở (ví dụ Xử lý sai phạm) không che nội dung mục vừa chọn: đóng lại khi chuyển mục
        if (document.querySelector(".modal")) {
            // chốt dòng đang sửa (lưu xong) rồi mới đóng, tránh lỗi "Component is destroyed" khi lưu dở
            document.activeElement?.blur?.();
            await new Promise((resolve) => setTimeout(resolve, 600));
            this.dialog.closeAll();
        }
        if (this.reportNavs.includes(child?.id)) {
            this.track({ child });
            this.state.activeNav = child.id;
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return this.loadReport();
        }
        if (child?.id === "access") {
            this.track({ child });
            this.state.activeNav = "access";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return this.loadPerm();
        }
        if (!child?.action) {
            return;
        }
        this.track({ child });
        await this.openAction(child.action, child.id);
    }

    // Lịch làm việc dạng lưới "Xếp ca": mỗi nhân viên một dòng, cột N1..Nn là Mã ca từng ngày
    async loadSchedule() {
        const sc = this.state.sched;
        const month = this.state.listFilters.month;
        if (!month) {
            sc.rows = [];
            sc.empty = "Hãy chọn một tháng cụ thể ở bộ lọc Tháng để xem lịch.";
            return;
        }
        sc.empty = "";
        sc.loading = true;
        try {
            const res = await this.orm.call("store.nvbh.schedule.line", "get_matrix", [this.listDomain(this.listBase || []), month]);
            sc.ndays = res.ndays;
            sc.rows = res.rows;
        } catch (error) {
            this.notifyError(error);
        } finally {
            sc.loading = false;
        }
    }

    get schedDays() {
        return Array.from({ length: this.state.sched.ndays }, (_, i) => i + 1);
    }

    onSchedCell(row, day) {
        const cell = row.days?.[day];
        return this.openScheduleForm(cell ? cell.schedule_id : false);
    }

    openScheduleForm(resId = false) {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "store.nvbh.schedule",
                res_id: resId,
                views: [[false, "form"]],
                target: "new",
                context: { dialog_size: "extra-large" },
            },
            { onClose: () => { this.state.viewKey += 1; if (this.isScheduleNav) { this.loadSchedule(); } } }
        );
    }

    // Popup "Thêm thông tin nhân viên" (Checklist NVBH > Nhân sự): form phiếu NVBH ở chế độ chỉ nhập nhân sự (context staff_form)
    openStaffForm(resId = false, afterClose = null) {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "store.audit",
                res_id: resId,
                views: [[false, "form"]],
                target: "new",
                context: { store_audit_type: "nvbh", staff_form: true, dialog_size: "extra-large" },
            },
            {
                onClose: () => {
                    this.state.viewKey += 1;
                    this.loadBadges();
                    afterClose?.();
                },
            }
        );
    }

    async loadPerm() {
        this.state.perm = await this.orm.call("store.perm.rule", "get_rules", []);
        this.state.permEdit = null;
    }

    get permList() {
        const q = this.state.permQ.trim().toLowerCase();
        return (this.state.perm?.rules || []).filter((r) => !q || (r.group || "").toLowerCase().includes(q));
    }

    get permOps() {
        return [["read", "Xem", "fa-eye"], ["create", "Thêm", "fa-plus"], ["write", "Sửa", "fa-pencil"], ["unlink", "Xóa", "fa-trash"], ["export", "Xuất Excel", "fa-file-excel-o"]];
    }

    // Chức năng gom theo thư mục (dropdown) như sidebar
    get permFolders() {
        const p = this.state.perm;
        return p.folders.map((f) => ({ ...f, menus: p.menus.filter((m) => m.folder === f.id) }));
    }

    toggleFolder(id) {
        this.state.permClosed[id] = !this.state.permClosed[id];
    }

    folderChecked(f, op) {
        return f.menus.every((m) => this.state.permEdit.perms[m.key][op]);
    }

    onPermFolder(f, op, ev) {
        for (const m of f.menus) {
            this.onPermToggle(m.key, op, ev);
        }
    }

    permAll(r, key) {
        return Object.values(r.perms[key]).every(Boolean);
    }

    // Mở popup thiết lập: sửa bản sao, chỉ ghi khi bấm "Lưu thay đổi"
    onPermOpen(rule) {
        const perms = {};
        for (const m of this.state.perm.menus) {
            perms[m.key] = { read: false, create: false, write: false, unlink: false, export: false, ...(rule?.perms[m.key] || {}) };
        }
        this.state.permEdit = {
            src: rule || null, id: rule?.id || 0, group: rule?.group || "",
            users: [...(rule?.users || [])], perms, lug: "",
        };
    }

    onPermClose() {
        this.state.permEdit = null;
    }

    onPermReset() {
        const e = this.state.permEdit;
        for (const k in e.perms) {
            Object.assign(e.perms[k], { read: false, create: false, write: false, unlink: false, export: false });
        }
    }

    onPermToggle(key, op, ev) {
        const v = ev.target.checked;
        for (const o of op === "all" ? ["read", "create", "write", "unlink", "export"] : [op]) {
            this.state.permEdit.perms[key][o] = v;
        }
    }

    onPermColumn(op, ev) {
        for (const k in this.state.permEdit.perms) {
            this.state.permEdit.perms[k][op] = ev.target.checked;
        }
    }

    onPermUserAdd(ev) {
        const e = this.state.permEdit;
        const u = this.state.perm.users.find((x) => x.name === ev.target.value.trim());
        ev.target.value = "";
        if (u && !e.users.some((x) => x.id === u.id)) {
            e.users.push(u);
        }
    }

    // Nạp toàn bộ user của một nhóm LUG Permission
    onPermLugGroup(ev) {
        const e = this.state.permEdit;
        const g = this.state.perm.groups.find((x) => x.name === ev.target.value);
        ev.target.value = "";
        for (const u of g?.users || []) {
            if (!e.users.some((x) => x.id === u.id)) {
                e.users.push(u);
            }
        }
    }

    onPermUserRemove(u) {
        const e = this.state.permEdit;
        e.users = e.users.filter((x) => x.id !== u.id);
    }

    async onPermSave() {
        const e = this.state.permEdit;
        if (!e.users.length) {
            return this.notification.add("Chọn ít nhất một user.", { type: "warning" });
        }
        const rules = this.state.perm.rules.filter((r) => r.id !== e.id || !e.id).map(this.permPayload);
        rules.push(this.permPayload({ id: e.id, group: e.group.trim(), users: e.users, perms: e.perms }));
        await this.orm.call("store.perm.rule", "save_rules", [rules]);
        this.notification.add("Đã lưu phân quyền.", { type: "success" });
        return this.loadPerm();
    }

    async onPermDelete() {
        const e = this.state.permEdit;
        const rules = this.state.perm.rules.filter((r) => r.id !== e.id).map(this.permPayload);
        await this.orm.call("store.perm.rule", "save_rules", [rules]);
        return this.loadPerm();
    }

    permPayload(r) {
        return { id: r.id, group: r.group, user_ids: r.users.map((u) => u.id), perms: r.perms };
    }

    openAudit(resId) {
        this.showWindow(
            { res_model: "store.audit", views: [[false, "form"]], domain: [], context: {} },
            "review",
            "form",
            resId
        );
    }

    async openAction(xmlid, navId) {
        if (navId === "nvbh_schedule") {
            this.state.activeNav = "nvbh_schedule";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            this.listBase = [];
            if (!this.state.dash) {
                this.loadOverview().catch(() => {});
            }
            return this.loadSchedule();
        }
        if (navId === "nvbh_jobs") {
            return this.openJobsPage();
        }
        if (navId === "nvbh_done") {
            return this.openDonePage();
        }
        if (navId === "nvbh_mg_staff" || navId === "nvbh_mg_eval") {
            return this.openManagePage(navId);
        }
        try {
            const act = await this.action.loadAction(xmlid);
            if (navId === "violation_stores") {
                // chỉ các phiếu thuộc hạng mục mình phụ trách / kiểm soát (Quản lý thấy tất cả)
                const scope = await this.orm.call("store.audit", "get_violation_scope", []);
                act.domain = [...this.evalActionValue(act.domain, []), ...scope];
            }
            const type = String(act.view_mode || "list,form").split(",")[0] === "form" ? "form" : "list";
            this.showWindow(act, navId, type, false);
            return act;
        } catch (error) {
            this.notifyError(error);
        }
    }

    showWindow(act, navId, type, resId) {
        const views = normalizeViews(act, type);
        const typed = views.find((view) => view[1] === type);
        const viewProps = {
            resModel: act.res_model,
            type,
            views,
            domain: this.evalActionValue(act.domain, []),
            context: this.evalActionValue(act.context, {}),
            display: { controlPanel: {} },
            loadActionMenus: true,
            loadIrFilters: false,
            selectRecord: (id) => this.openRecord(act, navId, id),
            createRecord: () => this.openRecord(act, navId, false),
        };
        if (typed && typed[0]) {
            viewProps.viewId = typed[0];
        }
        if (type === "form") {
            viewProps.resId = resId || false;
        }
        // đặt màn hiện tại trước khi tính domain lọc: listDomain chọn trường ngày (audit_date / work_date) theo activeNav
        this.state.activeNav = navId;
        if (navId === "shift") {
            // Danh mục ca làm việc: mỗi tab = một loại ca
            this.listBase = viewProps.domain;
            viewProps.domain = this.shiftDomain();
            this.loadShiftStats();
        }
        if (this.filterNavs.includes(navId)) {
            this.listBase = viewProps.domain; // không đặt vào viewProps: ListController từ chối prop lạ
            viewProps.domain = this.listDomain(this.listBase);
        }
        this.state.viewKey += 1;
        this.state.activeNav = navId;
        this.state.embeddedViewProps = viewProps;
        this.state.contentMode = "list";
    }

    // Xử lý sai phạm: bấm "Xử lý sai phạm" (hoặc dòng phiếu) thì mở popup bảng lỗi cần khắc phục như file Excel
    async openViolation(id) {
        try {
            await this.action.doAction(await this.orm.call("store.audit", "action_open_violation_popup", [[id]]));
        } catch (error) {
            this.notifyError(error);
        }
    }

    // Ghi lại các nhóm đang mở + vị trí cuộn của danh sách để khôi phục sau khi nạp lại (lưu xong không bị về đầu / mất nhóm)
    snapshotList() {
        const wrap = document.querySelector(".o_store_list_wrap");
        const scrollers = wrap ? [wrap, ...wrap.querySelectorAll(".o_list_renderer, .o_content")] : [];
        return {
            open: [...document.querySelectorAll(".o_store_list_wrap tr.o_group_header.o_group_open")].map((tr) => tr.innerText.trim()),
            scroll: scrollers.map((el) => [el, el.scrollLeft, el.scrollTop]),
            page: [document.scrollingElement.scrollLeft, document.scrollingElement.scrollTop],
        };
    }

    async restoreList(keep) {
        for (let i = 0; i < 12; i++) {
            await new Promise((r) => setTimeout(r, 250));
            const heads = [...document.querySelectorAll(".o_store_list_wrap tr.o_group_header")];
            if (!heads.length) { continue; }
            let clicked = false;
            heads.forEach((tr) => {
                if (!tr.classList.contains("o_group_open") && keep.open.includes(tr.innerText.trim())) {
                    (tr.querySelector("th") || tr).click();
                    clicked = true;
                }
            });
            if (!clicked) { break; }
        }
        await new Promise((r) => setTimeout(r, 400));
        const wrap = document.querySelector(".o_store_list_wrap");
        const now = wrap ? [wrap, ...wrap.querySelectorAll(".o_list_renderer, .o_content")] : [];
        keep.scroll.forEach(([old, left, top], i) => {
            const el = now[i] && now[i].isConnected ? now[i] : old.isConnected ? old : null;
            if (el) { el.scrollLeft = left; el.scrollTop = top; }
        });
        document.scrollingElement.scrollLeft = keep.page[0];
        document.scrollingElement.scrollTop = keep.page[1];
    }

    async openRecord(act, navId, resId) {
        if (navId === "nvbh_done") {
            // bấm tên nhân viên -> popup nội dung checklist đã lưu
            try {
                const payload = resId ? await this.orm.call("store.nvbh.check", "read_checklist", [resId]) : false;
                if (payload) {
                    this.dialog.add(StoreCheckViewDialog, { payload, onSaved: () => { this.state.viewKey += 1; } });
                }
            } catch (error) {
                this.notifyError(error);
            }
            return;
        }
        if (navId === "nvbh_schedule") {
            // dòng lịch -> popup lịch làm việc chứa dòng đó; Thêm mới -> popup trống
            let scheduleId = false;
            if (resId) {
                const [row] = await this.orm.read("store.nvbh.schedule.line", [resId], ["schedule_id"]);
                scheduleId = row?.schedule_id?.[0] || false;
            }
            return this.openScheduleForm(scheduleId);
        }
        if (navId === "nvbh_staff") {
            // dòng nhân sự -> popup form nhân sự của phiếu chứa nó; Thêm mới -> popup trống
            let auditId = false;
            if (resId) {
                const [row] = await this.orm.read("store.audit.staff", [resId], ["audit_id"]);
                auditId = row?.audit_id?.[0] || false;
            }
            return this.openStaffForm(auditId);
        }
        if (navId === "violation_stores" && resId) {
            return this.openViolation(resId);
        }
        if (navId === "violation_all" && resId) {
            // bấm dòng lỗi thì mở popup xử lý sai phạm của biên bản chứa dòng đó
            return this.orm.read("store.audit.action", [resId], ["audit_id"]).then(([row]) => row && this.openViolation(row.audit_id[0]));
        }
        if (!["benchmark", "review", "review_list", "level", "nvbh_jobs", "gs_benchmark", "gs_level", "shift", "nvbh_task", "nvbh_rating", "nvbh", "asm", "gs", "report_gs", "violation_stores", "violation_all"].includes(navId)) {
            return this.showWindow(act, navId, "form", resId);
        }
        // Điểm chuẩn và Phiếu đánh giá mở trong popup, đóng xong thì nạp lại danh sách (giữ nguyên nhóm đang mở và vị trí cuộn)
        const keep = this.snapshotList();
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: act.res_model,
                res_id: resId || false,
                views: [[false, "form"]],
                target: "new",
                context: {
                    ...this.evalActionValue(act.context, {}),
                    dialog_size: "extra-large",
                    ...(navId === "shift" ? { default_shift_type: this.state.shiftTab } : {}),
                },
            },
            {
                onClose: () => {
                    this.state.viewKey += 1;
                    this.restoreList(keep);
                },
            }
        );
    }

    evalActionValue(value, fallback) {
        // loadAction trả domain / context dạng chuỗi Python: evaluate để giữ store_audit_type, search_default_*
        if (!value) {
            return fallback;
        }
        if (typeof value !== "string") {
            return value;
        }
        try {
            return evaluateExpr(value, { ...user.context, uid: user.userId });
        } catch {
            return fallback;
        }
    }

    notifyError(error) {
        const message = error?.data?.message || error?.message || "Không mở được màn hình này.";
        this.notification.add(message, { type: "danger" });
    }
}

registry.category("actions").add("store_checklist_shell", StoreChecklistShell);
