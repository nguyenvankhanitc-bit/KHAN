/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const COUNT_CODES = ["S2", "S4", "S9", "C1", "GS1", "GS2", "GC", "F8", "F7"];
const JOB_TITLES = ["NV", "NT", "CHT", "NVPT", "TV", "ASM", "RSM"];
const WEEKDAY_LABELS = new Set(["T2", "T3", "T4", "T5", "T6", "T7", "CN"]);
const FALLBACK_SHIFT_CODES = ["S2", "S4", "S9", "C1", "GS1", "GS2", "GC1", "F7", "F8", "OFF", "LE"];
const HOUR_MAP = {
    S2: 6.5,
    S4: 6.0,
    S9: 8.0,
    C1: 7.0,
    GS1: 10.0,
    GS2: 8.0,
        GC1: 10.0,
    GC: 10.0,
    F8: 12.5,
    F7: 13.0,
    OFF: 0,
    LE: 0,
    "LỄ": 0,
};

function optionCode(opt) {
    if (opt == null || opt === false) {
        return "";
    }
    if (typeof opt === "string" || typeof opt === "number") {
        return displayCode(opt);
    }
    if (typeof opt === "object") {
        return displayCode(opt.code || opt.name || "");
    }
    return displayCode(opt);
}

function displayCode(raw) {
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        return displayCode(raw.code || "");
    }
    let value = (raw || "").toString().replace(/（/g, "(").trim();
    if (!value || value === "[OBJECT OBJECT]") {
        return "";
    }
    value = value.split("(")[0].trim().split(/\s+/)[0];
    value = value.toUpperCase();
    if (WEEKDAY_LABELS.has(value)) {
        return "";
    }
    return value;
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

function hoursFromLineData(line) {
    const hourCodes = line.data.hour_codes || {};
    let fromHours = 0;
    for (const value of Object.values(hourCodes)) {
        fromHours += Number(value || 0);
    }
    if (fromHours) {
        return fromHours;
    }
    const stored = Number(line.data.hour_total || 0);
    if (stored) {
        return stored;
    }
    const actual = line.data.actual_codes || {};
    const plan = line.data.plan_codes || {};
    let total = 0;
    for (let day = 1; day <= 31; day += 1) {
        const code = displayCode(
            actual[String(day)] || actual[day] || plan[String(day)] || plan[day] || ""
        );
        total += HOUR_MAP[code] || 0;
    }
    return total;
}

export class MonthlyMatrixGrid extends X2ManyField {
    static template = "lug_phan_he.MonthlyMatrixGrid";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.catalog = useState({ options: [], hours: {} });
        this.state = useState({
            isDirty: false,
            isSaving: false,
            pendingChanges: {},
            picker: null,
            hover: null,
            menu: null,
            editor: null,
        });
        this._lastCell = null;
        onWillStart(async () => {
            this.catalog.options = await this.loadShiftOptions();
        });
        onMounted(() => {
            this._onKeyDown = (ev) => this.onGridKeydown(ev);
            document.addEventListener("keydown", this._onKeyDown);
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeyDown);
        });
    }

    async loadShiftOptions() {
        try {
            const rows = await this.orm.searchRead(
                "linkq.shift.code",
                [],
                ["code", "total_hours"],
                { order: "sequence, code" }
            );
            const options = [];
            const hours = { ...HOUR_MAP, GC: 10 };
            const seen = new Set();
            for (const rec of rows) {
                const code = displayCode(rec.code);
                if (!code || WEEKDAY_LABELS.has(code) || seen.has(code)) {
                    continue;
                }
                seen.add(code);
                options.push(code);
                const recHours = Number(rec.total_hours);
                if (Number.isFinite(recHours) && recHours > 0) {
                    hours[code] = recHours;
                }
            }
            for (const extra of ["OFF", "LE"]) {
                if (!seen.has(extra)) {
                    seen.add(extra);
                    options.push(extra);
                }
            }
            this.catalog.hours = hours;
            return options.length ? options : FALLBACK_SHIFT_CODES;
        } catch {
            this.catalog.hours = { ...HOUR_MAP, GC: 10 };
            return FALLBACK_SHIFT_CODES;
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
        const raw = this.catalog.options || [];
        const options = [];
        const seen = new Set();
        for (const opt of raw) {
            const code = optionCode(opt);
            if (!code || WEEKDAY_LABELS.has(code) || seen.has(code)) {
                continue;
            }
            seen.add(code);
            options.push(code);
        }
        return options.length ? options : FALLBACK_SHIFT_CODES;
    }

    get daysInMonth() {
        return this.roster.data.days_in_month || 31;
    }

    get confirmed() {
        return this.roster.data.state === "confirmed";
    }

    get isEditMode() {
        return !this.props.readonly && !this.confirmed && !this.roster.data.is_locked && !this.roster.data.period_edit_blocked;
    }

    get hasEmployees() {
        return Boolean(this.list.records.length);
    }

    rowIndex(line) {
        return this.list.records.indexOf(line) + 1;
    }

    wdClass(day) {
        const header = this.headerOf(day);
        if (header.sunday) {
            return "is-sunday";
        }
        if (header.weekend) {
            return "is-weekend";
        }
        return "";
    }

    holidayClass(day) {
        return this.headerOf(day).holiday ? " is-holiday" : "";
    }

    lackClass(day) {
        const morning = this.roster.data.lack_morning || [];
        const evening = this.roster.data.lack_evening || [];
        if (morning[day - 1] || evening[day - 1]) {
            return " is-lack";
        }
        return "";
    }

    countOf(line, kind, code) {
        const map = this.mergedMap(line, kind);
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            const value = displayCode(map[String(day)] || map[day] || "");
            if (code === "GC") {
                if (value.startsWith("GC")) {
                    total += 1;
                }
            } else if (value === code) {
                total += 1;
            }
        }
        return total;
    }

    getShiftOptionsFor(line, kind, day) {
        const options = [...this.shiftOptions];
        const current = this.codeOf(line, kind, day);
        if (current && !WEEKDAY_LABELS.has(current) && !options.includes(current)) {
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
        if (!line) {
            return "0";
        }
        return String(line.resId || line.id || 0);
    }

    mergedMap(line, kind) {
        const field = kind === "actual" ? "actual_codes" : "plan_codes";
        const source = line.data[field] || {};
        const result = Array.isArray(source) ? {} : { ...source };
        if (Array.isArray(source)) {
            for (let d = 1; d <= 31; d += 1) {
                const code = displayCode(this.mapValue(source, d));
                if (code) {
                    result[String(d)] = code;
                }
            }
        }
        const keyPrefix = `${this.lineKey(line)}_${kind}_`;
        for (const [changeKey, item] of Object.entries(this.state.pendingChanges)) {
            if (!changeKey.startsWith(keyPrefix) || item.meta) {
                continue;
            }
            result[String(item.day)] = item.code || "";
        }
        return result;
    }

    mapValue(map, day) {
        if (!map) {
            return "";
        }
        if (Array.isArray(map)) {
            const item = map[day] ?? map[day - 1];
            return optionCode(item);
        }
        return map[String(day)] || map[day] || "";
    }

    codeOf(line, kind, day) {
        const changeKey = `${this.lineKey(line)}_${kind}_${day}`;
        const pending = this.state.pendingChanges[changeKey];
        if (pending && !pending.meta) {
            return displayCode(pending.code);
        }
        const map = line.data[kind === "actual" ? "actual_codes" : "plan_codes"] || {};
        return displayCode(this.mapValue(map, day));
    }

    hourOf(line, day) {
        const actual = this.codeOf(line, "actual", day);
        const plan = this.codeOf(line, "plan", day);
        const code = actual || plan;
        const mapped = this.hoursForCode(code);
        if (code && mapped !== 0) {
            return mapped;
        }
        if (code && this.hoursForCode(code) === 0 && (code === "OFF" || code === "LE" || code === "LỄ")) {
            return 0;
        }
        const stored = line.data.hour_codes || {};
        const raw = stored[String(day)] ?? stored[day];
        if (raw === 0 || raw === "0") {
            return 0;
        }
        return raw === undefined || raw === null || raw === "" ? (code ? mapped : "") : Number(raw);
    }

    hoursForCode(code) {
        const value = displayCode(code);
        if (!value) {
            return 0;
        }
        const catalogHours = this.catalog.hours || {};
        if (catalogHours[value] !== undefined && catalogHours[value] !== "") {
            return Number(catalogHours[value]) || 0;
        }
        if (HOUR_MAP[value] !== undefined) {
            return HOUR_MAP[value];
        }
        if (value.startsWith("GC")) {
            return Number(catalogHours.GC1 || catalogHours.GC || HOUR_MAP.GC1 || 10);
        }
        if (value.startsWith("GS") && value !== "GS1" && value !== "GS2") {
            return Number(catalogHours.GS1 || HOUR_MAP.GS1 || 10);
        }
        return 0;
    }

    hoursTotal(line, kind) {
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            total += this.hoursForCode(this.codeOf(line, kind, day));
        }
        if (total) {
            return total;
        }
        const stored = kind === "actual" ? line.data.actual_hours : line.data.plan_hours;
        return Number(stored || 0);
    }

    formatHours(value) {
        if (value === "" || value === null || value === undefined) {
            return "";
        }
        const num = Number(value);
        if (!Number.isFinite(num) || num === 0) {
            return value === 0 || value === "0" ? "0" : "";
        }
        if (Math.abs(num - Math.round(num)) < 0.05) {
            return String(Math.round(num));
        }
        return num.toFixed(1).replace(".", ",");
    }

    hourRowTotal(line) {
        let total = 0;
        for (let day = 1; day <= 31; day += 1) {
            total += Number(this.hourOf(line, day) || 0);
        }
        return total;
    }

    metaOf(line, field) {
        if (!line) {
            return "";
        }
        const changeKey = `${this.lineKey(line)}_meta_${field}`;
        const pending = this.state.pendingChanges[changeKey];
        if (pending) {
            return pending.value;
        }
        return (line.data && line.data[field]) || "";
    }

    markDirty(changeKey, payload) {
        this.state.pendingChanges = {
            ...this.state.pendingChanges,
            [changeKey]: payload,
        };
        this.state.isDirty = true;
    }

    onCellChange(line, kind, day, ev) {
        this.applyCellCode(line, kind, day, ev?.target?.value);
    }

    applyCellCode(line, kind, day, raw) {
        if (!this.isEditMode) {
            return;
        }
        const code = displayCode(raw);
        const field = kind === "actual" ? "actual_codes" : "plan_codes";
        const current = line.data[field] || {};
        const next = {};
        for (let d = 1; d <= 31; d += 1) {
            next[String(d)] = displayCode(this.mapValue(current, d));
        }
        next[String(day)] = code;
        if (typeof line.update === "function") {
            line.update({ [field]: next });
        }
        this.markDirty(`${this.lineKey(line)}_${kind}_${day}`, {
            line_id: line.resId || false,
            lineKey: this.lineKey(line),
            day,
            shift_type: kind,
            code,
        });
    }

    onOpenPicker(ev, line, kind, day) {
        if (!this.isEditMode || !this.headerOf(day).valid) {
            return;
        }
        this.rememberCell(line, kind, day);
        ev.preventDefault();
        ev.stopPropagation();
        const rect = ev.currentTarget.getBoundingClientRect();
        const key = `${this.lineKey(line)}_${kind}_${day}`;
        if (this.state.picker && this.state.picker.key === key) {
            this.state.picker = null;
            return;
        }
        const left = Math.min(rect.left, window.innerWidth - 240);
        const top = rect.bottom + 4 + 220 > window.innerHeight ? rect.top - 224 : rect.bottom + 4;
        this.state.picker = {
            key,
            lineKey: this.lineKey(line),
            kind,
            day,
            top,
            left: Math.max(8, left),
        };
    }

    onPickCode(code) {
        const picker = this.state.picker;
        if (!picker) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === picker.lineKey);
        if (line) {
            this.applyCellCode(line, picker.kind, picker.day, code);
        }
        this.state.picker = null;
    }

    closePicker() {
        this.state.picker = null;
        this.state.menu = null;
        this.state.hover = null;
        this.state.editor = null;
    }

    closeMenu() {
        this.state.menu = null;
    }

    noop() {}

    notesField(kind) {
        return kind === "actual" ? "actual_notes" : "plan_notes";
    }

    commentOf(line, kind, day) {
        const changeKey = `${this.lineKey(line)}_note_${kind}_${day}`;
        const pending = this.state.pendingChanges[changeKey];
        if (pending && pending.note !== undefined) {
            return pending.note || null;
        }
        const map = line.data[this.notesField(kind)] || {};
        const raw = map[String(day)] || map[day];
        if (!raw || typeof raw !== "object") {
            return null;
        }
        if (!(raw.content || raw.title)) {
            return null;
        }
        return raw;
    }

    hasComment(line, kind, day) {
        return Boolean(this.commentOf(line, kind, day));
    }

    formatNoteTime(value) {
        if (!value) {
            return "";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        const pad = (n) => String(n).padStart(2, "0");
        return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    currentAuthor() {
        return user.name || "";
    }

    rememberCell(line, kind, day) {
        this._lastCell = { lineKey: this.lineKey(line), kind, day };
    }

    applyComment(line, kind, day, comment) {
        if (!this.isEditMode) {
            return;
        }
        const field = this.notesField(kind);
        const current = line.data[field] || {};
        const next = { ...(Array.isArray(current) ? {} : current) };
        const key = String(day);
        if (comment && (comment.content || comment.title)) {
            next[key] = comment;
        } else {
            delete next[key];
        }
        if (typeof line.update === "function") {
            line.update({ [field]: next });
        }
        this.markDirty(`${this.lineKey(line)}_note_${kind}_${day}`, {
            line_id: line.resId || false,
            lineKey: this.lineKey(line),
            day,
            shift_type: `note_${kind}`,
            note: comment || null,
        });
    }

    onCellContextMenu(ev, line, kind, day) {
        if (!this.isEditMode || !this.headerOf(day).valid) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.rememberCell(line, kind, day);
        this.state.picker = null;
        this.state.editor = null;
        this.state.hover = null;
        this.state.menu = {
            lineKey: this.lineKey(line),
            kind,
            day,
            top: ev.clientY,
            left: Math.min(ev.clientX, window.innerWidth - 180),
            hasNote: this.hasComment(line, kind, day),
        };
    }

    onCellHover(ev, line, kind, day, show) {
        if (!show) {
            this.state.hover = null;
            return;
        }
        const note = this.commentOf(line, kind, day);
        if (!note) {
            this.state.hover = null;
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        this.state.hover = {
            title: note.title || "",
            content: note.content || "",
            author: note.author || "",
            updated_at: this.formatNoteTime(note.updated_at),
            top: rect.bottom + 8,
            left: Math.min(rect.left, window.innerWidth - 280),
        };
    }

    onCellDblClick(ev, line, kind, day) {
        if (!this.isEditMode || !this.headerOf(day).valid) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.openNoteEditor(line, kind, day, ev.currentTarget.getBoundingClientRect());
    }

    openNoteEditorFromMenu() {
        const menu = this.state.menu;
        if (!menu) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === menu.lineKey);
        this.state.menu = null;
        if (line) {
            this.openNoteEditor(line, menu.kind, menu.day, {
                bottom: menu.top,
                left: menu.left,
                top: menu.top - 28,
            });
        }
    }

    openNoteEditor(line, kind, day, rect) {
        if (!this.isEditMode) {
            return;
        }
        this.rememberCell(line, kind, day);
        const note = this.commentOf(line, kind, day) || {};
        this.state.picker = null;
        this.state.menu = null;
        this.state.hover = null;
        this.state.editor = {
            lineKey: this.lineKey(line),
            kind,
            day,
            title: note.title || "",
            content: note.content || "",
            top: Math.min((rect.bottom || rect.top || 80) + 6, window.innerHeight - 260),
            left: Math.min(rect.left || 16, window.innerWidth - 320),
        };
    }

    onEditorTitle(ev) {
        if (this.state.editor) {
            this.state.editor.title = ev.target.value;
        }
    }

    onEditorContent(ev) {
        if (this.state.editor) {
            this.state.editor.content = ev.target.value;
        }
    }

    saveNoteEditor() {
        const editor = this.state.editor;
        if (!editor) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === editor.lineKey);
        const title = (editor.title || "").trim();
        const content = (editor.content || "").trim();
        if (line) {
            if (!title && !content) {
                this.applyComment(line, editor.kind, editor.day, null);
            } else {
                this.applyComment(line, editor.kind, editor.day, {
                    title,
                    content,
                    author: this.currentAuthor(),
                    updated_at: new Date().toISOString(),
                });
            }
        }
        this.state.editor = null;
    }

    deleteNoteFromEditor() {
        const editor = this.state.editor;
        if (!editor) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === editor.lineKey);
        if (line) {
            this.applyComment(line, editor.kind, editor.day, null);
        }
        this.state.editor = null;
        this.state.menu = null;
    }

    deleteNoteFromMenu() {
        const menu = this.state.menu;
        if (!menu) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === menu.lineKey);
        if (line) {
            this.applyComment(line, menu.kind, menu.day, null);
        }
        this.state.menu = null;
    }

    cancelNoteEditor() {
        this.state.editor = null;
    }

    get hoverStyle() {
        const hover = this.state.hover;
        if (!hover) {
            return "";
        }
        return `top:${hover.top}px;left:${hover.left}px;`;
    }

    get menuStyle() {
        const menu = this.state.menu;
        if (!menu) {
            return "";
        }
        return `top:${menu.top}px;left:${menu.left}px;`;
    }

    get editorStyle() {
        const editor = this.state.editor;
        if (!editor) {
            return "";
        }
        return `top:${editor.top}px;left:${editor.left}px;`;
    }

    onGridKeydown(ev) {
        if (!this.isEditMode || !ev.shiftKey || ev.key !== "F2" || !this._lastCell) {
            return;
        }
        const line = this.list.records.find((rec) => this.lineKey(rec) === this._lastCell.lineKey);
        if (line) {
            ev.preventDefault();
            this.openNoteEditor(line, this._lastCell.kind, this._lastCell.day, {
                top: 120,
                left: 120,
                bottom: 148,
            });
        }
    }

    get pickerStyle() {
        const picker = this.state.picker;
        if (!picker) {
            return "";
        }
        return `top:${picker.top}px;left:${picker.left}px;`;
    }

    get pickerOptions() {
        return this.shiftOptions;
    }

    hydrateInput(ev, value) {
        const el = ev.target;
        if (!el || el.dataset.hydrated) {
            return;
        }
        el.dataset.hydrated = "1";
        if (el.value === "" && value != null && value !== "") {
            el.value = String(value);
        }
    }

    onMetaInput(line, field, ev) {
        if (!this.isEditMode) {
            return;
        }
        let value = ev.target.value;
        if (field === "employee_code") {
            const parsed = parseInt(value, 10);
            value = Number.isFinite(parsed) ? parsed : 0;
        }
        if (typeof line.update === "function") {
            line.update({ [field]: value });
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
        if (!line || !line.data) {
            return "";
        }
        const emp = line.data.employee_id;
        return Array.isArray(emp) ? emp[1] : emp?.display_name || "";
    }

    async onAddEmployee() {
        if (!this.isEditMode) {
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

export class MonthlyStaffSummary extends Component {
    static template = "lug_phan_he.MonthlyStaffSummary";
    static props = { ...standardFieldProps };

    get staffRows() {
        const rec = this.props.record;
        const list = rec?.data?.line_ids;
        const records = list?.records || [];
        return records.map((line, idx) => {
            const data = line.data || line;
            const emp = data.employee_id;
            const empName = Array.isArray(emp) ? emp[1] : emp?.display_name || "";
            const hours = hoursFromLineData({ data });
            const hoursTxt =
                Math.abs(hours - Math.round(hours)) < 0.05
                    ? String(Math.round(hours))
                    : Number(hours).toFixed(1).replace(".", ",");
            return {
                key: line.id || idx,
                idx: idx + 1,
                name: data.employee_name || empName || "N/A",
                job: data.job_title || "NV",
                hours: hoursTxt,
            };
        });
    }
}

registry.category("fields").add("monthly_staff_summary", {
    component: MonthlyStaffSummary,
    supportedTypes: ["char", "integer", "html"],
});
