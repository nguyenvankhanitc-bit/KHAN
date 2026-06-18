# -*- coding: utf-8 -*-

from odoo import api, models

from ..constants import SKIP_HANDOVER_CONSTRAINTS_ON_LEAVE_SYNC_CTX


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    def _with_handover_skip_constraints_on_sync(self):
        return self.with_context(**{SKIP_HANDOVER_CONSTRAINTS_ON_LEAVE_SYNC_CTX: True})

    @api.model_create_multi
    def create(self, vals_list):
        return super(
            ResourceCalendarLeaves, self._with_handover_skip_constraints_on_sync()
        ).create(vals_list)

    def write(self, vals):
        return super(
            ResourceCalendarLeaves, self._with_handover_skip_constraints_on_sync()
        ).write(vals)

    def unlink(self):
        return super(
            ResourceCalendarLeaves, self._with_handover_skip_constraints_on_sync()
        ).unlink()
