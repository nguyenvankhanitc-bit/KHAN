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
            # Quản lý xem cả Team → hiện tên người phụ trách dưới nội dung công việc
            "whole_team": self._sees_whole_team(team),
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
        """Xuất Báo cáo CV NV Kho ra Excel: khổ A4 ngang, vừa 1 trang chiều ngang, canh lề, lặp tiêu đề."""
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
        linked = [r for r in rows if r.get("linked")]
        eff = num(sum(int((r.get("eval") or {}).get("percent") or 0) for r in linked) / len(linked)) if linked else 0

        # Group theo hạng mục
        groups = {}
        for r in rows:
            key = r.get("category") or ""
            groups.setdefault(key, []).append(r)
        order = sorted(groups, key=lambda k: (k == "", k.casefold()))

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Bao cao CV NV Kho")
        F = lambda **kw: wb.add_format(dict({"font_name": "Times New Roman", "font_size": 10, "valign": "vcenter"}, **kw))
        f_title = F(bold=True, font_size=16, align="center")
        f_center = F(align="center")
        f_sub = F(align="center", italic=True, font_color="#475569")
        f_kpi_lbl = F(bold=True, align="center", border=1, bg_color="#e2e8f0", text_wrap=True, font_size=9)
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

        # Cột (độ rộng ký tự) — tổng vừa A4 ngang khi co 1 trang chiều ngang
        cols = [("STT", 5), ("Tuần", 7), ("Nội dung công việc", 46)]
        if whole:
            cols.append(("Người phụ trách", 18))
        cols += [("Ngày bắt đầu", 13), ("Deadline", 11), ("Tổng TG (giờ)", 8), ("Trạng thái", 13),
                 ("Kiểm soát", 16), ("Ghi chú", 20)]
        n_main = len(cols)
        eval_cols = [("% Hoàn thành", 9, f_head_eval), ("Ghi chú", 20, f_head_eval), ("Đạt", 6, f_head_pass),
                     ("Trung bình", 8, f_head_avg), ("Không đạt", 8, f_head_fail), ("Xác nhận QL", 9, f_head_eval)]
        last_col = n_main + len(eval_cols) - 1
        for i, (_l, w) in enumerate(cols):
            ws.set_column(i, i, w)
        for j, (_l, w, _f) in enumerate(eval_cols):
            ws.set_column(n_main + j, n_main + j, w)

        # Đầu báo cáo (giống Báo cáo cá nhân)
        r = 0
        ws.merge_range(r, 0, r, last_col, "BÁO CÁO CÔNG VIỆC KHO", f_title)
        ws.set_row(r, 26)
        r += 1
        who = ("Team: %s" % data.get("team_name")) if whole else ("Họ và tên: %s" % (data.get("me") or ""))
        ws.merge_range(r, 0, r, last_col, who, F(align="center", bold=True, font_size=11))
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

        # 6 ô chỉ số
        kpis = [("TỔNG CÔNG VIỆC", str(total)), ("HOÀN THÀNH", "%s (%s%%)" % (cnt("done"), pct(cnt("done")))),
                ("ĐANG THỰC HIỆN", "%s (%s%%)" % (cnt("in_progress"), pct(cnt("in_progress")))),
                ("CHƯA BẮT ĐẦU", "%s (%s%%)" % (cnt("not_started"), pct(cnt("not_started")))),
                ("TỔNG THỜI GIAN (giờ)", str(hours)), ("HIỆU SUẤT (QL đánh giá)", "%s%%" % eff)]
        # Chia 6 ô theo độ rộng thật của cột (cột STT / Tuần hẹp) → các ô rộng gần bằng nhau
        widths = [w for _l, w in cols] + [w for _l, w, _f in eval_cols]
        target = sum(widths) / float(len(kpis))
        c0 = 0
        for i, (lbl, val) in enumerate(kpis):
            if i == len(kpis) - 1:
                c1 = last_col
            else:
                c1, acc = c0, widths[c0]
                remain_blocks = len(kpis) - i - 1
                while c1 + 1 <= last_col - remain_blocks and acc + widths[c1 + 1] / 2.0 <= target:
                    c1 += 1
                    acc += widths[c1]
            if c1 > c0:
                ws.merge_range(r, c0, r, c1, lbl, f_kpi_lbl)
                ws.merge_range(r + 1, c0, r + 1, c1, val, f_kpi_val)
            else:
                ws.write(r, c0, lbl, f_kpi_lbl)
                ws.write(r + 1, c0, val, f_kpi_val)
            c0 = c1 + 1
        ws.set_row(r, 18)
        ws.set_row(r + 1, 22)
        r += 3

        # Tiêu đề bảng (2 hàng) — lặp lại ở đầu mỗi trang in
        h1 = r
        for i, (lbl, _w) in enumerate(cols):
            ws.merge_range(h1, i, h1 + 1, i, lbl, f_head)
        ws.merge_range(h1, n_main, h1, last_col, "QUẢN LÝ ĐÁNH GIÁ", f_head_eval)
        for j, (lbl, _w, fm) in enumerate(eval_cols):
            ws.write(h1 + 1, n_main + j, lbl, fm)
        ws.set_row(h1, 20)
        ws.set_row(h1 + 1, 28)
        r = h1 + 2
        ws.repeat_rows(h1, h1 + 1)
        ws.freeze_panes(r, 0)

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
                         (num(it["hours"]), f_cell_c), (states.get(it["state"], ""), f_state.get(it["state"], f_cell_c)),
                         (it.get("controller") or "", f_cell), (it.get("note") or "", f_cell)]
                p = ev.get("percent")
                vals += [("%s%%" % p if p is not None else "", f_eval), (ev.get("note") or "", f_eval_l),
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

        # In: A4 ngang, vừa 1 trang chiều ngang, canh giữa, lề hẹp, đánh số trang
        ws.set_paper(9)
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.center_horizontally()
        ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.55)
        ws.set_footer('&L&"Times New Roman"&8Báo cáo CV NV Kho – Tháng %s/%s&R&"Times New Roman"&8Trang &P / &N' % (month, year))
        ws.print_area(0, 0, r, last_col)
        wb.close()

        team = (data.get("team_name") or "team").replace(" ", "_")
        name = "Bao_cao_CV_NV_Kho_%s_%02d-%s%s.xlsx" % (team, month, year, ("_Tuan%s" % week[0]) if week else "")
        return {"file_base64": base64.b64encode(buf.getvalue()).decode(), "filename": name}
