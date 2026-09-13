/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { booleanToggleField, BooleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";

export class InternetPermToggleField extends BooleanToggleField {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    async onChange(newValue) {
        await super.onChange(newValue);
        const id = this.props.record.resId;
        if (!id) {
            return;
        }
        await this.orm.call("phan.he.module.access", "update_internet_permission_instant", [
            id,
            this.props.name,
            newValue,
        ]);
    }
}

registry.category("fields").add("internet_perm_toggle", {
    ...booleanToggleField,
    component: InternetPermToggleField,
});
