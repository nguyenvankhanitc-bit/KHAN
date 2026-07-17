# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyWorkNotebook(models.Model):
    _name = "daily.work.notebook"
    _description = "Sổ tay khách hàng"
    _order = "name asc, id asc"

    name = fields.Char(string="Tên khách hàng", required=True, index=True)
    company = fields.Char(string="Công ty")
    contact_name = fields.Char(string="Người liên hệ")
    phone = fields.Char(string="Số điện thoại")
    email = fields.Char(string="Email")
    address = fields.Char(string="Địa chỉ")
    note = fields.Text(string="Ghi chú")
    user_id = fields.Many2one(
        "res.users",
        string="Người sở hữu",
        default=lambda self: self.env.user,
        required=True,
        index=True,
        ondelete="cascade",
    )
    color = fields.Integer(string="Màu icon", default=1)

    @api.constrains("email")
    def _check_email(self):
        for rec in self:
            mail = (rec.email or "").strip()
            if mail and "@" not in mail:
                raise ValidationError("Email không hợp lệ: %s" % mail)

    @api.model
    def get_notebook_data(self, search=None):
        """Danh sách sổ tay của user đang đăng nhập."""
        domain = [("user_id", "=", self.env.user.id)]
        q = (search or "").strip()
        if q:
            domain += [
                "|",
                "|",
                "|",
                "|",
                "|",
                ("name", "ilike", q),
                ("company", "ilike", q),
                ("contact_name", "ilike", q),
                ("phone", "ilike", q),
                ("email", "ilike", q),
                ("address", "ilike", q),
            ]
        records = self.search(domain, order="name asc, id asc")
        rows = []
        for idx, rec in enumerate(records, start=1):
            rows.append(
                {
                    "id": rec.id,
                    "stt": idx,
                    "name": rec.name or "",
                    "company": rec.company or "",
                    "contact_name": rec.contact_name or "",
                    "phone": rec.phone or "",
                    "email": rec.email or "",
                    "address": rec.address or "",
                    "note": rec.note or "",
                    "color": rec.color or 1,
                }
            )
        return {
            "user_name": self.env.user.name or "",
            "rows": rows,
            "total": len(rows),
        }

    @api.model
    def save_notebook_row(self, vals):
        """Tạo / cập nhật một dòng sổ tay (chỉ của mình)."""
        vals = dict(vals or {})
        rid = int(vals.pop("id", 0) or 0)
        clean = {
            "name": (vals.get("name") or "").strip(),
            "company": (vals.get("company") or "").strip() or False,
            "contact_name": (vals.get("contact_name") or "").strip() or False,
            "phone": (vals.get("phone") or "").strip() or False,
            "email": (vals.get("email") or "").strip() or False,
            "address": (vals.get("address") or "").strip() or False,
            "note": (vals.get("note") or "").strip() or False,
            "color": int(vals.get("color") or 1),
            "user_id": self.env.user.id,
        }
        if not clean["name"]:
            raise ValidationError("Vui lòng nhập Tên khách hàng.")
        if rid:
            rec = self.browse(rid).exists()
            if not rec or rec.user_id != self.env.user:
                raise ValidationError("Không tìm thấy dòng sổ tay hoặc bạn không có quyền sửa.")
            rec.write(clean)
            return rec.id
        return self.create(clean).id

    def delete_notebook_row(self):
        for rec in self:
            if rec.user_id != self.env.user and not self.env.user.has_group(
                "daily_work_task.group_daily_work_manager"
            ):
                raise ValidationError("Bạn chỉ được xóa sổ tay của chính mình.")
        self.unlink()
        return True
