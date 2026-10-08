/** @odoo-module **/

import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

/** Các cột cho phép kéo-copy kiểu Excel */
const FILLABLE_FIELDS = new Set([
    "name",
    "work_group_id",
    "south_user_ids",
    "dtt_user_ids",
    "north_user_ids",
    "office_user_ids",
    "assignee_user_ids",
    "detail_user_ids",
    "check_user_ids",
    "coord_user_ids",
    "participant_ids",
    "note",
]);

function isAssignFillList(renderer) {
    const list = renderer?.props?.list;
    if (!list || list.resModel !== "daily.task.assign") {
        return false;
    }
    if (renderer.props.readonly) {
        return false;
    }
    const root =
        renderer.tableRef?.el?.closest(".o_list_view") ||
        renderer.__owl__?.bdom?.el?.closest?.(".o_list_view");
    return !root || root.classList.contains("o_daily_task_assign_list");
}

function serverWriteValue(record, fieldName) {
    const field = record.fields[fieldName];
    if (!field) {
        return undefined;
    }
    const value = record.data[fieldName];
    switch (field.type) {
        case "many2many":
        case "one2many": {
            const ids = value?.currentIds || value?.resIds || [];
            return [[6, 0, [...ids]]];
        }
        case "many2one":
        case "many2one_reference":
            return value ? value.resId || value.id || false : false;
        case "boolean":
            return !!value;
        case "integer":
        case "float":
        case "monetary":
            return value === false || value === undefined ? false : value;
        default:
            return value === undefined ? false : value;
    }
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this._dtaFill = {
            active: false,
            fieldName: null,
            sourceIndex: -1,
            endIndex: -1,
            sourceRecordId: null,
        };
        this._dtaOnPointerMove = this._dtaOnPointerMove.bind(this);
        this._dtaOnPointerUp = this._dtaOnPointerUp.bind(this);

        onMounted(() => this._dtaRefreshFillHandles());
        onPatched(() => this._dtaRefreshFillHandles());
        onWillUnmount(() => this._dtaCleanupFill());
    },

    _dtaCleanupFill() {
        document.removeEventListener("pointermove", this._dtaOnPointerMove, true);
        document.removeEventListener("pointerup", this._dtaOnPointerUp, true);
        document.removeEventListener("pointercancel", this._dtaOnPointerUp, true);
        this._dtaClearFillHighlight();
        this._dtaFill.active = false;
    },

    _dtaRefreshFillHandles() {
        if (!isAssignFillList(this)) {
            return;
        }
        const table = this.tableRef?.el;
        if (!table) {
            return;
        }
        table.classList.add("o_dta_fill_enabled");

        const cells = table.querySelectorAll("tbody tr.o_data_row td.o_data_cell[name]");
        for (const td of cells) {
            const name = td.getAttribute("name");
            if (!FILLABLE_FIELDS.has(name)) {
                continue;
            }
            td.classList.add("o_dta_fillable");
            if (td.querySelector(":scope > .o_dta_fill_handle")) {
                continue;
            }
            const handle = document.createElement("span");
            handle.className = "o_dta_fill_handle";
            handle.title = "Kéo xuống để copy (như Excel)";
            handle.addEventListener("pointerdown", (ev) => this._dtaOnFillPointerDown(ev));
            td.appendChild(handle);
        }
    },

    _dtaOnFillPointerDown(ev) {
        if (!isAssignFillList(this) || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();

        const td = ev.currentTarget.closest("td.o_data_cell");
        const tr = td?.closest("tr.o_data_row");
        if (!td || !tr) {
            return;
        }
        const fieldName = td.getAttribute("name");
        if (!FILLABLE_FIELDS.has(fieldName)) {
            return;
        }
        const records = this.props.list.records;
        const sourceIndex = records.findIndex((r) => r.id === tr.dataset.id);
        if (sourceIndex < 0) {
            return;
        }

        this._dtaFill = {
            active: true,
            fieldName,
            sourceIndex,
            endIndex: sourceIndex,
            sourceRecordId: tr.dataset.id,
        };
        this._dtaPaintFillRange(sourceIndex, sourceIndex, fieldName);

        document.addEventListener("pointermove", this._dtaOnPointerMove, true);
        document.addEventListener("pointerup", this._dtaOnPointerUp, true);
        document.addEventListener("pointercancel", this._dtaOnPointerUp, true);
    },

    _dtaOnPointerMove(ev) {
        if (!this._dtaFill.active) {
            return;
        }
        const el = document.elementFromPoint(ev.clientX, ev.clientY);
        const tr = el?.closest?.("tr.o_data_row");
        if (!tr || !this.tableRef?.el?.contains(tr)) {
            return;
        }
        const records = this.props.list.records;
        const idx = records.findIndex((r) => r.id === tr.dataset.id);
        if (idx < 0) {
            return;
        }
        this._dtaFill.endIndex = idx;
        this._dtaPaintFillRange(this._dtaFill.sourceIndex, idx, this._dtaFill.fieldName);
    },

    async _dtaOnPointerUp(ev) {
        if (!this._dtaFill.active) {
            return;
        }
        document.removeEventListener("pointermove", this._dtaOnPointerMove, true);
        document.removeEventListener("pointerup", this._dtaOnPointerUp, true);
        document.removeEventListener("pointercancel", this._dtaOnPointerUp, true);

        const { fieldName, sourceIndex, endIndex } = this._dtaFill;
        this._dtaFill.active = false;
        this._dtaClearFillHighlight();

        if (sourceIndex < 0 || endIndex < 0 || sourceIndex === endIndex) {
            return;
        }

        const list = this.props.list;
        const records = list.records;
        const source = records[sourceIndex];
        if (!source) {
            return;
        }

        const from = Math.min(sourceIndex, endIndex);
        const to = Math.max(sourceIndex, endIndex);
        const targets = [];
        for (let i = from; i <= to; i++) {
            if (i === sourceIndex) {
                continue;
            }
            const rec = records[i];
            if (rec?.resId) {
                targets.push(rec);
            }
        }
        if (!targets.length) {
            return;
        }

        const writeValue = serverWriteValue(source, fieldName);
        if (writeValue === undefined) {
            return;
        }

        try {
            if (list.editedRecord) {
                await list.leaveEditMode();
            }
            await this.orm.write(
                list.resModel,
                targets.map((r) => r.resId),
                { [fieldName]: writeValue }
            );
            await list.model.load();
            this.notificationService.add(
                `Đã copy xuống ${targets.length} dòng`,
                { type: "success" }
            );
        } catch (error) {
            console.error(error);
            this.notificationService.add("Không copy được. Thử lại.", { type: "danger" });
        }
    },

    _dtaPaintFillRange(sourceIndex, endIndex, fieldName) {
        this._dtaClearFillHighlight();
        const table = this.tableRef?.el;
        if (!table) {
            return;
        }
        const rows = table.querySelectorAll("tbody tr.o_data_row");
        const from = Math.min(sourceIndex, endIndex);
        const to = Math.max(sourceIndex, endIndex);
        for (let i = from; i <= to; i++) {
            const tr = rows[i];
            if (!tr) {
                continue;
            }
            const cell = tr.querySelector(`td.o_data_cell[name="${fieldName}"]`);
            if (cell) {
                cell.classList.add("o_dta_fill_range");
                if (i === sourceIndex) {
                    cell.classList.add("o_dta_fill_source");
                }
            }
        }
        table.classList.add("o_dta_filling");
    },

    _dtaClearFillHighlight() {
        const table = this.tableRef?.el;
        if (!table) {
            return;
        }
        table.classList.remove("o_dta_filling");
        table
            .querySelectorAll(".o_dta_fill_range, .o_dta_fill_source")
            .forEach((el) => el.classList.remove("o_dta_fill_range", "o_dta_fill_source"));
    },
});
