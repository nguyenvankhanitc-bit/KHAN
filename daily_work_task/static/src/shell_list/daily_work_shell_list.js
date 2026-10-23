/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

/** Model → mục thanh bên cần tô sáng. */
const NAV_BY_MODEL = {
    "daily.task.team": "team",
    "daily.task.recurring": "recurring",
    "daily.task.employee": "employees",
    "daily.task.access": "access",
    "daily.task.self.review": "self_review",
    "daily.task.report.access": "report_access",
    "daily.task.performance.access": "performance_access",
};

function getShellNav(props) {
    const ctx = props.context || {};
    return (
        ctx.shell_nav ||
        ctx.active_nav ||
        (ctx.search_default_group_by_project ? "projects" : "") ||
        NAV_BY_MODEL[props.resModel] ||
        ""
    );
}

/**
 * Danh sách cấu hình (Cài đặt) và danh sách dự án hiển thị trong khung ứng dụng — có thanh bên trái
 * giống các màn hình khác của module. Mở dạng popup thì giữ danh sách thường.
 */
export class DailyWorkShellListController extends ListController {
    static template = "daily_work_task.ShellListView";
    static components = { ...ListController.components, DailyWorkAppShell };

    get shellNav() {
        return getShellNav(this.props);
    }
}

export class DailyWorkShellKanbanController extends KanbanController {
    static template = "daily_work_task.ShellKanbanView";
    static components = { ...KanbanController.components, DailyWorkAppShell };

    get shellNav() {
        return getShellNav(this.props);
    }
}

registry.category("views").add("daily_work_shell_list", {
    ...listView,
    Controller: DailyWorkShellListController,
});

registry.category("views").add("daily_work_shell_kanban", {
    ...kanbanView,
    Controller: DailyWorkShellKanbanController,
});
