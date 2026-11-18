import re

from odoo import api, fields, models

SHIFT_TYPES = [
    ('full', 'FULL'),
    ('split_pm', 'GÃY CHIỀU'),
    ('split_am', 'GÃY SÁNG'),
    ('morning', 'SÁNG'),
    ('afternoon', 'CHIỀU'),
]


class StoreShiftType(models.Model):
    """Loại ca (SÁNG, CHIỀU, FULL, GÃY SÁNG, GÃY CHIỀU): danh mục để chọn "Loại ca áp dụng" cho công việc NVBH.
    Mỗi loại ca ứng với các Mã ca có cùng "Loại ca" trong Danh mục ca."""
    _name = 'store.shift.type'
    _description = 'Loại ca'
    _order = 'sequence, id'

    _code_uniq = models.Constraint('UNIQUE(code)', 'Loại ca đã tồn tại.')

    sequence = fields.Integer(default=10)
    name = fields.Char(string='Loại ca', required=True)
    code = fields.Char(string='Khóa', required=True, help='Khớp với trường Loại ca của Mã ca (morning, afternoon, full, split_am, split_pm).')
    shift_ids = fields.One2many('store.shift', 'shift_type_id', string='Mã ca')

    def init(self):
        cr = self.env.cr
        for seq, (code, label) in enumerate([('morning', 'SÁNG'), ('afternoon', 'CHIỀU'), ('full', 'FULL'),
                                             ('split_am', 'GÃY SÁNG'), ('split_pm', 'GÃY CHIỀU')], 1):
            cr.execute("INSERT INTO store_shift_type (code, name, sequence, create_date, write_date) "
                       "SELECT %s, %s, %s, now(), now() WHERE NOT EXISTS (SELECT 1 FROM store_shift_type WHERE code = %s)",
                       (code, label, seq, code))


class StoreShiftGroup(models.Model):
    """Nhóm mã ca (ví dụ "F1, F2, ..., F12"): các mã ca cùng nhóm; công việc NVBH chọn Loại ca áp dụng theo nhóm này."""
    _name = 'store.shift.group'
    _description = 'Nhóm mã ca'
    _order = 'sequence, id'

    _name_uniq = models.Constraint('UNIQUE(name)', 'Nhóm mã ca đã tồn tại.')

    sequence = fields.Integer(default=10)
    name = fields.Char(string='Nhóm mã ca', required=True)
    shift_ids = fields.One2many('store.shift', 'group_id', string='Mã ca')


class StoreShift(models.Model):
    _name = 'store.shift'
    _inherit = 'store.perm.mixin'
    _description = 'Mã ca làm việc'
    _order = 'sequence, id'
    _rec_name = 'code'  # hiển thị F1, F2, GC1... khi chọn ca ở nơi khác (Many2one)
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return 'shift'

    @api.model
    def _perm_key_vals(self, vals):
        return 'shift'

    _code_uniq = models.Constraint('UNIQUE(code)', 'Mã ca đã tồn tại.')

    sequence = fields.Integer(default=10)
    code = fields.Char(string='Mã ca', required=True)
    shift_name = fields.Char(string='Tên ca', help='Ví dụ: Ca sáng 1')
    group_id = fields.Many2one('store.shift.group', string='Nhóm mã ca', ondelete='set null', index=True,
                               help='Chọn nhóm có sẵn hoặc gõ tên mới để tạo nhóm (ví dụ F1, F2, ..., F12).')
    start_time = fields.Float(string='Giờ vào')
    end_time = fields.Float(string='Giờ ra')
    hours = fields.Float(string='Số giờ', compute='_compute_hours', store=True)
    shift_type = fields.Selection(SHIFT_TYPES, string='Loại ca', required=True, default='full')
    shift_type_id = fields.Many2one('store.shift.type', string='Loại ca (danh mục)', compute='_compute_shift_type_id', store=True)

    def init(self):
        """Chuyển Nhóm mã ca (trước là ô chữ) thành danh mục nhóm; lần đầu chưa có nhóm nào thì gom theo tiền tố chữ."""
        cr = self.env.cr
        # liên kết Mã ca -> Loại ca (danh mục) theo trường Loại ca
        cr.execute("UPDATE store_shift s SET shift_type_id = t.id FROM store_shift_type t "
                   "WHERE t.code = s.shift_type AND s.shift_type_id IS DISTINCT FROM t.id")
        cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'store_shift_group'")
        if not cr.fetchone():
            return

        def group_id(label):
            cr.execute("SELECT id FROM store_shift_group WHERE name = %s", (label,))
            row = cr.fetchone()
            if row:
                return row[0]
            cr.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM store_shift_group")
            seq = cr.fetchone()[0]
            cr.execute("INSERT INTO store_shift_group (name, sequence, create_date, write_date) "
                       "VALUES (%s, %s, now(), now()) RETURNING id", (label, seq))
            return cr.fetchone()[0]

        # Tên ca còn trống -> "Ca sáng 1", "Ca chiều 2"... theo loại ca và số trong mã ca
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'store_shift' AND column_name = 'shift_name'")
        if cr.fetchone():
            cr.execute("""
                UPDATE store_shift SET shift_name = CASE shift_type
                        WHEN 'morning' THEN 'Ca sáng' WHEN 'afternoon' THEN 'Ca chiều' WHEN 'full' THEN 'Ca full'
                        WHEN 'split_am' THEN 'Ca gãy sáng' WHEN 'split_pm' THEN 'Ca gãy chiều' ELSE 'Ca' END
                    || COALESCE(' ' || substring(code from '[0-9]+$'), '')
                WHERE shift_name IS NULL OR shift_name = ''
            """)
        # 1) ô chữ cũ -> nhóm (chạy một lần: xong thì xóa nội dung cột cũ)
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'store_shift' AND column_name = 'group_name'")
        if cr.fetchone():
            cr.execute("SELECT id, group_name FROM store_shift WHERE group_name IS NOT NULL AND group_name <> '' AND group_id IS NULL ORDER BY sequence, id")
            for sid, label in cr.fetchall():
                cr.execute("UPDATE store_shift SET group_id = %s WHERE id = %s", (group_id(label.strip()), sid))
            cr.execute("UPDATE store_shift SET group_name = NULL WHERE group_name IS NOT NULL")
        # 2) cài mới: chưa có nhóm nào -> gom theo tiền tố chữ (F, GC, GS, S, C), mỗi nhóm ghi đủ các mã
        cr.execute("SELECT 1 FROM store_shift_group LIMIT 1")
        if cr.fetchone():
            return
        cr.execute("SELECT id, code FROM store_shift ORDER BY sequence, id")
        series = {}
        for rid, code in cr.fetchall():
            m = re.match(r'^([A-Za-z]+)(\d+)$', (code or '').strip())
            if m:
                series.setdefault(m.group(1).upper(), []).append((int(m.group(2)), rid, code.strip()))
        for prefix, items in series.items():
            cap = 12 if prefix == 'F' and len(items) > 12 else None  # nhóm F: F1..F12, F13 là mã riêng
            for part in ([i for i in items if cap is None or i[0] <= cap], [i for i in items if cap is not None and i[0] > cap]):
                if part:
                    gid = group_id(', '.join(i[2] for i in sorted(part)))
                    cr.execute("UPDATE store_shift SET group_id = %s WHERE id = ANY(%s)", (gid, [i[1] for i in part]))

    @api.depends('shift_type')
    def _compute_shift_type_id(self):
        types = {t.code: t for t in self.env['store.shift.type'].search([])}
        for rec in self:
            rec.shift_type_id = types.get(rec.shift_type)

    @api.depends('start_time', 'end_time')
    def _compute_hours(self):
        for rec in self:
            rec.hours = max(rec.end_time - rec.start_time, 0.0)

    def action_open_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'views': [(False, 'form')], 'target': 'new', 'context': {'dialog_size': 'large'},
        }
