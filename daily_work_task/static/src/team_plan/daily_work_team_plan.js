/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";
import { TeamLineEditDialog, TeamTaskDialog } from "@daily_work_task/team_plan/team_task_dialog";

/** Plan tổng team — tổng hợp từ Plan CV cá nhân của các thành viên (theo mẫu PLAN TEAM). */
export class DailyWorkTeamPlan extends Component {
    static template = "daily_work_task.DailyWorkTeamPlan";
    static components = { DailyWorkAppShell, TeamTaskDialog, TeamLineEditDialog };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const today = new Date();
        this.state = useState({
            loading: true,
            exporting: false,
            year: today.getFullYear(),
            month: today.getMonth() + 1,
            teamId: false,
            data: null,
            filterState: "",
            closedGroups: {},
            closedDepts: {},
            showMembers: false,
            adding: false,
            editLine: null,
            closedTeams: {},
            busy: false,
            rejectingId: false,
            rejectReason: "",
        });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "team_plan";
    }

    statusCount(key) {
        const summary = this.state.data?.summary || {};
        if (key === "total") {
            return summary.task_total || 0;
        }
        return (summary.status || {})[key] || 0;
    }

    get doneTaskPercent() {
        const total = this.statusCount("total");
        return total ? Math.round((100 * this.statusCount("done")) / total) : 0;
    }

    /** Mọi nhóm hạng mục của mọi team đang hiển thị. */
    get allGroups() {
        const out = [];
        for (const d of this.state.data?.departments || []) {
            for (const t of d.teams || []) {
                out.push(...(t.groups || []));
            }
        }
        return out;
    }

    xCount(key) {
        let n = 0;
        for (const g of this.allGroups) {
            for (const line of g.lines || []) {
                for (const cell of line.cells || []) {
                    const cls = cell.cls.split(" ");
                    if (cls.includes("is-plan") && (key === "total" || cls.includes(`st-${key}`))) {
                        n += 1;
                    }
                }
            }
        }
        return n;
    }

    // ---- Bước 3–4: Duyệt / Từ chối Plan tháng ----
    approvalCount(stateKey) {
        return (this.state.data?.members || []).filter((m) => m.approval?.state === stateKey).length;
    }

    get pendingApprovable() {
        return (this.state.data?.members || []).filter(
            (m) => m.approval?.can_approve && m.approval.state !== "approved"
        );
    }

    async _approvalCall(method, args, kwargs, okMessage) {
        this.state.busy = true;
        try {
            await this.orm.call("daily.task.plan.approval", method, args, kwargs || {});
            this.notification.add(okMessage, { type: "success" });
            await this.load(true);
            return true;
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không thực hiện được."), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    async approve(member) {
        await this._approvalCall(
            "approve_plan",
            [member.id, this.state.year, this.state.month],
            {},
            _t("Đã duyệt và chốt Plan tháng của %s.", member.name)
        );
    }

    async approveAll() {
        const ids = this.pendingApprovable.map((m) => m.id);
        await this._approvalCall(
            "approve_team",
            [ids, this.state.year, this.state.month],
            {},
            _t("Đã duyệt %s Plan tháng.", ids.length)
        );
    }

    startReject(member) {
        this.state.rejectingId = member.id;
        this.state.rejectReason = "";
    }

    cancelReject() {
        this.state.rejectingId = false;
        this.state.rejectReason = "";
    }

    async confirmReject(member) {
        const reason = (this.state.rejectReason || "").trim();
        if (!reason) {
            this.notification.add(_t("Vui lòng nhập lý do từ chối."), { type: "warning" });
            return;
        }
        const ok = await this._approvalCall(
            "reject_plan",
            [member.id, this.state.year, this.state.month],
            { reason },
            _t("Đã từ chối Plan tháng của %s.", member.name)
        );
        if (ok) {
            this.cancelReject();
        }
    }

    // ---- Thêm công việc chung của team (khung dùng chung TeamTaskDialog) ----
    openAdd() {
        this.state.adding = true;
    }

    closeAdd() {
        this.state.adding = false;
    }

    // ---- Chỉnh sửa / Xóa công việc chung (Phân quyền Plan tổng) ----
    canOpenLine(line) {
        if (line.line_id) {
            return Boolean(this.state.data?.can_write || this.state.data?.can_unlink);
        }
        // Việc bổ sung cá nhân: chính chủ cập nhật ngay trên Plan tổng
        return Boolean(line.own && line.task_id);
    }

    openLine(line) {
        if (this.canOpenLine(line)) {
            this.state.editLine = line;
        }
    }

    closeLine() {
        this.state.editLine = null;
    }

    async onLineSaved() {
        this.state.editLine = null;
        await this.load(true);
    }

    async onAddSaved() {
        this.state.adding = false;
        await this.load(true);
    }

    /** Mở / thu gọn danh sách nhân viên ở khung Duyệt Plan tháng. */
    toggleMembers() {
        this.state.showMembers = !this.state.showMembers;
    }

    setFilter(stateKey) {
        this.state.filterState = this.state.filterState === stateKey ? "" : stateKey;
    }

    get hasRows() {
        return this.allGroups.length > 0;
    }

    deptOpen(dept) {
        return !this.state.closedDepts[dept.id];
    }

    toggleDept(dept) {
        this.state.closedDepts = { ...this.state.closedDepts, [dept.id]: this.deptOpen(dept) };
    }

    teamOpen(team) {
        return !this.state.closedTeams[team.id];
    }

    toggleTeam(team) {
        this.state.closedTeams = { ...this.state.closedTeams, [team.id]: this.teamOpen(team) };
    }

    visibleGroupsOf(team) {
        const groups = team.groups || [];
        const key = this.state.filterState;
        if (!key) {
            return groups;
        }
        return groups
            .map((g) => ({
                ...g,
                lines: g.lines.filter((l) =>
                    (l.cells || []).some((c) => c.cls.split(" ").includes(`st-${key}`))
                ),
            }))
            .filter((g) => g.lines.length);
    }

    groupOpen(group) {
        return !this.state.closedGroups[group.key];
    }

    toggleGroup(group) {
        this.state.closedGroups = { ...this.state.closedGroups, [group.key]: this.groupOpen(group) };
    }

    async shiftMonth(delta) {
        let month = this.state.month + delta;
        let year = this.state.year;
        if (month < 1) {
            month = 12;
            year -= 1;
        } else if (month > 12) {
            month = 1;
            year += 1;
        }
        this.state.month = month;
        this.state.year = year;
        await this.load();
    }

    async onTeam(ev) {
        const v = ev.target.value;
        this.state.teamId = v === "all" ? "all" : parseInt(v) || false;
        await this.load();
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            this.state.data = await this.orm.call("daily.task.assign", "get_team_plan_overview", [], {
                year: this.state.year,
                month: this.state.month,
                team_id: this.state.teamId,
            });
            // Quản lý mặc định xem tất cả phòng ban / team
            this.state.teamId = this.state.data?.mode === "all" ? "all" : this.state.data?.team?.id || false;
        } catch (e) {
            this.state.data = null;
            this.notification.add(e?.data?.message || _t("Không tải được Plan tổng team."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    _downloadBase64Excel(b64, filename) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || "Plan_tong_team.xlsx";
        a.click();
        URL.revokeObjectURL(url);
    }

    async onExportExcel() {
        this.state.exporting = true;
        try {
            const result = await this.orm.call("daily.task.assign", "export_team_plan_excel", [], {
                year: this.state.year,
                month: this.state.month,
                team_id: this.state.teamId,
            });
            if (!result?.file_base64) {
                throw new Error(_t("Không nhận được file Excel."));
            }
            this._downloadBase64Excel(result.file_base64, result.filename);
            this.notification.add(_t("Đã xuất Plan tổng team ra Excel."), { type: "success" });
        } catch (e) {
            this.notification.add(e?.data?.message || _t("Không xuất được Excel."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("daily_work_team_plan", DailyWorkTeamPlan);
