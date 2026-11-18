from odoo import api, fields, models
from odoo.exceptions import AccessError

STAFF_POSITIONS = [
    ('NVBH', 'NVBH'),
    ('NT', 'NT'),
    ('CHT', 'CHT'),
    ('ASM', 'ASM'),
    ('RSM', 'RSM'),
]

STAFF_STATES = [
    ('active', 'Hoạt động'),
    ('inactive', 'Ngừng'),
]


class StoreAuditStaff(models.Model):
    _name = 'store.audit.staff'
    _description = 'Nhân sự trong phiếu audit'
    _order = 'sequence, id'

    audit_id = fields.Many2one('store.audit', string='Phiếu audit', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    stt = fields.Integer(string='STT', compute='_compute_stt')
    name = fields.Char(string='Họ và tên NV', required=True)
    position = fields.Char(string='Chức vụ', required=True, default='NVBH', help='Mã chức vụ theo file xếp ca: NVBH, NT, CHT, ASMTT, PT...')
    employee_code = fields.Char(string='ID')
    work_status = fields.Char(string='Trạng thái nhân viên', help='Chính thức / Thời vụ... theo file lịch ca')
    phone = fields.Char(string='Số điện thoại')
    # Thông tin phiếu mẹ để lọc / hiển thị trong danh sách Nhân sự
    store_id = fields.Many2one('hr.store', related='audit_id.store_id', string='Cửa hàng', store=True, index=True)
    mien = fields.Selection(related='audit_id.store_id.mien', string='Miền')
    manager = fields.Char(related='audit_id.store_id.manager_id.name', string='ASM phụ trách')
    audit_date = fields.Datetime(related='audit_id.audit_date', string='Ngày vào làm')
    auditor_id = fields.Many2one('res.users', related='audit_id.auditor_id', string='Người nhập')
    staff_state = fields.Selection(STAFF_STATES, string='Trạng thái', default='active', required=True)

    @api.depends('audit_id.staff_ids', 'audit_id.staff_ids.sequence')
    def _compute_stt(self):
        for rec in self:
            rows = rec.audit_id.staff_ids.sorted('sequence')  # sắp xếp ổn định: dòng mới nằm cuối khi trùng sequence
            rec.stt = (list(rows).index(rec) + 1) if rec in rows else 0

    def action_edit_staff(self):
        """Nút cây bút (Quản trị viên): mở popup form nhân sự của phiếu chứa dòng này."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'store.audit', 'res_id': self.audit_id.id,
            'views': [(False, 'form')], 'target': 'new',
            'context': {'store_audit_type': 'nvbh', 'staff_form': True, 'dialog_size': 'extra-large'},
        }

    def action_delete_staff(self):
        """Nút thùng rác (Quản trị viên): xóa nhân sự khỏi danh sách."""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError('Chỉ Quản trị viên mới được xóa nhân sự.')
        self.unlink()
        return True
