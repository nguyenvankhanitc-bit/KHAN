from odoo import api, fields, models

from .store_audit_template import AUDIT_TYPES

TONES = [('green', 'Xanh lá'), ('blue', 'Xanh dương'), ('orange', 'Cam'), ('red', 'Đỏ'), ('darkred', 'Đỏ đậm')]


class StoreAuditLevel(models.Model):
    _name = 'store.audit.level'
    _inherit = 'store.perm.mixin'
    _perm_enforce_read = False
    _perm_manager_ops = ('create', 'write', 'unlink')

    def _perm_key(self):
        return ('gs_' if self.audit_type == 'gs' else '') + 'level'

    @api.model
    def _perm_key_vals(self, vals):
        return ('gs_' if (vals.get('audit_type') or 'nvbh') == 'gs' else '') + 'level'

    _description = 'Mức đánh giá'
    _order = 'min_score desc, id'

    name = fields.Char(string='Mức đánh giá', required=True)
    min_score = fields.Float(string='Từ điểm', required=True,
                             help='Điểm tối thiểu để đạt mức này, tính theo thang 100 (tỷ lệ % so với điểm chuẩn).')
    score_range = fields.Char(string='Khoảng điểm', compute='_compute_score_range')
    audit_type = fields.Selection(AUDIT_TYPES, string='Loại checklist', required=True, default='nvbh')
    tone = fields.Selection(TONES, string='Màu hiển thị', required=True, default='orange')

    @api.depends('min_score', 'audit_type')
    def _compute_score_range(self):
        # mức nào cũng kéo dài tới ngay dưới mức cao hơn kế tiếp
        for rec in self:
            levels = self.search([('audit_type', '=', rec.audit_type)], order='min_score asc')
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
    def level_for(self, pct, audit_type='nvbh'):
        """Mức đánh giá ứng với tỷ lệ điểm pct (0..100): mức có 'Từ điểm' lớn nhất không vượt pct, theo loại checklist."""
        levels = self.sudo().search([('audit_type', '=', audit_type or 'nvbh')], order='min_score desc')
        return next((l for l in levels if pct >= l.min_score), levels[-1:] if levels else levels)
