/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { evaluateExpr } from "@web/core/py_js/py";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { View } from "@web/views/view";
import { StoreMgrDetailDialog, StoreViolPickDialog } from "@store_checklist/violation/violation_header";
import { PhanHeInternetShell } from "@lug_phan_he/internet_shell/phan_he_internet_shell";

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
    static components = { PhanHeInternetShell, View };
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
            openGroups: { audit: true, evaluation: true, supervision: true, settings: true },
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
            mgrFilter: "",
            mgrPage: 0,
            personal: null,
            canCreate: false,
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
        });
        onWillUnmount(() => {
            sideObserver?.disconnect();
            window.removeEventListener("resize", syncSidebarWidth);
            document.removeEventListener("mousedown", gripSidebar, true);
            document.documentElement.style.removeProperty("--store-sidebar-w");
        });
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
            this.state.badges.violation_stores = await this.orm.searchCount("store.audit", [["state", "!=", "draft"], ["error_count", ">", 0]]);
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
                    { id: "report_store", label: "Báo cáo theo cửa hàng", icon: "fa-building" },
                    { id: "report_rank", label: "Báo cáo xếp loại", icon: "fa-trophy" },
                    { id: "report_manager", label: "Báo cáo theo quản lý", icon: "fa-user" },
                    { id: "report_flow", label: "Sơ đồ quy trình vận hành", icon: "fa-sitemap" },
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
                sec.children = sec.children.filter((c) => rights[c.id]?.read);
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
            const vis = (list) => (rights ? list.filter((c) => rights[c.id]?.read) : list);
            const evalVis = vis(evaluation), supVis = vis(supervision);
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

    navChildClass(child) {
        const cls = ["store-tn-" + child.id];
        if (this.state.activeNav === child.id) {
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
        this.state.dash = await this.orm.call("store.audit", "get_dashboard_data", [], {
            month: f.month || false,
            mien: f.mien || false,
            store_id: f.store ? Number(f.store) : false,
        });
        f.month = this.state.dash.month;
    }

    // Các danh sách phiếu (Checklist NVBH / ASM / GS và Danh Sách Đánh Giá) có thanh lọc tháng / cửa hàng / miền
    get filterNavs() {
        return ["review", "review_list", "nvbh", "asm", "gs", "violation_stores", "violation_all", ...this.reportNavs];
    }

    get reportNavs() {
        return ["report_gs", "report_store", "report_rank", "report_manager", "report_flow"];
    }

    // Nút "Thêm mới" riêng của module (thanh bộ lọc), không phụ thuộc nút mặc định của Odoo ở thanh điều khiển
    get showOwnAdd() {
        return Boolean(
            this.showListFilters
            && !this.reportNavs.includes(this.state.activeNav)
            && !["violation_stores", "violation_all"].includes(this.state.activeNav)
            && this.state.canCreate
            && (!this.state.rights || this.state.rights[this.state.activeNav]?.create)
            && this.state.embeddedViewProps
        );
    }

    // Điểm chuẩn / Mức đánh giá (Cài đặt, chỉ Quản lý): các màn mở phiếu trong hộp thoại, cũng dùng nút riêng
    get showSettingsAdd() {
        return Boolean(
            (this.state.isManager || this.state.rights?.[this.state.activeNav]?.create)
            && this.state.embeddedViewProps
            && ["benchmark", "level", "gs_benchmark", "gs_level"].includes(this.state.activeNav)
        );
    }

    onAddNew() {
        this.state.embeddedViewProps?.createRecord?.();
    }

    get canExport() {
        return this.state.activeNav !== "report_flow" && (!this.state.rights || Boolean(this.state.rights[this.state.activeNav]?.export));
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
        if (month) {
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
            review: "DANH SÁCH PHIẾU ĐÁNH GIÁ CỬA HÀNG",
            report_gs: "BÁO CÁO GIÁM SÁT CỬA HÀNG",
            violation_stores: "XỬ LÝ LỖI SAI PHẠM CỬA HÀNG",
            violation_all: "DANH SÁCH XỬ LÝ SAI PHẠM",
            report_rank: "Báo cáo xếp loại",
            report_manager: "BÁO CÁO THEO QUẢN LÝ",
            report_flow: "SƠ ĐỒ QUY TRÌNH VẬN HÀNH",
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
                    const td = el("td", ([0, 3, 4, 7, 10, 11].includes(i) ? "n " : "") + (grp === 2 ? "g2" : ""), i === 6 ? "" : String(v));
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
        return [["audit_type", "=", "gs"], ["state", "!=", "draft"]];
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
            return;
        }
        if (this.state.activeNav === "report_store") {
            return this.loadStoreReport();
        }
        if (this.isPersonal) {
            this.state.personal = await this.orm.call("store.audit", "get_report_personal", [this.state.listFilters.month || false]);
            return;
        }
        const month = this.state.listFilters.month;
        let prev = false;
        if (month) {
            const [y, m] = month.split("-").map(Number);
            prev = this.listDomain(this.reportBase, `${m === 1 ? y - 1 : y}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}`);
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
        const rows = this.state.dash?.todo_rows || [];
        return this.state.showAllTodo ? rows : rows.slice(0, 5);
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
        const W = 520, H = 190, L = 40, R = 16, T = 16, B = 28;
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
        try {
            const act = await this.action.loadAction(xmlid);
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

    openRecord(act, navId, resId) {
        if (navId === "violation_stores" && resId) {
            return this.openViolation(resId);
        }
        if (navId === "violation_all" && resId) {
            // bấm dòng lỗi thì mở popup xử lý sai phạm của biên bản chứa dòng đó
            return this.orm.read("store.audit.action", [resId], ["audit_id"]).then(([row]) => row && this.openViolation(row.audit_id[0]));
        }
        if (!["benchmark", "review", "review_list", "level", "gs_benchmark", "gs_level", "nvbh", "asm", "gs", "report_gs", "violation_stores", "violation_all"].includes(navId)) {
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
                context: { ...this.evalActionValue(act.context, {}), dialog_size: "extra-large" },
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
