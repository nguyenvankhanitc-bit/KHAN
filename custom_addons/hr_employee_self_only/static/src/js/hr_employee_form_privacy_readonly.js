/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillStart, onWillUnmount, status } from "@odoo/owl";
import { user } from "@web/core/user";
import { effect } from "@web/core/utils/reactive";

import { EmployeeFormController } from "@hr/views/form_view";

/**
 * Edit Employee Profile = No: employee form is always readonly (no typing).
 */
patch(EmployeeFormController.prototype, {
    setup() {
        super.setup(...arguments);
        this._employeesNoUiLock = false;
        this._employeesNoInteractionClass = "o_hr_employee_no_interaction";
        this._employeesNoClickBlocker = null;
        this._employeesNoObserver = null;
        onWillStart(async () => {
            const canEdit = await user.hasGroup(
                "hr_employee_self_only.group_hr_employee_edit_allowed"
            );
            const isManager = await user.hasGroup("hr.group_hr_manager");
            const isOfficer = await user.hasGroup("hr.group_hr_user");
            this._employeesNoUiLock = isOfficer && !canEdit && !isManager;
            if (this._employeesNoUiLock) {
                this.canCreate = false;
                this.canEdit = false;
            }
        });
        onMounted(() => {
            const lockInteractiveElements = () => {
                if (!this.el || !this._employeesNoUiLock) {
                    return;
                }
                this.el
                    .querySelectorAll(
                        "a, button, .o_external_button, .o-dropdown--menu .dropdown-item, .o_notebook_headers .nav-link"
                    )
                    .forEach((node) => {
                        node.style.pointerEvents = "none";
                        node.style.cursor = "default";
                    });
            };
            this._employeesNoClickBlocker = (ev) => {
                if (!this._employeesNoUiLock) {
                    return;
                }
                const root = this.model?.root;
                if (!root || root.isNew || !root.resId) {
                    return;
                }
                const target = ev.target;
                if (!(target instanceof Element)) {
                    return;
                }
                const interactive = target.closest(
                    "a, button, .o_field_widget, .dropdown-item, .o_notebook_headers"
                );
                if (interactive) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
            };
            this.el?.addEventListener("click", this._employeesNoClickBlocker, true);
            if (this._employeesNoUiLock && this.el) {
                this._employeesNoObserver = new MutationObserver(() => {
                    lockInteractiveElements();
                });
                this._employeesNoObserver.observe(this.el, {
                    childList: true,
                    subtree: true,
                });
                lockInteractiveElements();
            }
            effect(
                (model) => {
                    if (status(this) !== "mounted") {
                        return;
                    }
                    const root = model.root;
                    if (!root || root.isNew || !root.resId) {
                        return;
                    }
                    if (this._employeesNoUiLock) {
                        this.el?.classList.add(this._employeesNoInteractionClass);
                        lockInteractiveElements();
                        if (root.config.mode !== "readonly") {
                            root.switchMode("readonly");
                        }
                    } else if (this.canEdit && root.config.mode === "readonly") {
                        this.el?.classList.remove(this._employeesNoInteractionClass);
                        root.switchMode("edit");
                    } else {
                        this.el?.classList.remove(this._employeesNoInteractionClass);
                    }
                },
                [this.model]
            );
        });
        onWillUnmount(() => {
            if (this._employeesNoClickBlocker) {
                this.el?.removeEventListener("click", this._employeesNoClickBlocker, true);
            }
            if (this._employeesNoObserver) {
                this._employeesNoObserver.disconnect();
                this._employeesNoObserver = null;
            }
        });
    },

    get cogMenuProps() {
        const props = super.cogMenuProps;
        if (!this._employeesNoUiLock) {
            return props;
        }
        return {
            ...props,
            items: {},
        };
    },
});
