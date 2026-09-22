/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const PAYMENT_TYPES = [
    { value: "monthly", label: "Trả sau hàng tháng" },
    { value: "prepaid_6", label: "Trả trước / 6 tháng" },
    { value: "prepaid_12", label: "Trả trước / 12 tháng" },
];

const OPS_STATUS = [
    { value: "active", label: "Đang hoạt động" },
    { value: "suspend", label: "Tạm ngưng" },
    { value: "liquidated", label: "Thanh lý" },
];

function emptyForm() {
    const today = new Date();
    const ymd = (d) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const end = new Date(today);
    end.setFullYear(end.getFullYear() + 1);
    return {
        store_id: "",
        provider_id: "",
        code: "",
        customer_code: "",
        bandwidth: "",
        contract_amount: "",
        payment_type: "prepaid_12",
        date_start: ymd(today),
        date_end: ymd(end),
        ops_status: "active",
        usage_address: "",
        bank_account_holder: "",
        bank_account_number: "",
        bank_display: "",
        note: "",
        invoice_file: null,
        invoice_filename: "",
    };
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

export class PhanHeInternetEntryPopup extends Component {
    static template = "lug_phan_he.PhanHeInternetEntryPopup";
    static props = {
        resId: { type: [Number, Boolean], optional: true },
        onClose: Function,
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.paymentTypes = PAYMENT_TYPES;
        this.opsStatuses = OPS_STATUS;
        this.state = useState({
            loading: true,
            saving: false,
            stores: [],
            providers: [],
            serviceTypeId: false,
            form: emptyForm(),
            mienLabel: "",
        });
        onWillStart(async () => {
            await this.loadMeta();
            if (this.props.resId) {
                await this.loadRecord(this.props.resId);
            }
            this.state.loading = false;
        });
    }

    get isEdit() {
        return Boolean(this.props.resId);
    }

    get title() {
        return this.isEdit ? "CHỈNH SỬA HỢP ĐỒNG" : "THÊM HỢP ĐỒNG MỚI";
    }

    async loadMeta() {
        const [stores, providers, types] = await Promise.all([
            this.orm.searchRead(
                "phan.he.store",
                [["active", "=", true]],
                ["id", "name", "code", "mien", "mien_id", "address"],
                { order: "name", limit: 500 }
            ),
            this.orm.searchRead(
                "phan.he.provider",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 200 }
            ),
            this.orm.searchRead(
                "phan.he.service.type",
                [["code", "=", "internet"]],
                ["id"],
                { limit: 1 }
            ),
        ]);
        this.state.stores = stores || [];
        this.state.providers = providers || [];
        this.state.serviceTypeId = types?.[0]?.id || false;
    }

    async loadRecord(resId) {
        const rows = await this.orm.searchRead(
            "phan.he.service",
            [["id", "=", resId]],
            [
                "store_id",
                "provider_id",
                "customer_code",
                "bandwidth",
                "contract_amount",
                "payment_type",
                "date_start",
                "date_end",
                "ops_status",
                "usage_address",
                "bank_account_holder",
                "bank_account_number",
                "bank_display",
                "note",
                "code",
                "invoice_filename",
            ],
            { limit: 1 }
        );
        const rec = rows?.[0];
        if (!rec) {
            return;
        }
        this.state.form = {
            store_id: rec.store_id?.[0] ? String(rec.store_id[0]) : "",
            provider_id: rec.provider_id?.[0] ? String(rec.provider_id[0]) : "",
            code: rec.code || "",
            customer_code: rec.customer_code || "",
            bandwidth: rec.bandwidth || "",
            contract_amount: rec.contract_amount != null ? String(rec.contract_amount) : "",
            payment_type: rec.payment_type || "prepaid_12",
            date_start: rec.date_start ? String(rec.date_start).slice(0, 10) : "",
            date_end: rec.date_end ? String(rec.date_end).slice(0, 10) : "",
            ops_status: rec.ops_status || "active",
            usage_address: rec.usage_address || "",
            bank_account_holder: rec.bank_account_holder || "",
            bank_account_number: rec.bank_account_number || "",
            bank_display: rec.bank_display || "",
            note: rec.note || "",
            invoice_file: null,
            invoice_filename: rec.invoice_filename || "",
        };
        this.syncMienFromStore();
    }

    syncMienFromStore() {
        const store = this.state.stores.find((s) => String(s.id) === String(this.state.form.store_id));
        this.state.mienLabel = store?.mien || store?.mien_id?.[1] || "";
        if (store?.address && !this.state.form.usage_address) {
            this.state.form.usage_address = store.address;
        }
    }

    onStoreChange(ev) {
        this.state.form.store_id = ev.target.value;
        this.syncMienFromStore();
        const store = this.state.stores.find((s) => String(s.id) === String(this.state.form.store_id));
        if (store?.address) {
            this.state.form.usage_address = store.address;
        }
    }

    onField(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    async onInvoiceChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        try {
            const data = await fileToBase64(file);
            this.state.form.invoice_file = data;
            this.state.form.invoice_filename = file.name;
        } catch {
            this.notification.add("Không đọc được file hóa đơn.", { type: "danger" });
        }
    }

    clearInvoice() {
        this.state.form.invoice_file = null;
        this.state.form.invoice_filename = "";
    }

    validate() {
        const f = this.state.form;
        if (!f.store_id) {
            return "Vui lòng chọn cửa hàng.";
        }
        if (!f.provider_id) {
            return "Vui lòng chọn nhà cung cấp.";
        }
        if (!f.date_start || !f.date_end) {
            return "Vui lòng nhập ngày bắt đầu và kết thúc.";
        }
        if (!f.usage_address?.trim()) {
            return "Vui lòng nhập địa chỉ lắp đặt.";
        }
        if (f.contract_amount === "" || Number.isNaN(Number(f.contract_amount))) {
            return "Vui lòng nhập cước tháng.";
        }
        if (!f.bank_account_holder?.trim() || !f.bank_account_number?.trim() || !f.bank_display?.trim()) {
            return "Vui lòng nhập đủ thông tin thanh toán (tài khoản / ngân hàng).";
        }
        if (!this.state.serviceTypeId && !this.isEdit) {
            return "Chưa cấu hình loại dịch vụ Internet.";
        }
        return null;
    }

    buildVals() {
        const f = this.state.form;
        const ops = f.ops_status || "active";
        const closing = ops === "liquidated" || ops === "cancel";
        const vals = {
            store_id: Number(f.store_id),
            provider_id: Number(f.provider_id),
            code: (f.code || "").trim() || false,
            customer_code: f.customer_code || false,
            bandwidth: f.bandwidth || false,
            contract_amount: Number(f.contract_amount || 0),
            payment_type: f.payment_type || "prepaid_12",
            date_start: f.date_start || false,
            date_end: f.date_end || false,
            ops_status: ops,
            state: ops,
            usage_address: f.usage_address || false,
            bank_account_holder: f.bank_account_holder || false,
            bank_account_number: f.bank_account_number || false,
            bank_display: f.bank_display || false,
            note: f.note || false,
        };
        // Sửa → Thanh lý: bỏ field trống khỏi vals để không xóa NCC / ngày bắt đầu / kết thúc.
        if (closing && this.isEdit) {
            for (const key of [
                "provider_id",
                "date_start",
                "date_end",
                "bandwidth",
                "customer_code",
                "usage_address",
                "package_name",
                "code",
            ]) {
                if (!vals[key]) {
                    delete vals[key];
                }
            }
            if (!Number(f.contract_amount || 0)) {
                delete vals.contract_amount;
            }
        }
        if (!this.isEdit && this.state.serviceTypeId) {
            vals.service_type_id = this.state.serviceTypeId;
        }
        if (f.invoice_file) {
            vals.invoice_file = f.invoice_file;
            vals.invoice_filename = f.invoice_filename || "hoa_don";
        }
        return vals;
    }

    async onSave() {
        if (this.state.saving) {
            return;
        }
        const err = this.validate();
        if (err) {
            this.notification.add(err, { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const vals = this.buildVals();
            let resId = this.props.resId || false;
            if (this.isEdit) {
                await this.orm.write("phan.he.service", [resId], vals);
            } else {
                resId = await this.orm.create("phan.he.service", [vals]);
                if (Array.isArray(resId)) {
                    resId = resId[0];
                }
            }
            this.notification.add(this.isEdit ? "Đã cập nhật hợp đồng." : "Đã lưu hợp đồng mới.", {
                type: "success",
            });
            this.props.onSaved?.(resId);
            this.props.onClose();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Không lưu được hợp đồng.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    onCancel() {
        this.props.onClose();
    }

    onOverlayClick() {
        if (!this.state.saving) {
            this.props.onClose();
        }
    }
}
