/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { RPCError, rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { UncaughtPromiseError } from "@web/core/errors/error_service";

const SESSION_EXCEPTIONS = new Set(["odoo.http.SessionExpiredException"]);

let redirectScheduled = false;

export function phanHeRedirectToLogin() {
    if (redirectScheduled) {
        return;
    }
    redirectScheduled = true;
    browser.location.replace("/web/session/logout?redirect=/web/login");
}

function isSessionExpiredRpcError(originalError) {
    if (!(originalError instanceof RPCError)) {
        return false;
    }
    const exceptionName = originalError.exceptionName;
    if (exceptionName && SESSION_EXCEPTIONS.has(exceptionName)) {
        return true;
    }
    return (originalError.message || "").toLowerCase().includes("session expired");
}

function notifyAndRedirectToLogin(env) {
    env.services.notification.add(
        _t("Phiên đăng nhập đã hết hạn (phân quyền vừa cập nhật). Đang chuyển về trang đăng nhập…"),
        { type: "warning" }
    );
    browser.setTimeout(() => phanHeRedirectToLogin(), 600);
}

export function phanHeSessionExpiredHandler(env, error, originalError) {
    if (!(error instanceof UncaughtPromiseError) || !isSessionExpiredRpcError(originalError)) {
        return false;
    }
    error.unhandledRejectionEvent.preventDefault();
    notifyAndRedirectToLogin(env);
    return true;
}

registry
    .category("error_handlers")
    .add("phanHeSessionExpiredHandler", phanHeSessionExpiredHandler, { sequence: 96 });

/** Poll thưa hơn; bỏ qua khi tab ẩn để giảm tải sau login. */
export const phanHeSessionPollService = {
    dependencies: ["notification"],
    start(env) {
        const intervalMs = 60000;
        let inFlight = false;
        const timer = browser.setInterval(async () => {
            if (inFlight) {
                return;
            }
            if (typeof document !== "undefined" && document.hidden) {
                return;
            }
            inFlight = true;
            try {
                await rpc("/web/session/get_session_info", {});
            } catch (error) {
                if (isSessionExpiredRpcError(error)) {
                    notifyAndRedirectToLogin(env);
                }
            } finally {
                inFlight = false;
            }
        }, intervalMs);
        return {
            stop() {
                browser.clearInterval(timer);
            },
        };
    },
};

registry.category("services").add("phan_he_session_poll", phanHeSessionPollService);
