# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LinkqShiftScheduleDtt(models.Model):
    _name = "linkq.shift.schedule.dtt"
    _description = "Lịch Miền ĐTT"
    _order = "sequence, store_name"
    _rec_name = "store_name"

    sequence = fields.Integer(string="STT", default=10)
    store_name = fields.Char(
        string="Cửa hàng / Mã quầy",
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        "linkq.shift.schedule.dtt.line",
        "schedule_id",
        string="Khung giờ áp dụng",
    )
    note = fields.Text(string="Ghi chú")
    line_count = fields.Integer(string="Số khung giờ", compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)


class LinkqShiftScheduleDttLine(models.Model):
    _name = "linkq.shift.schedule.dtt.line"
    _description = "Khung giờ Lịch Miền ĐTT"
    _order = "schedule_id, sequence, id"

    sequence = fields.Integer(string="STT", default=10)
    schedule_id = fields.Many2one(
        "linkq.shift.schedule.dtt",
        string="Cửa hàng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    store_name = fields.Char(
        related="schedule_id.store_name",
        store=True,
        string="Cửa hàng / Mã quầy",
    )
    apply_days = fields.Char(
        string="Ngày áp dụng",
        required=True,
        help="Ví dụ: T2 - T6, T7, CN, LỄ, FULL...",
    )
    shift_full = fields.Char(string="Ca Full")
    shift_split_morning = fields.Char(string="Ca Gãy Sáng")
    shift_split_afternoon = fields.Char(string="Ca Gãy Chiều")
    shift_morning = fields.Char(string="Ca Sáng")
    shift_afternoon = fields.Char(string="Ca Chiều")
    note = fields.Char(string="Ghi chú")

    @api.depends("store_name", "apply_days")
    def _compute_display_name(self):
        for rec in self:
            store = rec.store_name or ""
            if store and rec.apply_days:
                rec.display_name = f"{store} · {rec.apply_days}"
            else:
                rec.display_name = store or rec.apply_days or ""

    def action_save_and_close(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "lug_phan_he.action_linkq_shift_schedule_dtt"
        )
