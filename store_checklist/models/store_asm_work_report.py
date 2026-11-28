# -*- coding: utf-8 -*-
import calendar
import re
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

RESULT_SELECTION = [
    ('violation', 'Phát hiện vi phạm'),
    ('discrepancy', 'Sai lệch'),
    ('ok', 'Không có vấn đề gì'),
]
RESULT_LABELS = dict(RESULT_SELECTION)

RATING_SELECTION = [
    ('excellent', 'Xuất sắc'),
    ('pass', 'Đạt'),
    ('need_improve', 'Cần cải thiện'),
    ('average', 'Trung bình'),
    ('fail', 'Chưa đạt'),
]
RATING_LABELS = dict(RATING_SELECTION)

STATE_SELECTION = [
    ('draft', 'Nháp'),
    ('done', 'Hoàn thành'),
]
STATE_LABELS = dict(STATE_SELECTION)

_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def _norm_hhmm(val):
    s = (val or '').strip()
    if not s:
        return ''
    if re.match(r'^\d:[0-5]\d$', s):
        s = '0' + s
    if not _TIME_RE.match(s):
        raise UserError('Giờ phải theo định dạng 24 tiếng HH:MM (ví dụ: 10:30, 12:00).')
    return s


class StoreAsmWorkReport(models.Model):
    _name = 'store.asm.work.report'
    _description = 'Báo cáo công việc ASM'
    _order = 'work_date desc, time_in desc, id desc'

    work_date = fields.Date('Ngày', required=True, default=fields.Date.context_today, index=True)
    time_in = fields.Char('Giờ vào', size=5)
    time_out = fields.Char('Giờ ra', size=5)
    store_id = fields.Many2one('hr.store', string='Tên cửa hàng', required=True, index=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', string='Người thực hiện', default=lambda self: self.env.user, index=True)
    work_group_ids = fields.Many2many(
        'store.asm.task.group', 'store_asm_work_report_group_rel', 'report_id', 'group_id',
        string='Nhóm công việc',
    )
    work_group = fields.Char('Nhóm công việc (tên)')
    goal_plan = fields.Text('Mục tiêu / kế hoạch')
    work_content = fields.Text('Nội dung công việc')
    result = fields.Selection(RESULT_SELECTION, string='Kết quả đạt được', default='ok')
    error_count = fields.Integer('Chi tiết lỗi', default=0)
    rating = fields.Selection(RATING_SELECTION, string='Đánh giá', default='pass')
    note = fields.Text('Ghi chú')
    state = fields.Selection(STATE_SELECTION, string='Trạng thái', default='done', required=True)

    @api.model
    def _is_manager(self):
        u = self.env.user
        return self.env.su or u.has_group('base.group_system') or u.has_group('store_checklist.group_store_manager')

    def _serialize(self):
        self.ensure_one()
        uid = self.env.uid
        is_mgr = self._is_manager()
        d = self.work_date
        return {
            'id': self.id,
            'work_date': d.strftime('%Y-%m-%d') if d else '',
            'date_label': d.strftime('%d/%m/%Y') if d else '',
            'time_in': self.time_in or '',
            'time_out': self.time_out or '',
            'store_id': self.store_id.id,
            'store_name': self.store_id.display_name or self.store_id.name or '',
            'user_id': self.user_id.id,
            'user_name': self.user_id.name or '',
            'work_group_ids': self.work_group_ids.ids,
            'work_group_names': [g.name for g in self.work_group_ids.sorted(lambda x: (x.sequence, x.id))],
            'work_group': ', '.join(g.name for g in self.work_group_ids.sorted(lambda x: (x.sequence, x.id))) or (self.work_group or ''),
            'goal_plan': self.goal_plan or '',
            'work_content': self.work_content or '',
            'result': self.result or '',
            'result_label': RESULT_LABELS.get(self.result, ''),
            'error_count': int(self.error_count or 0),
            'rating': self.rating or '',
            'rating_label': RATING_LABELS.get(self.rating, ''),
            'note': self.note or '',
            'state': self.state or 'done',
            'state_label': STATE_LABELS.get(self.state, 'Hoàn thành'),
            'can_edit': bool(is_mgr or self.user_id.id == uid),
        }

    @api.model
    def get_asm_work_reports(self, month=False, store_id=False, q=False):
        today = fields.Date.context_today(self)
        mkey = (month or '').strip()
        if not re.match(r'^\d{4}-\d{2}$', mkey):
            mkey = today.strftime('%Y-%m')
        y, m = int(mkey[:4]), int(mkey[5:7])
        d1 = date(y, m, 1)
        d2 = date(y, m, calendar.monthrange(y, m)[1])

        stores = self.env['store.nvbh.check'].get_my_stores()
        allowed_ids = [s['id'] for s in stores]
        is_mgr = self._is_manager()

        dom = [('work_date', '>=', d1), ('work_date', '<=', d2)]
        if store_id:
            dom.append(('store_id', '=', int(store_id)))
        elif not is_mgr:
            if allowed_ids:
                dom.extend(['|', ('store_id', 'in', allowed_ids), ('user_id', '=', self.env.uid)])
            else:
                dom.append(('user_id', '=', self.env.uid))

        recs = self.sudo().search(dom, order='work_date desc, time_in desc, id desc')
        rows = [r._serialize() for r in recs]
        q_str = (q or '').strip().lower()
        if q_str:
            rows = [
                r for r in rows
                if q_str in (r['store_name'] or '').lower()
                or q_str in (r['work_group'] or '').lower()
                or q_str in (r['goal_plan'] or '').lower()
                or q_str in (r['work_content'] or '').lower()
                or q_str in (r['note'] or '').lower()
                or q_str in (r['user_name'] or '').lower()
            ]
        groups = [
            {'id': g.id, 'name': g.name}
            for g in self.env['store.asm.task.group'].sudo().search([], order='sequence, id')
        ]
        return {
            'month': mkey,
            'month_label': f'{m:02d}/{y}',
            'stores': stores,
            'groups': groups,
            'rows': rows,
        }

    @api.model
    def save_asm_work_report(self, vals):
        vals = vals or {}
        rec_id = int(vals.get('id') or 0)
        work_date = (vals.get('work_date') or '').strip()
        if not work_date:
            raise UserError('Vui lòng chọn Ngày.')
        store_id = int(vals.get('store_id') or 0)
        if not store_id:
            raise UserError('Vui lòng chọn Tên cửa hàng.')
        if not self._is_manager():
            allowed_ids = {s['id'] for s in self.env['store.nvbh.check'].get_my_stores()}
            if allowed_ids and store_id not in allowed_ids:
                raise AccessError('Bạn chỉ được tạo báo cáo cho cửa hàng mình quản lý.')

        time_in = _norm_hhmm(vals.get('time_in'))
        time_out = _norm_hhmm(vals.get('time_out'))
        if time_in and time_out and time_out < time_in:
            raise UserError('Giờ ra phải lớn hơn hoặc bằng Giờ vào.')

        result = vals.get('result') or 'ok'
        if result not in RESULT_LABELS:
            result = 'ok'
        rating = vals.get('rating') or 'pass'
        if rating not in RATING_LABELS:
            rating = 'pass'
        try:
            error_count = max(0, int(vals.get('error_count') or 0))
        except (TypeError, ValueError):
            error_count = 0

        raw_gids = vals.get('work_group_ids') or []
        gids = [int(x) for x in raw_gids if str(x).isdigit()]
        grp_recs = self.env['store.asm.task.group'].sudo().browse(gids).exists().sorted(lambda x: (x.sequence, x.id))
        wg_text = ', '.join(grp_recs.mapped('name')) or (vals.get('work_group') or '').strip()

        write_vals = {
            'work_date': work_date,
            'time_in': time_in or False,
            'time_out': time_out or False,
            'store_id': store_id,
            'work_group_ids': [(6, 0, grp_recs.ids)],
            'work_group': wg_text,
            'goal_plan': (vals.get('goal_plan') or '').strip(),
            'work_content': (vals.get('work_content') or '').strip(),
            'result': result,
            'error_count': error_count,
            'rating': rating,
            'note': (vals.get('note') or '').strip(),
            'state': 'done',  # khi lưu phiếu -> Hoàn thành
        }
        if rec_id:
            rec = self.sudo().browse(rec_id).exists()
            if not rec:
                raise UserError('Không tìm thấy phiếu báo cáo.')
            if not self._is_manager() and rec.user_id.id != self.env.uid:
                raise AccessError('Bạn không có quyền sửa phiếu báo cáo này.')
            rec.write(write_vals)
        else:
            write_vals['user_id'] = self.env.uid
            rec = self.sudo().create(write_vals)
        return rec._serialize()

    @api.model
    def delete_asm_work_report(self, rec_id):
        rec = self.sudo().browse(int(rec_id or 0)).exists()
        if not rec:
            return True
        if not self._is_manager() and rec.user_id.id != self.env.uid:
            raise AccessError('Bạn không có quyền xóa phiếu báo cáo này.')
        rec.unlink()
        return True
