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
            "assignee_uid": rec.task_id.assignee_user_id.id or False,
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
            # Quản lý xem cả Team → hiện tên người phụ trách dưới nội dung công việc
            "whole_team": self._sees_whole_team(team),
            # QL đánh giá tổng đã chốt (Báo cáo hiệu suất) theo user — kết quả cuối cùng «QL đánh giá»
            "manager_perf": {str(k): v for k, v in self.env["daily.task.manager.perf"].get_map(
                year, month, user_ids=(team.manager_ids | team.member_ids).ids if team else [self.env.uid]).items()},
            # Đầu báo cáo (giống Báo cáo cá nhân): chức danh · phòng ban của user đang đăng nhập
            "me_job": (self.env.user.employee_id.sudo().job_title or self.env.user.employee_id.sudo().job_id.name or ""),
            "me_dept": self.env.user.employee_id.sudo().department_id.name or "",
            "kinds": [{"key": k, "label": l} for k, l in KIND_SELECTION],
            "states": [{"key": k, "label": l} for k, l in STATE_SELECTION],
            "can_write": self._can_write(),
            "can_export": bool(self.env.su or self._perm().get("export")),
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


    # ------------------------------------------------------------------ Xuất Excel (A4)
    @api.model
    def _final_manager_eval(self, rows, overrides):
        """QL đánh giá cuối cùng: theo từng nhân viên = QL đánh giá tổng đã chốt (nếu có), không thì
        TB % QL chấm trên Kiểm tra CV; gộp nhiều nhân viên = TB có trọng số theo số việc."""
        per = {}
        for r in rows:
            if not r.get("linked"):
                continue
            uid = str(r.get("assignee_uid") or 0)
            s = per.setdefault(uid, [0, 0])
            s[0] += int((r.get("eval") or {}).get("percent") or 0)
            s[1] += 1
        total = count = 0
        for uid, (sm, n) in per.items():
            val = overrides.get(uid)
            total += (val if val is not None else sm / float(n)) * n
            count += n
        return total / count if count else 0

    @api.model
    def _month_weeks(self, year, month):
        """Tuần trong tháng: Thứ 2 → Chủ nhật (tuần đầu / cuối cắt theo tháng) — giống màn hình."""
        from calendar import monthrange
        from datetime import date
        last = monthrange(year, month)[1]
        weeks, start = [], 1
        while start <= last:
            dow = date(year, month, start).weekday()  # 0 = Thứ 2
            end = min(last, start + (6 - dow))
            weeks.append((len(weeks) + 1, start, end))
            start = end + 1
        return weeks

    @api.model
    def export_kho_sheet_excel(self, year=None, month=None, team_id=None, week_no=0):
        """Xuất Báo cáo CV NV Kho ra Excel: khổ A4 dọc, vừa 1 trang chiều ngang, canh lề, lặp tiêu đề."""
        self.env["daily.task.report.perm"].check("khocv", "export")
        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc
        import base64
        import io

        data = self.get_kho_sheet(year=year, month=month, team_id=team_id)
        year, month = data["year"], data["month"]
        weeks = self._month_weeks(year, month)
        week = next((w for w in weeks if w[0] == int(week_no or 0)), None)
        rows = data["rows"]
        if week:
            rows = [r for r in rows if r["date"] and week[1] <= int(r["date"][8:10]) <= week[2]]
        whole = bool(data.get("whole_team"))
        states = {s["key"]: s["label"] for s in data["states"]}
        wd = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

        def fmt(iso):
            return "%s/%s/%s" % (iso[8:10], iso[5:7], iso[0:4]) if iso else ""

        def num(v):
            """20.0 → 20 · 92.8 → 92.8 (giống màn hình)."""
            v = round(float(v or 0), 1)
            return int(v) if v == int(v) else v

        def week_of(iso):
            if not iso:
                return ""
            d = int(iso[8:10])
            w = next((x for x in weeks if x[1] <= d <= x[2]), None)
            return "Tuần %s" % w[0] if w else ""

        def day_label(iso):
            if not iso:
                return ""
            return "%s %s" % (fmt(iso), wd[fields.Date.to_date(iso).weekday()])

        # Chỉ số (giống ô trên màn hình)
        total = len(rows)
        cnt = lambda k: sum(1 for r in rows if r["state"] == k)
        pct = lambda n: num(n * 100.0 / total) if total else 0
        hours = num(sum(float(r["hours"] or 0) for r in rows))
        eff = num(self._final_manager_eval(rows, data.get("manager_perf") or {}))
        today_iso = fields.Date.context_today(self).isoformat()
        st = {"done": 0, "doing": 0, "todo": 0, "overdue": 0}
        for x in rows:
            if x["state"] == "done":
                st["done"] += 1
            elif x.get("deadline") and x["deadline"] < today_iso:
                st["overdue"] += 1
            elif x["state"] == "in_progress":
                st["doing"] += 1
            else:
                st["todo"] += 1
        rt = {"pass": 0, "average": 0, "fail": 0}
        unrated = 0
        for x in rows:
            k = (x.get("eval") or {}).get("rating")
            if k in rt:
                rt[k] += 1
            elif x.get("linked"):
                unrated += 1
        rated = sum(rt.values())
        self_eval = num(sum(int(x.get("completion") or 0) for x in rows) / len(rows)) if rows else 0
        mperf = data.get("manager_perf") or {}
        locked = any(str(x.get("assignee_uid") or 0) in mperf for x in rows if x.get("linked"))

        # Group theo hạng mục
        groups = {}
        for r in rows:
            key = r.get("category") or ""
            groups.setdefault(key, []).append(r)
        order = sorted(groups, key=lambda k: (k == "", k.casefold()))

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Bao cao CV NV Kho")
        F = lambda **kw: wb.add_format(dict({"font_name": "Times New Roman", "font_size": 12, "valign": "vcenter"}, **kw))
        f_title = F(bold=True, font_size=12, align="center")
        f_center = F(align="center")
        f_sub = F(align="center", italic=True, font_color="#475569")
        f_kpi_lbl = F(bold=True, align="center", border=1, bg_color="#e2e8f0", text_wrap=True, font_size=12)
        f_kpi_val = F(bold=True, align="center", border=1, font_size=12)
        f_head = F(bold=True, align="center", border=1, bg_color="#0f4c9c", font_color="#ffffff", text_wrap=True)
        f_head_eval = F(bold=True, align="center", border=1, bg_color="#fce4d6", text_wrap=True)
        f_head_pass = F(bold=True, align="center", border=1, bg_color="#fce4d6", font_color="#15803d", text_wrap=True)
        f_head_avg = F(bold=True, align="center", border=1, bg_color="#fce4d6", font_color="#b45309", text_wrap=True)
        f_head_fail = F(bold=True, align="center", border=1, bg_color="#fce4d6", font_color="#b91c1c", text_wrap=True)
        f_group = F(bold=True, border=1, bg_color="#b4c7e7")
        f_cell = F(border=1, text_wrap=True)
        f_cell_c = F(border=1, align="center", text_wrap=True)
        f_eval = F(border=1, align="center", bg_color="#fff7ed", text_wrap=True)
        f_eval_l = F(border=1, bg_color="#fff7ed", text_wrap=True)
        f_tick = F(border=1, align="center", bg_color="#fff7ed", bold=True, font_color="#15803d")
        f_state = {
            "done": F(border=1, align="center", font_color="#15803d", bold=True),
            "in_progress": F(border=1, align="center", font_color="#b45309", bold=True),
            "not_started": F(border=1, align="center", font_color="#4b5563"),
        }
        f_total = F(bold=True, border=1, bg_color="#b4c7e7")
        f_pct_i = F(border=1, align="center", num_format="0%")
        f_pct_1 = F(border=1, align="center", num_format="0.0%")
        f_eval_pi = F(border=1, align="center", bg_color="#fff7ed", num_format="0%")
        f_eval_p1 = F(border=1, align="center", bg_color="#fff7ed", num_format="0.0%")
        f_num = F(border=1, align="center")  # General: 147 · 0,5 (không thừa dấu phẩy)

        def pfmt(v, fi, f1):
            v = round(float(v or 0), 1)
            return fi if v == int(v) else f1

        # Cột (độ rộng ký tự) — tổng vừa A4 ngang khi co 1 trang chiều ngang
        cols = [("STT", 6), ("Tuần", 9), ("Nội dung công việc", 58)]
        if whole:
            cols.append(("Người phụ trách", 22))
        cols += [("Ngày bắt đầu", 16), ("Deadline", 14), ("Tổng TG (giờ)", 10), ("Trạng thái", 16),
                 ("Kiểm soát", 20), ("Ghi chú", 25)]
        n_main = len(cols)
        eval_cols = [("% Hoàn thành", 11, f_head_eval), ("Ghi chú", 25, f_head_eval), ("Đạt", 8, f_head_pass),
                     ("Trung bình", 10, f_head_avg), ("Không đạt", 10, f_head_fail), ("Xác nhận QL", 11, f_head_eval)]
        last_col = n_main + len(eval_cols) - 1
        for i, (_l, w) in enumerate(cols):
            ws.set_column(i, i, w)
        for j, (_l, w, _f) in enumerate(eval_cols):
            ws.set_column(n_main + j, n_main + j, w)

        # Đầu báo cáo (giống Báo cáo cá nhân)
        r = 0
        ws.merge_range(r, 0, r, last_col, "BÁO CÁO CÔNG VIỆC", f_title)
        ws.set_row(r, 22)
        r += 1
        who = ("Team: %s" % data.get("team_name")) if whole else ("Họ và tên: %s" % (data.get("me") or ""))
        ws.merge_range(r, 0, r, last_col, who, F(align="center", bold=True, font_size=12))
        r += 1
        sub = " · ".join(x for x in (data.get("me_job"), data.get("me_dept")) if x) if not whole else ""
        if sub:
            ws.merge_range(r, 0, r, last_col, sub, f_sub)
            r += 1
        period = "Tháng %s Năm %s" % (month, year)
        if week:
            period += " · Tuần %s (%02d/%02d – %02d/%02d)" % (week[0], week[1], month, week[2], month)
        ws.merge_range(r, 0, r, last_col, period, f_center)
        r += 2

        # 3 biểu đồ (giống màn hình) + bảng số liệu dưới mỗi biểu đồ
        widths = [w for _l, w in cols] + [w for _l, w, _f in eval_cols]

        def split(n):
            """Chia cột thành n khối có độ rộng gần bằng nhau (cột STT / Tuần hẹp)."""
            target = sum(widths) / float(n)
            out, c0 = [], 0
            for i in range(n):
                if i == n - 1:
                    out.append((c0, last_col))
                    break
                c1, acc = c0 + 2, sum(widths[c0:c0 + 3])  # tối thiểu 3 cột / khối
                while c1 + 1 <= last_col - 3 * (n - i - 1) and acc + widths[c1 + 1] / 2.0 <= target:
                    c1 += 1
                    acc += widths[c1]
                out.append((c0, c1))
                c0 = c1 + 1
            return out

        px = lambda c0, c1: sum(int(w * 7 + 5) for w in widths[c0:c1 + 1])
        f_sec = F(bold=True, font_size=12, font_color="#0b2a5b", bottom=2, bottom_color="#1d4ed8")
        f_lh = F(bold=True, border=1, bg_color="#f1f5f9", font_color="#0b2a5b", align="center", font_size=12)
        f_ll = F(border=1)
        f_lb = F(border=1, bold=True)
        f_lc = F(border=1, align="center", bold=True)
        CH = 13  # số dòng vùng biểu đồ
        blocks = split(3)
        sec = r
        chart_top = sec + 1
        tbl = chart_top + CH + 1
        titles = ["1. TỔNG CÔNG VIỆC", "2. KẾT QUẢ ĐÁNH GIÁ QUẢN LÝ", "3. THỜI GIAN VÀ HIỆU SUẤT"]
        total_tasks = sum(st.values())
        p_of = lambda n, t: (n / float(t)) if t else 0
        legends = [
            [("Hoàn thành", st["done"], p_of(st["done"], total_tasks), "#16a34a"),
             ("Đang thực hiện", st["doing"], p_of(st["doing"], total_tasks), "#f59e0b"),
             ("Chưa bắt đầu", st["todo"], p_of(st["todo"], total_tasks), "#94a3b8"),
             ("Quá hạn", st["overdue"], p_of(st["overdue"], total_tasks), "#dc2626")],
            [("Đạt", rt["pass"], p_of(rt["pass"], rated), "#16a34a"),
             ("Trung bình", rt["average"], p_of(rt["average"], rated), "#f59e0b"),
             ("Không đạt", rt["fail"], p_of(rt["fail"], rated), "#dc2626")],
            [("NV tự đánh giá", None, self_eval / 100.0, "#2563eb"),
             ("QL đánh giá" + (" (QL chốt)" if locked else ""), None, eff / 100.0, "#16a34a")],
        ]
        foot = [("Tổng công việc", total_tasks), ("Đã đánh giá", rated), ("Tổng thời gian (giờ)", hours)]
        heads = [("Trạng thái", "Số CV", "Tỷ lệ"), ("Xếp loại", "Số CV", "Tỷ lệ"), ("Tiêu chí", "", "Giá trị")]
        for bi, (c0, c1) in enumerate(blocks):
            lc1 = c1 - 2  # nhãn: c0..c1-2 · số: c1-1 · %: c1
            ws.merge_range(sec, c0, sec, c1, titles[bi], f_sec)
            # bảng số liệu
            t = tbl
            h = heads[bi]
            (ws.merge_range(t, c0, t, lc1, h[0], f_lh) if lc1 > c0 else ws.write(t, c0, h[0], f_lh))
            ws.write(t, c1 - 1, h[1], f_lh)
            ws.write(t, c1, h[2], f_lh)
            first = t + 1
            for k, (lbl, n, p, _color) in enumerate(legends[bi]):
                rr = first + k
                (ws.merge_range(rr, c0, rr, lc1, lbl, f_ll) if lc1 > c0 else ws.write(rr, c0, lbl, f_ll))
                if n is None:
                    ws.write_blank(rr, c1 - 1, None, f_ll)
                else:
                    ws.write_number(rr, c1 - 1, n, f_num)
                ws.write_number(rr, c1, p, pfmt(p * 100, f_pct_i, f_pct_1))
            last = first + len(legends[bi]) - 1
            fr = last + 1
            flbl, fval = foot[bi]
            (ws.merge_range(fr, c0, fr, lc1, flbl, f_lb) if lc1 > c0 else ws.write(fr, c0, flbl, f_lb))
            if bi == 2:
                ws.merge_range(fr, c1 - 1, fr, c1, "%s giờ" % fval, f_lc)
            else:
                ws.write_number(fr, c1 - 1, fval, f_lc)
                ws.write_blank(fr, c1, None, f_lc)
            if bi == 1 and unrated:
                ws.merge_range(fr + 1, c0, fr + 1, c1, "%s việc chưa được đánh giá" % unrated,
                               F(italic=True, font_color="#475569"))
            # biểu đồ
            colors = [x[3] for x in legends[bi]]
            if bi < 2:
                ch = wb.add_chart({"type": "doughnut"})
                ch.add_series({
                    "categories": ["Bao cao CV NV Kho", first, c0, last, c0],
                    "values": ["Bao cao CV NV Kho", first, c1 - 1, last, c1 - 1],
                    "points": [{"fill": {"color": cl}, "border": {"color": "#ffffff"}} for cl in colors],
                    "data_labels": {"value": True, "font": {"bold": True, "color": "#ffffff", "size": 12}},
                })
                ch.set_hole_size(55)
                ch.set_legend({"position": "right", "font": {"size": 12, "name": "Times New Roman"}})
            else:
                ch = wb.add_chart({"type": "bar"})
                ch.add_series({
                    "categories": ["Bao cao CV NV Kho", first, c0, last, c0],
                    "values": ["Bao cao CV NV Kho", first, c1, last, c1],
                    "points": [{"fill": {"color": cl}} for cl in colors],
                    "data_labels": {"value": True, "num_format": "0.0%", "font": {"bold": True, "size": 12}},
                    "gap": 60,
                })
                ch.set_x_axis({"min": 0, "max": 1, "num_format": "0%", "major_gridlines": {"visible": True,
                               "line": {"color": "#e5e7eb"}}, "num_font": {"size": 12}})
                ch.set_y_axis({"reverse": True, "num_font": {"size": 12, "name": "Times New Roman"}})
                ch.set_legend({"none": True})
                ch.set_title({"name": "Tổng thời gian: %s giờ" % hours,
                              "name_font": {"size": 12, "bold": True, "color": "#6d28d9", "name": "Times New Roman"}})
            ch.set_chartarea({"border": {"none": True}})
            ch.set_size({"width": max(px(c0, c1) - 12, 160), "height": CH * 20})
            ws.insert_chart(chart_top, c0, ch, {"x_offset": 6, "y_offset": 3, "object_position": 1})
        r = tbl + 8
        # Tiêu đề bảng (2 hàng) — lặp lại ở đầu mỗi trang in
        h1 = r
        for i, (lbl, _w) in enumerate(cols):
            ws.merge_range(h1, i, h1 + 1, i, lbl, f_head)
        ws.merge_range(h1, n_main, h1, last_col, "QUẢN LÝ ĐÁNH GIÁ", f_head_eval)
        for j, (lbl, _w, fm) in enumerate(eval_cols):
            ws.write(h1 + 1, n_main + j, lbl, fm)
        ws.set_row(h1, 22)
        ws.set_row(h1 + 1, 34)
        r = h1 + 2
        ws.repeat_rows(h1, h1 + 1)

        # Dữ liệu theo nhóm hạng mục
        avgs = []
        for key in order:
            items = groups[key]
            g_hours = num(sum(float(x["hours"] or 0) for x in items))
            g_avg = num(sum(int(x.get("completion") or 0) for x in items) / len(items))
            avgs.append(g_avg)
            ws.merge_range(r, 0, r, last_col, "%s   —   %s việc · %s giờ · %% Hoàn thành CV TB hạng mục (AVERAGE): %s%%"
                           % (key or "Chưa có hạng mục", len(items), g_hours, g_avg), f_group)
            r += 1
            for i, it in enumerate(items, start=1):
                ev = it.get("eval") or {}
                vals = [(i, f_cell_c), (week_of(it["date"]), f_cell_c), (it["name"] or "", f_cell)]
                if whole:
                    vals.append((it.get("responsible") or "", f_cell))
                vals += [(day_label(it.get("date_start")) or "", f_cell_c), (fmt(it.get("deadline")), f_cell_c),
                         (num(it["hours"]), f_num), (states.get(it["state"], ""), f_state.get(it["state"], f_cell_c)),
                         (it.get("controller") or "", f_cell), (it.get("note") or "", f_cell)]
                p = ev.get("percent")
                vals += [((p / 100.0, pfmt(p, f_eval_pi, f_eval_p1)) if p is not None else ("", f_eval)),
                         (ev.get("note") or "", f_eval_l),
                         ("✓" if ev.get("rating") == "pass" else "", f_tick),
                         ("✓" if ev.get("rating") == "average" else "", f_tick),
                         ("✓" if ev.get("rating") == "fail" else "", f_tick),
                         ("✓" if ev.get("confirmed") else "", f_tick)]
                for c, (v, fm) in enumerate(vals):
                    ws.write(r, c, v, fm)
                r += 1
        if not rows:
            ws.merge_range(r, 0, r, last_col, "Không có công việc.", f_cell_c)
            r += 1
        month_avg = num(sum(avgs) / len(avgs)) if avgs else 0
        ws.merge_range(r, 0, r, last_col,
                       "Tổng %% hoàn thành công việc trong tháng (AVERAGE các hạng mục): %s%%" % month_avg, f_total)

        # Đánh giá của cấp quản lý + chữ ký (giống Báo cáo công việc tháng)
        f_bold = F(bold=True)
        f_dot = F(bottom=4)
        r += 2
        ws.write(r, 0, "Đánh giá của cấp quản lý/ trưởng bộ phận:", f_bold)
        for k in range(1, 4):
            ws.set_row(r + k, 20)
            for col in range(0, last_col + 1):
                ws.write_blank(r + k, col, None, f_dot)
        r += 5
        ws.write(r, 0, "Ngày............................", F())
        r += 1
        third = (last_col + 1) // 3
        ws.merge_range(r, 0, r, third - 1, "Người lập", F(bold=True, align="left"))
        ws.merge_range(r, third, r, 2 * third - 1, "Trưởng bộ phận", F(bold=True, align="center"))
        ws.merge_range(r, 2 * third, r, last_col, "Ban Giám đốc", F(bold=True, align="center"))
        r += 5
        ws.merge_range(r, 0, r, third - 1, data.get("me") or "", F(align="left"))

        # In: A4 dọc, lề 0,3 cm, vừa 1 trang chiều ngang, canh giữa, lề hẹp, đánh số trang
        ws.set_paper(9)
        ws.set_portrait()  # A4 dọc
        ws.fit_to_pages(1, 0)
        ws.center_horizontally()
        ws.set_margins(left=0.12, right=0.12, top=0.12, bottom=0.3)  # 0,3 cm (chừa chỗ chân trang)
        ws.set_footer('&L&"Times New Roman"&8Báo cáo CV NV Kho – Tháng %s/%s&R&"Times New Roman"&8Trang &P / &N' % (month, year), {"margin": 0.12})
        ws.print_area(0, 0, r, last_col)
        wb.close()

        team = (data.get("team_name") or "team").replace(" ", "_")
        name = "Bao_cao_CV_NV_Kho_%s_%02d-%s%s.xlsx" % (team, month, year, ("_Tuan%s" % week[0]) if week else "")
        return {"file_base64": base64.b64encode(buf.getvalue()).decode(), "filename": name}
