# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    lug_notify_lead_days = fields.Integer(
        string="Thời gian thông báo (ngày)",
        config_parameter="lug_project.notify_lead_days",
        default=1,
        help="Số ngày thông báo trước hạn công việc cho người phụ trách, giám sát và nhân sự.",
    )
