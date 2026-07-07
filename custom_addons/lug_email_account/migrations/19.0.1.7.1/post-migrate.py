# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE lug_email_account
        SET function_name = '-',
            purpose = CASE
                WHEN purpose = employee_name THEN '-'
                ELSE purpose
            END
        WHERE function_name = employee_name
          AND COALESCE(function_name, '') NOT IN ('', '-')
    """)
    _logger.info(
        "Reset %s email account rows where function_name duplicated employee_name",
        cr.rowcount,
    )
