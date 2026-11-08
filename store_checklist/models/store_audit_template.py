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
    _description = 'Mẫu checklist audit'

    name = fields.Char(string='Tên mẫu', required=True)
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    active = fields.Boolean(default=True)
    line_ids = fields.One2many('store.audit.template.line', 'template_id', string='Tiêu chí')


class StoreAuditSubGroup(models.Model):
    _name = 'store.audit.sub.group'
    _description = 'Phân nhóm tiêu chí'
    _order = 'sequence, id'

    name = fields.Char(string='Phân nhóm', required=True)
    category = fields.Selection(CATEGORIES, string='Nhóm tiêu chí', required=True, default='a')
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    sequence = fields.Integer(string='STT', default=10)


class StoreAuditTemplateLine(models.Model):
    _name = 'store.audit.template.line'
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
