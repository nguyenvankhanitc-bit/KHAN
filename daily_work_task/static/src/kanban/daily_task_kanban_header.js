/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanHeader } from "@web/views/kanban/kanban_header";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

patch(KanbanHeader.prototype, {
    get isDailyTaskKanban() {
        const list = this.props.list;
        return list?.resModel === "daily.task" || list?.model?.config?.resModel === "daily.task";
    },
});

patch(KanbanRenderer.prototype, {
    getGroupClasses(group, isGroupProcessing) {
        let classes = super.getGroupClasses(group, isGroupProcessing);
        const resModel =
            this.props.list?.resModel || this.props.list?.model?.config?.resModel;
        if (resModel === "daily.task") {
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
