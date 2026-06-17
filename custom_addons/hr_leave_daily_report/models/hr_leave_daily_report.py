# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools


class HrLeaveDailyReport(models.Model):
    _name = "hr.leave.daily.report"
    _description = "Ngày nghỉ theo ngày"
    _auto = False
    _order = "request_date_from desc, employee_id, id"
    _rec_name = "employee_name"

    leave_id = fields.Many2one("hr.leave", string="Đơn nghỉ", readonly=True)
    stt = fields.Integer(string="STT", readonly=True)
    employee_leave_mien = fields.Selection(
        selection=[
            ("Bắc", "Bắc"),
            ("Nam", "Nam"),
            ("ĐTT", "ĐTT"),
            ("VP", "VP"),
        ],
        string="Miền",
        readonly=True,
    )
    employee_id_hrm = fields.Char(string="ID", readonly=True)
    employee_name = fields.Char(string="Họ và Tên NV", readonly=True)
    employee_ma_bo_phan = fields.Char(string="Mã bộ phận", readonly=True)
    job_title = fields.Char(string="Chức danh", readonly=True)
    job_title_display = fields.Char(
        string="Chức danh",
        compute="_compute_job_title_display",
        readonly=True,
    )
    request_date_from = fields.Date(string="Ngày nghỉ bắt đầu", readonly=True)
    request_date_to = fields.Date(string="Ngày nghỉ kết thúc", readonly=True)
    number_of_days = fields.Float(string="Số ngày nghỉ", readonly=True)
    state = fields.Selection(
        selection=[
            ("cancel", "Cancelled"),
            ("confirm", "To Approve"),
            ("refuse", "Refused"),
            ("validate1", "Second Approval"),
            ("validate", "Approved"),
        ],
        string="Status",
        readonly=True,
    )
    status_display_label = fields.Char(
        string="Trạng thái",
        compute="_compute_status_display_label",
        readonly=True,
    )
    employee_id = fields.Many2one("hr.employee", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    @api.depends("employee_id", "job_title")
    def _compute_job_title_display(self):
        Employee = self.env["hr.employee"]
        selection_labels = {}
        if "job_title" in Employee._fields and Employee._fields["job_title"].type == "selection":
            selection_labels = dict(
                Employee._fields["job_title"]._description_selection(self.env)
            )
        for report in self:
            employee = report.employee_id
            key = report.job_title or (employee.job_title if employee else "")
            label = selection_labels.get(key, key or "")
            if not label and employee and employee.job_id:
                label = (employee.job_id.name or "").strip()
            report.job_title_display = label

    @api.depends("leave_id", "leave_id.status_display_label", "state")
    def _compute_status_display_label(self):
        state_labels = dict(self._fields["state"].selection)
        for report in self:
            leave = report.leave_id
            if leave and "status_display_label" in leave._fields and leave.status_display_label:
                report.status_display_label = leave.status_display_label
            else:
                report.status_display_label = state_labels.get(report.state, report.state or "")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, "hr_leave_daily_report")
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW hr_leave_daily_report AS (
                SELECT
                    l.id AS id,
                    l.id AS leave_id,
                    ROW_NUMBER() OVER (
                        ORDER BY l.request_date_from DESC NULLS LAST, l.employee_id, l.id
                    ) AS stt,
                    l.employee_leave_mien AS employee_leave_mien,
                    COALESCE(NULLIF(TRIM(e.id_hrm), ''), '') AS employee_id_hrm,
                    COALESCE(e.name, '') AS employee_name,
                    UPPER(COALESCE(NULLIF(TRIM(e.ma_bo_phan), ''), '')) AS employee_ma_bo_phan,
                    COALESCE(e.job_title, '') AS job_title,
                    l.request_date_from AS request_date_from,
                    l.request_date_to AS request_date_to,
                    l.number_of_days AS number_of_days,
                    l.state AS state,
                    l.employee_id AS employee_id,
                    l.employee_company_id AS company_id
                FROM hr_leave l
                INNER JOIN hr_employee e ON l.employee_id = e.id
                WHERE e.active IS TRUE
                  AND l.state != 'cancel'
            )
            """
        )

    def action_open_leave(self):
        self.ensure_one()
        if not self.leave_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.leave",
            "res_id": self.leave_id.id,
            "view_mode": "form",
            "target": "current",
        }
