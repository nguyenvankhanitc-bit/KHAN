# -*- coding: utf-8 -*-

from odoo import api, models

from ..constants import PUBLIC_HOLIDAY_LEAVE_SYNC_CONTEXT


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    def _with_public_holiday_leave_sync_context(self):
        return self.with_context(**PUBLIC_HOLIDAY_LEAVE_SYNC_CONTEXT)

    @api.model_create_multi
    def create(self, vals_list):
        return super(
            ResourceCalendarLeaves, self._with_public_holiday_leave_sync_context()
        ).create(vals_list)

    def write(self, vals):
        return super(
            ResourceCalendarLeaves, self._with_public_holiday_leave_sync_context()
        ).write(vals)

    def unlink(self):
        return super(
            ResourceCalendarLeaves, self._with_public_holiday_leave_sync_context()
        ).unlink()
