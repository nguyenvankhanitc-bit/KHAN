/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class GuideDocsDialog extends Component {
    static template = "lug_phan_he.GuideDocsDialog";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            isAdmin: false,
            documents: [],
            searchTerm: "",
        });
        onWillStart(async () => {
            this.state.isAdmin =
                (await user.hasGroup("base.group_system")) ||
                (await user.hasGroup("lug_phan_he.group_phan_he_admin"));
            await this.loadData();
        });
        onMounted(() => this.syncAdminInputs());
        onPatched(() => this.syncAdminInputs());
    }

    syncAdminInputs() {
        if (!this.state.isAdmin) {
            return;
        }
        const rows = document.querySelectorAll(".o_guide_admin_table tbody tr");
        this.state.documents.forEach((doc, i) => {
            const tr = rows[i];
            if (!tr) {
                return;
            }
            const num = tr.querySelector("input[type=number]");
            const text = tr.querySelector("input[type=text]");
            const checks = tr.querySelectorAll("input[type=checkbox]");
            if (num && document.activeElement !== num) {
                num.value = doc.sequence == null ? "" : doc.sequence;
            }
            if (text && document.activeElement !== text) {
                text.value = doc.name || "";
            }
            if (checks[0] && document.activeElement !== checks[0]) {
                checks[0].checked = Boolean(doc.allow_view);
            }
            if (checks[1] && document.activeElement !== checks[1]) {
                checks[1].checked = Boolean(doc.allow_download);
            }
        });
    }

    async loadData() {
        const fields = [
            "id",
            "sequence",
            "name",
            "file_name",
            "file_type",
            "file_size_text",
            "allow_view",
            "allow_download",
            "write_date",
        ];
        const domain = this.state.isAdmin
            ? [["active", "=", true]]
            : [
                  ["active", "=", true],
                  ["allow_view", "=", true],
              ];
        try {
            this.state.documents = await this.orm.searchRead("shift.guide.document", domain, fields);
        } catch (_e) {
            this.state.documents = [];
        }
    }

    addNewRow() {
        const nextSeq = this.state.documents.length + 1;
        this.state.documents.push({
            id: false,
            sequence: nextSeq,
            name: "",
            file_data: false,
            file_name: "",
            file_type: "pdf",
            file_size_text: "",
            allow_view: true,
            allow_download: true,
            isNew: true,
        });
    }

    async deleteRow(doc, index) {
        if (doc.id) {
            await this.orm.unlink("shift.guide.document", [doc.id]);
        }
        this.state.documents.splice(index, 1);
        this.notification.add("Đã xóa dòng tài liệu", { type: "info" });
    }

    onFileChange(ev, doc) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            const raw = String(e.target.result || "");
            doc.file_data = raw.includes(",") ? raw.split(",")[1] : raw;
            doc.file_name = file.name;
            const sizeKb = file.size / 1024;
            doc.file_size_text =
                sizeKb >= 1024 ? (sizeKb / 1024).toFixed(1) + " MB" : Math.round(sizeKb) + " KB";
            const lower = file.name.toLowerCase();
            if (lower.endsWith(".pdf")) {
                doc.file_type = "pdf";
            } else if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
                doc.file_type = "xlsx";
            } else if (lower.endsWith(".docx") || lower.endsWith(".doc")) {
                doc.file_type = "docx";
            } else {
                doc.file_type = "other";
            }
        };
        reader.readAsDataURL(file);
    }

    setName(doc, ev) {
        doc.name = ev.target.value;
    }

    setSequence(doc, ev) {
        doc.sequence = parseInt(ev.target.value, 10) || 0;
    }

    toggleAllow(doc, key, ev) {
        doc[key] = ev.target.checked;
    }

    onSearch(ev) {
        this.state.searchTerm = ev.target.value || "";
    }

    async saveAdminData() {
        try {
            for (const doc of this.state.documents) {
                if (!(doc.name || "").trim()) {
                    continue;
                }
                const vals = {
                    sequence: doc.sequence,
                    name: doc.name,
                    allow_view: Boolean(doc.allow_view),
                    allow_download: Boolean(doc.allow_download),
                };
                if (doc.file_data) {
                    vals.file_data = doc.file_data;
                    vals.file_name = doc.file_name;
                }
                if (doc.id) {
                    await this.orm.write("shift.guide.document", [doc.id], vals);
                } else if (doc.file_data) {
                    await this.orm.create("shift.guide.document", [vals]);
                }
            }
            this.notification.add("Cập nhật tài liệu thành công!", { type: "success" });
            await this.loadData();
        } catch (_e) {
            this.notification.add("Không lưu được tài liệu.", { type: "danger" });
        }
    }

    get filteredDocuments() {
        const term = (this.state.searchTerm || "").trim().toLowerCase();
        if (!term) {
            return this.state.documents;
        }
        return this.state.documents.filter((d) => (d.name || "").toLowerCase().includes(term));
    }

    formatDate(dateStr) {
        if (!dateStr) {
            return "";
        }
        const raw = String(dateStr).replace(" ", "T");
        const d = new Date(raw.endsWith("Z") ? raw : raw + "Z");
        if (Number.isNaN(d.getTime())) {
            return "";
        }
        const dd = String(d.getDate()).padStart(2, "0");
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        return dd + "/" + mm + "/" + d.getFullYear();
    }

    getFileIcon(type) {
        if (type === "pdf") {
            return "fa-file-pdf-o text-danger";
        }
        if (type === "xlsx") {
            return "fa-file-excel-o text-success";
        }
        if (type === "docx") {
            return "fa-file-word-o text-primary";
        }
        return "fa-file-text-o text-secondary";
    }

    downloadBtnClass(type) {
        return type === "xlsx" ? "btn btn-sm btn-success" : "btn btn-sm o_guide_btn_purple";
    }
}
