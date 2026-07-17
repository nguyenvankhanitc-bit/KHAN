# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


OLD_DEPT_MAP = {
    "kinh_doanh": ["KINH DOANH", "MARKETING - KINH DOANH", "PHÒNG MARKETING"],
    "marketing": ["Marketing", "MARKETING"],
    "ky_thuat": ["THI CÔNG", "Kỹ thuật", "KY THUAT"],
    "it": ["Quản trị", "IT", "HCNS"],
}


def _find_department(env, keywords):
    Dept = env["hr.department"].sudo()
    for kw in keywords:
        dept = Dept.search([("name", "ilike", kw)], limit=1)
        if dept:
            return dept
    return Dept.browse()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Task = env["daily.task"].sudo()
    Dept = env["hr.department"].sudo()

    # Map từ mã bộ phận cũ
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_task' AND column_name = 'x_department_old'
        """
    )
    if cr.fetchone():
        cache = {}
        for code, keywords in OLD_DEPT_MAP.items():
            cache[code] = _find_department(env, keywords)
        cr.execute("SELECT id, x_department_old FROM daily_task")
        for task_id, old_code in cr.fetchall():
            task = Task.browse(task_id)
            if not task.exists():
                continue
            dept = False
            # ưu tiên phòng ban trên hồ sơ HR của người phụ trách
            if task.assignee_id and task.assignee_id.employee_id and task.assignee_id.employee_id.department_id:
                dept = task.assignee_id.employee_id.department_id
            elif old_code in cache and cache[old_code]:
                dept = cache[old_code]
            if dept:
                task.department_id = dept.id
        cr.execute("ALTER TABLE daily_task DROP COLUMN IF EXISTS x_department_old")

    # Drop cột cũ của bridge nếu còn
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_task_employee' AND column_name = 'x_department_old'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE daily_task_employee DROP COLUMN IF EXISTS x_department_old")

    # Drop hr_department_id cũ nếu model đã đổi tên related field — Odoo tự xử lý
    # Đồng bộ department_id còn trống từ HR employee
    for task in Task.search([("department_id", "=", False)]):
        hr = task.assignee_id.employee_id
        if hr and hr.department_id:
            task.department_id = hr.department_id.id
