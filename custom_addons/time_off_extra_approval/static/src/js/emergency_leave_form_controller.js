/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const EMERGENCY_CTX = "emergency_leave_confirmed";
const CON_LAI_ZERO_CTX = "con_lai_zero_confirmed";

const LEAVE_PREVIEW_FIELDS = [
    "employee_id",
    "holiday_status_id",
    "request_date_from",
    "request_date_to",
    "date_from",
    "date_to",
    "supported_attachment_ids",
    "attachment_ids",
];

/**
 * RPC cần đủ ngày/nhân viên trên form; `changes` chỉ chứa field vừa sửa.
 */
function serializeFieldValue(value) {
    if (value === undefined || value === null || value === false) {
        return value;
    }
    if (Array.isArray(value)) {
        return value;
    }
    if (typeof value === "object" && "id" in value) {
        return value.id;
    }
    if (typeof value === "object" && typeof value.toISODate === "function") {
        return value.toISODate({ includeTime: false });
    }
    if (typeof value === "object" && typeof value.toISO === "function") {
        const iso = value.toISO();
        return iso ? iso.slice(0, 10) : value;
    }
    return value;
}

function buildLeavePreviewVals(record, changes) {
    const vals = {};
    for (const [key, value] of Object.entries(changes || {})) {
        vals[key] = serializeFieldValue(value);
    }
    const data = record.data || {};
    for (const fieldName of LEAVE_PREVIEW_FIELDS) {
        if (vals[fieldName] !== undefined && vals[fieldName] !== false) {
            continue;
        }
        if (data[fieldName] === undefined || data[fieldName] === false) {
            continue;
        }
        vals[fieldName] = serializeFieldValue(data[fieldName]);
    }
    return vals;
}

patch(FormController.prototype, {
    async onWillSaveRecord(record, changes) {
        const sup = await super.onWillSaveRecord(...arguments);
        if (sup === false) {
            return false;
        }
        if (record.resModel !== "hr.leave") {
            return true;
        }
        const preview = await this.orm.call(
            "hr.leave",
            "check_leave_form_save_confirmations",
            [],
            {
                res_id: record.resId || false,
                vals: buildLeavePreviewVals(record, changes),
            },
            {
                context: {
                    ...this.model.config.context,
                },
            }
        );
        if (preview.blocked) {
            await new Promise((resolve) => {
                this.dialogService.add(ConfirmationDialog, {
                    title: preview.title || _t("Cannot save"),
                    body: preview.message,
                    confirmLabel: _t("OK"),
                    confirm: () => resolve(),
                    cancel: () => resolve(),
                });
            });
            return false;
        }
        if (!preview.needs_confirmation) {
            return true;
        }
        const confirmed = await new Promise((resolve) => {
            this.dialogService.add(ConfirmationDialog, {
                title: preview.title || _t("Xác nhận"),
                body: preview.message,
                confirmLabel: _t("Tiếp tục"),
                cancelLabel: _t("Hủy"),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
        if (!confirmed) {
            return false;
        }
        if (preview.set_emergency_confirmed) {
            Object.assign(this.model.config.context, { [EMERGENCY_CTX]: true });
        }
        if (preview.set_con_lai_zero_confirmed) {
            Object.assign(this.model.config.context, { [CON_LAI_ZERO_CTX]: true });
        }
        return true;
    },
    async onRecordSaved(record) {
        const res = await super.onRecordSaved(...arguments);
        if (record.resModel === "hr.leave") {
            if (EMERGENCY_CTX in this.model.config.context) {
                delete this.model.config.context[EMERGENCY_CTX];
            }
            if (CON_LAI_ZERO_CTX in this.model.config.context) {
                delete this.model.config.context[CON_LAI_ZERO_CTX];
            }
        }
        return res;
    },
});
