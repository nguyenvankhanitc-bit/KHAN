# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


_GROUP_COLORS = (
    "#4f7cff",
    "#fb923c",
    "#22c55e",
    "#06b6d4",
    "#8b5cf6",
    "#f43f5e",
    "#0ea5e9",
    "#ec4899",
    "#6366f1",
    "#14b8a6",
    "#f59e0b",
    "#64748b",
)


def _group_icon(name):
    text = (name or "").lower()
    pairs = (
        ("odoo", "fa-cubes"),
        ("lark", "fa-cloud"),
        ("camera", "fa-video-camera"),
        ("internet", "fa-globe"),
        ("chấm công", "fa-clock-o"),
        ("cham cong", "fa-clock-o"),
        ("vi tính", "fa-desktop"),
        ("vi tinh", "fa-desktop"),
        ("máy tính", "fa-desktop"),
        ("may tinh", "fa-desktop"),
        ("máy in", "fa-print"),
        ("may in", "fa-print"),
        ("điện", "fa-bolt"),
        ("dien", "fa-bolt"),
        ("nước", "fa-tint"),
        ("nuoc", "fa-tint"),
        ("lương", "fa-money"),
        ("hoa hồng", "fa-money"),
        ("thông báo", "fa-bullhorn"),
        ("ctkm", "fa-bullhorn"),
        ("backup", "fa-server"),
        ("máy chủ", "fa-server"),
        ("bảo hiểm", "fa-shield"),
        ("chứng từ", "fa-file-text-o"),
        ("phát sinh", "fa-cogs"),
        ("doanh thu", "fa-line-chart"),
        ("chi phí", "fa-usd"),
        ("ngân hàng", "fa-university"),
        ("cháy", "fa-fire"),
        ("logo", "fa-picture-o"),
        ("bảng hiệu", "fa-picture-o"),
        ("thiết kế", "fa-paint-brush"),
        ("phần mềm", "fa-code"),
        ("khác", "fa-th-list"),
        ("huy", "fa-user"),
        ("dhkd", "fa-file-text-o"),
    )
    for key, icon in pairs:
        if key in text:
            return icon
    return "fa-folder-o"


def _group_color(key):
    s = str(key or "")
    n = sum(ord(c) for c in s)
    return _GROUP_COLORS[n % len(_GROUP_COLORS)]


class DailyTaskTeamChecklist(models.Model):
    _inherit = "daily.task"

    @api.model
    def get_team_checklist_data(self, filters=None):
        """Dashboard Checklist công việc team (theo ngày)."""
        filters = filters or {}
        today = fields.Date.context_today(self)
        target = filters.get("date") or today
        if isinstance(target, str):
            target = fields.Date.from_string(target)
        emp_id = int(filters.get("employee_id") or 0)
        wg_id = int(filters.get("work_group_id") or 0)
        state_f = (filters.get("state") or "").strip()
        search = (filters.get("search") or "").strip().lower()
        only_open = bool(filters.get("only_open"))

        my = self._my_hr_employee()
        if self._is_manager():
            allowed = None
        else:
            allowed = self._checklist_employee_ids() or []
            if not allowed:
                raise ValidationError(
                    "Chưa được phân quyền xem Checklist CV nhân viên. "
                    "Vào Cấu hình → Phân quyền, chọn nhân viên và tick Checklist CV."
                )

        month_start = target.replace(day=1)
        domain = [
            ("manager_confirmed", "=", False),
            "|",
            "&",
            "&",
            ("deadline", "!=", False),
            ("deadline", ">=", month_start),
            ("deadline", "<=", target),
            "&",
            "&",
            ("deadline", "=", False),
            ("assign_date", ">=", month_start),
            ("assign_date", "<=", target),
        ]
        if allowed is not None:
            if not allowed:
                tasks = self.browse()
            else:
                domain.append(("assignee_id.employee_id", "in", allowed))
                tasks = self.sudo().search(domain, order="assignee_id, deadline, id")
        else:
            tasks = self.sudo().search(domain, order="assignee_id, deadline, id")

        def _is_handed_over(task):
            assignee_uid = (
                task.assignee_id.employee_id.user_id.id
                if task.assignee_id.employee_id and task.assignee_id.employee_id.user_id
                else False
            )
            return bool(
                task.assigned_by_id
                and assignee_uid
                and task.assigned_by_id.id != assignee_uid
            )

        if emp_id:
            tasks = tasks.filtered(lambda t: t.assignee_id.employee_id.id == emp_id)
        if wg_id:
            tasks = tasks.filtered(lambda t: t.work_group_id.id == wg_id)

        def _is_overdue(task):
            return bool(
                task.deadline
                and not task._is_work_completed()
                and task.deadline < target
            )

        def _is_todo(task):
            return task.state == "not_started" and not _is_overdue(task)

        def _is_doing(task):
            return task.state == "in_progress" and not _is_overdue(task)

        if state_f == "done":
            tasks = tasks.filtered(lambda t: t.state == "done")
        elif state_f == "not_started":
            tasks = tasks.filtered(_is_todo)
        elif state_f == "in_progress":
            tasks = tasks.filtered(_is_doing)
        elif state_f == "overdue":
            tasks = tasks.filtered(_is_overdue)

        if only_open:
            tasks = tasks.filtered(lambda t: t.state != "done")

        if search:
            tasks = tasks.filtered(
                lambda t: search
                in " ".join(
                    [
                        t.name or "",
                        t.work_group_id.name or "",
                        t.department_id.name or "",
                        t.assignee_id.name or "",
                    ]
                ).lower()
            )

        editable = self._editable_employee_ids()
        if self._is_manager():
            can_edit_ids = None
        else:
            can_edit_ids = set(editable or [])
            if my:
                can_edit_ids.add(my.id)

        pending = tasks

        v_domain = [
            ("manager_confirmed", "=", True),
            "|",
            "&",
            "&",
            ("deadline", "!=", False),
            ("deadline", ">=", month_start),
            ("deadline", "<=", target),
            "&",
            "&",
            ("deadline", "=", False),
            ("assign_date", ">=", month_start),
            ("assign_date", "<=", target),
        ]
        if allowed is not None:
            if not allowed:
                verified = self.browse()
            else:
                v_domain.append(("assignee_id.employee_id", "in", allowed))
                verified = self.sudo().search(v_domain, order="assignee_id, deadline, id")
        else:
            verified = self.sudo().search(v_domain, order="assignee_id, deadline, id")
        if emp_id:
            verified = verified.filtered(lambda t: t.assignee_id.employee_id.id == emp_id)
        if wg_id:
            verified = verified.filtered(lambda t: t.work_group_id.id == wg_id)
        if search:
            verified = verified.filtered(
                lambda t: search
                in " ".join(
                    [
                        t.name or "",
                        t.work_group_id.name or "",
                        t.department_id.name or "",
                        t.assignee_id.name or "",
                    ]
                ).lower()
            )

        done_n = len(pending.filtered(lambda t: t.state == "done"))
        todo_n = len(pending.filtered(_is_todo))
        doing_n = len(pending.filtered(_is_doing))
        overdue_n = len(pending.filtered(_is_overdue))
        total = len(pending)

        def _pct(part):
            return round((part / float(total)) * 100) if total else 0

        def _task_row(t, can_edit):
            return {
                "id": t.id,
                "name": t.name or "",
                "assignee_id": t.assignee_id.id,
                "assignee_name": t.assignee_id.name or "",
                "category": t.work_group_id.name or "Khác",
                "work_group_id": t.work_group_id.id or 0,
                "category_icon": _group_icon(t.work_group_id.name),
                "store": t.department_id.name or "",
                "deadline": t.deadline.strftime("%d/%m/%Y") if t.deadline else "",
                "assign_date": t.assign_date.strftime("%d/%m/%Y") if t.assign_date else "",
                "duration_minutes": int(t.duration_minutes or 0),
                "note": t.note or "",
                "priority": t.priority or "",
                "priority_label": dict(self._fields["priority"].selection).get(
                    t.priority, ""
                ),
                "state": t.state,
                "state_label": dict(self._fields["state"].selection).get(
                    t.state, ""
                ),
                "is_done": t.state == "done",
                "is_overdue": _is_overdue(t),
                "can_edit": can_edit,
                "manager_confirmed": bool(t.manager_confirmed),
                "can_confirm": t._can_manager_confirm(),
                "is_assigned": _is_handed_over(t),
                "assigned_by_name": t.assigned_by_id.name or "",
            }

        employees = []
        grouped = {}
        for task in pending:
            key = task.assignee_id.id
            grouped.setdefault(key, self.env["daily.task"])
            grouped[key] |= task

        for assignee_id, u_tasks in grouped.items():
            assignee = u_tasks[:1].assignee_id
            hr = assignee.employee_id
            u_done = u_tasks.filtered(lambda t: t.state == "done")
            u_overdue = u_tasks.filtered(_is_overdue)
            u_todo = u_tasks.filtered(_is_todo)
            hr_id = hr.id if hr else 0
            can_edit = can_edit_ids is None or hr_id in can_edit_ids
            name = assignee.name or hr.name or ""
            initial = (name.strip()[:1] or "?").upper()
            uid = hr.user_id.id if hr and hr.user_id else 0
            employees.append(
                {
                    "assignee_id": assignee.id,
                    "employee_id": hr_id,
                    "user_id": uid,
                    "name": name,
                    "initial": initial,
                    "avatar_url": (
                        "/web/image/res.users/%s/avatar_128" % uid if uid else ""
                    ),
                    "total": len(u_tasks),
                    "done_count": len(u_done),
                    "todo_count": len(u_todo),
                    "overdue_count": len(u_overdue),
                    "percent": round(len(u_done) / float(len(u_tasks)) * 100)
                    if u_tasks
                    else 0,
                    "can_edit": can_edit,
                    "tasks": [_task_row(t, can_edit) for t in u_tasks],
                }
            )
        employees.sort(key=lambda e: e["name"])

        categories = {}
        for task in pending | verified:
            wg = task.work_group_id
            key = wg.id or 0
            name = wg.name or "Khác"
            row = categories.setdefault(
                key,
                {
                    "id": key,
                    "seq": int(wg.sequence or 0) or key or 0,
                    "name": name,
                    "icon": _group_icon(name),
                    "color": _group_color(name or key),
                    "total": 0,
                    "done": 0,
                    "tasks": [],
                },
            )
            can_edit = can_edit_ids is None or (
                task.assignee_id.employee_id.id in (can_edit_ids or [])
            )
            row["total"] += 1
            if task.state == "done":
                row["done"] += 1
            row["tasks"].append(_task_row(task, can_edit))
        category_list = []
        for i, row in enumerate(sorted(categories.values(), key=lambda c: (c["name"], c["id"]))):
            total = row["total"] or 0
            done = row["done"] or 0
            pct = round(done / float(total) * 100) if total else 0
            if not row["seq"]:
                row["seq"] = i + 1
            row["percent"] = pct
            row["complete"] = bool(total and done >= total)
            category_list.append(row)

        work_groups = [
            {"id": g.id, "name": g.name}
            for g in self.env["daily.task.work.group"].sudo().search([], order="name")
        ]
        emp_options = []
        if allowed is None:
            emp_ids = self.env["hr.employee"].sudo().search([("active", "=", True)]).ids
        else:
            emp_ids = allowed
        for row in self._hr_employee_rows_by_ids(emp_ids):
            emp_options.append({"id": row["id"], "name": row.get("name") or ""})

        return {
            "date": target.isoformat(),
            "date_display": target.strftime("%d/%m/%Y"),
            "can_assign": self._is_assigner() or self._is_manager(),
            "can_confirm": self._is_manager()
            or bool(self._checklist_employee_ids()),
            "verified": [
                _task_row(
                    t,
                    can_edit_ids is None
                    or (t.assignee_id.employee_id.id in (can_edit_ids or [])),
                )
                for t in verified.sorted(
                    lambda t: (t.assignee_id.name or "", str(t.deadline or ""), t.id)
                )
            ],
            "stats": {
                "total": total,
                "done": done_n,
                "todo": todo_n,
                "in_progress": doing_n,
                "overdue": overdue_n,
                "done_percent": _pct(done_n),
                "todo_percent": _pct(todo_n),
                "in_progress_percent": _pct(doing_n),
                "overdue_percent": _pct(overdue_n),
            },
            "employees": employees,
            "categories": category_list,
            "filters": {
                "employees": emp_options,
                "work_groups": work_groups,
            },
        }

    def toggle_team_checklist_done(self, done=True):
        self.ensure_one()
        if done:
            return self.update_from_manager({"state": "done", "completion_percent": 100})
        return self.update_from_manager({"state": "not_started", "completion_percent": 0})

    def toggle_manager_confirm(self, confirmed=True):
        confirmed = bool(confirmed)
        for rec in self:
            if not rec._can_manager_confirm():
                raise ValidationError("Bạn không có quyền xác nhận công việc này.")
            rec.sudo().with_context(
                tracking_disable=True,
                mail_notrack=True,
                mail_create_nolog=True,
            ).write(
                {
                    "manager_confirmed": confirmed,
                    "manager_confirmed_uid": self.env.uid if confirmed else False,
                    "manager_confirmed_date": fields.Datetime.now() if confirmed else False,
                }
            )
        return True
