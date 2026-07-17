# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Backfill Ngày giao việc cho việc cũ."""
    cr.execute(
        """
        UPDATE daily_task
           SET assign_date = COALESCE(assign_date, create_date::date, CURRENT_DATE)
         WHERE assign_date IS NULL
        """
    )
