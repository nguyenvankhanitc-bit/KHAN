# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ChecklistEmployeeEntry(models.Model):
    """One employee block within a checklist sheet.
    Groups all checklist lines belonging to a single employee.
    """
    _name = 'checklist.employee.entry'
    _description = 'Checklist Employee Entry'
    _order = 'checklist_id, sequence, id'

    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist Sheet',
        required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, index=True, ondelete='restrict')
    sequence = fields.Integer('Sequence', default=10)
    line_ids = fields.One2many(
        'checklist.line', 'employee_entry_id', string='Checklist Items')

    # --- Aggregated summary (computed from child lines) ---
    total_lines = fields.Integer(
        'Total Items', compute='_compute_summary', store=True)
    total_so_diem = fields.Float(
        'Total Score', compute='_compute_summary', store=True, digits=(16, 2))
    xep_loai = fields.Selection([
        ('excellent', 'Xuất sắc'),
        ('good', 'Tốt'),
        ('average', 'Trung bình'),
        ('poor', 'Yếu'),
    ], string='Xếp loại', compute='_compute_summary', store=True)

    @api.depends('line_ids.so_diem')
    def _compute_summary(self):
        for entry in self:
            lines = entry.line_ids
            entry.total_lines = len(lines)
            total = sum(lines.mapped('so_diem'))
            entry.total_so_diem = total
            if total >= 90:
                entry.xep_loai = 'excellent'
            elif total >= 75:
                entry.xep_loai = 'good'
            elif total >= 50:
                entry.xep_loai = 'average'
            else:
                entry.xep_loai = 'poor'
