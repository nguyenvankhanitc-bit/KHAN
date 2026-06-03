from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


MIEN_ACCESS_FIELDS = frozenset({'mien', 'ma_bo_phan_id'})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _search(
        self,
        domain,
        offset=0,
        limit=None,
        order=None,
        *,
        active_test=True,
        bypass_access=False,
    ):
        domain = self.env['hr.employee.access.mixin']._hr_employee_apply_access_domain(
            domain, model_name=self._name
        )
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        domain = self.env['hr.employee.access.mixin']._hr_employee_apply_access_domain(
            domain, model_name=self._name
        )
        return super().search_fetch(domain, field_names, offset, limit, order)

    def _get_id_hrm_duplicate(self, id_hrm):
        """Return another employee using the same ID HRM, or an empty recordset."""
        id_hrm = (id_hrm or '').strip()
        if not id_hrm:
            return self.env['hr.employee']
        domain = [('id_hrm', '=', id_hrm)]
        if self.ids:
            domain.append(('id', 'not in', self.ids))
        return self.env['hr.employee'].search(domain, limit=1)

    def _raise_id_hrm_duplicate_error(self, id_hrm, duplicate):
        id_hrm = (id_hrm or '').strip()
        raise ValidationError(
            _('ID HRM %s đã tồn tại cho nhân viên %s') % (id_hrm, duplicate.name)
        )

    @api.constrains('id_hrm')
    def _check_id_hrm_unique(self):
        for employee in self:
            id_hrm = (employee.id_hrm or '').strip()
            if not id_hrm:
                continue
            duplicate = employee._get_id_hrm_duplicate(id_hrm)
            if duplicate:
                employee._raise_id_hrm_duplicate_error(id_hrm, duplicate)

    @api.onchange('id_hrm')
    def _onchange_id_hrm_unique(self):
        id_hrm = (self.id_hrm or '').strip()
        if not id_hrm:
            return
        self.id_hrm = id_hrm
        duplicate = self._get_id_hrm_duplicate(id_hrm)
        if duplicate:
            self.id_hrm = False
            return {
                'warning': {
                    'title': _('ID HRM trùng'),
                    'message': _('ID HRM %s đã tồn tại cho nhân viên %s')
                    % (id_hrm, duplicate.name),
                },
            }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            id_hrm = (vals.get('id_hrm') or '').strip()
            if not id_hrm:
                continue
            vals['id_hrm'] = id_hrm
            duplicate = self._get_id_hrm_duplicate(id_hrm)
            if duplicate:
                vals['id_hrm'] = False
                self._raise_id_hrm_duplicate_error(id_hrm, duplicate)
        employees = super().create(vals_list)
        if any(MIEN_ACCESS_FIELDS & set(vals) for vals in vals_list):
            self.env.registry.clear_cache()
        return employees

    def write(self, vals):
        if 'id_hrm' in vals:
            id_hrm = (vals.get('id_hrm') or '').strip()
            vals = dict(vals, id_hrm=id_hrm or False)
            if id_hrm:
                for employee in self:
                    duplicate = employee._get_id_hrm_duplicate(id_hrm)
                    if duplicate:
                        vals['id_hrm'] = False
                        employee.id_hrm = False
                        employee._raise_id_hrm_duplicate_error(id_hrm, duplicate)
        res = super().write(vals)
        if MIEN_ACCESS_FIELDS & set(vals):
            # ir.rule domains are ormcache'd per uid; refresh when Miền scope changes.
            self.env.registry.clear_cache()
        return res

    # Regional and ID Information
    mien = fields.Selection([
        ('Bắc', 'Bắc'),
        ('Nam', 'Nam'),
        ('ĐTT', 'ĐTT'),
        ('VP', 'VP'),
    ], string='Miền', groups='hr.group_hr_user')
    id_hrm = fields.Char(string='ID HRM', groups='hr.group_hr_user')

    # Accounting and Attendance Codes
    ma_nv_ke_toan = fields.Char(string='Mã NV kế toán', groups='hr.group_hr_user')
    ma_cham_cong = fields.Char(string='Mã chấm công', groups='hr.group_hr_user')

    # Name without diacritics
    ten_khong_dau = fields.Char(string='Tên không dấu', groups='hr.group_hr_user')

    # Employee Status
    trang_thai_nhan_vien = fields.Selection([
        ('active', 'Đang làm việc'),
        ('probation', 'Thử việc'),
        ('leave', 'Nghỉ phép'),
        ('terminated', 'Đã nghỉ việc'),
    ], string='Trạng thái nhân viên', default='active', groups='hr.group_hr_user')

    # Department Information
    ma_bo_phan_id = fields.Many2one(
        'hr.store.code',
        string='Mã bộ phận',
        groups='hr.group_hr_user',
    )
    ma_bo_phan = fields.Char(
        string='Mã bộ phận (mã)',
        related='ma_bo_phan_id.code',
        store=True,
        readonly=False,
        groups='hr.group_hr_user',
    )

    def _get_ma_bo_phan_domain(self):
        if self.mien:
            return [('mien', '=', self.mien)]
        return []

    @api.onchange('mien')
    def _onchange_mien_ma_bo_phan(self):
        if self.ma_bo_phan_id and self.mien and self.ma_bo_phan_id.mien != self.mien:
            self.ma_bo_phan_id = False
        return {'domain': {'ma_bo_phan_id': self._get_ma_bo_phan_domain()}}

    @api.constrains('mien', 'ma_bo_phan_id')
    def _check_ma_bo_phan_mien(self):
        for employee in self:
            if (
                employee.mien
                and employee.ma_bo_phan_id
                and employee.ma_bo_phan_id.mien
                and employee.ma_bo_phan_id.mien != employee.mien
            ):
                raise ValidationError(
                    _('Mã bộ phận %s không thuộc miền %s')
                    % (employee.ma_bo_phan_id.code, employee.mien)
                )

    ten_bo_phan = fields.Char(string='Tên bộ phận', groups='hr.group_hr_user')
    bp_ke_toan = fields.Char(string='BP Kế toán', groups='hr.group_hr_user')

    # Banking Information
    so_tai_khoan = fields.Char(string='Số tài khoản', groups='hr.group_hr_user')
    chi_nhanh_ngan_hang = fields.Char(string='Chi nhánh NH', groups='hr.group_hr_user')

    # Position Details
    ma_chuc_vu = fields.Char(string='Mã chức vụ', groups='hr.group_hr_user')
    cap_tai = fields.Char(string='Cấp tại', groups='hr.group_hr_user')

    # Additional Address
    dia_chi_tam_tru = fields.Char(string='Địa chỉ tạm trú', groups='hr.group_hr_user')

    # Personal Background
    trinh_do = fields.Selection([
        ('secondary', 'Trung học cơ sở'),
        ('high_school', 'Trung học phổ thông'),
        ('intermediate', 'Trung cấp'),
        ('college', 'Cao đẳng'),
        ('bachelor', 'Đại học'),
        ('master', 'Thạc sĩ'),
        ('doctorate', 'Tiến sĩ'),
    ], string='Trình độ', groups='hr.group_hr_user')
    ton_giao = fields.Char(string='Tôn giáo', groups='hr.group_hr_user')
    dan_toc = fields.Char(string='Dân tộc', groups='hr.group_hr_user')
    nguyen_quan = fields.Char(string='Nguyên quán', groups='hr.group_hr_user')

    # Social Insurance
    so_so_bhxh = fields.Char(string='Số sổ BHXH', groups='hr.group_hr_user')
    ngay_tham_gia_bhxh = fields.Date(string='Ngày tham gia BHXH', groups='hr.group_hr_user')

    # Tax Information
    ma_so_thue = fields.Char(string='Mã số thuế', groups='hr.group_hr_user')

    # Employment Dates
    ngay_vao_lam = fields.Date(string='Ngày vào làm', groups='hr.group_hr_user')
    ngay_nghi_viec = fields.Date(string='Ngày nghỉ việc', groups='hr.group_hr_user')
    ngay_chinh_thuc = fields.Date(string='Ngày chính thức', groups='hr.group_hr_user')

    # Recruitment and Notes
    nguon_tuyen_dung = fields.Char(string='Nguồn tuyển dụng', groups='hr.group_hr_user')
    ghi_chu = fields.Text(string='Ghi chú', groups='hr.group_hr_user')

    # Former Employee Flag
    nhan_vien_cu = fields.Boolean(string='Nhân viên cũ', default=False, groups='hr.group_hr_user')
