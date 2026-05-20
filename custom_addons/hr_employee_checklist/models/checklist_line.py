# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ChecklistLine(models.Model):
    """One inspection/checklist item row.

    Columns mirror the physical inspection table:
      STT | NỘI DUNG | NGƯỜI KS | PHẠM VI | KHUNG GIỜ | Lần 1 | Lần 2 | Lần 3
      | ĐIỂM | day_01…day_31 | TL(%)ĐẠT | Số lần Đạt | Có TH ko Đạt
      | Số điểm | Xếp loại | Ghi chú
    """
    _name = 'checklist.line'
    _description = 'Checklist Item Line'
    _order = 'employee_entry_id, sequence, id'

    employee_entry_id = fields.Many2one(
        'checklist.employee.entry', string='Employee Entry',
        required=True, ondelete='cascade', index=True)
    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist Sheet',
        related='employee_entry_id.checklist_id', store=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        related='employee_entry_id.employee_id', store=True)

    sequence = fields.Integer('STT', default=10)
    noi_dung = fields.Char('Nội dung', required=True)
    nguoi_ks = fields.Char('Người KS')
    pham_vi = fields.Char('Phạm vi')
    khung_gio = fields.Char('Khung giờ')
    lan_1 = fields.Char('Lần 1')
    lan_2 = fields.Char('Lần 2')
    lan_3 = fields.Char('Lần 3')
    diem = fields.Float('Điểm', default=0.0, digits=(16, 2))

    # --- 31 daily checkbox columns ---
    day_01 = fields.Boolean('1')
    day_02 = fields.Boolean('2')
    day_03 = fields.Boolean('3')
    day_04 = fields.Boolean('4')
    day_05 = fields.Boolean('5')
    day_06 = fields.Boolean('6')
    day_07 = fields.Boolean('7')
    day_08 = fields.Boolean('8')
    day_09 = fields.Boolean('9')
    day_10 = fields.Boolean('10')
    day_11 = fields.Boolean('11')
    day_12 = fields.Boolean('12')
    day_13 = fields.Boolean('13')
    day_14 = fields.Boolean('14')
    day_15 = fields.Boolean('15')
    day_16 = fields.Boolean('16')
    day_17 = fields.Boolean('17')
    day_18 = fields.Boolean('18')
    day_19 = fields.Boolean('19')
    day_20 = fields.Boolean('20')
    day_21 = fields.Boolean('21')
    day_22 = fields.Boolean('22')
    day_23 = fields.Boolean('23')
    day_24 = fields.Boolean('24')
    day_25 = fields.Boolean('25')
    day_26 = fields.Boolean('26')
    day_27 = fields.Boolean('27')
    day_28 = fields.Boolean('28')
    day_29 = fields.Boolean('29')
    day_30 = fields.Boolean('30')
    day_31 = fields.Boolean('31')

    # --- Computed summary columns ---
    so_lan_dat = fields.Integer(
        'Số lần Đạt', compute='_compute_summary', store=True)
    ty_le_dat = fields.Float(
        'TL(%)Đạt', compute='_compute_summary', store=True, digits=(16, 2))
    co_th_ko_dat = fields.Boolean(
        'Có TH ko Đạt', compute='_compute_summary', store=True,
        help='True nếu có ít nhất 1 ngày không đạt trong tháng')
    so_diem = fields.Float(
        'Số điểm', compute='_compute_summary', store=True, digits=(16, 2))
    xep_loai = fields.Selection([
        ('excellent', 'Xuất sắc'),
        ('good', 'Tốt'),
        ('average', 'Trung bình'),
        ('poor', 'Yếu'),
    ], string='Xếp loại', compute='_compute_summary', store=True)
    ghi_chu = fields.Char('Ghi chú')

    _DAY_FIELDS = [f'day_{str(i).zfill(2)}' for i in range(1, 32)]

    def _get_checked_days(self):
        """Return number of days checked True for this line."""
        self.ensure_one()
        return sum(1 for f in self._DAY_FIELDS if self[f])

    def _get_active_days(self):
        """Return total number of active day columns for the month.
        Uses the parent checklist month/year to find the real number of days.
        Falls back to 31 if not determinable.
        """
        self.ensure_one()
        checklist = self.checklist_id
        if checklist and checklist.month and checklist.year:
            import calendar
            return calendar.monthrange(checklist.year, int(checklist.month))[1]
        return 31

    @api.depends(*_DAY_FIELDS, 'diem',
                 'checklist_id.month', 'checklist_id.year')
    def _compute_summary(self):
        for line in self:
            active_days = line._get_active_days()
            checked = sum(1 for f in line._DAY_FIELDS[:active_days] if line[f])
            unchecked = active_days - checked

            line.so_lan_dat = checked
            line.ty_le_dat = round(checked / active_days * 100, 2) if active_days else 0.0
            line.co_th_ko_dat = unchecked > 0
            # Score: proportional to pass rate
            line.so_diem = round(line.diem * checked / active_days, 2) if active_days else 0.0

            rate = line.ty_le_dat
            if rate >= 95:
                line.xep_loai = 'excellent'
            elif rate >= 80:
                line.xep_loai = 'good'
            elif rate >= 60:
                line.xep_loai = 'average'
            else:
                line.xep_loai = 'poor'
