# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import AccessError

from .phan_he_module_access import SERVICE_NAME_MAP


OPERATION_TO_PERM = {
    "read": "view",
    "create": "create",
    "write": "edit",
    "unlink": "delete",
}


class PhanHeAccessMixin(models.AbstractModel):
    """Ép quyền Xem/Thêm/Sửa/Xóa theo nhóm phân hệ dịch vụ."""

    _name = "phan.he.access.mixin"
    _description = "Mixin phân quyền phân hệ dịch vụ"

    def _phan_he_bypass_matrix(self):
        user = self.env.user
        return bool(
            self.env.su
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
        )

    def _phan_he_user_in_access_group(self):
        return bool(
            self.env["phan.he.module.access"].sudo().search([
                ("user_ids", "in", self.env.user.id),
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
            ], limit=1)
        )

    def _phan_he_service_code(self):
        """Override trên model cụ thể — trả mã dịch vụ của record."""
        self.ensure_one()
        return False

    @api.model
    def _phan_he_service_code_from_vals(self, vals):
        return False

    def _phan_he_make_access_error(self, operation, records=None):
        perm = OPERATION_TO_PERM.get(operation, operation)
        label = {
            "view": "Xem",
            "create": "Thêm",
            "edit": "Sửa",
            "delete": "Xóa",
        }.get(perm, perm)
        names = []
        for rec in (records or self)[:3]:
            code = rec._phan_he_service_code() if rec else False
            names.append(SERVICE_NAME_MAP.get(code, code or "?"))
        detail = ", ".join(names) if names else "dịch vụ"
        return AccessError(
            "Bạn chỉ được cấp quyền xem hoặc chưa được cấp quyền %s trên: %s."
            % (label, detail)
        )

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        if self._phan_he_bypass_matrix():
            return None
        # Chưa gán vào nhóm phân quyền → giữ ACL Odoo cũ
        if not self._phan_he_user_in_access_group():
            return None

        perm_key = OPERATION_TO_PERM.get(operation)
        if not perm_key:
            return None

        rights = self.env["phan.he.module.access"].get_user_module_rights()

        # create / check trên empty recordset
        if not self:
            if operation == "create":
                if any(r.get("create") for r in rights.values()):
                    return None

                def _raise_create():
                    raise self._phan_he_make_access_error(operation, self)

                return self, _raise_create
            return None

        forbidden = self.browse()
        for rec in self:
            code = (rec._phan_he_service_code() or "").lower()
            row = rights.get(code) or {}
            if not row.get(perm_key):
                forbidden |= rec
        if forbidden:

            def _raise_forbidden():
                raise self._phan_he_make_access_error(operation, forbidden)

            return forbidden, _raise_forbidden
        return None

    @api.model_create_multi
    def create(self, vals_list):
        if not self._phan_he_bypass_matrix() and self._phan_he_user_in_access_group():
            rights = self.env["phan.he.module.access"].get_user_module_rights()
            for vals in vals_list:
                code = (self._phan_he_service_code_from_vals(vals) or "").lower()
                row = rights.get(code) or {}
                if code and not row.get("create"):
                    raise AccessError(
                        "Bạn không có quyền Thêm trên phân hệ '%s'."
                        % SERVICE_NAME_MAP.get(code, code)
                    )
        return super().create(vals_list)
