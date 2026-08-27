# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LinkqShiftScheduleNorth(models.Model):
    _name = "linkq.shift.schedule.north"
    _description = "Lịch Miền Bắc"
    _order = "sequence, store_name, apply_days"
    _rec_name = "store_name"

    sequence = fields.Integer(string="STT", default=10)
    store_name = fields.Char(
        string="Cửa hàng / Mã quầy",
        required=True,
        index=True,
    )
    apply_days = fields.Char(
        string="Ngày áp dụng",
        required=True,
        help="Ví dụ: T2 - T5, T6, T7, CN, Lễ, Cả tuần",
    )
    shift_full = fields.Char(string="Ca Full")
    shift_split_morning = fields.Char(string="Ca Gãy Sáng")
    shift_split_afternoon = fields.Char(string="Ca Gãy Chiều")
    shift_morning = fields.Char(string="Ca Sáng")
    shift_afternoon = fields.Char(string="Ca Chiều")
    note = fields.Text(string="Ghi chú vận hành")

    @api.depends("store_name", "apply_days")
    def _compute_display_name(self):
        for rec in self:
            store = (rec.store_name or "").replace("\n", " / ")
            if store and rec.apply_days:
                rec.display_name = f"{store} · {rec.apply_days}"
            else:
                rec.display_name = store or rec.apply_days or ""
