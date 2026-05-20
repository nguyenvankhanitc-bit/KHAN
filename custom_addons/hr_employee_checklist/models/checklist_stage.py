# -*- coding: utf-8 -*-

from odoo import fields, models


class ChecklistStage(models.Model):
    _name = 'checklist.stage'
    _description = 'Checklist Stage'
    _order = 'sequence, name'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    description = fields.Text(string='Stage Description', translate=True)
    sequence = fields.Integer('Sequence', default=1)
    fold = fields.Boolean(string='Folded in Kanban', default=False)
    pipe_end = fields.Boolean(
        string='End Stage', default=False,
        help='Checklists will automatically be moved into this stage when they are finished.')
