/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { DiscussClientAction } from "@mail/core/public_web/discuss_client_action";
import { MessagingMenu } from "@mail/core/public_web/messaging_menu";

import { onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const LARK_BODY_CLASS = "o-mail-lark-ui";

function isMobileUi(ui) {
    if (ui?.isSmall) {
        return true;
    }
    return typeof window !== "undefined" && window.matchMedia("(max-width: 767.98px)").matches;
}

function setLarkUiActive(active) {
    document.body.classList.toggle(LARK_BODY_CLASS, active);
}

function bindLarkUiOnAction(component) {
    const ui = component.env.services.ui;
    onMounted(() => {
        if (isMobileUi(ui)) {
            setLarkUiActive(true);
        }
    });
    onWillUnmount(() => {
        if (isMobileUi(ui)) {
            setLarkUiActive(false);
        }
    });
}

patch(DiscussClientAction.prototype, {
    setup() {
        super.setup();
        bindLarkUiOnAction(this);
    },
});

patch(Discuss.prototype, {
    setup() {
        super.setup();
        bindLarkUiOnAction(this);
    },
});

patch(MessagingMenu.prototype, {
    get larkFilterTabs() {
        const tabs = [
            { id: "chat", label: _t("Chats") },
            { id: "channel", label: _t("Channels") },
        ];
        const inboxTab =
            this.store.self.main_user_id?.notification_type === "inbox"
                ? { id: "inbox", label: _t("Unread"), counter: this.store.inbox.counter }
                : {
                      id: "starred",
                      label: _t("Starred"),
                      counter: this.store.starred.counter,
                  };
        return [inboxTab, ...tabs];
    },

    get larkActiveFilterId() {
        const tab = this.store.discuss.activeTab;
        if (tab === "notification") {
            return this.store.self.main_user_id?.notification_type === "inbox" ? "inbox" : "starred";
        }
        if (["inbox", "starred", "chat", "channel"].includes(tab)) {
            return tab;
        }
        return "chat";
    },

    onLarkFilterClick(filterId) {
        if (filterId === "inbox" || filterId === "starred") {
            this.onClickNavTab(filterId);
            return;
        }
        if (filterId === "chat" || filterId === "channel") {
            this.onClickNavTab(filterId);
        }
    },

    onLarkSearchClick() {
        document.querySelector(".o-mail-DiscussSearch-inputClickable")?.click();
    },

    onLarkComposeClick() {
        const meetingBtn = document.querySelector(".o-mail-DiscussSearch button[data-hotkey='m']");
        if (meetingBtn) {
            meetingBtn.click();
            return;
        }
        this.env.services.command?.openMainPalette({ searchValue: "@" });
    },

    onLarkAppMenuClick() {
        document.querySelector(".o_main_navbar > a.o_menu_toggle")?.click();
    },
});
