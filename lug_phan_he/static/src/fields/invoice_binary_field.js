/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FileInput } from "@web/core/file_input/file_input";
import { useX2ManyCrud } from "@web/views/fields/relational_utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

export class PhanHeInvoiceBinaryField extends Component {
    static template = "lug_phan_he.InvoiceBinaryField";
    static components = { FileInput };
    static props = {
        ...standardFieldProps,
        acceptedFileExtensions: { type: String, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.operations = useX2ManyCrud(() => this.props.record.data[this.props.name], true);
    }

    get uploadText() {
        return this.props.record.fields[this.props.name].string || _t("Tải file hóa đơn");
    }

    get files() {
        const list = this.props.record.data[this.props.name];
        if (!list || !list.records) {
            return [];
        }
        return list.records.map((record) => ({
            ...record.data,
            id: record.resId,
        }));
    }

    getUrl(id) {
        return "/web/content/" + id + "?download=true";
    }

    getExtension(file) {
        return (file.name || "").replace(/^.*\./, "");
    }

    isImage(file) {
        return Boolean(file.mimetype && String(file.mimetype).startsWith("image/"));
    }

    async onFileUploaded(files) {
        try {
            for (const file of files) {
                if (file.error) {
                    this.notification.add(file.error, {
                        title: _t("Lỗi tải file"),
                        type: "danger",
                    });
                    return;
                }
                if (file.id) {
                    await this.operations.saveRecord([file.id]);
                }
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || _t("Không đính kèm được hóa đơn."),
                { type: "danger" }
            );
        }
    }

    async onFileRemove(deleteId) {
        const list = this.props.record.data[this.props.name];
        const record = list.records.find((rec) => rec.resId === deleteId);
        if (record) {
            this.operations.removeRecord(record);
        }
    }
}

export const phanHeInvoiceBinaryField = {
    component: PhanHeInvoiceBinaryField,
    supportedTypes: ["many2many"],
    isEmpty: () => false,
    relatedFields: [
        { name: "name", type: "char" },
        { name: "mimetype", type: "char" },
    ],
    extractProps: ({ attrs, options }) => ({
        acceptedFileExtensions: options.accepted_file_extensions || ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
        className: attrs.class,
    }),
};

registry.category("fields").add("phan_he_invoice_files", phanHeInvoiceBinaryField);
