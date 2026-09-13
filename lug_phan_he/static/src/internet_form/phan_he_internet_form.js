/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { FileInput } from "@web/core/file_input/file_input";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { isBinarySize } from "@web/core/utils/binary";
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { INTERNET_NAV_TO_CODE, internetMenuCan } from "../access/internet_menu_nav";

export class PhanHeInternetFormController extends FormController {
    static template = "lug_phan_he.InternetFormView";

    setup() {
        super.setup();
        this.internetMenus = {};
        this._baseCanCreate = this.canCreate;
        this._baseCanEdit = this.canEdit;
        onWillStart(async () => {
            try {
                const rights = await this.orm.call("phan.he.module.access", "get_user_module_rights", []);
                this.internetMenus = rights?.internet_menus || {};
            } catch {
                this.internetMenus = {};
            }
            this._applyInternetActionFlags();
        });
    }

    get internetMenuCode() {
        const ctx = this.props.context || {};
        if (ctx.phan_he_internet_menu) {
            return ctx.phan_he_internet_menu;
        }
        const status = this.model?.root?.data?.ops_status || "active";
        return INTERNET_NAV_TO_CODE[`list_${status}`] || "internet_active";
    }

    _inetCan(op) {
        return internetMenuCan(this.internetMenus, this.internetMenuCode, op);
    }

    _applyInternetActionFlags() {
        this.canCreate = Boolean(this._baseCanCreate && this._inetCan("create"));
        this.canEdit = Boolean(this._baseCanEdit && this._inetCan("write"));
        const root = this.model?.root;
        if (!root) {
            return;
        }
        if (!this.canEdit && root.isInEdition && !root.isNew) {
            Promise.resolve(root.switchMode("readonly")).catch(() => {});
            return;
        }
        if (this.canEdit && !root.isInEdition && !root.isNew) {
            const mode = this.props.context?.form_view_initial_mode;
            if (mode === "edit" && !this.props.readonly && !this.props.preventEdit) {
                Promise.resolve(root.switchMode("edit")).catch(() => {});
            }
        }
    }

    get isEditing() {
        return Boolean(this.model?.root?.isInEdition);
    }

    async onClickEdit() {
        if (!this.canEdit || !this._inetCan("write")) {
            return;
        }
        if (!this.model?.root || this.model.root.isInEdition) {
            return;
        }
        await this.model.root.switchMode("edit");
    }

    async onClickSave() {
        await this.saveButtonClicked({ closable: false });
    }

    async onClickCancel() {
        try {
            if (this.model?.root?.isInEdition) {
                await this.model.root.discard();
            }
        } catch {
            /* ignore */
        }
        if (this.props.onDiscard) {
            this.props.onDiscard(this.model.root);
            return;
        }
        if (this.env.config.historyBack) {
            this.env.config.historyBack();
        }
    }
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            const b64 = result.includes(",") ? result.split(",")[1] : result;
            resolve(b64);
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

export class PhanHeDropzoneField extends Component {
    static template = "lug_phan_he.InvoiceDropzone";
    static components = { FileInput };
    static props = {
        ...standardFieldProps,
        acceptedFileExtensions: { type: String, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.drop = useState({ over: false });
    }

    get fileName() {
        return this.props.record.data.invoice_filename || "";
    }

    get extraFiles() {
        const list = this.props.record.data.invoice_attachment_ids;
        return (list?.records || []).map((rec) => ({
            id: rec.resId,
            name: rec.data.name || rec.data.display_name || "file",
        }));
    }

    getUrl(id) {
        return "/web/content/" + id + "?download=false";
    }

    guessMime(name) {
        const ext = String(name || "").split(".").pop().toLowerCase();
        return {
            pdf: "application/pdf",
            png: "image/png",
            jpg: "image/jpeg",
            jpeg: "image/jpeg",
            gif: "image/gif",
            webp: "image/webp",
            doc: "application/msword",
            docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            xls: "application/vnd.ms-excel",
            xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }[ext] || "application/octet-stream";
    }

    b64ToBlob(b64, mime) {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
            bytes[i] = bin.charCodeAt(i);
        }
        return new Blob([bytes], { type: mime });
    }

    onViewMain(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const rec = this.props.record;
        const value = rec.data[this.props.name];
        const filename = encodeURIComponent(this.fileName || "hoa_don");
        if (typeof value === "string" && value.length > 8 && !isBinarySize(value)) {
            const url = URL.createObjectURL(this.b64ToBlob(value, this.guessMime(this.fileName)));
            window.open(url, "_blank", "noopener");
            return;
        }
        if (rec.resId) {
            window.open(
                `/web/content/${rec.resModel}/${rec.resId}/${this.props.name}?download=false&filename=${filename}`,
                "_blank",
                "noopener"
            );
        }
    }

    onDragOver(ev) {
        ev.preventDefault();
        this.drop.over = true;
    }

    onDragLeave() {
        this.drop.over = false;
    }

    async applyFiles(fileList) {
        const files = [...fileList];
        if (!files.length || this.props.readonly) {
            return;
        }
        const first = files[0];
        const b64 = await fileToBase64(first);
        await this.props.record.update({
            [this.props.name]: b64,
            invoice_filename: first.name,
        });
    }

    async onDrop(ev) {
        ev.preventDefault();
        this.drop.over = false;
        await this.applyFiles(ev.dataTransfer?.files || []);
    }

    async onInputChange(ev) {
        await this.applyFiles(ev.target.files || []);
        ev.target.value = "";
    }

    async onFileUploaded(files) {
        const mapped = (files || []).map((f) => f.file || f).filter(Boolean);
        if (mapped.length && mapped[0] instanceof Blob) {
            await this.applyFiles(mapped);
        }
    }

    async clearMain() {
        await this.props.record.update({
            [this.props.name]: false,
            invoice_filename: false,
        });
    }
}

const fields = registry.category("fields");
fields.add("phan_he_dropzone", {
        component: PhanHeDropzoneField,
        supportedTypes: ["binary"],
        extractProps: ({ attrs, options }) => ({
            acceptedFileExtensions: options.accepted_file_extensions || ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
            className: attrs.class,
        }),
    }, { force: true });

const views = registry.category("views");
if (!views.contains("phan_he_internet_form")) {
    views.add("phan_he_internet_form", {
        ...formView,
        Controller: PhanHeInternetFormController,
    });
}
