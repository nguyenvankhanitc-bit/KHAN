from odoo import api, fields, models

from .store_audit_level import TONES


class StoreNvbhRating(models.Model):
    """Xếp loại checklist công việc NVBH (Cài đặt > Công việc checklist NVBH > Xếp loại): theo tỷ lệ điểm đạt / điểm chuẩn
    của nhân viên, dùng ở Danh sách checklist nhân viên."""
    _name = 'store.nvbh.rating'
    _inherit = 'store.perm.mixin'
    _description = 'Xếp loại checklist công việc NVBH'
    _order = 'min_score desc, id'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return 'nvbh_rating'

    @api.model
    def _perm_key_vals(self, vals):
        return 'nvbh_rating'

    name = fields.Char(string='Xếp loại', required=True)
    min_score = fields.Float(string='Từ điểm', required=True,
                             help='Tỷ lệ điểm tối thiểu (thang 100, % điểm đạt so với điểm chuẩn) để đạt xếp loại này.')
    score_range = fields.Char(string='Khoảng điểm', compute='_compute_score_range')
    tone = fields.Selection(TONES, string='Màu hiển thị', required=True, default='orange')

    @api.depends('min_score')
    def _compute_score_range(self):
        # mức nào cũng kéo dài tới ngay dưới mức cao hơn kế tiếp
        levels = self.search([], order='min_score asc')
        for rec in self:
            higher = levels.filtered(lambda l: l.min_score > rec.min_score)[:1]
            top = '%g' % (higher.min_score - 1) if higher else '100'
            rec.score_range = '%g - %s' % (rec.min_score, top) if rec.min_score < float(top) else '%g' % rec.min_score

    def action_open_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'views': [(False, 'form')], 'target': 'new', 'context': {'dialog_size': 'large'},
        }

    @api.model
    def rating_for(self, pct):
        """Xếp loại ứng với tỷ lệ điểm pct (0..100): mức có 'Từ điểm' lớn nhất không vượt pct."""
        levels = self.sudo().search([], order='min_score desc')
        return next((l for l in levels if pct >= l.min_score), levels[-1:] if levels else levels)
