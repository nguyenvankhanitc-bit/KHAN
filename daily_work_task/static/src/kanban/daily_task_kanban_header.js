/** @odoo-module **/

import { onMounted, onPatched } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { KanbanHeader } from "@web/views/kanban/kanban_header";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

function isDailyTaskKanbanList(list) {
    return list?.resModel === "daily.task" || list?.model?.config?.resModel === "daily.task";
}

function enableDailyKanbanMobileScroll(rootEl) {
    if (!rootEl || typeof window === "undefined" || window.innerWidth > 768) {
        return;
    }
    const content = rootEl.closest(".o_content");
    const action = rootEl.closest(".o_action, .o_kanban_view");
    if (action) {
        action.style.minHeight = "0";
        action.style.overflow = "hidden";
        action.style.display = "flex";
        action.style.flexDirection = "column";
        action.style.height = "100%";
    }
    if (content) {
        content.style.minHeight = "0";
        content.style.flex = "1 1 0px";
        content.style.height = "auto";
        content.style.maxHeight = "calc(100dvh - 8.5rem)";
        content.style.overflowY = "scroll";
        content.style.overflowX = "hidden";
        content.style.webkitOverflowScrolling = "touch";
        content.style.touchAction = "pan-y";
    }
    rootEl.style.setProperty("height", "auto", "important");
    rootEl.style.setProperty("max-height", "none", "important");
    rootEl.style.setProperty("overflow", "visible", "important");
    rootEl.style.setProperty("overflow-x", "hidden", "important");
    rootEl.style.setProperty("overflow-y", "visible", "important");
    rootEl.style.setProperty("scroll-snap-type", "none", "important");
    rootEl.style.setProperty("flex-direction", "column", "important");
    rootEl.style.setProperty("flex-wrap", "nowrap", "important");
    rootEl.querySelectorAll(".o_kanban_group").forEach((groupEl, index) => {
        groupEl.style.setProperty("overflow", "visible", "important");
        groupEl.style.setProperty("overflow-y", "visible", "important");
        groupEl.style.setProperty("max-height", "none", "important");
        groupEl.style.setProperty("height", "auto", "important");
        groupEl.style.setProperty("flex", "0 0 auto", "important");
        groupEl.style.setProperty("min-width", "100%", "important");
        groupEl.style.setProperty("max-width", "100%", "important");
        groupEl.style.setProperty("width", "100%", "important");
        groupEl.style.setProperty("scroll-snap-align", "none", "important");
        groupEl.classList.add("o_daily_kdrop");
        if (!groupEl.dataset.dailyDropInit) {
            groupEl.dataset.dailyDropInit = "1";
            groupEl.classList.add("is-collapsed");
            const header = groupEl.querySelector(".o_kanban_header");
            if (header) {
                header.addEventListener("click", (ev) => {
                    if (ev.target.closest(".o_group_config, .dropdown, .dropdown-menu, .o_kanban_quick_add, button")) {
                        return;
                    }
                    ev.preventDefault();
                    ev.stopPropagation();
                    groupEl.classList.toggle("is-collapsed");
                });
            }
        }
    });
}

patch(KanbanHeader.prototype, {
    get isDailyTaskKanban() {
        return isDailyTaskKanbanList(this.props.list);
    },
});

patch(KanbanRenderer.prototype, {
    setup() {
        super.setup();
        const syncScroll = async () => {
            if (!isDailyTaskKanbanList(this.props.list)) {
                return;
            }
            const list = this.props.list;
            if (
                !this._dailyKanbanUnfolded
                && typeof window !== "undefined"
                && window.innerWidth <= 768
                && list?.groups
            ) {
                this._dailyKanbanUnfolded = true;
                for (const group of list.groups) {
                    if (group.isFolded && typeof group.toggle === "function") {
                        await group.toggle();
                    }
                }
            }
            enableDailyKanbanMobileScroll(this.rootRef?.el);
        };
        onMounted(syncScroll);
        onPatched(syncScroll);
    },

    getGroupClasses(group, isGroupProcessing) {
        let classes = super.getGroupClasses(group, isGroupProcessing);
        if (isDailyTaskKanbanList(this.props.list)) {
            const raw = group.value;
            const key =
                Array.isArray(raw) && raw.length
                    ? raw[0]
                    : raw === false || raw === undefined
                      ? "false"
                      : String(raw);
            classes = `${classes} o_daily_kcol_${key}`.trim();
        }
        return classes;
    },
});
