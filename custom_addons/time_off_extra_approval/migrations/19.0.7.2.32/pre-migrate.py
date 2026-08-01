import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    table = "hr_leave_type_special_employee_line"
    if not sql.table_exists(cr, table):
        return

    if not sql.column_exists(cr, table, "line_kind"):
        cr.execute(
            """
            ALTER TABLE hr_leave_type_special_employee_line
            ADD COLUMN line_kind VARCHAR
            """
        )

    # Rows that already have explicit Approvals Employee → store special employees.
    if sql.table_exists(cr, "hr_leave_type_special_employee_approver_rel"):
        cr.execute(
            """
            UPDATE hr_leave_type_special_employee_line AS line
               SET line_kind = 'store'
             WHERE EXISTS (
                SELECT 1
                  FROM hr_leave_type_special_employee_approver_rel AS rel
                 WHERE rel.line_id = line.id
             )
               AND (line.line_kind IS NULL OR BTRIM(line.line_kind) = '')
            """
        )

    # Remaining rows (director / stop-position flow) → office special employees.
    cr.execute(
        """
        UPDATE hr_leave_type_special_employee_line
           SET line_kind = 'office'
         WHERE line_kind IS NULL OR BTRIM(line_kind) = ''
        """
    )

    # Backfill ID HRM for store rows that still miss it.
    if sql.column_exists(cr, table, "employee_hrm_id"):
        cr.execute(
            """
            UPDATE hr_leave_type_special_employee_line AS line
               SET employee_hrm_id = NULLIF(BTRIM(employee.id_hrm), '')
              FROM hr_employee AS employee
             WHERE employee.id = line.employee_id
               AND line.line_kind = 'store'
               AND (line.employee_hrm_id IS NULL OR BTRIM(line.employee_hrm_id) = '')
            """
        )

    cr.execute(
        """
        SELECT line_kind, COUNT(*)
          FROM hr_leave_type_special_employee_line
         GROUP BY line_kind
         ORDER BY line_kind
        """
    )
    for kind, count in cr.fetchall():
        _logger.info(
            "time_off_extra_approval: special employee lines kind=%s count=%s",
            kind,
            count,
        )
