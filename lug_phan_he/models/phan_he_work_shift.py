# -*- coding: utf-8 -*-

from odoo import api, fields, models


SHIFT_GROUP_COLOR = {
    "full": 11,   # tím
    "sang": 10,   # xanh lá
    "chieu": 2,   # cam
    "gay": 3,     # vàng
    "off": 0,     # xám
}

LUNCH_FROM, LUNCH_TO = 11.5, 13.5
DINNER_FROM, DINNER_TO = 17.5, 18.5


def _hhmm(value):
    hours = int(value or 0)
    minutes = int(round(((value or 0) - hours) * 60))
    if minutes >= 60:
        hours += 1
        minutes = 0
    return f"{hours:02d}:{minutes:02d}"


class PhanHeWorkShift(models.Model):
    _name = "phan.he.work.shift"
    _description = "Ký hiệu công"
    _order = "sequence, code"
    _rec_names_search = ["name", "code"]

    name = fields.Char(string="Tên ca", required=True)
    code = fields.Char(string="Mã công", required=True)
    sequence = fields.Integer(default=10)
    shift_group = fields.Selection(
        [
            ("full", "FULL"),
            ("sang", "SÁNG"),
            ("chieu", "CHIỀU"),
            ("gay", "GÃY"),
            ("off", "OFF"),
        ],
        string="Nhóm ca",
        required=True,
        default="full",
        index=True,
    )
    color = fields.Integer(string="Màu hiển thị", default=11)
    state = fields.Selection(
        [
            ("applying", "Đang áp dụng"),
            ("stopped", "Ngừng áp dụng"),
        ],
        string="Trạng thái",
        default="applying",
        required=True,
    )
    active = fields.Boolean(default=True)

    time_in = fields.Float(string="Giờ vào")
    time_out = fields.Float(string="Giờ về")
    total_hours = fields.Float(
        string="Tổng hiện diện",
        compute="_compute_hours",
        store=True,
        readonly=True,
    )
    break_time = fields.Float(
        string="Thời gian trừ nghỉ",
        compute="_compute_hours",
        store=True,
        readonly=True,
    )
    actual_hours = fields.Float(
        string="Công thực tế",
        compute="_compute_hours",
        store=True,
        readonly=True,
    )
    work_coefficient = fields.Float(string="Hệ số tính công", default=1.0)

    has_lunch_break = fields.Boolean(string="Nghỉ ăn trưa")
    lunch_from = fields.Float(string="Ăn trưa từ", default=LUNCH_FROM)
    lunch_to = fields.Float(string="Ăn trưa đến", default=LUNCH_TO)
    lunch_hours = fields.Float(string="Trừ ăn trưa", compute="_compute_hours", store=True)

    has_dinner_break = fields.Boolean(string="Nghỉ ăn chiều")
    dinner_from = fields.Float(string="Ăn chiều từ", default=DINNER_FROM)
    dinner_to = fields.Float(string="Ăn chiều đến", default=DINNER_TO)
    dinner_hours = fields.Float(string="Trừ ăn chiều", compute="_compute_hours", store=True)

    apply_weekday = fields.Boolean(string="Ca ngày thường", default=True)
    apply_weekend = fields.Boolean(string="Ca cuối tuần", default=True)
    note = fields.Text(string="Ghi chú chi tiết")
    time_in_display = fields.Char(
        string="Giờ vào",
        compute="_compute_list_display",
    )
    time_out_display = fields.Char(
        string="Giờ về",
        compute="_compute_list_display",
    )
    break_summary = fields.Char(
        string="Ghi chú",
        compute="_compute_list_display",
    )

    _code_uniq = models.Constraint("unique(code)", "Mã công phải duy nhất.")

    @api.depends(
        "time_in",
        "time_out",
        "has_lunch_break",
        "lunch_from",
        "lunch_to",
        "has_dinner_break",
        "dinner_from",
        "dinner_to",
    )
    def _compute_hours(self):
        for rec in self:
            total = max(0.0, (rec.time_out or 0.0) - (rec.time_in or 0.0))
            lunch = max(0.0, (rec.lunch_to or 0.0) - (rec.lunch_from or 0.0)) if rec.has_lunch_break else 0.0
            dinner = max(0.0, (rec.dinner_to or 0.0) - (rec.dinner_from or 0.0)) if rec.has_dinner_break else 0.0
            rec.total_hours = total
            rec.lunch_hours = lunch
            rec.dinner_hours = dinner
            rec.break_time = lunch + dinner
            rec.actual_hours = max(0.0, total - rec.break_time)

    @api.depends(
        "shift_group",
        "time_in",
        "time_out",
        "has_lunch_break",
        "lunch_from",
        "lunch_to",
        "has_dinner_break",
        "dinner_from",
        "dinner_to",
        "note",
    )
    def _compute_list_display(self):
        for rec in self:
            is_off = rec.shift_group == "off"
            rec.time_in_display = "--:--" if is_off else _hhmm(rec.time_in)
            rec.time_out_display = "--:--" if is_off else _hhmm(rec.time_out)
            if is_off:
                rec.break_summary = rec.note or "Nghỉ tuần / Để trống"
            elif rec.has_lunch_break and rec.has_dinner_break:
                rec.break_summary = f"Ăn trưa {_hhmm(rec.lunch_from)}, Tối {_hhmm(rec.dinner_from)}"
            elif rec.has_lunch_break:
                rec.break_summary = f"Nghỉ ăn trưa: {_hhmm(rec.lunch_from)}-{_hhmm(rec.lunch_to)}"
            elif rec.has_dinner_break:
                rec.break_summary = f"Nghỉ ăn chiều: {_hhmm(rec.dinner_from)}-{_hhmm(rec.dinner_to)}"
            else:
                rec.break_summary = rec.note or ""

    @api.onchange("shift_group")
    def _onchange_shift_group(self):
        for rec in self:
            rec.color = SHIFT_GROUP_COLOR.get(rec.shift_group, 0)

    @api.onchange("state")
    def _onchange_state(self):
        for rec in self:
            rec.active = rec.state == "applying"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_state_active(vals)
            if not vals.get("color") and vals.get("shift_group"):
                vals["color"] = SHIFT_GROUP_COLOR.get(vals["shift_group"], 0)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_state_active(vals)
        return super().write(vals)

    @staticmethod
    def _sync_state_active(vals):
        if "state" in vals and "active" not in vals:
            vals["active"] = vals["state"] == "applying"
        elif "active" in vals and "state" not in vals:
            vals["state"] = "applying" if vals["active"] else "stopped"

    @api.depends("name", "code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.code or rec.name or ""

    @api.model
    def _post_migrate_form_layout(self):
        """Nạp trường form mới từ dữ liệu cũ (hour_from / shift_type / meal notes)."""
        cr = self.env.cr
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'phan_he_work_shift'
            """
        )
        cols = {row[0] for row in cr.fetchall()}
        if "hour_from" in cols and "time_in" in cols:
            cr.execute(
                """
                UPDATE phan_he_work_shift
                   SET time_in = COALESCE(NULLIF(time_in, 0), hour_from, 0),
                       time_out = COALESCE(NULLIF(time_out, 0), hour_to, 0)
                """
            )
        if "shift_type" in cols and "shift_group" in cols:
            cr.execute(
                """
                UPDATE phan_he_work_shift
                   SET shift_group = CASE shift_type
                        WHEN 'gay_sang' THEN 'gay'
                        WHEN 'gay_chieu' THEN 'gay'
                        WHEN 'full' THEN 'full'
                        WHEN 'sang' THEN 'sang'
                        WHEN 'chieu' THEN 'chieu'
                        WHEN 'off' THEN 'off'
                        ELSE COALESCE(shift_group, 'full')
                   END
                """
            )
        for rec in self.search([]):
            rec._apply_catalog_values()

    def _apply_catalog_values(self):
        self.ensure_one()
        code = (self.code or "").upper()
        group = self.shift_group
        if not group:
            if code.startswith("F") and code != "OFF":
                group = "full"
            elif code.startswith("S"):
                group = "sang"
            elif code.startswith("C"):
                group = "chieu"
            elif code.startswith("GS") or code.startswith("GC"):
                group = "gay"
            elif code == "OFF":
                group = "off"
            else:
                group = "full"

        has_lunch = bool(
            code == "F1"
            or code.startswith("GS")
            or (code.startswith("S") and not code.startswith("GS"))
        )
        has_dinner = bool(
            code == "F1"
            or code.startswith("GC")
            or (code.startswith("C") and not code.startswith("GC"))
        )
        if code == "OFF":
            has_lunch = has_dinner = False

        name = self._catalog_name(code, group, self.time_in, self.time_out)
        note = self.note
        if code == "F1" and not note:
            note = "Ca chuẩn áp dụng cho nhân sự chạy full ngày tại các cụm cửa hàng TTTM."

        self.write({
            "shift_group": group,
            "color": SHIFT_GROUP_COLOR.get(group, 0),
            "name": name,
            "has_lunch_break": has_lunch,
            "lunch_from": LUNCH_FROM,
            "lunch_to": LUNCH_TO,
            "has_dinner_break": has_dinner,
            "dinner_from": DINNER_FROM,
            "dinner_to": DINNER_TO,
            "work_coefficient": self.work_coefficient or 1.0,
            "apply_weekday": True,
            "apply_weekend": True,
            "state": "applying" if self.active else "stopped",
            "note": note or False,
        })

    @staticmethod
    def _catalog_name(code, group, time_in, time_out):
        if code == "OFF" or group == "off":
            return "Nghỉ (OFF)"
        if code.startswith("GS"):
            prefix = "Ca Gãy sáng"
        elif code.startswith("GC"):
            prefix = "Ca Gãy chiều"
        else:
            prefix = {
                "full": "Ca Full",
                "sang": "Ca Sáng",
                "chieu": "Ca Chiều",
                "gay": "Ca Gãy",
            }.get(group, "Ca")
        return f"{prefix} {_hhmm(time_in)} - {_hhmm(time_out)}"
