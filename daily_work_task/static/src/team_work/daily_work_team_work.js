/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

const pad = (n) => String(n).padStart(2, "0");
const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fmtDate = (iso) => {
    if (!iso) {
        return "";
    }
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
};
let seq = 0;

/** Quản lý công việc → Phân công việc team (theo mẫu). */
export class DailyWorkTeamWork extends Component {
    static template = "daily_work_task.DailyWorkTeamWork";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const now = new Date();
        this.state = useState({
            loading: true,
            saving: false,
            exporting: false,
            message: false,
            departments: [],
            teams: [],
            teamId: 0,
            teamName: "",
            departmentId: 0,
            members: [],
            categories: [],
            canCreate: false,
            canWrite: false,
            edit: null, // công việc đang sửa (bấm Lưu mới ghi)
            editSaving: false,
            coordinatorId: 0,
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            catId: 0,
            detailPicked: {},
            taskName: "",
            taskNames: {},
            query: "",
            picked: {},
            rows: [],
            listRows: [],
            listLoading: false,
            form: { date_start: "", deadline: "", checker_id: 0, note: "" },
        });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "team_work";
    }

    async load(teamId = null) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("daily.task", "get_team_work_data", [], {
                team_id: teamId || this.state.teamId || false,
            });
            this.state.departments = data.departments || [];
            this.state.teams = data.teams || [];
            this.state.teamId = data.team_id || 0;
            this.state.teamName = data.team_name || "";
            this.state.departmentId = data.department_id || 0;
            this.state.members = data.members || [];
            this.state.categories = data.categories || [];
            this.state.canCreate = Boolean(data.can_create);
            this.state.canWrite = Boolean(data.can_write);
            if (!this.state.members.some((m) => m.user_id === this.state.coordinatorId)) {
                this.state.coordinatorId = (this.state.members.find((m) => m.user_id === data.me) || this.state.members[0] || {}).user_id || 0;
            }
            this.state.catId = (this.state.categories[0] || {}).id || 0;
            this.state.detailPicked = {};
            this.state.taskNames = data.task_names || {};
            this.state.picked = {};
            this.state.message = false;
            this._resetForm();
            await this.loadList();
        } catch (e) {
            this.state.message = e?.data?.message || _t("Không tải được dữ liệu.");
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------ bộ lọc
    get teamsOfDept() {
        return this.state.teams.filter((t) => !this.state.departmentId || t.department_id === this.state.departmentId);
    }

    get monthOptions() {
        const out = [];
        const now = new Date();
        for (let y = now.getFullYear() - 1; y <= now.getFullYear() + 1; y++) {
            for (let m = 1; m <= 12; m++) {
                out.push({ key: `${y}-${m}`, label: `${pad(m)}/${y}` });
            }
        }
        return out;
    }

    get monthKey() {
        return `${this.state.year}-${this.state.month}`;
    }

    get monthLabel() {
        return `${pad(this.state.month)}/${this.state.year}`;
    }

    _confirmDiscard() {
        return !this.state.rows.length || window.confirm(_t("Danh sách công việc chưa lưu sẽ bị xoá. Tiếp tục?"));
    }

    async onDept(ev) {
        const id = Number(ev.target.value) || 0;
        const team = this.state.teams.find((t) => t.department_id === id);
        if (!this._confirmDiscard()) {
            ev.target.value = String(this.state.departmentId);
            return;
        }
        this.state.rows = [];
        await this.load(team ? team.id : null);
    }

    async onTeam(ev) {
        if (!this._confirmDiscard()) {
            ev.target.value = String(this.state.teamId);
            return;
        }
        this.state.rows = [];
        await this.load(Number(ev.target.value) || null);
    }

    async onMonth(ev) {
        const [y, m] = ev.target.value.split("-").map(Number);
        this.state.year = y;
        this.state.month = m;
        this._resetForm();
        await this.loadList();
    }

    /** Ngày thực hiện / Deadline / Người kiểm tra mặc định theo tháng kế hoạch + người điều phối. */
    _resetForm() {
        const day = this._defaultDay();
        this.state.form = {
            date_start: day,
            deadline: day,
            checker_id: this.state.coordinatorId || 0,
            note: "",
        };
    }

    onForm(field, ev) {
        let v = ev.target.value;
        if (field === "checker_id") {
            v = Number(v) || 0;
        }
        this.state.form[field] = v;
    }

    /** Danh sách công việc đã phân của Team trong tháng (chỉ xem). */
    async loadList() {
        if (!this.state.teamId) {
            this.state.listRows = [];
            return;
        }
        this.state.listLoading = true;
        try {
            const res = await this.orm.call("daily.task", "get_team_work_list", [this.state.teamId], {
                year: this.state.year,
                month: this.state.month,
            });
            this.state.listRows = res.rows || [];
        } finally {
            this.state.listLoading = false;
        }
    }

    stateClass(state) {
        return `o_dtw_state is-${state || "not_started"}`;
    }

    onCoordinator(ev) {
        this.state.coordinatorId = Number(ev.target.value) || 0;
    }

    // ------------------------------------------------------------ hạng mục
    get currentCat() {
        return this.state.categories.find((c) => c.id === this.state.catId);
    }

    get nextStt() {
        return this.state.listRows.length + 1;
    }

    onCat(ev) {
        this.state.catId = Number(ev.target.value) || 0;
        this.state.detailPicked = {};
    }

    catLabel(catId) {
        return (this.state.categories.find((c) => c.id === catId) || {}).label || "";
    }

    /** Hạng mục của 1 dòng (từ chi tiết hoặc chính hạng mục). */
    catOfWg(wgId) {
        return this.state.categories.find((c) => c.id === wgId || c.details.some((d) => d.id === wgId));
    }

    detailName(wgId) {
        for (const c of this.state.categories) {
            const d = c.details.find((x) => x.id === wgId);
            if (d) {
                return d.name;
            }
        }
        return "";
    }

    // ------------------------------------------------------------ nhân sự
    get filteredMembers() {
        const q = (this.state.query || "").trim().toLowerCase();
        return this.state.members.filter((m) => !q || m.name.toLowerCase().includes(q));
    }

    get pickedMembers() {
        return this.state.members.filter((m) => this.state.picked[m.user_id]);
    }

    togglePick(m) {
        this.state.picked = { ...this.state.picked, [m.user_id]: !this.state.picked[m.user_id] };
    }

    unpick(m) {
        this.state.picked = { ...this.state.picked, [m.user_id]: false };
    }

    memberName(uid) {
        return (this.state.members.find((m) => m.user_id === uid) || {}).name || "";
    }

    // ------------------------------------------------------------ danh sách công việc
    _defaultDay() {
        const now = new Date();
        const inMonth = now.getFullYear() === this.state.year && now.getMonth() + 1 === this.state.month;
        return inMonth ? isoOf(now) : `${this.state.year}-${pad(this.state.month)}-01`;
    }

    // ------------------------------------------------------------ chi tiết hạng mục (tick nhiều)
    get catDetails() {
        return (this.currentCat && this.currentCat.details) || [];
    }

    get pickedDetails() {
        return this.catDetails.filter((d) => this.state.detailPicked[d.id]);
    }

    get allDetailsPicked() {
        return this.catDetails.length > 0 && this.catDetails.every((d) => this.state.detailPicked[d.id]);
    }

    toggleDetail(d) {
        this.state.detailPicked = { ...this.state.detailPicked, [d.id]: !this.state.detailPicked[d.id] };
    }

    toggleAllDetails() {
        const on = !this.allDetailsPicked;
        const picked = {};
        for (const d of this.catDetails) {
            picked[d.id] = on;
        }
        this.state.detailPicked = picked;
    }

    /** Gợi ý «Tên công việc» (Quản lý công việc cá nhân) theo chi tiết đang tick / cả hạng mục. */
    get nameSuggestions() {
        const map = this.state.taskNames || {};
        const ids = (this.pickedDetails.length ? this.pickedDetails : this.catDetails).map((d) => d.id);
        if (this.state.catId) {
            ids.push(this.state.catId);
        }
        const out = [];
        for (const id of ids) {
            for (const n of map[String(id)] || []) {
                if (!out.includes(n)) {
                    out.push(n);
                }
            }
        }
        return out.slice(0, 50);
    }

    /** Thêm công việc: mỗi nhân sự × mỗi chi tiết hạng mục đã tick → 1 dòng. */
    onAddRows() {
        return this._addRows();
    }

    _addRows() {
        const people = this.pickedMembers;
        if (!people.length) {
            this.notification.add(_t("Chọn ít nhất 1 nhân sự ở «Người phụ trách»."), { type: "warning" });
            return false;
        }
        if (!this.state.catId) {
            this.notification.add(_t("Chọn Hạng mục trước."), { type: "warning" });
            return false;
        }
        let details = this.pickedDetails;
        if (!details.length) {
            // Không tick chi tiết → gắn thẳng vào hạng mục (Nội dung = Tên công việc / tên hạng mục)
            details = [{ id: this.state.catId, name: (this.currentCat || {}).name || "", noDetail: true }];
        }
        const taskName = (this.state.taskName || "").trim();
        const form = this.state.form;
        for (const m of people) {
            for (const d of details) {
                this.state.rows.push({
                    key: `r-${Date.now()}-${seq++}`,
                    user_id: m.user_id,
                    cat_id: this.state.catId || 0,
                    work_group_id: d.id,
                    no_detail: Boolean(d.noDetail),
                    name: taskName || d.name,
                    date_start: form.date_start,
                    deadline: form.deadline,
                    checker_id: form.checker_id || 0,
                    note: form.note || "",
                });
            }
        }
        return true;
    }

    onRow(row, field, ev) {
        let v = ev.target.value;
        if (["user_id", "checker_id"].includes(field)) {
            v = Number(v) || 0;
        }
        if (field === "cat_id") {
            v = Number(v) || 0;
            const cat = this.state.categories.find((c) => c.id === v);
            row.work_group_id = (cat && (cat.details[0] || {}).id) || v || false;
        }
        row[field] = v;
    }

    fmt(iso) {
        return fmtDate(iso);
    }

    /** Ngày gõ tay dd/mm/yyyy. */
    onRowDate(row, field, ev) {
        const raw = (ev.target.value || "").trim();
        const m = raw.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/);
        const d = m && Number(m[1]);
        const mo = m && Number(m[2]);
        const y = m && Number(m[3]);
        if (!m || mo < 1 || mo > 12 || d < 1 || d > new Date(y, mo, 0).getDate()) {
            this.notification.add(_t("Ngày không hợp lệ — nhập dạng dd/mm/yyyy."), { type: "warning" });
            ev.target.value = fmtDate(row[field]);
            return;
        }
        row[field] = `${y}-${pad(mo)}-${pad(d)}`;
        ev.target.value = fmtDate(row[field]);
    }

    openPicker(ev) {
        const picker = ev.currentTarget.parentElement.querySelector(".o_dtw_date_picker");
        if (picker?.showPicker) {
            picker.showPicker();
        } else {
            picker?.click();
        }
    }

    onPicker(row, field, ev) {
        row[field] = ev.target.value;
    }

    _payloadRows(rows) {
        return rows.map((r) => ({
            user_id: r.user_id,
            work_group_id: r.work_group_id || false,
            name: r.name,
            date_start: r.date_start || false,
            deadline: r.deadline || false,
            checker_id: r.checker_id || false,
            note: r.note,
        }));
    }

    /** Xuất Excel danh sách công việc phân công (chưa có dòng → lấy theo lựa chọn hiện tại). */
    async onExport() {
        if (!this.state.listRows.length) {
            this.notification.add(_t("Chưa có công việc đã phân trong tháng này để xuất."), { type: "warning" });
            return;
        }
        this.state.exporting = true;
        try {
            const res = await this.orm.call("daily.task", "export_team_work_excel", [
                this.state.teamId,
                this.state.coordinatorId || false,
                this.state.year,
                this.state.month,
            ]);
            const bin = atob(res.file_base64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) {
                bytes[i] = bin.charCodeAt(i);
            }
            const url = URL.createObjectURL(new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }));
            const a = document.createElement("a");
            a.href = url;
            a.download = res.filename || "phan_cong_viec_team.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }

    removeRow(row) {
        this.state.rows = this.state.rows.filter((r) => r.key !== row.key);
    }

    onCancel() {
        if (this.state.rows.length && !window.confirm(_t("Xoá toàn bộ danh sách công việc chưa lưu?"))) {
            return;
        }
        this.state.rows = [];
    }

    /** Bấm 1 dòng trong Danh sách công việc phân công → hộp Sửa (chưa ghi cho tới khi bấm Lưu). */
    openEdit(r) {
        if (!this.state.canWrite) {
            this.notification.add(_t("Bạn không có quyền Phân công việc team (Chỉnh sửa)."), { type: "warning" });
            return;
        }
        this.state.edit = {
            id: r.id,
            user_id: r.user_id || 0,
            name: r.name || "",
            date_start: r.date_start || "",
            deadline: r.deadline || "",
            checker_id: r.checker_id || 0,
            note: r.note || "",
            category: r.category || "",
            detail: r.detail || "",
            state_label: r.state_label || "",
        };
    }

    onEdit(field, ev) {
        let v = ev.target.value;
        if (field === "user_id" || field === "checker_id") {
            v = Number(v) || 0;
        }
        this.state.edit[field] = v;
    }

    closeEdit() {
        if (!this.state.editSaving) {
            this.state.edit = null;
        }
    }

    async saveEdit() {
        const e = this.state.edit;
        if (!e || this.state.editSaving) {
            return;
        }
        if (!(e.name || "").trim()) {
            this.notification.add(_t("Vui lòng nhập Nội dung công việc."), { type: "warning" });
            return;
        }
        this.state.editSaving = true;
        try {
            await this.orm.call("daily.task", "update_team_work_task", [e.id, {
                user_id: e.user_id || false,
                name: e.name,
                date_start: e.date_start || false,
                deadline: e.deadline || false,
                checker_id: e.checker_id || false,
                note: e.note || "",
            }]);
            this.state.edit = null;
            await this.loadList();
            this.notification.add(_t("Đã lưu công việc."), { type: "success" });
        } catch (err) {
            this.notification.add(err?.data?.message || _t("Không lưu được công việc."), { type: "danger" });
        } finally {
            this.state.editSaving = false;
        }
    }

    async onSave() {
        if (!this.state.canCreate) {
            this.notification.add(_t("Bạn không có quyền Phân công việc team (Thêm)."), { type: "warning" });
            return;
        }
        // Lưu: mỗi nhân sự × mỗi chi tiết hạng mục đã tick → 1 công việc cá nhân
        this.state.rows = [];
        if (!this._addRows()) {
            return;
        }
        this.state.saving = true;
        try {
            const res = await this.orm.call("daily.task", "create_team_work_tasks", [
                this.state.teamId,
                this.state.coordinatorId || false,
                this.state.rows.map((r) => ({
                    user_id: r.user_id,
                    work_group_id: r.work_group_id || false,
                    name: r.name,
                    date_start: r.date_start || false,
                    deadline: r.deadline || false,
                    checker_id: r.checker_id || false,
                    note: r.note,
                    no_detail: Boolean(r.no_detail),
                })),
            ]);
            this.state.rows = [];
            this.state.picked = {};
            this.state.detailPicked = {};
            this.state.taskName = "";
            await this.loadList();
            this.notification.add(`Đã phân ${res.count} công việc — đã xuống danh sách công việc cá nhân của từng nhân sự.`, {
                type: "success",
            });
        } catch (e) {
            this.state.rows = [];
            this.notification.add(e?.data?.message || _t("Không lưu được."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("daily_work_team_work", DailyWorkTeamWork);
