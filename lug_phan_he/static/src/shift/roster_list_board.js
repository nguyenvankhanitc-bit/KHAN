/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";

const REGION_LABEL = {
    north: "Miền Bắc",
    south: "Miền Nam",
    dtt: "Miền ĐTT",
};

function defaultFilters() {
    const now = new Date();
    return {
        month: String(now.getMonth() + 1),
        year: String(now.getFullYear()),
        storeId: "all",
        regionId: "all",
        status: "all",
        lockStatus: "all",
    };
}

class RosterHardDeleteDialog extends Component {
    static template = "lug_phan_he.RosterHardDeleteDialog";
    static components = { Dialog };
    static props = {
        count: { type: Number },
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.state = useState({ code: "", busy: false });
    }

    get canConfirm() {
        const code = (this.state.code || "").trim().toUpperCase();
        return code === "DELETE" || code === "XOA";
    }

    async onConfirm() {
        if (!this.canConfirm || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.props.onConfirm(this.state.code);
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }
}

export class RosterListBoard extends Component {
    static template = "lug_phan_he.RosterListBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.months = Array.from({ length: 12 }, (_, i) => ({
            value: String(i + 1),
            label: `Tháng ${i + 1}`,
        }));
        const y = new Date().getFullYear();
        this.years = [y - 1, y, y + 1];

        this.state = useState({
            filters: defaultFilters(),
            storeOptions: [],
            rosterList: [],
            totalCount: 0,
            currentPage: 1,
            pageSize: 10,
            totalPages: 1,
            canManage: false,
            isAdmin: false,
        });

        onWillStart(async () => {
            this.state.isAdmin = await user.hasGroup("base.group_system");
            this.state.canManage =
                this.state.isAdmin ||
                (await user.hasGroup("lug_phan_he.group_linkq_manager")) ||
                (await user.hasGroup("lug_phan_he.group_phan_he_admin")) ||
                (await user.hasGroup("lug_phan_he.group_phan_he_service_manager"));
            await this.loadStores();
            await this.fetchRosters();
        });
    }

    async loadStores() {
        try {
            this.state.storeOptions = await this.orm.searchRead("hr.store", [], ["id", "name"], {
                limit: 500,
                order: "name",
            });
        } catch {
            this.state.storeOptions = [];
        }
    }

    buildDomain() {
        const domain = [];
        const { month, year, storeId, regionId, status, lockStatus } = this.state.filters;
        if (month !== "all") {
            domain.push(["month", "=", month]);
        }
        if (year !== "all") {
            domain.push(["year", "=", parseInt(year, 10)]);
        }
        if (storeId !== "all") {
            domain.push(["store_id", "=", parseInt(storeId, 10)]);
        }
        if (regionId !== "all") {
            domain.push(["region", "=", regionId]);
        }
        if (status === "applying") {
            domain.push(["apply_status", "=", "applying"]);
        } else if (status === "unapplied") {
            domain.push(["apply_status", "!=", "applying"]);
        }
        if (lockStatus === "locked") {
            domain.push(["is_locked", "=", true]);
        }
        if (lockStatus === "unlocked") {
            domain.push(["is_locked", "=", false]);
        }
        return domain;
    }

    async fetchRosters() {
        const domain = this.buildDomain();
        const offset = (this.state.currentPage - 1) * this.state.pageSize;
        try {
            const records = await this.orm.searchRead(
                "linkq.monthly.roster",
                domain,
                ["id", "name", "month", "year", "store_id", "region", "apply_status", "is_locked", "write_date"],
                { offset, limit: this.state.pageSize, order: "write_date desc" }
            );
            this.state.rosterList = records.map((r) => ({
                ...r,
                store_name: r.store_id ? r.store_id[1] : "",
                region_name: REGION_LABEL[r.region] || r.region || "",
                is_applied: r.apply_status === "applying",
                selected: false,
            }));
            this.state.totalCount = await this.orm.searchCount("linkq.monthly.roster", domain);
            this.state.totalPages = Math.max(1, Math.ceil(this.state.totalCount / this.state.pageSize));
        } catch (e) {
            this.state.rosterList = [];
            this.state.totalCount = 0;
            this.state.totalPages = 1;
            this.notification.add(e?.data?.message || e?.message || "Không tải được danh sách lịch ca.", {
                type: "danger",
            });
        }
    }

    get selectedIds() {
        return this.state.rosterList.filter((r) => r.selected).map((r) => r.id);
    }

    get selectedCount() {
        return this.selectedIds.length;
    }

    onHardDelete() {
        const ids = this.selectedIds;
        if (!ids.length) {
            this.notification.add("Vui lòng tick chọn các bảng lịch ca cần xóa vĩnh viễn!", { type: "warning" });
            return;
        }
        this.dialog.add(RosterHardDeleteDialog, {
            count: ids.length,
            onConfirm: async (code) => {
                try {
                    const res = await this.orm.call("linkq.monthly.roster", "action_hard_delete_permanent", [
                        ids,
                        code,
                    ]);
                    this.notification.add(res.message || "Đã xóa vĩnh viễn.", { type: "success" });
                    await this.fetchRosters();
                } catch (error) {
                    this.notification.add(
                        error?.data?.message || error?.message || "Có lỗi xảy ra khi xóa dữ liệu!",
                        { type: "danger" }
                    );
                    throw error;
                }
            },
        });
    }

    onSearch() {
        this.state.currentPage = 1;
        this.fetchRosters();
    }

    onReset() {
        this.state.filters = defaultFilters();
        this.state.currentPage = 1;
        this.fetchRosters();
    }

    onToggleSelectAll(ev) {
        const checked = ev.target.checked;
        this.state.rosterList.forEach((r) => {
            r.selected = checked;
        });
    }

    onToggleRow(row) {
        row.selected = !row.selected;
    }

    setPage(page) {
        if (page >= 1 && page <= this.state.totalPages) {
            this.state.currentPage = page;
            this.fetchRosters();
        }
    }

    onChangePageSize(ev) {
        this.state.pageSize = parseInt(ev.target.value, 10);
        this.state.currentPage = 1;
        this.fetchRosters();
    }

    get pageNumbers() {
        return Array.from({ length: this.state.totalPages }, (_, i) => i + 1);
    }

    get paginationInfo() {
        if (!this.state.totalCount) {
            return "0-0 trong 0 kết quả";
        }
        const start = (this.state.currentPage - 1) * this.state.pageSize + 1;
        const end = Math.min(this.state.currentPage * this.state.pageSize, this.state.totalCount);
        return `${start}-${end} trong ${this.state.totalCount} kết quả`;
    }

    formatDateTime(dateStr) {
        if (!dateStr) {
            return "";
        }
        const d = new Date(dateStr);
        if (Number.isNaN(d.getTime())) {
            return dateStr;
        }
        const pad = (n) => String(n).padStart(2, "0");
        return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    onOpenDetail(rosterId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "linkq.monthly.roster",
            res_id: rosterId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onCopyRoster(rosterId) {
        try {
            const newId = await this.orm.call("linkq.monthly.roster", "action_duplicate_roster", [rosterId]);
            this.notification.add("Đã sao chép bảng ca.", { type: "success" });
            this.onOpenDetail(newId);
        } catch (e) {
            this.notification.add(e?.data?.message || e?.message || "Không sao chép được bảng ca.", {
                type: "danger",
            });
        }
    }

    async onToggleLock(row, lock) {
        try {
            if (lock) {
                await this.orm.call("linkq.monthly.roster", "action_lock_roster", [row.id, "Khóa thủ công"]);
            } else {
                await this.orm.call("linkq.monthly.roster", "action_unlock_roster", [row.id, "Mở khóa từ danh sách"]);
            }
            this.notification.add(lock ? "Đã khóa bảng ca." : "Đã mở khóa bảng ca.", { type: "success" });
            await this.fetchRosters();
        } catch (e) {
            this.notification.add(e?.data?.message || e?.message || "Không cập nhật được khóa lịch.", {
                type: "danger",
            });
        }
    }

    onDeleteRoster(rosterId) {
        this.dialog.add(ConfirmationDialog, {
            title: "Xóa bảng xếp ca",
            body: "Bạn có chắc chắn muốn xóa bảng xếp ca này không? Dữ liệu đã xóa sẽ không thể phục hồi!",
            confirm: async () => {
                try {
                    await this.orm.unlink("linkq.monthly.roster", [rosterId]);
                    this.notification.add("Đã xóa bảng xếp ca.", { type: "success" });
                    await this.fetchRosters();
                } catch (e) {
                    this.notification.add(e?.data?.message || e?.message || "Không xóa được bảng xếp ca.", {
                        type: "danger",
                    });
                }
            },
            cancel: () => {},
        });
    }
}
