/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

let uidSeq = 1;

function makeRow(data) {
    return {
        uid: "r" + uidSeq++,
        id: data.id || 0,
        name: data.name || "",
        file_name: data.file_name || "",
        size: data.size || "",
        kind: data.kind || "pdf",
        perm_view: data.perm_view !== false,
        perm_download: Boolean(data.perm_download),
        file_b64: "",
    };
}

export class GuideDocsManageDialog extends Component {
    static template = "lug_phan_he.GuideDocsManageDialog";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: true, rows: [] });
        onWillStart(async () => {
            try {
                const rows = (await this.orm.call("linkq.guide.document", "get_guide_manage_rows", [])) || [];
                this.state.rows = rows.map((r) => makeRow(r));
            } catch (_e) {
                this.state.rows = [];
            }
            this.state.loading = false;
        });
        onMounted(() => this.syncInputs());
        onPatched(() => this.syncInputs());
    }

    syncInputs() {
        const root = this.el;
        if (!root) {
            return;
        }
        const titles = root.querySelectorAll(".input-title");
        this.state.rows.forEach((row, i) => {
            if (titles[i] && document.activeElement !== titles[i]) {
                titles[i].value = row.name;
            }
            const checks = root.querySelectorAll("tbody tr")[i]?.querySelectorAll("input[type=checkbox]");
            if (checks && checks.length >= 2) {
                checks[0].checked = row.perm_view;
                checks[1].checked = row.perm_download;
            }
        });
    }

    get el() {
        return document.querySelector(".o_guide_manage");
    }

    setTitle(row, ev) {
        row.name = ev.target.value;
    }

    togglePerm(row, key, ev) {
        row[key] = ev.target.checked;
    }

    addRow() {
        this.state.rows.push(
            makeRow({
                id: 0,
                name: "",
                perm_view: true,
                perm_download: true,
                kind: "pdf",
            })
        );
    }

    removeRow(row) {
        this.state.rows = this.state.rows.filter((r) => r.uid !== row.uid);
    }

    changeFile(row) {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".pdf,.xlsx,.xls,.doc,.docx";
        input.onchange = () => {
            const file = input.files && input.files[0];
            if (!file) {
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                row.file_name = file.name;
                row.file_b64 = String(reader.result || "");
                row.kind = file.name.toLowerCase().match(/\.xlsx?$/) ? "xlsx" : "pdf";
                const kb = file.size / 1024;
                row.size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
            };
            reader.readAsDataURL(file);
        };
        input.click();
    }

    async saveRows() {
        try {
            await this.orm.call("linkq.guide.document", "save_guide_rows", [
                this.state.rows.map((r) => ({
                    id: r.id,
                    name: r.name,
                    file_name: r.file_name,
                    size: r.size,
                    perm_view: r.perm_view,
                    perm_download: r.perm_download,
                    file_b64: r.file_b64,
                })),
            ]);
            this.notification.add("Đã lưu tài liệu hướng dẫn.", { type: "success" });
            this.props.close();
        } catch (_e) {
            this.notification.add("Không lưu được tài liệu.", { type: "danger" });
        }
    }
}
