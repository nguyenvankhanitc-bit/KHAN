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
    no_error = fields.Boolean(string='Không được có lỗi',
                              help='Bật: phiếu chỉ được xếp mức này khi Tổng số lỗi = 0; có lỗi thì xếp xuống mức thấp hơn kế tiếp.')

    @api.depends('min_score', 'audit_type')
    def _compute_score_range(self):
        # mức nào cũng kéo dài tới ngay dưới mức cao hơn kế tiếp
        for rec in self:
            levels = self.search(self.COMMON_DOMAIN if rec.audit_type != 'gs' else [('audit_type', '=', 'gs')], order='min_score asc')
            higher = levels.filtered(lambda l: l.min_score > rec.min_score)[:1]
            top = '%g' % (higher.min_score - 1) if higher else '100'
            rec.score_range = '%g - %s' % (rec.min_score, top) if rec.min_score < float(top) else '%g' % rec.min_score

    def action_open_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'views': [(False, 'form')], 'target': 'new', 'context': {'dialog_size': 'large'},
        }

    # Một bảng chung cho mọi phiếu đánh giá (NVBH / ASM / GS): Cài đặt › Công việc đánh giá › Mức Đánh giá.
    # Trang "Mức độ đánh giá" của Công việc giám sát mở cùng bảng này; các dòng loại GS cũ không còn dùng.
    COMMON_DOMAIN = [('audit_type', '!=', 'gs')]

    @api.model
    def common_levels(self):
        return self.sudo().search(self.COMMON_DOMAIN, order='min_score desc')

    @api.model
    def level_for(self, pct, audit_type=None, errors=0):
        """Mức đánh giá ứng với tỷ lệ điểm pct (0..100): mức có 'Từ điểm' lớn nhất không vượt pct, theo bảng Mức Đánh giá chung
        (audit_type giữ để tương thích, không còn tách bảng theo loại checklist). Có lỗi (errors > 0) thì bỏ qua các mức
        đánh dấu "Không được có lỗi" (vd. Tốt: phải 0 lỗi) và xếp xuống mức kế tiếp."""
        levels = self.common_levels()
        return next((l for l in levels if pct >= l.min_score and not (errors and l.no_error)), levels[-1:] if levels else levels)

    @api.model
    def _init_no_error(self):
        """Lần đầu: bật "Không được có lỗi" cho mức cao nhất của bảng chung (vd. Tốt)."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('store_checklist.level_no_error_init') == '1':
            return
        top = self.common_levels()[:1]
        if top:
            top.write({'no_error': True})
        ICP.set_param('store_checklist.level_no_error_init', '1')
