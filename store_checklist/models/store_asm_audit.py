# -*- coding: utf-8 -*-
"""Phiếu Audit & Đánh giá cửa hàng (ASM): ASM trực tiếp kiểm tra cửa hàng theo danh mục tiêu chí (Cài đặt › Công việc checklist
NVBH › Danh sách công việc Audit), chấm Đạt / Cần cải thiện / Không đạt kèm dẫn chứng, tổng kết nhận xét + yêu cầu khắc phục
(Action Plan) rồi gửi CHT và cấp trên."""
import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_notify import bot_send, card

AUDIT_GROUPS = [
    '01 – Nhân sự và tác phong',
    '02 – Vệ sinh và vận hành cửa hàng',
    '03 – Tài sản, thiết bị và CCDC',
    '04 – Marketing và chương trình bán hàng',
    '05 – Hàng hóa và tồn kho',
    '06 – POSM và trưng bày',
    '07 – Hồ sơ và tuân thủ',
]

# 30 tiêu chí mặc định: (tiêu chí, tiêu chuẩn, số nhóm 1..7)
AUDIT_DEFAULT = [
    ('Nhân viên có mặt đúng giờ, đúng vị trí và đúng lịch phân công', 'Đúng đồng phục, đúng vị trí', 1),
    ('Nhân viên mặc đồng phục, đeo bảng tên và tuân thủ quy định tác phong', 'Đồng phục LUG chuẩn, đeo bảng tên', 1),
    ('Nhân viên chủ động chào hỏi, tư vấn và hỗ trợ khách hàng', 'Chào khách trong 5s, tư vấn nhiệt tình', 1),
    ('Nhân viên nắm rõ thông tin sản phẩm, giá bán và chương trình khuyến mãi', 'Tư vấn chính xác CTKM hiện hành', 1),
    ('CHT phân công, giám sát và điều phối nhân sự hợp lý', 'Bố trí đủ người giờ cao điểm', 1),
    ('CHT nắm bắt năng lực nhân viên và có kế hoạch đào tạo nhân sự', 'Có đánh giá & kèm cặp nhân sự kế thừa', 1),
    ('Sàn nhà, cửa kính và khu vực bán hàng sạch sẽ', 'Sạch sẽ, không bụi bẩn', 2),
    ('Quầy kệ, khu vực tư vấn và khu vực thanh toán gọn gàng', 'Không để vật dụng cá nhân bừa bộn', 2),
    ('Khu vực kho và khu vực làm việc được vệ sinh sạch sẽ', 'Kho sạch, thông thoáng, không rác tồn', 2),
    ('Thiết bị điện, máy lạnh, máy tính và hệ thống chiếu sáng hoạt động bình thường', 'Đầy đủ ánh sáng, nhiệt độ chuẩn', 2),
    ('Cửa hàng thực hiện đúng quy trình bàn giao ca', 'Ghi chép sổ bàn giao & ký xác nhận đủ', 2),
    ('Cửa hàng tuân thủ quy định PCCC, an toàn và lối thoát hiểm', 'Lối thoát hiểm thông thoáng, bình PCCC đạt hạn', 2),
    ('Tài sản, thiết bị và CCDC được bảo quản đúng quy định', 'Sắp xếp đúng vị trí, không thất thoát', 3),
    ('Thiết bị, tài sản không có tình trạng hư hỏng hoặc xuống cấp chưa được xử lý', 'Không có thiết bị hỏng chưa báo IT/Admin', 3),
    ('Số lượng và tình trạng CCDC thực tế phù hợp với danh mục quản lý', 'Khớp 100% biên bản bàn giao CCDC', 3),
    ('Chương trình khuyến mãi đang triển khai đúng nội dung và thời gian', 'Áp dụng đúng thể lệ CTKM hiện hành', 4),
    ('Bảng thông tin chương trình, giá bán và ưu đãi được cập nhật chính xác', 'Thông tin rõ ràng, không dùng bảng cũ', 4),
    ('Cửa hàng thực hiện đầy đủ các nội dung nhận diện và truyền thông theo yêu cầu', 'TV/Loa phát clip nhận diện đúng quy định', 4),
    ('Hàng hóa được vệ sinh sạch sẽ, không bám bụi', 'Vali, balo trên kệ sạch sẽ, không trầy xước', 5),
    ('Hàng hóa trong kho được sắp xếp đúng khu vực, dễ tìm kiếm', 'Đúng khu vực, gọn gàng', 5),
    ('Số lượng hàng hóa thực tế khớp với dữ liệu kiểm tra trên hệ thống', 'Không chênh lệch tồn thực tế & phần mềm', 5),
    ('Hàng hóa hư hỏng, lỗi, mất mát được nhận diện và báo cáo', 'Tách riêng hàng lỗi & lập biên bản kịp thời', 5),
    ('Thẻ kho và sổ theo dõi nhập xuất tồn được cập nhật đầy đủ', 'Chứng từ nhập xuất lưu trữ đủ chữ ký', 5),
    ('Hàng hóa được bổ sung kịp thời, không để thiếu hàng trên quầy kệ', 'Châm hàng ngay sau khi bán, không để trống kệ', 5),
    ('Hàng hóa được trưng bày đúng sơ đồ và guideline', 'Đúng layout màu sắc, kích thước chuẩn LUG', 6),
    ('Tem giá, tem tag và bảng giá chính xác, đầy đủ', 'Đầy đủ, chính xác', 6),
    ('Bảng sale, POSM được bố trí đúng vị trí, đúng quy chuẩn', 'Wobbler, standee đặt đúng điểm chạm', 6),
    ('Khu vực trưng bày đảm bảo tính thẩm mỹ và nhận diện thương hiệu', 'Gọn đẹp, bắt mắt, không che khuất logo', 6),
    ('Hồ sơ, giấy phép kinh doanh và tài liệu bắt buộc được lưu trữ đầy đủ', 'GPKD, hồ sơ PCCC lưu tại quầy dễ xuất trình', 7),
    ('Bill, chứng từ và hồ sơ bàn giao được lưu trữ, sắp xếp đúng quy định', 'Đóng tập theo ngày, đối chiếu khớp doanh thu', 7),
]

RESULTS = [('pass', 'Đạt'), ('improve', 'Cần cải thiện'), ('fail', 'Không đạt')]
REMARK_CATS = [('hr', 'Nhân sự'), ('ops', 'Vận hành'), ('goods', 'Hàng hóa'), ('cost', 'Chi phí'), ('posm', 'POSM')]
PLAN_STATES = [('in_progress', 'Đang xử lý'), ('done', 'Đã khắc phục')]


# ======================================================================
# Danh mục: Cài đặt › Công việc checklist NVBH › Danh sách công việc Audit
# ======================================================================
class StoreAsmAuditGroup(models.Model):
    _name = 'store.asm.audit.group'
    _inherit = 'store.cht.task.group'
    _description = 'Nhóm tiêu chí Audit cửa hàng'

    _perm_menu = 'audit_task'
    _form_view_xmlid = 'store_checklist.view_store_asm_audit_group_form'
    _default_group_labels = AUDIT_GROUPS


class StoreAsmAuditCrit(models.Model):
    _name = 'store.asm.audit.crit'
    _inherit = 'store.perm.mixin'
    _description = 'Tiêu chí Audit cửa hàng (ASM)'
    _order = 'sequence, id'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')
    _perm_menu = 'audit_task'

    def _perm_key(self):
        return self._perm_menu

    @api.model
    def _perm_key_vals(self, vals):
        return self._perm_menu

    sequence = fields.Integer(string='STT', default=10)
    name = fields.Char(string='Tiêu chí ASM trực tiếp kiểm tra', required=True)
    standard = fields.Char(string='Tiêu chuẩn')
    group_id = fields.Many2one('store.asm.audit.group', string='Nhóm tiêu chí', ondelete='restrict', index=True)
    score = fields.Integer(string='Điểm chuẩn', default=2, help='Đạt = điểm chuẩn; Cần cải thiện = 1/2 điểm chuẩn; Không đạt = 0')
    active = fields.Boolean(default=True)

    def action_open_popup(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Tiêu chí Audit', 'res_model': self._name, 'res_id': self.id,
                'views': [(False, 'form')], 'target': 'new'}

    @api.model
    def _seed_default(self):
        """Tạo 7 nhóm + 30 tiêu chí Audit mặc định (chỉ khi danh mục đang trống)."""
        if self.sudo().with_context(active_test=False).search_count([]):
            return
        Group = self.env['store.asm.audit.group'].sudo()
        Group._ensure_default_groups()
        groups = {g.name: g.id for g in Group.search([])}
        self.sudo().create([{'sequence': i, 'name': name, 'standard': std, 'group_id': groups.get(AUDIT_GROUPS[g - 1]), 'score': 2}
                            for i, (name, std, g) in enumerate(AUDIT_DEFAULT, 1)])

    _XLS_HEAD = ['STT', 'Nhóm tiêu chí', 'Tiêu chí', 'Tiêu chuẩn', 'Điểm chuẩn']

    @api.model
    def export_xlsx(self):
        """Xuất Danh sách công việc Audit ra Excel (file xuất nhập lại được)."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        crits = self.search([], order='sequence, id')
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Tieu chi Audit')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center', 'valign': 'vcenter',
                                'border': 1, 'text_wrap': True})
        cell = book.add_format({'border': 1, 'valign': 'top', 'text_wrap': True})
        for i, (h, w) in enumerate(zip(self._XLS_HEAD, [6, 34, 60, 40, 10])):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        for r, c in enumerate(crits, 1):
            for col, v in enumerate([c.sequence, c.group_id.name or '', c.name, c.standard or '', c.score]):
                sheet.write(r, col, v, cell)
        sheet.freeze_panes(1, 0)
        book.close()
        return {'name': 'Tieu_chi_Audit.xlsx', 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def import_xlsx(self, data):
        """Nhập Danh sách công việc Audit (cùng cột với file xuất): trùng Tiêu chí thì cập nhật, chưa có thì thêm."""
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

        hi = next((i for i, r in enumerate(rows) if 'tiêu chí' in [txt(c).casefold() for c in r]), None)
        if hi is None:
            raise UserError(_('Không tìm thấy dòng tiêu đề có cột "Tiêu chí".'))
        col = {txt(c).casefold(): i for i, c in enumerate(rows[hi]) if txt(c)}

        def get(r, name):
            i = col.get(name.casefold())
            return txt(r[i]) if i is not None and i < len(r) else ''

        created = updated = 0
        errors = []
        existing = {(c.name or '').strip().casefold(): c for c in self.with_context(active_test=False).search([])}
        for n, r in enumerate(rows[hi + 1:], hi + 2):
            name = get(r, 'Tiêu chí')
            if not name:
                continue
            vals = {'name': name, 'standard': get(r, 'Tiêu chuẩn') or False, 'active': True}
            if get(r, 'Nhóm tiêu chí'):
                vals['group_id'] = self.env['store.asm.audit.group']._find_or_create(get(r, 'Nhóm tiêu chí')).id or False
            try:
                if get(r, 'STT'):
                    vals['sequence'] = int(float(get(r, 'STT').replace(',', '.')))
                if get(r, 'Điểm chuẩn'):
                    vals['score'] = int(float(get(r, 'Điểm chuẩn').replace(',', '.')))
            except ValueError:
                errors.append('Dòng %s: STT / Điểm chuẩn không phải số' % n)
                continue
            rec = existing.get(name.casefold())
            if rec:
                rec.write(vals)
                updated += 1
            else:
                existing[name.casefold()] = self.create(vals)
                created += 1
        return {'created': created, 'updated': updated, 'errors': errors}


# ======================================================================
# Phiếu Audit & Đánh giá cửa hàng (ASM)
# ======================================================================
class StoreAsmAudit(models.Model):
    _name = 'store.asm.audit'
    _description = 'Phiếu Audit & Đánh giá cửa hàng (ASM)'
    _order = 'audit_date desc, id desc'

    name = fields.Char(string='Mã phiếu', compute='_compute_name', store=True)
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', string='ASM kiểm tra', required=True, default=lambda self: self.env.user, index=True)
    audit_date = fields.Date(string='Ngày kiểm tra', required=True, default=fields.Date.context_today, index=True)
    state = fields.Selection([('draft', 'Đang kiểm tra'), ('submitted', 'Đã gửi CHT & cấp trên')], default='draft', string='Trạng thái')
    submit_date = fields.Datetime(string='Ngày gửi')
    line_ids = fields.One2many('store.asm.audit.line', 'sheet_id', string='Tiêu chí')
    remark_ids = fields.One2many('store.asm.audit.remark', 'sheet_id', string='Nhận xét và đề xuất của ASM')
    plan_ids = fields.One2many('store.asm.audit.plan', 'sheet_id', string='Yêu cầu khắc phục')
    comment = fields.Text(string='Nhận xét tổng quan của ASM')
    total = fields.Integer(string='Tổng tiêu chí', compute='_compute_summary', store=True)
    rated = fields.Integer(string='Đã chấm', compute='_compute_summary', store=True)
    pass_count = fields.Integer(string='Đạt', compute='_compute_summary', store=True)
    improve_count = fields.Integer(string='Cần cải thiện', compute='_compute_summary', store=True)
    fail_count = fields.Integer(string='Không đạt', compute='_compute_summary', store=True)
    score = fields.Float(string='Điểm Audit', compute='_compute_summary', store=True)
    max_score = fields.Float(string='Điểm tối đa', compute='_compute_summary', store=True)
    rate = fields.Float(string='Tỷ lệ đạt (%)', compute='_compute_summary', store=True)

    @api.depends('store_id', 'audit_date')
    def _compute_name(self):
        for rec in self:
            rec.name = 'AUD/%s/%s' % (rec.store_id.code or rec.store_id.name or '', rec.audit_date.strftime('%d%m%Y') if rec.audit_date else '')

    @api.depends('line_ids.result', 'line_ids.max_score')
    def _compute_summary(self):
        for rec in self:
            lines = rec.line_ids
            rec.total = len(lines)
            rec.rated = len(lines.filtered('result'))
            rec.pass_count = len(lines.filtered(lambda l: l.result == 'pass'))
            rec.improve_count = len(lines.filtered(lambda l: l.result == 'improve'))
            rec.fail_count = len(lines.filtered(lambda l: l.result == 'fail'))
            rec.score = sum(lines.mapped('score'))
            rec.max_score = sum(lines.mapped('max_score'))
            rec.rate = round(100.0 * rec.score / rec.max_score, 1) if rec.max_score else 0.0

    # ---------------- quyền ----------------
    @api.model
    def _audit_rights(self):
        rights = self.env['store.perm.rule']._rights()
        if rights is None:
            return {'read': True, 'create': True, 'write': True}
        r = rights.get('nvbh_audit') or {}
        return {'read': bool(r.get('read')), 'create': bool(r.get('create')), 'write': bool(r.get('write') or r.get('create'))}

    @api.model
    def _audit_store_ids(self):
        return {s['id'] for s in self.env['store.nvbh.check'].get_my_stores()}

    def _can_edit(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager'):
            return True
        return self.user_id == user and self._audit_rights()['write']

    def _check_read(self):
        if not self._audit_rights()['read']:
            raise AccessError(_('Bạn không có quyền xem Phiếu Audit cửa hàng.'))
        for rec in self:
            if rec.store_id.id not in self._audit_store_ids() and not self.env.user.has_group('base.group_system'):
                raise AccessError(_('Bạn không có quyền xem phiếu Audit của cửa hàng %s.') % rec.store_id.display_name)

    # ---------------- dữ liệu trang ----------------
    def _payload(self):
        """Dữ liệu phiếu cho trang (phiếu đã lưu: self; chưa lưu: dựng từ danh mục tiêu chí)."""
        today = fields.Date.context_today(self)
        if self:
            s = self.sudo()
            lines = [{
                'id': l.id, 'crit_id': l.crit_id.id, 'sequence': l.sequence, 'group': l.group_name or 'Khác', 'name': l.name,
                'standard': l.standard or '', 'max_score': l.max_score, 'result': l.result or '', 'note': l.note or '',
                'photos': [{'id': a.id, 'name': a.name} for a in l.photo_ids],
            } for l in s.line_ids.sorted(lambda l: (l.group_seq, l.sequence, l.id))]
            return {
                'id': s.id, 'name': s.name, 'state': s.state, 'store_id': s.store_id.id, 'store': s.store_id.display_name,
                'store_code': s.store_id.code or '', 'date': str(s.audit_date), 'user': s.user_id.name or '',
                'can_edit': self._can_edit(), 'lines': lines, 'comment': s.comment or '',
                'remarks': [{'id': r.id, 'category': r.category, 'text': r.text or ''} for r in s.remark_ids],
                'plans': [{'id': p.id, 'content': p.content or '', 'owner': p.owner or '', 'deadline': str(p.deadline) if p.deadline else '',
                           'state': p.state, 'overdue': bool(p.deadline and p.deadline < today and p.state != 'done')} for p in s.plan_ids],
            }
        crits = self.env['store.asm.audit.crit'].sudo().search([])
        crits = crits.sorted(lambda c: (c.group_id.sequence if c.group_id else 9999, c.group_id.id or 0, c.sequence, c.id))
        return {
            'id': False, 'name': '', 'state': 'draft', 'user': self.env.user.name, 'can_edit': self._audit_rights()['create'],
            'lines': [{'id': False, 'crit_id': c.id, 'sequence': c.sequence, 'group': c.group_id.name or 'Khác', 'name': c.name,
                       'standard': c.standard or '', 'max_score': c.score, 'result': '', 'note': '', 'photos': []} for c in crits],
            'remarks': [], 'plans': [], 'comment': '',
        }

    @api.model
    def get_audit_page(self, store_id=None, audit_date=None, audit_id=None):
        """Trang Phiếu Audit: danh sách cửa hàng được xem, phiếu của cửa hàng + ngày (chưa có thì phiếu trống theo danh mục tiêu chí)
        và lịch sử các phiếu gần nhất của cửa hàng."""
        if not self._audit_rights()['read']:
            raise AccessError(_('Bạn không có quyền xem Phiếu Audit cửa hàng.'))
        stores = self.env['store.nvbh.check'].get_my_stores()
        ids = {s['id'] for s in stores}
        sheet = self.browse()
        if audit_id:
            sheet = self.sudo().browse(int(audit_id)).exists()
            sheet._check_read()
            store_id, audit_date = sheet.store_id.id, str(sheet.audit_date)
        day = fields.Date.to_date(audit_date) if audit_date else fields.Date.context_today(self)
        if not store_id or int(store_id) not in ids:
            store_id = stores[0]['id'] if stores else False
        if store_id and not sheet:
            sheet = self.sudo().search([('store_id', '=', int(store_id)), ('audit_date', '=', day)], order='id desc', limit=1)
        history = self.sudo().search([('store_id', '=', int(store_id))], limit=30) if store_id else self.browse()
        payload = self.browse(sheet.id)._payload() if sheet else self._payload()
        return {
            'stores': stores, 'store_id': store_id or False, 'date': str(day), 'sheet': payload,
            'history': [{'id': h.id, 'date': h.audit_date.strftime('%d/%m/%Y'), 'user': h.user_id.name or '', 'rate': h.rate,
                         'state': h.state} for h in history],
        }

    @api.model
    def get_audit_list(self, month=None, store_id=None, mien=None, q=None):
        """Danh sách phiếu Audit (giống Danh sách Checklist GS): lọc theo tháng (YYYY-MM), cửa hàng, miền, từ khóa."""
        if not self._audit_rights()['read']:
            raise AccessError(_('Bạn không có quyền xem Phiếu Audit cửa hàng.'))
        stores = self.env['store.nvbh.check'].get_my_stores()
        mien_of = {s['id']: s.get('mien') or '' for s in stores}
        ids = set(mien_of)
        if store_id:
            ids &= {int(store_id)}
        if mien == 'other':
            ids = {i for i in ids if mien_of[i] not in ('Nam', 'ĐTT', 'Bắc')}
        elif mien:
            ids = {i for i in ids if mien_of[i] == mien}
        domain = [('store_id', 'in', list(ids))]
        if month:
            try:
                y, m = (int(x) for x in str(month).split('-')[:2])
                start = fields.Date.to_date('%04d-%02d-01' % (y, m))
                end = fields.Date.to_date('%04d-%02d-01' % (y + (m == 12), 1 if m == 12 else m + 1))
                domain += [('audit_date', '>=', start), ('audit_date', '<', end)]
            except ValueError:
                pass
        if q:
            domain += ['|', '|', ('name', 'ilike', q), ('store_id.name', 'ilike', q), ('user_id.name', 'ilike', q)]
        rows = []
        for s in self.sudo().search(domain, order='audit_date desc, id desc', limit=1000):
            pct = s.rate
            rows.append({
                'id': s.id, 'name': s.name or '', 'date': s.audit_date.strftime('%d/%m/%Y') if s.audit_date else '',
                'store_id': s.store_id.id, 'store': s.store_id.display_name or '', 'store_code': s.store_id.code or '',
                'mien': mien_of.get(s.store_id.id, ''), 'user': s.user_id.name or '',
                'score': s.score, 'max_score': s.max_score, 'rate': pct, 'rated': s.rated, 'total': s.total,
                'errors': s.improve_count + s.fail_count, 'improve': s.improve_count, 'fail': s.fail_count,
                'rank': 'Xuất sắc' if pct >= 90 else 'Khá / Đạt chuẩn' if pct >= 80 else 'Trung bình' if pct >= 65 else 'Cần khắc phục gấp',
                'rank_tone': 'ok' if pct >= 80 else 'warn' if pct >= 65 else 'bad',
                'state': s.state, 'comment': s.comment or '',
                'can_edit': self.browse(s.id)._can_edit() and s.state == 'draft',
            })
        return {'stores': stores, 'rows': rows, 'can_create': self._audit_rights()['create']}

    @api.model
    def save_audit(self, data):
        """Lưu phiếu (Lưu nháp / Hoàn tất): data = {id, store_id, date, lines: [{crit_id, result, note}], remarks, plans}."""
        rights = self._audit_rights()
        sheet = self.sudo().browse(int(data.get('id') or 0)).exists()
        if sheet:
            if not self.browse(sheet.id)._can_edit():
                raise AccessError(_('Chỉ ASM lập phiếu mới được sửa phiếu Audit này.'))
        else:
            if not rights['create']:
                raise AccessError(_('Bạn không có quyền lập Phiếu Audit cửa hàng.'))
            store_id = int(data.get('store_id') or 0)
            if store_id not in self._audit_store_ids():
                raise AccessError(_('Bạn không có quyền lập phiếu Audit cho cửa hàng này.'))
            crits = self.env['store.asm.audit.crit'].sudo().search([])
            sheet = self.sudo().create({
                'store_id': store_id, 'audit_date': fields.Date.to_date(data.get('date')) or fields.Date.context_today(self),
                'user_id': self.env.user.id,
                'line_ids': [(0, 0, {'crit_id': c.id, 'sequence': c.sequence, 'name': c.name, 'standard': c.standard,
                                     'group_name': c.group_id.name or 'Khác', 'group_seq': c.group_id.sequence if c.group_id else 9999,
                                     'max_score': c.score}) for c in crits],
            })
        valid = {k for k, _l in RESULTS}
        if sheet.state == 'draft':
            by_crit = {l.crit_id.id: l for l in sheet.line_ids}
            by_id = {l.id: l for l in sheet.line_ids}
            for row in data.get('lines') or []:
                line = by_id.get(row.get('id') or 0) or by_crit.get(row.get('crit_id') or 0)
                if line:
                    res = row.get('result') or False
                    line.write({'result': res if res in valid else False, 'note': (row.get('note') or '').strip() or False})
            if 'comment' in data:
                sheet.write({'comment': (data.get('comment') or '').strip() or False})
        if 'remarks' in data:
            cats = {k for k, _l in REMARK_CATS}
            sheet.remark_ids.unlink()
            sheet.write({'remark_ids': [(0, 0, {'category': r.get('category') if r.get('category') in cats else 'ops',
                                                'text': (r.get('text') or '').strip()})
                                        for r in data['remarks'] if (r.get('text') or '').strip()]})
        if 'plans' in data:
            sheet.plan_ids.unlink()
            sheet.write({'plan_ids': [(0, 0, {'content': (p.get('content') or '').strip(), 'owner': (p.get('owner') or 'CHT').strip(),
                                              'deadline': fields.Date.to_date(p.get('deadline')) if p.get('deadline') else False,
                                              'state': p.get('state') if p.get('state') in ('in_progress', 'done') else 'in_progress'})
                                      for p in data['plans'] if (p.get('content') or '').strip()]})
        return self.browse(sheet.id)._payload()

    @api.model
    def submit_audit(self, audit_id):
        """Gửi CHT & cấp trên: mọi tiêu chí đã chấm; tiêu chí Cần cải thiện / Không đạt phải có ghi chú hoặc ảnh dẫn chứng."""
        sheet = self.sudo().browse(int(audit_id)).exists()
        if not sheet or not self.browse(sheet.id)._can_edit():
            raise AccessError(_('Chỉ ASM lập phiếu mới được gửi phiếu Audit này.'))
        todo = sheet.line_ids.filtered(lambda l: not l.result)
        if todo:
            raise UserError(_('Còn %s tiêu chí chưa chấm (vd. #%s %s).') % (len(todo), todo[0].sequence, todo[0].name))
        miss = sheet.line_ids.filtered(lambda l: l.result in ('improve', 'fail') and not (l.note or '').strip() and not l.photo_ids)
        if miss:
            raise UserError(_('Tiêu chí #%s (%s) chưa đạt nhưng thiếu ghi chú / ảnh dẫn chứng.') % (miss[0].sequence, miss[0].name))
        sheet.write({'state': 'submitted', 'submit_date': fields.Datetime.now()})
        # thông báo CHT của cửa hàng + cấp trên trực tiếp của ASM
        Emp = self.env['hr.employee'].sudo()
        store = sheet.store_id
        chts = Emp.search(['|', ('checklist_store_ids', 'in', store.id), ('store_id', '=', store.id), ('user_id', '!=', False)]) \
            if 'store_id' in Emp._fields else Emp.search([('checklist_store_ids', 'in', store.id), ('user_id', '!=', False)])
        chts = chts.filtered(lambda e: e._checklist_effective_level() == 2)
        boss = sheet.user_id.employee_id.parent_id.user_id
        to = (chts.mapped('user_id') | boss) - sheet.user_id
        if to:
            bot_send(self.env, to, card('KẾT QUẢ AUDIT CỬA HÀNG %s' % (store.code or store.name), [
                ('Cửa hàng', store.display_name), ('ASM kiểm tra', sheet.user_id.name), ('Ngày kiểm tra', sheet.audit_date.strftime('%d/%m/%Y')),
                ('Điểm Audit', '%s / %s (%s%%)' % (round(sheet.score, 1), round(sheet.max_score, 1), sheet.rate)),
                ('Tiêu chí lỗi', '%s Không đạt • %s Cần cải thiện' % (sheet.fail_count, sheet.improve_count)),
                ('Yêu cầu khắc phục', '%s việc' % len(sheet.plan_ids)),
            ], label='Mở Checklist Audit'))
        return self.browse(sheet.id)._payload()

    @api.model
    def upload_audit_photo(self, line_id, name, data):
        line = self.env['store.asm.audit.line'].sudo().browse(int(line_id)).exists()
        if not line or not self.browse(line.sheet_id.id)._can_edit():
            raise AccessError(_('Bạn không có quyền đính kèm ảnh cho phiếu Audit này.'))
        att = self.env['ir.attachment'].sudo().create({'name': name or 'anh.jpg', 'datas': data, 'res_model': line._name, 'res_id': line.id})
        line.write({'photo_ids': [(4, att.id)]})
        return [{'id': a.id, 'name': a.name} for a in line.photo_ids]

    @api.model
    def remove_audit_photo(self, line_id, attachment_id):
        line = self.env['store.asm.audit.line'].sudo().browse(int(line_id)).exists()
        if not line or not self.browse(line.sheet_id.id)._can_edit() or line.sheet_id.state != 'draft':
            raise AccessError(_('Bạn không có quyền xóa ảnh của phiếu Audit này.'))
        line.write({'photo_ids': [(3, int(attachment_id))]})
        return [{'id': a.id, 'name': a.name} for a in line.photo_ids]


class StoreAsmAuditLine(models.Model):
    _name = 'store.asm.audit.line'
    _description = 'Tiêu chí của phiếu Audit cửa hàng'
    _order = 'group_seq, sequence, id'

    sheet_id = fields.Many2one('store.asm.audit', ondelete='cascade', required=True, index=True)
    crit_id = fields.Many2one('store.asm.audit.crit', string='Tiêu chí (danh mục)', ondelete='set null')
    sequence = fields.Integer(string='STT')
    group_name = fields.Char(string='Nhóm')
    group_seq = fields.Integer(default=9999)
    name = fields.Char(string='Tiêu chí', required=True)
    standard = fields.Char(string='Tiêu chuẩn')
    max_score = fields.Float(string='Điểm chuẩn', default=2)
    result = fields.Selection(RESULTS, string='Kết quả')
    score = fields.Float(string='Điểm', compute='_compute_score', store=True)
    note = fields.Char(string='Dẫn chứng & ghi chú hiện trường')
    photo_ids = fields.Many2many('ir.attachment', 'store_asm_audit_line_photo_rel', 'line_id', 'attachment_id', string='Ảnh dẫn chứng')

    @api.depends('result', 'max_score')
    def _compute_score(self):
        for l in self:
            l.score = l.max_score if l.result == 'pass' else (l.max_score / 2.0 if l.result == 'improve' else 0.0)


class StoreAsmAuditRemark(models.Model):
    _name = 'store.asm.audit.remark'
    _description = 'Nhận xét và đề xuất của ASM (phiếu Audit)'
    _order = 'id'

    sheet_id = fields.Many2one('store.asm.audit', ondelete='cascade', required=True, index=True)
    category = fields.Selection(REMARK_CATS, string='Mục', default='ops')
    text = fields.Text(string='Nội dung')


class StoreAsmAuditPlan(models.Model):
    _name = 'store.asm.audit.plan'
    _description = 'Yêu cầu khắc phục sau Audit (Action Plan)'
    _order = 'id'

    sheet_id = fields.Many2one('store.asm.audit', ondelete='cascade', required=True, index=True)
    content = fields.Char(string='Nội dung yêu cầu khắc phục', required=True)
    owner = fields.Char(string='Người phụ trách', default='CHT')
    deadline = fields.Date(string='Hạn xử lý')
    state = fields.Selection(PLAN_STATES, string='Trạng thái', default='in_progress')
