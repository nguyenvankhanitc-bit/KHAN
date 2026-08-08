# -*- coding: utf-8 -*-
"""Đảm bảo cột kanban_column tồn tại (lab/workspace thiếu cột → RPC crash)."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'daily_task'
           AND column_name = 'kanban_column'
        """
    )
    if cr.fetchone():
        return
    cr.execute(
        """
        ALTER TABLE daily_task
          ADD COLUMN kanban_column VARCHAR
        """
    )
