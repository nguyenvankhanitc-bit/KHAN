from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

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
    _inherit = 'store.perm.mixin'
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
    category = fields.Selection(CATEGORIES, string='Nhóm tiêu chí', required=True, default='a')
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    sequence = fields.Integer(string='STT', default=10)


class StoreAuditTemplateLine(models.Model):
    _name = 'store.audit.template.line'
    _inherit = 'store.perm.mixin'
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
    sequence = fields.Integer(string='STT', default=10)
    category = fields.Selection(CATEGORIES, string='Nhóm tiêu chí', required=True)
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
        for i, (h, w) in enumerate(zip(self._XLS_HEAD, [18, 6, 26, 24, 34, 60, 10, 28, 28, 26])):
            sheet.write(0, i, h, head)
            sheet.set_column(i, i, w)
        cats = dict(CATEGORIES)
        for r, ln in enumerate(lines, 1):
            vals = [ln.template_id.name, ln.sequence, cats.get(ln.category, ''), ln.sub_group_id.name or '', ln.name, ln.requirement or '',
                    ln.max_score, ', '.join(ln.sudo().responsible_ids.mapped('name')), ', '.join(ln.controller_ids.mapped('name')),
                    ', '.join(ln.sudo().lug_group_ids.mapped('name'))]
            for c, v in enumerate(vals):
                sheet.write(r, c, v, num if c in (1, 6) else cell)
        sheet.freeze_panes(1, 0)
        book.close()
        name = 'Diem_chuan_%s.xlsx' % ('giam_sat' if scope == 'gs' else 'nvbh_asm')
        return {'name': name, 'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def import_xlsx(self, scope, data):
        """Nhập Điểm chuẩn từ Excel (cùng cột với file xuất): trùng Mẫu + Tiêu chí thì cập nhật, chưa có thì thêm mới.
        Dòng lỗi được bỏ qua và báo lại; các dòng hợp lệ vẫn được lưu."""
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
        cat_keys = {k for k, _l in CATEGORIES}
        created = updated = 0
        errors = []

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
            line = self.search([('template_id', '=', tmpl.id), ('name', '=', name)], limit=1)
            vals = {'name': name}
            cat = get(r, 'Nhóm tiêu chí')[:1].lower()
            if cat in cat_keys:
                vals['category'] = cat
            elif not line:
                errors.append('Dòng %s: thiếu Nhóm tiêu chí (A / B / C)' % n)
                continue
            try:
                if get(r, 'STT'):
                    vals['sequence'] = int(float(get(r, 'STT').replace(',', '.')))
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
            if miss or miss2 or miss3:
                errors.append('Dòng %s: không tìm thấy %s (đã bỏ qua phần này)' % (n, ', '.join(miss + miss2 + miss3)))
            if line:
                line.write(vals)
                updated += 1
            else:
                self.create(dict(vals, template_id=tmpl.id))
                created += 1
        return {'created': created, 'updated': updated, 'errors': errors[:20], 'error_count': len(errors)}

    @api.onchange('category')
    def _onchange_category(self):
        if self.sub_group_id and self.sub_group_id.category != self.category:
            self.sub_group_id = False

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
