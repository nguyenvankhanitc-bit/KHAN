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
    mien = fields.Selection(related='audit_id.store_id.mien', string='Miền', store=True, index=True)  # lưu để group theo Miền
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

    @api.model
    def _search(self, domain, *args, **kwargs):
        # Phân quyền xem nhân sự: user có cấu hình thì chỉ thấy đúng Miền / Cửa hàng được cấp
        # (thay cho phạm vi cửa hàng mặc định của phiếu audit -> tìm bằng sudo để không bị cắt thêm).
        scope = self.env['store.staff.view.rule']._staff_domain(('nvbh_staff',))
        if scope is None:
            return super()._search(domain, *args, **kwargs)
        return super(StoreAuditStaff, self.sudo())._search(scope + list(domain or []), *args, **kwargs)


# Các mục con của Checklist NVBH mà phân quyền xem nhân sự áp dụng được
STAFF_MENUS = [
    ('nvbh_staff', 'Nhân sự'),
    ('nvbh_jobs', 'Công việc check list'),
    ('nvbh_done', 'Danh sách checklist NV'),
    ('nvbh_mg', 'Quản lý & đánh giá'),
]
# 3 mục cùng dùng dữ liệu phiếu checklist / lịch xếp ca (store.nvbh.check, store.nvbh.schedule.line)
CHECK_MENUS = ('nvbh_jobs', 'nvbh_done', 'nvbh_mg')

SCOPES = [
    ('all', 'Tất cả nhân sự'),
    ('mien', 'Theo miền'),
    ('store', 'Theo cửa hàng'),
]


class StoreStaffViewRule(models.Model):
    """Cài đặt > Phân quyền > tab "Phân quyền xem nhân sự": user được xem nhân sự của Miền / Cửa hàng nào
    trong Checklist NVBH > Nhân sự. User không có dòng nào = phạm vi mặc định; Quản lý / Admin xem tất cả.
    User nằm trong nhiều dòng thì phạm vi được cộng dồn."""
    _name = 'store.staff.view.rule'
    _description = 'Phân quyền xem nhân sự'
    _order = 'id'

    name = fields.Char('Tên phân quyền')
    user_ids = fields.Many2many('res.users', 'store_staff_view_rule_users', 'rule_id', 'user_id', string='User')
    scope = fields.Selection(SCOPES, string='Phạm vi', default='store', required=True)
    miens = fields.Json('Miền', default=list)  # danh sách mã miền (hr.store.mien)
    store_ids = fields.Many2many('hr.store', 'store_staff_view_rule_stores', 'rule_id', 'store_id', string='Cửa hàng')
    menu_keys = fields.Json('Mục áp dụng', default=lambda self: ['nvbh_staff'])  # khóa trong STAFF_MENUS

    def _menus(self):
        return self.menu_keys if self.menu_keys is not None else ['nvbh_staff']  # dòng cũ: chỉ mục Nhân sự

    @api.model
    def _scope_store_ids(self, keys):
        """Cửa hàng user hiện tại được xem ở các mục `keys`: None = không có cấu hình (giữ phạm vi mặc định),
        True = tất cả, set(id) = đúng các cửa hàng được cấp. Admin / Quản lý luôn None."""
        user = self.env.user
        if self.env.su or user._is_admin() or user.has_group('store_checklist.group_store_manager'):
            return None
        rules = self.sudo().search([('user_ids', 'in', user.id)]).filtered(lambda r: set(r._menus()) & set(keys))
        if not rules:
            return None
        if any(r.scope == 'all' for r in rules):
            return True
        store_ids = set(rules.filtered(lambda r: r.scope == 'store').store_ids.ids)
        miens = {m for r in rules.filtered(lambda r: r.scope == 'mien') for m in (r.miens or [])}
        if miens:
            store_ids |= set(self.env['hr.store'].sudo().search([('mien', 'in', list(miens))]).ids)
        return store_ids

    @api.model
    def _staff_domain(self, keys):
        """Domain theo cửa hàng cho các mục `keys`; None = không áp."""
        ids = self._scope_store_ids(keys)
        if ids is None:
            return None
        return [] if ids is True else [('store_id', 'in', list(ids))]

    @api.model
    def get_my_staff_scope(self):
        """Các mục (khóa) user hiện tại có cấu hình -> shell không bắt chọn cửa hàng trước ở màn Nhân sự."""
        return [k for k, _l in STAFF_MENUS if self._scope_store_ids((k,)) is not None]

    @api.model
    def get_my_staff_stores(self):
        """Cửa hàng user hiện tại được xem ở mục Nhân sự (ô lọc cửa hàng); rỗng = không có cấu hình."""
        ids = self._scope_store_ids(('nvbh_staff',))
        if ids is None:
            return []
        Store = self.env['hr.store'].sudo()
        stores = Store.search([] if ids is True else [('id', 'in', list(ids))], order='name')
        return [{'id': s.id, 'name': s.display_name} for s in stores]

    def _manager_only(self):
        if not self.env.user.has_group('store_checklist.group_store_manager') and not self.env.is_admin():
            raise AccessError('Chỉ Quản lý mới được phân quyền.')

    @api.model
    def get_rules(self):
        self._manager_only()
        mien_labels = dict(self.env['hr.store']._fields['mien']._description_selection(self.env))
        return {
            'miens': [{'id': k, 'name': v} for k, v in mien_labels.items()],
            'menus': [{'id': k, 'name': v} for k, v in STAFF_MENUS],
            'stores': [{'id': s.id, 'name': s.display_name, 'mien': s.mien or ''}
                       for s in self.env['hr.store'].sudo().search([], order='name')],
            'rules': [{
                'id': r.id, 'name': r.name or '', 'scope': r.scope, 'menus': r._menus(),
                'users': [{'id': u.id, 'name': u.name} for u in r.user_ids],
                'miens': [{'id': m, 'name': mien_labels.get(m, m)} for m in (r.miens or [])],
                'stores': [{'id': s.id, 'name': s.display_name} for s in r.store_ids],
            } for r in self.sudo().search([])],
        }

    @api.model
    def save_rule(self, vals):
        """vals: {id|0, name, scope, user_ids, miens, store_ids}."""
        self._manager_only()
        data = {
            'name': vals.get('name') or False,
            'scope': vals.get('scope') or 'store',
            'menu_keys': [k for k in (vals.get('menu_keys') or []) if k in dict(STAFF_MENUS)],
            'user_ids': [(6, 0, vals.get('user_ids') or [])],
            'miens': vals.get('miens') or [] if vals.get('scope') == 'mien' else [],
            'store_ids': [(6, 0, vals.get('store_ids') or [] if vals.get('scope') == 'store' else [])],
        }
        if vals.get('id'):
            self.sudo().browse(vals['id']).write(data)
        else:
            self.sudo().create(data)
        return True

    @api.model
    def delete_rule(self, rule_id):
        self._manager_only()
        self.sudo().browse(rule_id).unlink()
        return True
