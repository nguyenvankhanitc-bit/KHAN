/** @odoo-module **/

export const SIDEBAR_WIDTH_KEY = "sidebar_custom_width";
export const SIDEBAR_COLLAPSED_KEY = "sidebar_collapsed";
export const SIDEBAR_MIN = 200;
export const SIDEBAR_MAX = 420;
export const SIDEBAR_DEFAULT = 260;
export const SIDEBAR_COLLAPSED_WIDTH = 70;

export function clampWidth(value) {
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n)) {
        return SIDEBAR_DEFAULT;
    }
    return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n));
}

export function loadSidebarWidth() {
    try {
        return clampWidth(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
    } catch {
        return SIDEBAR_DEFAULT;
    }
}

export function loadSidebarCollapsed() {
    try {
        return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    } catch {
        return false;
    }
}

export function saveSidebarWidth(width) {
    try {
        window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clampWidth(width)));
    } catch {
        /* private mode / quota */
    }
}

export function saveSidebarCollapsed(collapsed) {
    try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
        /* private mode / quota */
    }
}

function effectiveWidth(width, collapsed) {
    return collapsed ? SIDEBAR_COLLAPSED_WIDTH : clampWidth(width);
}

/**
 * Sidebar sits inside the current action (CSS grid / flex), not as a fixed overlay.
 * Width is written on the sidebar; the main pane follows via --phan-he-sidebar-width
 * (grid-template-columns) which is the equivalent of action-manager margin-left.
 */
export function applySidebarLayout(width, collapsed) {
    const px = effectiveWidth(width, collapsed);
    const cssPx = `${px}px`;
    const root = document.documentElement;
    root.style.setProperty("--phan-he-sidebar-width", cssPx);
    root.classList.toggle("o_phan_he_sidebar_is_collapsed", Boolean(collapsed));

    document.querySelectorAll(".o_phan_he_app_sidebar, .o_phan_he_sidebar").forEach((el) => {
        el.style.width = cssPx;
        el.style.minWidth = cssPx;
        el.style.maxWidth = cssPx;
    });

    document.querySelectorAll(".o_phan_he_app_shell").forEach((el) => {
        el.style.gridTemplateColumns = `${cssPx} minmax(0, 1fr)`;
    });

    document.querySelectorAll(".o_phan_he_shell > .o_phan_he_dashboard").forEach((el) => {
        el.style.marginLeft = "0";
        el.style.minWidth = "0";
        el.style.flex = "1 1 auto";
    });
}

export function goBack() {
    window.history.back();
}

export function isFullscreen() {
    return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
}

export async function toggleFullscreen() {
    try {
        if (!isFullscreen()) {
            const el = document.documentElement;
            if (el.requestFullscreen) {
                await el.requestFullscreen();
            } else if (el.webkitRequestFullscreen) {
                el.webkitRequestFullscreen();
            }
        } else if (document.exitFullscreen) {
            await document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        }
    } catch (error) {
        console.warn("Fullscreen toggle failed", error);
    }
}

applySidebarLayout(loadSidebarWidth(), loadSidebarCollapsed());
