/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { PhanHeAppSidebar } from "../shell/phan_he_app_sidebar";

export class LinkQPermissionMatrix extends Component {
    static template = "lug_phan_he.LinkQPermissionMatrix";
    static components = { PhanHeAppSidebar };
    static props = { ...standardActionServiceProps };

    setup() {
        this.action = useService("action");
        onWillStart(() =>
            this.action.doAction("lug_phan_he.action_phan_he_module_access", {
                clearBreadcrumbs: true,
                stackPosition: "replaceCurrentAction",
            })
        );
    }
}

registry.category("actions").add("linkq_permission_matrix", LinkQPermissionMatrix);
