from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

AUDIT_TYPES = [
    ('nvbh', 'Checklist NVBH'),
    ('asm', 'Checklist ASM'),
    ('gs', 'Checklist GS'),
]

CATEGORIES = [
    ('a', 'A. Cơ sở vật chất'),
    ('b', 'B. Tác phong & kỹ năng phục vụ'),
    ('c', 'C. Chuyên môn nghiệp vụ tư vấn'),
]
BASE_CATEGORY_CODES = ('a', 'b', 'c')  # 3 nhóm gốc có tab / cột điểm riêng trên phiếu; nhóm thêm sau (d, e...) gộp vào "Nhóm bổ sung"

DEFAULT_STORE_PLACES = [
    ('GO', 'GO', 10),
    ('TTTM', 'TTTM', 4),
    ('AEON', 'AEON', 6),
    ('Nhà Phố', 'Nhà Phố', 2),
]


class StoreAuditPlace(models.Model):
    """Loại vị trí cửa hàng (đồng bộ từ trường Store Place trên hồ sơ Cửa hàng hr.store)
    để chọn một hoặc nhiều loại trên từng dòng Điểm chuẩn đánh giá giám sát."""
    _name = 'store.audit.place'
    _description = 'Loại vị trí cửa hàng (Store Place)'
    _order = 'sequence, id'

    name = fields.Char(string='Store Place', required=True)
    code = fields.Char(string='Mã', required=True, index=True)
    sequence = fields.Integer(string='STT', default=10)
    color = fields.Integer(string='Màu', default=4)

    _code_uniq = models.Constraint('unique(code)', 'Mã Store Place đã tồn tại.')

    @api.model
    def _sync_from_hr_store(self):
        existing = {p.code: p for p in self.sudo().search([])}
        colors = {'GO': 10, 'TTTM': 4, 'AEON': 6, 'Nhà Phố': 2}
        items = list(DEFAULT_STORE_PLACES)
        if 'hr.store.place' in self.env:
            try:
                places = self.env['hr.store.place'].sudo().search([], order='sequence, id')
                if places:
                    items = []
                    for i, p in enumerate(places):
                        name = (p.name or p.code or '').strip()
                        code = 'Nhà Phố' if name == 'Mặt phố' else name
                        items.append((code, code, colors.get(code, (i % 10) + 1)))
            except Exception:
                pass
        elif 'hr.store' in self.env and 'store_place' in self.env['hr.store']._fields:
            field = self.env['hr.store']._fields['store_place']
            if getattr(field, 'type', None) == 'selection':
                sel = getattr(field, 'selection', None)
                if callable(sel):
                    try:
                        sel = sel(self.env['hr.store'])
                    except Exception:
                        sel = None
                if sel:
                    items = [(k, lbl, colors.get(k, (i % 10) + 1)) for i, (k, lbl) in enumerate(sel)]
        if 'Mặt phố' in existing and 'Nhà Phố' not in existing:
            existing['Mặt phố'].sudo().write({'code': 'Nhà Phố', 'name': 'Nhà Phố', 'color': 2})
            existing['Nhà Phố'] = existing.pop('Mặt phố')
        for idx, (code, label, color) in enumerate(items, 1):
            rec = existing.get(code)
            if rec:
                if rec.name != label:
                    rec.sudo().write({'name': label})
            else:
                existing[code] = self.sudo().create({
                    'code': code, 'name': label, 'sequence': idx * 10, 'color': color,
                })
        return self.sudo().search([], order='sequence, id')

    def init(self):
        self._sync_from_hr_store()

    @api.model
    def get_place_options(self):
        recs = self._sync_from_hr_store()
        return [{'id': r.id, 'code': r.code, 'name': r.name, 'color': r.color} for r in recs]


def category_selection(model):
    """Danh sách Nhóm tiêu chí: 3 nhóm gốc A/B/C (tên lấy theo danh mục nếu đã đổi) + các nhóm người dùng tự thêm."""
    env = model.env
    res = dict(CATEGORIES)
    order = [k for k, _l in CATEGORIES]
    if 'store.audit.category' in env:
        try:
            with env.cr.savepoint(flush=False):
                env.cr.execute("SELECT code, name FROM store_audit_category ORDER BY sequence, id")
                for code, name in env.cr.fetchall():
                    if code:
                        if code not in res:
                            order.append(code)
                        res[code] = name
        except Exception:
            pass  # bảng chưa tạo (đang cài module)
    return [(k, res[k]) for k in order]


def category_list(env):
    """[(code, name)] theo thứ tự hiển thị."""
    return category_selection(env['store.audit.category'])


class StoreAuditCategory(models.Model):
    """Danh mục Nhóm tiêu chí (A. Cơ sở vật chất, B. ..., C. ..., và nhóm tự thêm D, E...).
    Giá trị lưu trên tiêu chí / phiếu là mã (a, b, c, d...) nên dữ liệu cũ giữ nguyên."""
    _name = 'store.audit.category'
    _description = 'Nhóm tiêu chí'
    _order = 'sequence, id'

    name = fields.Char(string='Nhóm tiêu chí', required=True)
    code = fields.Char(string='Mã', readonly=True, copy=False, index=True)
    sequence = fields.Integer(string='STT', default=10)

    _code_uniq = models.Constraint('unique(code)', 'Mã nhóm tiêu chí đã tồn tại.')

    def _check_access(self, operation):
        res = super()._check_access(operation)
        if operation == 'read' or res or self.env.su:
            return res
        user = self.env.user
        if user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager'):
            return res
        rights = self.env['store.perm.rule']._rights()
        if rights is not None and any((rights.get(k) or {}).get(operation) for k in ('subgroup', 'gs_subgroup', 'benchmark', 'gs_benchmark')):
            return res
        return self, lambda: AccessError('Bạn không có quyền thêm / sửa Nhóm tiêu chí.')

    @api.model
    def _next_code(self, used):
        for i in range(ord('d'), ord('z') + 1):
            if chr(i) not in used:
                return chr(i)
        n = 1
        while 'z%d' % n in used:
            n += 1
        return 'z%d' % n

    @api.model_create_multi
    def create(self, vals_list):
        used = set(self.sudo().search([]).mapped('code')) | set(BASE_CATEGORY_CODES)
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self._next_code(used)
            used.add(vals['code'])
            if 'sequence' not in vals:
                vals['sequence'] = 10 * (len(used) + 1)
        return super().create(vals_list)

    def unlink(self):
        if self.filtered(lambda c: c.code in BASE_CATEGORY_CODES):
            raise UserError(_('Không xóa được 3 nhóm gốc A / B / C (chỉ đổi tên được).'))
        for cat in self:
            if self.env['store.audit.template.line'].sudo().search_count([('category', '=', cat.code)]):
                raise UserError(_('Nhóm "%s" đang có tiêu chí, hãy chuyển tiêu chí sang nhóm khác trước khi xóa.') % cat.name)
        return super().unlink()

    @api.model
    def _ensure_base_categories(self):
        """Tạo 3 nhóm gốc A/B/C trong danh mục (chạy mỗi lần nâng cấp, không ghi đè tên đã đổi)."""
        have = set(self.sudo().search([]).mapped('code'))
        for i, (code, name) in enumerate(CATEGORIES):
            if code not in have:
                self.sudo().create({'code': code, 'name': name, 'sequence': 10 * (i + 1)})


class CategoryPickMixin(models.AbstractModel):
    """Ô chọn Nhóm tiêu chí dạng danh mục (thêm nhóm mới ngay trong ô chọn); giá trị thật vẫn lưu ở trường category."""
    _name = 'store.audit.category.pick.mixin'
    _description = 'Chọn nhóm tiêu chí'

    category = fields.Selection(category_selection, string='Nhóm tiêu chí')
    category_id = fields.Many2one('store.audit.category', string='Nhóm tiêu chí', compute='_compute_category_id',
                                  inverse='_inverse_category_id')

    @api.depends('category')
    def _compute_category_id(self):
        cats = {c.code: c for c in self.env['store.audit.category'].sudo().search([])}
        for rec in self:
            rec.category_id = cats.get(rec.category, False)

    def _inverse_category_id(self):
        for rec in self:
            if rec.category_id and rec.category != rec.category_id.code:
                rec.category = rec.category_id.code

    @api.model
    def _map_category_vals(self, vals):
        if vals.get('category_id'):
            vals['category'] = self.env['store.audit.category'].sudo().browse(vals['category_id']).code
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._map_category_vals(dict(v)) for v in vals_list])

    def write(self, vals):
        return super().write(self._map_category_vals(dict(vals)))

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category != self.category_id.code:
            self.category = self.category_id.code


class StoreAuditTemplate(models.Model):
    _name = 'store.audit.template'
    _inherit = 'store.perm.mixin'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return ('gs_' if self.audit_type == 'gs' else '') + 'benchmark'

    @api.model
    def _perm_key_vals(self, vals):
        return ('gs_' if (vals.get('audit_type') or 'nvbh') == 'gs' else '') + 'benchmark'

    _description = 'Mẫu checklist audit'

    name = fields.Char(string='Tên mẫu', required=True)
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    active = fields.Boolean(default=True)
    line_ids = fields.One2many('store.audit.template.line', 'template_id', string='Tiêu chí')


class StoreAuditSubGroup(models.Model):
    _name = 'store.audit.sub.group'
    _inherit = ['store.perm.mixin', 'store.audit.category.pick.mixin']
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return ('gs_' if self.audit_type == 'gs' else '') + 'subgroup'

    @api.model
    def _perm_key_vals(self, vals):
        return ('gs_' if (vals.get('audit_type') or 'nvbh') == 'gs' else '') + 'subgroup'

    _description = 'Phân nhóm tiêu chí'
    _order = 'sequence, id'

    name = fields.Char(string='Phân nhóm', required=True)
    category = fields.Selection(category_selection, string='Mã nhóm tiêu chí', required=True, default='a')
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    sequence = fields.Integer(string='STT', default=10)

    def write(self, vals):
        res = super().write(vals)
        if 'sequence' in vals or 'category' in vals or 'category_id' in vals:
            # đổi thứ tự / nhóm của phân nhóm: đánh lại STT tiêu chí của các mẫu có dùng phân nhóm này
            Line = self.env['store.audit.template.line'].sudo()
            Line._renumber(templates=Line.search([('sub_group_id', 'in', self.ids)]).mapped('template_id'))
        return res

    def action_edit_popup(self):
        """Nút bút chì trên dòng nhóm của bảng Điểm chuẩn: sửa tên / nhóm tiêu chí / STT của Phân nhóm trong popup."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sửa phân nhóm',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(self.env.ref('store_checklist.view_store_sub_group_form').id, 'form')],
            'target': 'new',
        }


class StoreAuditTemplateLine(models.Model):
    _name = 'store.audit.template.line'
    _inherit = ['store.perm.mixin', 'store.audit.category.pick.mixin']
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return ('gs_' if self.audit_type == 'gs' else '') + 'benchmark'

    @api.model
    def _perm_key_vals(self, vals):
        return ('gs_' if (self.env['store.audit.template'].sudo().browse(vals.get('template_id') or 0).audit_type or 'nvbh') == 'gs' else '') + 'benchmark'

    _description = 'Tiêu chí mẫu checklist'
    _order = 'sequence, id'

    template_id = fields.Many2one('store.audit.template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='STT', default=0,
                              help='Hệ thống tự đánh số liên tục 1, 2, 3... theo nhóm A, B, C. Để trống: thêm vào cuối nhóm; '
                                   'nhập số: chèn vào vị trí đó trong nhóm.')
    category = fields.Selection(category_selection, string='Nhóm tiêu chí', required=True)
    sub_group_id = fields.Many2one('store.audit.sub.group', string='Phân nhóm', ondelete='restrict')
    audit_type = fields.Selection(related='template_id.audit_type', string='Loại checklist')
    name = fields.Char(string='Tiêu chí đánh giá', required=True)
    requirement = fields.Text(string='Yêu cầu / Tiêu chuẩn')
    max_score = fields.Float(string='Điểm chuẩn', default=2.0)
    responsible_ids = fields.Many2many(
        'hr.employee', 'store_audit_template_line_responsible_rel', 'line_id', 'employee_id',
        string='Người phụ trách')
    controller_ids = fields.Many2many(
        'res.users', 'store_audit_template_line_controller_rel', 'line_id', 'user_id',
        string='Người kiểm soát')
    lug_group_ids = fields.Many2many(
        'lug.group', 'store_audit_template_line_lug_group_rel', 'line_id', 'group_id',
        string='Group (LUG Permission)')
    store_place_ids = fields.Many2many(
        'store.audit.place', 'store_audit_template_line_place_rel', 'line_id', 'place_id',
        string='Store Place',
        help='Chọn loại hình cửa hàng áp dụng (GO, TTTM, AEON, Nhà Phố). Để trống = không đưa vào Checklist Giám sát của bất kỳ cửa hàng nào.')

    def matches_store(self, store):
        """Logic lọc Store Place cho Checklist Giám sát (audit_type == 'gs'):
        - Không gán Store Place -> không hiển thị ở bất kỳ cửa hàng nào.
        - Cửa hàng chưa chọn hoặc không khớp loại hình được gán -> không hiển thị.
        - Cửa hàng thuộc loại hình được gán tại Store Place -> hiển thị.
        Các loại phiếu khác (nvbh, asm) không dùng Store Place -> luôn hiển thị."""
        if self.template_id.audit_type != 'gs':
            return True
        places = self.sudo().store_place_ids
        if not places or not store:
            return False
        st = store.sudo()
        splace = (st.store_place or '').strip() if 'store_place' in st._fields else ''
        if not splace:
            return False
        return splace in {(p.code or '').strip() for p in places}

    def web_read(self, specification):
        """User thường không xem được hồ sơ nhân viên khác (hr_employee_self_only) nên đọc cột này báo MissingError;
        tên người phụ trách chỉ là nhãn của tiêu chí nên đọc bằng sudo."""
        if 'responsible_ids' not in specification:
            return super().web_read(specification)
        res = super().web_read({k: v for k, v in specification.items() if k != 'responsible_ids'})
        for vals in res:
            emps = self.browse(vals['id']).sudo().responsible_ids
            vals['responsible_ids'] = [{'id': e.id, 'display_name': e.display_name} for e in emps]
        return res

    _XLS_HEAD = ['Mẫu checklist', 'STT', 'Nhóm tiêu chí', 'Phân nhóm', 'Tiêu chí đánh giá', 'Yêu cầu / Tiêu chuẩn', 'Điểm chuẩn',
                 'Người phụ trách', 'Người kiểm soát', 'Group (LUG Permission)']
    _XLS_HEAD_GS = ['Mẫu checklist', 'STT', 'Nhóm tiêu chí', 'Phân nhóm', 'Tiêu chí đánh giá', 'Yêu cầu / Tiêu chuẩn', 'Store Place',
                    'Điểm chuẩn', 'Người phụ trách', 'Người kiểm soát', 'Group (LUG Permission)']

    @api.model
    def _xls_domain(self, scope):
        return [('template_id.audit_type', '=', 'gs')] if scope == 'gs' else [('template_id.audit_type', '!=', 'gs')]

    @api.model
    def export_xlsx(self, scope='gs'):
        """Xuất Điểm chuẩn đánh giá ra Excel (scope 'gs' = giám sát, 'other' = NVBH / ASM). File xuất ra nhập lại được."""
        self.env['store.perm.rule'].check_export()
        import base64
        import io as _io
        import xlsxwriter
        lines = self.search(self._xls_domain(scope), order='template_id, sequence, id')
        buf = _io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Diem chuan')
        head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True})
        cell = book.add_format({'border': 1, 'valign': 'top', 'text_wrap': True})
        num = book.add_format({'border': 1, 'valign': 'top', 'num_format': '0.##'})
        is_gs = scope == 'gs'
        headers = self._XLS_HEAD_GS if is_gs else self._XLS_HEAD
        widths = [18, 6, 26, 24, 34, 60, 20, 10, 28, 28, 26] if is_gs else [18, 6, 26, 24, 34, 60, 10, 28, 28, 26]
        num_cols = (1, 7) if is_gs else (1, 6)
        for i, (h, w) in enumerate(zip(headers, widths)):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        cats = dict(category_list(self.env))
        for r, ln in enumerate(lines, 1):
            vals = [ln.template_id.name, ln.sequence, cats.get(ln.category, ''), ln.sub_group_id.name or '', ln.name, ln.requirement or '']
            if is_gs:
                vals.append(', '.join(ln.sudo().store_place_ids.mapped('name')))
            vals.extend([
                ln.max_score, ', '.join(ln.sudo().responsible_ids.mapped('name')), ', '.join(ln.controller_ids.mapped('name')),
                ', '.join(ln.sudo().lug_group_ids.mapped('name')),
            ])
            for c, v in enumerate(vals):
                sheet.write(r, c, v, num if c in num_cols else cell)
        sheet.freeze_panes(1, 0)
        book.close()
        name = 'Diem_chuan_%s.xlsx' % ('giam_sat' if scope == 'gs' else 'nvbh_asm')
        return {'name': name, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def import_xlsx(self, scope, data):
        """Nhập Điểm chuẩn từ Excel (cùng cột với file xuất) theo kiểu THAY THẾ: file là dữ liệu chuẩn của mẫu.
        Trùng Mẫu + Tiêu chí thì cập nhật, chưa có thì thêm mới; tiêu chí của mẫu không còn trong file thì xóa;
        STT đánh lại theo thứ tự dòng trong file; phân nhóm không còn tiêu chí nào thì xóa.
        Dòng lỗi được bỏ qua và báo lại. Phiếu đánh giá đã tạo không bị ảnh hưởng (phiếu lưu bản sao tiêu chí)."""
        import base64
        import io as _io
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise UserError(_('Máy chủ chưa cài thư viện openpyxl để đọc file Excel.'))
        try:
            wb = load_workbook(_io.BytesIO(base64.b64decode(data)), data_only=True, read_only=True)
            rows = list(wb.worksheets[0].iter_rows(values_only=True))
        except Exception:
            raise UserError(_('Không đọc được file. Hãy dùng file .xlsx (xuất từ nút Xuất Excel).'))

        def txt(v):
            return ('%s' % v).strip() if v is not None else ''

        hi = next((i for i, r in enumerate(rows) if 'tiêu chí đánh giá' in [txt(c).casefold() for c in r]), None)
        if hi is None:
            raise UserError(_('Không tìm thấy dòng tiêu đề có cột "Tiêu chí đánh giá".'))
        col = {txt(c).casefold(): i for i, c in enumerate(rows[hi]) if txt(c)}

        def get(r, name):
            i = col.get(name.casefold())
            return txt(r[i]) if i is not None and i < len(r) else ''

        Template = self.env['store.audit.template'].sudo()
        templates = Template.search([('audit_type', '=', 'gs')] if scope == 'gs' else [('audit_type', '!=', 'gs')])
        if not templates:
            raise UserError(_('Chưa có mẫu checklist nào để nhập.'))
        by_name = {t.name.strip().casefold(): t for t in templates}
        Emp, User = self.env['hr.employee'].sudo(), self.env['res.users'].sudo()
        Group = self.env['lug.group'].sudo() if 'lug.group' in self.env else None
        SubGroup = self.env['store.audit.sub.group'].sudo()
        places = self.env['store.audit.place'].sudo()._sync_from_hr_store()
        place_map = {}
        for p in places:
            place_map[p.code.strip().casefold()] = p.id
            place_map[p.name.strip().casefold()] = p.id
        if 'nhà phố' in place_map:
            place_map['mặt phố'] = place_map['nhà phố']
        cat_list = category_list(self.env)
        cat_keys = {k for k, _l in cat_list}
        cat_by_name = {l.strip().casefold(): k for k, l in cat_list}
        created = updated = 0
        errors = []
        touched = {}  # template id -> ids tiêu chí có trong file

        def many(model, names, domain_fn):
            ids, miss = [], []
            for n in [x.strip() for x in names.replace(';', ',').split(',') if x.strip()]:
                rec = model.search(domain_fn(n), limit=1)
                (ids.append(rec.id) if rec else miss.append(n))
            return ids, miss

        for n, r in enumerate(rows[hi + 1:], hi + 2):
            name = get(r, 'Tiêu chí đánh giá')
            if not name:
                continue
            tname = get(r, 'Mẫu checklist').casefold()
            tmpl = by_name.get(tname) if tname else (templates[0] if scope == 'gs' else None)
            if not tmpl:
                errors.append('Dòng %s: không tìm thấy mẫu checklist "%s"' % (n, get(r, 'Mẫu checklist')))
                continue
            seen = touched.setdefault(tmpl.id, [])
            # trùng tên trong cùng file: dòng sau là tiêu chí mới, không ghi đè dòng trước
            line = self.search([('template_id', '=', tmpl.id), ('name', '=', name), ('id', 'not in', seen)], limit=1)
            vals = {'name': name, 'sequence': n}  # giữ đúng thứ tự dòng trong file; đánh lại 1..N ở cuối
            cat_txt = get(r, 'Nhóm tiêu chí')
            cat = cat_by_name.get(cat_txt.casefold()) or (cat_txt.split('.')[0].strip().lower() if cat_txt else '')
            if cat in cat_keys:
                vals['category'] = cat
            elif not line:
                errors.append('Dòng %s: Nhóm tiêu chí "%s" chưa có trong danh mục' % (n, cat_txt))
                continue
            try:
                if get(r, 'Điểm chuẩn'):
                    vals['max_score'] = float(get(r, 'Điểm chuẩn').replace(',', '.'))
            except ValueError:
                errors.append('Dòng %s: STT hoặc Điểm chuẩn không phải số' % n)
                continue
            if 'yêu cầu / tiêu chuẩn' in col:
                vals['requirement'] = get(r, 'Yêu cầu / Tiêu chuẩn')
            sg = get(r, 'Phân nhóm')
            if sg:
                grp = SubGroup.search([('audit_type', '=', tmpl.audit_type), ('name', '=ilike', sg)], limit=1)
                if not grp:
                    grp = SubGroup.create({'name': sg, 'audit_type': tmpl.audit_type, 'category': vals.get('category') or line.category})
                vals['sub_group_id'] = grp.id
            ids, miss = many(Emp, get(r, 'Người phụ trách'), lambda x: [('name', '=ilike', x)])
            if 'người phụ trách' in col:
                vals['responsible_ids'] = [Command.set(ids)]
            ids2, miss2 = many(User, get(r, 'Người kiểm soát'), lambda x: ['|', ('name', '=ilike', x), ('login', '=ilike', x)])
            if 'người kiểm soát' in col:
                vals['controller_ids'] = [Command.set(ids2)]
            miss3 = []
            if Group is not None and 'group (lug permission)' in col:
                ids3, miss3 = many(Group, get(r, 'Group (LUG Permission)'), lambda x: [('name', '=ilike', x)])
                vals['lug_group_ids'] = [Command.set(ids3)]
            miss_sp = []
            if 'store place' in col:
                raw_sp = get(r, 'Store Place')
                if raw_sp.casefold() in ('', '-'):
                    vals['store_place_ids'] = [Command.set([])]
                elif raw_sp.casefold() in ('tất cả', 'all'):
                    vals['store_place_ids'] = [Command.set(places.ids)]
                else:
                    pids = []
                    for tok in [x.strip() for x in raw_sp.replace(';', ',').replace('/', ',').split(',') if x.strip()]:
                        pid = place_map.get(tok.casefold())
                        if pid:
                            if pid not in pids:
                                pids.append(pid)
                        else:
                            miss_sp.append(tok)
                    vals['store_place_ids'] = [Command.set(pids)]
            if miss or miss2 or miss3 or miss_sp:
                errors.append('Dòng %s: không tìm thấy %s (đã bỏ qua phần này)' % (n, ', '.join(miss + miss2 + miss3 + miss_sp)))
            if line:
                line.with_context(skip_renumber=True).write(vals)
                if 'category' in vals or 'sub_group_id' in vals:
                    line._auto_sub_group()
                updated += 1
            else:
                line = self.with_context(skip_renumber=True).create(dict(vals, template_id=tmpl.id))
                created += 1
            seen.append(line.id)
        removed = 0
        tmpls = Template.browse(list(touched))
        if tmpls:
            # thay thế: tiêu chí của mẫu không còn trong file thì xóa
            old = self.search([('template_id', 'in', tmpls.ids), ('id', 'not in', [i for ids in touched.values() for i in ids])])
            removed = len(old)
            old.with_context(skip_renumber=True).unlink()
            self._renumber(templates=tmpls)
            # phân nhóm của loại checklist này không còn tiêu chí nào thì xóa
            for atype in set(tmpls.mapped('audit_type')):
                used = self.search([('template_id.audit_type', '=', atype)]).mapped('sub_group_id')
                SubGroup.search([('audit_type', '=', atype), ('id', 'not in', used.ids)]).unlink()
        return {'created': created, 'updated': updated, 'removed': removed, 'benchmark': True,
                'errors': errors[:20], 'error_count': len(errors)}

    @api.onchange('category')
    def _onchange_category(self):
        if self.sub_group_id and self.sub_group_id.category != self.category:
            self.sub_group_id = False

    @api.model_create_multi
    def create(self, vals_list):
        # STT để trống: đưa xuống cuối phân nhóm; sau đó đánh lại STT liên tục cho cả mẫu
        for vals in vals_list:
            if not vals.get('sequence'):
                vals['sequence'] = 10 ** 6
        lines = super().create(vals_list)
        lines._auto_sub_group()
        lines._renumber(moved=lines.filtered(lambda l: l.sequence < 10 ** 6))
        return lines

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_renumber'):
            return res
        if 'category' in vals or 'category_id' in vals or 'sub_group_id' in vals:
            self._auto_sub_group()
        if {'sequence', 'category', 'category_id', 'sub_group_id', 'template_id'} & set(vals):
            self._renumber(moved=self if 'sequence' in vals else self.browse())
        return res

    def unlink(self):
        templates = self.mapped('template_id')
        res = super().unlink()
        if not self.env.context.get('skip_renumber'):
            self._renumber(templates=templates)
        return res

    def _renumber(self, templates=None, moved=None):
        """Đánh lại STT liên tục 1..N trong mỗi mẫu checklist: theo thứ tự nhóm tiêu chí (A, B, C...), rồi phân nhóm,
        rồi STT hiện tại. Dòng vừa nhập STT (moved) được chèn trước dòng đang giữ số đó."""
        templates = (templates if templates is not None else self.mapped('template_id')).exists()
        if not templates:
            return
        cat_idx = {k: i for i, (k, _l) in enumerate(category_list(self.env))}
        moved_ids = set((moved or self.browse()).ids)
        for tmpl in templates.sudo():
            lines = self.sudo().search([('template_id', '=', tmpl.id)])
            ordered = lines.sorted(lambda l: (
                cat_idx.get(l.category, len(cat_idx)), l.sub_group_id.sequence or 0, l.sub_group_id.id or 0,
                l.sequence, 0 if l.id in moved_ids else 1, l.id))
            for i, line in enumerate(ordered, 1):
                if line.sequence != i:
                    line.with_context(skip_renumber=True).write({'sequence': i})

    @api.model
    def _renumber_all(self):
        self._renumber(templates=self.env['store.audit.template'].sudo().with_context(active_test=False).search([]))

    def _auto_sub_group(self):
        """Tiêu chí thuộc nhóm tự thêm (D, E...) mà chưa chọn Phân nhóm: tự gán phân nhóm cùng tên nhóm (vd. "E. HÀNG HÓA"),
        chưa có thì tạo, để bảng Điểm chuẩn / phiếu hiện đúng nhóm thay vì "Không"."""
        SubGroup = self.env['store.audit.sub.group'].sudo()
        names = dict(category_list(self.env))
        for line in self.sudo().filtered(lambda l: not l.sub_group_id and l.category and l.category not in BASE_CATEGORY_CODES):
            atype = line.template_id.audit_type or 'nvbh'
            grp = SubGroup.search([('category', '=', line.category), ('audit_type', '=', atype)], order='sequence, id', limit=1)
            if not grp:
                last = SubGroup.search([('audit_type', '=', atype)], order='sequence desc', limit=1)
                grp = SubGroup.create({'name': (names.get(line.category) or line.category).upper(), 'category': line.category,
                                       'audit_type': atype, 'sequence': (last.sequence or 0) + 10})
            line.sub_group_id = grp

    @api.model
    def _fix_missing_sub_groups(self):
        self.sudo().search([('sub_group_id', '=', False), ('category', 'not in', list(BASE_CATEGORY_CODES))])._auto_sub_group()

    @api.onchange('sub_group_id')
    def _onchange_sub_group_id(self):
        if self.sub_group_id:
            self.category = self.sub_group_id.category

    def action_open_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }
