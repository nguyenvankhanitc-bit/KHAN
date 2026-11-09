# -*- coding: utf-8 -*-
from odoo import models


class HrStore(models.Model):
    _inherit = 'hr.store'

    # Cho phép gõ mã cửa hàng (vd: LUG_KDV) hoặc tên khi chọn cửa hàng.
    _rec_names_search = ['name', 'code']
