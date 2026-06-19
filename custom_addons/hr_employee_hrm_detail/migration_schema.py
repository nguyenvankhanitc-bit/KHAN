# -*- coding: utf-8 -*-
"""Idempotent SQL helpers for res.users visibility_policy schema repair."""

import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cr.fetchone() is not None


def _table_exists(cr, table):
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (table,),
    )
    return cr.fetchone() is not None


def ensure_res_users_visibility_schema(cr):
    """Create missing res.users columns/tables; drop legacy visibility artifacts."""
    if not _column_exists(cr, "res_users", "visibility_policy"):
        cr.execute("ALTER TABLE res_users ADD COLUMN visibility_policy VARCHAR")
        cr.execute(
            "UPDATE res_users SET visibility_policy = 'self' "
            "WHERE visibility_policy IS NULL"
        )
        _logger.info("migration_schema: added res_users.visibility_policy")

    if not _column_exists(cr, "res_users", "employee_ma_bo_phan_id"):
        cr.execute(
            "ALTER TABLE res_users ADD COLUMN employee_ma_bo_phan_id INTEGER"
        )
        _logger.info("migration_schema: added res_users.employee_ma_bo_phan_id")

    if not _column_exists(cr, "res_users", "employee_department_id"):
        cr.execute(
            "ALTER TABLE res_users ADD COLUMN employee_department_id INTEGER"
        )
        _logger.info("migration_schema: added res_users.employee_department_id")

    if not _column_exists(cr, "res_users", "employee_mien"):
        cr.execute("ALTER TABLE res_users ADD COLUMN employee_mien VARCHAR")
        _logger.info("migration_schema: added res_users.employee_mien")

    if not _table_exists(cr, "res_users_assigned_ma_bo_phan_rel"):
        cr.execute(
            """
            CREATE TABLE res_users_assigned_ma_bo_phan_rel (
                user_id INTEGER NOT NULL,
                store_code_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, store_code_id)
            )
            """
        )
        _logger.info("migration_schema: created res_users_assigned_ma_bo_phan_rel")

    if _column_exists(cr, "res_users", "hr_user_workforce_scope"):
        cr.execute("ALTER TABLE res_users DROP COLUMN hr_user_workforce_scope")
        _logger.info("migration_schema: dropped res_users.hr_user_workforce_scope")

    if _table_exists(cr, "res_users_assigned_employee_rel"):
        cr.execute("DROP TABLE res_users_assigned_employee_rel")
        _logger.info("migration_schema: dropped res_users_assigned_employee_rel")
