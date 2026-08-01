# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _


class HrLeaveHistoryReport(models.Model):
    _name = "hr.leave.history.report"
    _description = "Lịch sử nghỉ phép"
    _auto = False
    _order = "ticket_create_date desc, id desc"
    _rec_name = "employee_name"

    leave_id = fields.Many2one("hr.leave", string="Đơn nghỉ", readonly=True)
    ticket_create_date = fields.Datetime(string="Ngày tạo", readonly=True)
    ticket_create_user_id = fields.Many2one("res.users", string="Người tạo", readonly=True)
    ticket_write_date = fields.Datetime(string="Cập nhật cuối", readonly=True)
    ticket_write_user_id = fields.Many2one("res.users", string="Người cập nhật", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Nhân viên", readonly=True)
    employee_name = fields.Char(string="Họ và tên", readonly=True)
    employee_id_hrm = fields.Char(string="ID HRM", readonly=True)
    department_id = fields.Many2one("hr.department", string="Phòng ban", readonly=True)
    employee_mien = fields.Selection(
        selection=[
            ("Bắc", "Miền Bắc"),
            ("Nam", "Miền Nam"),
            ("ĐTT", "Miền ĐTT"),
            ("VP", "VP"),
            ("Tất cả", "Tất cả"),
        ],
        string="Miền",
        readonly=True,
    )
    workforce_block = fields.Selection(
        selection=[
            ("office", "Văn phòng"),
            ("store", "Cửa hàng"),
            ("all", "Tất cả"),
        ],
        string="Khối",
        readonly=True,
    )
    store_id = fields.Many2one("hr.store", string="Cửa hàng", readonly=True)
    store_code = fields.Char(string="Mã cửa hàng", readonly=True)
    holiday_status_id = fields.Many2one("hr.leave.type", string="Loại nghỉ", readonly=True)
    request_date_from = fields.Date(string="Từ ngày", readonly=True)
    request_date_to = fields.Date(string="Đến ngày", readonly=True)
    date_from = fields.Datetime(string="Bắt đầu", readonly=True)
    date_to = fields.Datetime(string="Kết thúc", readonly=True)
    number_of_days = fields.Float(string="Số ngày nghỉ", readonly=True)
    number_of_hours = fields.Float(string="Số giờ nghỉ", readonly=True)
    validation_type = fields.Selection(
        related="leave_id.validation_type",
        string="Luồng duyệt",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "To Submit"),
            ("cancel", "Cancelled"),
            ("confirm", "To Approve"),
            ("refuse", "Refused"),
            ("validate1", "Second Approval"),
            ("validate", "Approved"),
        ],
        string="Trạng thái",
        readonly=True,
    )
    status_display_label = fields.Char(
        string="Trạng thái hiển thị",
        compute="_compute_status_display_label",
        readonly=True,
    )
    current_approver_display = fields.Char(
        string="Đang chờ người duyệt",
        compute="_compute_approval_display",
        readonly=True,
    )
    approver_display = fields.Text(
        string="Lịch sử người duyệt",
        compute="_compute_approval_display",
        readonly=True,
    )
    last_refuser_id = fields.Many2one("res.users", string="Người từ chối", readonly=True)
    last_refusal_reason = fields.Text(string="Lý do từ chối", readonly=True)
    request_reason = fields.Text(string="Lý do nghỉ", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, "hr_leave_history_report")
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW hr_leave_history_report AS (
                SELECT
                    l.id AS id,
                    l.id AS leave_id,
                    l.create_date AS ticket_create_date,
                    l.create_uid AS ticket_create_user_id,
                    l.write_date AS ticket_write_date,
                    l.write_uid AS ticket_write_user_id,
                    l.employee_id AS employee_id,
                    COALESCE(e.name, '') AS employee_name,
                    COALESCE(NULLIF(TRIM(e.id_hrm), ''), '') AS employee_id_hrm,
                    COALESCE(v.department_id, e.department_id) AS department_id,
                    COALESCE(l.employee_leave_mien, e.mien) AS employee_mien,
                    COALESCE(e.employee_visibility, 'all') AS workforce_block,
                    sc.store_id AS store_id,
                    COALESCE(sc.code, '') AS store_code,
                    l.holiday_status_id AS holiday_status_id,
                    l.request_date_from AS request_date_from,
                    l.request_date_to AS request_date_to,
                    l.date_from AS date_from,
                    l.date_to AS date_to,
                    l.number_of_days AS number_of_days,
                    l.number_of_hours AS number_of_hours,
                    l.state AS state,
                    l.last_refuser_id AS last_refuser_id,
                    l.last_refusal_reason AS last_refusal_reason,
                    l.notes AS request_reason,
                    l.employee_company_id AS company_id
                FROM hr_leave l
                LEFT JOIN hr_employee e ON l.employee_id = e.id
                LEFT JOIN hr_version v ON v.id = e.current_version_id
                LEFT JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id
            )
            """
        )

    @api.depends("leave_id", "leave_id.status_display_label", "state")
    def _compute_status_display_label(self):
        state_labels = dict(self._fields["state"]._description_selection(self.env))
        for report in self:
            leave = report.leave_id
            if leave and "status_display_label" in leave._fields and leave.status_display_label:
                report.status_display_label = leave.status_display_label
            else:
                report.status_display_label = state_labels.get(report.state, report.state or "")

    @api.depends(
        "leave_id",
        "leave_id.state",
        "leave_id.validation_type",
        "leave_id.first_approver_id",
        "leave_id.second_approver_id",
        "leave_id.approval_actionable_user_ids",
        "leave_id.responsible_approval_line_ids",
        "leave_id.responsible_approval_line_ids.state",
        "leave_id.responsible_approval_line_ids.action_date",
        "leave_id.multi_approval_line_ids",
        "leave_id.multi_approval_line_ids.approved_at",
    )
    def _compute_approval_display(self):
        responsible_labels = dict(
            self.env["hr.leave.responsible.approval"]._fields["state"]._description_selection(self.env)
        )
        for report in self:
            leave = report.leave_id.sudo()
            if not leave:
                report.current_approver_display = ""
                report.approver_display = ""
                continue

            report.current_approver_display = report._get_current_approver_display(leave)
            report.approver_display = report._get_approval_history_display(leave, responsible_labels)

    def _get_current_approver_display(self, leave):
        if leave.state not in ("confirm", "validate1"):
            return ""

        Users = self.env["res.users"].sudo()
        current_users = Users
        if leave.validation_type == "employee_hr_responsibles":
            pending = leave.responsible_approval_line_ids.filtered(
                lambda line: line.state == "pending" and line.user_id
            ).sorted(lambda line: (line.sequence, line.id))
            if pending:
                mode = leave._responsible_approval_mode()
                current = leave._responsible_pending_current_wave() if mode == "sequential" else pending
                current_users = current.mapped("user_id")
        elif leave.validation_type == "multi_step_6":
            current_users = leave._get_multi_step_approvers().filtered(lambda user: user and not user.share)
        elif "approval_actionable_user_ids" in leave._fields:
            current_users = leave.approval_actionable_user_ids.filtered(lambda user: user and not user.share)

        return ", ".join(current_users.mapped("display_name"))

    def _get_approval_history_display(self, leave, responsible_labels):
        parts = []
        if leave.first_approver_id:
            parts.append(_("Duyệt lần 1: %s") % leave.first_approver_id.name)
        if leave.second_approver_id and leave.second_approver_id != leave.first_approver_id:
            parts.append(_("Duyệt lần 2: %s") % leave.second_approver_id.name)

        for line in leave.responsible_approval_line_ids.sorted(lambda item: (item.sequence, item.id)):
            if not line.user_id:
                continue
            label = responsible_labels.get(line.state, line.state or "")
            if line.action_date:
                parts.append("%s: %s (%s)" % (line.user_id.display_name, label, line.action_date))
            else:
                parts.append("%s: %s" % (line.user_id.display_name, label))

        for line in leave.multi_approval_line_ids.sorted(lambda item: (item.approved_at, item.id)):
            step = line.step_id.name or _("Bước duyệt")
            parts.append("%s - %s (%s)" % (step, line.approver_user_id.display_name, line.approved_at))

        return "\n".join(dict.fromkeys(parts))

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
