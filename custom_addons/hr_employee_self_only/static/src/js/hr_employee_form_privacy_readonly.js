/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, status } from "@odoo/owl";
import { effect } from "@web/core/utils/reactive";

import { EmployeeFormController } from "@hr/views/form_view";

/**
 * Edit Employee Profile = No: employee form is readonly.
 * Lock state comes from server field employee_form_force_readonly_ui
 * (not client session groups, which stay stale until re-login).
 */
patch(EmployeeFormController.prototype, {
    setup() {
        super.setup(...arguments);
        this._employeesNoUiLock = false;
        this._employeesNoInteractionClass = "o_hr_employee_no_interaction";
        this._employeesNoClickBlocker = null;
        this._employeesNoObserver = null;
        this._baseCanCreate = this.canCreate;
        this._baseCanEdit = this.canEdit;

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

            const applyLockState = (lock) => {
                if (this._employeesNoUiLock === lock) {
                    return;
                }
                this._employeesNoUiLock = lock;
                if (lock) {
                    this.canCreate = false;
                    this.canEdit = false;
                } else {
                    this.canCreate = this._baseCanCreate;
                    this.canEdit = this._baseCanEdit;
                }
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

            effect(
                (model) => {
                    if (status(this) !== "mounted") {
                        return;
                    }
                    const root = model.root;
                    if (!root || root.isNew || !root.resId) {
                        return;
                    }
                    const lock = Boolean(root.data?.employee_form_force_readonly_ui);
                    applyLockState(lock);

                    if (this._employeesNoUiLock) {
                        this.el?.classList.add(this._employeesNoInteractionClass);
                        if (!this._employeesNoObserver && this.el) {
                            this._employeesNoObserver = new MutationObserver(() => {
                                lockInteractiveElements();
                            });
                            this._employeesNoObserver.observe(this.el, {
                                childList: true,
                                subtree: true,
                            });
                        }
                        lockInteractiveElements();
                        if (root.config.mode !== "readonly") {
                            root.switchMode("readonly");
                        }
                    } else {
                        this.el?.classList.remove(this._employeesNoInteractionClass);
                        if (this.canEdit && root.config.mode === "readonly") {
                            root.switchMode("edit");
                        }
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
