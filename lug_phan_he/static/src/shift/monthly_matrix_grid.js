/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const COUNT_CODES = ["S2", "S4", "S9", "C1", "GS1", "GS2", "GC1", "F8", "F7"];
const JOB_TITLES = ["NV", "NT", "CHT", "NVPT", "TV", "ASM", "RSM"];

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
        this.catalog = useState({ options: [] });
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

    codeOf(line, kind, day) {
        const map = line.data[kind === "actual" ? "actual_codes" : "plan_codes"] || {};
        const raw = (map[String(day)] || map[day] || "").toString();
        return displayCode(raw.split(" ")[0].split("(")[0]);
    }

    hourOf(line, day) {
        const map = line.data.hour_codes || {};
        const value = map[String(day)] || map[day] || "";
        return value === "" || value === 0 ? "" : value;
    }

    countOf(line, kind, code) {
        const map = line.data[kind === "actual" ? "count_actual" : "count_plan"] || {};
        return map[code] || 0;
    }

    cellClass(code) {
        return cellClass(code);
    }

    employeeName(line) {
        const emp = line.data.employee_id;
        return Array.isArray(emp) ? emp[1] : emp?.display_name || "";
    }

    async onCellChange(line, kind, day, ev) {
        if (this.confirmed) {
            return;
        }
        const field = kind === "actual" ? "actual_codes" : "plan_codes";
        const next = { ...(line.data[field] || {}) };
        next[String(day)] = displayCode(ev.target.value);
        ev.target.value = next[String(day)];
        await line.update({ [field]: next });
    }

    async onMetaInput(line, field, ev) {
        if (this.confirmed) {
            return;
        }
        if (field === "employee_code") {
            const parsed = parseInt(ev.target.value, 10);
            await line.update({ employee_code: Number.isFinite(parsed) ? parsed : 0 });
            return;
        }
        await line.update({ [field]: ev.target.value });
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
