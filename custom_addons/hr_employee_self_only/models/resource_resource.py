# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.exceptions import AccessError

from .hr_employee_privacy import (
    _privacy_is_employee_edit_forbidden,
    _privacy_raise_if_hr_employee_resource_no_write,
)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if _privacy_is_employee_edit_forbidden(self.env):
            linked = records.filtered(lambda r: r.employee_id)
            if linked:
                linked.sudo().unlink()
                raise AccessError(_("Bạn không có quyền chỉnh sửa hồ sơ nhân viên."))
        return records

    def write(self, vals):
        _privacy_raise_if_hr_employee_resource_no_write(self.env, self)
        return super().write(vals)

    def unlink(self):
        _privacy_raise_if_hr_employee_resource_no_write(self.env, self)
        return super().unlink()
