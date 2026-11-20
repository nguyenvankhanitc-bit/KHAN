# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError

# Thư mục (id khớp sidebar) và các mục con: (khóa, nhãn, thư mục)
FOLDERS = [
    ('audit', 'Checklist Audit'),
    ('report', 'Báo cáo'),
    ('violation', 'Xử lý sai phạm'),
    ('evaluation', 'Cài đặt › Công việc đánh giá'),
    ('supervision', 'Cài đặt › Công việc giám sát'),
    ('nvbh_work', 'Cài đặt › Công việc checklist NVBH'),
]
MENUS = [
    ('overview', 'Tổng quan', 'audit'),
    ('nvbh', 'Checklist NVBH', 'audit'),
    ('nvbh_staff', 'Checklist NVBH › Nhân sự', 'audit'),
    ('nvbh_jobs', 'Checklist NVBH › Công việc check list', 'audit'),
    ('nvbh_today', 'Checklist NVBH › Lịch ca hôm nay', 'audit'),
    ('nvbh_done', 'Checklist NVBH › Danh sách checklist NV', 'audit'),
    ('nvbh_mg', 'Checklist NVBH › Quản lý & đánh giá', 'audit'),
    ('asm', 'Checklist ASM', 'audit'),
    ('gs', 'Checklist GS', 'audit'),
    ('review', 'Phiếu Đánh Giá', 'audit'),
    ('review_list', 'Danh Sách Đánh Giá', 'audit'),
    ('report_gs', 'Báo cáo GS', 'report'),
    ('report_nvbh', 'BC Checklist NVBH KPI', 'report'),
    ('report_nsuat', 'BC Năng suất NVBH', 'report'),
    ('report_nvbh_asm', 'BC Checklist NVBH ASM', 'report'),
    ('report_nvbh_perf', 'BC Hiệu suất NVBH', 'report'),
    ('report_store', 'Báo cáo Audit CH', 'report'),
    ('report_rank', 'Báo cáo xếp loại Audit CH', 'report'),
    ('report_manager', 'Báo cáo theo quản lý', 'report'),
    ('report_flow', 'Sơ đồ quy trình vận hành giám sát', 'report'),
    ('violation_stores', 'Cửa hàng sai phạm', 'violation'),
    ('violation_all', 'Danh sách xử lý sai phạm', 'violation'),
    ('subgroup', 'Phân nhóm đánh giá', 'evaluation'),
    ('benchmark', 'Điểm chuẩn đánh giá', 'evaluation'),
    ('level', 'Mức Đánh giá', 'evaluation'),
    ('gs_subgroup', 'Phân nhóm đánh giá', 'supervision'),
    ('gs_benchmark', 'Điểm chuẩn đánh giá', 'supervision'),
    ('gs_level', 'Mức độ đánh giá', 'supervision'),
    ('shift', 'Danh mục ca', 'nvbh_work'),
    ('nvbh_task', 'Danh sách công việc NVBH', 'nvbh_work'),
    ('nvbh_rating', 'Xếp loại', 'nvbh_work'),
]
OPS = ('read', 'create', 'write', 'unlink', 'export')
# Mục mới chưa có trong ma trận đã lưu thì kế thừa quyền của mục cũ tương ứng (để user hiện có không bị mất quyền sau khi cập nhật)
PERM_INHERIT = {
    'overview': 'nvbh', 'nvbh_staff': 'nvbh', 'nvbh_jobs': 'nvbh', 'nvbh_done': 'nvbh', 'nvbh_mg': 'nvbh',
    'nvbh_today': 'nvbh_jobs',  # Lịch ca hôm nay: mặc định theo quyền Công việc check list
    'report_nvbh': 'report_gs', 'report_nsuat': 'report_gs', 'report_nvbh_asm': 'report_gs',
    'report_nvbh_perf': 'report_nvbh_asm',  # Báo cáo hiệu suất NVBH: mặc định theo quyền BC Checklist NVBH ASM
}
NVBH_SUB_KEYS = ('nvbh_staff', 'nvbh_jobs', 'nvbh_today', 'nvbh_done', 'nvbh_mg')  # quyền gốc 'nvbh' (dữ liệu phiếu NVBH) = có ít nhất một mục con


def perm_of(perms, key):
    """Quyền {op: bool} của một mục trong ma trận đã lưu; mục chưa có thì lấy theo mục kế thừa."""
    perms = perms or {}
    seen = set()
    while key and key not in perms and key not in seen:  # kế thừa nhiều cấp (vd. report_nvbh_perf -> report_nvbh_asm -> report_gs)
        seen.add(key)
        key = PERM_INHERIT.get(key)
    return (perms.get(key) or {}) if key else {}


class StorePermMixin(models.AbstractModel):
    """Áp ma trận quyền (store.perm.rule) lên model. Model con khai báo _perm_key() và _perm_key_vals(vals)."""
    _name = 'store.perm.mixin'
    _description = 'Áp ma trận quyền Checklist Audit'

    _perm_enforce_read = True  # False: chỉ chặn Thêm/Sửa/Xóa (model cấu hình, ai cũng cần đọc)
    _perm_manager_ops = ('unlink',)  # thao tác chỉ Quản lý khi user không có ma trận

    def _perm_key(self):
        raise NotImplementedError

    @api.model
    def _perm_key_vals(self, vals):
        raise NotImplementedError

    def _perm_is_manager(self):
        user = self.env.user
        return self.env.su or user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager')

    def _check_access(self, operation):
        res = super()._check_access(operation)
        if operation == 'read' and not self._perm_enforce_read:
            return res
        rights = self.env['store.perm.rule']._rights()
        if rights is None:
            if operation in self._perm_manager_ops and not self._perm_is_manager():
                return self, lambda: AccessError('Bạn không có quyền thực hiện thao tác này.')
            return res
        if self:
            # sudo: đọc audit_type không được gọi lại kiểm tra quyền (đệ quy)
            bad = self.browse(self.sudo().filtered(lambda r: not rights[r._perm_key()].get(operation)).ids)
        elif any(r.get(operation) for r in rights.values()):  # mức model: cần ít nhất một mục cho phép
            return res
        else:
            return self, lambda: AccessError('Bạn không có quyền này (ma trận phân quyền).')
        if not bad:
            return res
        if res:
            bad |= res[0]
        return bad, lambda: AccessError('Bạn không có quyền thực hiện thao tác này trên mục đã chọn (ma trận phân quyền).')

    @api.model_create_multi
    def create(self, vals_list):
        rights = self.env['store.perm.rule']._rights()
        if rights is not None:
            for vals in vals_list:
                if not rights[self._perm_key_vals(vals)]['create']:
                    raise AccessError('Bạn không có quyền Thêm ở mục này (ma trận phân quyền).')
        return super().create(vals_list)


class StorePermRule(models.Model):
    """Một dòng phân quyền: nhiều user dùng chung một ma trận Xem/Thêm/Sửa/Xóa theo từng mục con.
    User Checklist Audit không nằm trong dòng nào = không có quyền mục nào; Quản lý / Admin luôn đủ quyền.
    User nằm trong nhiều dòng thì quyền được cộng dồn."""
    _name = 'store.perm.rule'
    _description = 'Phân quyền mục con Checklist Audit'
    _order = 'group_label, id'

    group_label = fields.Char('Tên nhóm quyền')
    user_ids = fields.Many2many('res.users', 'store_perm_rule_users', 'rule_id', 'user_id', string='User')
    perms = fields.Json('Quyền', default=dict)  # {menu_key: {read, create, write, unlink}}

    @api.model
    def _rights(self):
        """{menu_key: {op: bool}} của người dùng hiện tại; None = không áp ma trận."""
        user = self.env.user
        if self.env.su or user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager'):
            return None
        rules = self.sudo().search([('user_ids', 'in', user.id)])
        if not rules:
            # user Checklist Audit chưa được gán nhóm phân quyền nào: ẩn toàn bộ (không còn dùng quyền theo nhóm hệ thống)
            if user.has_group('store_checklist.group_store_user'):
                return {key: {op: False for op in OPS} for key, _l, _f in MENUS}
            return None
        rights = {key: {op: any(perm_of(r.perms, key).get(op) for r in rules) for op in OPS} for key, _l, _f in MENUS}
        for op in OPS:  # 'nvbh' (phiếu / dữ liệu NVBH) mở khi có ít nhất một mục con NVBH
            rights['nvbh'][op] = rights['nvbh'][op] or any(rights[k][op] for k in NVBH_SUB_KEYS)
        return rights

    @api.model
    def check_export(self):
        """Chặn xuất Excel khi user có ma trận mà không mục nào cho phép."""
        rights = self._rights()
        if rights is not None and not any(r['export'] for r in rights.values()):
            raise AccessError('Bạn không có quyền xuất Excel.')

    @api.model
    def get_my_rights(self):
        return self._rights()

    def _manager_only(self):
        if not self.env.user.has_group('store_checklist.group_store_manager') and not self.env.is_admin():
            raise AccessError('Chỉ Quản lý mới được phân quyền.')

    @api.model
    def get_rules(self):
        self._manager_only()
        blank = {op: False for op in OPS}
        groups = [{'name': g.name, 'users': [{'id': u.id, 'name': u.name} for u in g.user_ids]}
                  for g in self.env['lug.group'].sudo().search([])] if 'lug.group' in self.env else []
        mgr = self.env.ref('store_checklist.group_store_manager')
        users = self.env['res.users'].sudo().search([('share', '=', False), ('id', 'not in', [1, 2])])
        return {
            'menus': [{'key': k, 'label': l, 'folder': f} for k, l, f in MENUS],
            'folders': [{'id': i, 'label': l} for i, l in FOLDERS],
            'groups': groups,
            'users': [{'id': u.id, 'name': u.name} for u in users.filtered(lambda u: mgr not in u.group_ids).sorted('name')],
            'rules': [{
                'id': r.id, 'group': r.group_label or '',
                'users': [{'id': u.id, 'name': u.name} for u in r.user_ids],
                'perms': {k: {**blank, **perm_of(r.perms, k)} for k, _l, _f in MENUS},
            } for r in self.sudo().search([])],
        }

    @api.model
    def save_rules(self, rules):
        """rules: danh sách đầy đủ [{id|0, group, user_ids, perms}]; dòng không còn trong danh sách bị xóa."""
        self._manager_only()
        keep = self.sudo().browse([r['id'] for r in rules if r.get('id')])
        (self.sudo().search([]) - keep).unlink()
        for r in rules:
            vals = {'group_label': r.get('group') or False, 'perms': r.get('perms') or {},
                    'user_ids': [(6, 0, r.get('user_ids') or [])]}
            if r.get('id'):
                self.sudo().browse(r['id']).write(vals)
            else:
                self.sudo().create(vals)
        return True
