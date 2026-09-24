/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { View } from "@web/views/view";

const WIDTH_KEY = "o_internet_sidebar_width_v3";
const COLLAPSED_KEY = "o_internet_sidebar_collapsed";
const MIN_W = 240;
const MAX_W = 340;
const DEFAULT_W = 280;
const COLLAPSED_W = 65;
const FIT_PAD = 36;

function clampWidth(value) {
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n)) {
        return DEFAULT_W;
    }
    return Math.min(MAX_W, Math.max(MIN_W, n));
}

function loadWidth() {
    try {
        const stored = window.localStorage.getItem(WIDTH_KEY);
        if (stored == null) {
            return DEFAULT_W;
        }
        return clampWidth(stored);
    } catch {
        return DEFAULT_W;
    }
}

function loadCollapsed() {
    try {
        return window.localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch {
        return false;
    }
}

function navFingerprint(sections) {
    if (!Array.isArray(sections)) {
        return "";
    }
    return sections
        .map((s) => `${s.id}:${s.label}:${(s.children || []).map((c) => c.label).join(",")}`)
        .join("|");
}

export class PhanHeInternetShell extends Component {
    static template = "lug_phan_he.PhanHeInternetShell";
    static components = { View };
    static props = {
        brand: { type: String, optional: true },
        moduleCode: { type: String, optional: true },
        navSections: { type: Array, optional: true },
        openGroups: { type: Object, optional: true },
        activeNav: { type: String, optional: true },
        alertCount: { type: Number, optional: true },
        badgeData: { type: Object, optional: true },
        contentMode: { type: String, optional: true },
        showOverview: { type: Boolean, optional: true },
        embeddedViewProps: { optional: true },
        viewKey: { type: [String, Number], optional: true },
        onOverview: Function,
        onToggleGroup: Function,
        onNavChild: Function,
        isGroupOpen: Function,
        navChildClass: Function,
        slots: { type: Object, optional: true },
    };

    setup() {
        this.rootRef = useRef("shellRoot");
        this.state = useState({
            sidebarWidth: loadWidth(),
            collapsed: loadCollapsed(),
            dragging: false,
            mobileNavOpen: false,
            isMobile: false,
        });
        this._navFp = "";
        this._onMove = this._onMove.bind(this);
        this._onUp = this._onUp.bind(this);
        this._onMqChange = this._onMqChange.bind(this);
        onMounted(() => {
            this._mq = window.matchMedia("(max-width: 991.98px)");
            this._onMqChange();
            if (this._mq.addEventListener) {
                this._mq.addEventListener("change", this._onMqChange);
            } else if (this._mq.addListener) {
                this._mq.addListener(this._onMqChange);
            }
            this._autofitSidebarWidth();
        });
        onPatched(() => {
            const fp = navFingerprint(this.props.navSections);
            if (fp !== this._navFp) {
                this._navFp = fp;
                this._autofitSidebarWidth();
            }
        });
        onWillUnmount(() => {
            this._stopResize();
            if (this._mq) {
                if (this._mq.removeEventListener) {
                    this._mq.removeEventListener("change", this._onMqChange);
                } else if (this._mq.removeListener) {
                    this._mq.removeListener(this._onMqChange);
                }
            }
            document.body.classList.remove("o_internet_mobile_nav_lock");
        });
    }

    _onMqChange() {
        const isMobile = !!(this._mq && this._mq.matches);
        this.state.isMobile = isMobile;
        if (!isMobile) {
            this.closeMobileNav();
        }
    }

    get shellClassName() {
        const parts = [];
        if (this.state.collapsed && !this.state.isMobile) {
            parts.push("is-sidebar-collapsed");
        }
        parts.push(this.props.contentMode === "view" ? "is-detail" : "is-overview");
        if (this.props.moduleCode === "internet") {
            parts.push("is-internet-nav");
        }
        if (this.state.isMobile) {
            parts.push("is-mobile-layout");
        }
        if (this.state.mobileNavOpen) {
            parts.push("is-mobile-nav-open");
        }
        return parts.join(" ");
    }

    get showOverview() {
        return this.props.showOverview !== false;
    }

    get showBack() {
        return this.props.contentMode === "view" || this.props.activeNav !== "overview";
    }

    get sidebarStyle() {
        if (this.state.isMobile) {
            return "--o-internet-sidebar-width: 0px";
        }
        const w = this.state.collapsed ? COLLAPSED_W : this.state.sidebarWidth;
        return `--o-internet-sidebar-width: ${w}px`;
    }

    openMobileNav() {
        this.state.mobileNavOpen = true;
        this.state.collapsed = false;
        document.body.classList.add("o_internet_mobile_nav_lock");
    }

    closeMobileNav() {
        this.state.mobileNavOpen = false;
        document.body.classList.remove("o_internet_mobile_nav_lock");
    }

    onOverviewClick() {
        this.props.onOverview();
        this.closeMobileNav();
    }

    onNavChildClick(child) {
        this.props.onNavChild(child);
        this.closeMobileNav();
    }

    /**
     * Đo theo nội dung chữ (không dùng width 100% của hàng — sẽ bị ảo rộng).
     */
    _autofitSidebarWidth() {
        if (this.state.isMobile || this.state.collapsed || this.state.dragging) {
            return;
        }
        const root = this.rootRef.el;
        if (!root) {
            return;
        }
        const aside = root.querySelector(".o_internet_sidebar");
        if (!aside) {
            return;
        }
        const rows = aside.querySelectorAll(
            ".o_phan_he_sidebar_brand, .o_phan_he_nav_item, .o_phan_he_nav_section, .o_phan_he_nav_sub"
        );
        let needed = DEFAULT_W;
        for (const row of rows) {
            const prevWidth = row.style.width;
            const prevMin = row.style.minWidth;
            row.style.width = "max-content";
            row.style.minWidth = "max-content";
            needed = Math.max(needed, row.scrollWidth + FIT_PAD);
            row.style.width = prevWidth;
            row.style.minWidth = prevMin;
        }
        needed = clampWidth(needed);
        // Chỉ chỉnh khi lệch rõ (tránh nhảy liên tục).
        if (Math.abs(needed - this.state.sidebarWidth) >= 8) {
            this.state.sidebarWidth = needed;
            try {
                window.localStorage.setItem(WIDTH_KEY, String(needed));
            } catch {
                /* ignore */
            }
        }
    }

    badgeValue(child) {
        if (!child?.badgeKey) {
            return 0;
        }
        return (this.props.badgeData && this.props.badgeData[child.badgeKey]) || 0;
    }

    badgeClass(child) {
        const n = Number(this.badgeValue(child) || 0);
        if (!n) {
            return "is-muted";
        }
        if (child.tone === "danger") {
            return "is-danger";
        }
        if (child.tone === "warn") {
            return "is-warn";
        }
        return "is-muted";
    }

    showSectionChildren(section) {
        if (this.state.isMobile || this.state.mobileNavOpen) {
            return this.props.isGroupOpen(section.id);
        }
        return this.state.collapsed || this.props.isGroupOpen(section.id);
    }

    sectionCaretClass(section) {
        if (this.props.isGroupOpen(section.id)) {
            return "fa fa-angle-up o_phan_he_nav_caret";
        }
        if (section.id === "settings") {
            return "fa fa-angle-right o_phan_he_nav_caret";
        }
        return "fa fa-angle-down o_phan_he_nav_caret";
    }

    onToggle() {
        this.state.collapsed = !this.state.collapsed;
        try {
            window.localStorage.setItem(COLLAPSED_KEY, this.state.collapsed ? "1" : "0");
        } catch {
            /* ignore */
        }
        if (!this.state.collapsed) {
            // Đợi layout mở rộng rồi đo lại chữ.
            requestAnimationFrame(() => this._autofitSidebarWidth());
        }
    }

    toggleSidebar() {
        this.onToggle();
    }

    onBack() {
        this.props.onOverview();
    }

    onBackToDashboard() {
        this.onBack();
    }

    onResizeStart(ev) {
        if (this.state.collapsed) {
            ev.preventDefault();
            return;
        }
        ev.preventDefault();
        this.state.dragging = true;
        this._startX = ev.clientX;
        this._startW = this.state.sidebarWidth;
        document.documentElement.classList.add("o_internet_resizing");
        window.addEventListener("mousemove", this._onMove);
        window.addEventListener("mouseup", this._onUp);
    }

    _onMove(ev) {
        if (!this.state.dragging) {
            return;
        }
        const next = clampWidth(this._startW + (ev.clientX - this._startX));
        this.state.sidebarWidth = next;
    }

    _onUp() {
        if (!this.state.dragging) {
            return;
        }
        this._stopResize();
        try {
            window.localStorage.setItem(WIDTH_KEY, String(this.state.sidebarWidth));
        } catch {
            /* ignore */
        }
    }

    _stopResize() {
        this.state.dragging = false;
        document.documentElement.classList.remove("o_internet_resizing");
        window.removeEventListener("mousemove", this._onMove);
        window.removeEventListener("mouseup", this._onUp);
    }
}
