import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

PHOTO_COL_PX = 24 * 7 + 5  # độ rộng cột Hình ảnh (24 ký tự) theo pixel của Excel


class StoreAuditAction(models.Model):
    _name = 'store.audit.action'
    _description = 'Hành động khắc phục sau audit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'deadline, id'
    _rec_name = 'issue'

    audit_id = fields.Many2one('store.audit', string='Phiếu audit', required=True, ondelete='cascade', index=True)
    line_id = fields.Many2one(
        'store.audit.line', string='Tiêu chí', ondelete='set null',
        domain="[('audit_id', '=', audit_id)]")
    store_id = fields.Many2one(related='audit_id.store_id', store=True)
    date_found = fields.Date(string='Ngày phát hiện', default=fields.Date.context_today)
    issue = fields.Text(string='Lỗi / Vấn đề phát hiện', required=True)
    root_cause = fields.Text(string='Nguyên nhân gốc rễ')
    action_plan = fields.Text(string='Hành động khắc phục')
    responsible = fields.Char(string='Bộ phận phụ trách')
    responsible_ids = fields.Many2many(
        'hr.employee', 'store_audit_action_responsible_rel', 'action_id', 'employee_id', string='Người phụ trách')
    date_done = fields.Date(string='Ngày hoàn thành')
    reviewer_id = fields.Many2one('res.users', string='Kiểm Soát (cũ)', ondelete='set null')  # shortcut: giữ cột cũ cho migration, thay bằng reviewer_ids
    reviewer_ids = fields.Many2many(
        'res.users', 'store_audit_action_reviewer_rel', 'action_id', 'user_id', string='Kiểm Soát')
    control_done = fields.Boolean(string='Kết quả kiểm soát', help='Tích chọn = kiểm soát đã hoàn thành')
    review_note = fields.Char(string='Giám sát nghiệm thu')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'store_audit_action_attachment_rel', 'action_id', 'attachment_id', string='Bằng chứng')
    line_sequence = fields.Integer(related='line_id.sequence', string='STT tiêu chí')
    line_category = fields.Selection(related='line_id.category', string='Nhóm tiêu chí', store=True)
    line_max_score = fields.Float(related='line_id.max_score', string='Điểm chuẩn')
    line_actual_score = fields.Float(related='line_id.actual_score', string='Điểm đạt')
    audit_date = fields.Datetime(related='audit_id.audit_date', string='Ngày kiểm tra', store=True)
    audit_name = fields.Char(related='audit_id.name', string='Mã phiếu')
    auditor_id = fields.Many2one(related='audit_id.auditor_id', string='Người đánh giá')
    mien = fields.Selection(related='audit_id.mien', string='Miền')
    line_requirement = fields.Text(related='line_id.requirement', string='Quy định cơ bản')
    line_attachment_ids = fields.Many2many(related='line_id.attachment_ids', string='Hình ảnh', readonly=True)
    score_deduct = fields.Float(string='Điểm trừ', compute='_compute_score_deduct', store=True)

    can_edit_resp = fields.Boolean(compute='_compute_can_edit')
    can_edit_ctrl = fields.Boolean(compute='_compute_can_edit')

    @api.depends('responsible_ids', 'reviewer_ids')
    @api.depends_context('uid')
    def _compute_can_edit(self):
        """Khắc phục: chỉ user gắn với "Người phụ trách"; kiểm soát: chỉ user trong "Kiểm Soát" của bảng điểm đánh giá."""
        uid = self.env.uid
        for rec in self:
            rec.can_edit_resp = uid in rec.sudo().responsible_ids.user_id.ids
            rec.can_edit_ctrl = uid in rec.reviewer_ids.ids

    def write(self, vals):
        if not self.env.su:  # code hệ thống (sudo/cron) không bị chặn
            resp = {'action_plan', 'date_done', 'state'} & set(vals)
            ctrl = {'control_done', 'review_note'} & set(vals)
            for rec in self:
                if 'issue' in vals and vals['issue'] != rec.issue:
                    raise AccessError(_('Chi tiết lỗi là nội dung của người đánh giá, không được chỉnh sửa.'))
                if resp and not rec.can_edit_resp:
                    raise AccessError(_('Chỉ người phụ trách của tiêu chí này mới được cập nhật việc khắc phục.'))
                if ctrl and not rec.can_edit_ctrl:
                    raise AccessError(_('Chỉ người kiểm soát của tiêu chí này mới được cập nhật kết quả kiểm soát.'))
        return super().write(vals)

    @api.depends('line_id.max_score', 'line_id.actual_score')
    def _compute_score_deduct(self):
        for rec in self:
            rec.score_deduct = rec.line_id.actual_score - rec.line_id.max_score
    deadline = fields.Date(string='Hạn hoàn thành (SLA)', tracking=True)
    state = fields.Selection([
        ('todo', 'Chưa làm'),
        ('doing', 'Đang làm'),
        ('done', 'Hoàn thành'),
    ], string='Trạng thái', default='todo', required=True, tracking=True)

    def web_read(self, specification):
        """User thường không xem được hồ sơ nhân viên khác (hr_employee_self_only) nên đọc người phụ trách bằng sudo."""
        if 'responsible_ids' not in specification:
            return super().web_read(specification)
        res = super().web_read({k: v for k, v in specification.items() if k != 'responsible_ids'})
        for vals in res:
            rec = self.browse(vals['id']).sudo()
            rec.invalidate_recordset(['responsible_ids'])  # cache có thể đang giữ giá trị đã bị record rule nhân viên lọc
            emps = rec.responsible_ids
            vals['responsible_ids'] = [{'id': e.id, 'display_name': e.display_name} for e in emps]
        return res

    @api.model
    def get_violation_header(self, audit_id):
        """Số liệu tiêu đề popup Xử lý sai phạm: điểm đạt / chuẩn của các tiêu chí sai phạm và tiến độ khắc phục."""
        audit = self.env['store.audit'].browse(audit_id)
        acts = audit.action_ids.filtered(lambda a: a.line_id.error_count > 0)
        done = len(acts.filtered(lambda a: a.state == 'done'))
        total = len(acts)
        date = fields.Datetime.context_timestamp(self, audit.audit_date).strftime('%d/%m/%Y') if audit.audit_date else ''
        return {
            'company_id': self.env.company.id,
            'store': audit.store_id.display_name or '',
            'date': date,
            # điểm đạt / chuẩn của cả phiếu; điểm trừ chỉ của các tiêu chí đang xử lý trong bảng
            'max': audit.max_score,
            'got': audit.total_score,
            'deduct': sum(acts.line_id.mapped('actual_score')) - sum(acts.line_id.mapped('max_score')),
            'total': total,
            'done': done,
            'status': 'Hoàn thành' if total and done == total else 'Đang xử lý',
        }

    @api.model
    def export_violation_xlsx(self, audit_id):
        """Kết xuất popup Xử lý sai phạm ra Excel đúng bố cục trên web: logo, tiêu đề, 4 thẻ số liệu, bảng nhóm theo
        nhóm tiêu chí với màu tiêu đề / ô như giao diện; trả về {name, data base64}."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        h = self.get_violation_header(audit_id)
        audit = self.env['store.audit'].browse(audit_id)
        acts = audit.action_ids.filtered(lambda a: a.line_id.error_count > 0).sorted(
            lambda a: (a.line_category or '', a.line_sequence))
        states = dict(self._fields['state'].selection)
        cats = dict(self._fields['line_category']._description_selection(self.env))
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Xu ly sai pham')
        sheet.hide_gridlines(2)
        fmt = book.add_format
        title = fmt({'bold': True, 'font_size': 20, 'font_color': '#12285F', 'valign': 'vcenter'})
        sub = fmt({'font_size': 11, 'font_color': '#475569', 'valign': 'vcenter'})

        def card(bg, border, color=None):
            lab = {'bg_color': bg, 'font_size': 10, 'bold': True, 'font_color': '#334155', 'left': 1, 'right': 1,
                   'top': 1, 'border_color': border, 'align': 'center', 'valign': 'vcenter'}
            val = {'bg_color': bg, 'font_size': 18, 'bold': True, 'font_color': color or '#12285F', 'left': 1,
                   'right': 1, 'bottom': 1, 'border_color': border, 'align': 'center', 'valign': 'vcenter'}
            return fmt(lab), fmt(val)

        def head_fmt(bg):
            return fmt({'bold': True, 'font_color': '#FFFFFF', 'bg_color': bg, 'align': 'center', 'valign': 'vcenter',
                        'border': 1, 'text_wrap': True})

        grp = fmt({'bold': True, 'bg_color': '#DCE6F2', 'font_color': '#1E3A8A', 'border': 1})
        orange = '#FFF1E0'

        def body(bg=None, align=None, numeric=False):
            d = {'border': 1, 'valign': 'vcenter', 'text_wrap': True}
            if bg:
                d['bg_color'] = bg
            if align:
                d['align'] = align
            return fmt(d)

        cols = [('STT', 6, '#1E3A6E'), ('Tiêu chí sai phạm', 30, '#1E3A6E'),
                ('Chi tiết lỗi giám sát ghi nhận', 36, '#1E3A6E'), ('Điểm chuẩn', 11, '#1E3A6E'),
                ('Điểm đạt', 11, '#1E3A6E'), ('Điểm trừ', 11, '#1E3A6E'), ('Người phụ trách', 24, '#15803D'),
                ('Nội dung khắc phục', 36, '#15803D'), ('Ngày hoàn thành', 16, '#15803D'),
                ('Trạng thái xử lý', 16, '#15803D'), ('Kiểm Soát', 24, '#C2410C'),
                ('Kết quả kiểm soát', 18, '#C2410C')]
        n = len(cols)
        for i, (_name, width, _bg) in enumerate(cols):
            sheet.set_column(i, i, width)
        for r in (0, 1, 2):
            sheet.set_row(r, 26)
        # logo công ty (cao ~72px) + tiêu đề
        logo = self.env.company.logo_web or self.env.company.logo
        if logo:
            raw = base64.b64decode(logo)
            scale = 1.0
            try:
                from PIL import Image
                scale = 72.0 / Image.open(io.BytesIO(raw)).height
            except Exception:  # shortcut: không đọc được kích thước thì giữ nguyên cỡ ảnh
                pass
            sheet.insert_image(0, 0, 'logo.png', {'image_data': io.BytesIO(raw), 'x_scale': scale, 'y_scale': scale,
                                                  'x_offset': 4, 'y_offset': 2, 'object_position': 2})
        sheet.merge_range(0, 2, 1, 5, 'BIÊN BẢN XỬ LÝ SAI PHẠM', title)
        sheet.merge_range(2, 2, 2, 5, 'Cửa hàng: %s   |   Ngày kiểm tra: %s' % (h['store'], h['date']), sub)
        # 4 thẻ số liệu (mỗi thẻ 3 cột): nhãn + giá trị
        trim = lambda v: ('%g' % v)
        pct = int(round(h['done'] * 100.0 / h['total'])) if h['total'] else 0
        cards = [
            ('Tổng điểm đạt', '%s / %s' % (trim(h['got']), trim(h['max'])), '#E8F0FF', '#DBE4F3', None),
            ('Tổng điểm trừ', trim(h['deduct']), '#FDE8EA', '#FBCFD5', '#DC2626'),
            ('Số lỗi cần xử lý', '%s tiêu chí' % h['total'], '#E6F7EC', '#BFE8CD', None),
            ('Tiến độ khắc phục', '%s / %s (%s%%)' % (h['done'], h['total'], pct), '#EEF1F6', '#DBE4F3', None),
        ]
        sheet.set_row(4, 20)
        sheet.set_row(5, 34)
        for k, (lab, val, bg, border, color) in enumerate(cards):
            fl, fv = card(bg, border, color)
            c0 = k * 3
            sheet.merge_range(4, c0, 4, c0 + 2, lab, fl)
            sheet.merge_range(5, c0, 5, c0 + 2, val, fv)
        # bảng
        top = 7
        sheet.set_row(top, 32)
        for i, (name, _w, bg) in enumerate(cols):
            sheet.write(top, i, name, head_fmt(bg))
        r, last = top + 1, None
        for a in acts:
            if a.line_category != last:
                last = a.line_category
                sheet.merge_range(r, 0, r, n - 1, cats.get(last, '') or '', grp)
                r += 1
            a = a.sudo()
            row = [a.line_sequence, a.line_id.name, a.issue or '', a.line_max_score, a.line_actual_score,
                   a.score_deduct, ', '.join(a.responsible_ids.mapped('name')), a.action_plan or '',
                   a.date_done.strftime('%d/%m/%Y') if a.date_done else '', states.get(a.state, ''),
                   ', '.join(a.reviewer_ids.mapped('name')), 'Đã kiểm soát' if a.control_done else 'Chưa']
            for i, v in enumerate(row):
                bg = orange if i >= 10 else None
                align = 'center' if i in (0, 3, 4, 5, 8, 9, 11) else None
                sheet.write(r, i, v, body(bg, align))
            r += 1
        sheet.freeze_panes(top + 1, 0)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Xu_ly_sai_pham_%s_%s.xlsx' % ((audit.name or 'phieu').replace('/', '-'), stamp),
                'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def violation_all_print_data(self, domain):
        """Dữ liệu in "Danh sách xử lý sai phạm" (cùng 14 cột như Excel), nhóm theo phiếu của từng cửa hàng."""
        acts = self.search(list(domain) + [('line_id.error_count', '>', 0)],
                           order='store_id, audit_date desc, audit_id, line_category, line_sequence')
        states = dict(self._fields['state'].selection)
        headers = [('STT', 0), ('Tiêu chuẩn, yêu cầu', 0), ('Quy định cơ bản', 0), ('Điểm chuẩn', 0),
                   ('Điểm đánh giá', 0), ('Chi tiết lỗi', 0), ('Hình ảnh', 0), ('Điểm trừ', 1),
                   ('Người phụ trách', 1), ('Nội dung khắc phục', 1), ('Ngày hoàn thành', 1),
                   ('Trạng thái xử lý', 1), ('Kiểm Soát', 2), ('Kết quả kiểm soát', 2)]
        groups, last = [], None
        for a in acts.sudo():
            if a.audit_id != last:
                last = a.audit_id
                when = fields.Datetime.context_timestamp(self, a.audit_date) if a.audit_date else None
                groups.append({'title': 'Cửa hàng: %s  |  Phiếu: %s  |  Ngày kiểm tra: %s' % (
                    a.store_id.display_name or '', a.audit_name or '', when.strftime('%d/%m/%Y') if when else ''),
                    'rows': []})
            photo = a.line_id.attachment_ids.filtered(lambda t: (t.mimetype or '').startswith('image/'))[:1]
            groups[-1]['rows'].append({'photo': photo.id or 0, 'cells': [
                a.line_sequence, a.line_id.name, a.line_requirement or '', a.line_max_score, a.line_actual_score,
                a.issue or '', '', a.score_deduct, ', '.join(a.responsible_ids.mapped('name')), a.action_plan or '',
                a.date_done.strftime('%d/%m/%Y') if a.date_done else '', states.get(a.state, ''),
                ', '.join(a.reviewer_ids.mapped('name')), 'Đã kiểm soát' if a.control_done else 'Chưa']})
        return {'headers': headers, 'groups': groups}

    @api.model
    def export_violation_all_xlsx(self, domain):
        """Danh sách xử lý sai phạm = bảng 1 (checklist giám sát: STT, tiêu chuẩn / yêu cầu, quy định cơ bản, điểm chuẩn,
        điểm đánh giá, chi tiết lỗi, hình ảnh) + bảng 2 (biên bản xử lý: điểm trừ, người phụ trách, nội dung khắc phục,
        ngày hoàn thành, trạng thái, kiểm soát, kết quả kiểm soát); nhóm theo phiếu của từng cửa hàng."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        from odoo.tools.image import image_process
        acts = self.search(list(domain) + [('line_id.error_count', '>', 0)],
                           order='store_id, audit_date desc, audit_id, line_category, line_sequence')
        states = dict(self._fields['state'].selection)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Danh sach xu ly sai pham')
        fmt = book.add_format
        big = fmt({'bold': True, 'font_size': 16, 'font_color': '#12285F'})
        grp = fmt({'bold': True, 'bg_color': '#DCE6F2', 'font_color': '#1E3A8A', 'border': 1})
        cell = fmt({'border': 1, 'valign': 'top', 'text_wrap': True})
        ctr = fmt({'border': 1, 'align': 'center', 'valign': 'top', 'text_wrap': True})
        orange = fmt({'border': 1, 'valign': 'top', 'text_wrap': True, 'bg_color': '#FFF1E0'})
        orange_c = fmt({'border': 1, 'align': 'center', 'valign': 'top', 'bg_color': '#FFF1E0'})

        def head(bg):
            return fmt({'bold': True, 'font_color': '#FFFFFF', 'bg_color': bg, 'align': 'center', 'valign': 'vcenter',
                        'border': 1, 'text_wrap': True})

        cols = [('STT', 7, '#1E3A6E'), ('Tiêu chuẩn, yêu cầu', 30, '#1E3A6E'), ('Quy định cơ bản', 40, '#1E3A6E'),
                ('Điểm chuẩn', 10, '#1E3A6E'), ('Điểm đánh giá', 11, '#1E3A6E'), ('Chi tiết lỗi', 34, '#1E3A6E'),
                ('Hình ảnh', 24, '#1E3A6E'), ('Điểm trừ', 10, '#15803D'), ('Người phụ trách', 22, '#15803D'),
                ('Nội dung khắc phục', 34, '#15803D'), ('Ngày hoàn thành', 15, '#15803D'),
                ('Trạng thái xử lý', 15, '#15803D'), ('Kiểm Soát', 22, '#C2410C'), ('Kết quả kiểm soát', 17, '#C2410C')]
        n = len(cols)
        sheet.merge_range(0, 0, 0, n - 1, 'DANH SÁCH XỬ LÝ SAI PHẠM', big)
        sheet.set_row(2, 32)
        for i, (name, width, bg) in enumerate(cols):
            sheet.write(2, i, name, head(bg))
            sheet.set_column(i, i, width)
        r, last = 3, None
        for a in acts:
            a = a.sudo()
            if a.audit_id != last:
                last = a.audit_id
                when = fields.Datetime.context_timestamp(self, a.audit_date) if a.audit_date else None
                sheet.merge_range(r, 0, r, n - 1, 'Cửa hàng: %s  |  Phiếu: %s  |  Ngày kiểm tra: %s' % (
                    a.store_id.display_name or '', a.audit_name or '', when.strftime('%d/%m/%Y') if when else ''), grp)
                r += 1
            row = [a.line_sequence, a.line_id.name, a.line_requirement or '', a.line_max_score, a.line_actual_score,
                   a.issue or '', '', a.score_deduct, ', '.join(a.responsible_ids.mapped('name')),
                   a.action_plan or '', a.date_done.strftime('%d/%m/%Y') if a.date_done else '',
                   states.get(a.state, ''), ', '.join(a.reviewer_ids.mapped('name')),
                   'Đã kiểm soát' if a.control_done else 'Chưa']
            for i, v in enumerate(row):
                if i >= 12:
                    f = orange_c if i == 13 else orange
                else:
                    f = ctr if i in (0, 3, 4, 7, 10, 11) else cell
                sheet.write(r, i, v, f)
            # Ảnh phủ kín đúng ô (không lề) và ô cao theo tỉ lệ ảnh: kéo giãn cột / dòng thì ảnh co giãn theo ("move and size with cells")
            sheet.set_row(r, 75)
            for att in a.line_id.attachment_ids.filtered(lambda t: (t.mimetype or '').startswith('image/'))[:1]:
                try:
                    from PIL import Image
                    raw = image_process(att.raw, size=(600, 600), quality=85)
                    w, h = Image.open(io.BytesIO(raw)).size
                    row_px = max(90, min(320, int(round(PHOTO_COL_PX * h / w))))  # shortcut: ảnh quá dài bị kéo giãn nhẹ khi vượt 320px
                    sheet.set_row(r, row_px * 0.75)
                    sheet.insert_image(r, 6, 'p.png', {'image_data': io.BytesIO(raw), 'x_scale': PHOTO_COL_PX / w,
                                                       'y_scale': row_px / h, 'x_offset': 0, 'y_offset': 0,
                                                       'object_position': 1})
                except Exception:  # ảnh hỏng thì bỏ qua, không làm hỏng cả file
                    pass
            r += 1
        sheet.freeze_panes(3, 2)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Danh_sach_xu_ly_sai_pham_%s.xlsx' % stamp,
                'data': base64.b64encode(buf.getvalue()).decode()}

    def _sync_violation_actions(self):
        """Danh sách tổng thể phải đủ mọi lỗi đã ghi nhận (NVBH / ASM / GS), kể cả phiếu chưa ai mở popup:
        tạo dòng khắc phục còn thiếu cho các phiếu đã hoàn tất có lỗi."""
        audits = self.env['store.audit'].sudo().search([('state', '!=', 'draft'), ('error_count', '>', 0)])
        for audit in audits:
            audit.action_create_actions()

    @api.model
    def web_search_read(self, *args, **kwargs):  # không đánh dấu readonly: có thể tạo dòng khắc phục còn thiếu
        if self.env.context.get('sync_violations'):
            self._sync_violation_actions()
        return super().web_search_read(*args, **kwargs)

    @api.model
    def web_read_group(self, *args, **kwargs):
        if self.env.context.get('sync_violations'):
            self._sync_violation_actions()
        return super().web_read_group(*args, **kwargs)
