# -*- coding: utf-8 -*-
"""Cài đặt → Xếp loại hiệu suất: thang xếp loại do Quản lý (Administrator) tự sửa.

Mỗi mức: Áp dụng (tích) · Từ % · Đến % (tự tính = Từ % của mức đang tích kế tiếp − 1) · Xếp loại.
Chỉ mức được tích «Áp dụng» mới dùng để xếp loại.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTaskRatingTier(models.Model):
    _name = "daily.task.rating.tier"
    _description = "Xếp loại hiệu suất"
    _order = "from_percent, id"

    apply = fields.Boolean(string="Áp dụng", default=True,
                           help="Tích để dùng mức này khi xếp loại hiệu suất. Bỏ tích = tạm bỏ mức.")
    from_percent = fields.Float(string="Từ %", required=True, default=0.0, digits=(5, 1))
    to_percent = fields.Float(string="Đến % (tự tính)", compute="_compute_to_percent", digits=(5, 1))
    to_label = fields.Char(string="Đến %", compute="_compute_to_percent")
    name = fields.Char(string="Xếp loại", required=True)

    @api.depends("from_percent", "apply")
    def _compute_to_percent(self):
        applied = self.search([("apply", "=", True)], order="from_percent, id")
        bounds = sorted(set(applied.mapped("from_percent")))
        for rec in self:
            if not rec.apply:
                rec.to_percent = 0.0
                rec.to_label = "—"
                continue
            higher = [b for b in bounds if b > rec.from_percent]
            to = (higher[0] - 1) if higher else 100.0
            rec.to_percent = max(to, rec.from_percent)
            rec.to_label = "%s%%" % ("%g" % rec.to_percent)

    @api.constrains("from_percent")
    def _check_from_percent(self):
        for rec in self:
            if rec.from_percent < 0 or rec.from_percent > 100:
                raise ValidationError("«Từ %» phải nằm trong khoảng 0 – 100.")

    @api.model
    def _can_edit_tiers(self):
        return self.env.su or self.env.user.has_group("daily_work_task.group_daily_work_manager")

    @api.model
    def get_tiers(self):
        """Trang Xếp loại hiệu suất (client action có thanh bên)."""
        tiers = self.sudo().search([], order="from_percent, id")
        return {
            "can_edit": self._can_edit_tiers(),
            "tiers": [
                {"id": t.id, "apply": t.apply, "from_percent": t.from_percent, "name": t.name or ""}
                for t in tiers
            ],
        }

    @api.model
    def save_tiers(self, rows, deleted_ids=None):
        """Lưu cả bảng: cập nhật / thêm dòng, xoá dòng đã bỏ. Chỉ Quản lý."""
        if not self._can_edit_tiers():
            raise AccessError("Chỉ Quản lý (Administrator) được sửa Xếp loại hiệu suất.")
        Tier = self.sudo()
        if deleted_ids:
            Tier.browse([int(i) for i in deleted_ids]).exists().unlink()
        for row in rows or []:
            vals = {
                "apply": bool(row.get("apply")),
                "from_percent": float(row.get("from_percent") or 0),
                "name": (row.get("name") or "").strip(),
            }
            if not vals["name"]:
                raise ValidationError("Vui lòng nhập Xếp loại cho mọi dòng.")
            if row.get("id"):
                Tier.browse(int(row["id"])).exists().write(vals)
            else:
                Tier.create(vals)
        return True

    @api.model
    def rate(self, percent):
        """Xếp loại theo % (mức đang tích có «Từ %» lớn nhất ≤ percent)."""
        pct = float(percent or 0)
        tiers = self.sudo().search([("apply", "=", True)], order="from_percent desc, id")
        for tier in tiers:
            if pct >= tier.from_percent:
                return tier.name
        return tiers[-1:].name or ""
