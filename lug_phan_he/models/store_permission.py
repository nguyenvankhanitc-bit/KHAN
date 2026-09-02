# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PhanHeModuleAccessStorePerm(models.Model):
    _inherit = "phan.he.module.access"

    store_permission_ids = fields.One2many(
        "linkq.store.permission.line",
        "permission_group_id",
        string="Phân quyền Cửa hàng",
        copy=True,
    )


class LinkqStorePermissionLine(models.Model):
    _name = "linkq.store.permission.line"
    _description = "Chi tiết phân quyền cửa hàng (Lịch ca & Nhân sự)"
    _order = "sequence, id"

    sequence = fields.Integer(string="Thứ tự", default=10)
    stt_display = fields.Integer(string="STT", compute="_compute_stt")
    permission_group_id = fields.Many2one(
        "phan.he.module.access",
        string="Nhóm quyền",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Người dùng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    can_view = fields.Boolean(string="Phân quyền xem", default=True)
    type_scope = fields.Selection(
        [
            ("all", "Tất cả cửa hàng"),
            ("region", "Theo khu vực"),
            ("custom", "Cửa hàng chỉ định"),
        ],
        string="Phạm vi xem",
        default="all",
        required=True,
    )
    region = fields.Selection(
        [
            ("Bắc", "Miền Bắc"),
            ("Nam", "Miền Nam"),
            ("ĐTT", "Miền ĐTT"),
            ("VP", "VP"),
        ],
        string="Khu vực / Miền",
    )
    store_ids = fields.Many2many(
        "hr.store",
        "linkq_store_perm_line_hr_store_rel",
        "line_id",
        "store_id",
        string="Danh sách cửa hàng",
    )
    store_display_text = fields.Char(
        string="Cửa hàng được xem",
        compute="_compute_store_display_text",
        store=True,
    )

    _sql_constraints = [
        (
            "user_group_uniq",
            "unique(permission_group_id, user_id)",
            "Mỗi user chỉ được khai báo một dòng trong nhóm quyền này.",
        ),
    ]

    @api.depends("permission_group_id", "permission_group_id.store_permission_ids")
    def _compute_stt(self):
        for rec in self:
            rec.stt_display = 0
        for parent in self.mapped("permission_group_id"):
            for idx, line in enumerate(parent.store_permission_ids, start=1):
                line.stt_display = idx

    @api.depends("can_view", "type_scope", "store_ids", "region")
    def _compute_store_display_text(self):
        Store = self.env["hr.store"].sudo()
        total = Store.search_count([])
        for rec in self:
            if not rec.can_view:
                rec.store_display_text = "—"
            elif rec.type_scope == "all":
                rec.store_display_text = "Tất cả cửa hàng (%s)" % total
            elif rec.type_scope == "region" and rec.region:
                n = Store.search_count([("mien", "=", rec.region)])
                labels = dict(rec._fields["region"].selection)
                rec.store_display_text = "%s (%s cửa hàng)" % (labels.get(rec.region, rec.region), n)
            elif rec.type_scope == "custom" and rec.store_ids:
                codes = [s.code or s.name for s in rec.store_ids if (s.code or s.name)]
                rec.store_display_text = ", ".join(codes)
            else:
                rec.store_display_text = "—"

    @api.constrains("can_view", "type_scope", "region", "store_ids")
    def _check_scope(self):
        for rec in self:
            if not rec.can_view:
                continue
            if rec.type_scope == "region" and not rec.region:
                raise ValidationError("Chọn khu vực / miền khi phạm vi là Theo khu vực.")
            if rec.type_scope == "custom" and rec.can_view and not rec.store_ids:
                raise ValidationError("Chọn ít nhất một cửa hàng khi phạm vi là Cửa hàng chỉ định.")

    @api.onchange("type_scope")
    def _onchange_type_scope(self):
        if self.type_scope != "custom":
            self.store_ids = False
        if self.type_scope != "region":
            self.region = False

    def action_open_store_detail(self):
        self.ensure_one()
        view = self.env.ref(
            "lug_phan_he.view_linkq_store_permission_line_form",
            raise_if_not_found=False,
        )
        return {
            "name": "Chỉnh sửa phân quyền cửa hàng: %s" % (self.user_id.name or ""),
            "type": "ir.actions.act_window",
            "res_model": "linkq.store.permission.line",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")] if view else [(False, "form")],
            "target": "new",
        }

    def _sync_user_linkq_stores(self):
        users = self.mapped("user_id")
        if users:
            users._compute_linkq_store()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_user_linkq_stores()
        return records

    def write(self, vals):
        old_users = self.mapped("user_id")
        res = super().write(vals)
        (old_users | self.mapped("user_id"))._compute_linkq_store()
        return res

    def unlink(self):
        users = self.mapped("user_id")
        res = super().unlink()
        if users:
            users._compute_linkq_store()
        return res
