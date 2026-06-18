/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { Store } from "@mail/core/common/store_service";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillDestroy } from "@odoo/owl";

const LEAVE_LINK_SELECTOR = [
    'a[data-oe-model="hr.leave"][data-oe-id]',
    'a[data-oe-type="handover"][data-oe-id]',
    'a[data-oe-type="approval"][data-oe-id]',
    'a[href*="/hr.leave/"]',
    'a[href*="/discuss_leave/"]',
].join(", ");

const APPROVAL_GROUP_SELECTOR =
    'a[data-oe-type="approval_group"][data-oe-action][data-oe-id]';

const APPROVAL_LIST_SELECTOR = 'a[data-oe-type="approval_list"]';

function findTimeOffLeaveLink(target) {
    if (target?.closest?.(APPROVAL_GROUP_SELECTOR)) {
        return null;
    }
    if (target?.closest?.(APPROVAL_LIST_SELECTOR)) {
        return null;
    }
    return target?.closest?.(LEAVE_LINK_SELECTOR) ?? null;
}

function findApprovalListLink(target) {
    return target?.closest?.(APPROVAL_LIST_SELECTOR) ?? null;
}

function findApprovalGroupLink(target) {
    return target?.closest?.(APPROVAL_GROUP_SELECTOR) ?? null;
}

function resolveLeaveId(link) {
    if (!link) {
        return 0;
    }
    const fromData = Number(link.dataset.oeId);
    if (fromData) {
        return fromData;
    }
    const href = link.getAttribute("href") || link.pathname || "";
    const m = href.match(/(?:hr\.leave\/|discuss_leave\/)(\d+)/);
    return m ? Number(m[1]) : 0;
}

function foldMobileChatWindow(store, ev, thread, link) {
    if (
        !store.env.services.ui.isSmall ||
        !ev.target.closest(".o-mail-ChatWindow") ||
        !link.href
    ) {
        return;
    }
    try {
        const url = new URL(link.href);
        if (
            browser.location.host === url.host &&
            browser.location.pathname.startsWith("/odoo")
        ) {
            store.ChatWindow.get({ thread })?.fold();
        }
    } catch {
        // ignore invalid URLs
    }
}

function openLeaveForm(env, resId) {
    return env.services.action.doAction({
        type: "ir.actions.act_window",
        res_model: "hr.leave",
        res_id: resId,
        views: [[false, "form"]],
        target: "current",
    });
}

function openApprovalPendingList(env) {
    return env.services.action.doAction("hr_holidays.hr_leave_action_action_approve_department");
}

async function markLeaveNotificationViewed(orm, resId, link) {
    if ((link.dataset.oeType || "") !== "approval") {
        return;
    }
    const splitGroupId = link.dataset.oeSplitGroup || false;
    try {
        await orm.call(
            "hr.leave",
            "action_discuss_mark_leave_notification_viewed",
            [resId, splitGroupId]
        );
    } catch {
        // Best-effort: opening the leave form must still work.
    }
}

function handleApprovalListLink(ev, store, thread) {
    const link = findApprovalListLink(ev.target);
    if (!link) {
        return false;
    }
    ev.preventDefault();
    ev.stopPropagation();
    foldMobileChatWindow(store, ev, thread, link);
    openApprovalPendingList(store.env);
    return true;
}

async function handleApprovalGroupAction(ev, store) {
    const link = findApprovalGroupLink(ev.target);
    if (!link) {
        return false;
    }
    const resId = resolveLeaveId(link);
    const action = link.dataset.oeAction;
    const splitGroupId = link.dataset.oeSplitGroup || false;
    if (!resId || !action) {
        return false;
    }
    ev.preventDefault();
    ev.stopPropagation();

    const { orm, notification, dialog } = store.env.services;

    const runApprove = async () => {
        try {
            await orm.call(
                "hr.leave",
                "action_discuss_split_group_approve_by_reference",
                [resId, splitGroupId]
            );
            notification.add(_t("Đã phê duyệt toàn bộ đơn nghỉ."), { type: "success" });
        } catch (e) {
            notification.add(e.data?.message || e.message, { type: "danger" });
        }
    };

    const runRefuse = async () => {
        try {
            await orm.call(
                "hr.leave",
                "action_discuss_split_group_refuse_by_reference",
                [resId, splitGroupId]
            );
            notification.add(_t("Đã từ chối toàn bộ đơn nghỉ."), { type: "warning" });
        } catch (e) {
            notification.add(e.data?.message || e.message, { type: "danger" });
        }
    };

    if (action === "approve_all") {
        await runApprove();
    } else if (action === "refuse_all") {
        dialog.add(ConfirmationDialog, {
            title: _t("Từ chối đơn nghỉ"),
            body: _t("Bạn có chắc muốn từ chối toàn bộ các phần trong đơn này?"),
            confirm: runRefuse,
            confirmLabel: _t("Từ chối tất cả"),
            cancel: () => {},
            cancelLabel: _t("Hủy"),
        });
    }
    return true;
}

function handleTimeOffLeaveLink(ev, store, thread) {
    const link = findTimeOffLeaveLink(ev.target);
    if (!link) {
        return false;
    }
    const resId = resolveLeaveId(link);
    if (!resId) {
        return false;
    }
    ev.preventDefault();
    ev.stopPropagation();
    foldMobileChatWindow(store, ev, thread, link);
    void markLeaveNotificationViewed(store.env.services.orm, resId, link);
    openLeaveForm(store.env, resId);
    return true;
}

async function handleTimeOffDiscussClick(ev, store, thread) {
    if (handleApprovalListLink(ev, store, thread)) {
        return true;
    }
    if (await handleApprovalGroupAction(ev, store)) {
        return true;
    }
    return handleTimeOffLeaveLink(ev, store, thread);
}

patch(Store.prototype, {
    handleClickOnLink(ev, thread) {
        if (handleApprovalListLink(ev, this, thread)) {
            return true;
        }
        if (findApprovalGroupLink(ev.target)) {
            void handleApprovalGroupAction(ev, this);
            return true;
        }
        if (handleTimeOffLeaveLink(ev, this, thread)) {
            return true;
        }
        return super.handleClickOnLink(...arguments);
    },
});

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        const onTimeOffLinkTap = async (ev) => {
            if (!this.root.el?.contains(ev.target)) {
                return;
            }
            await handleTimeOffDiscussClick(ev, this.store, this.props.thread);
        };
        onMounted(() => {
            this.root.el?.addEventListener("click", onTimeOffLinkTap, { capture: true });
        });
        onWillDestroy(() => {
            this.root.el?.removeEventListener("click", onTimeOffLinkTap, { capture: true });
        });
    },
});
