/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState, useSubEnv, Component, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { formatDate } from "@web/core/l10n/dates";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const DASHBOARD_BY_SERVICE = {
    internet: "lug_phan_he.action_phan_he_dashboard",
    camera: "lug_phan_he.action_phan_he_dashboard_camera",
    attendance: "lug_phan_he.action_phan_he_dashboard_attendance",
    linkq_hrm: "lug_phan_he.action_phan_he_dashboard_linkq_hrm",
    linkq_nb: "lug_phan_he.action_phan_he_dashboard_linkq_nb",
    server: "lug_phan_he.action_phan_he_dashboard_server",
};

function formatMoneyVn(amount) {
    return `${new Intl.NumberFormat("vi-VN").format(Math.round(Number(amount || 0)))} VNĐ`;
}

export class PhanHeExpandToggleField extends Component {
    static template = "lug_phan_he.ExpandToggleField";
    static props = { ...standardFieldProps };

    get expanded() {
        return this.env.phanHeTracking?.isExpanded(this.props.record) || false;
    }

    onToggle(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.env.phanHeTracking?.toggle(this.props.record);
    }
}

registry.category("fields").add("phan_he_expand_toggle", {
    component: PhanHeExpandToggleField,
    supportedTypes: ["boolean", "integer", "char"],
});

export class PhanHeSttField extends Component {
    static template = "lug_phan_he.SttField";
    static props = { ...standardFieldProps };

    get stt() {
        const live = this.env.phanHeTracking?.getStt?.(this.props.record);
        if (live != null && live !== "") {
            return live;
        }
        const stored = this.props.record?.data?.stt;
        return stored || "—";
    }
}

registry.category("fields").add("phan_he_stt", {
    component: PhanHeSttField,
    supportedTypes: ["integer"],
});

export class PhanHeTrackingListRenderer extends ListRenderer {
    static rowsTemplate = "lug_phan_he.TrackingRows";
    static groupRowTemplate = "lug_phan_he.TrackingGroupRow";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.expandedMap = useState({});
        this.mienStats = useState({ by_mien: {}, totals: {} });
        useSubEnv({
            phanHeTracking: {
                isExpanded: (record) => this.isExpanded(record),
                toggle: (record) => this.toggleExpand(record),
                getStt: (record) => this.getStt(record),
            },
        });
        onWillStart(() => this.loadMienStats(this.props.list.domain));
        onWillUpdateProps((nextProps) => {
            const prev = JSON.stringify(this.props.list.domain || []);
            const next = JSON.stringify(nextProps.list.domain || []);
            if (prev !== next) {
                return this.loadMienStats(nextProps.list.domain);
            }
        });
    }

    _isSameRecord(a, b) {
        if (!a || !b) {
            return false;
        }
        if (a.resId && b.resId) {
            return a.resId === b.resId;
        }
        return a.id === b.id;
    }

    /**
     * STT theo thứ tự hiển thị:
     * - Có group miền: 1..n trong từng nhóm
     * - Không group: 1..n theo trang (cộng offset phân trang)
     */
    getStt(record) {
        const root = this.props.list;
        const indexIn = (records, offset = 0) => {
            const idx = (records || []).findIndex((r) => this._isSameRecord(r, record));
            return idx >= 0 ? offset + idx + 1 : null;
        };

        if (root.isGrouped) {
            for (const group of root.groups || []) {
                if (group.list?.isGrouped) {
                    for (const sub of group.list.groups || []) {
                        const n = indexIn(sub.list?.records);
                        if (n != null) {
                            return n;
                        }
                    }
                } else {
                    const n = indexIn(group.list?.records);
                    if (n != null) {
                        return n;
                    }
                }
            }
            return record.data?.stt || "—";
        }

        const n = indexIn(root.records, root.offset || 0);
        if (n != null) {
            return n;
        }
        return record.data?.stt || "—";
    }

    async loadMienStats(domain) {
        const data = await this.orm.call("phan.he.service", "get_tracking_mien_stats", [domain || []]);
        this.mienStats.by_mien = data.by_mien || {};
        this.mienStats.totals = data.totals || {};
    }

    isExpanded(record) {
        const key = record.resId || record.id;
        return !!this.expandedMap[key];
    }

    toggleExpand(record) {
        const key = record.resId || record.id;
        this.expandedMap[key] = !this.expandedMap[key];
    }

    getRowClass(record) {
        let classNames = super.getRowClass(record);
        classNames += " o_phan_he_tracking_row";
        if (this.props.list.isGrouped || this.env.model?.root?.isGrouped) {
            classNames += " o_phan_he_child_row";
        }
        if (this.isExpanded(record)) {
            classNames += " is-expanded";
        }
        const hasEnd = !!record.data?.date_end;
        if (hasEnd) {
            const days = Number(record.data.remaining_days);
            if (!Number.isNaN(days)) {
                if (days <= 0) {
                    classNames += " o_phan_he_row_danger";
                } else if (days <= 30) {
                    classNames += " o_phan_he_row_warn";
                }
            }
        }
        return classNames;
    }

    getGroupMienId(group) {
        const value = group.value;
        if (Array.isArray(value)) {
            return value[0] || 0;
        }
        return value || 0;
    }

    getGroupStats(group) {
        const mid = this.getGroupMienId(group);
        const stats = this.mienStats.by_mien[String(mid)] || this.mienStats.by_mien[mid] || {};
        const amount = stats.amount != null
            ? stats.amount
            : (group.aggregates && group.aggregates.contract_amount) || 0;
        return {
            id: mid,
            name: (stats.name || group.displayName || "MIỀN").toUpperCase(),
            color: stats.color || "#64748b",
            count: stats.count != null ? stats.count : group.count || 0,
            amount,
            expire_soon: stats.expire_soon || 0,
            overdue: stats.overdue || 0,
        };
    }

    getGroupHeaderClass(group) {
        const stats = this.getGroupStats(group);
        const classes = ["o_phan_he_group_header"];
        if (stats.overdue > 0) {
            classes.push("is-danger");
        } else if (stats.expire_soon > 0) {
            classes.push("is-warn");
        } else {
            classes.push("is-ok");
        }
        if (!group.isFolded) {
            classes.push("is-open");
        }
        return classes.join(" ");
    }

    getGroupSummaryText(group) {
        const s = this.getGroupStats(group);
        return (
            `${s.count} Hợp đồng · Chi phí tháng: ${formatMoneyVn(s.amount)}` +
            ` · Sắp hết hạn: ${s.expire_soon} HĐ · Quá hạn: ${s.overdue} HĐ`
        );
    }

    getFooterTotals() {
        const t = this.mienStats.totals || {};
        return {
            count: t.count || 0,
            amount: t.amount || 0,
            expire_soon: t.expire_soon || 0,
            overdue: t.overdue || 0,
            text: (
                `TỔNG CỘNG: ${t.count || 0} Hợp đồng · Chi phí: ${formatMoneyVn(t.amount || 0)}` +
                ` · Sắp hết hạn: ${t.expire_soon || 0} HĐ · Quá hạn: ${t.overdue || 0} HĐ`
            ),
        };
    }

    formatExpandDate(value) {
        if (!value) {
            return "—";
        }
        try {
            return formatDate(value);
        } catch (_e) {
            return String(value);
        }
    }

    formatMoneyVn(amount) {
        return formatMoneyVn(amount);
    }
}

export class PhanHeTrackingListController extends ListController {
    static template = "lug_phan_he.TrackingListView";

    onBackToDashboard() {
        const crumbs = this.env.config?.breadcrumbs || [];
        if (crumbs.length > 1) {
            const prev = crumbs[crumbs.length - 2];
            if (typeof prev?.onSelected === "function") {
                prev.onSelected();
                return;
            }
        }
        const code = this.props.context?.phan_he_service_type_code || "internet";
        const actionXmlId = DASHBOARD_BY_SERVICE[code] || DASHBOARD_BY_SERVICE.internet;
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: false });
    }
}

export const phanHeTrackingListView = {
    ...listView,
    Controller: PhanHeTrackingListController,
    Renderer: PhanHeTrackingListRenderer,
};

registry.category("views").add("phan_he_tracking_list", phanHeTrackingListView);
