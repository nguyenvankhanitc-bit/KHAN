# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DailyTaskSendOverdueMail(models.TransientModel):
    _name = "daily.task.send.overdue.mail"
    _description = "Gửi mail giục quá hạn"

    assignee_id = fields.Many2one(
        "daily.task.employee",
        string="Người phụ trách",
        help="Để trống = gửi tất cả nhân viên có việc quá hạn",
    )
    overdue_count = fields.Integer(string="Số việc quá hạn", compute="_compute_overdue")
    employee_count = fields.Integer(string="Số người nhận", compute="_compute_overdue")
    preview_html = fields.Html(string="Xem trước", compute="_compute_overdue", sanitize=False)

    @api.depends("assignee_id")
    def _compute_overdue(self):
        Task = self.env["daily.task"]
        for wiz in self:
            domain = [("is_overdue", "=", True)]
            if wiz.assignee_id:
                domain.append(("assignee_id", "=", wiz.assignee_id.id))
            tasks = Task.search(domain)
            wiz.overdue_count = len(tasks)
            assignees = tasks.mapped("assignee_id")
            wiz.employee_count = len(assignees)
            if not tasks:
                wiz.preview_html = "<p>Không có công việc quá hạn.</p>"
            else:
                lines = [
                    "<li><b>%s</b> — %s việc (email: %s)</li>"
                    % (emp.name, len(tasks.filtered(lambda t: t.assignee_id == emp)), emp.email or "—")
                    for emp in assignees
                ]
                wiz.preview_html = (
                    "<p>Sẽ gửi nhắc tới <b>%s</b> nhân viên / <b>%s</b> việc:</p><ul>%s</ul>"
                    % (wiz.employee_count, wiz.overdue_count, "".join(lines))
                )

    def action_send(self):
        self.ensure_one()
        Task = self.env["daily.task"]
        domain = [("is_overdue", "=", True)]
        if self.assignee_id:
            domain.append(("assignee_id", "=", self.assignee_id.id))
        overdue = Task.search(domain)
        if not overdue:
            raise UserError(_("Không có công việc quá hạn để gửi mail."))

        by_assignee = {}
        for task in overdue:
            by_assignee.setdefault(task.assignee_id, Task)
            by_assignee[task.assignee_id] |= task

        Mail = self.env["mail.mail"].sudo()
        sent = 0
        for employee, tasks in by_assignee.items():
            if not employee.email:
                continue
            body = Task._build_overdue_email_body(employee, tasks)
            Mail.create(
                {
                    "subject": "[Nhắc việc] Bạn có %s công việc quá hạn" % len(tasks),
                    "body_html": body,
                    "email_to": employee.email,
                    "auto_delete": True,
                }
            ).send()
            sent += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đã gửi mail"),
                "message": _("Đã gửi nhắc quá hạn tới %s nhân viên.") % sent,
                "type": "success",
                "sticky": False,
            },
        }
