# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'lug_email_account'
          AND column_name = 'date_created'
    """)
    row = cr.fetchone()
    if not row or row[0] != "date":
        return

    _logger.info("Converting lug.email.account.date_created from date to text...")
    cr.execute("""
        ALTER TABLE lug_email_account
        ADD COLUMN IF NOT EXISTS date_created_text VARCHAR
    """)
    cr.execute("""
        UPDATE lug_email_account
        SET date_created_text = to_char(date_created, 'DD/MM/YYYY')
        WHERE date_created IS NOT NULL
    """)
    cr.execute("ALTER TABLE lug_email_account DROP COLUMN date_created")
    cr.execute("""
        ALTER TABLE lug_email_account
        RENAME COLUMN date_created_text TO date_created
    """)
