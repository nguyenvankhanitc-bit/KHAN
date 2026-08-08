# -*- coding: utf-8 -*-
"""
Lab/workspace DB có thể thiếu cột stored (upgrade XML lỗi giữa chừng).
Tạo cột trước khi ORM load / constraint.
"""


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
    cr.execute(
        "ALTER TABLE %s ADD COLUMN %s %s"
        % (table, column, typedef)
    )
    return True


def migrate(cr, version):
    # daily_task — các cột hay thiếu trên lab
    cols = [
        ("kanban_column", "VARCHAR"),
        ("recurring_id", "INTEGER"),
        ("description", "TEXT"),
        ("assigned_by_id", "INTEGER"),
        ("color", "INTEGER"),
        ("is_overdue", "BOOLEAN"),
        ("duration_hours", "DOUBLE PRECISION"),
        ("duration_minutes", "INTEGER"),
        ("completion_percent", "INTEGER"),
        ("work_group_id", "INTEGER"),
        ("department_id", "INTEGER"),
        ("employee_hr_id", "INTEGER"),
        ("assign_date", "DATE"),
    ]
    for name, typedef in cols:
        _add_column(cr, "daily_task", name, typedef)

    cr.execute(
        """
        CREATE INDEX IF NOT EXISTS daily_task_recurring_id_index
            ON daily_task (recurring_id)
        """
    )
