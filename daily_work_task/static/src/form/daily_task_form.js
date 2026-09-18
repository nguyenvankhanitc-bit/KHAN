/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

export class DailyTaskFormController extends FormController {
    static template = "daily_work_task.DailyTaskFormView";
    static components = { ...FormController.components };

    _shouldReturnToday() {
        const ctx = this.props.context || {};
        return Boolean(ctx.daily_work_return_today) && !this.env.inDialog;
    }

    async _returnToday() {
        await this.actionService.doAction("daily_work_task.action_daily_work_today", {
            stackPosition: "replaceCurrentAction",
        });
    }

    async saveButtonClicked(params = {}) {
        const saved = await super.saveButtonClicked(params);
        if (saved && this._shouldReturnToday()) {
            await this._returnToday();
        }
        return saved;
    }

    async discard() {
        await super.discard();
        if (this._shouldReturnToday()) {
            await this._returnToday();
        }
    }
}

registry.category("views").add("daily_task_form", {
    ...formView,
    Controller: DailyTaskFormController,
});
