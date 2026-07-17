# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Backfill Người giao việc từ create_uid cho việc cũ."""
    cr.execute(
        """
        UPDATE daily_task
           SET assigned_by_id = create_uid
         WHERE assigned_by_id IS NULL
           AND create_uid IS NOT NULL
        """
    )
