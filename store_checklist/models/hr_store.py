# -*- coding: utf-8 -*-
from odoo import models


class HrStore(models.Model):
    _inherit = 'hr.store'

    # Cho phép gõ mã cửa hàng (vd: LUG_KDV) hoặc tên khi chọn cửa hàng.
    _rec_names_search = ['name', 'code']

    def web_read(self, specification):
        """Người dùng không được xem hồ sơ nhân viên của quản lý cửa hàng thì web_read báo KeyError
        (module hr_employee_self_only). Tên quản lý chỉ là nhãn của cửa hàng nên đọc bằng sudo."""
        if 'manager_id' not in specification:
            return super().web_read(specification)
        res = super().web_read({k: v for k, v in specification.items() if k != 'manager_id'})
        for vals in res:
            mgr = self.browse(vals['id']).sudo().manager_id
            vals['manager_id'] = {'id': mgr.id, 'display_name': mgr.display_name} if mgr else False
        return res
