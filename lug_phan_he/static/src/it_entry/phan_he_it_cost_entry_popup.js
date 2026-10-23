/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const RENEWAL_STATES = [
    { value: "active", label: "Đang hiệu lực" },
    { value: "expiring", label: "Sắp hết hạn" },
    { value: "quote", label: "Chờ báo giá" },
    { value: "approval", label: "Chờ phê duyệt" },
    { value: "processing", label: "Đang xử lý gia hạn" },
    { value: "renewed", label: "Đã gia hạn" },
    { value: "overdue", label: "Quá hạn" },
    { value: "cancel", label: "Đã hủy" },
];

const PAYMENT_STATES = [
    { value: "not_due", label: "Chưa đến hạn thanh toán" },
    { value: "confirm", label: "Chờ xác nhận" },
    { value: "pending", label: "Chờ thanh toán" },
    { value: "paid", label: "Đã thanh toán" },
    { value: "overdue", label: "Quá hạn thanh toán" },
    { value: "cancel", label: "Đã hủy" },
];

function formatDisplayDate(date) {
    return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}/${date.getFullYear()}`;
}

function isoToDisplay(value) {
    const match = String(value || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) {
        return String(value || "").trim();
    }
    return `${match[3]}/${match[2]}/${match[1]}`;
}

function parseDisplayDate(value) {
    const raw = String(value || "").trim();
    if (!raw) {
        return null;
    }
    let day;
    let month;
    let year;
    let match = raw.match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/);
    if (match) {
        day = Number(match[1]);
        month = Number(match[2]);
        year = Number(match[3]);
    } else {
        match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) {
            return null;
        }
        year = Number(match[1]);
        month = Number(match[2]);
        day = Number(match[3]);
    }
    if (month < 1 || month > 12 || day < 1 || day > 31 || year < 1900 || year > 2100) {
        return null;
    }
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
        return null;
    }
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            resolve(result.includes(",") ? result.split(",")[1] : result);
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

function emptyForm() {
    const today = new Date();
    return {
        code: "",
        asset_id: "",
        category_id: "",
        provider_id: "",
        contract_ref: "",
        bandwidth: "",
        cycle_id: "",
        date_start: formatDisplayDate(today),
        date_end: "",
        date_due: "",
        date_paid: "",
        responsible_id: "",
        renewal_state: "active",
        payment_state: "not_due",
        currency_id: "",
        amount_untaxed: "",
        amount_total: "",
        tax_rate: "0",
        amount_untaxed_actual: "",
        note: "",
        attachment: null,
        attachment_name: "",
    };
}

export class PhanHeItCostEntryPopup extends Component {
    static template = "lug_phan_he.PhanHeItCostEntryPopup";
    static props = {
        resId: { type: [Number, Boolean], optional: true },
        defaultAssetId: { type: [Number, Boolean], optional: true },
        onClose: Function,
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.renewalStates = RENEWAL_STATES;
        this.paymentStates = PAYMENT_STATES;
        this.state = useState({
            loading: true,
            saving: false,
            assets: [],
            categories: [],
            providers: [],
            cycles: [],
            employees: [],
            currencies: [],
            form: emptyForm(),
            responsibleQuery: "",
            responsibleOpen: false,
        });
        onWillStart(async () => {
            await this.loadMeta();
            if (this.props.resId) {
                await this.loadRecord(this.props.resId);
            } else if (this.props.defaultAssetId) {
                this.state.form.asset_id = String(this.props.defaultAssetId);
            }
            this.state.loading = false;
        });
    }

    get isEdit() {
        return Boolean(this.props.resId);
    }

    get title() {
        return this.isEdit ? "CHỈNH SỬA KHOẢN CHI PHÍ" : "THÊM KHOẢN CHI PHÍ MỚI";
    }

    get responsibleLabel() {
        const id = this.state.form.responsible_id;
        if (!id) {
            return "";
        }
        const emp = this.state.employees.find((e) => String(e.id) === String(id));
        return emp?.name || "";
    }

    get filteredEmployees() {
        const q = String(this.state.responsibleQuery || "").trim().toLowerCase();
        const list = this.state.employees || [];
        if (!q) {
            return list.slice(0, 40);
        }
        return list
            .filter((e) => String(e.name || "").toLowerCase().includes(q))
            .slice(0, 40);
    }

    formatMoney(v) {
        const n = Number(v || 0);
        return `${Math.round(n).toLocaleString("vi-VN")} VND`;
    }

    async loadMeta() {
        const [assets, categories, providers, cycles, employees, currencies] = await Promise.all([
            this.orm.searchRead(
                "phan.he.it.asset",
                [["active", "=", true]],
                ["id", "name", "code"],
                { order: "code", limit: 500 }
            ),
            this.orm.searchRead(
                "phan.he.it.cost.category",
                [["active", "=", true]],
                ["id", "name"],
                { order: "sequence, name", limit: 200 }
            ),
            this.orm.searchRead(
                "phan.he.provider",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 200 }
            ),
            this.orm.searchRead(
                "phan.he.it.renewal.cycle",
                [["active", "=", true]],
                ["id", "name", "months"],
                { order: "months", limit: 50 }
            ),
            this.orm.searchRead(
                "hr.employee",
                [],
                ["id", "name"],
                { order: "name", limit: 300 }
            ),
            this.orm.searchRead(
                "res.currency",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 50 }
            ),
        ]);
        this.state.assets = assets || [];
        this.state.categories = categories || [];
        this.state.providers = providers || [];
        this.state.cycles = cycles || [];
        this.state.employees = employees || [];
        this.state.currencies = currencies || [];
        if (!this.props.resId && !this.state.form.currency_id) {
            const vnd = (currencies || []).find((c) => c.name === "VND");
            this.state.form.currency_id = String((vnd || currencies?.[0] || {}).id || "");
        }
        if (!this.props.resId) {
            this.state.form.code = "Tự sinh khi lưu";
        }
    }

    async loadRecord(resId) {
        const rows = await this.orm.searchRead(
            "phan.he.it.cost",
            [["id", "=", resId]],
            [
                "code", "asset_id", "category_id", "provider_id", "contract_ref", "bandwidth", "cycle_id",
                "date_start", "date_end", "date_due", "date_paid", "responsible_id",
                "renewal_state", "payment_state", "currency_id", "amount_untaxed", "amount_total",
                "note", "attachment_name",
            ],
            { limit: 1 }
        );
        const rec = rows?.[0];
        if (!rec) {
            return;
        }
        const m2o = (v) => (v?.[0] ? String(v[0]) : "");
        const num = (v) => (v != null && v !== false ? String(v) : "");
        this.state.form = {
            ...emptyForm(),
            code: rec.code || "",
            asset_id: m2o(rec.asset_id),
            category_id: m2o(rec.category_id),
            provider_id: m2o(rec.provider_id),
            contract_ref: rec.contract_ref || "",
            bandwidth: rec.bandwidth || "",
            cycle_id: m2o(rec.cycle_id),
            date_start: isoToDisplay(rec.date_start) || "",
            date_end: isoToDisplay(rec.date_end) || "",
            date_due: isoToDisplay(rec.date_due) || "",
            date_paid: isoToDisplay(rec.date_paid) || "",
            responsible_id: m2o(rec.responsible_id),
            renewal_state: rec.renewal_state || "active",
            payment_state: rec.payment_state || "not_due",
            currency_id: m2o(rec.currency_id),
            amount_untaxed: num(rec.amount_untaxed),
            amount_total: num(rec.amount_total),
            note: rec.note || "",
            attachment: null,
            attachment_name: rec.attachment_name || "",
        };
        const emp = this.state.employees.find(
            (e) => String(e.id) === String(this.state.form.responsible_id)
        );
        this.state.responsibleQuery = emp?.name || "";
    }

    onField(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    onResponsibleInput(ev) {
        this.state.responsibleQuery = ev.target.value;
        this.state.responsibleOpen = true;
        // Đang gõ tìm kiếm → chưa chọn id.
        if (!this.responsibleLabel
            || String(this.state.responsibleQuery).trim() !== String(this.responsibleLabel).trim()) {
            this.state.form.responsible_id = "";
        }
    }

    onResponsibleFocus() {
        this.state.responsibleOpen = true;
        if (!this.state.responsibleQuery && this.responsibleLabel) {
            this.state.responsibleQuery = this.responsibleLabel;
        }
    }

    onResponsibleBlur() {
        // Delay để click chọn option kịp chạy trước khi đóng.
        setTimeout(() => {
            this.state.responsibleOpen = false;
            if (this.state.form.responsible_id) {
                this.state.responsibleQuery = this.responsibleLabel;
            } else if (!String(this.state.responsibleQuery || "").trim()) {
                this.state.form.responsible_id = "";
            }
        }, 180);
    }

    selectResponsible(emp) {
        if (!emp) {
            this.state.form.responsible_id = "";
            this.state.responsibleQuery = "";
        } else {
            this.state.form.responsible_id = String(emp.id);
            this.state.responsibleQuery = emp.name || "";
        }
        this.state.responsibleOpen = false;
    }

    clearResponsible() {
        this.selectResponsible(null);
    }

    async onFileChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        try {
            this.state.form.attachment = await fileToBase64(file);
            this.state.form.attachment_name = file.name;
        } catch {
            this.notification.add("Không đọc được tệp chứng từ.", { type: "danger" });
        }
    }

    clearFile() {
        this.state.form.attachment = null;
        this.state.form.attachment_name = "";
    }

    validate() {
        const f = this.state.form;
        if (!f.asset_id) {
            return "Vui lòng chọn tài sản.";
        }
        if (!f.category_id) {
            return "Vui lòng chọn hạng mục chi phí.";
        }
        for (const [key, label] of [
            ["date_start", "Ngày bắt đầu"],
            ["date_end", "Ngày hết hạn"],
        ]) {
            if (f[key] && !parseDisplayDate(f[key])) {
                return `${label} phải dạng dd/mm/yyyy.`;
            }
        }
        if (f.date_start && f.date_end) {
            const s = parseDisplayDate(f.date_start);
            const e = parseDisplayDate(f.date_end);
            if (s && e && e < s) {
                return "Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.";
            }
        }
        if (f.amount_untaxed !== "" && Number.isNaN(Number(f.amount_untaxed))) {
            return "Cước tháng phải là số.";
        }
        if (f.amount_total !== "" && Number.isNaN(Number(f.amount_total))) {
            return "Số tiền thanh toán phải là số.";
        }
        return null;
    }

    onAmountUntaxedInput(ev) {
        this.state.form.amount_untaxed = ev.target.value;
        // Nếu chưa nhập số tiền TT → gợi ý bằng cước tháng (vẫn sửa được).
        if (!String(this.state.form.amount_total || "").trim() && ev.target.value !== "") {
            this.state.form.amount_total = ev.target.value;
        }
    }

    buildVals() {
        const f = this.state.form;
        const vals = {
            asset_id: Number(f.asset_id),
            category_id: Number(f.category_id),
            provider_id: f.provider_id ? Number(f.provider_id) : false,
            contract_ref: (f.contract_ref || "").trim() || false,
            bandwidth: (f.bandwidth || "").trim() || false,
            cycle_id: f.cycle_id ? Number(f.cycle_id) : false,
            date_start: parseDisplayDate(f.date_start) || false,
            date_end: parseDisplayDate(f.date_end) || false,
            renewal_state: f.renewal_state || "active",
            payment_state: f.payment_state || "not_due",
            currency_id: f.currency_id ? Number(f.currency_id) : false,
            amount_untaxed: f.amount_untaxed === "" ? 0 : Number(f.amount_untaxed || 0),
            amount_total: f.amount_total === "" ? 0 : Number(f.amount_total || 0),
            tax_rate: 0,
            note: (f.note || "").trim() || false,
        };
        if (f.attachment) {
            vals.attachment = f.attachment;
            vals.attachment_name = f.attachment_name || "hoa_don.bin";
        }
        if (this.isEdit && f.code && f.code !== "Tự sinh khi lưu") {
            vals.code = f.code;
        }
        return vals;
    }

    async onSave() {
        const err = this.validate();
        if (err) {
            this.notification.add(err, { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const vals = this.buildVals();
            if (this.isEdit) {
                await this.orm.write("phan.he.it.cost", [this.props.resId], vals);
                this.notification.add("Đã cập nhật khoản chi phí.", { type: "success" });
            } else {
                await this.orm.create("phan.he.it.cost", [vals]);
                this.notification.add("Đã thêm khoản chi phí.", { type: "success" });
            }
            this.props.onSaved?.();
            this.props.onClose();
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không lưu được khoản chi phí.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    onCancel() {
        if (this.state.saving) {
            return;
        }
        this.props.onClose();
    }

    onOverlayClick() {
        this.onCancel();
    }
}
