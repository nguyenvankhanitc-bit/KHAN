# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT id, department
        FROM lug_email_account
        WHERE department_id IS NULL
          AND COALESCE(department, '') NOT IN ('', 'Chưa phân loại')
    """)
    rows = cr.fetchall()
    if not rows:
        return

    updated = 0
    for account_id, department_name in rows:
        cr.execute(
            """
            SELECT id
            FROM hr_department
            WHERE name ILIKE %s
            ORDER BY id
            LIMIT 1
            """,
            (department_name,),
        )
        dept = cr.fetchone()
        if dept:
            cr.execute(
                """
                UPDATE lug_email_account
                SET department_id = %s
                WHERE id = %s
                """,
                (dept[0], account_id),
            )
            updated += 1

    _logger.info(
        "Linked %s email account rows to hr.department from text department",
        updated,
    )
