/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const ASSET_STATES = [
    { value: "draft", label: "Nháp" },
    { value: "active", label: "Đang sử dụng" },
    { value: "suspended", label: "Ngừng sử dụng tạm" },
    { value: "retired", label: "Lưu trữ / Thanh lý" },
];

const CLOUD_BILLING = [
    { value: "", label: "— Chưa chọn —" },
    { value: "monthly", label: "Hàng tháng" },
    { value: "yearly", label: "Hàng năm" },
    { value: "other", label: "Khác" },
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

function emptyForm() {
    return {
        code: "",
        name: "",
        asset_type_id: "",
        manufacturer: "",
        model_name: "",
        serial_number: "",
        location: "",
        mien_id: "",
        store_id: "",
        date_start: formatDisplayDate(new Date()),
        provider_id: "",
        responsible_id: "",
        state: "active",
        note: "",
        cpu_info: "",
        ram_gb: "",
        storage_gb: "",
        raid_info: "",
        nic_info: "",
        hypervisor: "",
        warranty_end: "",
        ip_address: "",
        ip_wan: "",
        login_user: "",
        login_password: "",
        hdd_gb: "",
        vm_name: "",
        host_asset_id: "",
        cloud_provider: "",
        cloud_account: "",
        cloud_region: "",
        cloud_service_type: "",
        cloud_billing_cycle: "",
        cloud_budget: "",
        admin_url: "",
        license_end: "",
        firmware_version: "",
        contract_amount: "",
        supplier_name: "",
        contract_filename: "",
        invoice_filename: "",
    };
}

/** 1234567 → "1.234.567" (VNĐ). */
function formatVnd(v) {
    const n = Number(String(v ?? "").replace(/[^\d]/g, ""));
    return n ? n.toLocaleString("vi-VN") : "";
}

export class PhanHeItAssetEntryPopup extends Component {
    static template = "lug_phan_he.PhanHeItAssetEntryPopup";
    static props = {
        resId: { type: [Number, Boolean], optional: true },
        onClose: Function,
        onSaved: { type: Function, optional: true },
        defaultTypeId: { type: [Number, Boolean], optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.assetStates = ASSET_STATES;
        this.cloudBilling = CLOUD_BILLING;
        this.files = {};
        this.state = useState({
            loading: true,
            saving: false,
            types: [],
            miens: [],
            stores: [],
            providers: [],
            employees: [],
            hosts: [],
            form: emptyForm(),
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
        return this.isEdit ? "CHỈNH SỬA TÀI SẢN" : "THÊM TÀI SẢN MỚI";
    }

    get selectedTypeCode() {
        const t = this.state.types.find(
            (x) => String(x.id) === String(this.state.form.asset_type_id)
        );
        return t?.code || "";
    }

    get isPhysical() {
        return this.selectedTypeCode === "physical";
    }

    get isVirtual() {
        return this.selectedTypeCode === "virtual";
    }

    get isCloud() {
        return this.selectedTypeCode === "cloud";
    }

    get isNetwork() {
        return this.selectedTypeCode === "network" || this.selectedTypeCode === "security";
    }

    get techSectionTitle() {
        if (this.isPhysical) {
            return "3. Thông tin máy chủ vật lý";
        }
        if (this.isVirtual) {
            return "3. Thông tin máy chủ ảo";
        }
        if (this.isCloud) {
            return "3. Thông tin dịch vụ Cloud";
        }
        if (this.isNetwork) {
            return "3. Thông tin mạng & bảo mật";
        }
        return "3. Thông tin kỹ thuật (chọn loại tài sản)";
    }

    async loadMeta() {
        const [types, miens, stores, providers, employees, hosts] = await Promise.all([
            this.orm.searchRead(
                "phan.he.it.asset.type",
                [["active", "=", true]],
                ["id", "name", "code"],
                { order: "sequence, name", limit: 50 }
            ),
            this.orm.searchRead(
                "phan.he.mien",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 50 }
            ),
            this.orm.searchRead(
                "phan.he.store",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 500 }
            ),
            this.orm.searchRead(
                "phan.he.provider",
                [["active", "=", true]],
                ["id", "name"],
                { order: "name", limit: 200 }
            ),
            this.orm.searchRead(
                "hr.employee",
                [],
                ["id", "name"],
                { order: "name", limit: 300 }
            ),
            this.orm.searchRead(
                "phan.he.it.asset",
                [["asset_type_code", "=", "physical"], ["active", "=", true]],
                ["id", "name", "code", "manufacturer", "model_name"],
                { order: "code", limit: 200 }
            ),
        ]);
        this.state.types = types || [];
        this.state.miens = miens || [];
        this.state.stores = stores || [];
        this.state.providers = providers || [];
        this.state.employees = employees || [];
        this.state.hosts = hosts || [];
        if (!this.props.resId && !this.state.form.asset_type_id && this.state.types.length) {
            const preset = this.props.defaultTypeId
                && this.state.types.find((t) => t.id === this.props.defaultTypeId);
            const physical = this.state.types.find((t) => t.code === "physical");
            this.state.form.asset_type_id = String((preset || physical || this.state.types[0]).id);
            await this.refreshAutoCode();
        }
    }

    hostOptionLabel(host) {
        const model = String(host?.model_name || "").replace(/^PowerEdge\s+/i, "").trim();
        const manufacturer = String(host?.manufacturer || "").trim();
        if (manufacturer && model) {
            return `${manufacturer} ${model}`;
        }
        if (model) {
            return model;
        }
        return host?.name || host?.code || "";
    }

    onHostChange(ev) {
        const hostId = ev.target.value;
        this.state.form.host_asset_id = hostId;
        const host = (this.state.hosts || []).find((item) => String(item.id) === String(hostId));
        if (!host) {
            return;
        }
        if (!this.state.form.name?.trim()) {
            this.state.form.name = `VM trên ${this.hostOptionLabel(host)}`;
        }
        if (!this.state.form.vm_name?.trim()) {
            this.state.form.vm_name = this.state.form.name;
        }
    }

    async refreshAutoCode() {
        if (this.isEdit || !this.state.form.asset_type_id) {
            return;
        }
        try {
            const code = await this.orm.call(
                "phan.he.it.asset",
                "next_asset_code",
                [Number(this.state.form.asset_type_id)]
            );
            this.state.form.code = code || "";
        } catch (error) {
            console.error(error);
        }
    }

    async onAssetTypeChange(ev) {
        this.state.form.asset_type_id = ev.target.value;
        await this.refreshAutoCode();
    }

    async loadRecord(resId) {
        const rows = await this.orm.searchRead(
            "phan.he.it.asset",
            [["id", "=", resId]],
            [
                "code", "name", "asset_type_id", "manufacturer", "model_name", "serial_number",
                "location", "mien_id", "store_id", "date_start", "provider_id", "responsible_id",
                "state", "note", "cpu_info", "ram_gb", "storage_gb", "raid_info", "nic_info",
                "hypervisor", "warranty_end", "ip_address", "ip_wan", "login_user", "login_password",
                "note", "hdd_gb", "vm_name", "host_asset_id",
                "cloud_provider", "cloud_account", "cloud_region", "cloud_service_type",
                "cloud_billing_cycle", "cloud_budget", "admin_url", "license_end", "firmware_version",
                "contract_amount", "supplier_name", "contract_filename", "invoice_filename",
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
            name: rec.name || "",
            asset_type_id: m2o(rec.asset_type_id),
            manufacturer: rec.manufacturer || "",
            model_name: rec.model_name || "",
            serial_number: rec.serial_number || "",
            location: rec.location || "",
            mien_id: m2o(rec.mien_id),
            store_id: m2o(rec.store_id),
            date_start: isoToDisplay(rec.date_start) || "",
            provider_id: m2o(rec.provider_id),
            responsible_id: m2o(rec.responsible_id),
            state: rec.state || "active",
            note: rec.note || "",
            cpu_info: rec.cpu_info || "",
            ram_gb: num(rec.ram_gb),
            storage_gb: num(rec.storage_gb),
            raid_info: rec.raid_info || "",
            nic_info: rec.nic_info || "",
            hypervisor: rec.hypervisor || "",
            warranty_end: isoToDisplay(rec.warranty_end) || "",
            ip_address: rec.ip_address || "",
            ip_wan: rec.ip_wan || "",
            login_user: rec.login_user || "",
            login_password: rec.login_password || "",
            hdd_gb: num(rec.hdd_gb),
            vm_name: rec.vm_name || "",
            host_asset_id: m2o(rec.host_asset_id),
            cloud_provider: rec.cloud_provider || "",
            cloud_account: rec.cloud_account || "",
            cloud_region: rec.cloud_region || "",
            cloud_service_type: rec.cloud_service_type || "",
            cloud_billing_cycle: rec.cloud_billing_cycle || "",
            cloud_budget: num(rec.cloud_budget),
            admin_url: rec.admin_url || "",
            license_end: isoToDisplay(rec.license_end) || "",
            firmware_version: rec.firmware_version || "",
            contract_amount: formatVnd(rec.contract_amount),
            supplier_name: rec.supplier_name || "",
            contract_filename: rec.contract_filename || "",
            invoice_filename: rec.invoice_filename || "",
        };
        // File đã có: chỉ gửi lại khi chọn file mới / bấm xóa
        this.files = {};
    }

    /** Số tiền: chỉ nhận số, tự chấm hàng nghìn. */
    onAmount(ev) {
        const v = formatVnd(ev.target.value);
        this.state.form.contract_amount = v;
        ev.target.value = v;
    }

    /** Chọn file Hợp đồng / Hóa đơn → base64 (lưu khi bấm Lưu tài sản). */
    onFile(kind, ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        if (file.size > 25 * 1024 * 1024) {
            this.notification.add("File quá lớn (tối đa 25 MB).", { type: "warning" });
            ev.target.value = "";
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const data = String(reader.result || "");
            this.files = this.files || {};
            this.files[kind] = { data: data.slice(data.indexOf(",") + 1), name: file.name };
            this.state.form[`${kind}_filename`] = file.name;
        };
        reader.readAsDataURL(file);
    }

    clearFile(kind) {
        this.files = this.files || {};
        this.files[kind] = { data: false, name: false };
        this.state.form[`${kind}_filename`] = "";
    }

    fileUrl(kind) {
        if (!this.isEdit || (this.files && this.files[kind])) {
            return "";
        }
        return `/web/content/phan.he.it.asset/${this.props.resId}/${kind}_file/${encodeURIComponent(this.state.form[`${kind}_filename`] || kind)}?download=true`;
    }

    /** Ô chọn: đánh dấu option đang có (select t-att-value không tự chọn trong OWL). */
    isSel(a, b) {
        return String(a ?? "") === String(b ?? "");
    }

    onField(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    validate() {
        const f = this.state.form;
        if (!f.code?.trim()) {
            return "Vui lòng nhập mã tài sản.";
        }
        if (!f.name?.trim()) {
            return this.isVirtual ? "Vui lòng nhập tên VM." : "Vui lòng nhập tên tài sản.";
        }
        if (!f.asset_type_id) {
            return "Vui lòng chọn loại tài sản.";
        }
        if (this.isVirtual && !f.host_asset_id) {
            return "Vui lòng chọn Tên máy chủ từ máy chủ vật lý (Dell R530 / Dell R650).";
        }
        if (f.date_start && !parseDisplayDate(f.date_start)) {
            return "Ngày bắt đầu phải dạng dd/mm/yyyy.";
        }
        if (f.warranty_end && !parseDisplayDate(f.warranty_end)) {
            return "Ngày hết hạn bảo hành phải dạng dd/mm/yyyy.";
        }
        if (f.license_end && !parseDisplayDate(f.license_end)) {
            return "Ngày hết hạn license phải dạng dd/mm/yyyy.";
        }
        return null;
    }

    _numOrFalse(v) {
        if (v === "" || v == null) {
            return false;
        }
        const n = Number(v);
        return Number.isNaN(n) ? false : n;
    }

    _m2oOrFalse(v) {
        return v ? Number(v) : false;
    }

    buildVals() {
        const f = this.state.form;
        const vals = {
            code: f.code.trim(),
            name: f.name.trim(),
            asset_type_id: Number(f.asset_type_id),
            manufacturer: f.manufacturer.trim() || false,
            model_name: f.model_name.trim() || false,
            serial_number: f.serial_number.trim() || false,
            location: f.location.trim() || false,
            mien_id: this._m2oOrFalse(f.mien_id),
            store_id: this._m2oOrFalse(f.store_id),
            date_start: parseDisplayDate(f.date_start) || false,
            provider_id: this._m2oOrFalse(f.provider_id),
            responsible_id: this._m2oOrFalse(f.responsible_id),
            state: f.state || "active",
            note: f.note.trim() || false,
            cpu_info: f.cpu_info.trim() || false,
            ram_gb: this._numOrFalse(f.ram_gb),
            storage_gb: this._numOrFalse(f.storage_gb),
            raid_info: f.raid_info.trim() || false,
            nic_info: f.nic_info.trim() || false,
            hypervisor: f.hypervisor.trim() || false,
            warranty_end: parseDisplayDate(f.warranty_end) || false,
            ip_address: f.ip_address.trim() || false,
            ip_wan: f.ip_wan.trim() || false,
            login_user: f.login_user.trim() || false,
            login_password: f.login_password.trim() || false,
            hdd_gb: this._numOrFalse(f.hdd_gb),
            vm_name: f.vm_name.trim() || false,
            host_asset_id: this._m2oOrFalse(f.host_asset_id),
            cloud_provider: f.cloud_provider.trim() || false,
            cloud_account: f.cloud_account.trim() || false,
            cloud_region: f.cloud_region.trim() || false,
            cloud_service_type: f.cloud_service_type.trim() || false,
            cloud_billing_cycle: f.cloud_billing_cycle || false,
            cloud_budget: this._numOrFalse(f.cloud_budget),
            admin_url: f.admin_url.trim() || false,
            license_end: parseDisplayDate(f.license_end) || false,
            firmware_version: f.firmware_version.trim() || false,
            contract_amount: Number(String(f.contract_amount || "").replace(/[^\d]/g, "")) || 0,
            supplier_name: (f.supplier_name || "").trim() || false,
        };
        for (const kind of ["contract", "invoice"]) {
            const file = this.files && this.files[kind];
            if (file) {
                vals[`${kind}_file`] = file.data;
                vals[`${kind}_filename`] = file.name;
            }
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
                await this.orm.write("phan.he.it.asset", [this.props.resId], vals);
                this.notification.add("Đã cập nhật tài sản.", { type: "success" });
            } else {
                await this.orm.create("phan.he.it.asset", [vals]);
                this.notification.add("Đã thêm tài sản mới.", { type: "success" });
            }
            this.props.onSaved?.();
            this.props.onClose();
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không lưu được tài sản.",
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
