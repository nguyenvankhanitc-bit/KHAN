/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

export class GuideDocsDialog extends Component {
    static template = "lug_phan_he.GuideDocsDialog";
    static components = { Dialog };
    static props = {
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            documents: [],
            searchTerm: "",
        });
        onWillStart(async () => {
            await this.loadDocuments();
        });
    }

    async loadDocuments() {
        try {
            const rows = await this.orm.call("shift.guide.document", "get_popup_documents", []);
            this.state.documents = rows || [];
        } catch (_e) {
            this.state.documents = [
                {
                    id: 0,
                    name: "Hướng dẫn sử dụng lịch ca",
                    file_type: "pdf",
                    file_size_text: "2.4 MB",
                    updated: "01/09/2026",
                    has_file: false,
                },
                {
                    id: 0,
                    name: "Mẫu Excel nhập lịch ca",
                    file_type: "xlsx",
                    file_size_text: "125 KB",
                    updated: "28/08/2026",
                    has_file: false,
                },
                {
                    id: 0,
                    name: "Quy định về khóa lịch ca",
                    file_type: "pdf",
                    file_size_text: "850 KB",
                    updated: "20/08/2026",
                    has_file: false,
                },
            ];
        }
    }

    onSearch(ev) {
        this.state.searchTerm = ev.target.value || "";
    }

    docsList() {
        const term = (this.state.searchTerm || "").trim().toLowerCase();
        if (!term) {
            return this.state.documents;
        }
        return this.state.documents.filter((doc) => (doc.name || "").toLowerCase().includes(term));
    }

    fileIcon(type) {
        if (type === "xlsx") {
            return "fa fa-file-excel-o text-success fs-2 mt-1";
        }
        if (type === "docx") {
            return "fa fa-file-word-o text-primary fs-2 mt-1";
        }
        return "fa fa-file-pdf-o text-danger fs-2 mt-1";
    }

    downloadBtnClass(type) {
        return type === "xlsx" ? "btn btn-sm btn-success" : "btn btn-sm o_guide_btn_purple";
    }

    openDoc(doc, download) {
        const url = download ? doc.download_url : doc.view_url;
        if (!url) {
            this.notification.add("Tài liệu chưa được tải file lên hệ thống.", { type: "warning" });
            return;
        }
        window.open(url, download ? "_self" : "_blank");
    }
}
