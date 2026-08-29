# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LinkqStoreSchedule(models.Model):
    _name = "linkq.store.schedule"
    _description = "Lịch cửa hàng"
    _order = "sequence, name"
    _inherit = ["lug.menu.access.mixin"]

    sequence = fields.Integer(string="STT", default=10)
    name = fields.Char(string="Cửa hàng / Mã quầy", required=True, index=True)
    code = fields.Char(string="Mã cửa hàng")
    region = fields.Selection(
        [
            ("north", "Miền Bắc"),
            ("south", "Miền Nam"),
            ("dtt", "Miền ĐTT"),
        ],
        string="Khu vực",
        required=True,
        index=True,
        default="north",
    )
    line_ids = fields.One2many(
        "linkq.store.schedule.line",
        "schedule_id",
        string="Khung giờ áp dụng",
    )
    note = fields.Text(string="Ghi chú")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        region = self.env.context.get("default_region")
        if region:
            res["region"] = region
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") and vals.get("name"):
                vals["code"] = (vals["name"] or "").split("\n")[0].strip()
        return super().create(vals_list)


class LinkqStoreScheduleLine(models.Model):
    _name = "linkq.store.schedule.line"
    _description = "Khung giờ áp dụng cửa hàng"
    _order = "schedule_id, sequence, id"
    _inherit = ["lug.menu.access.mixin"]

    sequence = fields.Integer(string="STT", default=10)
    schedule_id = fields.Many2one(
        "linkq.store.schedule",
        string="Cửa hàng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    store_name = fields.Char(related="schedule_id.name", store=True)
    region = fields.Selection(related="schedule_id.region", store=True, index=True)
    apply_days = fields.Char(string="Ngày áp dụng", required=True)
    shift_full_id = fields.Many2one(
        "linkq.shift.code",
        string="Ca FULL",
        domain="[('shift_group', 'in', ['FULL', 'OFF'])]",
    )
    shift_split_morning_id = fields.Many2one(
        "linkq.shift.code",
        string="Ca GÃY SÁNG",
        domain="[('shift_group', 'in', ['GAY_SANG', 'GAY', 'OFF'])]",
    )
    shift_split_afternoon_id = fields.Many2one(
        "linkq.shift.code",
        string="Ca GÃY CHIỀU",
        domain="[('shift_group', 'in', ['GAY_CHIEU', 'GAY', 'OFF'])]",
    )
    shift_morning_id = fields.Many2one(
        "linkq.shift.code",
        string="Ca SÁNG",
        domain="[('shift_group', 'in', ['SANG', 'OFF'])]",
    )
    shift_afternoon_id = fields.Many2one(
        "linkq.shift.code",
        string="Ca CHIỀU",
        domain="[('shift_group', 'in', ['CHIEU', 'OFF'])]",
    )
    note = fields.Char(string="Ghi chú vận hành")

    def action_save_and_close(self):
        region = (self[:1].region or self.env.context.get("default_region") or "north")
        xmlid = {
            "north": "lug_phan_he.action_linkq_store_schedule_north",
            "south": "lug_phan_he.action_linkq_store_schedule_south",
            "dtt": "lug_phan_he.action_linkq_store_schedule_dtt",
        }.get(region, "lug_phan_he.action_linkq_store_schedule_north")
        return self.env["ir.actions.act_window"]._for_xml_id(xmlid)
