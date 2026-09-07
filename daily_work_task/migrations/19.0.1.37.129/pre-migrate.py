# -*- coding: utf-8 -*-
"""Add date_done and backfill from Done state tracking."""


def _add_column(cr, table, column, typedef):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    if cr.fetchone():
        return False
    cr.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, typedef))
    return True


def migrate(cr, version):
    _add_column(cr, "daily_task", "date_done", "DATE")

    done_labels = ("done", "Đã hoàn thành")
    cr.execute(
        """
        UPDATE daily_task t
           SET date_done = src.done_day
          FROM (
                SELECT DISTINCT ON (mm.res_id)
                       mm.res_id AS task_id,
                       (mm.date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS done_day
                  FROM mail_message mm
                  JOIN mail_tracking_value mtv ON mtv.mail_message_id = mm.id
                  JOIN ir_model_fields f ON f.id = mtv.field_id
                 WHERE mm.model = 'daily.task'
                   AND f.name = 'state'
                   AND mtv.new_value_char = ANY(%s)
                 ORDER BY mm.res_id, mm.date DESC
              ) src
         WHERE t.id = src.task_id
           AND t.state = 'done'
           AND t.date_done IS NULL
        """,
        (list(done_labels),),
    )

    cr.execute(
        """
        UPDATE daily_task
           SET date_done = (write_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
         WHERE state = 'done'
           AND date_done IS NULL
           AND write_date IS NOT NULL
           AND deadline IS NOT NULL
           AND (write_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= deadline
        """
    )
