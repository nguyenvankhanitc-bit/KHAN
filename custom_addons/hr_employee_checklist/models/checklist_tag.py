# -*- coding: utf-8 -*-

from random import randint

from odoo import api, fields, models


class ChecklistTagCategory(models.Model):
    _name = 'checklist.tag.category'
    _description = 'Checklist Tag Category'
    _order = 'sequence'

    def _default_sequence(self):
        return (self.search([], order='sequence desc', limit=1).sequence or 0) + 1

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=_default_sequence)
    tag_ids = fields.One2many('checklist.tag', 'category_id', string='Tags')


class ChecklistTag(models.Model):
    _name = 'checklist.tag'
    _description = 'Checklist Tag'
    _order = 'category_sequence, sequence, id'

    def _default_color(self):
        return randint(1, 11)

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=0)
    category_id = fields.Many2one(
        'checklist.tag.category', string='Category',
        required=True, index=True, ondelete='cascade')
    category_sequence = fields.Integer(
        related='category_id.sequence', string='Category Sequence', store=True)
    color = fields.Integer(
        string='Color Index', default=lambda self: self._default_color())
