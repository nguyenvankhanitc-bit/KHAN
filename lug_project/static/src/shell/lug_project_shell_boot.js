/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Fallback so opening Project never throws KeyNotFoundError
 * when the full OWL shell is not in the asset bundle yet.
 * The real LugProjectShell replaces this with { force: true }.
 */
const actions = registry.category("actions");
if (!actions.contains("lug_project_shell")) {
    actions.add("lug_project_shell", async (_env, action) => ({
        type: "ir.actions.act_window",
        name: (action && action.name) || "Dự án",
        res_model: "project.project",
        views: [
            [false, "kanban"],
            [false, "list"],
            [false, "form"],
        ],
        domain: [["is_template", "=", false]],
        context: { display_milestone_deadline: true },
        target: "current",
    }));
}
