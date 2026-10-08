# -*- coding: utf-8 -*-
"""Drop Char column `team` trước khi ORM tạo Many2one `team_id`."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name = 'daily_task_work_group'
           AND column_name = 'team'
        """
    )
    row = cr.fetchone()
    if row and row[0] in ("character varying", "text", "varchar"):
        cr.execute("DROP INDEX IF EXISTS daily_task_work_group__team_index")
        cr.execute("ALTER TABLE daily_task_work_group DROP COLUMN team")
