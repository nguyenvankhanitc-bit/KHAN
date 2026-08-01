/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Stub cho URL/bookmark cũ còn tag "phan_he_access_matrix".
 * Redirect sang form Nhóm quyền chuẩn.
 */
async function phanHeAccessMatrixRedirect(env, _action, options = {}) {
    return env.services.action.doAction("lug_phan_he.action_phan_he_module_access", {
        ...options,
        clearBreadcrumbs: true,
        stackPosition: options.stackPosition || "replaceCurrentAction",
    });
}

registry.category("actions").add("phan_he_access_matrix", phanHeAccessMatrixRedirect);
