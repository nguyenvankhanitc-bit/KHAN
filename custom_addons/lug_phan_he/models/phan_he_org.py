# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PhanHeMien(models.Model):
    _name = "phan.he.mien"
    _description = "Miền"
    _order = "sequence, name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(string="Tên miền", required=True)
    code = fields.Char(string="Mã", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    area_ids = fields.One2many("phan.he.area", "mien_id", string="Khu vực")
    store_ids = fields.One2many("phan.he.store", "mien_id", string="Cửa hàng")
    area_count = fields.Integer(compute="_compute_counts")
    store_count = fields.Integer(compute="_compute_counts")
    note = fields.Text(string="Ghi chú")

    _code_uniq = models.Constraint("unique(code)", "Mã miền phải duy nhất.")

    def _compute_counts(self):
        for rec in self:
            rec.area_count = len(rec.area_ids)
            rec.store_count = len(rec.store_ids)


class PhanHeArea(models.Model):
    _name = "phan.he.area"
    _description = "Khu vực"
    _order = "mien_id, sequence, name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(string="Tên khu vực", required=True)
    code = fields.Char(string="Mã", required=True)
    sequence = fields.Integer(default=10)
    mien_id = fields.Many2one(
        "phan.he.mien",
        string="Miền",
        required=True,
        ondelete="restrict",
        index=True,
    )
    active = fields.Boolean(default=True)
    store_ids = fields.One2many("phan.he.store", "area_id", string="Cửa hàng")
    store_count = fields.Integer(compute="_compute_store_count")
    manager_ids = fields.Many2many(
        "res.users",
        "phan_he_area_manager_rel",
        "area_id",
        "user_id",
        string="Area Manager",
    )
    note = fields.Text(string="Ghi chú")

    _code_uniq = models.Constraint("unique(code)", "Mã khu vực phải duy nhất.")

    def _compute_store_count(self):
        for rec in self:
            rec.store_count = len(rec.store_ids)

    @api.depends("name", "mien_id")
    def _compute_display_name(self):
        for rec in self:
            if rec.mien_id:
                rec.display_name = f"{rec.mien_id.name} / {rec.name}"
            else:
                rec.display_name = rec.name or ""
