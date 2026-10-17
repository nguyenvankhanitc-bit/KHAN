# -*- coding: utf-8 -*-
"""Cài đặt → Xếp loại hiệu suất / Xếp loại đạt: thang xếp loại do Quản lý (Administrator) tự sửa.

- kind = performance: Xếp loại hiệu suất (Báo cáo CV theo hạng mục, tên tự nhập).
- kind = eval: Xếp loại đạt — % Hoàn thành (QL đánh giá) → Đạt / Trung bình / Không đạt ở Kiểm tra CV.

Mỗi mức: Áp dụng (tích) · Từ % · Đến % (tự tính = Từ % của mức đang tích kế tiếp − 1) · Xếp loại.
Chỉ mức được tích «Áp dụng» mới dùng để xếp loại.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

KINDS = ("performance", "eval")
EVAL_RATINGS = [("pass", "Đạt"), ("average", "Trung bình"), ("fail", "Không đạt")]


class DailyTaskRatingTier(models.Model):
    _name = "daily.task.rating.tier"
    _description = "Xếp loại hiệu suất"
    _order = "from_percent, id"

    kind = fields.Selection(
        [("performance", "Xếp loại hiệu suất"), ("eval", "Xếp loại đạt")],
        string="Loại thang", required=True, default="performance", index=True,
    )
    rating_key = fields.Selection(EVAL_RATINGS, string="Kết quả (Xếp loại đạt)")
    apply = fields.Boolean(string="Áp dụng", default=True,
                           help="Tích để dùng mức này khi xếp loại hiệu suất. Bỏ tích = tạm bỏ mức.")
    from_percent = fields.Float(string="Từ %", required=True, default=0.0, digits=(5, 1))
    to_percent = fields.Float(string="Đến % (tự tính)", compute="_compute_to_percent", digits=(5, 1))
    to_label = fields.Char(string="Đến %", compute="_compute_to_percent")
    name = fields.Char(string="Xếp loại", required=True)

    @api.depends("from_percent", "apply", "kind")
    def _compute_to_percent(self):
        bounds_by_kind = {}
        for rec in self:
            kind = rec.kind or "performance"
            if kind not in bounds_by_kind:
                applied = self.sudo().search([("apply", "=", True), ("kind", "=", kind)])
                bounds_by_kind[kind] = sorted(set(applied.mapped("from_percent")))
            bounds = bounds_by_kind[kind]
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
    def _kind(self, kind):
        return kind if kind in KINDS else "performance"

    @api.model
    def get_tiers(self, kind="performance"):
        """Trang Xếp loại hiệu suất / Xếp loại đạt (client action có thanh bên)."""
        kind = self._kind(kind)
        tiers = self.sudo().search([("kind", "=", kind)], order="from_percent, id")
        return {
            "can_edit": self._can_edit_tiers(),
            "kind": kind,
            "ratings": [{"key": k, "label": l} for k, l in EVAL_RATINGS],
            "tiers": [
                {"id": t.id, "apply": t.apply, "from_percent": t.from_percent, "name": t.name or "",
                 "rating_key": t.rating_key or ""}
                for t in tiers
            ],
        }

    @api.model
    def save_tiers(self, rows, deleted_ids=None, kind="performance"):
        """Lưu cả bảng: cập nhật / thêm dòng, xoá dòng đã bỏ. Chỉ Quản lý."""
        kind = self._kind(kind)
        if not self._can_edit_tiers():
            raise AccessError("Chỉ Quản lý (Administrator) được sửa thang xếp loại.")
        Tier = self.sudo()
        labels = dict(EVAL_RATINGS)
        if deleted_ids:
            Tier.browse([int(i) for i in deleted_ids]).exists().filtered(lambda t: t.kind == kind).unlink()
        for row in rows or []:
            vals = {
                "kind": kind,
                "apply": bool(row.get("apply")),
                "from_percent": float(row.get("from_percent") or 0),
                "name": (row.get("name") or "").strip(),
            }
            if kind == "eval":
                key = row.get("rating_key") or ""
                if key not in labels:
                    raise ValidationError("Vui lòng chọn Xếp loại (Đạt / Trung bình / Không đạt) cho mọi dòng.")
                vals.update({"rating_key": key, "name": labels[key]})
            if not vals["name"]:
                raise ValidationError("Vui lòng nhập Xếp loại cho mọi dòng.")
            if row.get("id"):
                Tier.browse(int(row["id"])).exists().write(vals)
            else:
                Tier.create(vals)
        return True

    @api.model
    def _match(self, percent, kind):
        pct = float(percent or 0)
        tiers = self.sudo().search([("apply", "=", True), ("kind", "=", kind)], order="from_percent desc, id")
        for tier in tiers:
            if pct >= tier.from_percent:
                return tier
        return tiers[-1:]

    @api.model
    def rate(self, percent):
        """Xếp loại hiệu suất theo % (mức đang tích có «Từ %» lớn nhất ≤ percent)."""
        return self._match(percent, "performance").name or ""

    @api.model
    def rate_eval(self, percent):
        """Xếp loại đạt theo % Hoàn thành QL đánh giá → pass / average / fail ('' nếu chưa có thang)."""
        return self._match(percent, "eval").rating_key or ""
