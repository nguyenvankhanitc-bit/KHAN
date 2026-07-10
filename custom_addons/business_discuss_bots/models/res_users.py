# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging

from odoo import api, models
from odoo.tools import file_open

from ..hooks import ensure_ctkm_discuss_bot

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _business_discuss_sync_bot_profiles(self):
        bot_sources = {
            "business_discuss_bots.user_bot_handover": "business_discuss_bots/static/src/img/bot_handover.png",
            "business_discuss_bots.user_bot_approval": "business_discuss_bots/static/src/img/bot_approval.png",
            "business_discuss_bots.user_bot_gate_ticket": "business_discuss_bots/static/src/img/bot_gate_ticket.png",
            "business_discuss_bots.user_bot_ctkm": "business_discuss_bots/static/src/img/bot_ctkm.png",
        }
        for user_xmlid, image_path in bot_sources.items():
            bot_user = self.env.ref(user_xmlid, raise_if_not_found=False)
            if not bot_user or not bot_user.partner_id:
                continue
            try:
                with file_open(image_path, "rb") as image_file:
                    image_b64 = base64.b64encode(image_file.read())
                bot_user.partner_id.sudo().write({"image_1920": image_b64})
            except Exception:
                _logger.exception("business_discuss_bots: failed to sync avatar for %s", user_xmlid)

    @api.model
    def _business_discuss_bot_users(self):
        xmlids = [
            "business_discuss_bots.user_bot_handover",
            "business_discuss_bots.user_bot_approval",
            "business_discuss_bots.user_bot_gate_ticket",
            "business_discuss_bots.user_bot_ctkm",
        ]
        bot_ids = []
        for xmlid in xmlids:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                bot_ids.append(record.id)
        return self.browse(bot_ids).filtered(lambda u: u.active and u.partner_id)

    def _business_discuss_ensure_dm_with_bots(self):
        bot_users = self._business_discuss_bot_users()
        if not bot_users:
            return
        channel_model = self.env["discuss.channel"].sudo()
        for user in self.sudo().filtered(lambda u: u.active and not u.share and u.partner_id):
            for bot_user in bot_users:
                if user.id == bot_user.id:
                    continue
                try:
                    channel_model.with_user(user)._get_or_create_chat([bot_user.partner_id.id], pin=True)
                except Exception:
                    _logger.exception(
                        "business_discuss_bots: failed to ensure DM user_id=%s bot_user_id=%s",
                        user.id,
                        bot_user.id,
                    )

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if self.env.context.get("business_discuss_skip_bot_bootstrap"):
            return users
        self._business_discuss_sync_bot_profiles()
        users._business_discuss_ensure_dm_with_bots()
        return users

    @api.model
    def cron_backfill_business_discuss_bots(self):
        ensure_ctkm_discuss_bot(self.env)
        self._business_discuss_sync_bot_profiles()
        users = self.search([("share", "=", False), ("active", "=", True)])
        users._business_discuss_ensure_dm_with_bots()
