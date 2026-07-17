# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Giữ giá trị bộ phận cũ trước khi Odoo đổi schema."""
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_task'
          AND column_name = 'department'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'daily_task'
              AND column_name = 'x_department_old'
            """
        )
        if not cr.fetchone():
            cr.execute(
                "ALTER TABLE daily_task RENAME COLUMN department TO x_department_old"
            )

    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_task_employee'
          AND column_name = 'department'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'daily_task_employee'
              AND column_name = 'x_department_old'
            """
        )
        if not cr.fetchone():
            cr.execute(
                "ALTER TABLE daily_task_employee RENAME COLUMN department TO x_department_old"
            )
