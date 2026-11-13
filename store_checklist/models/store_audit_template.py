from odoo import api, fields, models

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
