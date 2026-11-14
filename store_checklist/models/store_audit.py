import base64
import io
from datetime import datetime

from odoo import Command, api, fields, models
from odoo.tools import file_open
from odoo.tools.image import image_process
from odoo.exceptions import AccessError, UserError, ValidationError

from .store_audit_template import AUDIT_TYPES, CATEGORIES


class StoreAudit(models.Model):
    _name = 'store.audit'
    _description = 'Phiếu Audit cửa hàng'
    _inherit = ['store.perm.mixin', 'mail.thread', 'mail.activity.mixin']
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
    error_count = fields.Integer(string='Tổng số lỗi', compute='_compute_error_total', store=True)

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
    can_edit_done = fields.Boolean(compute='_compute_can_edit_done')
    form_title = fields.Char(compute='_compute_form_title')

    # Thẻ số liệu trên đầu phiếu: tính realtime từ các dòng A/B/C của chính phiếu này, không lưu
    kpi_total = fields.Integer(compute='_compute_kpi')
    kpi_pass = fields.Integer(compute='_compute_kpi')
    kpi_pass_pct = fields.Float(compute='_compute_kpi')
    kpi_improve = fields.Integer(compute='_compute_kpi')
    kpi_improve_pct = fields.Float(compute='_compute_kpi')
    kpi_fail = fields.Integer(compute='_compute_kpi')
    kpi_fail_pct = fields.Float(compute='_compute_kpi')
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
            improve = len(scored.filtered(lambda l: l.result == 'partial'))  # Trung bình
            failed = len(scored.filtered(lambda l: l.result == 'fail'))  # Không đạt
            rec.kpi_total = len(lines)
            rec.kpi_pass = passed
            rec.kpi_pass_pct = 100 * passed / len(scored) if scored else 0.0
            rec.kpi_improve = improve
            rec.kpi_improve_pct = 100 * improve / len(scored) if scored else 0.0
            rec.kpi_fail = failed
            rec.kpi_fail_pct = 100 * failed / len(scored) if scored else 0.0
            rec.kpi_avg = sum(lines.mapped('actual_score'))
            rec.kpi_max = sum(lines.mapped('max_score'))
            rec.kpi_score_pct = 100 * rec.kpi_avg / rec.kpi_max if rec.kpi_max else 0.0

    @api.depends('line_ids.error_count', 'line_a_ids.error_count', 'line_b_ids.error_count', 'line_c_ids.error_count')
    def _compute_error_total(self):
        for rec in self:
            rec.error_count = sum((rec.line_a_ids | rec.line_b_ids | rec.line_c_ids).mapped('error_count'))

    @api.depends_context('uid')
    def _compute_can_edit_done(self):
        # Quản lý (gồm Administrator) được sửa phiếu đã Hoàn tất; người dùng thường thì phiếu Hoàn tất bị khóa
        can = self.env.user.has_group('store_checklist.group_store_manager')
        for rec in self:
            rec.can_edit_done = can

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

    def action_edit_popup(self):
        """Mở phiếu ở popup để chỉnh sửa (nút bút chì trong danh sách, dành cho Quản lý)."""
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'views': [(False, 'form')],
                'target': 'new', 'context': {**self.env.context, 'dialog_size': 'extra-large'}}

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

    # --- Ma trận quyền theo mục con (store.perm.mixin) ---
    def _perm_key(self):
        return self.audit_type if self.audit_type in ('nvbh', 'asm', 'gs') else 'review'

    @api.model
    def _perm_key_vals(self, vals):
        tpl = self.env['store.audit.template'].sudo().browse(vals.get('template_id') or 0)
        return tpl.audit_type if tpl.audit_type in ('nvbh', 'asm', 'gs') else 'review'

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
    def is_gs_supervisor(self):
        """Chức danh có chữ "Giám sát": chỉ thấy phiếu do mình đánh giá (cùng điều kiện với quy tắc truy cập)."""
        return 'giám sát' in (self.env.user.employee_id.job_title or '').strip().lower()

    @api.model
    def get_report_gs(self, domain, prev_domain=False):
        """Dashboard quản trị & hoạt động giám sát: KPI, phân loại, năng suất từng giám sát (theo domain đang lọc)."""
        audits = self.search(domain, order='audit_date desc, id desc')
        done = audits.filtered(lambda r: r.state != 'draft')

        def avg(recs):
            return round(100 * sum(recs.mapped('pass_rate')) / len(recs), 1) if recs else 0.0

        chain_avg = avg(done)
        levels = self.env['store.audit.level'].search([('audit_type', '=', 'gs')], order='min_score desc')
        prev_done = self.search(prev_domain).filtered(lambda r: r.state != 'draft') if prev_domain else self.browse()

        def row_of(a):
            return {
                'id': a.id, 'store': a.store_id.display_name or '', 'auditor': a.auditor_id.name or '',
                'date': fields.Datetime.context_timestamp(self, a.audit_date).strftime('%d/%m/%Y %H:%M:%S'),
                'score': round(100 * a.pass_rate, 1), 'level': a.lvl_t or '',
            }

        rows = []
        for user in audits.mapped('auditor_id').sorted('name'):
            mine = audits.filtered(lambda r: r.auditor_id == user)
            mine_done = mine.filtered(lambda r: r.state != 'draft')
            mine_avg = avg(mine_done)
            draft = len(mine) - len(mine_done)
            if draft:
                status, tone = 'Còn phiếu nháp', 'orange'
            elif not mine_done:
                status, tone = 'Chưa có phiếu', 'gray'
            elif mine_avg - chain_avg > 5:
                status, tone = 'Chấm nới tay', 'yellow'
            elif chain_avg - mine_avg > 5:
                status, tone = 'Chấm chặt tay', 'red'
            else:
                status, tone = 'Chấm sát thực tế', 'green'
            rows.append({
                'id': user.id, 'name': user.name or 'Chưa rõ',
                'plan': len(mine), 'audited': len(mine), 'done': len(mine_done), 'draft': draft,
                'avg': mine_avg,
                'by_level': [len(mine_done.filtered(lambda r: r.lvl_t == lv.name)) for lv in levels],
                'status': status, 'tone': tone,
                'audits': [row_of(r) for r in mine_done],
            })
        auditors = self.sudo().search([('audit_type', '=', 'gs')]).mapped('auditor_id').sorted('name')
        return {
            'total': len(audits), 'done': len(done), 'draft': len(audits) - len(done),
            'done_rate': round(100 * len(done) / len(audits), 1) if audits else 0.0,
            'avg': chain_avg, 'prev_avg': avg(prev_done) if prev_domain and prev_done else None,
            'levels': [{'name': lv.name, 'range': lv.score_range, 'tone': lv.tone,
                        'count': len(done.filtered(lambda r: r.lvl_t == lv.name))} for lv in levels],
            'rows': rows,
            'stores': [row_of(r) for r in done],
            'auditor_options': [{'id': u.id, 'name': u.name} for u in auditors],
        }

    @api.model
    def _rank_rows(self, domain):
        """Mỗi cửa hàng một dòng: lần audit đã chốt gần nhất trong kỳ, xếp theo tỷ lệ đạt giảm dần."""
        latest = {}
        for a in self.search(domain, order='audit_date desc, id desc').filtered(lambda r: r.state != 'draft'):
            latest.setdefault(a.store_id, a)
        return [{'id': a.id, 'store': a.store_id.display_name or '', 'max': a.max_score, 'score': a.total_score,
                 'rate': round(100 * a.pass_rate, 2), 'level': a.lvl_t or '', 'tone': a.tone_t or 'orange',
                 # mỗi dòng chữ trong "Chi tiết lỗi" của tiêu chí là một lỗi: "Tiêu chí: lỗi"
                 'errors': ['%s: %s' % (l.name, ln.strip()) for l in a.line_ids.sorted('sequence')
                            for ln in (l.note or '').splitlines() if ln.strip()]}
                for a in sorted(latest.values(), key=lambda a: -a.pass_rate)]

    @api.model
    def get_report_rank(self, domain):
        """Báo cáo xếp loại: STT, Cửa hàng, Điểm chuẩn, Điểm đánh giá, Tỷ lệ đạt, Xếp loại (theo bảng Xếp loại trong Cài đặt)."""
        return self._rank_rows(domain)

    @api.model
    def export_rank_xlsx(self, domain):
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        rows = self._rank_rows(domain)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Bao cao xep loai')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1D55BD', 'align': 'center',
                                'valign': 'vcenter', 'border': 1})
        cell = book.add_format({'border': 1, 'valign': 'vcenter'})
        ctr = book.add_format({'border': 1, 'align': 'center'})
        num = book.add_format({'border': 1, 'num_format': '0.##', 'align': 'center'})
        pct = book.add_format({'border': 1, 'num_format': '0.00', 'align': 'center'})
        wrap = book.add_format({'border': 1, 'valign': 'vcenter', 'text_wrap': True})
        sheet.merge_range(0, 0, 0, 6, 'BÁO CÁO XẾP LOẠI', book.add_format({'bold': True, 'font_size': 16, 'font_color': '#12285F'}))
        for i, (name, width) in enumerate(zip(['STT', 'Cửa hàng', 'Điểm chuẩn', 'Điểm đánh giá', 'Tỷ lệ đạt (%)', 'Chi tiết lỗi', 'Xếp loại'],
                                              [6, 24, 14, 16, 14, 16, 18])):
            sheet.write(2, i, name, head)
            sheet.set_column(i, i, width)
        for n, r in enumerate(rows, 1):
            sheet.write(2 + n, 0, n, ctr)
            sheet.write(2 + n, 1, r['store'], cell)
            sheet.write(2 + n, 2, r['max'], num)
            sheet.write(2 + n, 3, r['score'], num)
            sheet.write(2 + n, 4, r['rate'], pct)
            sheet.write(2 + n, 5, len(r['errors']), num)
            sheet.write(2 + n, 6, r['level'], ctr)
        sheet.freeze_panes(3, 0)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Bao_cao_xep_loai_%s.xlsx' % stamp, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def get_report_store(self, domain):
        """Báo cáo xếp loại cửa hàng: mỗi cửa hàng lấy lần audit gần nhất (đã chốt) trong kỳ, xếp theo bảng Mức đánh giá GS."""
        latest = {}
        for a in self.search(domain, order='audit_date desc, id desc').filtered(lambda r: r.state != 'draft'):
            latest.setdefault(a.store_id, a)
        miens = dict(self.env['hr.store']._fields['mien'].selection)
        levels = self.env['store.audit.level'].search([('audit_type', '=', 'gs')], order='min_score desc')

        def short(m):
            return (miens.get(m) or 'Khác').replace('Miền ', 'M.')

        out = []
        for lv in levels:
            sel = sorted((a for a in latest.values() if a.lvl_t == lv.name), key=lambda a: -a.pass_rate)
            out.append({'name': lv.name, 'tone': lv.tone, 'range': lv.score_range, 'count': len(sel),
                        'stores': [{'id': a.id, 'store': a.store_id.display_name or '', 'mien': short(a.mien),
                                    'score': round(100 * a.pass_rate)} for a in sel]})
        order = [k for k in ('Bắc', 'ĐTT', 'Nam') if k in miens] + [False]
        by_mien = []
        for key in order:
            group = [a for a in latest.values() if (a.mien if a.mien in miens else False) == key]
            if group:
                by_mien.append({'label': (miens.get(key) or 'Khác'),
                                'counts': [len([a for a in group if a.lvl_t == lv.name]) for lv in levels]})
        return {'total': len(latest), 'levels': out, 'by_mien': by_mien}

    @api.model
    def _manager_rows(self, domain):
        """Mỗi quản lý: các lần audit chốt gần nhất của từng (cửa hàng, loại GS/ASM) trong kỳ."""
        latest = {}
        for a in self.sudo().search(domain, order='audit_date desc, id desc').filtered(lambda r: r.state != 'draft'):
            if a.audit_type in ('gs', 'asm'):
                latest.setdefault((a.store_id.id, a.audit_type), a)
        miens = dict(self.env['hr.store']._fields['mien'].selection)
        managers = {}
        for (store_id, kind), a in latest.items():
            mgr = a.store_id.manager_id
            m = managers.setdefault(mgr.id, {'id': mgr.id, 'name': mgr.name or 'Chưa gán quản lý', 'stores': {},
                                             'audits': [], 'miens': set(), 'mc': {}})
            m['audits'].append(a)
            m['miens'].add(miens.get(a.mien) or 'Khác')
            key = a.mien if a.mien in miens else 'other'
            m['mc'][key] = m['mc'].get(key, 0) + 1
            s = m['stores'].setdefault(store_id, {'store': a.store_id.display_name or '', 'code': a.store_id.code or '',
                                                  'gs': None, 'asm': None, 'rates': [], 'errors': 0, 'ok': True, 'audit': False})
            if kind == 'gs' or not s['audit']:
                s['audit'] = a.id
            s[kind] = round(100 * a.pass_rate, 1)
            s['rates'].append(100 * a.pass_rate)
            s['errors'] += a.error_count
            s['ok'] = s['ok'] and a.conclusion == 'pass'
        return managers

    @api.model
    def _store_level(self, rates):
        lv = self.env['store.audit.level'].level_for(sum(rates) / len(rates), 'gs')
        return {'level': lv.name or '', 'tone': lv.tone or 'orange'}

    @api.model
    def get_report_manager(self, domain, prev_domain=False):
        """Báo cáo theo quản lý: điểm TB (%) các cửa hàng phụ trách, so tháng trước, tỷ lệ đạt chuẩn, tách GS / ASM."""
        def avg(rs):
            return round(sum(100 * a.pass_rate for a in rs) / len(rs), 1) if rs else None

        prev = self._manager_rows(prev_domain) if prev_domain else {}
        rows = []
        for m in self._manager_rows(domain).values():
            au = m['audits']
            gs, asm = [a for a in au if a.audit_type == 'gs'], [a for a in au if a.audit_type == 'asm']
            score, before = avg(au), prev.get(m['id'])
            lv = self.env['store.audit.level'].level_for(score, 'gs')
            pa = before['audits'] if before else []
            before = avg(pa)
            rows.append({'id': m['id'], 'name': m['name'], 'area': ', '.join(sorted(m['miens'])),
                         'store_count': len(m['stores']), 'avg': score, 'gs_avg': avg(gs), 'asm_avg': avg(asm),
                         'delta': round(score - before, 1) if before is not None else None,
                         'mien': max(m['mc'], key=m['mc'].get), 'level': lv.name or '', 'tone': lv.tone or 'orange',
                         'audits': len(au), 'passed': len([a for a in au if a.conclusion == 'pass']),
                         'errors': sum(a.error_count for a in au),
                         'p_errors': sum(a.error_count for a in pa) if pa else None,
                         'stores': [{'store': s['store'], 'code': s['code'], 'gs': s['gs'], 'asm': s['asm'],
                                     'score': round(sum(s['rates']) / len(s['rates']), 1), 'errors': s['errors'], 'ok': s['ok'],
                                     'audit': s['audit'], **self._store_level(s['rates'])}
                                    for s in sorted(m['stores'].values(), key=lambda x: x['store'])]})
        rows.sort(key=lambda r: -r['avg'])
        return rows

    @api.model
    def get_flow_stats(self, domain):
        """Sơ đồ quy trình vận hành: số liệu 3 phân hệ (chấm điểm GS, xử lý sai phạm kiểu Kanban, báo cáo KPI)."""
        tmpl = self.env['store.audit.template'].sudo().search([('audit_type', '=', 'gs')], order='id desc')
        tmpl = tmpl.filtered('line_ids')[:1]
        audits = self.sudo().search(domain).filtered(lambda a: a.state != 'draft')
        acts = self.env['store.audit.action'].sudo().search(
            [('audit_id', 'in', audits.ids), ('line_id.error_count', '>', 0)], order='deadline, id')
        today = fields.Date.context_today(self)

        def card(a):
            return {'id': a.id, 'store': a.store_id.code or a.store_id.display_name or '', 'issue': a.line_id.name or a.issue or '',
                    'late': bool(a.deadline and a.deadline < today and not a.control_done)}

        green = acts.filtered('control_done')
        red = acts - green
        return {
            'criteria': len(tmpl.line_ids), 'max_score': round(sum(tmpl.line_ids.mapped('max_score')), 1),
            'audits': len(audits), 'stores': len(audits.mapped('store_id')),
            'red': len(red), 'late': len([a for a in red if card(a)['late']]), 'green': len(green),
            'red_cards': [card(a) for a in red[:3]], 'green_cards': [card(a) for a in green[:3]],
        }

    @api.model
    def export_manager_xlsx(self, domain, manager_id=None):
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        rows = self.get_report_manager(domain)
        if manager_id is not None:
            return self._manager_detail_xlsx([r for r in rows if r['id'] == manager_id])
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Bao cao theo quan ly')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#6D4AFF', 'align': 'center', 'valign': 'vcenter', 'border': 1})
        cell = book.add_format({'border': 1, 'valign': 'vcenter'})
        ctr = book.add_format({'border': 1, 'align': 'center', 'num_format': '0.##'})
        sheet.merge_range(0, 0, 0, 8, 'BÁO CÁO THEO QUẢN LÝ', book.add_format({'bold': True, 'font_size': 16, 'font_color': '#12285F'}))
        heads = ['Hạng', 'Người quản lý', 'Khu vực', 'Số cửa hàng', 'Tổng số lỗi', 'Điểm đánh giá TB (%)', 'Điểm GS (%)', 'Điểm ASM (%)', 'Xếp loại']
        for i, (h, w) in enumerate(zip(heads, [7, 28, 18, 13, 13, 13, 13, 13, 14])):
            sheet.write(2, i, h, head)
            sheet.set_column(i, i, w)
        for n, r in enumerate(rows, 1):
            vals = [n, r['name'], r['area'], r['store_count'], r['errors'], r['avg'], r['gs_avg'], r['asm_avg'],
                    r['level']]
            for c, v in enumerate(vals):
                sheet.write(2 + n, c, '' if v is None else v, cell if c in (1, 2) else ctr)
        sheet.freeze_panes(3, 0)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Bao_cao_theo_quan_ly_%s.xlsx' % stamp, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def _manager_detail_xlsx(self, rows):
        import xlsxwriter
        r = rows[0] if rows else {'name': '', 'area': '', 'store_count': 0, 'errors': 0, 'avg': 0, 'audits': 0, 'passed': 0, 'stores': []}
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Chi tiet quan ly')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#6D4AFF', 'align': 'center', 'valign': 'vcenter', 'border': 1})
        cell = book.add_format({'border': 1, 'valign': 'vcenter'})
        ctr = book.add_format({'border': 1, 'align': 'center', 'num_format': '0.##'})
        bold = book.add_format({'bold': True})
        sheet.merge_range(0, 0, 0, 7, 'CHI TIẾT QUẢN LÝ: %s' % r['name'], book.add_format({'bold': True, 'font_size': 16, 'font_color': '#12285F'}))
        pct = round(100 * r['passed'] / r['audits']) if r['audits'] else 0
        sheet.write(1, 0, 'Khu vực: %s   |   Số cửa hàng: %s   |   Tổng số lỗi: %s   |   Điểm TB: %s   |   Đạt chuẩn: %s%%'
                    % (r['area'], r['store_count'], r['errors'], r['avg'], pct), bold)
        heads = ['STT', 'Mã cửa hàng', 'Tên cửa hàng', 'Điểm GS', 'Điểm ASM', 'Điểm đánh giá', 'Số lỗi', 'Xếp loại']
        for i, (h, w) in enumerate(zip(heads, [6, 16, 28, 12, 12, 14, 10, 14])):
            sheet.write(3, i, h, head)
            sheet.set_column(i, i, w)
        for n, s in enumerate(r['stores'], 1):
            vals = [n, s['code'], s['store'], s['gs'], s['asm'], s['score'], s['errors'], s['level']]
            for c, v in enumerate(vals):
                sheet.write(3 + n, c, '' if v is None else v, cell if c in (1, 2) else ctr)
        book.close()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d%m%Y_%H%M')
        return {'name': 'Chi_tiet_quan_ly_%s.xlsx' % stamp, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def get_report_personal(self, month=None):
        """Báo cáo hoạt động giám sát cá nhân (người dùng thường): chỉ phiếu GS của chính người dùng trong tháng."""
        today = fields.Date.context_today(self)
        year, mon = map(int, (month or today.strftime('%Y-%m')).split('-'))
        end_y, end_m = (year + 1, 1) if mon == 12 else (year, mon + 1)
        base = [('audit_type', '=', 'gs'), ('audit_date', '>=', datetime(year, mon, 1)),
                ('audit_date', '<', datetime(end_y, end_m, 1))]
        mine = self.search(base + [('auditor_id', '=', self.env.uid)], order='audit_date desc, id desc')
        done = mine.filtered(lambda r: r.state != 'draft')
        # trung bình chuỗi: toàn bộ phiếu GS đã chốt trong tháng của mọi giám sát (quy tắc truy cập chỉ cho thấy phiếu của mình)
        chain = self.sudo().search(base + [('state', '!=', 'draft')])

        def avg(recs):
            return round(100 * sum(recs.mapped('pass_rate')) / len(recs), 1) if recs else 0.0

        states = dict(self._fields['state'].selection)
        miens = dict(self.env['hr.store']._fields['mien'].selection)
        rows = []
        for r in mine:
            due = min(r.action_ids.filtered(lambda a: a.state != 'done' and a.deadline).mapped('deadline'), default=False)
            rows.append({
                'id': r.id, 'name': r.name, 'store': r.store_id.display_name or '',
                'date': fields.Datetime.context_timestamp(self, r.audit_date).strftime('%d/%m/%Y %H:%M:%S'),
                'score': r.total_score, 'max': r.max_score, 'rate': round(100 * r.pass_rate, 2),
                'level': r.lvl_t or '', 'tone': r.tone_t or 'orange', 'draft': r.state == 'draft', 'passed': r.conclusion == 'pass',
                'state': 'Nháp (Cần bổ sung)' if r.state == 'draft' else states.get(r.state, ''),
                'state_key': r.state,
                'capa': 'Không có' if not due else ('Trong ngày' if due == today else due.strftime('%d/%m/%Y')),
            })
        levels = []
        for lv in self.env['store.audit.level'].search([('audit_type', '=', 'gs')], order='min_score desc'):
            sel = [x for x in rows if not x['draft'] and x['level'] == lv.name]
            if sel:
                levels.append({'name': lv.name, 'tone': lv.tone, 'count': len(sel), 'rows': sel})
        weeks = [0, 0, 0, 0]  # tuần 4 gồm cả các ngày cuối tháng
        for r in mine:
            day = fields.Datetime.context_timestamp(self, r.audit_date).day
            weeks[min((day - 1) // 7, 3)] += 1
        return {
            'month': '%04d-%02d' % (year, mon), 'name': self.env.user.name,
            'mien': ', '.join(sorted({miens.get(m, '') for m in mine.mapped('store_id.mien') if m})),
            'plan': len(mine), 'done': len(done), 'draft': len(mine) - len(done),
            'rate': round(100 * len(done) / len(mine)) if mine else 0,
            'avg': avg(done), 'chain_avg': avg(chain),
            'levels': levels, 'weeks': weeks, 'rows': rows,
        }

    @api.model
    def export_list_xlsx(self, domain, title='DANH SÁCH PHIẾU ĐÁNH GIÁ'):
        """Kết xuất danh sách phiếu (đúng bộ lọc đang xem) ra file Excel; trả về {name, data base64}."""
        self.env['store.perm.rule'].check_export()
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
            sheet.write(r, 9, a.lvl_t or '', ctr)
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
        """Tạo phiếu khắc phục cho mọi tiêu chí có lỗi giám sát ghi nhận (cùng số liệu "Tổng số lỗi") chưa có khắc phục."""
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.error_count > 0 and l not in self.action_ids.line_id)
        self.env['store.audit.action'].create([{
            'audit_id': self.id,
            'line_id': line.id,
            'date_found': fields.Date.to_date(self.audit_date),
            'issue': line.note or line.name,
        } for line in lines])
        self._sync_action_owners()
        return self.action_view_actions()

    def _sync_action_owners(self):
        """Một chiều: "Người phụ trách" + nhân viên thuộc "Group (LUG Permission)" của tiêu chí mẫu cùng tên
        -> cột "Người phụ trách" của biên bản xử lý sai phạm (cập nhật mỗi lần mở)."""
        self.ensure_one()
        owners, ctrls = {}, {}
        for t in self.template_id.line_ids:
            ctrls[(t.name or '').strip().casefold()] = t.controller_ids.ids
            emps = t.responsible_ids | t.lug_group_ids.user_ids.employee_ids
            owners[(t.name or '').strip().casefold()] = emps.ids
        for act in self.action_ids:
            ids = owners.get((act.line_id.name or '').strip().casefold(), [])
            cids = ctrls.get((act.line_id.name or '').strip().casefold(), [])
            if set(act.reviewer_ids.ids) != set(cids):
                act.reviewer_ids = [Command.set(cids)]
            if set(act.responsible_ids.ids) != set(ids):
                act.responsible_ids = [Command.set(ids)]

    def action_open_violation_popup(self):
        """Popup "Xử lý sai phạm" của phiếu: bảng lỗi cần khắc phục như file Excel (tự tạo nếu chưa có)."""
        self.ensure_one()
        self.sudo().action_create_actions()
        self.sudo()._sync_action_owners()  # xem biên bản là đủ để thấy việc khắc phục, không bắt buộc quyền tạo
        view = self.env.ref('store_checklist.view_store_audit_action_violation_list')
        date = fields.Datetime.context_timestamp(self, self.audit_date).strftime('%d/%m/%Y') if self.audit_date else ''
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xử lý sai phạm - %s - %s' % (self.store_id.display_name or '', date),
            'res_model': 'store.audit.action',
            'views': [(view.id, 'list')],
            'domain': [('audit_id', '=', self.id), ('line_id.error_count', '>', 0)],
            'target': 'new',
            'context': {'default_audit_id': self.id, 'dialog_size': 'extra-large', 'group_by': 'line_category'},
        }

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
    error_count = fields.Integer(string='Tổng số lỗi', compute='_compute_error_count', store=True)
    def _report_photos(self):
        """Ảnh của dòng cho biên bản: thu về tối đa 400x500 (gấp đôi ô 200x250 để nét), giữ tỉ lệ, không phóng to."""
        self.ensure_one()
        out = []
        for att in self.sudo().attachment_ids.filtered(lambda a: (a.mimetype or '').startswith('image/')):
            try:
                raw = image_process(att.raw, size=(400, 500), quality=90)
            except Exception:  # ảnh hỏng thì bỏ qua, không làm hỏng cả biên bản
                continue
            out.append('data:%s;base64,%s' % (att.mimetype, base64.b64encode(raw).decode()))
        return out

    attachment_ids = fields.Many2many(
        'ir.attachment', 'store_audit_line_attachment_rel', 'line_id', 'attachment_id',
        string='Bằng chứng')

    @api.depends('note')
    def _compute_error_count(self):
        for rec in self:  # mỗi dòng không trống của "Chi tiết lỗi" là một lỗi
            rec.error_count = len([ln for ln in (rec.note or '').splitlines() if ln.strip()])

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

    # Quy tắc: dòng có "Chi tiết lỗi" thì điểm = 0 và kết quả Không đạt
    def _has_error_note(self):
        return bool((self.note or '').strip())

    @api.onchange('note')
    def _onchange_note(self):
        if self._has_error_note():
            self.actual_score = 0.0
            self.is_scored = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (vals.get('note') or '').strip():
                vals.update(actual_score=0.0, is_scored=True)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'note' in vals or 'actual_score' in vals or 'is_scored' in vals:
            bad = self.filtered(lambda l: l._has_error_note() and (l.actual_score or not l.is_scored))
            if bad:
                super(StoreAuditLine, bad).write({'actual_score': 0.0, 'is_scored': True})
        return res

    @api.onchange('actual_score')
    def _onchange_actual_score(self):
        self.is_scored = True
        if self._has_error_note() and self.actual_score:
            self.actual_score = 0.0
            return {'warning': {
                'title': 'Tiêu chí có lỗi',
                'message': 'Tiêu chí đã nhập "Chi tiết lỗi" nên điểm đánh giá luôn bằng 0 (Không đạt). Xóa chi tiết lỗi nếu muốn chấm điểm.',
            }}
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
