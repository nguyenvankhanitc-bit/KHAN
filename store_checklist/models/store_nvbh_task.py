import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TASK_GROUPS = [
    ('I', 'I. TRANG THIẾT BỊ, VẬT TƯ'),
    ('II', 'II. HÀNG HÓA, CTKM'),
    ('III', 'III. NHÂN VIÊN'),
    ('IV', 'IV. CÔNG VIỆC HẰNG NGÀY'),
    ('V', 'V. MEDIA'),
    ('VI', 'VI. ĐỐI THỦ CẠNH TRANH'),
]
TASK_SHIFTS = [
    ('morning', 'Ca sáng'),
    ('full', 'Ca Full'),
    ('afternoon', 'Ca chiều'),
]
TASK_STORE_TYPES = [('ALL', 'ALL'), ('TTTM', 'TTTM')]


class StoreNvbhTask(models.Model):
    _name = 'store.nvbh.task'
    _inherit = 'store.perm.mixin'
    _description = 'Công việc checklist NVBH'
    _order = 'sequence, id'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return 'nvbh_task'

    @api.model
    def _perm_key_vals(self, vals):
        return 'nvbh_task'

    sequence = fields.Integer(default=10)
    name = fields.Char(string='Tên công việc', required=True)
    task_group = fields.Selection(TASK_GROUPS, string='Nhóm công việc')
    # Loại ca áp dụng: chọn nhiều loại ca (SÁNG, CHIỀU, FULL, GÃY SÁNG, GÃY CHIỀU); mã ca chi tiết tự tra trong Danh mục ca
    shift_type_ids = fields.Many2many('store.shift.type', 'store_nvbh_task_shift_type_rel', 'task_id', 'type_id', string='Loại ca áp dụng')
    shift_codes = fields.Char(string='Mã ca áp dụng', compute='_compute_shift_codes',
                              help='Tự tra từ Danh mục ca theo các Loại ca áp dụng đã chọn')
    shift_type = fields.Selection(TASK_SHIFTS, string='Loại ca (cũ)')  # chỉ còn để dữ liệu mẫu cũ không lỗi
    store_type = fields.Selection(TASK_STORE_TYPES, string='Loại cửa hàng', required=True, default='ALL')
    time_slot = fields.Char(string='Khung giờ / Thời hạn')
    executor = fields.Char(string='Người thực hiện')
    controller = fields.Char(string='Người kiểm soát', default='CHT')
    final_check = fields.Char(string='Bộ phận phúc tra cuối')
    score = fields.Integer(string='Điểm chuẩn', default=5)

    @api.depends('shift_type_ids')
    def _compute_shift_codes(self):
        Shift = self.env['store.shift']
        for rec in self:
            codes = rec.shift_type_ids.mapped('code')
            rec.shift_codes = ', '.join(Shift.search([('shift_type', 'in', codes)]).mapped('code')) if codes else False

    def write(self, vals):
        res = super().write(vals)
        if 'score' in vals:
            self._sync_check_line_scores()
        return res

    def _sync_check_line_scores(self):
        """Điểm chuẩn đổi trong Cài đặt thì cập nhật lại điểm của các dòng checklist đã tạo (và Điểm đạt theo KQ đánh giá)."""
        lines = self.env['store.nvbh.check.line'].sudo().search([('task_id', 'in', self.ids)])
        for task in self:
            todo = lines.filtered(lambda l: l.task_id == task and l.max_score != task.score)
            if todo:
                todo.write({'max_score': task.score})

    @api.model
    def _sync_all_check_line_scores(self):
        """Đồng bộ một lần mọi dòng checklist cũ theo Điểm chuẩn hiện tại của công việc."""
        self.search([])._sync_check_line_scores()

    def init(self):
        """Chuyển Loại ca áp dụng cũ (theo Nhóm mã ca) sang Loại ca của các mã ca trong nhóm đó, chạy một lần."""
        cr = self.env.cr
        cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name IN "
                   "('store_nvbh_task_group_rel', 'store_nvbh_task_shift_type_rel', 'store_shift_type') HAVING count(*) = 3")
        if not cr.fetchone():
            return
        cr.execute("""
            INSERT INTO store_nvbh_task_shift_type_rel (task_id, type_id)
            SELECT DISTINCT r.task_id, t.id
            FROM store_nvbh_task_group_rel r
            JOIN store_shift s ON s.group_id = r.group_id
            JOIN store_shift_type t ON t.code = s.shift_type
            ON CONFLICT DO NOTHING
        """)
        cr.execute("DELETE FROM store_nvbh_task_group_rel")

    def action_open_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'views': [(False, 'form')], 'target': 'new', 'context': {'dialog_size': 'large'},
        }

    _XLS_HEAD = ['STT', 'Nhóm công việc', 'Tên công việc', 'Loại ca áp dụng', 'Loại cửa hàng', 'Khung giờ / Thời hạn',
                 'Người thực hiện', 'Người kiểm soát', 'Bộ phận phúc tra cuối', 'Điểm chuẩn']

    @api.model
    def export_xlsx(self):
        """Xuất Danh sách công việc NVBH ra Excel. File xuất ra nhập lại được."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        tasks = self.search([], order='sequence, id')
        groups = dict(TASK_GROUPS)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Cong viec NVBH')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center',
                                'valign': 'vcenter', 'border': 1, 'text_wrap': True})
        cell = book.add_format({'border': 1, 'valign': 'top', 'text_wrap': True})
        num = book.add_format({'border': 1, 'valign': 'top', 'num_format': '0.##'})
        for i, (h, w) in enumerate(zip(self._XLS_HEAD, [6, 30, 52, 28, 14, 26, 26, 18, 22, 12])):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        for r, t in enumerate(tasks, 1):
            vals = [t.sequence, groups.get(t.task_group, ''), t.name, ', '.join(t.shift_type_ids.mapped('name')), t.store_type or '',
                    t.time_slot or '', t.executor or '', t.controller or '', t.final_check or '', t.score]
            for c, v in enumerate(vals):
                sheet.write(r, c, v, num if c in (0, 9) else cell)
        sheet.write(len(tasks) + 1, 8, 'Tổng', head)
        sheet.write(len(tasks) + 1, 9, sum(tasks.mapped('score')), num)
        sheet.freeze_panes(1, 0)
        book.close()
        return {'name': 'Cong_viec_NVBH.xlsx', 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def import_xlsx(self, data):
        """Nhập Danh sách công việc NVBH từ Excel (cùng cột với file xuất): trùng Tên công việc thì cập nhật,
        chưa có thì thêm mới. Dòng lỗi được bỏ qua và báo lại; các dòng hợp lệ vẫn được lưu."""
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise UserError(_('Máy chủ chưa cài thư viện openpyxl để đọc file Excel.'))
        try:
            wb = load_workbook(io.BytesIO(base64.b64decode(data)), data_only=True, read_only=True)
            rows = list(wb.worksheets[0].iter_rows(values_only=True))
        except Exception:
            raise UserError(_('Không đọc được file. Hãy dùng file .xlsx (xuất từ nút Xuất Excel).'))

        def txt(v):
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return ('%s' % v).strip() if v is not None else ''

        hi = next((i for i, r in enumerate(rows) if 'tên công việc' in [txt(c).casefold() for c in r]), None)
        if hi is None:
            raise UserError(_('Không tìm thấy dòng tiêu đề có cột "Tên công việc".'))
        col = {txt(c).casefold(): i for i, c in enumerate(rows[hi]) if txt(c)}

        def get(r, name):
            i = col.get(name.casefold())
            return txt(r[i]) if i is not None and i < len(r) else ''

        # nhóm: nhận mã (I, II...) hoặc nhãn đầy đủ; ca: nhận khóa hoặc nhãn
        group_map = {}
        for k, label in TASK_GROUPS:
            group_map[k.casefold()] = k
            group_map[label.casefold()] = k
            group_map[label.split('.', 1)[-1].strip().casefold()] = k
        Shift = self.env['store.shift']
        types_by_key = {}
        for t in self.env['store.shift.type'].search([]):
            types_by_key[t.name.casefold()] = t
            types_by_key[t.code.casefold()] = t
        for label, code in (('ca sáng', 'morning'), ('ca chiều', 'afternoon'), ('ca full', 'full')):
            if code in types_by_key:
                types_by_key[label] = types_by_key[code]
        shifts_by_code = {sh.code.casefold(): sh for sh in Shift.search([])}

        def parse_types(text):
            """Loại ca cách nhau dấu phẩy / | / xuống dòng (SÁNG, CHIỀU, FULL, GÃY SÁNG, GÃY CHIỀU); cũng nhận nhãn cũ (Ca sáng...) hoặc một Mã ca."""
            Type = self.env['store.shift.type']
            found, bad = Type, []
            for part in [x.strip() for x in text.replace('\n', ',').replace('|', ',').replace(';', ',').split(',') if x.strip()]:
                key = part.casefold()
                if key in types_by_key:
                    found |= types_by_key[key]
                elif key in shifts_by_code and shifts_by_code[key].shift_type_id:
                    found |= shifts_by_code[key].shift_type_id
                else:
                    bad.append(part)
            return found, bad

        store_types = {k for k, _l in TASK_STORE_TYPES}

        created = updated = 0
        errors = []
        next_seq = (self.search([], order='sequence desc', limit=1).sequence or 0) + 1
        for n, r in enumerate(rows[hi + 1:], hi + 2):
            name = get(r, 'Tên công việc')
            if not name or name.casefold() == 'tổng':
                continue
            shift_txt = get(r, 'Loại ca áp dụng')
            types, bad = parse_types(shift_txt)
            if bad or not types:
                errors.append('Dòng %s: Loại ca áp dụng "%s" không hợp lệ (SÁNG, CHIỀU, FULL, GÃY SÁNG, GÃY CHIỀU; cách nhau dấu phẩy)' % (n, shift_txt))
                continue
            vals = {'name': name, 'shift_type_ids': [(6, 0, types.ids)]}
            if 'nhóm công việc' in col:
                gtxt = get(r, 'Nhóm công việc')
                if gtxt and gtxt.casefold() not in group_map:
                    errors.append('Dòng %s: Nhóm công việc "%s" không hợp lệ' % (n, gtxt))
                    continue
                vals['task_group'] = group_map.get(gtxt.casefold(), False)
            if 'loại cửa hàng' in col and get(r, 'Loại cửa hàng'):
                st = get(r, 'Loại cửa hàng').upper()
                if st not in store_types:
                    errors.append('Dòng %s: Loại cửa hàng "%s" không hợp lệ (ALL / TTTM)' % (n, get(r, 'Loại cửa hàng')))
                    continue
                vals['store_type'] = st
            try:
                if get(r, 'STT'):
                    vals['sequence'] = int(float(get(r, 'STT').replace(',', '.')))
                if get(r, 'Điểm chuẩn'):
                    vals['score'] = int(float(get(r, 'Điểm chuẩn').replace(',', '.')))
            except ValueError:
                errors.append('Dòng %s: STT hoặc Điểm chuẩn không phải số' % n)
                continue
            for xls, fname in (('Khung giờ / Thời hạn', 'time_slot'), ('Người thực hiện', 'executor'),
                               ('Người kiểm soát', 'controller'), ('Bộ phận phúc tra cuối', 'final_check')):
                if xls.casefold() in col:
                    vals[fname] = get(r, xls)
            rec = self.search([('name', '=', name)], limit=1)
            try:
                if rec:
                    rec.write(vals)
                    updated += 1
                else:
                    vals.setdefault('sequence', next_seq)
                    next_seq = max(next_seq, vals['sequence']) + 1
                    self.create(vals)
                    created += 1
            except Exception as e:  # lỗi quyền / dữ liệu: bỏ qua dòng và báo lại
                errors.append('Dòng %s: %s' % (n, getattr(e, 'args', [e])[0]))
        return {'created': created, 'updated': updated, 'errors': errors[:20], 'error_count': len(errors)}
