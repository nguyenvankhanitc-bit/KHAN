# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.osv import expression

from .lug_menu_permission import MENU_PARENT, OP_TO_FLAG


REGION_TO_MENU = {
    "north": "schedule_north",
    "south": "schedule_south",
    "dtt": "schedule_dtt",
}


class LugMenuAccessMixin(models.AbstractModel):
    """Áp quyền Xem/Thêm/Sửa/Xóa menu con LinkQ ERP lên model."""

    _name = "lug.menu.access.mixin"
    _description = "Mixin phân quyền menu LinkQ ERP"

    _linkq_menu_key = False

    def _linkq_bypass(self):
        user = self.env.user
        return bool(
            self.env.su
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
            or user.has_group("lug_phan_he.group_phan_he_service_manager")
            or user.has_group("lug_phan_he.group_linkq_manager")
        )

    def _linkq_matrix_applies(self):
        return bool(
            self.env["phan.he.module.access"].sudo().search(
                [
                    ("user_ids", "in", self.env.user.id),
                    ("company_id", "=", self.env.company.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )

    def _linkq_menu_rights(self):
        return self.env["phan.he.module.access"].get_user_linkq_menu_rights()

    def _linkq_keys_for_model(self):
        if self._linkq_menu_key:
            return [self._linkq_menu_key]
        if "region" in self._fields:
            return list(REGION_TO_MENU.values())
        return []

    def _linkq_key_for_record(self, rec):
        if rec._linkq_menu_key:
            return rec._linkq_menu_key
        region = getattr(rec, "region", False)
        return REGION_TO_MENU.get(region)

    def _linkq_key_from_vals(self, vals):
        if self._linkq_menu_key:
            return self._linkq_menu_key
        region = vals.get("region") or self.env.context.get("default_region")
        return REGION_TO_MENU.get(region)

    def _linkq_flag(self, menu_key, operation):
        if not menu_key:
            return False
        flag = OP_TO_FLAG.get(operation)
        row = self._linkq_menu_rights().get(menu_key) or {}
        if operation == "read" and self._name in (
            "linkq.shift.code",
            "phan.he.work.shift",
        ):
            # xếp ca / lịch miền cần đọc ký hiệu công để hiện Many2one
            rights = self._linkq_menu_rights()
            if row.get("read"):
                return True
            if (rights.get("schedule_main") or {}).get("read"):
                return True
            if any(
                (rights.get(k) or {}).get("read")
                for k in ("schedule_north", "schedule_south", "schedule_dtt")
            ):
                return True
            return False
        return bool(row.get(flag)) or (
            bool(MENU_PARENT.get(menu_key))
            and bool((self._linkq_menu_rights().get(MENU_PARENT.get(menu_key)) or {}).get(flag))
        )

    def _linkq_model_allows(self, operation):
        keys = self._linkq_keys_for_model()
        if not keys:
            return True
        return any(self._linkq_flag(key, operation) for key in keys)

    def _linkq_record_domain(self, operation):
        # Model gắn 1 menu (lịch xếp ca, ký hiệu công): không lọc theo miền.
        if self._linkq_menu_key:
            if self._linkq_model_allows(operation):
                return []
            return [("id", "=", 0)]
        if "region" not in self._fields:
            if self._linkq_model_allows(operation):
                return []
            return [("id", "=", 0)]
        regions = [
            region
            for region, key in REGION_TO_MENU.items()
            if self._linkq_flag(key, operation)
        ]
        if not regions:
            return [("id", "=", 0)]
        return [("region", "in", regions)]

    def _linkq_access_error(self, operation, records=None):
        labels = {
            "read": "Xem",
            "create": "Thêm",
            "write": "Sửa",
            "unlink": "Xóa",
        }
        return AccessError(
            "Bạn không có quyền %s trên menu LinkQ ERP tương ứng."
            % labels.get(operation, operation)
        )

    def _check_access(self, operation):
        if self.env.su or self._linkq_bypass():
            return super()._check_access(operation)

        if self._linkq_matrix_applies():
            if not self._linkq_model_allows(operation):
                return self, lambda: self._linkq_access_error(operation, self)

            forbidden = self.browse()
            for rec in self:
                if not isinstance(rec.id, int):
                    continue
                key = self._linkq_key_for_record(rec)
                if key and not self._linkq_flag(key, operation):
                    forbidden |= rec
            if forbidden:
                return forbidden, lambda: self._linkq_access_error(operation, forbidden)
            return super()._check_access(operation)

        if self._name in ("linkq.monthly.roster", "linkq.monthly.roster.line") and not self.env.user.has_group(
            "lug_phan_he.group_linkq_schedule_user"
        ):
            return self, lambda: self._linkq_access_error(operation, self)
        return super()._check_access(operation)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        if (
            not self.env.su
            and not kwargs.get("bypass_access")
            and not self._linkq_bypass()
            and self._linkq_matrix_applies()
        ):
            extra = self._linkq_record_domain("read")
            if extra:
                domain = expression.AND([extra, domain or []])
        return super()._search(
            domain, offset=offset, limit=limit, order=order, **kwargs
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self._linkq_bypass() and self._linkq_matrix_applies():
            for vals in vals_list:
                key = self._linkq_key_from_vals(vals)
                if key and not self._linkq_flag(key, "create"):
                    raise self._linkq_access_error("create")
                if not key and not self._linkq_model_allows("create"):
                    raise self._linkq_access_error("create")
        return super().create(vals_list)
