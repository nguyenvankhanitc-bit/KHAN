import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TASK_GROUPS = [
    ('01', '01. Quản lý nhân sự và đào tạo'),
    ('02', '02. Quản lý vận hành cửa hàng'),
    ('03', '03. Quản lý tài sản, thiết bị và CCDC'),
    ('04', '04. Quản lý truyền thông và Marketing'),
    ('05', '05. Quản lý hàng hóa và tồn kho'),
    ('06', '06. POSM – Quản lý trưng bày và hình ảnh'),
    ('07', '07. Quản lý tài chính và doanh thu'),
    ('08', '08. Quản lý hành chính và an toàn'),
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
# Thứ áp dụng của công việc: (trường, nhãn, chỉ số thứ theo date.weekday())
TASK_WEEKDAYS = [('wd_mon', 'T2', 0), ('wd_tue', 'T3', 1), ('wd_wed', 'T4', 2), ('wd_thu', 'T5', 3),
                 ('wd_fri', 'T6', 4), ('wd_sat', 'T7', 5), ('wd_sun', 'CN', 6)]


class StoreNvbhTaskGroup(models.Model):
    _name = 'store.nvbh.task.group'
    _inherit = 'store.perm.mixin'
    _description = 'Nhóm công việc NVBH'
    _order = 'sequence, id'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return 'nvbh_task'

    @api.model
    def _perm_key_vals(self, vals):
        return 'nvbh_task'

    name = fields.Char(string='Nhóm công việc', required=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    active = fields.Boolean(default=True)

    def action_edit_popup(self):
        """Nút bút chì trên dòng nhóm của Danh sách công việc NVBH: sửa tên / thứ tự nhóm trong popup."""
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Sửa nhóm công việc', 'res_model': self._name, 'res_id': self.id,
                'views': [(self.env.ref('store_checklist.view_store_nvbh_task_group_form').id, 'form')], 'target': 'new'}

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            Line = self.env['store.nvbh.check.line'].sudo()
            for g in self:
                lines = Line.search([('task_id.group_id', '=', g.id), ('sub_category', '!=', g.name)])
                if lines:
                    lines.write({'sub_category': g.name})
        return res

    @api.model
    def _find_or_create(self, text):
        """Tìm nhóm theo tên (chuẩn hóa dấu gạch ngang) hoặc theo mã đầu (vd. "01"); chưa có thì tạo nhóm mới."""
        t = ' '.join((text or '').split())
        if not t:
            return self.browse()
        norm = lambda s: ' '.join((s or '').replace('–', '-').replace('—', '-').split()).casefold()  # noqa: E731
        nt = norm(t)
        G = self.sudo()
        for g in G.search([]):
            if norm(g.name) == nt or (len(t) <= 3 and norm(g.name).startswith(nt + '.')):
                return g
        last = G.search([], order='sequence desc', limit=1)
        return G.create({'name': t, 'sequence': (last.sequence or 0) + 10})


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
    group_id = fields.Many2one('store.nvbh.task.group', string='Nhóm công việc', ondelete='restrict', index=True)
    task_group = fields.Selection(TASK_GROUPS, string='Nhóm công việc (mã cũ)')
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
    # Thứ áp dụng: mặc định làm việc từ T2 đến CN; bỏ tick thứ nào thì công việc không xuất hiện trong checklist của ngày thứ đó
    wd_mon = fields.Boolean(string='T2', default=True)
    wd_tue = fields.Boolean(string='T3', default=True)
    wd_wed = fields.Boolean(string='T4', default=True)
    wd_thu = fields.Boolean(string='T5', default=True)
    wd_fri = fields.Boolean(string='T6', default=True)
    wd_sat = fields.Boolean(string='T7', default=True)
    wd_sun = fields.Boolean(string='CN', default=True)
    weekdays_label = fields.Char(string='Thứ áp dụng', compute='_compute_weekdays_label')

    @api.depends('wd_mon', 'wd_tue', 'wd_wed', 'wd_thu', 'wd_fri', 'wd_sat', 'wd_sun')
    def _compute_weekdays_label(self):
        for rec in self:
            days = [label for fname, label, _i in TASK_WEEKDAYS if rec[fname]]
            rec.weekdays_label = 'T2 - CN' if len(days) == 7 else ', '.join(days)

    def runs_on(self, work_date):
        """Công việc có áp dụng cho ngày work_date (theo thứ trong tuần) hay không; không có ngày thì coi là có."""
        self.ensure_one()
        if not work_date:
            return True
        day = fields.Date.to_date(work_date)
        for fname, _label, idx in TASK_WEEKDAYS:
            if idx == day.weekday():
                return bool(self[fname])
        return True

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
        if {'wd_mon', 'wd_tue', 'wd_wed', 'wd_thu', 'wd_fri', 'wd_sat', 'wd_sun', 'shift_type_ids'} & set(vals):
            # đổi Thứ / Loại ca áp dụng: cập nhật lại các phiếu đang thực hiện
            self.env['store.nvbh.check']._sync_open_checks_by_weekday()
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

    @api.model
    def _sync_group_ids(self):
        """Chuyển mã nhóm cũ (task_group) sang danh mục Nhóm công việc NVBH (group_id) cho các công việc chưa có group_id."""
        labels = dict(TASK_GROUPS)
        Group = self.env['store.nvbh.task.group'].sudo()
        for t in self.sudo().search([('group_id', '=', False), ('task_group', '!=', False)], order='task_group, sequence, id'):
            lbl = labels.get(t.task_group)
            if lbl:
                t.write({'group_id': Group._find_or_create(lbl).id})

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
                 'Người thực hiện', 'Người kiểm soát', 'Bộ phận phúc tra cuối', 'Điểm chuẩn', 'Thứ áp dụng']

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
        for i, (h, w) in enumerate(zip(self._XLS_HEAD, [6, 30, 52, 28, 14, 26, 26, 18, 22, 12, 22])):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        for r, t in enumerate(tasks, 1):
            vals = [t.sequence, t.group_id.name or groups.get(t.task_group, ''), t.name, ', '.join(t.shift_type_ids.mapped('name')), t.store_type or '',
                    t.time_slot or '', t.executor or '', t.controller or '', t.final_check or '', t.score, t.weekdays_label]
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

        # nhóm: nhận mã (01..08, I..VI) hoặc nhãn đầy đủ (chuẩn hóa dấu gạch ngang - / – / —)
        def norm_g(s):
            return ' '.join((s or '').replace('–', '-').replace('—', '-').split()).casefold()

        group_map = {}
        for k, label in TASK_GROUPS:
            group_map[norm_g(k)] = k
            group_map[norm_g(label)] = k
            group_map[norm_g(label.split('.', 1)[-1])] = k
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

        created = updated = removed = 0
        kept_ids = set()
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
                if gtxt:
                    gkey = norm_g(gtxt)
                    code = group_map.get(gkey)
                    label = dict(TASK_GROUPS).get(code, gtxt) if code else gtxt
                    vals['group_id'] = self.env['store.nvbh.task.group']._find_or_create(label).id
                    vals['task_group'] = code or False
                else:
                    vals['group_id'] = False
                    vals['task_group'] = False
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
            if 'thứ áp dụng' in col and get(r, 'Thứ áp dụng'):
                wtxt = get(r, 'Thứ áp dụng').upper().replace(' ', '')
                if wtxt in ('T2-CN', 'T2–CN', 'CẢTUẦN', 'ALL'):
                    picked = {f for f, _l, _i in TASK_WEEKDAYS}
                else:
                    labels = {label: f for f, label, _i in TASK_WEEKDAYS}
                    tokens = [x for x in wtxt.replace(';', ',').replace('|', ',').split(',') if x]
                    if not tokens or any(t not in labels for t in tokens):
                        errors.append('Dòng %s: Thứ áp dụng "%s" không hợp lệ (T2, T3, T4, T5, T6, T7, CN; cách nhau dấu phẩy)' % (n, get(r, 'Thứ áp dụng')))
                        continue
                    picked = {labels[t] for t in tokens}
                vals.update({f: f in picked for f, _l, _i in TASK_WEEKDAYS})
            rec = self.search([('name', '=', name)], limit=1)
            try:
                if rec:
                    rec.write(vals)
                    kept_ids.add(rec.id)
                    updated += 1
                else:
                    vals.setdefault('sequence', next_seq)
                    next_seq = max(next_seq, vals['sequence']) + 1
                    kept_ids.add(self.create(vals).id)
                    created += 1
            except Exception as e:  # lỗi quyền / dữ liệu: bỏ qua dòng và báo lại
                errors.append('Dòng %s: %s' % (n, getattr(e, 'args', [e])[0]))
        # chỉ xóa công việc cũ không còn trong file khi file nhập có dữ liệu hợp lệ và không bị lỗi
        if kept_ids and not errors:
            stale = self.search([('id', 'not in', list(kept_ids))])
            removed = len(stale)
            if stale:
                stale.unlink()
        return {'label': 'Công việc NVBH', 'created': created, 'updated': updated, 'removed': removed,
                'errors': errors[:20], 'error_count': len(errors)}
