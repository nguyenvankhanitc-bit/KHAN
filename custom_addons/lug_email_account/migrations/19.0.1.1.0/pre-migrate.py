# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

POSITION_MAP = {
    "giám đốc": "director",
    "giam doc": "director",
    "phó giám đốc": "deputy_director",
    "trưởng phòng": "dept_head",
    "truong phong": "dept_head",
    "phó phòng": "deputy_head",
    "trưởng nhóm": "team_lead",
    "nhân viên": "staff",
    "nhan vien": "staff",
    "thủ kho": "warehouse_keeper",
    "thu kho": "warehouse_keeper",
    "kế toán": "accountant",
    "ke toan": "accountant",
    "hcns": "hr",
    "marketing": "marketing",
    "it": "it",
}

USAGE_TARGET_MAP = {
    "internal": "Nội bộ",
    "personal": "Cá nhân",
    "external": "Đối tác / Khách hàng",
}

STATE_MAP = {
    "inactive": "cancel",
    "suspended": "lock",
}

VALID_POSITIONS = {
    "director", "deputy_director", "dept_head", "deputy_head", "team_lead",
    "staff", "warehouse_keeper", "accountant", "hr", "marketing", "it", "other",
}


def _get_or_create_department(cr, env, name):
    if not name:
        return None
    dept = env["hr.department"].search([("name", "=ilike", name)], limit=1)
    if not dept:
        dept = env["hr.department"].create({"name": name})
    return dept.id


def _get_or_create_employee(cr, env, name, department_id):
    if not name:
        return None
    emp = env["hr.employee"].search([("name", "=ilike", name)], limit=1)
    if not emp:
        vals = {"name": name}
        if department_id:
            vals["department_id"] = department_id
        emp = env["hr.employee"].create(vals)
    return emp.id


def migrate(cr, version):
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'lug_email_account'
          AND column_name = 'department'
    """)
    if not cr.fetchone():
        return

    _logger.info("Pre-migrating lug.email.account records to v1.1...")

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        ALTER TABLE lug_email_account
        ADD COLUMN IF NOT EXISTS department_id INTEGER,
        ADD COLUMN IF NOT EXISTS employee_id INTEGER
    """)

    cr.execute("""
        SELECT id, department, employee_name, position, usage_target, state
        FROM lug_email_account
    """)

    for row_id, dept_name, emp_name, position_val, usage_val, state_val in cr.fetchall():
        department_id = _get_or_create_department(cr, env, dept_name)
        employee_id = _get_or_create_employee(cr, env, emp_name, department_id)

        if position_val in VALID_POSITIONS:
            position = position_val
        else:
            position = POSITION_MAP.get((position_val or "").strip().lower(), "other")

        usage_target = USAGE_TARGET_MAP.get(usage_val, usage_val or "")
        state = STATE_MAP.get(state_val, state_val or "active")

        cr.execute("""
            UPDATE lug_email_account
            SET department_id = %s,
                employee_id = %s,
                position = %s,
                usage_target = %s,
                state = %s
            WHERE id = %s
        """, (department_id, employee_id, position, usage_target, state, row_id))
