/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

function remainMs(lockAt) {
    if (!lockAt) {
        return 0;
    }
    const raw = String(lockAt).replace(" ", "T");
    const end = new Date(raw.endsWith("Z") ? raw : raw + "Z");
    return end.getTime() - Date.now();
}

export class StoreNotifDialog extends Component {
    static template = "lug_phan_he.StoreNotifDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        kind: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const kindMap = {
            sap_khoa: "expiring",
            nhac_nho: "reminder",
            da_khoa: "locked",
            can_xu_ly: "need",
            thong_tin: "info",
        };
        const raw = this.props.kind || "all";
        const start = raw === "all" ? "all" : kindMap[raw] || raw;
        this.state = useState({
            loading: true,
            allCards: [],
            counts: { all: 0, expiring: 0, reminder: 0, locked: 0, need: 0, info: 0 },
            filter: start,
            sort: "newest",
            tick: 0,
        });
        onWillStart(async () => {
            await this.loadCards();
        });
        onMounted(() => {
            this._timer = setInterval(() => {
                this.state.tick += 1;
            }, 1000);
        });
        onWillUnmount(() => clearInterval(this._timer));
    }

    get dialogTitle() {
        return "Thông báo cửa hàng";
    }

    get totalCount() {
        return this.state.counts.all || this.state.allCards.length || 0;
    }

    get sortLabel() {
        return this.state.sort === "oldest" ? "Cũ nhất" : "Mới nhất";
    }

    get visibleCards() {
        let list = this.state.allCards.slice();
        if (this.state.filter && this.state.filter !== "all") {
            list = list.filter((c) => c.type === this.state.filter);
        }
        if (this.state.sort === "oldest") {
            list.reverse();
        }
        return list;
    }

    isFilter(name) {
        return this.state.filter === name ? "active" : "";
    }

    countOf(name) {
        return this.state.counts[name] || 0;
    }

    setFilter(name) {
        this.state.filter = name;
    }

    toggleSort() {
        this.state.sort = this.state.sort === "newest" ? "oldest" : "newest";
    }

    async loadCards() {
        try {
            const data = await this.orm.call("linkq.store.notification", "get_store_notification_cards", ["all"]);
            const payload = data && data.cards ? data : { cards: data || [], counts: {} };
            this.state.allCards = payload.cards || [];
            if (payload.counts) {
                this.state.counts = payload.counts;
            }
        } catch (_e) {
            this.state.allCards = [];
        }
        this.state.loading = false;
    }

    remainMsOf(card) {
        void this.state.tick;
        return remainMs(card.lock_at);
    }

    cardSkin(card) {
        const map = {
            expiring: "card-border-orange",
            reminder: "card-border-blue",
            locked: "card-border-red",
            need: "card-border-orange",
            info: "card-border-green",
        };
        return map[card.type] || "card-border-blue";
    }

    remainClass(card) {
        const ms = this.remainMsOf(card);
        return ms > 0 && ms < 3600000 ? "pill-urgent" : "pill-orange";
    }

    remainLabel(card) {
        const ms = this.remainMsOf(card);
        if (ms <= 0) {
            return "Đến hạn khóa";
        }
        const minutes = Math.floor(ms / 60000);
        if (minutes < 60) {
            return "Còn " + minutes + " phút";
        }
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        if (days > 0) {
            return "Còn " + days + " ngày";
        }
        return "Còn " + hours + " giờ";
    }

    async openRoster(card) {
        this.props.close();
        const action = {
            type: "ir.actions.act_window",
            name: "Bảng xếp ca",
            res_model: "linkq.monthly.roster",
            views: card.id ? [[false, "form"]] : [[false, "form"]],
            target: "current",
        };
        if (card.id) {
            action.res_id = card.id;
        }
        await this.action.doAction(action);
    }
}
