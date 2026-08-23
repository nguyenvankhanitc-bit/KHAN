/** @odoo-module **/

import { Component, onMounted, onPatched, useState, xml } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";
import { FileInput } from "@web/core/file_input/file_input";
import { useFileUploader } from "@web/core/utils/files";
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field";

const LUG_LIST_STYLE_ID = "lug-project-list-grid-v11";
const LUG_LIST_CSS = `
.o_lps_view_host .o_list_view .o_list_renderer,
.o_list_view.o_lug_project_list .o_list_renderer {
    overflow: auto !important;
    min-height: 0 !important;
}
.o_lps_view_host .o_list_view .o_list_table,
.o_list_view.o_lug_project_list .o_list_table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
    border: 1px solid #64748b !important;
}
.o_lps_view_host .o_list_view .o_list_table thead,
.o_list_view.o_lug_project_list .o_list_table thead {
    position: sticky !important;
    top: 0 !important;
    z-index: 8 !important;
}
.o_lps_view_host .o_list_view .o_list_table thead th,
.o_list_view.o_lug_project_list .o_list_table thead th {
    position: sticky !important;
    top: 0 !important;
    z-index: 8 !important;
    background: #e2e8f0 !important;
    color: #0f172a !important;
    font-weight: 800 !important;
    border: 1px solid #64748b !important;
    box-shadow: inset 0 0 0 1px #64748b !important;
    text-align: center !important;
    white-space: normal !important;
    overflow: visible !important;
    vertical-align: middle !important;
    line-height: 1.2 !important;
    min-width: 4.2rem;
}
.o_lps_view_host .o_list_view .o_list_table thead th .text-truncate,
.o_list_view.o_lug_project_list .o_list_table thead th .text-truncate {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    text-align: center !important;
    min-width: 0 !important;
    width: 100% !important;
}
.o_lps_view_host .o_list_view .o_list_table thead th .d-flex,
.o_list_view.o_lug_project_list .o_list_table thead th .d-flex {
    justify-content: center !important;
    flex-wrap: wrap !important;
    text-align: center !important;
}
.o_lps_view_host .o_list_view .o_list_table tbody td,
.o_lps_view_host .o_list_view .o_list_table tbody th,
.o_list_view.o_lug_project_list .o_list_table tbody td,
.o_list_view.o_lug_project_list .o_list_table tbody th,
.o_lps_view_host .o_list_view .o_list_table .o_data_row > td,
.o_list_view.o_lug_project_list .o_list_table .o_data_row > td {
    border: 1px solid #94a3b8 !important;
    border-bottom-width: 1px !important;
    border-right-width: 1px !important;
    box-shadow: inset 0 0 0 1px #94a3b8 !important;
    outline: 1px solid #94a3b8 !important;
    outline-offset: -1px !important;
    background-clip: padding-box !important;
}
.o_lps_view_host .o_list_view .o_list_table th[data-name="lug_stt"],
.o_lps_view_host .o_list_view .o_list_table td[name="lug_stt"],
.o_list_view.o_lug_project_list th[data-name="lug_stt"],
.o_list_view.o_lug_project_list td[name="lug_stt"] {
    text-align: center !important;
}
.o_lps_view_host .o_list_view .o_list_table td[name="lug_content"],
.o_list_view.o_lug_project_list td[name="lug_content"] {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    word-break: break-word !important;
    max-width: 240px;
    min-width: 140px;
    vertical-align: middle !important;
}
.o_lug_workers {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    cursor: pointer;
    color: #1d4ed8;
    max-width: 160px;
}
.o_lug_workers img {
    width: 22px;
    height: 22px;
    border-radius: 99px;
    object-fit: cover;
    flex: 0 0 auto;
}
.o_lug_workers span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.o_lug_drop {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    min-width: 88px;
    padding: 2px 4px;
    border: 1px dashed #94a3b8;
    border-radius: 6px;
    background: #f8fafc;
    cursor: pointer;
    gap: 0.3rem;
}
.o_lug_drop.is-over {
    border-color: #2563eb;
    background: #dbeafe;
}
.o_lug_drop .fa {
    font-size: 1.05rem;
}
.o_lug_drop.is-pdf .fa { color: #dc2626; }
.o_lug_drop.is-word .fa { color: #2563eb; }
.o_lug_drop.is-excel .fa { color: #15803d; }
.o_lug_drop em {
    font-style: normal;
    font-size: 0.72rem;
    color: #334155;
    max-width: 72px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.o_lps_view_host .o_list_view .o_list_button,
.o_list_view.o_lug_project_list .o_list_button {
    white-space: nowrap !important;
    text-align: center !important;
    width: 4.5rem !important;
    min-width: 4.5rem !important;
}
.o_lug_btn_edit {
    color: #2563eb !important;
    font-size: 1.1rem !important;
    line-height: 1 !important;
}
.o_lug_btn_del {
    color: #dc2626 !important;
    font-size: 1.1rem !important;
    line-height: 1 !important;
}
`;

function injectLugListGridCss() {
    if (typeof document === "undefined") {
        return;
    }
    let el = document.getElementById(LUG_LIST_STYLE_ID);
    if (!el) {
        el = document.createElement("style");
        el.id = LUG_LIST_STYLE_ID;
        document.head.appendChild(el);
    }
    el.textContent = LUG_LIST_CSS;
}

function paintLugListGrid(table) {
    if (!table) {
        return;
    }
    table.style.setProperty("border-collapse", "separate", "important");
    table.style.setProperty("border-spacing", "0", "important");
    table.style.setProperty("border", "1px solid #64748b", "important");
    const renderer = table.closest(".o_list_renderer");
    if (renderer) {
        renderer.style.setProperty("overflow", "auto", "important");
        renderer.setAttribute("data-lps-list", "grid-v10");
        const content = renderer.closest(".o_content");
        if (content) {
            content.style.setProperty("overflow", "hidden", "important");
            content.style.setProperty("display", "flex", "important");
            content.style.setProperty("flex-direction", "column", "important");
            content.style.setProperty("min-height", "0", "important");
        }
    }
    table.querySelectorAll("thead th").forEach((th) => {
        th.style.setProperty("position", "sticky", "important");
        th.style.setProperty("top", "0", "important");
        th.style.setProperty("z-index", "8", "important");
        th.style.setProperty("background", "#e2e8f0", "important");
        th.style.setProperty("border", "1px solid #64748b", "important");
        th.style.setProperty("font-weight", "800", "important");
        th.style.setProperty("text-align", "center", "important");
        th.style.setProperty("white-space", "normal", "important");
        th.style.setProperty("overflow", "visible", "important");
    });
    table.querySelectorAll("tbody td, tbody th").forEach((cell) => {
        cell.style.setProperty("border", "1px solid #94a3b8", "important");
        cell.style.setProperty("border-bottom-width", "1px", "important");
        cell.style.setProperty("box-shadow", "inset 0 0 0 1px #94a3b8", "important");
        cell.style.setProperty("outline", "1px solid #94a3b8", "important");
        cell.style.setProperty("outline-offset", "-1px", "important");
    });
}

injectLugListGridCss();

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        injectLugListGridCss();
        const paint = () => {
            const table = this.tableRef?.el;
            if (!table) {
                return;
            }
            if (table.closest(".o_lug_task_detail, .o_lug_intake_form, .o_form_view")) {
                return;
            }
            if (!table.closest(".o_lug_project_list, .o_lps_view_host .o_list_view")) {
                return;
            }
            paintLugListGrid(table);
        };
        onMounted(paint);
        onPatched(paint);
    },
});

export class LugTimeleftField extends Component {
    static props = { ...standardFieldProps };
    static template = xml`
        <span t-att-class="'o_lug_tl is-' + meta.state">
            <i t-if="meta.state === 'done'" class="fa fa-check-square"/>
            <i t-elif="meta.state === 'ok' or meta.state === 'late'" class="fa fa-circle"/>
            <span t-esc="meta.label"/>
        </span>
    `;

    get meta() {
        const raw = this.props.record.data[this.props.name] || "none|—";
        const sep = String(raw).indexOf("|");
        if (sep < 0) {
            return { state: "none", label: raw || "—" };
        }
        const state = String(raw).slice(0, sep) || "none";
        let label = String(raw).slice(sep + 1) || "—";
        const dayMatch = label.match(/^(\d+)\s*ngày$/);
        if (state === "ok" && dayMatch) {
            label = `Còn ${dayMatch[1]} ngày`;
        } else if (state === "late" && dayMatch) {
            label = `Trễ ${dayMatch[1]} ngày`;
        }
        return { state, label };
    }
}

export class LugPdfField extends Component {
    static props = { ...standardFieldProps };
    static template = xml`
        <button t-if="hasPdf" type="button" class="btn btn-link p-0 o_lug_pdf_btn" title="Tải PDF" t-on-click.stop="onClick">
            <i class="fa fa-file-pdf-o"/>
        </button>
        <span t-else="" class="text-muted">—</span>
    `;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get hasPdf() {
        return Boolean(this.props.record.data[this.props.name]);
    }

    async onClick() {
        const id = this.props.record.resId;
        if (!id) {
            return;
        }
        const act = await this.orm.call("project.project", "lug_action_open_pdf", [id]);
        if (act) {
            await this.action.doAction(act);
        }
    }
}

registry.category("fields").add("lug_timeleft", {
    component: LugTimeleftField,
    supportedTypes: ["char"],
});

registry.category("fields").add("lug_pdf_link", {
    component: LugPdfField,
    supportedTypes: ["many2one"],
});

const LUG_DOC_EXTS = [".pdf", ".doc", ".docx", ".xls", ".xlsx"];

function lugFileKind(name) {
    const lower = String(name || "").toLowerCase();
    if (lower.endsWith(".pdf")) {
        return "pdf";
    }
    if (lower.endsWith(".doc") || lower.endsWith(".docx")) {
        return "word";
    }
    if (lower.endsWith(".xls") || lower.endsWith(".xlsx")) {
        return "excel";
    }
    return "";
}

function lugIsAllowedFile(name) {
    const lower = String(name || "").toLowerCase();
    return LUG_DOC_EXTS.some((ext) => lower.endsWith(ext));
}

export class LugWorkersField extends Component {
    static props = { ...standardFieldProps };
    static template = xml`
        <div class="o_lug_workers" t-on-click.stop="onClick" title="Xem người làm">
            <t t-if="workers.length">
                <img t-att-src="'/web/image/res.users/' + workers[0].id + '/avatar_128'" alt=""/>
                <span t-esc="label"/>
            </t>
            <span t-else="" class="text-muted">—</span>
        </div>
    `;

    setup() {
        this.action = useService("action");
    }

    get workers() {
        const data = this.props.record.data[this.props.name];
        const recs = data?.records || [];
        return recs
            .filter((rec) => rec.resId)
            .map((rec) => ({
                id: rec.resId,
                name: rec.data.display_name || rec.data.name || "User",
            }));
    }

    get label() {
        const list = this.workers;
        if (!list.length) {
            return "—";
        }
        const first = (list[0].name || "").trim().split(/\s+/)[0] || list[0].name;
        return list.length > 1 ? `${first} +${list.length - 1}` : list[0].name;
    }

    async onClick() {
        const ids = this.workers.map((item) => item.id);
        if (!ids.length) {
            return;
        }
        if (ids.length === 1) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.users",
                res_id: ids[0],
                views: [[false, "form"]],
                target: "new",
            });
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Người làm",
            res_model: "res.users",
            domain: [["id", "in", ids]],
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "new",
        });
    }
}

export class LugFileDropField extends Component {
    static props = { ...standardFieldProps };
    static components = { FileInput };
    static template = xml`
        <div t-att-class="dropClass"
             t-on-click.stop=""
             t-on-dragenter.prevent="onDragEnter"
             t-on-dragover.prevent="onDragEnter"
             t-on-dragleave.prevent="onDragLeave"
             t-on-drop.prevent.stop="onDrop">
            <FileInput
                acceptedFileExtensions="'.pdf,.doc,.docx,.xls,.xlsx'"
                resModel="'project.project'"
                resId="props.record.resId || 0"
                onUpload.bind="onUploaded"
                onWillUploadFiles.bind="filterFiles">
                <t t-if="fileName">
                    <i t-att-class="fileIcon"/>
                    <em t-esc="fileName" t-on-click.stop="onOpen"/>
                </t>
                <t t-else="">
                    <i class="fa fa-cloud-upload"/>
                    <em>Thả file</em>
                </t>
            </FileInput>
        </div>
    `;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.uploadFiles = useFileUploader();
        this.state = useState({ hovering: false });
    }

    get fileName() {
        const value = this.props.record.data[this.props.name];
        return value?.display_name || "";
    }

    get fileKind() {
        return lugFileKind(this.fileName);
    }

    get fileIcon() {
        const kind = this.fileKind;
        if (kind === "word") {
            return "fa fa-file-word-o";
        }
        if (kind === "excel") {
            return "fa fa-file-excel-o";
        }
        return "fa fa-file-pdf-o";
    }

    get dropClass() {
        const kind = this.fileKind || "empty";
        return `o_lug_drop is-${kind}${this.state.hovering ? " is-over" : ""}`;
    }

    filterFiles(files) {
        const allowed = [...files].filter((file) => lugIsAllowedFile(file.name));
        if (allowed.length !== files.length) {
            this.notification.add("Chỉ nhận file Word, PDF hoặc Excel.", { type: "warning" });
        }
        if (!allowed.length) {
            throw new Error("invalid-file");
        }
        return allowed;
    }

    onDragEnter() {
        this.state.hovering = true;
    }

    onDragLeave() {
        this.state.hovering = false;
    }

    async onDrop(ev) {
        this.state.hovering = false;
        const id = this.props.record.resId;
        if (!id) {
            this.notification.add("Lưu dự án trước khi đính file.", { type: "warning" });
            return;
        }
        const files = [...(ev.dataTransfer?.files || [])];
        try {
            this.filterFiles(files);
        } catch {
            return;
        }
        const parsed = await this.uploadFiles("/web/binary/upload_attachment", {
            csrf_token: odoo.csrf_token,
            ufile: files.filter((file) => lugIsAllowedFile(file.name)),
            model: "project.project",
            id,
        });
        await this.onUploaded(parsed || []);
    }

    async onUploaded(files) {
        const ids = (files || []).filter((file) => file && file.id && !file.error).map((file) => file.id);
        if (!ids.length) {
            const err = (files || []).find((file) => file?.error);
            if (err) {
                this.notification.add(err.error, { type: "danger" });
            }
            return;
        }
        await this.orm.call("project.project", "lug_action_link_files", [this.props.record.resId, ids]);
        await this.props.record.load();
    }

    async onOpen() {
        const id = this.props.record.resId;
        if (!id) {
            return;
        }
        const act = await this.orm.call("project.project", "lug_action_open_pdf", [id]);
        if (act) {
            await this.action.doAction(act);
        }
    }
}

registry.category("fields").add("lug_workers", {
    component: LugWorkersField,
    supportedTypes: ["many2many"],
    relatedFields: [{ name: "display_name", type: "char" }],
});

registry.category("fields").add("lug_file_drop", {
    component: LugFileDropField,
    supportedTypes: ["many2one"],
    listViewWidth: [110],
});

const LUG_INTAKE_STYLE_ID = "lug-intake-sheet-v2";
const LUG_INTAKE_CSS = `
.o_form_view.o_lug_intake_form .o_control_panel,
.o_lug_intake_form .o_control_panel,
.modal .o_form_view.o_lug_intake_form .o_control_panel {
    display: none !important;
}
.o_form_view.o_lug_intake_form .o_form_sheet_bg,
.o_form_view.o_lug_intake_form .o_form_sheet {
    max-width: 100% !important;
    width: 100% !important;
    background: #f7f4fc !important;
    box-shadow: none !important;
    border: none !important;
}
.o_form_view.o_lug_intake_form .o_form_sheet {
    padding: 0.4rem 1.1rem 1.6rem !important;
}
.o_form_view.o_lug_intake_form .o_form_statusbar {
    display: flex !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    gap: 0.55rem 0.7rem !important;
    padding: 0.85rem 1.1rem 0.35rem !important;
    background: #f7f4fc !important;
    border: none !important;
}
.o_form_view.o_lug_intake_form .o_statusbar_buttons {
    display: flex !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    gap: 0.55rem 0.7rem !important;
    flex: 1 1 auto;
    min-width: 0;
}
.o_form_view.o_lug_intake_form .o_lug_crumb {
    flex: 1 0 100%;
    order: -1;
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
}
.o_form_view.o_lug_intake_form .o_lug_crumb > span:first-child {
    color: #7c3aed;
    font-weight: 700;
}
.o_form_view.o_lug_intake_form .o_lug_crumb_sep {
    color: #94a3b8;
}
.o_form_view.o_lug_intake_form .o_lug_crumb .o_field_widget,
.o_form_view.o_lug_intake_form .o_lug_crumb textarea {
    flex: 1;
    min-width: 0;
    min-height: 0 !important;
    height: 34px !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 1.12rem !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    resize: none !important;
    overflow: hidden !important;
    padding: 0 !important;
}
.o_form_view.o_lug_intake_form .o_lug_btn_save,
.o_form_view.o_lug_intake_form .o_form_statusbar .oe_highlight,
.o_form_view.o_lug_intake_form .o_statusbar_buttons .oe_highlight {
    background: #7c3aed !important;
    border: 1px solid #7c3aed !important;
    color: #fff !important;
    font-weight: 800 !important;
    border-radius: 8px !important;
    padding: 0.38rem 1.15rem !important;
}
.o_form_view.o_lug_intake_form .o_lug_btn_cancel {
    background: #fff !important;
    border: 1.5px solid #7c3aed !important;
    color: #7c3aed !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
    padding: 0.35rem 1.05rem !important;
}
.o_form_view.o_lug_intake_form .o_statusbar_status,
.o_form_view.o_lug_intake_form .o_field_statusbar {
    margin-left: auto !important;
}
.o_form_view.o_lug_intake_form .o_statusbar_status {
    display: flex !important;
    flex-direction: row-reverse !important;
}
.o_form_view.o_lug_intake_form .o_arrow_button {
    font-weight: 700 !important;
    color: #64748b !important;
    background: #fff !important;
}
.o_form_view.o_lug_intake_form .o_arrow_button.o_arrow_button_current,
.o_form_view.o_lug_intake_form .o_arrow_button.btn-primary {
    background: #7c3aed !important;
    color: #fff !important;
}
.o_form_view.o_lug_intake_form .o_lug_summary {
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(0, 1.1fr);
    gap: 0;
    background: #fff;
    border: 1px solid #e9d5ff;
    border-radius: 12px;
    overflow: hidden;
    margin: 0.55rem 0 1rem;
}
.o_form_view.o_lug_intake_form .o_lug_summary_side {
    display: flex;
    flex-direction: column;
    min-width: 0;
}
.o_form_view.o_lug_intake_form .o_lug_summary_side .o_lug_card {
    border-right: none;
}
.o_form_view.o_lug_intake_form .o_lug_form_actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.55rem;
    padding: 0.85rem 1.1rem 1rem;
}
.o_form_view.o_lug_intake_form .o_lug_form_actions .o_lug_btn_save,
.o_form_view.o_lug_intake_form .o_lug_form_actions .oe_highlight {
    background: #7c3aed !important;
    border: 1px solid #7c3aed !important;
    color: #fff !important;
    font-weight: 800 !important;
    border-radius: 8px !important;
    padding: 0.38rem 1.15rem !important;
}
.o_form_view.o_lug_intake_form .o_lug_form_actions .o_lug_btn_cancel {
    background: #fff !important;
    border: 1.5px solid #7c3aed !important;
    color: #7c3aed !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
    padding: 0.35rem 1.05rem !important;
}
.o_form_view.o_lug_intake_form .o_lug_card {
    padding: 0.95rem 1.1rem 1rem;
    border-right: 1px solid #ede9fe;
    min-width: 0;
}
.o_form_view.o_lug_intake_form .o_lug_card:last-child {
    border-right: none;
}
.o_form_view.o_lug_intake_form .o_lug_card h3,
.o_form_view.o_lug_intake_form .o_lug_tasks_block h3 {
    margin: 0 0 0.85rem;
    color: #6d28d9;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.04em;
}
.o_form_view.o_lug_intake_form .o_lug_kv {
    display: grid;
    grid-template-columns: 132px minmax(0, 1fr);
    gap: 0.28rem 0.65rem;
    align-items: center;
    margin-bottom: 0.48rem;
}
.o_form_view.o_lug_intake_form .o_lug_k {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 600;
}
.o_form_view.o_lug_intake_form .o_lug_kv .o_field_widget {
    margin-bottom: 0 !important;
    width: 100%;
}
.o_form_view.o_lug_intake_form .o_lug_kv textarea {
    min-height: 34px !important;
    height: 34px !important;
    resize: vertical;
    padding: 0.28rem 0.5rem !important;
}
.o_form_view.o_lug_intake_form .o_lug_kv_file .o_field_many2many_binary,
.o_form_view.o_lug_intake_form .o_lug_kv_file .o_field_widget {
    border: 1px dashed #94a3b8;
    border-radius: 8px;
    background: #f8fafc;
    padding: 0.25rem 0.4rem;
    min-height: 36px;
}
.o_form_view.o_lug_intake_form .o_lug_card .o_lug_tl {
    font-size: 0.98rem;
    font-weight: 800;
}
.o_form_view.o_lug_intake_form .o_lug_card .o_lug_tl.is-ok {
    color: #16a34a;
}
.o_form_view.o_lug_intake_form .o_lug_card .o_lug_tl.is-late {
    color: #dc2626;
}
.o_lug_ring {
    position: relative;
    width: 148px;
    height: 148px;
    margin: 0.2rem auto 0;
}
.o_lug_ring_svg { width: 100%; height: 100%; }
.o_lug_ring_bg { fill: none; stroke: #ede9fe; stroke-width: 12; }
.o_lug_ring_fg {
    fill: none;
    stroke: #22c55e;
    stroke-width: 12;
    stroke-linecap: round;
    transform: rotate(-90deg);
    transform-origin: 60px 60px;
}
.o_lug_ring_pct {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.55rem;
    font-weight: 800;
    color: #0f172a;
}
.o_form_view.o_lug_intake_form .o_lug_tasks_block {
    background: #fff;
    border: 2px solid #ddd6fe;
    border-radius: 14px;
    padding: 1rem 1.1rem 0.85rem;
    margin: 1rem 0 1.25rem;
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
    box-shadow: 0 2px 10px rgba(109, 40, 217, 0.07);
}
.o_lug_task_detail .o_list_table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
}
.o_lug_task_detail .o_list_table thead th {
    background: #f8fafc !important;
    color: #475569 !important;
    font-weight: 800 !important;
    text-align: center !important;
    white-space: normal !important;
    border-bottom: 1px solid #e2e8f0 !important;
}
.o_lug_task_detail .o_list_table tbody td {
    border-bottom: 1px solid #f1f5f9 !important;
    vertical-align: middle !important;
}
.o_lug_task_detail .o_list_table td[name="name"],
.o_lug_task_detail .o_list_table th[data-name="name"] {
    text-align: left !important;
}
.o_lug_task_detail .o_list_table td[name="lug_line_stt"] {
    text-align: center !important;
    color: #64748b;
    font-weight: 700;
}
.o_lug_phase {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.12rem 0.62rem;
    font-size: 0.75rem;
    font-weight: 700;
    white-space: nowrap;
}
.o_lug_phase.is-1 { background: #dcfce7; color: #166534; }
.o_lug_phase.is-2 { background: #ecfccb; color: #3f6212; }
.o_lug_phase.is-3 { background: #ffedd5; color: #9a3412; }
.o_lug_phase.is-4 { background: #ede9fe; color: #6d28d9; }
.o_lug_phase.is-5 { background: #dbeafe; color: #1d4ed8; }
.o_lug_phase.is-6 { background: #e2e8f0; color: #334155; }
.o_lug_phase.is-none { background: #f1f5f9; color: #94a3b8; }
.o_lug_status {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.12rem 0.62rem;
    font-size: 0.75rem;
    font-weight: 700;
    white-space: nowrap;
}
.o_lug_status.is-todo { background: #f1f5f9; color: #475569; }
.o_lug_status.is-progress { background: #fff; color: #2563eb; border: 1px solid #60a5fa; }
.o_lug_status.is-review { background: #fff7ed; color: #c2410c; }
.o_lug_status.is-done { background: #dcfce7; color: #166534; }
.o_lug_status.is-cancel { background: #f1f5f9; color: #94a3b8; }
.o_lug_task_detail .o_field_x2many_list_row_add a {
    font-size: 0 !important;
}
.o_lug_task_detail .o_field_x2many_list_row_add a::before {
    content: "+ Thêm dòng";
    font-size: 0.88rem;
    font-weight: 800;
    color: #7c3aed;
}
.o_lug_task_detail .o_list_record_open_form_view button {
    font-size: 0 !important;
    width: 30px;
    height: 30px;
    padding: 0 !important;
    border-radius: 8px;
    background: #ede9fe;
    line-height: 30px;
}
.o_lug_task_detail .o_list_record_open_form_view button::before {
    content: "✎";
    font-family: inherit;
    font-size: 14px;
    color: #7c3aed;
}
.o_lug_task_detail .o_list_record_remove button {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: #fee2e2;
    color: #dc2626 !important;
    line-height: 30px;
}
.o_form_view.o_lug_intake_form .o_lug_intake_notebook {
    background: #fff;
    border: 1px solid #ede9fe;
    border-radius: 12px;
    padding: 0.35rem 0.7rem 0.7rem;
}
@media (max-width: 1100px) {
    .o_form_view.o_lug_intake_form .o_lug_summary {
        grid-template-columns: 1fr;
    }
    .o_form_view.o_lug_intake_form .o_lug_card {
        border-right: none;
        border-bottom: 1px solid #ede9fe;
    }
}
`;

function injectLugIntakeCss() {
    if (typeof document === "undefined") {
        return;
    }
    let el = document.getElementById(LUG_INTAKE_STYLE_ID);
    if (!el) {
        el = document.createElement("style");
        el.id = LUG_INTAKE_STYLE_ID;
        document.head.appendChild(el);
    }
    el.textContent = LUG_INTAKE_CSS;
}

injectLugIntakeCss();

export class LugProgressRingField extends Component {
    static props = { ...standardFieldProps };
    static template = xml`
        <div class="o_lug_ring" t-att-title="pct + '%'">
            <svg class="o_lug_ring_svg" viewBox="0 0 120 120">
                <circle class="o_lug_ring_bg" cx="60" cy="60" r="52"/>
                <circle class="o_lug_ring_fg" cx="60" cy="60" r="52" t-att-stroke-dasharray="dashArray"/>
            </svg>
            <div class="o_lug_ring_pct"><t t-esc="pct"/>%</div>
        </div>
    `;

    get pct() {
        const n = Number(this.props.record.data[this.props.name]) || 0;
        return Math.max(0, Math.min(100, Math.round(n)));
    }

    get dashArray() {
        const c = 2 * Math.PI * 52;
        return `${(this.pct / 100) * c} ${c}`;
    }
}

export class LugPhaseBadgeField extends SelectionField {
    static template = xml`
        <t t-if="props.readonly">
            <span t-att-class="'o_lug_phase is-' + (value || 'none')" t-esc="string || '—'"/>
        </t>
        <t t-else="">
            <select class="o_input o_lug_phase_select" t-on-change="onNativeChange">
                <option value="" t-att-selected="!value">Chọn...</option>
                <t t-foreach="options" t-as="opt" t-key="opt[0]">
                    <option t-att-value="opt[0]" t-att-selected="value === opt[0]" t-esc="opt[1]"/>
                </t>
            </select>
        </t>
    `;

    onNativeChange(ev) {
        const raw = ev.target.value;
        this.onChange(raw === "" ? false : raw);
    }
}

export class LugStatusPillField extends SelectionField {
    static template = xml`
        <t t-if="props.readonly">
            <span t-att-class="'o_lug_status is-' + (value || 'todo')" t-esc="string || '—'"/>
        </t>
        <t t-else="">
            <select class="o_input o_lug_status_select" t-on-change="onNativeChange">
                <t t-foreach="options" t-as="opt" t-key="opt[0]">
                    <option t-att-value="opt[0]" t-att-selected="value === opt[0]" t-esc="opt[1]"/>
                </t>
            </select>
        </t>
    `;

    onNativeChange(ev) {
        this.onChange(ev.target.value || false);
    }
}

registry.category("fields").add("lug_progress_ring", {
    component: LugProgressRingField,
    supportedTypes: ["integer"],
});

registry.category("fields").add("lug_phase_badge", {
    ...selectionField,
    component: LugPhaseBadgeField,
    supportedTypes: ["selection"],
});

registry.category("fields").add("lug_status_pill", {
    ...selectionField,
    component: LugStatusPillField,
    supportedTypes: ["selection"],
});

