# -*- coding: utf-8 -*-
"""Renumber STT (sequence) on special employee lines after fixing default-all-1 create behavior."""

import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not sql.table_exists(cr, "hr_leave_type_special_employee_line"):
        return
    cr.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY leave_type_id
                       ORDER BY COALESCE(sequence, 999999), id
                   ) AS rn
            FROM hr_leave_type_special_employee_line
        )
        UPDATE hr_leave_type_special_employee_line AS l
        SET sequence = r.rn
        FROM ranked AS r
        WHERE l.id = r.id
          AND COALESCE(l.sequence, 0) IS DISTINCT FROM r.rn
        """
    )
    _logger.info("time_off_extra_approval: renumbered special employee line STT (sequence) where needed.")
