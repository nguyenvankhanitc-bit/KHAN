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

    # Việc tạo từ «Phân công việc team» (danh sách chỉ xem + Xuất Excel)
    team_work_team_id = fields.Many2one("daily.task.team", string="Phân công việc team", copy=False, index=True)
    team_work_coordinator_id = fields.Many2one("res.users", string="Người điều phối", copy=False)
    team_work_checker_id = fields.Many2one("res.users", string="Người kiểm tra (phân công team)", copy=False)
    team_work_no_detail = fields.Boolean(string="Giao theo hạng mục (không chọn chi tiết)", copy=False)

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
            "can_write": Access.can("teamwork", "write"),
        }

    # ------------------------------------------------------------------ sửa 1 việc đã phân
    @api.model
    def update_team_work_task(self, task_id, vals):
        """Sửa công việc trong «Danh sách công việc phân công» (bấm «Lưu» mới ghi)."""
        if not self.env["daily.task.assign.access"].can("teamwork", "write"):
            raise AccessError("Bạn không có quyền Phân công việc team (Chỉnh sửa).")
        task = self.sudo().browse(int(task_id or 0)).exists()
        if not task or not task.team_work_team_id:
            raise ValidationError("Không tìm thấy công việc phân công.")
        team = self._teamwork_teams().filtered(lambda t: t.id == task.team_work_team_id.id)[:1]
        if not team:
            raise AccessError("Bạn không được phân công cho Team này.")
        vals = vals or {}
        name = (vals.get("name") or "").strip()
        if not name:
            raise ValidationError("Vui lòng nhập Nội dung công việc.")
        start = vals.get("date_start") or False
        deadline = vals.get("deadline") or False
        if not deadline:
            raise ValidationError("Vui lòng chọn Deadline.")
        if start and fields.Date.to_date(deadline) < fields.Date.to_date(start):
            raise ValidationError("Deadline phải sau hoặc bằng Ngày thực hiện.")
        members = {m["user_id"]: m for m in self._teamwork_members(team)}
        write = {
            "name": name,
            "assign_date": start,
            "deadline": deadline,
            "note": (vals.get("note") or "").strip(),
        }
        checker = self.env["res.users"].sudo().browse(int(vals.get("checker_id") or 0)).exists()
        write["team_work_checker_id"] = checker.id or False
        uid = int(vals.get("user_id") or 0)
        if uid and uid != task.assignee_user_id.id:
            if uid not in members:
                raise ValidationError("Nhân sự không thuộc Team «%s»." % team.name)
            bridge = self.env["daily.task.employee"].sudo().get_or_create_from_hr(members[uid]["hr_id"])
            write["assignee_id"] = bridge.id
        task.with_context(skip_work_group_user_check=True).write(write)
        return {"ok": True}

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
                "team_work_team_id": team.id,
                "team_work_coordinator_id": coordinator.id,
                "team_work_checker_id": checker.id or False,
                "team_work_no_detail": bool(row.get("no_detail")),
            })
            task._notify_assignee_assigned()
            partners = task._discussion_partner_ids()
            if partners:
                task.message_subscribe(partner_ids=partners.ids)
            created |= task
        return {"count": len(created), "ids": created.ids}

    # ------------------------------------------------------------------ danh sách đã phân (chỉ xem)
    @api.model
    def _team_work_list(self, team, year, month):
        year, month, date_from, date_to = self._month_date_bounds(year=year, month=month)
        tasks = self.sudo().search(
            [("team_work_team_id", "=", team.id),
             "|", "&", ("assign_date", ">=", date_from), ("assign_date", "<=", date_to),
             "&", ("deadline", ">=", date_from), ("deadline", "<=", date_to)],
            order="assign_date asc, id asc",
        )
        cats = {c["id"]: c["label"] for c in self._teamwork_categories(team)}
        WG = self.env["daily.task.work.group"]
        states = dict(self._fields["state"].selection)
        rows = []
        for t in tasks:
            wg = t.work_group_id
            head = wg.category_head_id or wg
            rows.append({
                "id": t.id,
                "user_id": t.assignee_user_id.id or False,
                "employee": t.assignee_id.name or "",
                "category": cats.get(head.id) or (WG._norm_category_name(head.name or "").upper() if wg else ""),
                "detail": (wg.task_name or "") if wg and not t.team_work_no_detail else "",
                "no_detail": bool(t.team_work_no_detail),
                "work_group_id": wg.id or False,
                "name": t.name or "",
                "date_start": t.assign_date.isoformat() if t.assign_date else "",
                "deadline": t.deadline.isoformat() if t.deadline else "",
                "checker": t.team_work_checker_id.name or "",
                "checker_id": t.team_work_checker_id.id or False,
                "note": t.note or "",
                "state": t.state or "",
                "state_label": states.get(t.state, ""),
            })
        return rows

    @api.model
    def get_team_work_list(self, team_id, year=None, month=None):
        self.env["daily.task.assign.access"].check("teamwork", "view")
        team = self._teamwork_teams().filtered(lambda t: t.id == int(team_id or 0))[:1]
        if not team:
            return {"rows": []}
        return {"rows": self._team_work_list(team, year, month)}

    # ------------------------------------------------------------------ Excel
    @api.model
    def export_team_work_excel(self, team_id, coordinator_id, year, month, rows=None):
        """Xuất Excel danh sách công việc phân công (đang soạn trên trang Phân công việc team)."""
        import base64
        import io

        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc
        self.env["daily.task.assign.access"].check("teamwork", "view")
        team = self._teamwork_teams().filtered(lambda t: t.id == int(team_id or 0))[:1]
        if not team:
            raise AccessError("Bạn không được phân công cho Team này.")
        Users = self.env["res.users"].sudo()
        WG = self.env["daily.task.work.group"].sudo()
        coordinator = Users.browse(int(coordinator_id or 0)).exists()
        cats = {c["id"]: c for c in self._teamwork_categories(team)}

        def cat_label(wg_id):
            wg = WG.browse(int(wg_id or 0)).exists()
            if not wg:
                return "", ""
            head = wg.category_head_id or wg
            c = cats.get(head.id)
            return (c["label"] if c else WG._norm_category_name(head.name or "").upper()), (wg.task_name or "")

        def dmy(iso):
            if not iso:
                return ""
            d = fields.Date.to_date(iso)
            return d.strftime("%d/%m/%Y") if d else ""

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Phân công việc team")
        title = wb.add_format({"bold": True, "font_size": 15, "font_color": "#FFFFFF", "bg_color": "#2B3A67",
                               "align": "center", "valign": "vcenter"})
        lbl = wb.add_format({"bold": True, "font_color": "#334155"})
        head = wb.add_format({"bold": True, "bg_color": "#E0E7FF", "border": 1, "border_color": "#A5B4FC",
                              "align": "center", "valign": "vcenter", "text_wrap": True})
        cell = wb.add_format({"border": 1, "border_color": "#CBD5E1", "valign": "vcenter", "text_wrap": True})
        center = wb.add_format({"border": 1, "border_color": "#CBD5E1", "valign": "vcenter", "align": "center"})
        cols = [("STT", 6), ("Nhân sự", 24), ("Hạng mục", 24), ("Tên chi tiết hạng mục", 30),
                ("Nội dung công việc", 40), ("Ngày thực hiện", 15), ("Deadline", 15), ("Người kiểm tra", 22), ("Ghi chú", 30)]
        last = len(cols) - 1
        ws.merge_range(0, 0, 0, last, "PHÂN CÔNG CÔNG VIỆC TEAM %s" % (team.name or "").upper(), title)
        ws.set_row(0, 28)
        ws.write(2, 0, "Phòng ban:", lbl)
        ws.write(2, 2, team.department_id.display_name or "")
        ws.write(2, 4, "Người điều phối:", lbl)
        ws.write(2, 5, coordinator.name or "")
        ws.write(3, 0, "Team:", lbl)
        ws.write(3, 2, team.name or "")
        ws.write(3, 4, "Tháng kế hoạch:", lbl)
        ws.write(3, 5, "%02d/%s" % (int(month or 0), year or ""))
        hr = 5
        for c, (label, width) in enumerate(cols):
            ws.write(hr, c, label, head)
            ws.set_column(c, c, width)
        r = hr + 1
        # Danh sách đã phân của Team trong tháng (giống bảng chỉ xem trên trang)
        rows = self._team_work_list(team, year, month) if rows is None else rows
        for i, row in enumerate(rows or [], start=1):
            cat, detail = cat_label(row.get("work_group_id"))
            if row.get("no_detail"):
                detail = ""
            person = Users.browse(int(row.get("user_id") or 0)).exists()
            checker = Users.browse(int(row.get("checker_id") or 0)).exists()
            vals = [(i, center), (person.name or "", cell), (cat, cell), (detail, cell), (row.get("name") or "", cell),
                    (dmy(row.get("date_start")), center), (dmy(row.get("deadline")), center),
                    (checker.name or "", cell), (row.get("note") or "", cell)]
            for c, (v, f) in enumerate(vals):
                ws.write(r, c, v, f)
            r += 1
        ws.autofilter(hr, 0, max(r - 1, hr), last)
        ws.freeze_panes(hr + 1, 0)
        wb.close()
        name = "phan_cong_viec_team_%s_%s_%02d.xlsx" % ((team.name or "team").replace(" ", "_"), year, int(month or 0))
        return {"file_base64": base64.b64encode(buf.getvalue()).decode(), "filename": name}
