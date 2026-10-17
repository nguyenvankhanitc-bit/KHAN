/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
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

/**
 * Danh sách cấu hình (Cài đặt) hiển thị trong khung ứng dụng — có thanh bên trái
 * giống các màn hình khác của module. Mở dạng popup thì giữ danh sách thường.
 */
export class DailyWorkShellListController extends ListController {
    static template = "daily_work_task.ShellListView";
    static components = { ...ListController.components, DailyWorkAppShell };

    get shellNav() {
        return NAV_BY_MODEL[this.props.resModel] || "";
    }
}

registry.category("views").add("daily_work_shell_list", {
    ...listView,
    Controller: DailyWorkShellListController,
});
