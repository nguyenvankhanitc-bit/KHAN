# -*- coding: utf-8 -*-
"""Quản lý công việc → Phân công việc team.

Người điều phối chọn Team → Hạng mục / Tên chi tiết hạng mục (từ trang Hạng mục của Team) → nhiều
nhân sự cùng lúc → danh sách công việc → Lưu: mỗi dòng tạo 1 công việc cá nhân cho nhân sự đó
(giống Giao việc). Quyền: Cài đặt → Phân quyền phân công công việc → «Phân công việc team».
"""

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTask(models.Model):
    _inherit = "daily.task"

    # ------------------------------------------------------------------ phạm vi
    @api.model
    def _teamwork_teams(self):
        """Team được phân công: Quản lý module → mọi Team; người khác → Team mình quản lý / thuộc."""
        return self._kho_teams()

    @api.model
    def _teamwork_categories(self, team):
        """Hạng mục của Team: [{id (dòng đại diện), name, details: [{id, name}]}] — theo trang Hạng mục."""
        WG = self.env["daily.task.work.group"].sudo()
        rows = WG.search([("active", "=", True), ("team_id", "=", team.id)], order="sequence, id")
        cats, order = {}, []
        for g in rows:
            head = g.category_head_id or g
            label = WG._norm_category_name(head.name or "").upper()
            if not label:
                continue
            if head.id not in cats:
                cats[head.id] = {"id": head.id, "name": label, "details": []}
                order.append(head.id)
            detail = (g.task_name or "").strip()
            if detail:
                cats[head.id]["details"].append({"id": g.id, "name": detail})
        out = [cats[k] for k in order]
        # Đánh số La Mã theo thứ tự trang Hạng mục
        WGm = self.env["daily.task.work.group"]
        for idx, c in enumerate(out, start=1):
            c["label"] = "%s. %s" % (WGm._roman(idx), c["name"])
        return out

    @api.model
    def _teamwork_task_names(self, team, members):
        """Gợi ý «Tên công việc» từ Quản lý công việc cá nhân: tên việc nhân sự trong Team đã nhập
        (6 tháng gần nhất), theo chi tiết hạng mục → {work_group_id: [tên, ...]} (mới nhất trước)."""
        user_ids = [m["user_id"] for m in members]
        if not user_ids:
            return {}
        since = fields.Date.subtract(fields.Date.context_today(self), months=6)
        tasks = self.sudo().search(
            [("assignee_user_id", "in", user_ids), ("work_group_id.team_id", "=", team.id),
             ("assign_date", ">=", since)],
            order="assign_date desc, id desc", limit=2000,
        )
        out = {}
        for t in tasks:
            name = " ".join((t.name or "").split())
            if not name:
                continue
            bucket = out.setdefault(str(t.work_group_id.id), [])
            if name not in bucket and len(bucket) < 30:
                bucket.append(name)
        return out

    @api.model
    def _teamwork_members(self, team):
        users = (team.manager_ids | team.member_ids).filtered("active")
        emps = self.env["hr.employee"].sudo().search([("user_id", "in", users.ids)], order="name")
        return [{"user_id": e.user_id.id, "hr_id": e.id, "name": e.name or ""} for e in emps]

    # ------------------------------------------------------------------ đọc
    @api.model
    def get_team_work_data(self, team_id=None):
        Access = self.env["daily.task.assign.access"]
        Access.check("teamwork", "view")
        teams = self._teamwork_teams()
        team = teams.filtered(lambda t: t.id == int(team_id or 0))[:1] or teams[:1]
        depts = {}
        for t in teams:
            d = t.department_id
            depts.setdefault(d.id or 0, {"id": d.id or 0, "name": d.display_name if d else "Chưa có phòng ban"})
        members = self._teamwork_members(team) if team else []
        return {
            "task_names": self._teamwork_task_names(team, members) if team else {},
            "departments": list(depts.values()),
            "teams": [{"id": t.id, "name": t.name or "", "department_id": t.department_id.id or 0} for t in teams],
            "team_id": team.id or False,
            "team_name": team.name or "",
            "department_id": team.department_id.id or 0 if team else 0,
            "members": self._teamwork_members(team) if team else [],
            "categories": self._teamwork_categories(team) if team else [],
            "me": self.env.uid,
            "can_create": Access.can("teamwork", "create"),
        }

    # ------------------------------------------------------------------ ghi
    @api.model
    def create_team_work_tasks(self, team_id, coordinator_id, rows):
        """Lưu: mỗi dòng → 1 công việc cá nhân của nhân sự (giống Giao việc). Trả về số việc đã tạo."""
        Access = self.env["daily.task.assign.access"]
        if not Access.can("teamwork", "create"):
            raise AccessError("Bạn không có quyền Phân công việc team (Thêm).")
        team = self._teamwork_teams().filtered(lambda t: t.id == int(team_id or 0))[:1]
        if not team:
            raise AccessError("Bạn không được phân công cho Team này.")
        members = {m["user_id"]: m for m in self._teamwork_members(team)}
        WG = self.env["daily.task.work.group"].sudo()
        team_wg = WG.search([("active", "=", True), ("team_id", "=", team.id)])
        Users = self.env["res.users"].sudo()
        coordinator = Users.browse(int(coordinator_id or 0)).exists() or self.env.user
        if not rows:
            raise ValidationError("Chưa có công việc nào trong danh sách.")
        created = self.browse()
        for idx, row in enumerate(rows, start=1):
            uid = int(row.get("user_id") or 0)
            if uid not in members:
                raise ValidationError("Dòng %s: nhân sự không thuộc Team «%s»." % (idx, team.name))
            name = (row.get("name") or "").strip()
            if not name:
                raise ValidationError("Dòng %s: vui lòng nhập Nội dung công việc." % idx)
            start = row.get("date_start") or fields.Date.context_today(self)
            deadline = row.get("deadline")
            if not deadline:
                raise ValidationError("Dòng %s: vui lòng chọn Deadline." % idx)
            if fields.Date.to_date(deadline) < fields.Date.to_date(start):
                raise ValidationError("Dòng %s: Deadline phải sau hoặc bằng Ngày thực hiện." % idx)
            wg = WG.browse(int(row.get("work_group_id") or 0))
            if wg and wg not in team_wg:
                raise ValidationError("Dòng %s: hạng mục không thuộc Team «%s»." % (idx, team.name))
            hr = self.env["hr.employee"].sudo().browse(members[uid]["hr_id"])
            bridge = self.env["daily.task.employee"].sudo().get_or_create_from_hr(hr.id)
            dept = wg.department_id or team.department_id or hr.department_id
            checker = Users.browse(int(row.get("checker_id") or 0)).exists()
            note = (row.get("note") or "").strip()
            desc_lines = ["Phân công việc team: %s" % team.name, "Người điều phối: %s" % coordinator.name]
            if checker:
                desc_lines.append("Người kiểm tra: %s" % checker.name)
            if note:
                desc_lines.append(note)
            task = self.with_context(
                daily_task_assigner_uid=self.env.uid, skip_work_group_user_check=True,
            ).sudo().create({
                "name": name,
                "assign_date": start,
                "deadline": deadline,
                "assigned_by_id": self.env.uid,
                "department_id": dept.id or False,
                "assignee_id": bridge.id,
                "work_group_id": wg.id or False,
                "priority": row.get("priority") or "medium",
                "state": "not_started",
                "note": note,
                "description": Markup("<br/>").join(escape(x) for x in desc_lines),
            })
            task._notify_assignee_assigned()
            partners = task._discussion_partner_ids()
            if partners:
                task.message_subscribe(partner_ids=partners.ids)
            created |= task
        return {"count": len(created), "ids": created.ids}
