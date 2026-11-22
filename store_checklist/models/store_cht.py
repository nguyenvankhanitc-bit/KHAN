# -*- coding: utf-8 -*-
"""Checklist công việc Cửa hàng trưởng (CHT).

- store.cht.task: danh mục công việc CHT (Cài đặt › Công việc checklist NVBH › Danh sách công việc CHT): tần suất ngày / tuần / tháng,
  thứ áp dụng hoặc ngày cụ thể trong tháng, mức phạt Lần 1 / 2 / 3.
- store.cht.check: phiếu check list CHT của một cửa hàng trong một ngày; dòng việc lấy từ danh mục theo ngày đến hạn.
  CHT tick hoàn thành (từ ngày D đến hết D+4), gửi ASM; ASM (cấp 3 trở lên) đánh giá Đạt / Không đạt.
- Vi phạm: việc đến hạn mà không hoàn thành (khi phiếu đã gửi hoặc đã quá hạn) hoặc ASM đánh giá Không đạt.
  Đếm theo cửa hàng + công việc trong tháng: lần 1, 2, 3 (từ lần 3 trở đi tính mức Lần 3).
"""
import base64
import calendar
import io
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_nvbh_task import TASK_GROUPS
from .store_role import role_level

CHT_FREQ = [('day', 'Ngày'), ('week', 'Tuần'), ('month', 'Tháng'), ('week_month', 'Tuần/Tháng')]
CHT_WEEKDAYS = [('wd_mon', 'T2', 0), ('wd_tue', 'T3', 1), ('wd_wed', 'T4', 2), ('wd_thu', 'T5', 3),
                ('wd_fri', 'T6', 4), ('wd_sat', 'T7', 5), ('wd_sun', 'CN', 6)]
CHT_STATES = [('draft', 'Đang thực hiện'), ('submitted', 'Chờ ASM đánh giá'), ('evaluated', 'Đã đánh giá')]
CHT_EVAL = [('pass', 'Đạt'), ('fail', 'Không đạt')]

# Danh mục mặc định (29 công việc CHT): (nội dung, KS/đánh giá cuối, khung giờ, phạt L1, L2, L3, tần suất, thứ, ngày trong tháng)
ALL = 'T2-CN'
CHT_DEFAULT_TASKS = [
    ('Họp định kỳ, training nhân viên, cập nhật CTKM', '', '15h-16h', '', '', '', 'week', 'T2', ''),
    ('Kiểm tra ca làm việc, tác phong nhân viên', '', '12h-12h30', '', '', '', 'day', ALL, ''),
    ('Sắp lịch ca, phân bổ nhân sự theo từng khu vực', '', '20h-21h', '', '', '', 'day', ALL, ''),
    ('Tuyển dụng và đào tạo nhân sự mới', '', 'Phát sinh / 16h-17h', '', '', '', 'day', ALL, ''),
    ('Xử lý khiếu nại, đổi trả sản phẩm', '', 'Phát sinh', '', '', '', 'day', ALL, ''),
    ('Mở các trang thiết bị khi vào ca (máy tính, đèn, máy lạnh)', 'CAMERA', '5 phút đầu ngày', '50.000', '100.000', '50% TN', 'day', ALL, ''),
    ('Kiểm tra vệ sinh cửa hàng: quét nhà, lau sàn, cửa kính...', 'ADMIN', '8h-10h', '50.000', '100.000', '100% TN', 'day', ALL, ''),
    ('Kiểm tra vệ sinh hàng hóa', 'ADMIN', '15h-16h', '', '', '', 'day', ALL, ''),
    ('Kiểm tra vệ sinh CCDC, quầy kệ', 'ADMIN', '15h-16h', '', '', '', 'week', 'T2', ''),
    ('Kiểm tra vệ sinh, sắp xếp kho', 'ADMIN', '15h-16h', '', '', '', 'week', 'T2', ''),
    ('Tắt máy lạnh trước khi về 30 phút', 'CAMERA', '21h30', '50.000', '100.000', '50% TN', 'day', ALL, ''),
    ('Mở trình chiếu clip / tivi / loa; gửi hình ảnh / video báo cáo qua Lark (TTTM trước 10h30)', 'MKT', '8h (9h)',
     '100.000', '200.000', '50% TN', 'day', ALL, ''),
    ('Tắt các thiết bị khi ra về (máy tính, tivi / led); khóa cửa hàng / niêm phong cửa hàng', 'CAMERA', '22h',
     '30% TN', '50% TN', '100% TN', 'day', ALL, ''),
    ('Kiểm tra số lượng thực tế và drive để đối chiếu số liệu', 'ADMIN', '8h-10h', '30% TN', '50% TN', '100% TN', 'day', ALL, ''),
    ('Làm thẻ kho và sổ theo dõi nhập xuất tồn kho (drive)', '', '15h-17h', '', '', '', 'day', ALL, ''),
    ('Kiểm tra bàn giao ca trên sổ theo khu vực', 'ADMIN', '8h (9h) hoặc 14h (15h)', '', '', '', 'day', ALL, ''),
    ('Kiểm tra, báo cáo các trang thiết bị / tài sản bị hư hỏng, mất (nếu có)', 'IT', '16h-17h', '20% TN', '30% TN', '50% TN',
     'week', 'T5', ''),
    ('Kiểm tra trưng bày, sắp xếp, bảng sale, hàng hóa, tem giá đúng guideline / chương trình, quy định tại cửa hàng và kho',
     'ADMIN', '10h-11h', '30% TN', '50% TN', '100% TN', 'day', ALL, ''),
    ('Báo cáo doanh thu hằng ngày đúng giờ, sổ sách đầy đủ; chụp hình và gửi bill BLK kèm tem tag + chứng từ kèm theo (nếu có)',
     'ADMIN', '21h30-22h', '100.000', '200.000', '50% TN', 'day', ALL, ''),
    ('Nộp tiền đúng thời gian quy định, ghi rõ tên cửa hàng', 'KTCN', 'Trước 11h hằng ngày', '100.000', '200.000', '50% TN',
     'day', ALL, ''),
    ('Check mail, phản hồi thông tin đúng thời gian quy định cho các bộ phận', 'ADMIN', '10h / 15h / 20h', '100.000', '200.000',
     '50% TN', 'day', ALL, ''),
    ('Đăng bài Facebook / GGB và báo cáo đầy đủ, đúng quy định', 'MKT', '19h', '50.000', '100.000', '200.000', 'week', 'T2', ''),
    ('Gửi báo cáo hình ảnh trưng bày CTKM, bảng sale hằng tuần', 'MKT', '12h-17h', '100.000', '200.000', '50% TN', 'week', 'T2', ''),
    ('Đối chiếu và chụp hình biên bản đối chiếu công nợ từ trung tâm và các chứng từ liên quan gửi về mail ketoan@sangtam.com, '
     'sau đó gửi bưu điện về Công ty', 'KẾ TOÁN THUẾ', '15h-17h', '50.000', '100.000', '200.000', 'week_month', 'T2', ''),
    ('Báo cáo số lượng, hình ảnh, tình trạng hàng hóa hư hỏng về Công ty', 'KTAD', '15h-16h', '100.000', '200.000', '50% TN',
     'week_month', '', '15/30'),
    ('Đối chiếu và giải trình số lượng tồn kho định kỳ', 'KTDT', '10h-12h (ngày 15 hoặc 30/31)', '100.000', '200.000', '50% TN',
     'month', '', '15/30'),
    ('Đặt hàng / châm hàng / CCDC', 'ON / SÀN', '12h-13h', '50.000', '100.000', '50% TN', 'week', 'T6', ''),
    ('Đặt văn phòng phẩm / đồng phục', 'ON / SÀN', '14h-15h', '50.000', '100.000', '50% TN', 'week_month', '', '02-05'),
    ('Làm biên bản tự kiểm tra công tác PCCC hằng tháng', '', '10h-10h30', '', '', '', 'month', '', '25'),
]


# Nhóm công việc mặc định của 29 việc (theo thứ tự trong CHT_DEFAULT_TASKS)
CHT_DEFAULT_GROUPS = ['III', 'III', 'III', 'III', 'IV', 'I', 'I', 'II', 'I', 'II', 'I', 'V', 'I', 'II', 'II', 'IV', 'I', 'II',
                      'IV', 'IV', 'IV', 'V', 'V', 'IV', 'II', 'II', 'II', 'I', 'I']


def _parse_money(text):
    """'50.000' -> 50000; '50% TN' / rỗng -> None (không cộng vào tổng tiền phạt)."""
    t = (text or '').strip()
    if not t or '%' in t:
        return None
    digits = re.sub(r'[^\d]', '', t)
    return int(digits) if digits else None


def _month_days(spec, day):
    """Ngày `day` có thuộc 'Ngày cụ thể' (vd. '15/30', '25', '02-05', '1,15') không. Ngày lớn hơn số ngày của tháng
    (30, 31 ở tháng 2...) thì tính vào ngày cuối tháng."""
    last = calendar.monthrange(day.year, day.month)[1]
    for tok in re.split(r'[,/;\s]+', spec or ''):
        tok = tok.strip()
        if not tok:
            continue
        m = re.match(r'^(\d{1,2})\s*-\s*(\d{1,2})$', tok)
        try:
            a, b = (int(m.group(1)), int(m.group(2))) if m else (int(tok), int(tok))
        except ValueError:
            continue
        a, b = min(a, last), min(b, last)
        if a <= day.day <= b:
            return True
    return False


class StoreChtTask(models.Model):
    _name = 'store.cht.task'
    _inherit = 'store.perm.mixin'
    _description = 'Công việc checklist CHT'
    _order = 'sequence, id'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return 'cht_task'

    @api.model
    def _perm_key_vals(self, vals):
        return 'cht_task'

    sequence = fields.Integer(string='STT', default=10)
    name = fields.Char(string='Tên công việc', required=True)
    task_group = fields.Selection(TASK_GROUPS, string='Nhóm công việc')
    executor = fields.Char(string='Người thực hiện', default='CHT')
    controller = fields.Char(string='Người kiểm soát', default='ASM')
    final_check = fields.Char(string='Bộ phận phúc tra cuối (cũ)', help='Dữ liệu cũ dạng chữ (CAMERA, ADMIN, MKT...), thay bằng cột Admin')
    admin_user_ids = fields.Many2many('res.users', 'store_cht_task_admin_user_rel', 'task_id', 'user_id', string='Admin',
                                      help='Các user Admin phúc tra cuối công việc này')
    related_user_ids = fields.Many2many('res.users', 'store_cht_task_related_user_rel', 'task_id', 'user_id', string='BP liên quan',
                                        help='Các user thuộc bộ phận liên quan đến công việc này')
    score = fields.Integer(string='Điểm chuẩn', default=2)
    time_slot = fields.Char(string='Khung giờ / Thời hạn')
    fine_1 = fields.Char(string='Phạt lần 1', help='Số tiền (vd. 50.000) hoặc % thu nhập (vd. 50% TN)')
    fine_2 = fields.Char(string='Phạt lần 2')
    fine_3 = fields.Char(string='Phạt lần 3', help='Áp dụng cho lần 3 và các lần sau trong tháng')
    frequency = fields.Selection(CHT_FREQ, string='Tần suất', required=True, default='day')
    wd_mon = fields.Boolean(string='T2', default=True)
    wd_tue = fields.Boolean(string='T3', default=True)
    wd_wed = fields.Boolean(string='T4', default=True)
    wd_thu = fields.Boolean(string='T5', default=True)
    wd_fri = fields.Boolean(string='T6', default=True)
    wd_sat = fields.Boolean(string='T7', default=True)
    wd_sun = fields.Boolean(string='CN', default=True)
    month_days = fields.Char(string='Ngày trong tháng',
                             help='Để trống: theo các thứ đã tick. Nhập ngày cụ thể trong tháng thì bỏ qua thứ: '
                                  'vd. "15/30" (ngày 15 và 30, tháng thiếu ngày thì lấy ngày cuối tháng), "25", "02-05" (từ ngày 2 đến 5).')
    schedule_label = fields.Char(string='Ngày cụ thể', compute='_compute_schedule_label')
    active = fields.Boolean(default=True)

    @api.depends('month_days', 'wd_mon', 'wd_tue', 'wd_wed', 'wd_thu', 'wd_fri', 'wd_sat', 'wd_sun')
    def _compute_schedule_label(self):
        for rec in self:
            if (rec.month_days or '').strip():
                rec.schedule_label = 'Ngày %s' % rec.month_days.strip()
                continue
            days = [label for fname, label, _i in CHT_WEEKDAYS if rec[fname]]
            rec.schedule_label = 'T2 - CN' if len(days) == 7 else (', '.join(days) or 'Không áp dụng')

    def runs_on(self, day):
        self.ensure_one()
        day = fields.Date.to_date(day)
        if (self.month_days or '').strip():
            return _month_days(self.month_days, day)
        for fname, _label, idx in CHT_WEEKDAYS:
            if idx == day.weekday():
                return bool(self[fname])
        return False

    def action_open_popup(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Công việc CHT', 'res_model': self._name, 'res_id': self.id, 'views': [(False, 'form')],
                'target': 'new', 'context': {'dialog_size': 'large'}}

    def _admin_names(self):
        return ', '.join(self.sudo().admin_user_ids.mapped('name'))

    def _related_names(self):
        return ', '.join(self.sudo().related_user_ids.mapped('name'))

    def fine_for(self, nth):
        self.ensure_one()
        return (self.fine_1 if nth == 1 else self.fine_2 if nth == 2 else self.fine_3) or ''

    @api.model
    def _seed_default_tasks(self):
        """Tạo danh mục 29 công việc CHT mặc định (chỉ khi danh mục đang trống, kể cả việc đã lưu trữ)."""
        if self.sudo().with_context(active_test=False).search_count([]):
            return
        vals_list = []
        for i, (name, final, slot, f1, f2, f3, freq, wds, mdays) in enumerate(CHT_DEFAULT_TASKS, 1):
            vals = {'sequence': i, 'name': name, 'final_check': final, 'time_slot': slot, 'fine_1': f1, 'fine_2': f2,
                    'fine_3': f3, 'frequency': freq, 'month_days': mdays, 'task_group': CHT_DEFAULT_GROUPS[i - 1]}
            on = {lbl for lbl in (wds.split(',') if wds and wds != ALL else [])}
            for fname, label, _i in CHT_WEEKDAYS:
                vals[fname] = wds == ALL or label in on
            vals_list.append(vals)
        self.sudo().create(vals_list)

    @api.model
    def _fill_default_groups(self):
        """Việc mặc định chưa có Nhóm công việc / Người thực hiện / Người kiểm soát: điền theo danh mục mặc định."""
        by_name = {t[0]: CHT_DEFAULT_GROUPS[i] for i, t in enumerate(CHT_DEFAULT_TASKS)}
        for rec in self.sudo().with_context(active_test=False).search([]):
            vals = {}
            if not rec.task_group and rec.name in by_name:
                vals['task_group'] = by_name[rec.name]
            if not rec.executor:
                vals['executor'] = 'CHT'
            if not rec.controller:
                vals['controller'] = 'ASM'
            if vals:
                rec.write(vals)

    # ---------------- Excel ----------------
    _XLS_HEAD = ['STT', 'Nhóm công việc', 'Tên công việc', 'Thứ áp dụng', 'Ngày trong tháng', 'Tần suất', 'Khung giờ / Thời hạn',
                 'Người thực hiện', 'Người kiểm soát', 'Admin', 'BP liên quan', 'Phạt lần 1', 'Phạt lần 2', 'Phạt lần 3', 'Điểm chuẩn']

    @api.model
    def export_xlsx(self):
        """Xuất Danh sách công việc CHT ra Excel. File xuất ra nhập lại được."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        tasks = self.search([], order='sequence, id')
        groups, freqs = dict(TASK_GROUPS), dict(CHT_FREQ)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Cong viec CHT')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center',
                                'valign': 'vcenter', 'border': 1, 'text_wrap': True})
        cell = book.add_format({'border': 1, 'valign': 'top', 'text_wrap': True})
        num = book.add_format({'border': 1, 'valign': 'top', 'num_format': '0.##'})
        for i, (h, w) in enumerate(zip(self._XLS_HEAD, [6, 28, 52, 16, 14, 12, 22, 14, 14, 26, 26, 12, 12, 12, 10])):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        for r, t in enumerate(tasks, 1):
            wd = '' if (t.month_days or '').strip() else t.schedule_label
            vals = [t.sequence, groups.get(t.task_group, ''), t.name, wd, t.month_days or '', freqs.get(t.frequency, ''),
                    t.time_slot or '', t.executor or '', t.controller or '', ', '.join(t.admin_user_ids.mapped('name')),
                    ', '.join(t.related_user_ids.mapped('name')), t.fine_1 or '', t.fine_2 or '', t.fine_3 or '', t.score]
            for c, v in enumerate(vals):
                sheet.write(r, c, v, num if c in (0, 14) else cell)
        sheet.write(len(tasks) + 1, 13, 'Tổng', head)
        sheet.write(len(tasks) + 1, 14, sum(tasks.mapped('score')), num)
        sheet.freeze_panes(1, 0)
        book.close()
        return {'name': 'Cong_viec_CHT.xlsx', 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def import_xlsx(self, data):
        """Nhập Danh sách công việc CHT từ Excel (cùng cột với file xuất): trùng Tên công việc thì cập nhật, chưa có thì thêm."""
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

        group_map = {}
        for k, label in TASK_GROUPS:
            group_map[k.casefold()] = k
            group_map[label.casefold()] = k
            group_map[label.split('.', 1)[-1].strip().casefold()] = k
        freq_map = {}
        for k, label in CHT_FREQ:
            freq_map[k] = k
            freq_map[label.casefold()] = k
            freq_map[label.casefold().replace(' ', '')] = k
        labels = {label: f for f, label, _i in CHT_WEEKDAYS}
        Users = self.env['res.users'].sudo()

        def users_of(text):
            """Tên / login user cách nhau dấu phẩy -> (ids, tên không tìm thấy)."""
            ids, miss = [], []
            for part in [x.strip() for x in re.split(r'[,;\n]', text or '') if x.strip()]:
                u = Users.search(['|', ('name', '=ilike', part), ('login', '=ilike', part)], limit=1)
                (ids.append(u.id) if u else miss.append(part))
            return ids, miss

        created = updated = 0
        errors = []
        next_seq = (self.search([], order='sequence desc', limit=1).sequence or 0) + 1
        for n, r in enumerate(rows[hi + 1:], hi + 2):
            name = get(r, 'Tên công việc')
            if not name or name.casefold() == 'tổng':
                continue
            vals = {'name': name}
            miss = []
            for xls, fname in (('Admin', 'admin_user_ids'), ('BP liên quan', 'related_user_ids')):
                if xls.casefold() in col:
                    ids, bad = users_of(get(r, xls))
                    vals[fname] = [(6, 0, ids)]
                    miss += bad
            if miss:
                errors.append('Dòng %s: không tìm thấy user %s (đã bỏ qua phần này)' % (n, ', '.join(miss)))
            if 'nhóm công việc' in col:
                g = get(r, 'Nhóm công việc')
                if g and g.casefold() not in group_map:
                    errors.append('Dòng %s: Nhóm công việc "%s" không hợp lệ' % (n, g))
                    continue
                vals['task_group'] = group_map.get(g.casefold(), False)
            if 'tần suất' in col and get(r, 'Tần suất'):
                f = get(r, 'Tần suất').casefold()
                if f not in freq_map and f.replace(' ', '') not in freq_map:
                    errors.append('Dòng %s: Tần suất "%s" không hợp lệ (Ngày / Tuần / Tháng / Tuần/Tháng)' % (n, get(r, 'Tần suất')))
                    continue
                vals['frequency'] = freq_map.get(f) or freq_map[f.replace(' ', '')]
            try:
                if get(r, 'STT'):
                    vals['sequence'] = int(float(get(r, 'STT').replace(',', '.')))
                if get(r, 'Điểm chuẩn'):
                    vals['score'] = int(float(get(r, 'Điểm chuẩn').replace(',', '.')))
            except ValueError:
                errors.append('Dòng %s: STT hoặc Điểm chuẩn không phải số' % n)
                continue
            for xls, fname in (('Khung giờ / Thời hạn', 'time_slot'), ('Người thực hiện', 'executor'), ('Người kiểm soát', 'controller'),
                               ('Phạt lần 1', 'fine_1'), ('Phạt lần 2', 'fine_2'),
                               ('Phạt lần 3', 'fine_3'), ('Ngày trong tháng', 'month_days')):
                if xls.casefold() in col:
                    vals[fname] = get(r, xls)
            wtxt = get(r, 'Thứ áp dụng').upper().replace(' ', '').replace('–', '-')
            if wtxt:
                if wtxt in ('T2-CN', 'CẢTUẦN', 'ALL'):
                    picked = {f for f, _l, _i in CHT_WEEKDAYS}
                else:
                    tokens = [x for x in re.split(r'[,;|]', wtxt) if x]
                    if any(t not in labels for t in tokens):
                        errors.append('Dòng %s: Thứ áp dụng "%s" không hợp lệ (T2, T3... CN hoặc T2 - CN)' % (n, get(r, 'Thứ áp dụng')))
                        continue
                    picked = {labels[t] for t in tokens}
                vals.update({f: f in picked for f, _l, _i in CHT_WEEKDAYS})
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
            except Exception as e:
                errors.append('Dòng %s: %s' % (n, getattr(e, 'args', [e])[0]))
        return {'created': created, 'updated': updated, 'removed': 0, 'label': 'Danh sách công việc CHT',
                'errors': errors[:20], 'error_count': len(errors)}


class StoreChtCheck(models.Model):
    _name = 'store.cht.check'
    _description = 'Phiếu checklist công việc CHT'
    _order = 'work_date desc, store_id'

    name = fields.Char(string='Phiếu', compute='_compute_name', store=True)
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True)
    mien = fields.Selection(related='store_id.mien', string='Miền')
    work_date = fields.Date(string='Ngày', required=True, index=True)
    user_id = fields.Many2one('res.users', string='CHT thực hiện')
    state = fields.Selection(CHT_STATES, string='Trạng thái', default='draft', required=True)
    submit_date = fields.Datetime(string='Gửi ASM lúc')
    eval_user_id = fields.Many2one('res.users', string='ASM đánh giá')
    eval_date = fields.Datetime(string='Đánh giá lúc')
    line_ids = fields.One2many('store.cht.check.line', 'check_id', string='Công việc')

    _uniq_store_day = models.Constraint('unique(store_id, work_date)', 'Mỗi cửa hàng chỉ có một phiếu checklist CHT mỗi ngày.')

    @api.depends('store_id', 'work_date')
    def _compute_name(self):
        for rec in self:
            rec.name = 'CHT/%s/%s' % (rec.store_id.code or rec.store_id.name or '', rec.work_date.strftime('%d%m%Y') if rec.work_date else '')

    # ---------------- quyền / thời hạn ----------------
    def _window_days(self):
        return int(self.env['ir.config_parameter'].sudo().get_param('store_checklist.staff_window_days', 4) or 4)

    def _deadline(self):
        self.ensure_one()
        return self.work_date + timedelta(days=self._window_days())

    def _overdue(self):
        self.ensure_one()
        return fields.Date.context_today(self) > self._deadline()

    def _closed(self):
        """Đã chốt để tính vi phạm: đã gửi ASM / đã đánh giá, hoặc quá hạn check list."""
        self.ensure_one()
        return self.state != 'draft' or self._overdue()

    @api.model
    def _me(self):
        user = self.env.user
        privileged = user._is_admin() or user.has_group('store_checklist.group_store_manager')
        level = role_level(user.sudo().employee_id.checklist_role_code) if user.employee_id else 0
        rights = self.env['store.perm.rule']._rights()
        r = (rights or {}).get('nvbh_cht', {})
        can_write = rights is None or bool(r.get('write'))
        return {
            'privileged': privileged,
            'can_tick': can_write and (privileged or level == 2),
            # ASM trở lên, hoặc chức danh văn phòng (không thuộc 6 cấp, vd. trưởng phòng) được đánh giá nếu có quyền Sửa
            'can_eval': can_write and (privileged or level >= 3 or level == 0),
            'can_read': rights is None or bool(r.get('read')),
        }

    @api.model
    def _my_store_ids(self):
        return [s['id'] for s in self.env['store.nvbh.check'].get_my_stores()]

    def _check_store(self, store_id):
        me = self._me()
        if not me['can_read']:
            raise AccessError(_('Bạn không có quyền xem Checklist CV CHT.'))
        if not me['privileged'] and int(store_id) not in self._my_store_ids():
            raise AccessError(_('Bạn không được phân quyền cửa hàng này.'))
        return me

    # ---------------- tạo / đồng bộ dòng việc ----------------
    def _sync_lines(self):
        """Phiếu còn đang thực hiện: thêm việc mới đến hạn trong ngày, bỏ việc không còn áp dụng (chưa tick)."""
        Task = self.env['store.cht.task'].sudo()
        tasks = Task.search([])
        for check in self.sudo().filtered(lambda c: c.state == 'draft'):
            due = tasks.filtered(lambda t: t.runs_on(check.work_date))
            have = check.line_ids.mapped('task_id')
            stale = check.line_ids.filtered(lambda l: l.task_id and l.task_id not in due and not l.done)
            stale.unlink()
            new = [{
                'check_id': check.id, 'task_id': t.id, 'sequence': t.sequence, 'name': t.name, 'time_slot': t.time_slot,
                'task_group': t.task_group, 'executor': t.executor, 'controller': t.controller, 'score': t.score,
                'admin_names': t._admin_names(), 'related_names': t._related_names(),
                'frequency': t.frequency, 'schedule_label': t.schedule_label,
                'fine_1': t.fine_1, 'fine_2': t.fine_2, 'fine_3': t.fine_3,
            } for t in due - have]
            if new:
                self.env['store.cht.check.line'].sudo().create(new)
            for line in check.line_ids.filtered(lambda l: l.task_id):
                t = line.task_id
                vals = {k: t[k] for k in ('sequence', 'task_group', 'executor', 'controller', 'score') if line[k] != t[k]}
                for k, v in (('admin_names', t._admin_names()), ('related_names', t._related_names())):
                    if (line[k] or '') != v:
                        vals[k] = v
                if vals:
                    line.write(vals)

    @api.model
    def _get_or_create(self, store_id, work_date):
        day = fields.Date.to_date(work_date) or fields.Date.context_today(self)
        check = self.sudo().search([('store_id', '=', int(store_id)), ('work_date', '=', day)], limit=1)
        if not check:
            check = self.sudo().create({'store_id': int(store_id), 'work_date': day})
        check._sync_lines()
        return check

    # ---------------- API cho trang Checklist CV CHT ----------------
    def _payload(self, me):
        self.ensure_one()
        today = fields.Date.context_today(self)
        overdue = self._overdue()
        editable = self.state == 'draft' and (not overdue or me['privileged']) and self.work_date <= today
        closed = self._closed()
        nth = self._violation_numbers()
        lines = []
        gorder = {k: i for i, (k, _l) in enumerate(TASK_GROUPS)}
        glabel = dict(TASK_GROUPS)
        for l in self.line_ids.sorted(lambda x: (gorder.get(x.task_group, 99), x.sequence, x.id)):
            viol = l._is_violation(closed)
            lines.append({
                'id': l.id, 'sequence': l.sequence, 'name': l.name, 'time_slot': l.time_slot or '',
                'group': glabel.get(l.task_group, 'KHÁC'), 'executor': l.executor or '', 'controller': l.controller or '',
                'score': l.score,
                'final_check': l.admin_names or l.final_check or '', 'related': l.related_names or '',
                'frequency': dict(CHT_FREQ).get(l.frequency, ''),
                'schedule_label': l.schedule_label or '', 'fines': [l.fine_1 or '', l.fine_2 or '', l.fine_3 or ''],
                'done': l.done, 'note': l.note or '', 'eval_result': l.eval_result or '',
                'violation': viol, 'nth': nth.get(l.id, 0) if viol else 0,
                'fine_now': l._fine_text(nth.get(l.id, 0)) if viol else '',
            })
        return {
            'id': self.id, 'name': self.name, 'store': self.store_id.display_name, 'work_date': fields.Date.to_string(self.work_date),
            'state': self.state, 'state_label': dict(CHT_STATES)[self.state],
            'user': self.user_id.name or '', 'submit_date': self.submit_date and fields.Datetime.context_timestamp(self, self.submit_date).strftime('%d/%m/%Y %H:%M') or '',
            'eval_user': self.eval_user_id.name or '', 'deadline': self._deadline().strftime('%d/%m/%Y'), 'overdue': overdue,
            'done_count': sum(1 for l in lines if l['done']), 'total': len(lines),
            'violation_count': sum(1 for l in lines if l['violation']),
            'can_tick': me['can_tick'] and editable,
            'can_submit': me['can_tick'] and editable and bool(lines),
            'can_eval': me['can_eval'] and self.state == 'submitted',
            'can_reopen': me['privileged'] and self.state != 'draft',
            'lines': lines,
        }

    @api.model
    def cht_get_day(self, store_id, work_date=None):
        me = self._check_store(store_id)
        check = self._get_or_create(store_id, work_date)
        return dict(check._payload(me), me=me)

    def _line_for_write(self, line_id, need):
        line = self.env['store.cht.check.line'].sudo().browse(int(line_id)).exists()
        if not line:
            raise UserError(_('Không tìm thấy dòng công việc.'))
        check = line.check_id
        me = check._check_store(check.store_id.id)
        data = check._payload(me)
        if not data[need]:
            raise UserError(_('Phiếu đã khóa hoặc bạn không có quyền thao tác ở bước này.'))
        return line, check, me

    @api.model
    def cht_toggle(self, line_id, done):
        line, check, me = self._line_for_write(line_id, 'can_tick')
        line.write({'done': bool(done), 'done_at': fields.Datetime.now() if done else False})
        if not check.user_id:
            check.user_id = self.env.user
        return check._payload(me)

    @api.model
    def cht_toggle_all(self, check_id, done):
        check = self.sudo().browse(int(check_id)).exists()
        me = check._check_store(check.store_id.id)
        if not check._payload(me)['can_tick']:
            raise UserError(_('Phiếu đã khóa hoặc bạn không có quyền check list.'))
        check.line_ids.write({'done': bool(done), 'done_at': fields.Datetime.now() if done else False})
        if not check.user_id:
            check.user_id = self.env.user
        return check._payload(me)

    @api.model
    def cht_note(self, line_id, note):
        check = self.env['store.cht.check.line'].sudo().browse(int(line_id)).check_id
        me = check._check_store(check.store_id.id)
        data = check._payload(me)
        if not (data['can_tick'] or data['can_eval']):
            raise UserError(_('Phiếu đã khóa hoặc bạn không có quyền ghi chú.'))
        self.env['store.cht.check.line'].sudo().browse(int(line_id)).note = note or False
        return True

    @api.model
    def cht_submit(self, check_id):
        check = self.sudo().browse(int(check_id)).exists()
        me = check._check_store(check.store_id.id)
        if not check._payload(me)['can_submit']:
            raise UserError(_('Phiếu đã khóa hoặc bạn không có quyền gửi.'))
        check.write({'state': 'submitted', 'submit_date': fields.Datetime.now(), 'user_id': check.user_id.id or self.env.uid})
        return check._payload(me)

    @api.model
    def cht_eval(self, line_id, result):
        line, check, me = self._line_for_write(line_id, 'can_eval')
        line.eval_result = result if result in ('pass', 'fail') else False
        return check._payload(me)

    @api.model
    def cht_eval_all(self, check_id, result):
        check = self.sudo().browse(int(check_id)).exists()
        me = check._check_store(check.store_id.id)
        if not check._payload(me)['can_eval']:
            raise UserError(_('Bạn không có quyền đánh giá phiếu này.'))
        for l in check.line_ids:
            l.eval_result = result if result in ('pass', 'fail') else ('pass' if l.done else 'fail')
        return check._payload(me)

    @api.model
    def cht_finish_eval(self, check_id):
        check = self.sudo().browse(int(check_id)).exists()
        me = check._check_store(check.store_id.id)
        if not check._payload(me)['can_eval']:
            raise UserError(_('Bạn không có quyền đánh giá phiếu này.'))
        for l in check.line_ids.filtered(lambda x: not x.eval_result):
            l.eval_result = 'pass' if l.done else 'fail'
        check.write({'state': 'evaluated', 'eval_user_id': self.env.uid, 'eval_date': fields.Datetime.now()})
        return check._payload(me)

    @api.model
    def cht_reopen(self, check_id):
        check = self.sudo().browse(int(check_id)).exists()
        me = check._check_store(check.store_id.id)
        if not me['privileged']:
            raise AccessError(_('Chỉ Quản lý mới mở lại được phiếu.'))
        check.write({'state': 'draft', 'eval_user_id': False, 'eval_date': False})
        return check._payload(me)

    # ---------------- vi phạm ----------------
    def _violation_numbers(self):
        """{line_id: lần vi phạm thứ mấy trong tháng} cho các dòng vi phạm của phiếu này (đếm theo cửa hàng + công việc)."""
        self.ensure_one()
        start = self.work_date.replace(day=1)
        rows = self._violations(start, self.work_date + timedelta(days=1), [self.store_id.id])
        return {r['line_id']: r['nth'] for r in rows if r['check_id'] == self.id}

    @api.model
    def _violations(self, start, end, store_ids=None):
        """Danh sách vi phạm trong [start, end): mỗi phần tử {store, task, line, ngày, lần, mức phạt}; đếm lần theo tháng."""
        dom = [('check_id.work_date', '>=', start.replace(day=1)), ('check_id.work_date', '<', end)]
        if store_ids is not None:
            dom.append(('check_id.store_id', 'in', list(store_ids)))
        lines = self.env['store.cht.check.line'].sudo().search(dom)
        closed = {c.id: c._closed() for c in lines.mapped('check_id')}
        out, counter = [], {}
        for l in lines.sorted(lambda x: (x.check_id.work_date, x.check_id.id, x.sequence, x.id)):
            if not l._is_violation(closed[l.check_id.id]):
                continue
            c = l.check_id
            key = (c.store_id.id, l.task_id.id or l.name, c.work_date.year, c.work_date.month)
            counter[key] = counter.get(key, 0) + 1
            if c.work_date < start:
                continue
            nth = counter[key]
            out.append({'line_id': l.id, 'check_id': c.id, 'store_id': c.store_id.id, 'store': c.store_id.display_name,
                        'mien': c.store_id.mien or '', 'task_key': str(l.task_id.id or l.name), 'task': l.name,
                        'sequence': l.sequence, 'date': c.work_date, 'nth': nth, 'fine': l._fine_text(nth),
                        'reason': 'ASM đánh giá Không đạt' if l.eval_result == 'fail' else 'Không hoàn thành'})
        return out

    @api.model
    def cht_month_violations(self, month=None, store_id=None):
        """Báo cáo vi phạm & mức phạt tháng: nhóm theo cửa hàng -> công việc."""
        me = self._me()
        if not me['can_read']:
            raise AccessError(_('Bạn không có quyền xem Checklist CV CHT.'))
        start, end, _days = self.env['store.nvbh.check']._month_range(month)
        if store_id:
            self._check_store(store_id)
            store_ids = [int(store_id)]
        else:
            store_ids = None if me['privileged'] else self._my_store_ids()
        rows = self._violations(start, end, store_ids)
        stores = {}
        for r in rows:
            st = stores.setdefault(r['store_id'], {'store': r['store'], 'mien': r['mien'], 'tasks': {}, 'money': 0, 'count': 0})
            tk = st['tasks'].setdefault(r['task_key'], {'task': r['task'], 'sequence': r['sequence'], 'items': [], 'money': 0, 'percent': []})
            money = _parse_money(r['fine'])
            tk['items'].append({'date': r['date'].strftime('%d/%m'), 'nth': r['nth'], 'fine': r['fine'] or '—', 'reason': r['reason']})
            if money:
                tk['money'] += money
                st['money'] += money
            elif r['fine']:
                tk['percent'].append(r['fine'])
            st['count'] += 1
        result = []
        for sid, st in sorted(stores.items(), key=lambda kv: kv[1]['store']):
            tasks = sorted(st['tasks'].values(), key=lambda t: t['sequence'])
            result.append({'store_id': sid, 'store': st['store'], 'mien': st['mien'], 'count': st['count'], 'money': st['money'],
                           'tasks': [dict(t, count=len(t['items'])) for t in tasks]})
        return {'month': start.strftime('%m/%Y'), 'stores': result,
                'total_count': sum(s['count'] for s in result), 'total_money': sum(s['money'] for s in result)}

    @api.model
    def cht_month_days(self, store_id, month=None):
        """Lịch tháng của cửa hàng: mỗi ngày đã có phiếu -> trạng thái, số việc xong / tổng, số vi phạm."""
        self._check_store(store_id)
        start, end, _days = self.env['store.nvbh.check']._month_range(month)
        checks = self.sudo().search([('store_id', '=', int(store_id)), ('work_date', '>=', start), ('work_date', '<', end)])
        viol = {}
        for r in self._violations(start, end, [int(store_id)]):
            viol[r['check_id']] = viol.get(r['check_id'], 0) + 1
        return {fields.Date.to_string(c.work_date): {'state': c.state, 'done': len(c.line_ids.filtered('done')),
                                                     'total': len(c.line_ids), 'violations': viol.get(c.id, 0)} for c in checks}


class StoreChtCheckLine(models.Model):
    _name = 'store.cht.check.line'
    _description = 'Dòng checklist công việc CHT'
    _order = 'sequence, id'

    check_id = fields.Many2one('store.cht.check', required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one('store.cht.task', string='Công việc', ondelete='set null', index=True)
    sequence = fields.Integer(string='STT', default=10)
    name = fields.Char(string='Nội dung công việc', required=True)
    time_slot = fields.Char(string='Khung giờ / Thời hạn')
    task_group = fields.Selection(TASK_GROUPS, string='Nhóm công việc')
    executor = fields.Char(string='Người thực hiện')
    controller = fields.Char(string='Người kiểm soát')
    score = fields.Integer(string='Điểm chuẩn')
    final_check = fields.Char(string='Bộ phận phúc tra cuối (cũ)')
    admin_names = fields.Char(string='Admin')
    related_names = fields.Char(string='BP liên quan')
    frequency = fields.Selection(CHT_FREQ, string='Tần suất')
    schedule_label = fields.Char(string='Ngày cụ thể')
    fine_1 = fields.Char(string='Phạt lần 1')
    fine_2 = fields.Char(string='Phạt lần 2')
    fine_3 = fields.Char(string='Phạt lần 3')
    done = fields.Boolean(string='Hoàn thành')
    done_at = fields.Datetime(string='Hoàn thành lúc')
    note = fields.Char(string='Ghi chú')
    eval_result = fields.Selection(CHT_EVAL, string='ASM đánh giá')

    def _is_violation(self, closed):
        self.ensure_one()
        if self.eval_result:
            return self.eval_result == 'fail'
        return closed and not self.done

    def _fine_text(self, nth):
        self.ensure_one()
        if nth <= 0:
            return ''
        return (self.fine_1 if nth == 1 else self.fine_2 if nth == 2 else self.fine_3) or ''
