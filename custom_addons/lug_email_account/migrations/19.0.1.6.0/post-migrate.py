# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

DEFAULT_STATUSES = [
    ("active", "Đang sử dụng", 10, "success", False),
    ("lock", "Tạm khóa", 20, "warning", False),
    ("cancel", "Hủy", 30, "danger", True),
]


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Status = env["lug.email.account.status"]
    Account = env["lug.email.account"]

    code_to_id = {}
    for code, name, sequence, badge_style, is_closed in DEFAULT_STATUSES:
        status = Status.search([("code", "=", code)], limit=1)
        if not status:
            status = Status.create({
                "name": name,
                "code": code,
                "sequence": sequence,
                "badge_style": badge_style,
                "is_closed": is_closed,
            })
        code_to_id[code] = status.id

    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'lug_email_account'
          AND column_name = 'state'
    """)
    if not cr.fetchone():
        return

    _logger.info("Post-migrating lug.email.account state -> status_id...")
    for code, status_id in code_to_id.items():
        cr.execute(
            """
            UPDATE lug_email_account
            SET status_id = %s
            WHERE state = %s AND (status_id IS NULL)
            """,
            (status_id, code),
        )

    Account.search([("status_id", "=", False)]).write({
        "status_id": code_to_id["active"],
    })
