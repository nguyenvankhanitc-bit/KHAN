# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

APPROVAL_STATES = [
    ("pending", "Chờ duyệt"),
    ("approved", "Đã duyệt"),
    ("rejected", "Từ chối"),
]


class DailyTaskPlanApproval(models.Model):
    """Duyệt Plan tháng của 1 nhân sự (Bước 3 — tổng hợp & duyệt, Bước 4 — chốt kế hoạch).

    Duyệt = chốt: lưu phiên bản kế hoạch ban đầu (Ngày bắt đầu / Deadline kế hoạch) vào từng
    việc để đối chiếu thực tế về sau; ngày thực tế đổi sau đó không ghi đè mốc kế hoạch.
    """

    _name = "daily.task.plan.approval"
    _description = "Duyệt Plan tháng"
    _order = "year desc, month desc, user_id"

    user_id = fields.Many2one("res.users", string="Nhân sự", required=True, index=True, ondelete="cascade")
    team_id = fields.Many2one("daily.task.team", string="Team", index=True, ondelete="set null")
    year = fields.Integer(string="Năm", required=True, index=True)
    month = fields.Integer(string="Tháng", required=True, index=True)
    state = fields.Selection(APPROVAL_STATES, string="Trạng thái", default="pending", required=True, index=True)
    approver_id = fields.Many2one("res.users", string="Người duyệt", ondelete="set null")
    decision_date = fields.Datetime(string="Thời điểm duyệt / từ chối")
    reason = fields.Text(string="Lý do từ chối")
    task_count = fields.Integer(string="Số việc khi chốt")
    snapshot = fields.Text(string="Phiên bản kế hoạch khi duyệt (JSON)")

    _user_month_uniq = models.Constraint(
        "UNIQUE(user_id, year, month)",
        "Mỗi nhân sự chỉ có 1 phiếu duyệt Plan cho 1 tháng.",
    )

    # ------------------------------------------------------------------
    @api.model
    def _get(self, user, year, month):
        return self.sudo().search(
            [("user_id", "=", user.id), ("year", "=", int(year)), ("month", "=", int(month))], limit=1
        )

    @api.model
    def _info(self, user, year, month, approver=None):
        """Trạng thái duyệt hiển thị trên Plan (chưa có phiếu = Chờ duyệt)."""
        rec = self._get(user, year, month)
        approver = approver or self.env.user
        state = rec.state if rec else "pending"
        return {
            "state": state,
            "state_label": dict(APPROVAL_STATES)[state],
            "approver": rec.approver_id.name if rec and rec.approver_id else "",
            "date": fields.Datetime.context_timestamp(rec, rec.decision_date).strftime("%d/%m/%Y %H:%M")
            if rec and rec.decision_date else "",
            "reason": rec.reason or "" if rec else "",
            "task_count": rec.task_count if rec else 0,
            "can_approve": self._can_approve(user, approver),
        }

    @api.model
    def _can_approve(self, member, approver=None):
        """Quản lý, hoặc Kiểm soát (trưởng nhóm) các dòng phân công của team thành viên.
        Không tự duyệt Plan của chính mình (trừ Quản lý)."""
        approver = approver or self.env.user
        if self.env["daily.task.assign.access"]._is_manager(approver):
            return True
        if member == approver:
            return False
        lines = self.env["daily.task.assign"].sudo().search([
            ("active", "=", True),
            ("check_user_ids", "in", approver.ids),
        ])
        if any(member in line._responsible_users() for line in lines):
            return True
        # User quản lý hạng mục duyệt cho nhân sự có việc trong hạng mục mình quản lý
        groups = self.env["daily.task.work.group"].sudo().search([
            ("active", "=", True), "|",
            ("category_manager_ids", "in", approver.ids),
            ("team_id.manager_ids", "in", approver.ids),
        ])
        if not groups:
            return False
        cat_lines = self.env["daily.task.assign"].sudo().search([
            ("active", "=", True), ("work_group_id", "in", groups.ids),
        ])
        return any(member in line._responsible_users() for line in cat_lines)

    @api.model
    def _decide(self, user_id, year, month, state, reason=""):
        member = self.env["res.users"].sudo().browse(int(user_id)).exists()
        if not member:
            raise UserError("Không tìm thấy nhân sự.")
        if not self._can_approve(member):
            raise AccessError("Bạn không có quyền duyệt Plan của %s." % member.name)
        year, month = int(year), int(month)
        rec = self._get(member, year, month)
        vals = {
            "state": state,
            "approver_id": self.env.uid,
            "decision_date": fields.Datetime.now(),
            "reason": reason if state == "rejected" else False,
        }
        if state == "approved":
            vals.update(self._freeze_plan(member, year, month))
        if rec:
            rec.write(vals)
        else:
            rec = self.sudo().create({"user_id": member.id, "year": year, "month": month, **vals})
        return self._info(member, year, month)

    @api.model
    def _freeze_plan(self, member, year, month):
        """Bước 4 — chốt kế hoạch: lưu mốc kế hoạch ban đầu cho các việc trong tháng."""
        Task = self.env["daily.task"].sudo()
        emp = self.env["hr.employee"].sudo().search([("user_id", "=", member.id)], limit=1)
        if not emp:
            return {"task_count": 0, "snapshot": "[]"}
        first, last = Task._month_date_bounds(year=year, month=month)[2:4]
        tasks = Task.search(Task._monthly_task_domain(emp.id, first, last))
        snapshot = []
        for task in tasks:
            vals = {}
            # Chỉ ghi lần chốt đầu tiên — duyệt lại không ghi đè phiên bản kế hoạch ban đầu
            if not task.plan_start_date and task.assign_date:
                vals["plan_start_date"] = task.assign_date
            if not task.plan_deadline and task.deadline:
                vals["plan_deadline"] = task.deadline
            if vals:
                task.with_context(tracking_disable=True, from_daily_task_assign=True).write(vals)
            snapshot.append({
                "id": task.id,
                "name": task.name,
                "plan_start": fields.Date.to_string(task.plan_start_date or task.assign_date),
                "plan_deadline": fields.Date.to_string(task.plan_deadline or task.deadline),
                "state": task.state,
            })
        return {"task_count": len(tasks), "snapshot": json.dumps(snapshot, ensure_ascii=False)}

    # ------------------------------------------------------------------ RPC
    @api.model
    def approve_plan(self, user_id, year, month):
        return self._decide(user_id, year, month, "approved")

    @api.model
    def reject_plan(self, user_id, year, month, reason=""):
        reason = (reason or "").strip()
        if not reason:
            raise UserError("Vui lòng nhập lý do từ chối.")
        return self._decide(user_id, year, month, "rejected", reason)

    @api.model
    def approve_team(self, user_ids, year, month):
        """Duyệt nhanh nhiều thành viên (bỏ qua người không có quyền duyệt)."""
        done = []
        for uid in user_ids or []:
            member = self.env["res.users"].sudo().browse(int(uid)).exists()
            if member and self._can_approve(member):
                self._decide(member.id, year, month, "approved")
                done.append(member.id)
        return done

    @api.model
    def resubmit_plan(self, year, month):
        """Nhân viên gửi duyệt lại Plan của mình sau khi bị từ chối."""
        rec = self._get(self.env.user, year, month)
        if rec and rec.state == "rejected":
            rec.write({"state": "pending", "reason": False})
        return self._info(self.env.user, year, month)
