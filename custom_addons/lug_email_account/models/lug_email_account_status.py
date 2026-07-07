# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LugEmailAccountStatus(models.Model):
    _name = "lug.email.account.status"
    _description = "Trạng thái tài khoản email"
    _order = "sequence, name"

    name = fields.Char(string="Tên trạng thái", required=True, translate=True)
    code = fields.Char(
        string="Mã",
        required=True,
        index=True,
        help="Mã kỹ thuật, dùng khi import (vd: active, lock, cancel).",
    )
    sequence = fields.Integer(default=10)
    badge_style = fields.Selection(
        [
            ("success", "Xanh lá"),
            ("warning", "Vàng"),
            ("danger", "Đỏ"),
            ("info", "Xanh dương"),
            ("secondary", "Xám"),
        ],
        string="Màu hiển thị",
        default="success",
        required=True,
    )
    is_closed = fields.Boolean(
        string="Trạng thái đóng",
        help="Bản ghi ở trạng thái này sẽ hiển thị mờ trên danh sách.",
    )
    active = fields.Boolean(default=True)
    account_count = fields.Integer(compute="_compute_account_count")

    _code_unique = models.Constraint(
        "unique(code)",
        "Mã trạng thái phải là duy nhất.",
    )

    @api.depends("code")
    def _compute_account_count(self):
        data = self.env["lug.email.account"]._read_group(
            [("status_id", "in", self.ids)],
            ["status_id"],
            ["__count"],
        )
        mapped = {status.id: count for status, count in data}
        for record in self:
            record.account_count = mapped.get(record.id, 0)

    @api.model
    def _generate_code(self, name):
        normalized = unicodedata.normalize("NFKD", name or "")
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        code = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
        return code or "status"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") and vals.get("name"):
                base_code = self._generate_code(vals["name"])
                code = base_code
                index = 1
                while self.search_count([("code", "=", code)]):
                    index += 1
                    code = f"{base_code}_{index}"
                vals["code"] = code
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_used(self):
        for record in self:
            if self.env["lug.email.account"].search_count([("status_id", "=", record.id)]):
                raise UserError(
                    _("Không thể xóa trạng thái '%s' vì đang được sử dụng.")
                    % record.name
                )

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if not (record.code or "").strip():
                raise ValidationError(_("Mã trạng thái không được để trống."))
