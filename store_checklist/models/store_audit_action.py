from odoo import fields, models


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
    responsible = fields.Char(string='Người phụ trách')
    deadline = fields.Date(string='Hạn hoàn thành', tracking=True)
    state = fields.Selection([
        ('todo', 'Đang xử lý'),
        ('done', 'Đã khắc phục'),
        ('verified', 'Đã xác minh'),
    ], string='Trạng thái', default='todo', required=True, tracking=True)
