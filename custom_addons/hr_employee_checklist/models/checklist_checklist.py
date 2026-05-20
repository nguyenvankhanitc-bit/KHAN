# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ChecklistChecklist(models.Model):
    _name = 'checklist.checklist'
    _description = 'Employee Checklist Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, id'

    name = fields.Char(string='Title', required=True, tracking=True)
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', required=True, tracking=True,
       default=lambda self: str(fields.Date.today().month))
    year = fields.Integer(string='Year', required=True, tracking=True,
                          default=lambda self: fields.Date.today().year)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        default=lambda self: self.env.user)
    stage_id = fields.Many2one(
        'checklist.stage', string='Stage', ondelete='restrict',
        default=lambda self: self.env['checklist.stage'].search([], limit=1),
        tracking=True, copy=False)
    active = fields.Boolean(default=True)
    note = fields.Html(string='Note')
    employee_entry_ids = fields.One2many(
        'checklist.employee.entry', 'checklist_id', string='Employee Entries')
    schedule_line_ids = fields.One2many(
        'checklist.schedule.line', 'checklist_id', string='Schedule Lines')

    @api.constrains('year')
    def _check_year(self):
        for rec in self:
            if rec.year < 2000 or rec.year > 2100:
                raise ValidationError(_('Year must be between 2000 and 2100.'))

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._('%s (copy)', rec.name))
                for rec, vals in zip(self, vals_list)]
