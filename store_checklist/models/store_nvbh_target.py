# -*- coding: utf-8 -*-
import base64
import io
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

MIEN_LABELS = {'Nam': 'Miền Nam', 'ĐTT': 'Miền ĐTT', 'Bắc': 'Miền Bắc', 'VP': 'Văn phòng'}


class StoreNvbhTarget(models.Model):
    """Checklist NVBH > Doanh thu > Phân Bổ Target: Target doanh thu cửa hàng theo tháng,
    phân bổ cho từng nhân viên theo tỷ trọng % (Thành tiền = Target CH x %)."""
    _name = 'store.nvbh.target'
    _description = 'Phân bổ Target doanh thu cửa hàng theo tháng'
    _order = 'month desc, store_id'

    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True, ondelete='cascade')
    mien = fields.Selection(related='store_id.mien', string='Miền', store=True)
    month = fields.Char(string='Tháng (YYYY-MM)', required=True, index=True)
    target = fields.Float(string='Target cửa hàng', digits=(16, 0), default=0.0)
    line_ids = fields.One2many('store.nvbh.target.line', 'target_id', string='Phân bổ nhân viên')

    @api.model
    def _tg_show_grand(self):
        """Dòng TỔNG HỆ THỐNG: ẩn với Nhân viên, CHT, ASM, RSM, Giám sát (cấp 1-5); admin / quản lý / QLBH / không có chức vụ thì thấy."""
        from .store_role import role_level
        user = self.env.user
        if user._is_admin() or user.has_group('store_checklist.group_store_manager'):
            return True
        emp = user.sudo().employee_id
        level = role_level(emp.checklist_role_code) if emp else 0
        return not (1 <= level <= 5)

    # ---------------- dữ liệu trang ----------------
    @api.model
    def get_target_page(self, month=None, mien=None, store_id=None):
        Rev = self.env['store.nvbh.revenue']
        # gọi nội bộ từ Theo Dõi Target / Import: kiểm tra quyền theo tab gọi
        Rev._check_perm('read', self.env.context.get('tg_perm_key') or 'nvbh_rev_target')
        start_d, end_d, m_key, m_label, _days = Rev._month_bounds(month)
        allowed = Rev._allowed_stores()
        if mien:
            allowed = allowed.filtered(lambda s: (s.mien or '') == mien)
        store_opts = [{'id': s.id, 'name': s.display_name or s.name or '-'}
                      for s in sorted(allowed, key=lambda x: (x.display_name or x.name or '').casefold())]
        targets = allowed.filtered(lambda s: s.id == int(store_id)) if store_id else allowed

        # Nhân sự có ca làm (NVBH / CHT, khác OFF) trong tháng theo Lịch xếp ca
        Check = self.env['store.nvbh.check'].sudo()
        sched = self.env['store.nvbh.schedule.line'].sudo().search([
            ('work_date', '>=', start_d), ('work_date', '<=', end_d), ('store_id', 'in', targets.ids),
        ], order='work_date, sequence, id') if targets else []
        staff_by_store = {}
        for ln in sched:
            scode = (ln.shift_id.code or '').strip().upper()
            if not scode or scode == 'OFF':
                continue
            kind = Check._schedule_kind(ln)
            if kind not in ('nvbh', 'cht'):
                continue
            nm = (ln.staff_name or '').strip()
            if not nm:
                continue
            code = (ln.employee_code or '').strip()
            key = code or nm.casefold()
            d = staff_by_store.setdefault(ln.store_id.id, {})
            pos = (ln.position or '').strip()
            if key not in d:
                d[key] = {'staff_key': key, 'staff_name': nm, 'employee_code': code,
                          'position': pos, 'is_cht': kind == 'cht'}
            else:
                # ID HRM / Mã chức vụ: theo dòng lịch ca mới nhất trong tháng
                if pos:
                    d[key]['position'] = pos
                if code:
                    d[key]['employee_code'] = code
                if kind == 'cht':
                    d[key]['is_cht'] = True

        existing = self.sudo().search([('month', '=', m_key), ('store_id', 'in', targets.ids)]) if targets else self.browse()
        by_store = {t.store_id.id: t for t in existing}

        stores = []
        for st in targets:
            tg = by_store.get(st.id)
            staff = dict(staff_by_store.get(st.id, {}))
            saved = {}
            if tg:
                for l in tg.line_ids:
                    saved[l.staff_key] = l
                    if l.staff_key not in staff:
                        staff[l.staff_key] = {'staff_key': l.staff_key, 'staff_name': l.staff_name,
                                              'employee_code': l.employee_code or '', 'position': l.position or '',
                                              'is_cht': l.is_cht}
            if not staff:
                continue
            lines = []
            for key, s in staff.items():
                l = saved.get(key)
                lines.append(dict(s, pct=round(l.pct, 2) if l else 0.0))
            lines.sort(key=lambda x: (0 if x['is_cht'] else 1, x['staff_name'].casefold()))
            smien = st.mien or ''
            stores.append({
                'store_id': st.id,
                'store': st.display_name or st.name or '-',
                'mien': smien,
                'mien_label': MIEN_LABELS.get(smien, smien or 'Khác'),
                'target': round(tg.target) if tg else 0,
                'lines': lines,
            })
        stores.sort(key=lambda s: (list(MIEN_LABELS).index(s['mien']) if s['mien'] in MIEN_LABELS else 99, s['store'].casefold()))

        return {
            'month': m_key,
            'month_label': m_label,
            'can_edit': Rev._rev_right('nvbh_rev_target', 'write'),
            'can_export': Rev._rev_right('nvbh_rev_target', 'export'),
            'show_grand': self._tg_show_grand(),
            'store_opts': store_opts,
            'stores': stores,
        }

    @api.model
    def save_target_batch(self, month, stores):
        """Lưu Target cửa hàng + tỷ trọng % từng nhân viên (bấm nút Lưu)."""
        Rev = self.env['store.nvbh.revenue']
        Rev._check_perm('write', 'nvbh_rev_target')
        m_key = Rev._month_bounds(month)[2]
        allowed = Rev._allowed_stores()
        allowed_ids = set(allowed.ids)
        names = {s.id: s.display_name for s in allowed}
        for s in stores or []:
            sid = int(s.get('store_id') or 0)
            if sid not in allowed_ids:
                raise UserError(_('Bạn không có quyền phân bổ target cho cửa hàng này (ID=%s).') % sid)
            lines = s.get('lines') or []
            total_pct = round(sum(max(0.0, float(l.get('pct') or 0.0)) for l in lines), 2)
            if total_pct > 100.0:
                raise UserError(_('Tổng tỷ trọng phân bổ của cửa hàng %s là %s%%, vượt quá 100%%.') % (names.get(sid, sid), total_pct))
        for s in stores or []:
            sid = int(s['store_id'])
            tg = self.sudo().search([('store_id', '=', sid), ('month', '=', m_key)], limit=1)
            if not tg:
                tg = self.sudo().create({'store_id': sid, 'month': m_key})
            tg.write({'target': max(0.0, round(float(s.get('target') or 0.0)))})
            tg.line_ids.unlink()
            vals = []
            for i, l in enumerate(s.get('lines') or [], 1):
                vals.append({
                    'target_id': tg.id,
                    'sequence': i,
                    'staff_key': l.get('staff_key') or (l.get('employee_code') or l.get('staff_name') or '').strip(),
                    'staff_name': l.get('staff_name') or '-',
                    'employee_code': l.get('employee_code') or '',
                    'position': l.get('position') or '',
                    'is_cht': bool(l.get('is_cht')),
                    'pct': round(max(0.0, min(100.0, float(l.get('pct') or 0.0))), 2),
                })
            if vals:
                self.env['store.nvbh.target.line'].sudo().create(vals)
        return True

    # ---------------- Theo Dõi Target (tiến độ doanh thu so với target) ----------------
    @api.model
    def get_target_track(self, month=None, store_id=None, mien=None, days=None):
        """Theo dõi Target của 1 cửa hàng trong tháng: chỉ tiêu cửa hàng, tiến độ từng nhân viên, theo tuần (Tuần 1-4)
        và từng ngày. Thuật ngữ: Target Tháng / Target Ngày / Phân bổ target (%) / Doanh thu đã đạt / % Đạt được /
        Còn lại phải đạt / % Còn lại; đánh giá Đạt / Không đạt (ngày chưa có doanh thu: Chưa nhập).
        days: Số Ngày Tháng (mặc định = số ngày thực của tháng)."""
        from datetime import timedelta
        Rev = self.env['store.nvbh.revenue']
        Rev._check_perm('read', 'nvbh_rev_track')
        start_d, end_d, m_key, m_label, month_days = Rev._month_bounds(month)
        allowed = Rev._allowed_stores()
        if mien:
            allowed = allowed.filtered(lambda s: (s.mien or '') == mien)

        def code_of(st):
            return st.code or st.display_name or st.name or '-'

        store_opts = [{'id': s.id, 'name': code_of(s)} for s in sorted(allowed, key=lambda x: code_of(x).casefold())]
        store = allowed.filtered(lambda s: s.id == int(store_id)) if store_id else allowed.browse()
        if not store and allowed:
            # mặc định: cửa hàng đầu tiên đã có target trong tháng, không có thì cửa hàng đầu tiên
            has_tg = self.sudo().search([('month', '=', m_key), ('store_id', 'in', allowed.ids), ('target', '>', 0)])
            pick = sorted(has_tg.mapped('store_id') or allowed, key=lambda x: code_of(x).casefold())
            store = pick[0] if pick else allowed.browse()
        base = {'month': m_key, 'month_label': m_label, 'store_opts': store_opts}
        base['can_export'] = Rev._rev_right('nvbh_rev_track', 'export')
        if not store:
            base['store'] = False
            return base
        store = store[:1]

        ndays = int(days or 0) or month_days
        ndays = max(1, min(31, ndays))
        page = self.with_context(tg_perm_key='nvbh_rev_track').get_target_page(m_key, False, store.id)
        sdata = next((s for s in page['stores'] if s['store_id'] == store.id), None)
        target = float(sdata['target']) if sdata else float(self.sudo().search(
            [('month', '=', m_key), ('store_id', '=', store.id)], limit=1).target or 0)
        lines = [dict(l) for l in (sdata['lines'] if sdata else [])]

        def norm(v):
            return (v or '').strip().casefold()

        # doanh thu đã lưu trong tháng, gom theo nhân viên + ngày
        recs = Rev.sudo().search([('store_id', '=', store.id), ('work_date', '>=', start_d), ('work_date', '<=', end_d),
                                  ('is_saved', '=', True)])
        by_code = {l['employee_code']: l for l in lines if l.get('employee_code')}
        by_name = {norm(l['staff_name']): l for l in lines}
        for l in lines:
            l['days'] = {}
        for r in recs:
            l = by_code.get((r.employee_code or '').strip()) or by_name.get(norm(r.staff_name))
            if not l:  # có doanh thu nhưng chưa có trong bảng phân bổ: thêm dòng 0%
                l = {'staff_key': (r.employee_code or '').strip() or norm(r.staff_name), 'staff_name': (r.staff_name or '-').strip(),
                     'employee_code': (r.employee_code or '').strip(), 'position': r.position or '', 'is_cht': False,
                     'pct': 0.0, 'days': {}}
                lines.append(l)
                if l['employee_code']:
                    by_code[l['employee_code']] = l
                by_name[norm(l['staff_name'])] = l
            k = r.work_date.isoformat()
            l['days'][k] = l['days'].get(k, 0) + (r.revenue or 0)

        def ev(done, tg):
            return 'Đạt' if tg > 0 and done >= tg else 'Không đạt'

        def pct(done, tg):
            # làm tròn 0,1% kiểu thông thường (0,05 -> 0,1), giống Excel
            return math.floor(1000.0 * done / tg + 0.5) / 10 if tg else 0.0

        def metrics(tg, done):
            p = pct(done, tg)
            return {'target': tg, 'done': done, 'pct': p, 'left': max(0, tg - done),
                    'left_pct': round(max(0.0, 100.0 - p), 1) if tg else 0.0, 'result': ev(done, tg)}

        target = round(target)
        day_target = round(target / ndays) if ndays else 0
        total_done = round(sum(sum(l['days'].values()) for l in lines))

        staff = []
        for i, l in enumerate(lines, 1):
            tg_nv = round(target * (l.get('pct') or 0) / 100.0)
            done = round(sum(l['days'].values()))
            staff.append(dict(metrics(tg_nv, done), stt=i, staff_key=l['staff_key'], staff_name=l['staff_name'],
                              employee_code=l.get('employee_code') or '', position=l.get('position') or '',
                              is_cht=bool(l.get('is_cht')), alloc=round(l.get('pct') or 0, 2),
                              day_target=round(tg_nv / ndays) if ndays else 0))
        sum_alloc = round(sum(s['alloc'] for s in staff), 2)
        staff_total = dict(metrics(sum(s['target'] for s in staff), total_done), alloc=sum_alloc,
                           day_target=sum(s['day_target'] for s in staff))

        WD = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN']
        today = fields.Date.context_today(self)
        day_rows = []
        cum = 0
        d = start_d
        while d <= end_d:
            k = d.isoformat()
            week = min(4, (d.day - 1) // 7 + 1)
            per = []
            for s, l in zip(staff, lines):
                v = l['days'].get(k)
                if v is not None or s['alloc']:
                    per.append({'staff_name': s['staff_name'], 'employee_code': s['employee_code'], 'is_cht': s['is_cht'],
                                'done': round(v or 0), 'day_target': s['day_target'],
                                'diff': round(v or 0) - s['day_target'],
                                'result': ('Chưa nhập' if v is None else ev(round(v), s['day_target']))})
            has = any(k in l['days'] for l in lines)
            done = round(sum(l['days'].get(k, 0) for l in lines))
            cum += done
            day_rows.append({'date': k, 'label': d.strftime('%d/%m/%Y'), 'weekday': WD[d.weekday()], 'week': week,
                             'target': day_target, 'done': done, 'diff': done - day_target,
                             'result': ev(done, day_target) if has else 'Chưa nhập', 'cum': cum,
                             'left_month': max(0, target - cum), 'is_today': d == today, 'staff': per})
            d += timedelta(days=1)

        weeks = []
        acc_target = 0
        for w in range(1, 5):
            rows = [r for r in day_rows if r['week'] == w]
            if not rows:
                continue
            n = len(rows)
            # Target Tuần = Target Ngày x số ngày; tuần cuối nhận phần còn lại để tổng 4 tuần = Target Tháng
            wt = (target - acc_target) if w == 4 or rows[-1]['date'] == end_d.isoformat() else day_target * n
            wt = max(0, wt)
            acc_target += wt
            done = sum(r['done'] for r in rows)
            weeks.append(dict(metrics(wt, done), week=w, label='Tuần %d' % w, days=n,
                              range='%s - %s' % (rows[0]['label'][:5], rows[-1]['label']), diff=done - wt))
        weeks_total = dict(metrics(sum(w['target'] for w in weeks), total_done), days=len(day_rows),
                           diff=total_done - sum(w['target'] for w in weeks))

        smien = store.mien or ''
        base.update({
            'store': {'id': store.id, 'code': code_of(store), 'mien': smien, 'mien_label': MIEN_LABELS.get(smien, smien or 'Khác')},
            'month_days': month_days,
            'days': ndays,
            'summary': dict(metrics(target, total_done), day_target=day_target),
            'staff': staff,
            'staff_total': staff_total,
            'weeks': weeks,
            'weeks_total': weeks_total,
            'day_rows': day_rows,
        })
        return base

    @api.model
    def export_track_xlsx(self, month=None, store_id=None, mien=None, days=None):
        self.env['store.nvbh.revenue']._check_perm('export', 'nvbh_rev_track')
        import xlsxwriter
        data = self.get_target_track(month, store_id, mien, days)
        if not data.get('store'):
            raise UserError(_('Không có cửa hàng để xuất.'))
        st, sm = data['store'], data['summary']
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        base = {'font_name': 'Times New Roman', 'font_size': 12, 'valign': 'vcenter', 'border': 1}
        F = {
            'title': book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 15, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'valign': 'vcenter'}),
            'sub': book.add_format({'font_name': 'Times New Roman', 'italic': True, 'font_size': 11, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'valign': 'vcenter'}),
            'sec': book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'font_color': '#1E3A6E'}),
            'head': book.add_format(dict(base, bold=True, font_color='#FFFFFF', bg_color='#15803D', align='center', text_wrap=True)),
            'nred': book.add_format(dict(base, align='right', bold=True, font_color='#DC2626', num_format='#,##0')),
            'tred': book.add_format(dict(base, align='right', bold=True, font_color='#DC2626', bg_color='#E2E8F0', num_format='#,##0')),
            'c': book.add_format(dict(base, align='center')),
            'cb': book.add_format(dict(base, align='center', bold=True)),
            'l': book.add_format(dict(base, align='left')),
            'lb': book.add_format(dict(base, align='left', bold=True)),
            'n': book.add_format(dict(base, align='right', num_format='#,##0')),
            'nb': book.add_format(dict(base, align='right', bold=True, num_format='#,##0')),
            'nblue': book.add_format(dict(base, align='right', bold=True, font_color='#1D4ED8', bg_color='#EFF6FF', num_format='#,##0')),
            'p': book.add_format(dict(base, align='center', num_format='0.0%')),
            'pb': book.add_format(dict(base, align='center', bold=True, num_format='0.0%')),
            'pblue': book.add_format(dict(base, align='center', bold=True, font_color='#1D4ED8', bg_color='#EFF6FF', num_format='0.0%')),
            'ok': book.add_format(dict(base, align='center', bold=True, font_color='#15803D')),
            'bad': book.add_format(dict(base, align='center', bold=True, font_color='#B91C1C')),
            'na': book.add_format(dict(base, align='center', italic=True, font_color='#64748B')),
            'tl': book.add_format(dict(base, align='center', bold=True, bg_color='#E2E8F0')),
            'tn': book.add_format(dict(base, align='right', bold=True, bg_color='#E2E8F0', num_format='#,##0')),
            'tp': book.add_format(dict(base, align='center', bold=True, bg_color='#E2E8F0', num_format='0.0%')),
        }

        def res_fmt(v):
            return F['ok'] if v == 'Đạt' else F['na'] if v == 'Chưa nhập' else F['bad']

        def heads(ws, r, hs):
            for c, h in enumerate(hs):
                ws.write(r, c, h, F['head'])
            ws.set_row(r, 34)

        # Sheet 1: tổng hợp
        ws = book.add_worksheet('Tong_Hop_Target_Tuan_NV')
        for c, w in enumerate([14, 16, 30, 18, 18, 18, 18, 18, 16, 16, 18]):
            ws.set_column(c, c, w)
        ws.merge_range(0, 0, 0, 10, 'LUG.VN - THEO DÕI TARGET CỬA HÀNG, NHÂN VIÊN & ĐÁNH GIÁ TUẦN (THÁNG %s - %s)' % (data['month_label'], st['code']), F['title'])
        ws.merge_range(1, 0, 1, 10, 'Phân bổ target (%) • Doanh thu đã đạt • % Đạt được • Còn lại phải đạt • % Còn lại', F['sub'])
        ws.set_row(0, 30)
        r = 3
        ws.write(r, 0, '1. CHỈ TIÊU CỬA HÀNG TRONG THÁNG', F['sec'])
        heads(ws, r + 1, ['Mã Cửa Hàng', 'Miền', 'Số Ngày Tháng', 'Target Tháng', 'Target Ngày', 'Doanh thu đã đạt',
                          'Còn lại phải đạt', '% Đạt được', '% Còn lại', 'Đánh giá tháng'])
        r += 2
        ws.write(r, 0, st['code'], F['cb'])
        ws.write(r, 1, st['mien_label'], F['c'])
        ws.write_number(r, 2, data['days'], F['cb'])
        ws.write_number(r, 3, sm['target'], F['nred'])
        ws.write_number(r, 4, sm['day_target'], F['nb'])
        ws.write_number(r, 5, sm['done'], F['nred'])
        ws.write_number(r, 6, sm['left'], F['nb'])
        ws.write_number(r, 7, sm['pct'] / 100.0, F['pb'])
        ws.write_number(r, 8, sm['left_pct'] / 100.0, F['pb'])
        ws.write(r, 9, sm['result'], res_fmt(sm['result']))
        r += 2
        ws.write(r, 0, '2. TARGET & TIẾN ĐỘ TỪNG NHÂN VIÊN', F['sec'])
        heads(ws, r + 1, ['STT', 'ID HRM', 'Tên nhân viên', 'Phân bổ target (%)', 'Target Tháng NV', 'Target Ngày NV',
                          'Doanh thu đã đạt', '% Đạt được', 'Còn lại phải đạt', '% Còn lại', 'Đánh giá tiến độ'])
        r += 2
        for s in data['staff']:
            ws.write_number(r, 0, s['stt'], F['c'])
            ws.write(r, 1, s['employee_code'], F['c'])
            ws.write(r, 2, s['staff_name'] + (' (CHT)' if s['is_cht'] else ''), F['lb'] if s['is_cht'] else F['l'])
            ws.write_number(r, 3, s['alloc'] / 100.0, F['pblue'])
            ws.write_number(r, 4, s['target'], F['nred'])
            ws.write_number(r, 5, s['day_target'], F['n'])
            ws.write_number(r, 6, s['done'], F['nred'])
            ws.write_number(r, 7, s['pct'] / 100.0, F['pb'])
            ws.write_number(r, 8, s['left'], F['n'])
            ws.write_number(r, 9, s['left_pct'] / 100.0, F['p'])
            ws.write(r, 10, s['result'], res_fmt(s['result']))
            r += 1
        t = data['staff_total']
        ws.merge_range(r, 0, r, 2, 'TỔNG CỘNG NHÂN VIÊN', F['tl'])
        ws.write_number(r, 3, t['alloc'] / 100.0, F['tp'])
        ws.write_number(r, 4, t['target'], F['tred'])
        ws.write_number(r, 5, t['day_target'], F['tn'])
        ws.write_number(r, 6, t['done'], F['tred'])
        ws.write_number(r, 7, t['pct'] / 100.0, F['tp'])
        ws.write_number(r, 8, t['left'], F['tn'])
        ws.write_number(r, 9, t['left_pct'] / 100.0, F['tp'])
        ws.write(r, 10, t['result'], F['tl'])
        r += 2
        ws.write(r, 0, '3. ĐÁNH GIÁ DOANH THU & TARGET THEO TUẦN (TUẦN 1 - TUẦN 4)', F['sec'])
        heads(ws, r + 1, ['Tuần', 'Từ ngày - Đến ngày', 'Số ngày', 'Target Tuần', 'Doanh thu đã đạt', 'Chênh lệch (+/-)',
                          'Còn lại trong tuần', '% Đạt được', '% Còn lại', 'Đánh giá tuần'])
        r += 2
        for w in data['weeks']:
            ws.write(r, 0, w['label'], F['cb'])
            ws.write(r, 1, w['range'], F['c'])
            ws.write_number(r, 2, w['days'], F['c'])
            ws.write_number(r, 3, w['target'], F['nred'])
            ws.write_number(r, 4, w['done'], F['nred'])
            ws.write_number(r, 5, w['diff'], F['n'])
            ws.write_number(r, 6, w['left'], F['n'])
            ws.write_number(r, 7, w['pct'] / 100.0, F['p'])
            ws.write_number(r, 8, w['left_pct'] / 100.0, F['p'])
            ws.write(r, 9, w['result'], res_fmt(w['result']))
            r += 1
        t = data['weeks_total']
        ws.merge_range(r, 0, r, 1, 'TỔNG CỘNG 4 TUẦN', F['tl'])
        ws.write_number(r, 2, t['days'], F['tl'])
        ws.write_number(r, 3, t['target'], F['tred'])
        ws.write_number(r, 4, t['done'], F['tred'])
        ws.write_number(r, 5, t['diff'], F['tn'])
        ws.write_number(r, 6, t['left'], F['tn'])
        ws.write_number(r, 7, t['pct'] / 100.0, F['tp'])
        ws.write_number(r, 8, t['left_pct'] / 100.0, F['tp'])
        ws.write(r, 9, t['result'], F['tl'])

        # Sheet 2: từng ngày
        ws = book.add_worksheet('Theo_Doi_Tung_Ngay')
        staff = data['staff']
        cols = ['Ngày', 'Thứ', 'Tuần', 'Target Ngày CH', 'Doanh thu đã đạt'] + ['DT %s' % s['staff_name'] for s in staff] + \
               ['Chênh lệch ngày', 'Đánh giá ngày', 'Tổng đã đạt từ đầu tháng', 'Còn lại Target Tháng']
        last = len(cols) - 1
        for c, w in enumerate([14, 9, 9, 17, 17] + [20] * len(staff) + [17, 14, 20, 20]):
            ws.set_column(c, c, w)
        ws.merge_range(0, 0, 0, last, 'LUG.VN - BẢNG THEO DÕI TARGET & DOANH THU TỪNG NGÀY (THÁNG %s - %s)' % (data['month_label'], st['code']), F['title'])
        ws.merge_range(1, 0, 1, last, 'Đánh giá ngày: Đạt / Không đạt so với Target Ngày; ngày chưa có doanh thu: Chưa nhập', F['sub'])
        ws.set_row(0, 30)
        heads(ws, 3, cols)
        r = 4
        for d in data['day_rows']:
            ws.write(r, 0, d['label'], F['c'])
            ws.write(r, 1, d['weekday'], F['c'])
            ws.write(r, 2, 'Tuần %d' % d['week'], F['cb'])
            ws.write_number(r, 3, d['target'], F['n'])
            ws.write_number(r, 4, d['done'], F['nred'])
            by = {p['staff_name']: p for p in d['staff']}
            for j, s in enumerate(staff):
                ws.write_number(r, 5 + j, (by.get(s['staff_name']) or {}).get('done', 0), F['nblue'])
            c0 = 5 + len(staff)
            ws.write_number(r, c0, d['diff'], F['n'])
            ws.write(r, c0 + 1, d['result'], res_fmt(d['result']))
            ws.write_number(r, c0 + 2, d['cum'], F['n'])
            ws.write_number(r, c0 + 3, d['left_month'], F['nb'])
            r += 1
        ws.merge_range(r, 0, r, 2, 'TỔNG CỘNG THÁNG %s' % data['month_label'], F['tl'])
        ws.write_number(r, 3, sum(d['target'] for d in data['day_rows']), F['tn'])
        ws.write_number(r, 4, sm['done'], F['tred'])
        for j, s in enumerate(staff):
            ws.write_number(r, 5 + j, s['done'], F['tn'])
        c0 = 5 + len(staff)
        ws.write_number(r, c0, sm['done'] - sum(d['target'] for d in data['day_rows']), F['tn'])
        ws.write(r, c0 + 1, '%d ngày Đạt' % sum(1 for d in data['day_rows'] if d['result'] == 'Đạt'), F['tl'])
        ws.write_number(r, c0 + 2, sm['done'], F['tn'])
        ws.write_number(r, c0 + 3, sm['left'], F['tn'])
        ws.freeze_panes(4, 3)
        book.close()
        return {
            'name': 'Theo_Doi_Target_%s_%s.xlsx' % (st['code'], data['month'].replace('-', '')),
            'data': base64.b64encode(buf.getvalue()).decode(),
        }

    @api.model
    def import_target_xlsx(self, month, data):
        """Import file Excel Phân Bổ Target (cùng mẫu với Xuất Excel): đọc cột Mã Cửa Hàng, Tên nhân viên, ID HRM,
        Target Cửa Hàng, Đã Phân Bổ NV theo %. Chỉ cập nhật cửa hàng có trong file; nhân viên không có trong file giữ nguyên %."""
        import openpyxl
        self.env['store.nvbh.revenue']._check_perm('write', 'nvbh_rev_target')
        try:
            wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(data)), data_only=True)
        except Exception:
            raise UserError(_('File không đọc được. Vui lòng chọn file Excel (.xlsx).'))
        ws = wb.worksheets[0]

        def norm(v):
            return re.sub(r'\s+', ' ', str(v or '')).strip().casefold()

        # dòng tiêu đề: có ô "Mã Cửa Hàng"
        head_row, cols = None, {}
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 15)):
            names = {norm(c.value): c.column - 1 for c in row if c.value}
            if 'mã cửa hàng' in names:
                head_row = row[0].row
                for key, labels in (('store', ['mã cửa hàng']), ('name', ['tên nhân viên']), ('code', ['id hrm', 'id']),
                                    ('target', ['target cửa hàng']), ('pct', ['đã phân bổ nv theo %', 'tỷ trọng %', '%'])):
                    cols[key] = next((names[l] for l in labels if l in names), None)
                break
        if not head_row or cols.get('store') is None or cols.get('pct') is None or (cols.get('name') is None and cols.get('code') is None):
            raise UserError(_('Không tìm thấy dòng tiêu đề (cần các cột: Mã Cửa Hàng, Tên nhân viên / ID HRM, Target Cửa Hàng, '
                              'Đã Phân Bổ NV theo %). Hãy dùng file từ nút Xuất Excel.'))

        def money(v):
            if isinstance(v, (int, float)):
                return float(v)
            digits = re.sub(r'[^\d]', '', str(v or ''))
            return float(digits) if digits else None

        def pct(cell):
            v = cell.value
            if v is None or v == '':
                return None
            if isinstance(v, (int, float)):
                return float(v) * 100 if '%' in (cell.number_format or '') else float(v)
            txt = str(v).replace('%', '').replace(',', '.').strip()
            try:
                return float(txt)
            except ValueError:
                return None

        page = self.get_target_page(month)
        by_store = {}
        for s in page['stores']:
            st = self.env['hr.store'].sudo().browse(s['store_id'])
            for k in (s['store'], st.name, st.code):
                if k:
                    by_store.setdefault(norm(k), s)

        found, skipped, last_store, last_target = {}, [], None, None
        for row in ws.iter_rows(min_row=head_row + 1):
            store_txt = row[cols['store']].value if cols['store'] < len(row) else None
            if not store_txt:
                continue  # dòng tổng / dòng trống
            s = by_store.get(norm(store_txt))
            if not s:
                skipped.append(_('Cửa hàng "%s" không có trong tháng hoặc bạn không có quyền') % store_txt)
                continue
            entry = found.setdefault(s['store_id'], {'store': s, 'target': None, 'pcts': {}})
            if cols.get('target') is not None and cols['target'] < len(row):
                t = money(row[cols['target']].value)
                if t is not None:
                    entry['target'] = t
            code = str(row[cols['code']].value or '').strip() if cols.get('code') is not None else ''
            if code.endswith('.0'):
                code = code[:-2]
            name = norm(re.sub(r'\s*\(CHT\)\s*$', '', str(row[cols['name']].value or ''), flags=re.I)) if cols.get('name') is not None else ''
            line = next((l for l in s['lines'] if code and (l['employee_code'] or '') == code), None) \
                or next((l for l in s['lines'] if name and norm(l['staff_name']) == name), None)
            p = pct(row[cols['pct']])
            if not line:
                skipped.append(_('%s: không tìm thấy nhân viên "%s"') % (s['store'], code or name))
                continue
            if p is not None:
                entry['pcts'][line['staff_key']] = round(max(0.0, min(100.0, p)), 2)

        if not found:
            raise UserError(_('Không có dòng nào khớp cửa hàng trong tháng %s.') % page['month_label'])
        payload = []
        for sid, e in found.items():
            s = e['store']
            payload.append({
                'store_id': sid,
                'target': e['target'] if e['target'] is not None else s['target'],
                'lines': [dict(l, pct=e['pcts'].get(l['staff_key'], l['pct'])) for l in s['lines']],
            })
        self.save_target_batch(page['month'], payload)
        return {'stores': len(payload), 'staff': sum(len(e['pcts']) for e in found.values()), 'skipped': skipped[:20]}

    @api.model
    def export_target_xlsx(self, month=None, mien=None, store_id=None):
        self.env['store.nvbh.revenue']._check_perm('export', 'nvbh_rev_target')
        import xlsxwriter
        data = self.get_target_page(month, mien, store_id)
        stores = data['stores']
        if not stores:
            raise UserError(_('Không có dữ liệu phân bổ target để xuất.'))

        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = book.add_worksheet('Phan_Bo_Target')
        base = {'font_name': 'Times New Roman', 'font_size': 12, 'valign': 'vcenter', 'border': 1}
        f_title = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 14, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'valign': 'vcenter'})
        f_sub = book.add_format({'font_name': 'Times New Roman', 'italic': True, 'font_size': 11, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'valign': 'vcenter'})
        f_head = book.add_format(dict(base, bold=True, font_color='#FFFFFF', bg_color='#1E3A6E', align='center', text_wrap=True))
        f_c = book.add_format(dict(base, align='center'))
        f_cb = book.add_format(dict(base, align='center', bold=True))
        f_l = book.add_format(dict(base, align='left'))
        f_lb = book.add_format(dict(base, align='left', bold=True))
        f_tg = book.add_format(dict(base, align='center', bold=True, font_color='#1D4ED8', bg_color='#EFF6FF', num_format='#,##0'))
        f_pct = book.add_format(dict(base, align='center', font_color='#1D4ED8', bg_color='#EFF6FF', num_format='0.0%'))
        f_money = book.add_format(dict(base, align='right', num_format='#,##0'))
        f_sum_l = book.add_format(dict(base, align='center', bold=True, bg_color='#E2E8F0'))
        f_sum_n = book.add_format(dict(base, align='right', bold=True, bg_color='#E2E8F0', num_format='#,##0'))
        f_sum_p = book.add_format(dict(base, align='center', bold=True, bg_color='#E2E8F0', font_color='#15803D', num_format='0.0%'))
        f_sum_pbad = book.add_format(dict(base, align='center', bold=True, bg_color='#E2E8F0', font_color='#DC2626', num_format='0.0%'))
        f_gt_l = book.add_format(dict(base, align='center', bold=True, bg_color='#CBD5E1'))
        f_gt_n = book.add_format(dict(base, align='right', bold=True, bg_color='#CBD5E1', num_format='#,##0'))
        f_gt_p = book.add_format(dict(base, align='center', bold=True, bg_color='#CBD5E1', num_format='0.0%'))

        headers = ['STT', 'Miền', 'Mã Cửa Hàng', 'Tên nhân viên', 'ID HRM', 'Mã chức vụ', 'Target Cửa Hàng',
                   'Đã Phân Bổ NV theo %', 'Target NV']
        for c, w in enumerate([8, 14, 16, 34, 14, 14, 20, 20, 26]):
            ws.set_column(c, c, w)
        ws.merge_range(0, 0, 0, 8, 'LUG.VN - BẢNG PHÂN BỔ TARGET DOANH THU CỬA HÀNG & NHÂN VIÊN · THÁNG %s' % data['month_label'], f_title)
        ws.merge_range(1, 0, 1, 8, 'Nhập Target Cửa Hàng (cột G) và Tỷ trọng % (cột H) • Cột I tự động quy đổi số tiền (VNĐ)', f_sub)
        ws.set_row(0, 30)
        ws.set_row(1, 22)
        for c, h in enumerate(headers):
            ws.write(3, c, h, f_head)
        ws.set_row(3, 32)

        r = 4
        stt = 0
        g_target = g_amount = 0
        for s in stores:
            n = len(s['lines'])
            first = r
            s_amount = 0
            s_pct = 0.0
            for l in s['lines']:
                stt += 1
                amt = round(s['target'] * l['pct'] / 100.0)
                s_amount += amt
                s_pct += l['pct']
                ws.write_number(r, 0, stt, f_c)
                ws.write_string(r, 1, s['mien_label'], f_c)
                ws.write_string(r, 2, s['store'], f_cb)
                ws.write_string(r, 4, l.get('employee_code') or '', f_c)
                ws.write_string(r, 3, l['staff_name'] + (' (CHT)' if l['is_cht'] else ''), f_lb if l['is_cht'] else f_l)
                ws.write_string(r, 5, l.get('position') or '', f_c)
                ws.write_number(r, 7, l['pct'] / 100.0, f_pct)
                ws.write_number(r, 8, amt, f_money)
                ws.set_row(r, 22)
                r += 1
            if n > 1:
                ws.merge_range(first, 6, r - 1, 6, s['target'], f_tg)
            else:
                ws.write_number(first, 6, s['target'], f_tg)
            ws.merge_range(r, 0, r, 5, 'Tổng phân bổ cửa hàng %s' % s['store'], f_sum_l)
            ws.write_number(r, 6, s['target'], f_sum_n)
            ws.write_number(r, 7, round(s_pct, 2) / 100.0, f_sum_p if abs(s_pct - 100) < 0.01 else f_sum_pbad)
            ws.write_number(r, 8, s_amount, f_sum_n)
            ws.set_row(r, 22)
            r += 1
            g_target += s['target']
            g_amount += s_amount
        if data.get('show_grand'):
            ws.merge_range(r, 0, r, 5, 'TỔNG HỆ THỐNG', f_gt_l)
            ws.write_number(r, 6, g_target, f_gt_n)
            ws.write_number(r, 7, (g_amount / g_target) if g_target else 0, f_gt_p)
            ws.write_number(r, 8, g_amount, f_gt_n)
        ws.set_row(r, 26)
        ws.freeze_panes(4, 0)
        book.close()
        return {
            'name': 'Phan_Bo_Target_%s.xlsx' % data['month'].replace('-', ''),
            'data': base64.b64encode(buf.getvalue()).decode(),
        }


class StoreNvbhTargetLine(models.Model):
    _name = 'store.nvbh.target.line'
    _description = 'Phân bổ Target nhân viên theo %'
    _order = 'target_id, sequence, id'

    target_id = fields.Many2one('store.nvbh.target', string='Target cửa hàng', required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    staff_key = fields.Char(string='Khóa nhân viên', index=True)
    staff_name = fields.Char(string='Tên nhân viên', required=True)
    employee_code = fields.Char(string='ID')
    position = fields.Char(string='Chức vụ')
    is_cht = fields.Boolean(string='CHT')
    pct = fields.Float(string='Tỷ trọng (%)', digits=(6, 2))
