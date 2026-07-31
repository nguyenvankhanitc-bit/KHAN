/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState, useSubEnv, Component, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { formatDate } from "@web/core/l10n/dates";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

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
        return this.env.phanHeTracking?.getStt(this.props.record) || "—";
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

    /**
     * STT tăng dần trong từng miền (nhóm).
     * Ví dụ Miền Bắc: 1..n, Miền Nam: 1..m
     */
    getStt(record) {
        const root = this.props.list;
        if (root.isGrouped) {
            for (const group of root.groups || []) {
                const records = group.list?.records || [];
                const idx = records.findIndex((r) => r.id === record.id || r.resId === record.resId);
                if (idx >= 0) {
                    return idx + 1;
                }
                // nested groups (hiếm)
                if (group.list?.isGrouped) {
                    for (const sub of group.list.groups || []) {
                        const subRecords = sub.list?.records || [];
                        const subIdx = subRecords.findIndex(
                            (r) => r.id === record.id || r.resId === record.resId
                        );
                        if (subIdx >= 0) {
                            return subIdx + 1;
                        }
                    }
                }
            }
            return "—";
        }
        // Không group: đánh số theo từng miền trong danh sách phẳng
        const all = root.records || [];
        const mienId = Array.isArray(record.data.mien_id)
            ? record.data.mien_id[0]
            : record.data.mien_id;
        let n = 0;
        for (const r of all) {
            const mid = Array.isArray(r.data.mien_id) ? r.data.mien_id[0] : r.data.mien_id;
            if (mid === mienId) {
                n += 1;
                if (r.id === record.id || r.resId === record.resId) {
                    return n;
                }
            }
        }
        return "—";
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

export const phanHeTrackingListView = {
    ...listView,
    Renderer: PhanHeTrackingListRenderer,
};

registry.category("views").add("phan_he_tracking_list", phanHeTrackingListView);
