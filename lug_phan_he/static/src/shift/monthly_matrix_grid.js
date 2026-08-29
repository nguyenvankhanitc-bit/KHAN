/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const COUNT_CODES = ["S2", "S4", "S9", "C1", "GS1", "GS2", "GC1", "F8", "F7"];
const JOB_TITLES = ["NV", "NT", "CHT", "NVPT", "TV", "ASM", "RSM"];
const HOUR_MAP = {
    S2: 6.5,
    S4: 6.0,
    S9: 8.0,
    C1: 7.0,
    GS1: 10.0,
    GS2: 8.0,
    GC1: 10.0,
    F8: 12.5,
    F7: 13.0,
    OFF: 0,
    LE: 0,
    "LỄ": 0,
};

function displayCode(raw) {
    let value = (raw || "").toString().replace(/（/g, "(").trim();
    if (!value) {
        return "";
    }
    value = value.split("(")[0].trim().split(/\s+/)[0];
    return value.toUpperCase();
}

function cellClass(code) {
    const value = displayCode(code);
    if (!value) {
        return "";
    }
    if (value === "OFF" || value === "LE" || value === "LỄ") {
        return "is-off";
    }
    if (value.startsWith("F")) {
        return "is-full";
    }
    if (value.startsWith("GC") || value.startsWith("GS")) {
        return "is-split";
    }
    if (value.startsWith("S") || value.startsWith("C")) {
        return "is-half";
    }
    return "";
}

export class MonthlyMatrixGrid extends X2ManyField {
    static template = "lug_phan_he.MonthlyMatrixGrid";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.catalog = useState({ options: [] });
        this.state = useState({
            isDirty: false,
            isSaving: false,
            pendingChanges: {},
        });
        onWillStart(async () => {
            this.catalog.options = await this.loadShiftOptions();
        });
    }

    async loadShiftOptions() {
        try {
            const rows = await this.orm.searchRead(
                "linkq.shift.code",
                [],
                ["code"],
                { order: "sequence, code" }
            );
            const options = [];
            const seen = new Set();
            for (const rec of rows) {
                const code = displayCode(rec.code);
                if (!code || seen.has(code)) {
                    continue;
                }
                seen.add(code);
                options.push(code);
            }
            if (!seen.has("LE") && !seen.has("LỄ")) {
                options.push("LE");
            }
            return options;
        } catch {
            return ["S2", "S4", "S9", "C1", "GC1", "F7", "F8", "OFF", "LE"];
        }
    }

    get roster() {
        return this.props.record;
    }

    get days() {
        return Array.from({ length: 31 }, (_, index) => index + 1);
    }

    get headers() {
        return this.roster.data.weekday_json || [];
    }

    get countCodes() {
        return COUNT_CODES;
    }

    get jobTitles() {
        return JOB_TITLES;
    }

    get shiftOptions() {
        return this.catalog.options || [];
    }

    get daysInMonth() {
        return this.roster.data.days_in_month || 31;
    }

    get confirmed() {
        return this.roster.data.state === "confirmed";
    }

    getShiftOptionsFor(line, kind, day) {
        const options = [...this.shiftOptions];
        const current = this.codeOf(line, kind, day);
        if (current && !options.includes(current)) {
            options.unshift(current);
        }
        return options;
    }

    headerOf(day) {
        const header = this.headers[day - 1];
        const fallbackValid = day <= this.daysInMonth;
        if (!header) {
            return { day, wd: "", weekend: false, sunday: false, holiday: "", valid: fallbackValid };
        }
        return { ...header, valid: header.valid !== false && fallbackValid };
    }

    lineKey(line) {
        return String(line.resId || line.id);
    }

    mergedMap(line, kind) {
        const field = kind === "actual" ? "actual_codes" : "plan_codes";
        const result = { ...(line.data[field] || {}) };
        const keyPrefix = `${this.lineKey(line)}_${kind}_`;
        for (const [changeKey, item] of Object.entries(this.state.pendingChanges)) {
            if (!changeKey.startsWith(keyPrefix) || item.meta) {
                continue;
            }
            result[String(item.day)] = item.code || "";
        }
        return result;
    }

    codeOf(line, kind, day) {
        const changeKey = `${this.lineKey(line)}_${kind}_${day}`;
        const pending = this.state.pendingChanges[changeKey];
        if (pending && !pending.meta) {
            return displayCode(pending.code);
        }
        const map = line.data[kind === "actual" ? "actual_codes" : "plan_codes"] || {};
        const raw = (map[String(day)] || map[day] || "").toString();
        return displayCode(raw.split(" ")[0].split("(")[0]);
    }

    hourOf(line, day) {
        const actual = this.codeOf(line, "actual", day);
        const plan = this.codeOf(line, "plan", day);
        const code = actual || plan;
        if (!code) {
            return "";
        }
        const hours = HOUR_MAP[code];
        return hours === undefined ? "" : hours;
    }

    countOf(line, kind, code) {
        const map = this.mergedMap(line, kind);
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            if (displayCode(map[String(day)] || map[day] || "") === code) {
                total += 1;
            }
        }
        return total;
    }

    hoursTotal(line, kind) {
        const map = this.mergedMap(line, kind);
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            const code = displayCode(map[String(day)] || map[day] || "");
            total += HOUR_MAP[code] || 0;
        }
        return total;
    }

    hourRowTotal(line) {
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            total += Number(this.hourOf(line, day) || 0);
        }
        return total;
    }

    metaOf(line, field) {
        const changeKey = `${this.lineKey(line)}_meta_${field}`;
        const pending = this.state.pendingChanges[changeKey];
        if (pending) {
            return pending.value;
        }
        return line.data[field];
    }

    markDirty(changeKey, payload) {
        this.state.pendingChanges = {
            ...this.state.pendingChanges,
            [changeKey]: payload,
        };
        this.state.isDirty = true;
    }

    onCellChange(line, kind, day, ev) {
        if (this.confirmed) {
            return;
        }
        const code = displayCode(ev.target.value);
        ev.target.value = code;
        this.markDirty(`${this.lineKey(line)}_${kind}_${day}`, {
            line_id: line.resId || false,
            lineKey: this.lineKey(line),
            day,
            shift_type: kind,
            code,
        });
    }

    onMetaInput(line, field, ev) {
        if (this.confirmed) {
            return;
        }
        let value = ev.target.value;
        if (field === "employee_code") {
            const parsed = parseInt(value, 10);
            value = Number.isFinite(parsed) ? parsed : 0;
        }
        this.markDirty(`${this.lineKey(line)}_meta_${field}`, {
            line_id: line.resId || false,
            lineKey: this.lineKey(line),
            meta: true,
            shift_type: field,
            value,
        });
    }

    async onSaveSchedule() {
        if (!this.state.isDirty || this.state.isSaving) {
            return;
        }
        const rosterId = this.roster.resId;
        if (!rosterId) {
            this.notification.add("Hãy lưu bảng xếp ca trước khi lưu lưới ca.", {
                type: "warning",
            });
            return;
        }
        const pending = Object.values(this.state.pendingChanges);
        const missingLine = pending.find((item) => !item.line_id);
        if (missingLine) {
            this.notification.add("Lưu nhân viên mới trên phiếu trước, rồi lưu lưới ca.", {
                type: "warning",
            });
            return;
        }
        this.state.isSaving = true;
        try {
            const result = await this.orm.call(
                "linkq.monthly.roster",
                "action_save_shift_grid",
                [rosterId, pending]
            );
            if (result && result.success) {
                this.notification.add("Đã lưu bảng phân ca thành công!", { type: "success" });
                this.state.pendingChanges = {};
                this.state.isDirty = false;
                if (this.roster.load) {
                    await this.roster.load();
                }
            } else {
                this.notification.add((result && result.message) || "Không lưu được bảng ca.", {
                    type: "danger",
                });
            }
        } catch (error) {
            this.notification.add(
                "Có lỗi xảy ra khi lưu: " + (error.message || error.data?.message || ""),
                { type: "danger" }
            );
        } finally {
            this.state.isSaving = false;
        }
    }

    onCancelChanges() {
        this.state.pendingChanges = {};
        this.state.isDirty = false;
        if (this.roster.load) {
            this.roster.load();
        }
    }

    cellClass(code) {
        return cellClass(code);
    }

    employeeName(line) {
        const emp = line.data.employee_id;
        return Array.isArray(emp) ? emp[1] : emp?.display_name || "";
    }

    async onAddEmployee() {
        if (this.confirmed) {
            return;
        }
        const first = this.list.records[0];
        const sequence = first ? Number(first.data.sequence || 10) - 1 : 1;
        const options = {
            context: { default_sequence: sequence },
            mode: "edit",
        };
        if (typeof this.list.addNewRecordAtIndex === "function") {
            await this.list.addNewRecordAtIndex(0, options);
            return;
        }
        await this.list.addNewRecord({
            ...options,
            position: "top",
        });
    }
}

export const monthlyMatrixGrid = {
    ...x2ManyField,
    component: MonthlyMatrixGrid,
};

registry.category("fields").add("monthly_matrix_grid", monthlyMatrixGrid);
registry.category("fields").add("monthly_matrix", monthlyMatrixGrid);
