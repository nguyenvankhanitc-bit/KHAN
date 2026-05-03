import base64
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrEmployeeGateTicket(models.Model):
    _name = 'hr.employee.gate.ticket'
    _description = 'HR Employee Gate Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_in desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self.env.user.employee_id,
        tracking=True,
    )
    check_in = fields.Datetime(
        string='Check In',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    gate_ticket = fields.Char(string='Reason', tracking=True)
    gate_items = fields.Text(string='Items', tracking=True)
    checkout_time = fields.Datetime(string='Checkout Time', tracking=True)

    approver_id = fields.Many2one(
        'res.users',
        string='First Approver',
        domain=[('share', '=', False)],
        tracking=True,
        help='User who can do the first approval',
    )
    second_approver_id = fields.Many2one(
        'res.users',
        string='Second Approver',
        domain=lambda self: [('id', 'in', self._get_allowed_approver_user_ids())],
        default=lambda self: self._get_auto_second_approver(),
        tracking=True,
        help='User who will do the second approval',
    )
    third_approver_id = fields.Many2one(
        'res.users',
        string='Third Approver',
        domain=lambda self: [('id', 'in', self._get_allowed_approver_user_ids())],
        default=lambda self: self._get_auto_third_approver(),
        tracking=True,
        help='User who will do the third approval',
    )
    state = fields.Selection(
        [
            ('draft', 'To Submit'),
            ('confirm', 'First Approval'),
            ('second_approve', 'Second Approval'),
            ('validate', 'Approved'),
            ('refuse', 'Refused'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    _AUTO_SECOND_APPROVER_BADGE = '041713543858'
    _AUTO_THIRD_APPROVER_BADGE = '041838157770'

    def _get_attendance_officer_user_ids(self):
        attendance_officer_group = self.env.ref('hr_attendance.group_hr_attendance_user')
        return self.env['res.users'].sudo().search(
            [
                ('share', '=', False),
                ('all_group_ids', 'in', attendance_officer_group.id),
            ]
        ).ids

    def _get_user_by_employee_barcode(self, barcode):
        employee = self.env['hr.employee'].sudo().search(
            [
                ('barcode', '=', barcode),
                ('user_id', '!=', False),
            ],
            limit=1,
        )
        return employee.user_id

    def _get_allowed_approver_user_ids(self):
        user_ids = set(self._get_attendance_officer_user_ids())
        second_user = self._get_user_by_employee_barcode(self._AUTO_SECOND_APPROVER_BADGE)
        third_user = self._get_user_by_employee_barcode(self._AUTO_THIRD_APPROVER_BADGE)
        if second_user:
            user_ids.add(second_user.id)
        if third_user:
            user_ids.add(third_user.id)
        return list(user_ids)

    def _get_auto_third_approver(self):
        user = self._get_user_by_employee_barcode(self._AUTO_THIRD_APPROVER_BADGE)
        return user if user else False

    def _get_auto_second_approver(self):
        user = self._get_user_by_employee_barcode(self._AUTO_SECOND_APPROVER_BADGE)
        return user if user else False

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        auto_second_approver = self._get_auto_second_approver()
        auto_third_approver = self._get_auto_third_approver()
        if 'second_approver_id' in fields_list and auto_second_approver and not values.get('second_approver_id'):
            values['second_approver_id'] = auto_second_approver.id
        if 'third_approver_id' in fields_list and auto_third_approver and not values.get('third_approver_id'):
            values['third_approver_id'] = auto_third_approver.id
        return values

    @api.onchange('employee_id')
    def _onchange_approver_domains(self):
        domain = [('id', 'in', self._get_allowed_approver_user_ids())]
        auto_second_approver = self._get_auto_second_approver()
        auto_third_approver = self._get_auto_third_approver()
        if auto_second_approver:
            self.second_approver_id = auto_second_approver
        if auto_third_approver:
            self.third_approver_id = auto_third_approver
        return {
            'domain': {
                'second_approver_id': domain,
                'third_approver_id': domain,
            }
        }

    def _is_valid_approver(self, user):
        return bool(user and user.id in self._get_allowed_approver_user_ids())

    @api.constrains('second_approver_id', 'third_approver_id')
    def _check_attendance_officer_approvers(self):
        for ticket in self:
            if ticket.second_approver_id and not self._is_valid_approver(ticket.second_approver_id):
                raise UserError(_('Second approver is not in the allowed approver list.'))
            if ticket.third_approver_id and not self._is_valid_approver(ticket.third_approver_id):
                raise UserError(_('Third approver is not in the allowed approver list.'))

    def _notify_approver(self, approver, message_body):
        self.ensure_one()
        if not approver or approver.share or not approver.partner_id:
            return
        try:
            bot_user = (
                self.env.ref("business_discuss_bots.user_bot_gate_ticket", raise_if_not_found=False)
                or self.env.ref("base.user_root")
            )
            bot_partner = bot_user.partner_id if bot_user else False
            if not bot_partner:
                return
            channel_model = self.env["discuss.channel"].sudo()
            mixed_channels = channel_model.search(
                [
                    ("channel_type", "=", "chat"),
                    ("channel_member_ids.partner_id", "in", [bot_partner.id]),
                    ("channel_member_ids.partner_id", "in", [approver.partner_id.id]),
                ]
            ).filtered(lambda c: len(c.channel_member_ids.partner_id) > 2)
            if mixed_channels:
                mixed_channels.unlink()
            chat = (
                channel_model
                .with_user(bot_user)
                ._get_or_create_chat([approver.partner_id.id], pin=True)
            )
            chat.with_user(bot_user).sudo().message_post(
                body=Markup(message_body) if not isinstance(message_body, Markup) else message_body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:
            _logger.exception(
                "hr_employee_gate_ticket: failed to send gate-ticket bot chat ticket_id=%s user_id=%s",
                self.id,
                approver.id,
            )

    def action_submit(self):
        for ticket in self:
            if ticket.state != 'draft':
                raise UserError(_('Only draft tickets can be submitted.'))
            ticket.state = 'confirm'
            if ticket.approver_id:
                check_in_formatted = ticket.check_in.strftime('%H:%M ngày %d/%m/%Y') if ticket.check_in else ''
                ticket._notify_approver(
                    ticket.approver_id,
                    _(
                        'Nhân viên <b>%(employee)s</b> xin giấy ra cổng lúc %(time)s, Trưởng bộ phận vào GATETICKET -> GATEWAY ĐỂ PHÊ DUYỆT',
                        employee=ticket.employee_id.name,
                        time=check_in_formatted,
                    ),
                )

    def action_first_approve(self):
        for ticket in self:
            if ticket.state not in ['confirm', 'refuse']:
                raise UserError(_('Only tickets in first approval or refused state can be approved.'))
            if ticket.approver_id and ticket.approver_id != self.env.user and not self.env.user.has_group('base.group_system'):
                raise UserError(_('Only the assigned first approver or administrators can do first approval.'))
            ticket.state = 'second_approve'
            if ticket.second_approver_id:
                check_in_formatted = ticket.check_in.strftime('%H:%M ngày %d/%m/%Y') if ticket.check_in else ''
                ticket._notify_approver(
                    ticket.second_approver_id,
                    _(
                        'Nhân viên <b>%(employee)s</b> xin giấy ra cổng lúc %(time)s, Trưởng bộ phận vào GATETICKET -> GATEWAY ĐỂ PHÊ DUYỆT',
                        employee=ticket.employee_id.name,
                        time=check_in_formatted,
                    ),
                )
            if ticket.employee_id.user_id:
                ticket._notify_approver(
                    ticket.employee_id.user_id,
                    _(
                        'Your gateway ticket has been approved by <b>%(approver)s</b>. '
                        'Waiting for second approval.',
                        approver=self.env.user.name,
                    ),
                )

    def action_second_approve(self):
        for ticket in self:
            if ticket.state != 'second_approve':
                raise UserError(_('Only tickets in second approval state can be approved.'))
            if not self.env.user.has_group('hr_attendance.group_hr_attendance_user') and not self.env.user.has_group('base.group_system'):
                raise UserError(_('Only users with Attendance Officer role or administrators can do second approval.'))
            if ticket.second_approver_id and ticket.second_approver_id != self.env.user and not self.env.user.has_group('base.group_system'):
                raise UserError(_('Only the assigned second approver or administrators can do second approval.'))
            ticket.state = 'validate'
            if ticket.employee_id.user_id:
                ticket._notify_approver(
                    ticket.employee_id.user_id,
                    _('Đơn ra cổng của bạn đã được chấp nhận.'),
                )
            if ticket.third_approver_id:
                ticket._notify_approver(
                    ticket.third_approver_id,
                    _(
                        'Nhân viên <b>%(employee)s</b> đã được chấp thuận ra cổng. (Notification only)',
                        employee=ticket.employee_id.name,
                    ),
                )
            ticket.message_post(
                body=_('Gateway ticket fully approved.'),
                subtype_xmlid='mail.mt_comment',
            )


    def action_refuse(self):
        for ticket in self:
            if ticket.state not in ['confirm', 'second_approve', 'validate']:
                raise UserError(_('Only confirmed, second approval, or approved tickets can be refused.'))
            ticket.state = 'refuse'
            if ticket.employee_id.user_id:
                ticket._notify_approver(
                    ticket.employee_id.user_id,
                    _(
                        'Your gateway ticket has been <b>refused</b> by <b>%(approver)s</b>.',
                        approver=self.env.user.name,
                    ),
                )
            approvers_to_notify = []
            if ticket.approver_id and ticket.approver_id != self.env.user:
                approvers_to_notify.append(ticket.approver_id)
            if ticket.second_approver_id and ticket.second_approver_id != self.env.user:
                approvers_to_notify.append(ticket.second_approver_id)
            if ticket.third_approver_id and ticket.third_approver_id != self.env.user:
                approvers_to_notify.append(ticket.third_approver_id)
            for approver in approvers_to_notify:
                ticket._notify_approver(
                    approver,
                    _(
                        'Gateway ticket for <b>%(employee)s</b> has been refused by <b>%(refuser)s</b>.',
                        employee=ticket.employee_id.name,
                        refuser=self.env.user.name,
                    ),
                )

    def action_draft(self):
        for ticket in self:
            ticket.state = 'draft'

    @api.model_create_multi
    def create(self, vals_list):
        auto_second_approver = self._get_auto_second_approver()
        auto_approver = self._get_auto_third_approver()
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.employee.gate.ticket') or _('New')
            if auto_second_approver and not vals.get('second_approver_id'):
                vals['second_approver_id'] = auto_second_approver.id
            if auto_approver and not vals.get('third_approver_id'):
                vals['third_approver_id'] = auto_approver.id
        tickets = super().create(vals_list)
        for ticket in tickets:
            _logger.info('Created gate ticket ID %s', ticket.id)
            ticket._generate_gate_ticket_pdf()
        return tickets

    def write(self, vals):
        if 'employee_id' in vals and ('second_approver_id' not in vals or 'third_approver_id' not in vals):
            auto_second_approver = self._get_auto_second_approver()
            auto_approver = self._get_auto_third_approver()
            new_vals = dict(vals)
            if auto_second_approver and 'second_approver_id' not in vals:
                new_vals['second_approver_id'] = auto_second_approver.id
            if auto_approver and 'third_approver_id' not in vals:
                new_vals['third_approver_id'] = auto_approver.id
            vals = new_vals
        result = super().write(vals)
        if any(
            field in vals
            for field in ['gate_ticket', 'gate_items', 'checkout_time', 'approver_id', 'second_approver_id', 'third_approver_id']
        ):
            for ticket in self:
                ticket._generate_gate_ticket_pdf()
        return result

    def _generate_gate_ticket_pdf(self):
        self.ensure_one()
        _logger.info('Attempting to generate PDF for gate ticket %s', self.id)
        try:
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'hr_employee_gate_ticket.action_report_gate_ticket',
                res_ids=[self.id],
            )
            attachment_vals = {
                'name': f'Gate_Ticket_{self.employee_id.name}_{self.id}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf',
            }
            old_attachments = self.env['ir.attachment'].search(
                [
                    ('res_model', '=', self._name),
                    ('res_id', '=', self.id),
                    ('name', 'like', 'Gate_Ticket_%'),
                ]
            )
            if old_attachments:
                old_attachments.unlink()
            self.env['ir.attachment'].create(attachment_vals)
        except Exception:
            _logger.exception('Error generating gate ticket PDF for %s', self.id)
