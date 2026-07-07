# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'lug_email_account'
          AND column_name = 'employee_name'
    """)
    if cr.fetchone():
        return

    _logger.info("Pre-migrating lug.email.account: add employee_name and department text...")

    cr.execute("""
        ALTER TABLE lug_email_account
        ADD COLUMN IF NOT EXISTS employee_name VARCHAR,
        ADD COLUMN IF NOT EXISTS department VARCHAR
    """)

    cr.execute("""
        UPDATE lug_email_account ea
        SET employee_name = he.name
        FROM hr_employee he
        WHERE ea.employee_id = he.id
          AND (ea.employee_name IS NULL OR ea.employee_name = '')
    """)

    cr.execute("""
        UPDATE lug_email_account ea
        SET department = hd.name
        FROM hr_department hd
        WHERE ea.department_id = hd.id
          AND (ea.department IS NULL OR ea.department = '')
    """)

    cr.execute("""
        UPDATE lug_email_account
        SET employee_name = '/'
        WHERE employee_name IS NULL OR employee_name = ''
    """)

    cr.execute("""
        UPDATE lug_email_account
        SET department = '/'
        WHERE department IS NULL OR department = ''
    """)
