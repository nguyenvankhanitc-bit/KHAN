# -*- coding: utf-8 -*-
"""Báo cáo CV NV Kho — bảng nhập tay theo tháng (BÁO CÁO → Các loại báo cáo).

Mỗi dòng: Ngày (→ Tuần, Thứ) · Hạng mục (Hằng ngày / Hằng tuần / Theo tháng / Phát sinh) · Nội dung ·
Người phụ trách · Deadline · Ngày hoàn thành · Tổng TG (giờ) · Trạng thái · Kiểm soát · Ghi chú.
Phân quyền theo nhóm «Báo cáo CV NV Kho» của Phân quyền báo cáo (Xem / Chỉnh sửa).
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

KIND_SELECTION = [
    ("daily", "Hằng ngày"),
    ("weekly", "Hằng tuần"),
    ("monthly", "Theo tháng"),
    ("adhoc", "Phát sinh"),
]
STATE_SELECTION = [
    ("done", "Hoàn thành"),
    ("in_progress", "Đang thực hiện"),
    ("not_started", "Chưa bắt đầu"),
]


class DailyTaskKhoSheetLine(models.Model):
    _name = "daily.task.kho.sheet.line"
    _description = "Báo cáo CV NV Kho — dòng nhập tay"
    _order = "year, month, team_id, date, sequence, id"

    year = fields.Integer(required=True, index=True)
    month = fields.Integer(required=True, index=True)
    team_id = fields.Many2one("daily.task.team", string="Team", index=True, ondelete="set null")
    sequence = fields.Integer(default=10)
    date = fields.Date(string="Ngày")
    kind = fields.Selection(KIND_SELECTION, string="Loại", default="daily")
    # Hạng mục: liên kết Phân công công việc → Hạng mục (dòng đại diện của hạng mục)
    work_group_id = fields.Many2one("daily.task.work.group", string="Hạng mục", ondelete="set null")
    time_in = fields.Float(string="Giờ vào")
    time_out = fields.Float(string="Giờ ra")
    name = fields.Char(string="Nội dung công việc")
    responsible = fields.Char(string="Người phụ trách")
    date_start = fields.Date(string="Ngày bắt đầu")
    deadline = fields.Date(string="Deadline")
    date_done = fields.Date(string="Ngày hoàn thành")
    hours = fields.Float(string="Tổng TG (giờ)", digits=(10, 2), help="= Giờ ra − Giờ vào")
    state = fields.Selection(STATE_SELECTION, string="Trạng thái", default="not_started")
    controller = fields.Char(string="Kiểm soát")
    note = fields.Char(string="Ghi chú")
    # Dòng tự sinh từ «Phân công việc team» — Ngày/Hạng mục/Nội dung/Người phụ trách/Trạng thái/Kiểm soát
    # lấy theo công việc đã phân (chỉ nhập tay Giờ vào / Giờ ra / Ghi chú)
    task_id = fields.Many2one("daily.task", string="Công việc phân công", index=True, ondelete="cascade")

    # ------------------------------------------------------------------ quyền
    @api.model
    def _perm(self):
        return self.env["daily.task.report.perm"].get_map()["khocv"]

    @api.model
    def _can_write(self):
        pmap = self._perm()
        return self.env.su or bool(pmap.get("write"))

    @api.model
    def _teams(self):
        return self.env["daily.task"]._kho_teams()

    # ------------------------------------------------------------------ đọc
    @api.model
    def _hhmm(self, value):
        if value is None or value is False:
            return ""
        total = int(round(float(value) * 60))
        return "%02d:%02d" % (total // 60 % 24, total % 60)

    @api.model
    def _parse_hhmm(self, value):
        if not value:
            return 0.0
        try:
            h, m = str(value).split(":")[:2]
            return int(h) + int(m) / 60.0
        except (TypeError, ValueError):
            raise ValidationError("Giờ không hợp lệ: %s" % value)

    @api.model
    def _category_label(self, wg):
        WG = self.env["daily.task.work.group"]
        return WG._norm_category_name(wg.name or "").upper() if wg else ""

    @api.model
    def _category_options(self, team):
        """Hạng mục cho ô chọn: các hạng mục đã phân cho user đang nhập (Công việc theo nhân sự);
        chưa được phân hạng mục nào → toàn bộ hạng mục của Team."""
        WG = self.env["daily.task.work.group"].sudo()
        groups = WG.browse([g["id"] for g in WG.with_user(self.env.user).get_groups_for_user(user_id=self.env.uid)])
        if team:
            in_team = groups.filtered(lambda g: g.team_id == team)
            groups = in_team or groups
        if not groups and team:
            groups = WG.search([("active", "=", True), ("team_id", "=", team.id)])
        seen, out = set(), []
        for g in groups.sorted(lambda g: (g.sequence, g.id)):
            head = g.category_head_id or g
            label = self._category_label(head)
            if not label or label in seen:
                continue
            seen.add(label)
            out.append({"id": head.id, "name": label})
        return out

    @api.model
    def _row(self, rec):
        return {
            "id": rec.id,
            "date": rec.date.isoformat() if rec.date else "",
            "kind": rec.kind or "",
            "work_group_id": rec.work_group_id.id or False,
            "category": self._category_label(rec.work_group_id),
            "time_in": self._hhmm(rec.time_in) if rec.time_in or rec.time_out else "",
            "time_out": self._hhmm(rec.time_out) if rec.time_in or rec.time_out else "",
            "name": rec.name or "",
            "responsible": rec.responsible or "",
            "date_start": rec.date_start.isoformat() if rec.date_start else "",
            "deadline": rec.deadline.isoformat() if rec.deadline else "",
            "date_done": rec.date_done.isoformat() if rec.date_done else "",
            "hours": rec.hours or 0.0,
            "state": rec.state or "not_started",
            "controller": rec.controller or "",
            "note": rec.note or "",
            "task_id": rec.task_id.id or False,
            "linked": bool(rec.task_id),
            "eval": self._eval_vals(rec.task_id),
            # % hoàn thành CV (giống Danh sách công việc); dòng nhập tay: Hoàn thành = 100%
            "completion": int(rec.task_id.sudo().completion_percent or 0) if rec.task_id
            else (100 if rec.state == "done" else 0),
        }

    @api.model
    def _eval_vals(self, task):
        """QUẢN LÝ ĐÁNH GIÁ (nhập trên Kiểm tra CV) của công việc liên kết — chỉ xem."""
        if not task:
            return {}
        task = task.sudo()
        rated = bool(task.manager_rating or task.manager_confirmed or task.manager_eval_percent
                     or (task.manager_eval_note or "").strip())
        return {
            "percent": int(task.manager_eval_percent or 0) if rated else None,
            "note": task.manager_eval_note or "",
            "rating": task.manager_rating or "",
            "confirmed": bool(task.manager_confirmed),
        }

    @api.model
    def _task_vals(self, task):
        """Giá trị dòng lấy theo công việc đã phân (Phân công việc team)."""
        wg = task.work_group_id
        head = (wg.category_head_id or wg) if wg else wg
        states = dict(STATE_SELECTION)
        done = task.date_done
        return {
            "date": task.assign_date or task.deadline,
            "work_group_id": head.id if head else False,
            "name": task.name or "",
            "responsible": task.assignee_id.name or "",
            # Ngày bắt đầu / Deadline / Tổng TG: cùng nguồn với Danh sách công việc
            "date_start": task.assign_date,
            "deadline": task.deadline,
            "hours": round(task.duration_hours or 0.0, 2),
            "date_done": done.date() if hasattr(done, "date") else done or False,
            "state": task.state if task.state in states else "not_started",
            "controller": self._controller_name(task),
        }

    @api.model
    def _controller_name(self, task):
        """Kiểm soát: Người kiểm tra / điều phối (Phân công việc team) → QL đã xác nhận → người giao
        (bỏ qua OdooBot của việc sinh tự động)."""
        root = self.env.ref("base.user_root", raise_if_not_found=False)
        for user in (task.team_work_checker_id, task.team_work_coordinator_id,
                     task.manager_confirmed_uid, task.assigned_by_id):
            if user and user != root:
                return user.name or ""
        return ""

    @api.model
    def _sync_team_work(self, team, year, month):
        """Đồng bộ dòng từ Danh sách công việc của nhân sự trong Team (Phân công việc team, Plan tổng,
        việc cá nhân...) trong tháng: thêm việc mới, cập nhật việc đã có, bỏ dòng khi công việc bị
        xoá / chuyển khỏi tháng / chuyển sang hạng mục Team khác."""
        if not team:
            return
        Line = self.sudo()
        _y, _m, date_from, date_to = self.env["daily.task"]._month_date_bounds(year=year, month=month)
        users = team.manager_ids | team.member_ids
        tasks = self.env["daily.task"].sudo().search([
            # Giống Danh sách công việc: mọi việc của nhân sự Team (kể cả hạng mục của Team khác)
            "|", ("team_work_team_id", "=", team.id), ("assignee_user_id", "in", users.ids),
            "|", "&", ("assign_date", ">=", date_from), ("assign_date", "<=", date_to),
            "&", "&", ("assign_date", "=", False), ("deadline", ">=", date_from), ("deadline", "<=", date_to),
        ])
        scope = [("year", "=", year), ("month", "=", month), ("team_id", "=", team.id)]
        linked = Line.search(scope + [("task_id", "!=", False)])
        by_task = {l.task_id.id: l for l in linked}
        stale = linked.filtered(lambda l: l.task_id not in tasks)
        if stale:
            stale.unlink()
        for task in tasks:
            vals = self._task_vals(task)
            line = by_task.get(task.id)
            if line:
                current = lambda k: line.work_group_id.id or False if k == "work_group_id" else line[k]
                changed = {k: v for k, v in vals.items() if current(k) != v}
                if changed:
                    line.write(changed)
            else:
                Line.create(dict(vals, year=year, month=month, team_id=team.id, task_id=task.id,
                                 kind="daily", note=task.note or "", sequence=0))

    @api.model
    def _sees_whole_team(self, team):
        """Quản lý (hệ thống / quản lý Team) xem việc của cả Team."""
        return bool(self.env.su or self.env["daily.task"]._is_manager()
                    or (team and self.env.user in team.manager_ids))

    @api.model
    def get_kho_sheet(self, year=None, month=None, team_id=None):
        self.env["daily.task.report.perm"].check("khocv", "view")
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        teams = self._teams()
        team = teams.filtered(lambda t: t.id == int(team_id or 0))[:1] or self.env["daily.task"]._kho_default_team(teams)
        domain = [("year", "=", year), ("month", "=", month), ("team_id", "=", team.id or False)]
        self._sync_team_work(team, year, month)
        rows = self.sudo().search(domain)
        # Theo user đang đăng nhập: quản lý xem cả Team, nhân viên chỉ xem việc của mình
        if not self._sees_whole_team(team):
            me = self.env.user
            rows = rows.filtered(
                lambda r: r.task_id.assignee_user_id == me if r.task_id
                else (r.create_uid == me or (r.responsible or "").strip().casefold() == (me.name or "").casefold())
            )
        # Gợi ý tên (Người phụ trách / Kiểm soát): thành viên Team
        names = sorted({u.name for u in (team.manager_ids | team.member_ids)} if team else set())
        pmap = self._perm()
        return {
            "year": year,
            "month": month,
            "teams": [{"id": t.id, "name": t.name or ""} for t in teams],
            "team_id": team.id or False,
            "team_name": team.name or "",
            "rows": [self._row(r) for r in rows],
            "people": names,
            "categories": self._category_options(team),
            "me": self.env.user.name or "",
            # Đầu báo cáo (giống Báo cáo cá nhân): chức danh · phòng ban của user đang đăng nhập
            "me_job": (self.env.user.employee_id.sudo().job_title or self.env.user.employee_id.sudo().job_id.name or ""),
            "me_dept": self.env.user.employee_id.sudo().department_id.name or "",
            "kinds": [{"key": k, "label": l} for k, l in KIND_SELECTION],
            "states": [{"key": k, "label": l} for k, l in STATE_SELECTION],
            "can_write": self._can_write(),
            "report_perm": {k: (v if v is not None else True) for k, v in pmap.items()},
        }

    # ------------------------------------------------------------------ ghi
    @api.model
    def _clean_date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            raise ValidationError("Ngày không hợp lệ: %s" % value)

    @api.model
    def save_kho_sheet(self, year, month, team_id, rows, deleted_ids=None):
        """Lưu cả bảng của tháng: thêm / sửa / xoá dòng."""
        if not self._can_write():
            raise AccessError("Bạn không có quyền chỉnh sửa Báo cáo CV NV Kho.")
        year, month = int(year), int(month)
        teams = self._teams()
        team = teams.filtered(lambda t: t.id == int(team_id or 0))[:1]
        if team_id and not team:
            raise AccessError("Bạn không thuộc Team này.")
        Line = self.sudo()
        scope = [("year", "=", year), ("month", "=", month), ("team_id", "=", team.id or False)]
        if deleted_ids:
            # Dòng từ Phân công việc team không xoá ở đây (xoá công việc bên phân công)
            Line.search(scope + [("id", "in", [int(i) for i in deleted_ids]), ("task_id", "=", False)]).unlink()
        kinds = dict(KIND_SELECTION)
        states = dict(STATE_SELECTION)
        for seq, row in enumerate(rows or [], start=1):
            name = (row.get("name") or "").strip()
            d = self._clean_date(row.get("date"))
            if d and (d.year, d.month) != (year, month):
                raise ValidationError(
                    "Ngày %s không thuộc tháng %02d/%s (dòng «%s»)." % (d.strftime("%d/%m/%Y"), month, year, name)
                )
            d_start = self._clean_date(row.get("date_start"))
            d_end = self._clean_date(row.get("deadline"))
            if d_start and d_end and d_end < d_start:
                raise ValidationError("Deadline phải sau hoặc bằng Ngày bắt đầu (dòng «%s»)." % name)
            try:
                hours = max(float(row.get("hours") or 0), 0.0)
            except (TypeError, ValueError):
                raise ValidationError("Tổng TG không hợp lệ (dòng «%s»)." % name)
            vals = {
                "year": year,
                "month": month,
                "team_id": team.id or False,
                "sequence": seq,
                "date": d,
                "work_group_id": int(row.get("work_group_id") or 0) or False,
                "kind": row.get("kind") if row.get("kind") in kinds else "daily",
                "name": name,
                "responsible": (row.get("responsible") or "").strip(),
                "date_start": d_start,
                "deadline": d_end,
                "date_done": self._clean_date(row.get("date_done")),
                "hours": round(hours, 2),
                "state": row.get("state") if row.get("state") in states else "not_started",
                "controller": (row.get("controller") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
            if not any([name, vals["responsible"], vals["note"], d]):
                continue  # dòng trống
            rid = int(row.get("id") or 0)
            rec = Line.search(scope + [("id", "=", rid)]) if rid else Line.browse()
            if rec and rec.task_id:
                # Dòng liên kết phân công: chỉ nhận Ghi chú (còn lại theo công việc đã phân)
                rec.write({k: vals[k] for k in ("sequence", "note")})
                continue
            if rec:
                rec.write(vals)
            else:
                Line.create(vals)
        return self.get_kho_sheet(year=year, month=month, team_id=team.id or False)
