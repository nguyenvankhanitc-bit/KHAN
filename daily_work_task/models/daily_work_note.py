# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyWorkNote(models.Model):
    _name = "daily.work.note"
    _description = "Ghi chú công việc"
    _order = "note_date desc, id desc"

    name = fields.Text(string="Nội dung", required=True)
    note_date = fields.Date(
        string="Ngày",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Người sở hữu",
        default=lambda self: self.env.user,
        required=True,
        index=True,
        ondelete="cascade",
    )

    @api.model
    def get_work_note_data(self, search=None):
        """Danh sách ghi chú của user đang đăng nhập."""
        Note = self.sudo()
        domain = [("user_id", "=", self.env.user.id)]
        q = (search or "").strip()
        if q:
            domain.append(("name", "ilike", q))
        records = Note.search(domain, order="note_date desc, id desc")
        rows = []
        for idx, rec in enumerate(records, start=1):
            rows.append(
                {
                    "id": rec.id,
                    "stt": idx,
                    "name": rec.name or "",
                    "note_date": rec.note_date.isoformat() if rec.note_date else "",
                    "note_date_display": rec.note_date.strftime("%d/%m/%Y")
                    if rec.note_date
                    else "—",
                }
            )
        return {
            "user_name": self.env.user.name or "",
            "rows": rows,
            "total": len(rows),
        }

    @api.model
    def save_work_note(self, vals):
        """Tạo / cập nhật ghi chú (chỉ của mình)."""
        vals = dict(vals or {})
        rid = int(vals.pop("id", 0) or 0)
        content = (vals.get("name") or "").strip()
        note_date = vals.get("note_date") or fields.Date.context_today(self)
        if not content:
            raise ValidationError("Vui lòng nhập nội dung ghi chú.")
        clean = {
            "name": content,
            "note_date": note_date,
            "user_id": self.env.user.id,
        }
        Note = self.sudo()
        if rid:
            rec = Note.browse(rid).exists()
            if not rec or rec.user_id.id != self.env.user.id:
                raise ValidationError(
                    "Không tìm thấy ghi chú hoặc bạn không có quyền sửa."
                )
            rec.write(clean)
            return rec.id
        return Note.create(clean).id

    def delete_work_note(self):
        for rec in self.sudo():
            if rec.user_id != self.env.user and not self.env.user.has_group(
                "daily_work_task.group_daily_work_manager"
            ):
                raise ValidationError("Bạn chỉ được xóa ghi chú của chính mình.")
        self.sudo().unlink()
        return True

    @api.model
    def get_reminder_rows_for_user(self, user_id, today=None, upcoming_days=7):
        """
        Ghi chú theo ngày → hàng nhắc việc (quá hạn / sắp tới trong N ngày).
        Dùng chung cho chuông Nhắc việc trên Báo cáo cá nhân.
        - Quá hạn: note_date trong 7 ngày trước hôm nay
        - Sắp tới: hôm nay → +upcoming_days
        """
        from datetime import timedelta

        if not user_id:
            return [], []
        today = today or fields.Date.context_today(self)
        days = int(upcoming_days or 7)
        upcoming_end = today + timedelta(days=days)
        overdue_start = today - timedelta(days=days)
        notes = self.sudo().search(
            [
                ("user_id", "=", int(user_id)),
                ("note_date", ">=", overdue_start),
                ("note_date", "<=", upcoming_end),
            ],
            order="note_date asc, id asc",
        )
        overdue_rows = []
        upcoming_rows = []
        for note in notes:
            d = note.note_date
            if not d:
                continue
            overdue_days = max(0, (today - d).days) if d < today else 0
            row = {
                "id": note.id,
                "source": "work_note",
                "name": note.name or "",
                "deadline": d.isoformat(),
                "deadline_display": d.strftime("%d/%m/%Y"),
                "priority": "medium",
                "priority_label": "Ghi chú",
                "completion_percent": 0,
                "state": "work_note",
                "state_label": "Ghi chú",
                "duration_hours": 0,
                "duration_hours_display": "0",
                "note": "",
                "is_active_overdue": d < today,
                "is_overdue": d < today,
                "overdue_days": overdue_days,
                "overdue_label": ("Trễ hạn %s ngày" % overdue_days)
                if overdue_days
                else "",
            }
            if d < today:
                overdue_rows.append(row)
            else:
                upcoming_rows.append(row)
        return overdue_rows, upcoming_rows
