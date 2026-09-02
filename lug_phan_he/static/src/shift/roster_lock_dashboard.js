/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

function pad(n) {
    return String(n).padStart(2, "0");
}

function formatRemain(lockAt) {
    if (!lockAt) {
        return "";
    }
    const end = new Date(lockAt.replace(" ", "T"));
    const diff = end.getTime() - Date.now();
    if (diff <= 0) {
        return "00:00:00";
    }
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

export class RosterLockBadgeField extends Component {
    static template = "lug_phan_he.RosterLockBadgeField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ remain: "" });
        this._timer = null;
        onMounted(() => {
            this.tick();
            this._timer = setInterval(() => this.tick(), 1000);
        });
        onWillUnmount(() => clearInterval(this._timer));
    }

    get badgeClass() {
        return "o_roster_lock_badge is-" + this.status;
    }

    get iconClass() {
        return "fa " + this.icon;
    }

    get status() {
        return this.props.record.data.lock_status || "unlocked";
    }

    get text() {
        const rec = this.props.record.data;
        if (this.status === "expiring") {
            return `Sắp khóa - Còn ${this.state.remain || formatRemain(rec.lock_datetime)}`;
        }
        return rec.lock_badge_text || "Chưa khóa - Chưa đặt thời gian";
    }

    get icon() {
        if (this.status === "locked") {
            return "fa-lock";
        }
        if (this.status === "expiring") {
            return "fa-clock-o";
        }
        return "fa-unlock-alt";
    }

    tick() {
        if (this.status === "expiring") {
            this.state.remain = formatRemain(this.props.record.data.lock_datetime);
        }
    }
}

registry.category("fields").add("roster_lock_badge", {
    component: RosterLockBadgeField,
    supportedTypes: ["selection", "char"],
});

const APPLY_META = {
    applying: { label: "Đang áp dụng", cls: "is-applying" },
    upcoming: { label: "Sắp áp dụng", cls: "is-upcoming" },
    paused: { label: "Tạm dừng", cls: "is-paused" },
    locked: { label: "Đang bị khóa", cls: "is-locked" },
};

export class RosterApplyStatusField extends Component {
    static template = "lug_phan_he.RosterApplyStatusField";
    static props = { ...standardFieldProps };

    get wrapClass() {
        return "o_roster_apply_dot " + this.meta.cls;
    }

    get meta() {
        return APPLY_META[this.props.record.data[this.props.name]] || APPLY_META.applying;
    }
}

registry.category("fields").add("roster_apply_status", {
    component: RosterApplyStatusField,
    supportedTypes: ["selection"],
});

export class RosterNotificationFeed extends Component {
    static template = "lug_phan_he.RosterNotificationFeed";
    static props = {
        events: { type: Array, optional: true },
        onViewAll: { type: Function },
        onGuide: { type: Function },
    };

    get items() {
        return this.props.events || [];
    }

    get hasEvents() {
        return this.items.length > 0;
    }
}

export class RosterLockPanel extends Component {
    static template = "lug_phan_he.RosterLockPanel";
    static props = { dash: { type: Object } };
    static components = { RosterNotificationFeed };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.panelRoot = useRef("panelRoot");
        useEffect(
            () => {
                const root = this.panelRoot.el;
                const cfg = this.state.config || {};
                if (!root) {
                    return;
                }
                root.querySelectorAll("input[type=checkbox][name]").forEach((input) => {
                    input.checked = Boolean(cfg[input.name]);
                });
            },
            () => [this.state.config]
        );
    }

    get state() {
        return this.props.dash;
    }

    get lockHourInput() {
        const hours = this.state.config.lock_hour;
        if (hours == null || hours === false) {
            return "17:00";
        }
        const h = Math.floor(Number(hours) || 0);
        const m = Math.round(((Number(hours) || 0) % 1) * 60);
        const hh = (h < 10 ? "0" : "") + h;
        const mm = (m < 10 ? "0" : "") + m;
        return `${hh}:${mm}`;
    }

    onLockHourChange(ev) {
        const parts = (ev.target.value || "17:00").split(":");
        const h = parseInt(parts[0] || "17", 10);
        const m = parseInt(parts[1] || "0", 10);
        this.setCfg("lock_hour", h + m / 60);
    }

    openFullSettings() {
        this.action.doAction("lug_phan_he.action_linkq_roster_lock_settings");
    }

    onViewAll() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Thông báo khóa lịch ca",
            res_model: "linkq.roster.lock.event",
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    onGuide() {
        this.openFullSettings();
    }

    setCfg(field, value) {
        this.state.config[field] = value;
    }

    async saveConfig() {
        const cfg = this.state.config;
        const saved = await this.orm.call("linkq.roster.lock.config", "action_save_settings", [
            {
                auto_lock_enabled: cfg.auto_lock_enabled,
                lock_before: cfg.lock_before,
                lock_hour: cfg.lock_hour,
                apply_to_new: cfg.apply_to_new,
                allow_manager_unlock: cfg.allow_manager_unlock,
                notify_expiring: cfg.notify_expiring,
                notify_offset: cfg.notify_offset,
                notify_employees: cfg.notify_employees,
                notify_store_manager: cfg.notify_store_manager,
                notify_admin: cfg.notify_admin,
            },
        ]);
        this.state.config = saved;
        this.notification.add("Đã lưu cài đặt khóa lịch ca.", { type: "success" });
    }

    onCheck(ev) {
        this.setCfg(ev.target.name, ev.target.checked);
    }

    onSelect(ev) {
        this.setCfg(ev.target.name, ev.target.value);
    }

    eventClass(item) {
        return "o_roster_ev is-" + (item.type || "");
    }

    eventIconClass(item) {
        return "fa " + this.eventIcon(item.type);
    }

    get hasEvents() {
        return Boolean(this.state.events && this.state.events.length);
    }

    eventIcon(type) {
        const icons = {
            expiring: "fa-clock-o",
            locked: "fa-lock",
            ended: "fa-flag-checkered",
            reminder: "fa-bell",
            success: "fa-check",
            unlocked: "fa-unlock",
        };
        return icons[type] || "fa-info";
    }
}
