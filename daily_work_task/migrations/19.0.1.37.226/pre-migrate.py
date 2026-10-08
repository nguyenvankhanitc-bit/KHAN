# -*- coding: utf-8 -*-
"""Migrate User áp dụng cũ → User chi tiết; tạo bảng quan hệ mới nếu cần."""


def _table_exists(cr, table):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = %s
        """,
        (table,),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    # Copy dữ liệu cũ (nếu còn) sang User chi tiết
    if _table_exists(cr, "daily_task_work_group_user_rel"):
        cr.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_task_work_group_detail_user_rel (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, user_id)
            )
            """
        )
        cr.execute(
            """
            INSERT INTO daily_task_work_group_detail_user_rel (group_id, user_id)
            SELECT group_id, user_id
              FROM daily_task_work_group_user_rel
             ON CONFLICT DO NOTHING
            """
        )
