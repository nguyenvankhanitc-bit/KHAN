# -*- coding: utf-8 -*-
# Model giữ lại sau lần implement mẫu; UI cây nằm trên tab
# phan.he.module.access → Phân quyền Menu LinkQ ERP.

from odoo import fields, models


class LinkqMenuAccess(models.Model):
    _name = "linkq.menu.access"
    _description = "Phân quyền Menu LinkQ ERP"
    _order = "sequence, id"

    name = fields.Char(string="Tên Menu", required=True)
    sequence = fields.Integer(default=10)
    menu_key = fields.Char(index=True)
    group_id = fields.Many2one("res.groups", string="Nhóm quyền", ondelete="cascade")
    parent_id = fields.Many2one("linkq.menu.access", string="Menu cha", ondelete="cascade")
    child_ids = fields.One2many("linkq.menu.access", "parent_id", string="Menu con")
    item_type = fields.Selection(
        [
            ("folder", "Thư mục"),
            ("file", "Trang chức năng"),
            ("action", "Hành động đặc thù"),
        ],
        default="file",
    )
    perm_read = fields.Boolean(string="XEM", default=False)
    perm_write = fields.Boolean(string="SỬA", default=False)
    perm_create = fields.Boolean(string="THÊM", default=False)
    perm_unlink = fields.Boolean(string="XÓA", default=False)
    perm_admin = fields.Boolean(string="QUẢN TRỊ", default=False)
    has_read = fields.Boolean(default=True)
    has_create = fields.Boolean(default=True)
    has_write = fields.Boolean(default=True)
    has_unlink = fields.Boolean(default=True)
    has_admin = fields.Boolean(default=True)
