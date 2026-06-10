import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    pending = env["hr.leave"].search(
        [
            ("state", "in", ("confirm", "validate1")),
            ("validation_type", "=", "employee_hr_responsibles"),
        ]
    )
    if not pending:
        return
    pending._ensure_responsible_approval_lines()
    pending._refresh_responsible_actionable_users()
    _logger.info(
        "time_off_responsible_approval: repaired actionable users for %s pending leave(s)",
        len(pending),
    )
