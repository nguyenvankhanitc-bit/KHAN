from odoo import fields, models


class StoreStore(models.Model):
    _name = 'store.store'
    _description = 'Cửa hàng / Gian hàng'
    _order = 'code'

    name = fields.Char(string='Tên cửa hàng', required=True)
    code = fields.Char(string='Mã cửa hàng', required=True, copy=False)
    address = fields.Text(string='Địa chỉ / TTTM')
    province = fields.Char(string='Tỉnh / Thành phố')
    area = fields.Float(string='Diện tích (m²)')
    manager = fields.Char(string='Quản lý gian hàng')
    phone = fields.Char(string='Số điện thoại')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'Mã cửa hàng phải là duy nhất!')
