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
    kind = fields.Selection(KIND_SELECTION, string="Hạng mục", default="daily")
    name = fields.Char(string="Nội dung công việc")
    responsible = fields.Char(string="Người phụ trách")
    deadline = fields.Date(string="Deadline")
    date_done = fields.Date(string="Ngày hoàn thành")
    hours = fields.Float(string="Tổng TG (giờ)", digits=(10, 2))
    state = fields.Selection(STATE_SELECTION, string="Trạng thái", default="not_started")
    controller = fields.Char(string="Kiểm soát")
    note = fields.Char(string="Ghi chú")

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
    def _row(self, rec):
        return {
            "id": rec.id,
            "date": rec.date.isoformat() if rec.date else "",
            "kind": rec.kind or "",
            "name": rec.name or "",
            "responsible": rec.responsible or "",
            "deadline": rec.deadline.isoformat() if rec.deadline else "",
            "date_done": rec.date_done.isoformat() if rec.date_done else "",
            "hours": rec.hours or 0.0,
            "state": rec.state or "not_started",
            "controller": rec.controller or "",
            "note": rec.note or "",
        }

    @api.model
    def get_kho_sheet(self, year=None, month=None, team_id=None):
        self.env["daily.task.report.perm"].check("khocv", "view")
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        teams = self._teams()
        team = teams.filtered(lambda t: t.id == int(team_id or 0))[:1] or self.env["daily.task"]._kho_default_team(teams)
        domain = [("year", "=", year), ("month", "=", month), ("team_id", "=", team.id or False)]
        rows = self.sudo().search(domain)
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
            Line.search(scope + [("id", "in", [int(i) for i in deleted_ids])]).unlink()
        kinds = dict(KIND_SELECTION)
        states = dict(STATE_SELECTION)
        for seq, row in enumerate(rows or [], start=1):
            name = (row.get("name") or "").strip()
            d = self._clean_date(row.get("date"))
            if d and (d.year, d.month) != (year, month):
                raise ValidationError(
                    "Ngày %s không thuộc tháng %02d/%s (dòng «%s»)." % (d.strftime("%d/%m/%Y"), month, year, name)
                )
            vals = {
                "year": year,
                "month": month,
                "team_id": team.id or False,
                "sequence": seq,
                "date": d,
                "kind": row.get("kind") if row.get("kind") in kinds else "daily",
                "name": name,
                "responsible": (row.get("responsible") or "").strip(),
                "deadline": self._clean_date(row.get("deadline")),
                "date_done": self._clean_date(row.get("date_done")),
                "hours": max(0.0, float(row.get("hours") or 0)),
                "state": row.get("state") if row.get("state") in states else "not_started",
                "controller": (row.get("controller") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
            if not any([name, vals["responsible"], vals["note"], d]):
                continue  # dòng trống
            rid = int(row.get("id") or 0)
            rec = Line.search(scope + [("id", "=", rid)]) if rid else Line.browse()
            if rec:
                rec.write(vals)
            else:
                Line.create(vals)
        return self.get_kho_sheet(year=year, month=month, team_id=team.id or False)
