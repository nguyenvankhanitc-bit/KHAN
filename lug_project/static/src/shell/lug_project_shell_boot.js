/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Safe fallback registered before the full OWL shell.
 * If lug_project_shell.js fails to load (stale assets / syntax error),
 * opening Dự án still shows the native Project kanban — never a blank pane.
 * LugProjectShell replaces this with { force: true } when it loads.
 */
const actions = registry.category("actions");
if (!actions.contains("lug_project_shell")) {
    actions.add("lug_project_shell", () => ({
        type: "ir.actions.act_url",
        url: "/odoo/du-an",
        target: "self",
    }));
}
