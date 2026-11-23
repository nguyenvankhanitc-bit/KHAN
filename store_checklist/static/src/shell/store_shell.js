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
import { StoreChtPage } from "@store_checklist/shell/store_cht_page";

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
    static components = { PhanHeInternetShell, View, DateTimeInput, StoreChtPage };
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
            schedImport: null,
            contentMode: "dashboard",
            shiftTab: "morning", shiftStats: { total: 0, types: 0 },
            job: { kind: "nvbh", editMode: false, date: "", storeId: "", stores: [], staff: [], off: [], storeStaff: 0, lineId: "", check: null, snap: "", closed: {} },
            done: { month: "", storeId: "", mien: "", mienOpen: {}, rowMienOpen: {}, rowStoreOpen: {}, storeStatus: {}, q: "", today: false, errors: false, rows: [], open: {}, all: {}, popup: "", dayPick: "", tab: "list", staff: "", monthly: null, onlyWork: true },
            needStore: false,
            auditStoreIds: [],
            myRole: "",
            kpi: { month: "", mien: "", closedStores: {}, storeStatus: {}, storeId: "", stores: [], staffOpts: [], staff: "", data: null, busy: false, tab: "staff", overview: null, profile: "kpi" },
            perf: { month: "", mien: "", asmId: "", storeId: "", rank: "", q: "", data: null, busy: false, closed: {} },
            kpiAsm: { month: "", mien: "", asmId: "", tab: "compare", pillarIdx: 0, rankFilter: "", data: null, closed: {}, openStores: {}, busy: false },
            mg: { month: "", date: "", storeStatus: {}, storeId: "", q: "", errors: false, active: true, evalMode: "day", name: "", names: [], rows: [], evalRows: [], week: { days: [], rows: [], week_label: "" }, busy: false },
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
            permTab: "rules",
            photoCfg: null, // Cài đặt > Lưu trữ hình ảnh
            photoBusy: false,
            photoDirty: false, // Phân quyền: "rules" = Quản trị phân quyền, "staff" = Phân quyền xem nhân sự
            staffPerm: null,
            staffPermQ: "",
            staffEdit: null,
            staffScope: [], // các mục Checklist NVBH user hiện tại có Phân quyền xem nhân sự
            staffStores: [], // cửa hàng được cấp ở mục Nhân sự (ô lọc cửa hàng)
            today: { mien: "", store: "", miens: [], stores: [] }, // Lịch ca hôm nay: bộ lọc Miền / Cửa hàng
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
            const isDonePopup = dlg.classList?.contains("o_store_done_popup") && ev.clientX - dlg.getBoundingClientRect().left <= 12;
            if (!isDonePopup && (!dlg.classList?.contains("modal-dialog") || !dlg.querySelector(".o_store_violation_list"))) {
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
                // sidebar có transition width 0.2s: đo lại khi transition kết thúc và sau khi thả chuột để popup không bị lệch
                side.addEventListener("transitionend", syncSidebarWidth);
            }
            this._syncAfterDrag = () => {
                syncSidebarWidth();
                setTimeout(syncSidebarWidth, 260);
            };
            document.addEventListener("mouseup", this._syncAfterDrag, true);
            // sidebar có thể bị render lại / tự nới rộng theo nội dung sau khi mount => ResizeObserver giữ phần tử cũ; đo định kỳ để popup luôn khớp
            this._sideTimer = setInterval(syncSidebarWidth, 300);
            window.addEventListener("resize", syncSidebarWidth);
            syncSidebarWidth();
            if (this._startChild && !this._deepCheckId) {
                const first = this._startChild;
                this._startChild = null;
                this.onNavChild(first);
            }
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
            document.removeEventListener("mouseup", this._syncAfterDrag, true);
            clearInterval(this._sideTimer);
            document.querySelector(".o_internet_sidebar")?.removeEventListener("transitionend", syncSidebarWidth);
            document.documentElement.style.removeProperty("--store-sidebar-w");
        });
        // liên kết từ tin nhắn OdooBot (?store_check=ID): mở thẳng phiếu cần đánh giá sau khi màn hình tải xong
        try {
            const raw = new URLSearchParams(window.location.search).get("store_check");
            // cookie do /store_checklist/open/<id> đặt (bền hơn tham số URL vì router của Odoo có thể bỏ tham số lạ); đọc xong xóa ngay
            const ck = document.cookie.split("; ").find((c) => c.startsWith("store_check="));
            this._deepCheckId = Number(raw || (ck ? ck.split("=")[1] : 0)) || 0;
            if (ck) {
                document.cookie = "store_check=; Max-Age=0; path=/";
            }
        } catch {
            this._deepCheckId = 0;
        }
        onWillStart(async () => {
            // user chưa được gán cửa hàng: các màn NVBH thu lại, chọn cửa hàng ở ô lọc mới hiện dữ liệu
            this.state.needStore = await this.orm.call("store.audit", "needs_store_pick", []).catch(() => false);
            this.state.auditStoreIds = this.state.needStore
                ? await this.orm.call("store.audit", "my_audit_store_ids", []).catch(() => [])
                : [];
            this.state.myRole = await this.orm.call("store.nvbh.check", "my_checklist_role", []).catch(() => "");
            this.state.isManager = await user.hasGroup("store_checklist.group_store_manager");
            this.state.canCreate = await user.hasGroup("store_checklist.group_store_user");
            this.state.isSupervisor = await this.orm.call("store.audit", "is_gs_supervisor", []);
            this.state.rights = await this.orm.call("store.perm.rule", "get_my_rights", []);
            this.state.staffScope = await this.orm.call("store.staff.view.rule", "get_my_staff_scope", []).catch(() => []);
            this.state.staffStores = this.state.staffScope.includes("nvbh_staff")
                ? await this.orm.call("store.staff.view.rule", "get_my_staff_stores", []).catch(() => [])
                : [];
            await this.loadOverview();
            // không có quyền Xem "Tổng quan": không hiện dashboard, mở thẳng mục đầu tiên được phép xem
            if (!this.showOverviewNav) {
                this.state.activeNav = "";
                this.state.contentMode = "list";
                this._startChild = this.firstAllowedChild();
            }
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
                    { id: "nvbh_staff", label: "Nhân sự", icon: "fa-id-badge", sub: true, permId: "nvbh_staff", action: "store_checklist.action_store_nvbh_staff" },
                    // Ca làm việc của ngày hôm nay (lấy từ Lịch xếp ca), nhóm theo Miền / Cửa hàng
                    { id: "nvbh_today", label: "Lịch ca hôm nay", icon: "fa-calendar-check-o", sub: true, permId: "nvbh_today", action: "store_checklist.action_store_nvbh_today" },
                    // Mục con "Công việc" của Checklist NVBH: màn hình có 2 tab (Check list công việc / Lịch làm việc)
                    { id: "nvbh_jobs", label: "Công việc check list", icon: "fa-tasks", sub: true, permId: "nvbh_jobs", action: "store_checklist.action_store_nvbh_jobs" },
                    // Danh sách nhân viên đã check list (đã bấm Lưu); bấm vào tên để xem nội dung
                    { id: "nvbh_done", label: "Danh sách checklist NV", icon: "fa-check-square-o", sub: true, permId: "nvbh_done", action: "store_checklist.action_store_nvbh_done" },
                    // Quản lý & đánh giá checklist NVBH: 2 tab Bảng Nhân viên (theo tháng) / Bảng Đánh giá (theo ngày)
                    { id: "nvbh_mg_staff", label: "Quản lý & đánh giá", icon: "fa-th-list", sub: true, permId: "nvbh_mg", action: "store_checklist.action_store_nvbh_done" },
                    // Checklist công việc Cửa hàng trưởng: CHT tick việc đến hạn trong ngày, ASM đánh giá, tự tính lần vi phạm / mức phạt
                    { id: "nvbh_cht", label: "Checklist CV CHT", icon: "fa-user-circle", sub: true, permId: "nvbh_cht" },
                    // Checklist công việc ASM: giống Checklist CV CHT (ASM tick, RSM đánh giá)
                    { id: "nvbh_asmcv", label: "Checklist CV ASM", icon: "fa-user-secret", sub: true, permId: "nvbh_asmcv" },
                    // Các mục phiếu khác (có trong ma trận phân quyền): ẩn / hiện theo quyền Xem của từng user
                    { id: "asm", label: "Checklist ASM", icon: "fa-users", action: "store_checklist.action_store_audit_asm" },
                    { id: "gs", label: "Checklist GS", icon: "fa-eye", action: "store_checklist.action_store_audit_gs" },
                    { id: "review", label: "Phiếu Đánh Giá", icon: "fa-pencil-square-o", action: "store_checklist.action_store_audit" },
                    { id: "review_list", label: "Danh Sách Đánh Giá", icon: "fa-tasks", action: "store_checklist.action_store_audit" },
                ],
            },
            {
                id: "report",
                label: "Báo cáo",
                icon: "fa-bar-chart",
                iconTone: "report",
                children: [
                    { id: "report_gs", label: "Báo cáo GS", icon: "fa-file-text", action: "store_checklist.action_store_report_gs" },
                    { id: "report_nvbh", label: "BC Checklist NVBH KPI", icon: "fa-clipboard", action: "store_checklist.action_store_nvbh_done" },
                    { id: "report_nsuat", label: "BC Năng suất NVBH", icon: "fa-line-chart", action: "store_checklist.action_store_nvbh_done" },
                    { id: "report_nvbh_asm", label: "BC Checklist NVBH ASM", icon: "fa-users", action: "store_checklist.action_store_nvbh_done" },
                    { id: "report_nvbh_perf", label: "BC Hiệu suất NVBH", icon: "fa-tachometer", action: "store_checklist.action_store_nvbh_done" },
                    { id: "report_store", label: "Báo cáo Audit CH", icon: "fa-building" },
                    { id: "report_rank", label: "Báo cáo xếp loại Audit CH", icon: "fa-trophy" },
                    { id: "report_manager", label: "Báo cáo theo quản lý", icon: "fa-user" },
                    { id: "report_flow", label: "Sơ đồ quy trình vận hành giám sát", icon: "fa-sitemap" },
                    { id: "report_flow_nvbh", label: "Sơ đồ quy trình checklist NVBH", icon: "fa-random" },
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
                { id: "cht_task", label: "Danh sách công việc CHT", icon: "fa-list-alt", action: "store_checklist.action_store_cht_task", sub: true },
                { id: "asm_task", label: "Danh sách công việc ASM", icon: "fa-list-alt", action: "store_checklist.action_store_asm_task", sub: true },
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
                    // Lưu trữ hình ảnh (xóa cuốn chiếu ảnh cột Hình ảnh): chỉ Quản trị viên
                    ...(this.isAdminUser ? [{ id: "photo_retention", label: "Lưu trữ ảnh & PDF", icon: "fa-picture-o" }] : []),
                    ...(evalVis.length ? [{ id: "evaluation", label: "Công việc đánh giá", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.evaluation ? evalVis : []),
                    ...(supVis.length ? [{ id: "supervision", label: "Công việc giám sát", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.supervision ? supVis : []),
                    ...(nvbhVis.length ? [{ id: "nvbh_work", label: "Công việc checklist NVBH", icon: "fa-folder-open-o", folder: true }] : []),
                    ...(this.state.openGroups.nvbh_work ? nvbhVis : []),
                ],
            });
        }
        // chưa được phân quyền mục nào: không hiện mục nào trên sidebar
        return this.noAccess ? [] : sections;
    }

    // user có ma trận phân quyền nhưng không được Xem mục nào (vd. chưa được gán nhóm phân quyền)
    get noAccess() {
        const rights = this.state.rights;
        return Boolean(rights) && !this.state.isManager && !Object.values(rights).some((r) => r.read);
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
            this.state.job.kind === "cht"
                ? { id: "nvbh_cht", label: "Check list công việc CHT", action: "" }
                : { id: "nvbh_jobs", label: "Check list công việc", action: "store_checklist.action_store_nvbh_jobs" },
            { id: "nvbh_schedule", label: "Lịch xếp ca", action: "store_checklist.action_store_nvbh_schedule" },
        ];
    }

    get isJobTabs() {
        // Checklist CV CHT: không có tab (lịch ca đã xem / nhập ở Công việc check list NVBH)
        return ["nvbh_jobs", "nvbh_schedule"].includes(this.state.activeNav) && !(this.state.activeNav === "nvbh_schedule" && this.state.job.kind === "cht");
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
                    headers: ["Ngày", "Cửa hàng", "Mã ca", "Trạng thái ngày", "Tổng việc ca", "Đã làm", "Số lỗi", "Tổng giờ", "Điểm đạt", "Điểm chuẩn ca", "Điểm CHT đánh giá", "Điểm ASM đánh giá", "Lỗi CHT đánh giá", "Lỗi ASM đánh giá", "Tỷ lệ đạt (%)", "Kết quả", "Ghi chú / Tóm tắt công việc"],
                    rows: data.rows.filter((r) => !d.onlyWork || r.kind !== "off").map((r) => [
                        r.date, r.store || "-", r.kind === "off" ? "OFF" : r.shift, r.status, r.total, r.done, r.errors, r.hours || 0,
                        r.kind === "off" || r.evaluated ? r.points : "-", r.max_points, r.pts_cht == null ? "-" : r.pts_cht, r.pts_asm == null ? "-" : r.pts_asm,
                        r.txt_cht || "-", r.txt_asm || "-",
                        r.kind === "off" || r.evaluated ? pct(r.pct) : "-", r.control, r.note || "-",
                    ]),
                    foot: [`TỔNG CỘNG KỲ ${this.doneMonthLabel} (${t.days || 0} ngày công thực tế)`, "", "", "", t.total || 0, t.done || 0, t.errors || 0, t.hours || 0,
                        t.avg_points == null ? "-" : t.avg_points, t.max_points || 0, t.avg_cht == null ? "-" : t.avg_cht, t.avg_asm == null ? "-" : t.avg_asm, `${t.err_cht || 0} lỗi`, `${t.err_asm || 0} lỗi`,
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
            { id: "nvbh_mg_staff", label: "Quản lý NV" },
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

    // Quản lý & đánh giá: danh sách cửa hàng theo Miền hiện luôn khi chưa chọn cửa hàng
    get mgPickGroups() {
        return this.mienGroups(this.state.job.stores || []);
    }

    onMgPickStore(st) {
        this.state.mg.storeId = String(st.id);
        return this.loadManage().catch((e) => this.notifyError(e));
    }

    async loadManage() {
        const mg = this.state.mg;
        // màu nút cửa hàng theo tháng của ngày / tháng đang xem: xanh = đã đánh giá xong, cam = chờ đánh giá, trắng = chưa gửi
        const mgMonth = (mg.date || "").slice(0, 7) || mg.month || false;
        mg.storeStatus = await this.orm.call("store.nvbh.check", "get_store_check_status", [mgMonth]).catch(() => ({}));
        if (this.state.needStore && !mg.storeId) {
            mg.rows = [];
            mg.evalRows = [];
            mg.names = [];
            mg.week = { days: [], rows: [], week_label: "" };
            return;
        }
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

    // true khi user chưa có cửa hàng phụ trách và chưa chọn cửa hàng ở ô lọc của màn đang mở
    get needStorePick() {
        if (!this.state.needStore) {
            return false;
        }
        const nav = this.state.activeNav;
        if (this.staffScopedNav) {
            return false; // đã có Phân quyền xem nhân sự: danh sách tự giới hạn theo Miền / Cửa hàng được cấp
        }
        if (nav === "nvbh_done") {
            return !this.state.done.storeId && (this.state.done.tab === 'total' || !this.state.done.q.trim());
        }
        if (nav === "nvbh_mg_staff" || nav === "nvbh_mg_eval") {
            return !this.state.mg.storeId;
        }
        if (nav === "report_nvbh" || nav === "report_nsuat") {
            return !this.state.kpi.storeId;
        }
        if (nav === "nvbh_schedule" || this.filterNavs.includes(nav)) {
            return !this.state.listFilters.store && nav !== "report_flow";
        }
        if (nav === "overview" || this.state.contentMode === "dashboard") {
            return !this.state.filters.store;
        }
        return false;
    }

    async loadDone() {
        const d = this.state.done;
        // màu nền nút cửa hàng: xanh = đã check list đánh giá xong, cam = chưa check list
        d.storeStatus = await this.orm.call("store.nvbh.check", "get_store_check_status", [d.month || false]).catch(() => ({}));
        // chưa chọn cửa hàng thì thu lại, trừ khi đang tìm theo tên nhân viên (tìm được nhân viên ở mọi cửa hàng user được xem)
        if (this.state.needStore && !d.storeId && (d.tab === 'total' || !d.q.trim())) {
            d.rows = [];
            d.monthly = null;
            d.storeStaff = [];
            return;
        }
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

    // Bảng DS nhân viên check list: chưa chọn cửa hàng (vd. Administrator xem tất cả) thì gom dòng theo Miền -> Cửa hàng,
    // mỗi cấp là một dropdown (mặc định thu gọn; đã lọc một Miền thì Miền đó mở sẵn). Đã chọn cửa hàng / đang tìm tên: danh sách phẳng.
    get doneDisplayRows() {
        const rows = this.state.done.rows || [];
        if (this.state.done.storeId || (this.state.done.q || "").trim()) {
            return rows.map((emp) => ({ type: "emp", key: emp.key, emp }));
        }
        const stores = new Map();
        for (const emp of rows) {
            const k = emp.store_id || emp.store;
            if (!stores.has(k)) {
                stores.set(k, { id: k, display_name: emp.store, mien: emp.mien, rows: [] });
            }
            stores.get(k).rows.push(emp);
        }
        const out = [];
        for (const g of this.mienGroups([...stores.values()])) {
            const open = this.isDoneRowMienOpen(g.key);
            const count = g.stores.reduce((n, st) => n + st.rows.length, 0);
            out.push({ type: "mien", key: `m:${g.key}`, gkey: g.key, label: g.label, stores: g.stores.length, count, open });
            if (!open) {
                continue;
            }
            const sorted = [...g.stores].sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));
            for (const st of sorted) {
                const sopen = Boolean(this.state.done.rowStoreOpen[st.id]);
                out.push({ type: "store", key: `s:${st.id}`, id: st.id, label: st.display_name, count: st.rows.length, open: sopen });
                if (sopen) {
                    st.rows.forEach((emp) => out.push({ type: "emp", key: emp.key, emp }));
                }
            }
        }
        return out;
    }

    isDoneRowMienOpen(key) {
        const v = this.state.done.rowMienOpen[key];
        return v === undefined ? Boolean(this.state.done.mien) : v;
    }

    toggleDoneRowMien(key) {
        this.state.done.rowMienOpen[key] = !this.isDoneRowMienOpen(key);
    }

    toggleDoneRowStore(id) {
        this.state.done.rowStoreOpen[id] = !this.state.done.rowStoreOpen[id];
    }

    // danh sách cửa hàng hiện dưới ô tìm kiếm: theo Miền đang chọn (miền trống = tất cả cửa hàng user được chọn)
    get donePickStores() {
        const mien = this.state.done.mien;
        const known = ["Nam", "ĐTT", "Bắc"];
        return (this.state.job.stores || []).filter((s) => !mien || (mien === "other" ? !known.includes(s.mien) : s.mien === mien));
    }

    // cửa hàng gom theo Miền (Nam, ĐTT, Bắc, Văn phòng, Khác); đã chọn một miền thì chỉ có một nhóm
    get donePickGroups() {
        return this.mienGroups(this.donePickStores);
    }

    // báo cáo KPI / Năng suất: cùng danh sách cửa hàng gom theo Miền như Danh sách checklist NV
    get kpiPickGroups() {
        return this.mienGroups(this.kpiStores);
    }

    onKpiPickStore(st) {
        this.state.kpi.storeId = String(st.id);
        return this.loadKpiStaff().catch((e) => this.notifyError(e));
    }

    mienGroups(stores) {
        const order = [["Nam", "Miền Nam"], ["ĐTT", "Miền ĐTT"], ["Bắc", "Miền Bắc"], ["VP", "Văn phòng"]];
        const groups = order.map(([key, label]) => ({ key, label, stores: stores.filter((s) => s.mien === key) }));
        const known = order.map(([key]) => key);
        groups.push({ key: "other", label: "Khác (chưa gán miền)", stores: stores.filter((s) => !known.includes(s.mien)) });
        return groups.filter((g) => g.stores.length);
    }

    // mỗi Miền là một dropdown: mặc định thu gọn; đã chọn một Miền ở ô lọc thì mở sẵn
    isMienOpen(key, mien) {
        const v = this.state.done.mienOpen[key];
        // user có chức danh ASM: các Miền mở sẵn
        return v === undefined ? Boolean(mien === undefined ? this.state.done.mien : mien) || (this.state.myRole || "").startsWith("ASM") : v;
    }

    toggleMienGroup(key) {
        this.state.done.mienOpen[key] = !this.isMienOpen(key);
    }

    onDonePickStore(st) {
        this.state.done.storeId = String(st.id);
        return this.loadDone().catch((e) => this.notifyError(e));
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

    // Thống kê các ngày đang xem: ngày "Đang làm" (draft) chưa tính vào điểm đạt / xếp loại tạm tính
    doneStats(emp) {
        const days = this.visibleDays(emp);
        const done = days.filter((d) => d.state !== "draft");
        const sum = (arr, k) => arr.reduce((s, d) => s + (Number(d[k]) || 0), 0);
        const sumStd = sum(days, "std_points");
        const sumPts = sum(done, "points");
        const sumStdDone = sum(done, "std_points");
        return {
            days: days.length,
            doneDays: done.length,
            drafts: days.length - done.length,
            okDays: done.filter((d) => !d.errors).length,
            evalDays: days.filter((d) => d.evaluated).length,
            total: sum(days, "total"),
            errors: sum(days, "errors"),
            sumStd,
            sumPts,
            sumStdDone,
            avgStd: days.length ? sumStd / days.length : 0,
            avgPts: done.length ? sumPts / done.length : 0,
            pct: sumStdDone ? Math.round((sumPts / sumStdDone) * 100) : 0,
            rating: emp.rating || "—",
        };
    }

    // Xuất file .xlsx (cùng bộ xuất Excel của các bảng khác) các ngày đang xem trong popup
    async onDoneExport(emp) {
        try {
            const data = this.readTable(".o_store_done_days");
            if (!data || !data.rows.length || data.rows.every((r) => r.length < 3)) {
                this.notification.add("Không có dữ liệu để xuất", { type: "warning" });
                return;
            }
            const file = await this.orm.call("store.nvbh.check", "export_table_xlsx", [], {
                title: "CHỈ TIÊU CÔNG VIỆC THEO NGÀY", subtitle: `Nhân viên: ${emp.name} (${emp.store})`,
                headers: data.headers, rows: data.rows, foot: data.foot, filename: "Chi_tieu_cong_viec_theo_ngay",
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

    // Xuất Excel checklist công việc: chọn nhân viên cần xuất (mỗi nhân viên một sheet)
    onJobExport() {
        const job = this.state.job;
        const items = (job.staff || []).map((sf) => ({ key: String(sf.id), label: `${sf.stt}. ${sf.name} · Ca ${sf.shift}` }));
        if (!items.length) {
            this.notification.add("Không có nhân viên nào để chọn", { type: "warning" });
            return;
        }
        this.dialog.add(StoreStaffPickDialog, {
            title: "Xuất Excel checklist công việc", confirmLabel: "Xuất Excel", items,
            selected: job.lineId ? [String(job.lineId)] : [], onConfirm: (keys) => this.exportJobStaff(keys),
        });
    }

    jobSheet(check, staff, storeName, dmy) {
        const rows = [];
        let group = null;
        for (const line of check.lines || []) {
            if (line.group !== group) {
                group = line.group;
                rows.push([group || "", "", "", "", "", "", ""]);
            }
            rows.push([
                line.stt, line.name, line.time_slot || "", Number(line.score) || 0,
                line.is_done ? "Có" : "Không", this.jobStatusLabel(this.jobLineStatus(line)), line.note || "",
            ]);
        }
        const lines = check.lines || [];
        const done = lines.filter((l) => l.is_done).length;
        const num = (v) => Math.round((v || 0) * 100) / 100;
        const pts = num(lines.reduce((s, l) => s + (l.actual_score || 0), 0));
        const max = num(lines.reduce((s, l) => s + (l.score || 0), 0));
        return {
            name: staff.name,
            title: "CHECKLIST CÔNG VIỆC NVBH",
            subtitle: `Ngày: ${dmy} | Cửa hàng: ${storeName} | Nhân viên: ${staff.name} (Ca ${staff.shift})`,
            headers: ["STT", "Tên công việc", "Thời gian", "Điểm", "Có làm", "Trạng thái", "Ghi chú"],
            rows,
            foot: ["TỔNG", `${done}/${lines.length} việc đã làm`, "", `${pts}/${max}`, "", "", ""],
        };
    }

    async exportJobStaff(keys) {
        try {
            const job = this.state.job;
            const dmy = (job.date || "").split("-").reverse().join("/");
            const store = (job.stores || []).find((s) => this.jobSel(s.id, job.storeId));
            const sheets = [];
            for (const key of keys) {
                const staff = (job.staff || []).find((s) => this.jobSel(s.id, key));
                if (!staff) {
                    continue;
                }
                // nhân viên đang mở trên màn hình: dùng dữ liệu hiện có (kể cả phần chưa lưu); còn lại đọc từ máy chủ
                const check = this.jobSel(key, job.lineId) && job.check
                    ? job.check
                    : await this.orm.call("store.nvbh.check", "get_checklist", [Number(key)]);
                sheets.push(this.jobSheet(check, staff, store?.display_name || "", dmy));
            }
            if (!sheets.length) {
                this.notification.add("Không có dữ liệu để xuất", { type: "warning" });
                return;
            }
            const file = await this.orm.call("store.nvbh.check", "export_sheets_xlsx", [], { sheets, filename: "Checklist_cong_viec" });
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
            out.push(emp.days.find((x) => x.date === key) || { id: 0, date: key, empty: true, off: (emp.off_dates || []).includes(key), pct: null, errors: 0 });
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
        if (day.off) {
            return "is-empty is-off";
        }
        if (day.empty) {
            return "is-empty";
        }
        if (!day.evaluated && day.edited) {
            return "is-wait is-edited"; // người thực hiện đã chỉnh sửa sau khi gửi, chờ cấp trên chấm lại
        }
        if (!day.evaluated && day.wait && !["NV", "CHT"].includes(day.wait)) {
            return "is-wait is-wait-up"; // đã qua CHT, đang chờ ASM (hoặc cấp cao hơn): màu xanh nhạt
        }
        return day.errors > 0 ? "is-bad" : day.evaluated ? "is-ok" : "is-wait";
    }

    dayIcon(day) {
        if (day.off) {
            return "fa-moon-o";
        }
        if (day.empty) {
            return "fa-minus-circle";
        }
        if (day.state === "draft" && !day.done) {
            return "fa-circle-o";
        }
        return day.errors > 0 ? "fa-exclamation-circle" : day.evaluated ? "fa-check-circle" : "fa-clock-o";
    }

    dayLabel(day) {
        if (day.off) {
            return "OFF";
        }
        if (day.empty) {
            return "Chưa có";
        }
        if (day.state === "draft" && (!day.wait || day.wait === "NV")) {
            // phiếu chưa gửi: chưa tích việc nào = Chưa check list; đã tích một phần = Đang làm
            return day.done > 0 ? "Đang làm" : "Chưa check list";
        }
        if (day.evaluated) {
            return day.errors > 0 ? "Lỗi" : "Đạt";
        }
        // chưa đánh giá xong: ghi rõ đang chờ cấp nào (Chờ CHT / Chờ ASM / Chờ Admin)
        return day.wait ? `Chờ ${day.wait}` : "Chờ";
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

    // ---- BC Checklist NVBH: Phiếu đánh giá năng suất & tính KPI cá nhân (theo tháng / cửa hàng / nhân viên) ----
    async openKpiPage(profile = "kpi") {
        try {
            const k = this.state.kpi;
            k.profile = profile;
            if (profile !== "kpi") {
                k.tab = "staff"; // báo cáo năng suất chỉ có phiếu cá nhân
            }
            this.state.activeNav = profile === "kpi" ? "report_nvbh" : "report_nsuat";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            if (!k.month) {
                const d = new Date();
                k.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
            }
            if (!k.stores.length) {
                k.stores = await this.orm.call("store.nvbh.check", "get_my_stores", []);
            }
            if (!k.storeId && k.stores.length === 1) {
                k.storeId = String(k.stores[0].id);
            }
            await this.loadKpiStaff();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async loadKpiStaff() {
        const k = this.state.kpi;
        // màu nút cửa hàng: xanh = đã đánh giá xong, cam = đã gửi check list chờ đánh giá, trắng = chưa gửi
        k.storeStatus = await this.orm.call("store.nvbh.check", "get_store_check_status", [k.month || false]).catch(() => ({}));
        if (this.state.needStore && !k.storeId) {
            k.staffOpts = [];
            k.staff = "";
            k.data = null;
            k.overview = null;
            return;
        }
        k.staffOpts = await this.orm.call("store.nvbh.check", "get_kpi_staff", [k.month || false, k.storeId ? Number(k.storeId) : false, k.mien || false]);
        if (!k.staffOpts.some((o) => o.name === k.staff)) {
            k.staff = k.staffOpts[0]?.name || "";
        }
        await this.loadKpi();
    }

    async loadKpi() {
        const k = this.state.kpi;
        k.overview = k.tab === "compare" ? await this.orm.call("store.nvbh.check", "get_kpi_overview", [k.month || false, k.storeId ? Number(k.storeId) : false, k.mien || false]) : null;
        k.data = k.staff ? await this.orm.call("store.nvbh.check", "get_kpi_report", [k.month || false, k.storeId ? Number(k.storeId) : false, k.staff, k.profile]) : null;
    }

    // Bảng So Sánh Tổng Thể: nhóm theo cửa hàng; hạng tính trong từng cửa hàng (điểm KPI giảm dần)
    get kpiOverviewGroups() {
        const rows = this.state.kpi.overview?.rows || [];
        const map = new Map();
        for (const r of rows) {
            const key = r.store || "-";
            if (!map.has(key)) {
                map.set(key, { store: key, rows: [] });
            }
            map.get(key).rows.push(r);
        }
        const num = (v) => Math.round((v || 0) * 100) / 100;
        return [...map.values()]
            .sort((a, b) => a.store.localeCompare(b.store))
            .map((g) => {
                g.rows.sort((a, b) => b.kpi_total - a.kpi_total || a.name.localeCompare(b.name));
                g.rows.forEach((r, i) => (r.rank_in_store = i + 1));
                g.avg = num(g.rows.reduce((s, r) => s + r.kpi_total, 0) / g.rows.length);
                return g;
            });
    }

    onKpiTab(tab) {
        this.state.kpi.tab = tab;
        return this.loadKpi().catch((e) => this.notifyError(e));
    }

    // bấm một dòng ở Bảng So Sánh Tổng Thể -> mở phiếu KPI cá nhân của nhân viên đó
    onKpiOpen(row) {
        this.state.kpi.staff = row.name;
        return this.onKpiTab("staff");
    }

    // thu gọn / mở rộng nhóm cửa hàng ở Bảng So Sánh Tổng Thể (áp dụng cho mọi user)
    isKpiStoreOpen(store) {
        return !this.state.kpi.closedStores[store];
    }

    toggleKpiStore(store) {
        this.state.kpi.closedStores[store] = !this.state.kpi.closedStores[store];
    }

    // Xuất Excel Bảng So Sánh: chọn cửa hàng, mỗi cửa hàng một sheet
    onKpiOverviewExport() {
        const groups = this.kpiOverviewGroups;
        if (!groups.length) {
            this.notification.add("Không có dữ liệu để xuất", { type: "warning" });
            return;
        }
        this.dialog.add(StoreStaffPickDialog, {
            title: "Xuất Excel Bảng So Sánh - chọn cửa hàng (mỗi cửa hàng một sheet)", confirmLabel: "Xuất Excel",
            items: groups.map((g) => ({ key: g.store, label: `${g.store} (${g.rows.length} NV)` })),
            selected: this.state.kpi.storeId ? groups.map((g) => g.store) : [],
            onConfirm: (stores) => this.exportKpiOverview(stores),
        });
    }

    async exportKpiOverview(stores) {
        try {
            const k = this.state.kpi;
            const file = await this.orm.call("store.nvbh.check", "export_kpi_overview_xlsx", [], {
                month: k.month || false, store_id: k.storeId ? Number(k.storeId) : false, mien: k.mien || false, stores: stores || [],
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

    // ô Tháng hiển thị dd/mm/yyyy: chọn ngày bất kỳ, báo cáo lấy theo tháng của ngày đó (hiển thị ngày 1 của tháng)
    onKpiMonthPick(dt) {
        const ym = dt && dt.isValid ? dt.toFormat("yyyy-MM") : "";
        if (!ym || ym === this.state.kpi.month) {
            return;
        }
        this.state.kpi.month = ym;
        return this.loadKpiStaff().catch((e) => this.notifyError(e));
    }

    // lọc theo Miền: danh sách cửa hàng thu hẹp theo miền; cửa hàng đang chọn không thuộc miền mới thì bỏ chọn
    get kpiStores() {
        const k = this.state.kpi;
        return k.mien ? k.stores.filter((s) => s.mien === k.mien) : k.stores;
    }

    onKpiMien(ev) {
        const k = this.state.kpi;
        k.mien = ev.target.value;
        if (k.storeId && !this.kpiStores.some((s) => String(s.id) === String(k.storeId))) {
            k.storeId = "";
        }
        return this.loadKpiStaff().catch((e) => this.notifyError(e));
    }

    onKpiStore(ev) {
        this.state.kpi.storeId = ev.target.value;
        return this.loadKpiStaff().catch((e) => this.notifyError(e));
    }

    onKpiStaff(ev) {
        this.state.kpi.staff = ev.target.value;
        return this.loadKpi().catch((e) => this.notifyError(e));
    }

    // nhập tay tiêu chí 4 (doanh số) / 5 (thái độ phục vụ): % hoàn thành 0-100
    async onKpiManual(row, ev) {
        const raw = ev.target.value.trim().replace(",", ".");
        const d = this.state.kpi.data;
        try {
            this.state.kpi.data = await this.orm.call("store.nvbh.check", "save_kpi_input", [
                d.month, d.store_id, d.staff, row.manual, raw === "" ? null : Number(raw), "",
            ]);
        } catch (error) {
            this.notifyError(error);
            await this.loadKpi();
        }
    }

    onKpiExport() {
        const k = this.state.kpi;
        if (k.tab === "compare") {
            return this.onKpiOverviewExport();
        }
        const items = k.staffOpts.map((o) => ({ key: o.name, label: o.code ? `${o.name} (ID: ${o.code})` : o.name }));
        if (!items.length) {
            this.notification.add("Không có nhân viên nào để chọn", { type: "warning" });
            return;
        }
        this.dialog.add(StoreStaffPickDialog, {
            title: k.profile === "kpi" ? "Xuất Excel Phiếu KPI cá nhân" : "Xuất Excel Báo cáo năng suất", confirmLabel: "Xuất Excel", items, selected: k.staff ? [k.staff] : [],
            onConfirm: (names) => this.exportKpiStaff(names),
        });
    }

    async exportKpiStaff(names) {
        try {
            const k = this.state.kpi;
            const file = await this.orm.call("store.nvbh.check", "export_kpi_xlsx", [], {
                month: k.month || false, store_id: k.storeId ? Number(k.storeId) : false, staff_names: names, profile: k.profile,
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

    fmtKpi(n) {
        return n === null || n === undefined ? "-" : new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
    }

    fmtKpiPct(n) {
        return n === null || n === undefined ? "-" : new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n) + "%";
    }

    // ---- BC Hiệu suất NVBH: mỗi dòng một nhân viên, xếp hạng theo Tổng KPI ----
    async openPerfPage() {
        try {
            const pf = this.state.perf;
            this.state.activeNav = "report_nvbh_perf";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            if (!pf.month) {
                const d = new Date();
                pf.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
            }
            await this.loadPerf();
        } catch (error) {
            this.notifyError(error);
        }
    }

    perfArgs() {
        const pf = this.state.perf;
        return {
            month: pf.month || false,
            mien: pf.mien || false,
            asm_id: pf.asmId !== "" ? Number(pf.asmId) : false,
            store_id: pf.storeId ? Number(pf.storeId) : false,
        };
    }

    async loadPerf() {
        const pf = this.state.perf;
        pf.busy = true;
        try {
            pf.data = await this.orm.call("store.nvbh.check", "get_nvbh_perf_report", [], this.perfArgs());
        } finally {
            pf.busy = false;
        }
    }

    onPerfFilter(key, ev) {
        const pf = this.state.perf;
        pf[key] = ev.target.value;
        if (key === "mien") {
            pf.asmId = "";
            pf.storeId = "";
        } else if (key === "asmId") {
            pf.storeId = "";
        }
        return this.loadPerf().catch((e) => this.notifyError(e));
    }

    onPerfRank(rk) {
        this.state.perf.rank = this.state.perf.rank === rk ? "" : rk;
    }

    onPerfSearch(ev) {
        this.state.perf.q = ev.target.value;
    }

    perfGroupName(i) {
        const names = this.state.perf.data?.group_names || [];
        return names[i] || `Nhóm ${["I", "II", "III", "IV", "V"][i]}`;
    }

    get perfRows() {
        const pf = this.state.perf;
        const q = (pf.q || "").trim().toLowerCase();
        return (pf.data?.rows || []).filter(
            (r) =>
                (!pf.rank || r.rank_code === pf.rank) &&
                (!q || `${r.name} ${r.code || ""} ${r.store} ${r.asm}`.toLowerCase().includes(q))
        );
    }

    // nhóm nhân viên theo cửa hàng: dòng cửa hàng = trung bình các NV đang hiện, xếp theo TB Tổng KPI
    get perfGroups() {
        const keys = ["g1", "g2", "g3", "g4", "g5", "complete", "discipline", "sales", "attitude", "kpi_total"];
        const map = new Map();
        for (const r of this.perfRows) {
            if (!map.has(r.store_id)) {
                map.set(r.store_id, { store_id: r.store_id, store: r.store, asm: r.asm, staff: [] });
            }
            map.get(r.store_id).staff.push(r);
        }
        const groups = [...map.values()].map((g) => {
            for (const k of keys) {
                g[k] = Math.round((100 * g.staff.reduce((s, x) => s + (x[k] || 0), 0)) / g.staff.length) / 100;
            }
            g.passed = g.kpi_total >= 72;
            return g;
        });
        return groups.sort((a, b) => b.kpi_total - a.kpi_total || a.store.localeCompare(b.store));
    }

    isPerfStoreOpen(id) {
        return !this.state.perf.closed[id];
    }

    togglePerfStore(id) {
        this.state.perf.closed[id] = !this.state.perf.closed[id];
    }

    async onPerfExport() {
        try {
            const file = await this.orm.call("store.nvbh.check", "export_nvbh_perf_xlsx", [], this.perfArgs());
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

    // ---- BC Checklist NVBH ASM: Báo cáo quản trị khu vực theo ASM ----
    async openKpiAsmPage() {
        try {
            const ka = this.state.kpiAsm;
            this.state.activeNav = "report_nvbh_asm";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            if (!ka.month) {
                const d = new Date();
                ka.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
            }
            await this.loadKpiAsm();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async loadKpiAsm() {
        const ka = this.state.kpiAsm;
        ka.busy = true;
        try {
            ka.data = await this.orm.call("store.nvbh.check", "get_kpi_asm_report", [], {
                month: ka.month || false,
                mien: ka.mien || false,
                asm_id: ka.asmId !== "" ? Number(ka.asmId) : false,
            });
            if (ka.asmId !== "" && !ka.data.asm_opts.some((o) => String(o.id) === String(ka.asmId))) {
                ka.asmId = "";
            }
        } finally {
            ka.busy = false;
        }
    }

    onKpiAsmTab(tab) {
        const ka = this.state.kpiAsm;
        ka.tab = tab;
        if (tab === "detail" && ka.asmId === "" && ka.data?.asm_opts?.length) {
            ka.asmId = String(ka.data.asm_opts[0].id);
            return this.loadKpiAsm().catch((e) => this.notifyError(e));
        }
        if (tab === "compare" && ka.asmId !== "") {
            ka.asmId = "";
            return this.loadKpiAsm().catch((e) => this.notifyError(e));
        }
    }

    get kpiAsmMonthOptions() {
        return this.monthOptions.map((m) => ({ value: m.value, label: `Tháng ${Number(m.value.slice(5))}` }));
    }

    onKpiAsmMonth(ev) {
        const ym = ev.target.value;
        if (!ym || ym === this.state.kpiAsm.month) {
            return;
        }
        this.state.kpiAsm.month = ym;
        return this.loadKpiAsm().catch((e) => this.notifyError(e));
    }

    onKpiAsmMonthPick(dt) {
        const ym = dt && dt.isValid ? dt.toFormat("yyyy-MM") : "";
        if (!ym || ym === this.state.kpiAsm.month) {
            return;
        }
        this.state.kpiAsm.month = ym;
        return this.loadKpiAsm().catch((e) => this.notifyError(e));
    }

    onKpiAsmMien(ev) {
        this.state.kpiAsm.mien = ev.target.value;
        this.state.kpiAsm.asmId = "";
        this.state.kpiAsm.rankFilter = "";
        return this.loadKpiAsm().catch((e) => this.notifyError(e));
    }

    onKpiAsmPick(ev) {
        this.state.kpiAsm.asmId = ev.target.value;
        this.state.kpiAsm.rankFilter = "";
        return this.loadKpiAsm().catch((e) => this.notifyError(e));
    }

    onKpiAsmOpenDetail(asm) {
        this.state.kpiAsm.asmId = String(asm.id);
        this.state.kpiAsm.tab = "detail";
        this.state.kpiAsm.rankFilter = "";
        return this.loadKpiAsm().catch((e) => this.notifyError(e));
    }

    onKpiAsmPillar(idx) {
        this.state.kpiAsm.pillarIdx = idx;
    }

    onKpiAsmRankFilter(rk) {
        this.state.kpiAsm.rankFilter = rk;
    }

    isKpiAsmOpen(id) {
        return !this.state.kpiAsm.closed[id];
    }

    toggleKpiAsmRow(id) {
        this.state.kpiAsm.closed[id] = !this.state.kpiAsm.closed[id];
    }

    isKpiAsmStoreOpen(storeId) {
        return Boolean(this.state.kpiAsm.openStores[storeId]);
    }

    toggleKpiAsmStore(storeId) {
        this.state.kpiAsm.openStores[storeId] = !this.state.kpiAsm.openStores[storeId];
    }

    async onKpiAsmExport() {
        try {
            const ka = this.state.kpiAsm;
            const file = await this.orm.call("store.nvbh.check", "export_kpi_asm_xlsx", [], {
                month: ka.month || false,
                mien: ka.mien || false,
                asm_id: ka.asmId !== "" ? Number(ka.asmId) : false,
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

    kpiAsmColor(idx) {
        const palette = ["#2563eb", "#f97316", "#16a34a", "#7c3aed", "#0891b2", "#e11d48"];
        return palette[idx % palette.length];
    }

    // tên 5 nhóm theo danh mục Nhóm công việc (I. TRANG THIẾT BỊ, VẬT TƯ ...)
    kpiAsmGroupName(i) {
        const names = this.state.kpiAsm.data?.group_names || [];
        return names[i] || `Nhóm ${["I", "II", "III", "IV", "V"][i]}`;
    }

    get kpiAsmPillarTabs() {
        return [
            ...[0, 1, 2, 3, 4].map((i) => ({ label: this.kpiAsmGroupName(i), desc: this.kpiAsmGroupName(i) })),
            { label: "Tổng 5 nhóm", desc: "Tổng hợp chất lượng thực hiện Checklist (5 nhóm)" },
        ];
    }

    get kpiAsmActivePillar() {
        return this.kpiAsmPillarTabs[this.state.kpiAsm.pillarIdx || 0];
    }

    get kpiAsmRegionPillarAvg() {
        return this.state.kpiAsm.data?.region?.pillar_avgs?.[this.state.kpiAsm.pillarIdx || 0] || 0;
    }

    get kpiAsmRegionPillarAvgInt() {
        return Math.round(this.kpiAsmRegionPillarAvg);
    }

    get kpiAsmFilteredAsms() {
        const asms = this.state.kpiAsm.data?.asms || [];
        const rk = this.state.kpiAsm.rankFilter;
        return rk ? asms.filter((a) => a.rank_code === rk) : asms;
    }

    get kpiAsmRankedRows() {
        const idx = this.state.kpiAsm.pillarIdx || 0;
        const avg = this.kpiAsmRegionPillarAvg;
        return [...this.kpiAsmFilteredAsms]
            .sort((a, b) => (b.pillars[idx] || 0) - (a.pillars[idx] || 0) || b.kpi_total - a.kpi_total || a.name.localeCompare(b.name))
            .map((a, i) => {
                const score = a.pillars[idx] || 0;
                return {
                    ...a,
                    pos: i + 1,
                    score,
                    scoreInt: Math.round(score),
                    barPct: Math.max(2, Math.min(100, score)),
                    above: score >= avg,
                };
            });
    }

    get kpiAsmRadarList() {
        return this.kpiAsmFilteredAsms.slice(0, 6);
    }

    get kpiAsmRadarAxes() {
        const labels = ["Kỷ luật", "Thái độ", "Tỷ lệ đi ca", "Doanh số", "Hàng hóa", "Hoàn thành"];
        const cx = 160, cy = 112, r = 64, lr = 82;
        return labels.map((label, i) => {
            const ang = -Math.PI / 2 + (i * Math.PI) / 3;
            const x = +(cx + r * Math.cos(ang)).toFixed(1);
            const y = +(cy + r * Math.sin(ang)).toFixed(1);
            const lx = +(cx + lr * Math.cos(ang)).toFixed(1);
            const ly = +(cy + lr * Math.sin(ang)).toFixed(1);
            const anchor = Math.abs(Math.cos(ang)) < 0.2 ? "middle" : Math.cos(ang) > 0 ? "start" : "end";
            return { label, x, y, lx, ly, anchor };
        });
    }

    kpiAsmRadarPolygon(values, scale = 1) {
        const cx = 160, cy = 112, r = 64;
        return values.map((v, i) => {
            const ang = -Math.PI / 2 + (i * Math.PI) / 3;
            const pct = Math.max(0, Math.min(100, Number(v) || 0)) / 100 * scale;
            return `${(cx + r * pct * Math.cos(ang)).toFixed(1)},${(cy + r * pct * Math.sin(ang)).toFixed(1)}`;
        }).join(" ");
    }

    fmtKpiWeight(n) {
        return String(n).replace(".", ",") + "đ";
    }

    async openJobsPage(kind = "nvbh") {
        try {
            // kind = "cht": Checklist CV CHT (người có chức vụ CHT trên lịch xếp ca, công việc theo Danh sách công việc CHT)
            this.state.activeNav = kind === "cht" ? "nvbh_cht" : "nvbh_jobs";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            const job = this.state.job;
            if (job.kind !== kind) {
                job.kind = kind;
                job.lineId = "";
                job.check = null;
                job.staff = [];
            }
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
            ? await this.orm.call("store.nvbh.check", "get_job_overview", [Number(job.storeId), job.date, job.kind || "nvbh"])
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
        job.editMode = false;
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

    // phiếu đã gửi cấp trên nhưng còn trong hạn sửa (đến 23h55): mặc định chỉ xem, bấm "Chỉnh sửa" mới mở ô tick / ghi chú
    get jobReedit() {
        const c = this.state.job.check;
        return Boolean(c) && c.state !== "draft" && c.can_execute === true;
    }

    get jobInputsLocked() {
        return this.jobLocked || (this.jobReedit && !this.state.job.editMode);
    }

    onJobEdit() {
        this.state.job.editMode = true;
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
            const wasReedit = this.jobReedit;
            this.state.job.check = await this.orm.call("store.nvbh.check", "save_checklist", [check.id, changes]);
            this.state.job.snap = this.jobSnapshot();
            this.state.job.editMode = false;
            if (wasReedit) {
                this.notification.add("Đã lưu chỉnh sửa · phiếu chuyển lại cấp trên đánh giá", { type: "info" });
            }
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
        if (this.state.activeNav === child.id || (child.id === (this.state.job.kind === "cht" ? "nvbh_cht" : "nvbh_jobs") && this.state.activeNav === "nvbh_schedule") || (child.id === "nvbh_mg_staff" && this.state.activeNav === "nvbh_mg_eval")) {
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
            store_id: f.store ? Number(f.store) : (this.state.needStore ? -1 : false),
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
    // các màn danh sách phiếu đánh giá (store.audit) có cột Người đánh giá
    get isAuditListNav() {
        return ["review", "review_list", "asm", "gs"].includes(this.state.activeNav);
    }

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
            && !["violation_stores", "violation_all", "nvbh_done", "nvbh_staff", "nvbh_schedule"].includes(this.state.activeNav)
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
            && ["benchmark", "level", "gs_benchmark", "gs_level", "shift", "nvbh_task", "cht_task", "asm_task", "nvbh_rating"].includes(this.state.activeNav)
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
        return ["benchmark", "gs_benchmark", "nvbh_task", "cht_task", "asm_task"].includes(this.state.activeNav);
    }

    // model + tham số của hàm export_xlsx / import_xlsx (Công việc NVBH không có scope)
    get excelModel() {
        if (this.state.activeNav === "nvbh_schedule") {
            return "store.nvbh.schedule.line";
        }
        if (this.state.activeNav === "cht_task") {
            return "store.cht.task";
        }
        if (this.state.activeNav === "asm_task") {
            return "store.asm.task";
        }
        return this.state.activeNav === "nvbh_task" ? "store.nvbh.task" : "store.audit.template.line";
    }

    excelArgs(extra = []) {
        if (this.state.activeNav === "nvbh_schedule") {
            // xuất theo bộ lọc đang chọn (tháng / cửa hàng / miền); nhập chỉ gửi file
            const month = this.state.listFilters.month;
            return extra.length ? [...extra, month] : [this.listDomain(this.listBase || []), month];
        }
        return ["nvbh_task", "cht_task", "asm_task"].includes(this.state.activeNav) ? extra : [this.benchmarkScope, ...extra];
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
                if (this.isScheduleNav) {
                    // Lịch xếp ca: xem trước các ô sẽ thay đổi, bấm Lưu mới ghi vào hệ thống
                    const data = btoa(bin);
                    const preview = await this.orm.call(this.excelModel, "preview_import_xlsx", this.excelArgs([data]));
                    this.state.schedImport = { data, file: file.name, res: preview, busy: false, filter: "all" };
                    return;
                }
                const run = async () => {
                    try {
                        const res = await this.orm.call(this.excelModel, "import_xlsx", this.excelArgs([btoa(bin)]));
                        this.importDone(res);
                    } catch (error) {
                        this.notifyError(error);
                    }
                };
                if (this.excelModel === "store.audit.template.line") {
                    // Điểm chuẩn: nhập kiểu thay thế -> hỏi trước
                    this.dialog.add(ConfirmationDialog, {
                        title: "Nhập Điểm chuẩn từ Excel",
                        body: `File "${file.name}" sẽ THAY THẾ toàn bộ tiêu chí của mẫu checklist có trong file: tiêu chí không còn trong file sẽ bị xóa, STT đánh lại theo thứ tự dòng trong file. Phiếu đánh giá đã tạo không bị ảnh hưởng. Tiếp tục?`,
                        confirmLabel: "Nhập và thay thế",
                        confirm: run,
                        cancel: () => {},
                    });
                    return;
                }
                await run();
            } catch (error) {
                this.notifyError(error);
            }
        };
        input.click();
    }

    importDone(res) {
        if (res.benchmark || res.label) {
            const warn = res.error_count ? ` · ${res.error_count} dòng lỗi: ${res.errors.slice(0, 3).join("; ")}${res.error_count > 3 ? "…" : ""}` : "";
            const removed = res.removed ? `, xóa ${res.removed} tiêu chí không còn trong file` : "";
            this.notification.add(`Đã nhập ${res.label || "Điểm chuẩn"}: thêm ${res.created}, cập nhật ${res.updated}${removed}${warn}`,
                { type: res.error_count ? "warning" : "success", sticky: Boolean(res.error_count) });
            this.state.viewKey += 1;
            return;
        }
        {
            {
                const warn = res.error_count ? ` · ${res.error_count} dòng lỗi: ${res.errors.slice(0, 3).join("; ")}${res.error_count > 3 ? "…" : ""}` : "";
                const kept = (res.skipped_past || 0) + (res.skipped_locked || 0);
                const keptTxt = kept ? ` · Giữ nguyên ${kept} ô (${res.skipped_past || 0} ô trước ngày ${res.ref_date || "hôm nay"}, ${res.skipped_locked || 0} ô đã check list / lưu / duyệt)` : "";
                this.notification.add(`Đã nhập lịch ca: thêm ${res.created}, cập nhật ${res.updated}${res.unchanged ? `, không đổi ${res.unchanged}` : ""}${res.removed ? `, xóa ${res.removed} ca không còn trong file` : ""}${keptTxt} · Nhân sự: thêm ${res.staff_created || 0}, cập nhật ${res.staff_updated || 0}${warn}`, { type: res.error_count ? "warning" : "success", sticky: Boolean(res.error_count || kept) });
                this.state.viewKey += 1;
                if (this.isScheduleNav) {
                    this.loadSchedule();
                }
            }
        }
    }

    // ---- Xem trước nhập Excel Lịch xếp ca ----
    get schedImportRows() {
        const si = this.state.schedImport;
        const rows = si?.res?.details || [];
        return si.filter === "all" ? rows : rows.filter((r) => r.kind === si.filter);
    }

    schedImportCount(kind) {
        return (this.state.schedImport?.res?.details || []).filter((r) => r.kind === kind).length;
    }

    onSchedImportFilter(kind) {
        this.state.schedImport.filter = kind;
    }

    onSchedImportCancel() {
        this.state.schedImport = null;
    }

    async onSchedImportSave() {
        const si = this.state.schedImport;
        if (!si || si.busy) {
            return;
        }
        si.busy = true;
        try {
            const res = await this.orm.call(this.excelModel, "import_xlsx", this.excelArgs([si.data]));
            this.state.schedImport = null;
            this.importDone(res);
        } catch (error) {
            si.busy = false;
            this.notifyError(error);
        }
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
    // nút "Tổng quan" ở sidebar: ẩn khi ma trận phân quyền không cho Xem mục Tổng quan
    get showOverviewNav() {
        const rights = this.state.rights;
        return !rights || Boolean(rights.overview && rights.overview.read);
    }

    get permKey() {
        const keys = { nvbh_staff: "nvbh_staff", nvbh_jobs: "nvbh_jobs", nvbh_cht: "nvbh_cht", nvbh_schedule: this.state.job.kind === "cht" ? "nvbh_cht" : "nvbh_jobs", nvbh_done: "nvbh_done", nvbh_mg_staff: "nvbh_mg", nvbh_mg_eval: "nvbh_mg" };
        return keys[this.state.activeNav] || this.state.activeNav;
    }

    get canExport() {
        return !["report_flow", "report_flow_nvbh", "nvbh_cht", "nvbh_asmcv", "nvbh_staff", "nvbh_jobs", "nvbh_schedule", "nvbh_done", "nvbh_mg_staff", "nvbh_mg_eval"].includes(this.state.activeNav) && (!this.state.rights || Boolean(this.state.rights[this.permKey]?.export));
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
        if (month && ["nvbh_jobs", "nvbh_cht", "nvbh_schedule", "nvbh_done"].includes(this.state.activeNav)) {
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
        } else if (this.state.needStore && !this.staffScopedNav) {
            if (this.isAuditListNav) {
                // chưa chọn cửa hàng: thấy phiếu của mọi cửa hàng được phân quyền + phiếu do chính mình đánh giá
                // (auditStoreIds = false: không giới hạn cửa hàng -> server tự lọc)
                const ids = this.state.auditStoreIds;
                if (ids === false) {
                    // không thêm điều kiện
                } else if (ids && ids.length) {
                    domain.push("|", ["store_id", "in", ids], ["auditor_id", "=", user.userId]);
                } else {
                    domain.push(["auditor_id", "=", user.userId]);
                }
            } else {
                domain.push(["id", "=", 0]); // user chưa có cửa hàng phụ trách: chưa chọn cửa hàng thì chưa hiện dữ liệu
            }
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
            nvbh_today: `LỊCH CA HÔM NAY · ${new Date().toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}`,
            report_nvbh: "BÁO CÁO CHECKLIST NVBH - PHIẾU KPI CÁ NHÂN",
            report_nsuat: "BÁO CÁO NĂNG SUẤT NVBH THEO TIÊU CHÍ CÔNG VIỆC",
            report_nvbh_perf: `BÁO CÁO HIỆU SUẤT NHÂN VIÊN BÁN HÀNG${this.state.perf.data?.month_label ? " · THÁNG " + this.state.perf.data.month_label : ""}`,
            report_nvbh_asm: `BÁO CÁO QUẢN TRỊ KHU VỰC THEO ASM${this.state.kpiAsm.data?.month_label ? " · THÁNG " + this.state.kpiAsm.data.month_label : ""}`,
            nvbh_done: this.state.done.tab === "total" ? "BẢNG CHECKLIST TỔNG" : "DANH SÁCH CHECKLIST NHÂN VIÊN",
            nvbh_mg_staff: "QUẢN LÝ & ĐÁNH GIÁ CHECKLIST NVBH",
            nvbh_mg_eval: "QUẢN LÝ & ĐÁNH GIÁ CHECKLIST NVBH",
            review: "DANH SÁCH PHIẾU ĐÁNH GIÁ CỬA HÀNG",
            report_gs: "BÁO CÁO GIÁM SÁT CỬA HÀNG",
            violation_stores: "XỬ LÝ LỖI SAI PHẠM CỬA HÀNG",
            violation_all: "DANH SÁCH XỬ LÝ SAI PHẠM",
            report_rank: "BÁO CÁO XẾP LOẠI AUDIT CH",
            report_manager: "BÁO CÁO THEO QUẢN LÝ",
            report_sup: "BÁO CÁO GIÁM SÁT",
            report_flow: "SƠ ĐỒ QUY TRÌNH VẬN HÀNH GIÁM SÁT",
            report_flow_nvbh: "SƠ ĐỒ QUY TRÌNH CHECK LIST NHÂN VIÊN BÁN HÀNG",
            nvbh_cht: "CHECK LIST CÔNG VIỆC CỬA HÀNG TRƯỞNG",
            nvbh_asmcv: "CHECK LIST CÔNG VIỆC ASM",
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

    // user phải chọn cửa hàng mới thấy dữ liệu: mỗi lần mở một màn thì bỏ lựa chọn cửa hàng cũ (không giữ lại từ màn trước)
    resetStorePick() {
        if (!this.state.needStore) {
            return;
        }
        this.state.listFilters.store = "";
        this.state.filters.store = "";
        this.state.done.storeId = "";
        this.state.mg.storeId = "";
        this.state.kpi.storeId = "";
        this.state.job.storeId = "";
    }

    // mục đầu tiên trên sidebar user được phép xem (bỏ qua thư mục)
    firstAllowedChild() {
        for (const sec of this.navSections) {
            const child = (sec.children || []).find((c) => !c.folder);
            if (child) {
                return child;
            }
        }
        return null;
    }

    onOverview() {
        if (!this.showOverviewNav) {
            const first = this.firstAllowedChild();
            if (first) {
                return this.onNavChild(first);
            }
            this.state.activeNav = "";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return;
        }
        this.resetStorePick();
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
        this.resetStorePick();
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
        if (child?.id === "photo_retention") {
            this.track({ child });
            this.state.activeNav = "photo_retention";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return this.loadPhotoRetention();
        }
        if (child?.id === "access") {
            this.track({ child });
            this.state.activeNav = "access";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return this.loadPerm();
        }
        if (child?.id === "nvbh_cht") {
            // Checklist CV CHT: trang Công việc check list ở chế độ CHT (cùng giao diện / tính năng với NVBH)
            this.track({ child });
            return this.openJobsPage("cht");
        }
        if (child?.id === "nvbh_asmcv") {
            // trang riêng (component StoreChtPage tự tải dữ liệu)
            this.track({ child });
            this.state.activeNav = child.id;
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return;
        }
        if (child?.id === "report_flow_nvbh") {
            // trang tĩnh: sơ đồ quy trình checklist NVBH (không có action / dữ liệu cần tải)
            this.track({ child });
            this.state.activeNav = "report_flow_nvbh";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return;
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
        if (this.state.needStore && !this.state.listFilters.store) {
            sc.rows = [];
            sc.empty = "Chọn cửa hàng ở bộ lọc để xem lịch xếp ca.";
            return;
        }
        sc.empty = "";
        sc.loading = true;
        try {
            const res = await this.orm.call("store.nvbh.schedule.line", "get_matrix", [this.listDomain(this.listBase || []), month]);
            sc.ndays = res.ndays;
            sc.pastDays = res.past_days || 0;
            sc.rows = res.rows;
        } catch (error) {
            this.notifyError(error);
        } finally {
            sc.loading = false;
        }
    }

    // Thứ của ngày d trong tháng đang xem (T2 ... T7, CN)
    schedWeekday(d) {
        const month = this.state.listFilters.month;
        if (!month) {
            return "";
        }
        const [y, m] = month.split("-").map(Number);
        return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][new Date(y, m - 1, d).getDay()];
    }

    // class ô ngày trên lưới Lịch xếp ca: ngày đã qua làm mờ (khóa), ô đã check list có ổ khóa, ô vừa đổi do nhập Excel tô màu
    schedCellClass(row, d) {
        const cell = row.days?.[d];
        const cls = [];
        if (d <= (this.state.sched.pastDays || 0)) {
            cls.push("is-past");
        }
        if (cell) {
            cls.push("has-shift");
            if (cell.locked) {
                cls.push("is-locked");
            }
            if (cell.changed) {
                cls.push(cell.prev ? "is-changed" : "is-new");
            }
        }
        return cls.join(" ");
    }

    schedCellTitle(row, d) {
        const cell = row.days?.[d];
        if (d <= (this.state.sched.pastDays || 0)) {
            return "Lịch quá khứ: chỉ xem, không được chỉnh sửa";
        }
        if (!cell) {
            return "";
        }
        if (cell.locked) {
            return "Nhân viên đã check list / bấm Lưu: không được đổi ca";
        }
        if (cell.changed) {
            return cell.prev ? `Đã đổi ca: ${cell.prev} → ${cell.code}` : "Ca mới thêm";
        }
        return "";
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
        const [perm, staffPerm] = await Promise.all([
            this.orm.call("store.perm.rule", "get_rules", []),
            this.orm.call("store.staff.view.rule", "get_rules", []),
        ]);
        this.state.perm = perm;
        this.state.staffPerm = staffPerm;
        this.state.permEdit = null;
        this.state.staffEdit = null;
    }

    // Màn Nhân sự của user có Phân quyền xem nhân sự: không bắt chọn cửa hàng, ô lọc liệt kê đúng cửa hàng được cấp
    get staffScopedNav() {
        return this.state.activeNav === "nvbh_staff" && this.state.staffScope.includes("nvbh_staff");
    }

    get listStoreOptions() {
        if (this.isSupLayout) {
            return this.state.supStores;
        }
        if (this.staffScopedNav && this.state.staffStores.length) {
            return this.state.staffStores;
        }
        return this.state.dash ? this.state.dash.store_options : [];
    }

    // ---- Cài đặt > Lưu trữ hình ảnh & file PDF: xóa cuốn chiếu theo ngày / tháng / năm (2 phần độc lập) ----
    async loadPhotoRetention() {
        try {
            this.state.photoCfg = await this.orm.call("store.photo.retention", "get_settings", []);
            this.state.photoDirty = false;
        } catch (error) {
            this.notifyError(error);
        }
    }

    fmtBytes(n) {
        n = Number(n) || 0;
        const u = ["B", "KB", "MB", "GB", "TB"];
        let i = 0;
        while (n >= 1024 && i < u.length - 1) {
            n /= 1024;
            i += 1;
        }
        return `${i ? n.toFixed(1) : n} ${u[i]}`;
    }

    photoUnitMax(unit) {
        return (this.state.photoCfg?.units || []).find((u) => u.id === unit)?.max || 1;
    }

    photoPayload() {
        const c = this.state.photoCfg;
        const part = (p) => ({ enabled: Boolean(p.enabled), value: Number(p.value), unit: p.unit });
        return { img: part(c.img), pdf: part(c.pdf), batch: Number(c.batch) };
    }

    // Đổi bật/tắt, số hoặc đơn vị của một phần (img / pdf): cập nhật ngay Mốc cuốn chiếu và số lượng sẽ xóa (chưa lưu)
    onPhotoChange(kind, key, value) {
        const c = this.state.photoCfg;
        if (kind === "batch") {
            c.batch = value;
        } else {
            c[kind][key] = value;
            if (key === "unit") {
                c[kind].value = Math.min(Math.max(Number(c[kind].value) || 1, 1), this.photoUnitMax(value));
            }
        }
        this.state.photoDirty = true;
        if (key === "enabled" || kind === "batch") {
            return;
        }
        clearTimeout(this._photoPreviewTimer);
        this._photoPreviewTimer = setTimeout(async () => {
            const p = c[kind];
            if (!(Number(p.value) >= 1 && Number(p.value) <= this.photoUnitMax(p.unit))) {
                return; // số chưa hợp lệ: chờ nhập xong
            }
            try {
                const stats = await this.orm.call("store.photo.retention", "preview", [this.photoPayload()]);
                for (const k of ["img", "pdf"]) {
                    const { enabled, value, unit, ...rest } = stats[k];
                    Object.assign(c[k], rest); // chỉ cập nhật mốc / số lượng, giữ nguyên giá trị đang nhập
                }
            } catch {
                // giá trị đang nhập dở: bỏ qua, sẽ báo khi bấm Lưu
            }
        }, 400);
    }

    async onPhotoSave(silent = false) {
        try {
            this.state.photoCfg = await this.orm.call("store.photo.retention", "save_settings", [this.photoPayload()]);
            this.state.photoDirty = false;
            if (!silent) {
                this.notification.add("Đã lưu cấu hình Lưu trữ hình ảnh & file PDF.", { type: "success" });
            }
            return true;
        } catch (error) {
            this.notifyError(error);
            return false;
        }
    }

    async onPhotoRun(dryRun) {
        const c = this.state.photoCfg;
        if (!c.img.enabled && !c.pdf.enabled) {
            this.notification.add("Hãy bật ít nhất một phần (hình ảnh hoặc file PDF).", { type: "warning" });
            return;
        }
        const parts = [
            c.img.enabled ? `ảnh cột "Hình ảnh" của phiếu trước ${c.img.cutoff}` : "",
            c.pdf.enabled ? `PDF biên bản đã lưu của phiếu trước ${c.pdf.cutoff} (và bản PDF lỗi thời)` : "",
        ].filter(Boolean).join(" và ");
        if (!dryRun && !window.confirm(`Xóa vĩnh viễn ${parts}? Thao tác không hoàn tác được.${this.state.photoDirty ? "\nCấu hình đang sửa sẽ được lưu trước khi chạy." : ""}`)) {
            return;
        }
        if (this.state.photoDirty && !(await this.onPhotoSave(true))) {
            return;
        }
        this.state.photoBusy = true;
        try {
            const res = await this.orm.call("store.photo.retention", "run_purge", [], { dry_run: dryRun, manual: true });
            const img = res.img_on ? `${res.files} ảnh (${this.fmtBytes(res.size)}) của ${res.lines} dòng đánh giá` : "";
            const pdf = res.pdf_on ? `${res.pdfs} PDF (${this.fmtBytes(res.pdf_size)})` : "";
            const what = [img, pdf].filter(Boolean).join(" và ");
            this.notification.add(res.error ? `Lỗi: ${res.error}` : `${dryRun ? "Chạy thử: sẽ xóa" : "Đã xóa"} ${what}.`,
                { type: res.error ? "danger" : "success", sticky: Boolean(res.error) });
            await this.loadPhotoRetention();
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.state.photoBusy = false;
        }
    }

    // ---- Checklist NVBH > Lịch ca hôm nay: lọc Miền / Cửa hàng, In, Xuất Excel ----
    async loadTodayOptions() {
        try {
            const data = await this.orm.call("store.nvbh.schedule.line", "get_today_rows", []);
            Object.assign(this.state.today, { miens: data.miens, stores: data.stores });
        } catch (error) {
            this.notifyError(error);
        }
    }

    get todayStoreOptions() {
        const t = this.state.today;
        return t.stores.filter((st) => !t.mien || st.mien === t.mien);
    }

    onTodayFilter(key, ev) {
        const t = this.state.today;
        t[key] = ev.target.value;
        if (key === "mien" && t.store && !this.todayStoreOptions.some((st) => String(st.id) === t.store)) {
            t.store = ""; // cửa hàng đang chọn không thuộc miền mới
        }
        const domain = [...(this.todayBase || [])];
        if (t.mien) {
            domain.push(["mien", "=", t.mien]);
        }
        if (t.store) {
            domain.push(["store_id", "=", Number(t.store)]);
        }
        this.state.embeddedViewProps = { ...this.state.embeddedViewProps, domain };
        this.state.viewKey += 1;
    }

    async onTodayExport() {
        const t = this.state.today;
        try {
            const file = await this.orm.call("store.nvbh.schedule.line", "export_today_xlsx", [], {
                mien: t.mien || false, store_id: t.store ? Number(t.store) : false,
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

    // Quản lý: gửi ngay Lịch ca hôm nay cho ASM / RSM (cron cũng tự gửi mỗi sáng)
    async onTodayNotify() {
        try {
            const n = await this.orm.call("store.nvbh.schedule.line", "send_today_shift_notify", [], { force: true });
            this.notification.add(n ? `Đã gửi lịch ca hôm nay cho ${n} ASM/RSM.` : "Không có ASM/RSM nào để gửi (chưa có ca hôm nay hoặc chưa xác định được người phụ trách).",
                { type: n ? "success" : "warning" });
        } catch (error) {
            this.notifyError(error);
        }
    }

    // In: mở hộp thoại in của trình duyệt (chọn máy in) với bảng theo bộ lọc đang chọn
    async onTodayPrint() {
        const t = this.state.today;
        try {
            const data = await this.orm.call("store.nvbh.schedule.line", "get_today_rows", [], {
                mien: t.mien || false, store_id: t.store ? Number(t.store) : false,
            });
            if (!data.rows.length) {
                this.notification.add("Không có ca làm việc hôm nay để in", { type: "warning" });
                return;
            }
            this.printPages([{ title: `LỊCH CA HÔM NAY - ${data.date}`, sub: data.subtitle, headers: data.headers, rows: data.rows, foot: null }]);
        } catch (error) {
            this.notifyError(error);
        }
    }

    // ---- Tab "Phân quyền xem nhân sự" ----
    get staffPermList() {
        const q = this.state.staffPermQ.trim().toLowerCase();
        return (this.state.staffPerm?.rules || []).filter((r) => !q
            || [r.name, ...r.users.map((u) => u.name), ...r.menus.map((m) => this.staffMenuLabel(m)), ...r.miens.map((m) => m.name), ...r.stores.map((s) => s.name)]
                .some((t) => (t || "").toLowerCase().includes(q)));
    }

    staffScopeLabel(scope) {
        return { all: "Tất cả nhân sự", mien: "Theo miền", store: "Theo cửa hàng" }[scope] || scope;
    }

    onStaffOpen(rule) {
        this.state.staffEdit = {
            id: rule?.id || 0, name: rule?.name || "", scope: rule?.scope || "store",
            users: [...(rule?.users || [])], miens: (rule?.miens || []).map((m) => m.id), stores: [...(rule?.stores || [])],
            menus: [...(rule?.menus || ["nvbh_staff"])], storeQ: "",
        };
    }

    // Cửa hàng (đã lọc theo ô tìm) gom theo miền để tích chọn
    get staffStoreGroups() {
        const q = (this.state.staffEdit?.storeQ || "").trim().toLowerCase();
        const p = this.state.staffPerm;
        const groups = [...p.miens, { id: "", name: "Chưa có miền" }].map((m) => ({
            id: m.id || "none", name: m.name,
            stores: p.stores.filter((st) => (st.mien || "") === m.id && (!q || st.name.toLowerCase().includes(q))),
        }));
        return groups.filter((g) => g.stores.length);
    }

    staffStoreChecked(id) {
        return this.state.staffEdit.stores.some((x) => x.id === id);
    }

    onStaffStore(st, ev) {
        const e = this.state.staffEdit;
        e.stores = e.stores.filter((x) => x.id !== st.id);
        if (ev.target.checked) {
            e.stores.push({ id: st.id, name: st.name });
        }
    }

    onStaffStoreGroup(g, ev) {
        for (const st of g.stores) {
            this.onStaffStore(st, ev);
        }
    }

    staffStoresAllChecked() {
        const groups = this.staffStoreGroups;
        return groups.length > 0 && groups.every((g) => g.stores.every((x) => this.staffStoreChecked(x.id)));
    }

    onStaffStoreAll(ev) {
        for (const g of this.staffStoreGroups) {
            this.onStaffStoreGroup(g, ev);
        }
    }

    staffMenuLabel(id) {
        return this.state.staffPerm?.menus.find((m) => m.id === id)?.name || id;
    }

    onStaffMenu(id, ev) {
        const e = this.state.staffEdit;
        e.menus = ev.target.checked ? [...new Set([...e.menus, id])] : e.menus.filter((m) => m !== id);
    }

    onStaffMenuAll(ev) {
        this.state.staffEdit.menus = ev.target.checked ? this.state.staffPerm.menus.map((m) => m.id) : [];
    }

    onStaffClose() {
        this.state.staffEdit = null;
    }

    onStaffUserAdd(ev) {
        const e = this.state.staffEdit;
        const u = this.state.perm.users.find((x) => x.name === ev.target.value.trim());
        ev.target.value = "";
        if (u && !e.users.some((x) => x.id === u.id)) {
            e.users.push(u);
        }
    }

    onStaffUserRemove(u) {
        this.state.staffEdit.users = this.state.staffEdit.users.filter((x) => x.id !== u.id);
    }

    onStaffMien(id, ev) {
        const e = this.state.staffEdit;
        e.miens = ev.target.checked ? [...new Set([...e.miens, id])] : e.miens.filter((m) => m !== id);
    }

    async onStaffSave() {
        const e = this.state.staffEdit;
        if (!e.users.length) {
            return this.notification.add("Chọn ít nhất một user.", { type: "warning" });
        }
        if (!e.menus.length) {
            return this.notification.add("Chọn ít nhất một mục áp dụng.", { type: "warning" });
        }
        if (e.scope === "mien" && !e.miens.length) {
            return this.notification.add("Chọn ít nhất một miền.", { type: "warning" });
        }
        if (e.scope === "store" && !e.stores.length) {
            return this.notification.add("Chọn ít nhất một cửa hàng.", { type: "warning" });
        }
        await this.orm.call("store.staff.view.rule", "save_rule", [{
            id: e.id, name: e.name.trim(), scope: e.scope,
            user_ids: e.users.map((u) => u.id), miens: e.miens, store_ids: e.stores.map((s) => s.id), menu_keys: e.menus,
        }]);
        this.notification.add("Đã lưu phân quyền xem nhân sự.", { type: "success" });
        return this.loadPerm();
    }

    async onStaffDelete(rule) {
        if (!window.confirm("Xóa phân quyền xem nhân sự này?")) {
            return;
        }
        await this.orm.call("store.staff.view.rule", "delete_rule", [rule.id]);
        return this.loadPerm();
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

    // Các nhóm quyền KHÁC có chung user với nhóm đang sửa (quyền được cộng dồn: chỉ cần một nhóm cho phép là user thấy)
    get permOverlaps() {
        const e = this.state.permEdit;
        if (!e) {
            return [];
        }
        const ids = new Set(e.users.map((u) => u.id));
        return (this.state.perm?.rules || [])
            .filter((r) => r.id !== e.id)
            .map((r) => ({ rule: r, users: r.users.filter((u) => ids.has(u.id)) }))
            .filter((o) => o.users.length)
            .map((o) => ({ ...o, label: o.rule.group || o.rule.users.map((u) => u.name).join(", ") }));
    }

    // tên các nhóm khác đang cho phép quyền này (cho user của nhóm đang sửa)
    permOtherGrant(key, op) {
        return this.permOverlaps.filter((o) => o.rule.perms?.[key]?.[op]).map((o) => o.label);
    }

    onPermOpenOther(rule) {
        this.onPermOpen(rule);
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
            return this.openJobsPage("nvbh");
        }
        if (navId === "report_nvbh" || navId === "report_nsuat") {
            return this.openKpiPage(navId === "report_nsuat" ? "productivity" : "kpi");
        }
        if (navId === "report_nvbh_asm") {
            return this.openKpiAsmPage();
        }
        if (navId === "report_nvbh_perf") {
            return this.openPerfPage();
        }
        if (navId === "nvbh_cht") {
            return this.openJobsPage("cht");
        }
        if (navId === "nvbh_asmcv") {
            this.state.activeNav = navId;
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return;
        }
        if (navId === "report_flow_nvbh") {
            this.state.activeNav = "report_flow_nvbh";
            this.state.contentMode = "list";
            this.state.embeddedViewProps = null;
            return;
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
        // group_by trong context của action (vd. Danh sách công việc CHT): View nhúng chỉ nhận qua prop groupBy
        const ctxGroupBy = viewProps.context.group_by;
        if (type === "list" && ctxGroupBy && ctxGroupBy.length) {
            viewProps.groupBy = Array.isArray(ctxGroupBy) ? ctxGroupBy : [ctxGroupBy];
        }
        // đặt màn hiện tại trước khi tính domain lọc: listDomain chọn trường ngày (audit_date / work_date) theo activeNav
        this.state.activeNav = navId;
        if (navId === "shift") {
            // Danh mục ca làm việc: mỗi tab = một loại ca
            this.listBase = viewProps.domain;
            viewProps.domain = this.shiftDomain();
            this.loadShiftStats();
        }
        if (navId === "nvbh_today") {
            this.todayBase = viewProps.domain;
            Object.assign(this.state.today, { mien: "", store: "" });
            this.loadTodayOptions();
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
        if (navId === "nvbh_today") {
            return; // Lịch ca hôm nay chỉ để xem
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
        if (!["benchmark", "review", "review_list", "level", "nvbh_jobs", "gs_benchmark", "gs_level", "shift", "nvbh_task", "cht_task", "asm_task", "nvbh_rating", "nvbh", "asm", "gs", "report_gs", "violation_stores", "violation_all"].includes(navId)) {
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
