# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging

from odoo.tools import file_open

_logger = logging.getLogger(__name__)

_CTKM_BOT = {
    "partner_xmlid": "partner_bot_ctkm",
    "user_xmlid": "user_bot_ctkm",
    "name": "OdooBot CTKM",
    "login": "odoo.bot.ctkm",
    "email": "odoo.bot.ctkm@example.com",
    "image_path": "business_discuss_bots/static/src/img/bot_ctkm.png",
}


def _partner_table_has_autopost_bills(cr):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'res_partner' AND column_name = 'autopost_bills'"
    )
    return bool(cr.fetchone())


def _create_ctkm_partner(env, partner_vals):
    Partner = env["res.partner"].sudo()
    image_b64 = partner_vals.pop("image_1920", None)
    if "autopost_bills" in Partner._fields:
        partner_vals = dict(partner_vals, autopost_bills="ask")
        partner = Partner.create(partner_vals)
        if image_b64:
            partner.write({"image_1920": image_b64})
        return partner
    if not _partner_table_has_autopost_bills(env.cr):
        partner = Partner.create(partner_vals)
        if image_b64:
            partner.write({"image_1920": image_b64})
        return partner

    env.cr.execute(
        """
        INSERT INTO res_partner (
            name, email, active, is_company, type, lang, autopost_bills,
            create_uid, write_uid, create_date, write_date
        ) VALUES (
            %s, %s, true, false, 'contact', 'en_US', 'ask',
            %s, %s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
        ) RETURNING id
        """,
        (partner_vals["name"], partner_vals["email"], env.uid, env.uid),
    )
    partner_id = env.cr.fetchone()[0]
    partner = Partner.browse(partner_id)
    if image_b64:
        try:
            partner.write({"image_1920": image_b64})
        except Exception:
            _logger.exception("business_discuss_bots: failed to set CTKM avatar on partner_id=%s", partner_id)
    return partner


def ensure_ctkm_discuss_bot(env):
    """Create OdooBot CTKM via Python (avoids account-only res.partner fields in XML)."""
    module = "business_discuss_bots"
    user_xmlid = f"{module}.{_CTKM_BOT['user_xmlid']}"
    partner_xmlid = f"{module}.{_CTKM_BOT['partner_xmlid']}"
    existing = env.ref(user_xmlid, raise_if_not_found=False)
    if existing:
        return existing

    Users = env["res.users"].sudo().with_context(active_test=False)
    user = Users.search([("login", "=", _CTKM_BOT["login"])], limit=1)
    if user:
        IrModelData = env["ir.model.data"].sudo()
        if not IrModelData.search([("module", "=", module), ("name", "=", _CTKM_BOT["user_xmlid"])], limit=1):
            IrModelData.create(
                {
                    "module": module,
                    "name": _CTKM_BOT["user_xmlid"],
                    "model": "res.users",
                    "res_id": user.id,
                    "noupdate": True,
                }
            )
        if user.partner_id and not IrModelData.search(
            [("module", "=", module), ("name", "=", _CTKM_BOT["partner_xmlid"])], limit=1
        ):
            IrModelData.create(
                {
                    "module": module,
                    "name": _CTKM_BOT["partner_xmlid"],
                    "model": "res.partner",
                    "res_id": user.partner_id.id,
                    "noupdate": True,
                }
            )
        if not user.active:
            user.write({"active": True})
        return user

    partner_vals = {
        "name": _CTKM_BOT["name"],
        "email": _CTKM_BOT["email"],
        "company_type": "person",
    }

    try:
        with file_open(_CTKM_BOT["image_path"], "rb") as image_file:
            partner_vals["image_1920"] = base64.b64encode(image_file.read())
    except Exception:
        _logger.exception("business_discuss_bots: failed to load avatar for %s", user_xmlid)

    partner = _create_ctkm_partner(env, partner_vals)
    env["ir.model.data"].sudo().create(
        {
            "module": module,
            "name": _CTKM_BOT["partner_xmlid"],
            "model": "res.partner",
            "res_id": partner.id,
            "noupdate": True,
        }
    )
    env.flush_all()
    user = (
        env["res.users"]
        .sudo()
        .with_context(business_discuss_skip_bot_bootstrap=True)
        .create(
            {
                "name": _CTKM_BOT["name"],
                "login": _CTKM_BOT["login"],
                "partner_id": partner.id,
                "group_ids": [(6, 0, [env.ref("base.group_user").id])],
            }
        )
    )
    env["ir.model.data"].sudo().create(
        {
            "module": module,
            "name": _CTKM_BOT["user_xmlid"],
            "model": "res.users",
            "res_id": user.id,
            "noupdate": True,
        }
    )
    _logger.info("business_discuss_bots: created %s (user_id=%s)", user_xmlid, user.id)
    return user


def post_init_hook(env):
    ensure_ctkm_discuss_bot(env)
    bot_users = env["res.users"].browse(
        [
            env.ref("business_discuss_bots.user_bot_handover").id,
            env.ref("business_discuss_bots.user_bot_approval").id,
            env.ref("business_discuss_bots.user_bot_gate_ticket").id,
            env.ref("business_discuss_bots.user_bot_ctkm").id,
        ]
    ).filtered(lambda u: u.partner_id and u.active)
    if not bot_users:
        return

    internal_users = env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)])
    for user in internal_users:
        if not user.partner_id:
            continue
        for bot_user in bot_users:
            if user.id == bot_user.id:
                continue
            try:
                env["discuss.channel"].with_user(user).sudo()._get_or_create_chat([bot_user.partner_id.id], pin=True)
            except Exception:
                _logger.exception(
                    "business_discuss_bots: failed to initialize chat user_id=%s bot_user_id=%s",
                    user.id,
                    bot_user.id,
                )
