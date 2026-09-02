/** @odoo-module **/

import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

function pad2(n) {
    return (n < 10 ? "0" : "") + n;
}

function clampDay(day) {
    const n = parseInt(day, 10);
    if (!Number.isFinite(n) || n < 1) {
        return 1;
    }
    return Math.min(n, 31);
}

function isoFromDay(day, base) {
    const src = String(base || "") || isoDate(new Date());
    const parts = src.split("-");
    const y = parseInt(parts[0] || String(new Date().getFullYear()), 10);
    const m = parseInt(parts[1] || String(new Date().getMonth() + 1), 10);
    const last = new Date(y, m, 0).getDate();
    const d = Math.min(clampDay(day), last);
    return y + "-" + pad2(m) + "-" + pad2(d);
}

function isoDate(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
}

function buildHourOptions() {
    const items = [];
    for (let h = 0; h < 24; h++) {
        items.push(pad2(h) + ":00");
        items.push(pad2(h) + ":30");
    }
    return items;
}

const HOUR_OPTIONS = buildHourOptions();

export class RosterLockSettingsPage extends Component {
    static template = "lug_phan_he.RosterLockSettingsPage";
    static components = { PhanHeAppSidebar };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.lockDaySelect = useRef("lockDaySelect");
        this.unlockDaySelect = useRef("unlockDaySelect");
        this.state = useState({
            auto_lock: true,
            lock_day: 10,
            lock_date: isoDate(new Date()),
            lock_time: "22:00",
            repeat_type: "monthly",
            unlock_mode: "manual",
            unlock_day: 1,
            unlock_date: isoFromDay(1),
            unlock_time: "00:00",
            unlock_repeat: "monthly",
            notify_on: true,
            notify_before: "2h",
            saving: false,
        });
        this._snapshot = null;
        onWillStart(async () => {
            const data = await this.orm.call("linkq.monthly.roster", "get_lock_dashboard", []);
            if (!data.can_configure) {
                this.action.doAction("lug_phan_he.action_linkq_monthly_roster", { stackPosition: "replaceCurrentAction" });
                return;
            }
            this.applyConfig(data.config || {});
            this._snapshot = this.payloadFromState();
        });
    }

    get sidebarActiveKey() {
        return "lock_settings";
    }

    get daysRange() {
        return Array.from({ length: 31 }, (_, i) => i + 1);
    }

    get hourOptions() {
        const extra = [];
        for (const t of [this.state.lock_time, this.state.unlock_time]) {
            if (t && !HOUR_OPTIONS.includes(t) && !extra.includes(t)) {
                extra.push(t);
            }
        }
        return extra.concat(HOUR_OPTIONS);
    }

    get lockDayNum() {
        return clampDay(this.state.lock_day);
    }

    get unlockDayNum() {
        return clampDay(this.state.unlock_day);
    }

    get isAutoUnlock() {
        return this.state.unlock_mode === "auto";
    }

    padDay(n) {
        return pad2(n);
    }

    isLockDay(d) {
        return this.lockDayNum === d;
    }

    isUnlockDay(d) {
        return this.unlockDayNum === d;
    }

    applyConfig(cfg) {
        this.state.auto_lock = cfg.auto_lock !== false;
        this.state.lock_time = cfg.lock_time || "22:00";
        this.state.repeat_type = cfg.repeat_type || "monthly";
        const day = clampDay(cfg.lock_day != null ? cfg.lock_day : 10);
        this.state.lock_day = day;
        if (cfg.lock_anchor_date) {
            this.state.lock_date = isoFromDay(day, cfg.lock_anchor_date);
        } else {
            this.state.lock_date = isoFromDay(day);
        }
        this.state.unlock_mode = cfg.unlock_mode || "manual";
        const unlockDay = clampDay(
            cfg.unlock_date ? String(cfg.unlock_date).split("-")[2] : cfg.unlock_day || 1
        );
        this.state.unlock_day = unlockDay;
        this.state.unlock_date = isoFromDay(unlockDay, cfg.unlock_date || this.state.lock_date);
        this.state.unlock_time = cfg.unlock_time || "00:00";
        this.state.unlock_repeat = cfg.unlock_repeat && cfg.unlock_repeat !== "none"
            ? cfg.unlock_repeat
            : "monthly";
        this.state.notify_on = cfg.notify_odoo !== false && cfg.notify_expiring !== false;
        this.state.notify_before = cfg.notify_before || cfg.notify_offset || "2h";
    }

    syncDaysFromDom() {
        if (this.lockDaySelect.el) {
            this.state.lock_day = clampDay(this.lockDaySelect.el.value);
            this.state.lock_date = isoFromDay(this.state.lock_day, this.state.lock_date);
        }
        if (this.unlockDaySelect.el) {
            this.state.unlock_day = clampDay(this.unlockDaySelect.el.value);
            this.state.unlock_date = isoFromDay(this.state.unlock_day, this.state.unlock_date || this.state.lock_date);
        }
    }

    payloadFromState() {
        this.syncDaysFromDom();
        return {
            auto_lock: this.state.auto_lock,
            lock_day: this.lockDayNum,
            lock_day_val: this.lockDayNum,
            lock_anchor_date: isoFromDay(this.lockDayNum, this.state.lock_date),
            repeat_type: this.state.repeat_type,
            lock_time: this.state.lock_time,
            unlock_mode: this.state.unlock_mode,
            unlock_date: isoFromDay(this.unlockDayNum, this.state.unlock_date || this.state.lock_date),
            unlock_time: this.state.unlock_time,
            unlock_repeat: this.state.unlock_repeat,
            notify_before: this.state.notify_before,
            notify_odoo: this.state.notify_on,
            allow_manager_unlock: true,
        };
    }

    toggle(field) {
        this.state[field] = !this.state[field];
    }

    toggleAutoUnlock() {
        this.state.unlock_mode = this.state.unlock_mode === "auto" ? "manual" : "auto";
        if (this.state.unlock_mode === "auto" && !this.state.unlock_date) {
            this.state.unlock_date = isoFromDay(1, this.state.lock_date);
        }
        if (this.state.unlock_mode === "auto" && this.state.unlock_repeat === "none") {
            this.state.unlock_repeat = "monthly";
        }
    }

    onLockDaySelect(ev) {
        const day = clampDay(ev.target.value);
        this.state.lock_day = day;
        this.state.lock_date = isoFromDay(day, this.state.lock_date);
    }

    onLockRepeatSelect(ev) {
        this.state.repeat_type = ev.target.value || "monthly";
    }

    onLockTimeChange(ev) {
        this.state.lock_time = ev.target.value || "22:00";
    }

    onUnlockDaySelect(ev) {
        const day = clampDay(ev.target.value);
        this.state.unlock_day = day;
        this.state.unlock_date = isoFromDay(day, this.state.unlock_date || this.state.lock_date);
    }

    onUnlockTimeChange(ev) {
        this.state.unlock_time = ev.target.value || "00:00";
    }

    onUnlockRepeatChange(ev) {
        this.state.unlock_repeat = ev.target.value || "monthly";
    }

    onCancel() {
        if (!this._snapshot) {
            return;
        }
        const snap = this._snapshot;
        this.state.auto_lock = snap.auto_lock;
        this.state.lock_day = clampDay(snap.lock_day);
        this.state.lock_date = isoFromDay(this.state.lock_day, snap.lock_anchor_date);
        this.state.lock_time = snap.lock_time;
        this.state.repeat_type = snap.repeat_type;
        this.state.unlock_mode = snap.unlock_mode;
        this.state.unlock_day = clampDay(String(snap.unlock_date || "01").split("-")[2] || 1);
        this.state.unlock_date = isoFromDay(this.state.unlock_day, snap.unlock_date || isoFromDay(1));
        this.state.unlock_time = snap.unlock_time;
        this.state.unlock_repeat = snap.unlock_repeat;
        this.state.notify_on = snap.notify_odoo;
        this.state.notify_before = snap.notify_before;
    }

    async onSave() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const saved = await this.orm.call(
                "linkq.roster.lock.config",
                "action_save_settings",
                [this.payloadFromState()]
            );
            this.applyConfig(saved || {});
            this._snapshot = this.payloadFromState();
            this.notification.add("Đã lưu và áp dụng cấu hình khóa lịch ca.", { type: "success" });
        } catch (err) {
            this.notification.add(err?.data?.message || err?.message || "Không lưu được cấu hình khóa lịch ca.", {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("linkq_roster_lock_settings", RosterLockSettingsPage);
