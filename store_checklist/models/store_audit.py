import base64
import io
from datetime import datetime

from odoo import Command, api, fields, models
from odoo.tools import file_open
from odoo.exceptions import UserError, ValidationError

from .store_audit_template import AUDIT_TYPES, CATEGORIES


class StoreAudit(models.Model):
    _name = 'store.audit'
    _description = 'Phiếu Audit cửa hàng'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'audit_date desc, id desc'

    name = fields.Char(string='Mã phiếu', required=True, copy=False, readonly=True, default='New')

    # Danh mục cửa hàng của hồ sơ nhân viên (module hr_store)
    store_id = fields.Many2one('hr.store', string='Cửa hàng / Gian hàng', required=True, tracking=True)
    store_code = fields.Char(related='store_id.code', store=True)
    mien = fields.Selection(related='store_id.mien', string='Miền')
    address = fields.Char(related='store_id.street')
    province = fields.Char(related='store_id.city', store=True)
    manager = fields.Char(related='store_id.manager_id.name')

    template_id = fields.Many2one(
        'store.audit.template', string='Mẫu checklist', default=lambda self: self._default_template())
    # Theo mẫu checklist; mở từ mục NVBH / ASM / GS thì context store_audit_type chọn sẵn mẫu cùng loại
    audit_type = fields.Selection(related='template_id.audit_type', store=True, string='Loại checklist')
    audit_date = fields.Datetime(string='Ngày giờ audit', default=fields.Datetime.now, required=True)
    auditor_id = fields.Many2one('res.users', string='Người đánh giá', default=lambda self: self.env.user)
    period = fields.Char(string='Kỳ đánh giá')
    pass_threshold = fields.Float(string='Ngưỡng đạt (%)', default=80.0)

    line_ids = fields.One2many('store.audit.line', 'audit_id', string='Chi tiết tiêu chí', copy=True)
    # Cùng dữ liệu line_ids, tách theo nhóm để hiện ở từng tab của phiếu
    line_a_ids = fields.One2many('store.audit.line', 'audit_id', domain=[('category', '=', 'a')], default=lambda self: self._default_lines('a'), string='A. Cơ sở vật chất')
    line_b_ids = fields.One2many('store.audit.line', 'audit_id', domain=[('category', '=', 'b')], default=lambda self: self._default_lines('b'), string='B. Tác phong & kỹ năng')
    line_c_ids = fields.One2many('store.audit.line', 'audit_id', domain=[('category', '=', 'c')], default=lambda self: self._default_lines('c'), string='C. Chuyên môn')
    action_ids = fields.One2many('store.audit.action', 'audit_id', string='Khắc phục')
    action_count = fields.Integer(compute='_compute_action_count')

    score_a = fields.Float(string='Điểm A', compute='_compute_scores', store=True)
    max_a = fields.Float(string='Chuẩn A', compute='_compute_scores', store=True)
    score_b = fields.Float(string='Điểm B', compute='_compute_scores', store=True)
    max_b = fields.Float(string='Chuẩn B', compute='_compute_scores', store=True)
    score_c = fields.Float(string='Điểm C', compute='_compute_scores', store=True)
    max_c = fields.Float(string='Chuẩn C', compute='_compute_scores', store=True)
    total_score = fields.Float(string='Tổng điểm đạt', compute='_compute_scores', store=True)
    max_score = fields.Float(string='Tổng điểm chuẩn', compute='_compute_scores', store=True)
    # Tỷ lệ 0..1 để widget percentage hiển thị đúng
    pass_rate = fields.Float(string='Tỷ lệ đạt', compute='_compute_scores', store=True)
    conclusion = fields.Selection(
        [('pass', 'ĐẠT'), ('fail', 'KHÔNG ĐẠT')], string='Kết luận',
        compute='_compute_scores', store=True)
    summary = fields.Text(string='Đánh giá tổng thể')

    # Mức đánh giá từng mục A/B/C và tổng (theo bảng Cài đặt > Mức Đánh giá), tính realtime, không lưu
    lvl_a = fields.Char(compute='_compute_levels')
    lvl_b = fields.Char(compute='_compute_levels')
    lvl_c = fields.Char(compute='_compute_levels')
    lvl_t = fields.Char(compute='_compute_levels')
    tone_a = fields.Char(compute='_compute_levels')
    tone_b = fields.Char(compute='_compute_levels')
    tone_c = fields.Char(compute='_compute_levels')
    tone_t = fields.Char(compute='_compute_levels')
    conclusion_text = fields.Char(compute='_compute_levels')
    form_title = fields.Char(compute='_compute_form_title')

    # Thẻ số liệu trên đầu phiếu: tính realtime từ các dòng A/B/C của chính phiếu này, không lưu
    kpi_total = fields.Integer(compute='_compute_kpi')
    kpi_pass = fields.Integer(compute='_compute_kpi')
    kpi_pass_pct = fields.Float(compute='_compute_kpi')
    kpi_improve = fields.Integer(compute='_compute_kpi')
    kpi_improve_pct = fields.Float(compute='_compute_kpi')
    kpi_avg = fields.Float(compute='_compute_kpi')
    kpi_max = fields.Float(compute='_compute_kpi')
    kpi_score_pct = fields.Float(compute='_compute_kpi')

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('audited', 'Đã đánh giá'),
        ('done', 'Hoàn tất'),
    ], string='Trạng thái', default='draft', required=True, tracking=True)

    @api.model
    def _default_template(self):
        audit_type = self.env.context.get('store_audit_type')
        domain = [('audit_type', '=', audit_type)] if audit_type else []
        return self.env['store.audit.template'].search(domain, limit=1)

    @api.model
    def _default_lines(self, category):
        template = self._default_template()
        return self._template_line_commands(template, category)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        # đổi mẫu thì nạp lại tiêu chí theo điểm chuẩn của mẫu (chỉ khi phiếu còn nháp)
        if self.state == 'draft':
            self.line_a_ids = [Command.clear()] + self._template_line_commands(self.template_id, 'a')
            self.line_b_ids = [Command.clear()] + self._template_line_commands(self.template_id, 'b')
            self.line_c_ids = [Command.clear()] + self._template_line_commands(self.template_id, 'c')

    @api.model
    def get_dashboard_data(self, month=None, mien=None, store_id=None):
        """Số liệu Tổng quan: cửa hàng đã / chưa được audit trong tháng, theo miền, xu hướng 6 tháng."""
        today = fields.Date.context_today(self)
        year, mon = map(int, (month or today.strftime('%Y-%m')).split('-'))
        domain = []
        if mien:
            domain.append(('mien', 'not in', ['Nam', 'ĐTT', 'Bắc']) if mien == 'other' else ('mien', '=', mien))
        if store_id:
            domain.append(('id', '=', store_id))
        stores = self.env['hr.store'].search(domain)

        def audited(y, m):
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            audits = self.search([('store_id', 'in', stores.ids), ('audit_date', '>=', datetime(y, m, 1)),
                                  ('audit_date', '<', datetime(ny, nm, 1))])
            return set(audits.store_id.ids)

        def bucket(store):
            return store.mien if store.mien in ('Nam', 'ĐTT', 'Bắc') else 'other'

        done = audited(year, mon)
        labels = [('Nam', 'Miền Nam'), ('ĐTT', 'Miền ĐTT'), ('Bắc', 'Miền Bắc'), ('other', 'Khác')]
        by_mien = []
        for key, label in labels:
            group = stores.filtered(lambda st: bucket(st) == key)
            if group or key != 'other':
                n_done = len(group.filtered(lambda st: st.id in done))
                by_mien.append({'key': key, 'label': label, 'total': len(group), 'done': n_done,
                                'todo': len(group) - n_done})
        trend = []
        for back in range(5, -1, -1):
            idx = year * 12 + mon - 1 - back
            y, m = divmod(idx, 12)
            pct = round(100 * len(audited(y, m + 1)) / len(stores)) if stores else 0
            trend.append({'label': 'T%d/%d' % (m + 1, y), 'done': pct, 'todo': 100 - pct if stores else 0})
        todo = stores.filtered(lambda st: st.id not in done)
        last = {r[0].id: r[1] for r in self._read_group(
            [('store_id', 'in', todo.ids)], ['store_id'], ['audit_date:max'])}
        mien_label = dict(labels)
        todo_rows = [{
            'id': st.id, 'store': st.display_name, 'mien': mien_label[bucket(st)],
            'key': bucket(st), 'last': last[st.id].strftime('%d/%m/%Y') if last.get(st.id) else '',
        } for st in todo.sorted('name')]
        total = len(stores)
        return {
            'month': '%04d-%02d' % (year, mon),
            'total': total, 'done': len(done), 'todo': total - len(done),
            'rate': round(100 * len(done) / total) if total else 0,
            'by_mien': by_mien, 'trend': trend, 'todo_rows': todo_rows,
            'store_options': [{'id': st.id, 'name': st.display_name}
                              for st in self.env['hr.store'].search([], order='name')],
        }

    @api.model
    def get_shell_overview(self):
        """Số liệu cho Dashboard của shell Checklist Audit."""
        audits = self.search([])
        done = audits.filtered(lambda a: a.state != 'draft')
        states = dict(self._fields['state'].selection)
        types = dict(AUDIT_TYPES)
        return {
            'total': len(audits),
            'draft': len(audits) - len(done),
            'fail': len(done.filtered(lambda a: a.conclusion == 'fail')),
            'pass_rate': round(100 * sum(done.mapped('pass_rate')) / len(done), 1) if done else 0,
            'by_type': [{'label': label, 'count': len(audits.filtered(lambda a: a.audit_type == code))}
                        for code, label in AUDIT_TYPES],
            'recent': [{
                'id': a.id,
                'name': a.name,
                'store': a.store_id.display_name,
                'type': types.get(a.audit_type, ''),
                'date': a.audit_date.strftime('%d/%m/%Y') if a.audit_date else '',
                'rate': round(a.pass_rate * 100, 1),
                'state': states.get(a.state, ''),
                'conclusion': a.conclusion if a.state != 'draft' else False,
            } for a in audits[:8]],
        }

    @api.depends('line_ids.actual_score', 'line_ids.max_score', 'line_ids.category', 'pass_threshold',
                 'line_a_ids.actual_score', 'line_b_ids.actual_score', 'line_c_ids.actual_score')
    def _compute_scores(self):
        for rec in self:
            # dòng sửa ở form nằm trong line_a/b/c_ids nên đọc từ đó để tổng cập nhật ngay khi nhập
            for cat, _label in CATEGORIES:
                lines = rec[f'line_{cat}_ids']
                rec[f'score_{cat}'] = sum(lines.mapped('actual_score'))
                rec[f'max_{cat}'] = sum(lines.mapped('max_score'))
            rec.total_score = rec.score_a + rec.score_b + rec.score_c
            rec.max_score = rec.max_a + rec.max_b + rec.max_c
            rec.pass_rate = rec.total_score / rec.max_score if rec.max_score else 0.0
            rec.conclusion = 'pass' if rec.max_score and rec.pass_rate * 100 >= rec.pass_threshold else 'fail'

    @api.depends('line_a_ids.result', 'line_b_ids.result', 'line_c_ids.result',
                 'line_a_ids.actual_score', 'line_b_ids.actual_score', 'line_c_ids.actual_score')
    def _compute_kpi(self):
        for rec in self:
            lines = rec.line_a_ids | rec.line_b_ids | rec.line_c_ids
            scored = lines.filtered('is_scored')
            passed = len(scored.filtered(lambda l: l.result == 'pass'))
            improve = len(scored) - passed  # chưa đạt mức yêu cầu = Trung bình + Không đạt
            rec.kpi_total = len(lines)
            rec.kpi_pass = passed
            rec.kpi_pass_pct = 100 * passed / len(scored) if scored else 0.0
            rec.kpi_improve = improve
            rec.kpi_improve_pct = 100 * improve / len(scored) if scored else 0.0
            rec.kpi_avg = sum(lines.mapped('actual_score'))
            rec.kpi_max = sum(lines.mapped('max_score'))
            rec.kpi_score_pct = 100 * rec.kpi_avg / rec.kpi_max if rec.kpi_max else 0.0

    @api.depends('audit_type')
    def _compute_form_title(self):
        for rec in self:
            rec.form_title = 'CHECK LIST GIÁM SÁT' if rec.audit_type == 'gs' else 'PHIẾU ĐÁNH GIÁ CỬA HÀNG'

    @api.depends('score_a', 'max_a', 'score_b', 'max_b', 'score_c', 'max_c', 'total_score', 'max_score', 'audit_date')
    def _compute_levels(self):
        Level = self.env['store.audit.level']
        for rec in self:
            for key, score, top in (('a', rec.score_a, rec.max_a), ('b', rec.score_b, rec.max_b),
                                    ('c', rec.score_c, rec.max_c), ('t', rec.total_score, rec.max_score)):
                lv = Level.level_for(100 * score / top if top else 0, rec.audit_type)
                rec[f'lvl_{key}'] = lv.name or ''
                rec[f'tone_{key}'] = lv.tone or 'orange'
            when = rec.audit_date or fields.Datetime.now()
            rec.conclusion_text = 'Cửa hàng đạt mức %s trong tháng %d/%d' % (rec.lvl_t, when.month, when.year)

    def action_view_report(self):
        """Mở biên bản PDF ở tab mới (trình xem của trình duyệt)."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f'/report/pdf/store_checklist.report_store_audit/{self.id}'}

    def action_download_report(self):
        self.ensure_one()
        return self.env.ref('store_checklist.action_report_store_audit').report_action(self, config=False)

    @api.model
    def _report_image(self, name):
        """Ảnh của biên bản nhúng thẳng vào HTML (wkhtmltopdf không tải được ảnh ngoài khi tắt truy cập file)."""
        with file_open('store_checklist/static/src/img/' + name, 'rb') as f:
            return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

    def _report_overview(self):
        """Bảng "Tổng quan đánh giá" của biên bản: điểm từng mục kèm mức đánh giá."""
        self.ensure_one()
        rows = [
            ('store', 'Cơ sở vật chất', 'Không gian bên ngoài, bên trong và sắp xếp sản phẩm', self.score_a, self.max_a),
            ('people', 'Tác phong và kỹ năng', 'Tác phong, diện mạo và kỹ năng giao tiếp của nhân viên', self.score_b, self.max_b),
            ('trend', 'Chuyên môn nghiệp vụ', 'Tìm hiểu nhu cầu, tư vấn sản phẩm và khuyến mãi', self.score_c, self.max_c),
            ('box', 'Tổng điểm', 'Tổng điểm đánh giá của cả ba mục', self.total_score, self.max_score),
        ]
        out = []
        for icon, name, note, score, top in rows:
            pct = 100 * score / top if top else 0
            lv = self.env['store.audit.level'].level_for(pct, self.audit_type)
            level = (lv.name or '', lv.tone or 'orange')
            # dòng Tổng lấy đúng "Kết luận" của phiếu (cột Kết luận ở danh sách), các mục còn lại so với cùng ngưỡng đạt
            passed = self.conclusion == 'pass' if icon == 'box' else bool(top) and pct >= self.pass_threshold
            out.append({'icon': icon, 'name': name, 'note': note, 'score': score, 'max': top,
                        'level': level[0], 'tone': level[1], 'passed': passed})
        return out

    def _report_sections(self):
        """Các mục A/B/C của biên bản: mỗi mục gồm các phân nhóm kèm tổng điểm."""
        self.ensure_one()
        titles = {'a': 'A: ĐIỂM CƠ SỞ VẬT CHẤT', 'b': 'B: TÁC PHONG VÀ KỸ NĂNG CỦA NHÂN VIÊN',
                  'c': 'C: CHUYÊN MÔN NGHIỆP VỤ TƯ VẤN'}
        sections = []
        for cat, _label in CATEGORIES:
            lines = self.line_ids.filtered(lambda l: l.category == cat).sorted(lambda l: (l.sequence, l.id))
            groups = {}
            for line in lines:
                groups.setdefault(line.sub_category or '', []).append(line)
            sections.append({
                'title': titles.get(cat, cat),
                'groups': [{'name': name, 'lines': ls, 'max': sum(l.max_score for l in ls),
                            'score': sum(l.actual_score for l in ls)} for name, ls in groups.items()],
                'max': self[f'max_{cat}'], 'score': self[f'score_{cat}'],
            })
        return sections

    def _compute_action_count(self):
        for rec in self:
            rec.action_count = len(rec.action_ids)

    @staticmethod
    def _template_line_commands(template, category=None):
        return [Command.create({
            'sequence': t.sequence,
            'category': t.category,
            'sub_category': t.sub_group_id.name,
            'name': t.name,
            'requirement': t.requirement,
            'max_score': t.max_score,
        }) for t in template.line_ids if not category or t.category == category]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self._next_name(vals.get('store_id'), vals.get('audit_date'))
        audits = super().create(vals_list)
        # sau super() để áp dụng cả template_id mặc định
        for audit in audits.filtered(lambda a: a.template_id and not a.line_ids):
            audit.line_ids = self._template_line_commands(audit.template_id)
        audits._auto_state()
        return audits

    def write(self, vals):
        res = super().write(vals)
        if 'state' not in vals:  # "Về nháp" chủ động thì giữ nguyên
            self._auto_state()
        return res

    @api.model
    def export_list_xlsx(self, domain, title='DANH SÁCH PHIẾU ĐÁNH GIÁ'):
        """Kết xuất danh sách phiếu (đúng bộ lọc đang xem) ra file Excel; trả về {name, data base64}."""
        import xlsxwriter
        audits = self.search(domain, order='store_id, audit_date desc, id desc')
        states = dict(self._fields['state'].selection)
        miens = dict(self.env['hr.store']._fields['mien'].selection)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Danh sach')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1D55BD', 'align': 'center',
                                'valign': 'vcenter', 'border': 1, 'text_wrap': True})
        cell = book.add_format({'border': 1, 'valign': 'vcenter'})
        num = book.add_format({'border': 1, 'num_format': '0.##', 'align': 'center'})
        pct = book.add_format({'border': 1, 'num_format': '0.00', 'align': 'center'})
        ctr = book.add_format({'border': 1, 'align': 'center'})
        bad = book.add_format({'border': 1, 'align': 'center', 'bold': True, 'font_color': '#DC2626'})
        good = book.add_format({'border': 1, 'align': 'center', 'bold': True, 'font_color': '#15803D'})
        big = book.add_format({'bold': True, 'font_size': 16, 'font_color': '#12285F'})
        cols = ['STT', 'Mã phiếu', 'Cửa hàng', 'Miền', 'Ngày giờ audit', 'Người đánh giá', 'Điểm đánh giá',
                'Điểm chuẩn', 'Tỷ lệ đạt (%)', 'Kết luận', 'Trạng thái']
        widths = [6, 28, 16, 12, 20, 22, 14, 12, 14, 14, 16]
        sheet.merge_range(0, 0, 0, len(cols) - 1, title, big)
        sheet.set_row(2, 30)
        for i, (name, width) in enumerate(zip(cols, widths)):
            sheet.write(2, i, name, head)
            sheet.set_column(i, i, width)
        for n, a in enumerate(audits, 1):
            r = 2 + n
            when = fields.Datetime.context_timestamp(self, a.audit_date)
            sheet.write(r, 0, n, ctr)
            sheet.write(r, 1, a.name, cell)
            sheet.write(r, 2, a.store_id.display_name or '', cell)
            sheet.write(r, 3, miens.get(a.mien, ''), cell)
            sheet.write(r, 4, when.strftime('%d/%m/%Y %H:%M'), ctr)
            sheet.write(r, 5, a.auditor_id.name or '', cell)
            sheet.write(r, 6, a.total_score, num)
            sheet.write(r, 7, a.max_score, num)
            sheet.write(r, 8, a.pass_rate * 100, pct)
            sheet.write(r, 9, 'ĐẠT' if a.conclusion == 'pass' else 'KHÔNG ĐẠT', good if a.conclusion == 'pass' else bad)
            sheet.write(r, 10, states.get(a.state, ''), ctr)
        sheet.freeze_panes(3, 0)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Danh_sach_check_list_%s.xlsx' % stamp, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def _next_name(self, store_id, audit_date=None):
        """Mã phiếu dạng LUG_KDV/07112026_1: cửa hàng / ngày audit (giờ người dùng) _ số biên bản thứ mấy trong ngày."""
        when = fields.Datetime.to_datetime(audit_date) if audit_date else fields.Datetime.now()
        store = self.env['hr.store'].browse(store_id)
        prefix = '%s/%s' % (store.code or store.display_name or 'PHIEU',
                            fields.Datetime.context_timestamp(self, when).strftime('%d%m%Y'))
        n = self.with_context(active_test=False).search_count([('name', '=like', prefix + '\\_%')]) + 1
        while self.with_context(active_test=False).search_count([('name', '=', '%s_%d' % (prefix, n))]):
            n += 1
        return '%s_%d' % (prefix, n)

    def _auto_state(self):
        """Popup chỉ có nút Lưu: phiếu đã chấm ít nhất một tiêu chí thì coi là Đã đánh giá, chưa chấm gì thì còn Nháp."""
        for rec in self.filtered(lambda r: r.state == 'draft' and any(r.line_ids.mapped('is_scored'))):
            rec.state = 'audited'

    def action_load_template(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Chỉ nạp lại tiêu chí khi phiếu đang ở trạng thái Nháp.')
            if not rec.template_id:
                raise UserError('Vui lòng chọn Mẫu checklist.')
            rec.line_ids = [Command.clear()] + self._template_line_commands(rec.template_id)

    def action_audit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError('Phiếu chưa có tiêu chí nào.')
            todo = rec.line_ids.filtered(lambda l: not l.is_scored)
            if todo:
                raise UserError('Còn %d tiêu chí chưa chấm:\n- %s' % (
                    len(todo), '\n- '.join(todo.mapped('name'))))
        self.state = 'audited'

    def action_done(self):
        self.state = 'done'

    def action_draft(self):
        self.state = 'draft'

    def action_create_actions(self):
        """Tạo phiếu khắc phục cho mọi tiêu chí không đạt / đạt một phần chưa có khắc phục."""
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.result in ('fail', 'partial') and l not in self.action_ids.line_id)
        self.env['store.audit.action'].create([{
            'audit_id': self.id,
            'line_id': line.id,
            'date_found': fields.Date.to_date(self.audit_date),
            'issue': line.note or line.name,
        } for line in lines])
        return self.action_view_actions()

    def action_view_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Khắc phục',
            'res_model': 'store.audit.action',
            'view_mode': 'list,form',
            'domain': [('audit_id', '=', self.id)],
            'context': {'default_audit_id': self.id},
        }


class StoreAuditLine(models.Model):
    _name = 'store.audit.line'
    _description = 'Chi tiết tiêu chí audit'
    _order = 'sequence, id'

    audit_id = fields.Many2one('store.audit', string='Phiếu audit', required=True, ondelete='cascade', index=True)
    store_id = fields.Many2one(related='audit_id.store_id', store=True)
    audit_date = fields.Datetime(related='audit_id.audit_date', store=True)
    sequence = fields.Integer(string='STT', default=10)
    category = fields.Selection(CATEGORIES, string='Nhóm tiêu chí', required=True)
    sub_category = fields.Char(string='Phân nhóm')
    name = fields.Char(string='Tiêu chí đánh giá', required=True)
    requirement = fields.Text(string='Yêu cầu / Tiêu chuẩn')
    max_score = fields.Float(string='Điểm chuẩn', default=2.0)
    actual_score = fields.Float(string='Điểm đánh giá')
    # Float không phân biệt "trống" với 0, nên cần cờ riêng cho trạng thái "Chưa chấm"
    is_scored = fields.Boolean(string='Đã chấm')
    result = fields.Selection([
        ('todo', 'Chưa chấm'),
        ('pass', 'Đạt'),
        ('partial', 'Trung bình'),
        ('fail', 'Không đạt'),
    ], string='Kết quả', compute='_compute_result', store=True)
    note = fields.Text(string='Chi tiết lỗi / Nhận xét thực tế')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'store_audit_line_attachment_rel', 'line_id', 'attachment_id',
        string='Bằng chứng')

    @api.depends('actual_score', 'max_score', 'is_scored')
    def _compute_result(self):
        for line in self:
            if not line.is_scored:
                line.result = 'todo'
            elif line.actual_score >= line.max_score:
                line.result = 'pass'
            elif line.actual_score == 0:
                line.result = 'fail'
            else:
                line.result = 'partial'

    @api.onchange('actual_score')
    def _onchange_actual_score(self):
        self.is_scored = True
        if self.actual_score < 0 or self.actual_score > self.max_score:
            bad = self.actual_score
            self.actual_score = self.max_score if bad > 0 else 0.0
            return {'warning': {
                'title': 'Điểm không hợp lệ',
                'message': 'Điểm đánh giá "%s" phải từ 0 đến điểm chuẩn (%s). Đã đặt lại điểm.' % (bad, self.max_score),
            }}

    @api.constrains('actual_score', 'max_score')
    def _check_score(self):
        for line in self:
            if line.actual_score < 0 or line.actual_score > line.max_score:
                raise ValidationError(
                    'Tiêu chí "%s": điểm đánh giá phải từ 0 đến %s.' % (line.name, line.max_score))
