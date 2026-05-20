# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ChecklistScheduleLine(models.Model):
    """One employee row in the monthly schedule (Lịch làm việc).

    Columns mirror the physical schedule table:
      HỌ VÀ TÊN | Miền | Mã bộ phận | Mã chức vụ
      | N1 … N31  (shift codes, e.g. CA1, CA2, OFF, X)
    """
    _name = 'checklist.schedule.line'
    _description = 'Checklist Schedule Line'
    _order = 'checklist_id, sequence, id'

    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist Sheet',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('Sequence', default=10)

    # --- Employee & auto-filled info ---
    employee_id = fields.Many2one(
        'hr.employee', string='Họ và tên',
        required=True, index=True, ondelete='restrict')
    mien = fields.Char(
        'Miền',
        compute='_compute_employee_fields', store=True, readonly=False,
        help='Region / area — auto-filled from employee, can be overridden')
    ma_bo_phan = fields.Char(
        'Mã bộ phận',
        compute='_compute_employee_fields', store=True, readonly=False,
        help='Department code — auto-filled from employee department name')
    ma_chuc_vu = fields.Char(
        'Mã chức vụ',
        compute='_compute_employee_fields', store=True, readonly=False,
        help='Job code — auto-filled from employee job name')

    # --- 31 daily shift-code columns ---
    n01 = fields.Char('N1')
    n02 = fields.Char('N2')
    n03 = fields.Char('N3')
    n04 = fields.Char('N4')
    n05 = fields.Char('N5')
    n06 = fields.Char('N6')
    n07 = fields.Char('N7')
    n08 = fields.Char('N8')
    n09 = fields.Char('N9')
    n10 = fields.Char('N10')
    n11 = fields.Char('N11')
    n12 = fields.Char('N12')
    n13 = fields.Char('N13')
    n14 = fields.Char('N14')
    n15 = fields.Char('N15')
    n16 = fields.Char('N16')
    n17 = fields.Char('N17')
    n18 = fields.Char('N18')
    n19 = fields.Char('N19')
    n20 = fields.Char('N20')
    n21 = fields.Char('N21')
    n22 = fields.Char('N22')
    n23 = fields.Char('N23')
    n24 = fields.Char('N24')
    n25 = fields.Char('N25')
    n26 = fields.Char('N26')
    n27 = fields.Char('N27')
    n28 = fields.Char('N28')
    n29 = fields.Char('N29')
    n30 = fields.Char('N30')
    n31 = fields.Char('N31')

    @api.depends('employee_id')
    def _compute_employee_fields(self):
        for line in self:
            emp = line.employee_id
            if emp:
                line.ma_bo_phan = emp.department_id.name or ''
                line.ma_chuc_vu = emp.job_id.name or ''
                # 'mien' has no standard Odoo field; leave blank for manual entry
                # unless the employee already has a value stored on the line
                if not line.mien:
                    line.mien = ''
            else:
                line.ma_bo_phan = ''
                line.ma_chuc_vu = ''
                line.mien = ''
