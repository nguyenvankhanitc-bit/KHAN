# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def _link_employees_to_hr(env):
    """Liên kết daily.task.employee với hr.employee theo tên (nếu chưa có)."""
    Emp = env["daily.task.employee"].sudo()
    Hr = env["hr.employee"].sudo()
    for bridge in Emp.search([("employee_id", "=", False)]):
        hr = Hr.search([("name", "=ilike", bridge.name)], limit=1)
        if not hr:
            # thử khớp bỏ khoảng thừa
            hr = Hr.search([("name", "ilike", bridge.name.strip())], limit=1)
        if hr:
            # tránh trùng unique employee_id
            other = Emp.search([("employee_id", "=", hr.id), ("id", "!=", bridge.id)], limit=1)
            if other:
                # chuyển task sang bridge đã liên kết
                bridge.task_ids.write({"assignee_id": other.id})
                bridge.unlink()
                _logger.info("Merged daily.task.employee %s -> %s (HR %s)", bridge.name, other.id, hr.name)
            else:
                bridge.employee_id = hr.id
                _logger.info("Linked daily.task.employee %s -> HR %s", bridge.name, hr.name)


def post_init_hook(env):
    _link_employees_to_hr(env)
