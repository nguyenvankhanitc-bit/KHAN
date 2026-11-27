# -*- coding: utf-8 -*-
"""Đánh giá Checklist toàn cửa hàng theo tuần (CHT + NVBH): ASM ghé thăm cửa hàng, chấm Đạt / T.Bình / Không đạt theo
nhóm công việc cho từng người (CHT, từng NVBH) và ghi nhận xét theo nhóm. Luồng phiếu: CHT check list -> ASM chốt;
NVBH check list -> CHT đánh giá -> ASM chốt điểm cuối cùng. Phiếu sau ngày ghé chuyển sang lần ghé tuần sau (hạn ASM hết tuần N+1)."""
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_nvbh_check import STEP_PREFIX, EVAL_RESULTS
from .store_nvbh_task import TASK_GROUPS

_PREFIX_RE = re.compile(r'^\s*([0-9]+|[IVXLC]+)\s*[.)–\-]\s*', re.IGNORECASE)


def group_norm(name):
    """Khóa so trùng nhóm công việc: bỏ số thứ tự đầu (01. / I. / 02 –), không phân biệt hoa thường."""
    return _PREFIX_RE.sub('', (name or '').strip()).strip().casefold() or 'khác'


class StoreChtVisitRow(models.Model):
    _name = 'store.cht.visit.row'
    _description = 'Kết quả / nhận xét của ASM theo nhóm công việc và nhân sự (lần ghé thăm)'

    visit_id = fields.Many2one('store.cht.visit', ondelete='cascade', required=True, index=True)
    row_key = fields.Char(required=True, index=True)  # khóa nhóm | khóa nhân sự
    group_name = fields.Char(string='Nhóm công việc')
    person = fields.Char(string='Nhân sự')
    result = fields.Selection(EVAL_RESULTS, string='KQ đánh giá')
    comment = fields.Char(string='Nhận xét của ASM theo nhóm')


class StoreChtVisit(models.Model):
    _inherit = 'store.cht.visit'

    row_ids = fields.One2many('store.cht.visit.row', 'visit_id', string='Nhận xét theo nhóm')


class StoreNvbhCheckWeek(models.Model):
    _inherit = 'store.nvbh.check'

    # ------------------------------------------------------------------
    # dữ liệu nguồn
    # ------------------------------------------------------------------
    @api.model
    def _sw_lines(self, start, end):
        """Dòng lịch CHT + NVBH trong [start, end) theo quyền xem lịch, lọc miền (context cht_mien).
        Người đăng nhập là CHT trên lịch: chỉ cửa hàng mình làm CHT."""
        Line = self.env['store.nvbh.schedule.line']
        hidden = self._hidden_kinds()
        if 'cht' in hidden:
            return Line
        dom = [('work_date', '>=', start), ('work_date', '<', end)]
        mien = self.env.context.get('cht_mien')
        if mien == 'other':
            dom.append(('store_id.mien', 'not in', ['Nam', 'ĐTT', 'Bắc']))
        elif mien:
            dom.append(('store_id.mien', '=', mien))
        lines = Line.search(dom, order='work_date, id')
        lines = lines.filtered(lambda l: self._schedule_kind(l) in ('cht', 'nvbh') and self._schedule_kind(l) not in hidden)
        emp = self.env.user.employee_id
        if emp:
            codes = {str(emp[f]).strip() for f in ('barcode', 'ma_cham_cong', 'ma_nv_ke_toan') if f in emp._fields and emp[f]}
            name = (emp.name or '').strip().casefold()
            me = lines.filtered(lambda l: self._schedule_kind(l) == 'cht' and ((l.employee_code or '').strip() in codes
                                                                              or (l.staff_name or '').strip().casefold() == name))
            if me:
                lines = lines.filtered(lambda l: l.store_id in me.store_id)
        return lines

    def _sw_asm_step(self):
        """Bước ASM người đăng nhập được chấm trên phiếu (đang đến lượt, hoặc vừa chấm còn trong hạn sửa đến 23h55)."""
        self.ensure_one()
        st = self._cht_my_step()
        return st if st and st['code'] == 'ASM' else None

    def _sw_asm_prefix(self):
        """Tiền tố cột kết quả của bước ASM trên phiếu (CHT: bước 1; NVBH: bước 2); None nếu luồng không có ASM."""
        self.ensure_one()
        for i, st in enumerate(self._approval_chain(), 1):
            if st['code'] == 'ASM':
                return STEP_PREFIX[i - 1]
        return None

    @api.model
    def _sw_scope(self, month, week, store_id, visit_date):
        start, end, _n = self._month_range(month)
        weeks = self._month_weeks(start, end)
        today = fields.Date.context_today(self)
        if week is None or week == '' or week is False:
            week = next((i for i, (a, b) in enumerate(weeks) if a <= today <= b), 0)
        week = max(0, min(int(week), len(weeks) - 1))
        a, b = weeks[week]
        mlines = self._sw_lines(start, end)
        stores = mlines.store_id.sorted(lambda s: (s.code or s.name or '').casefold())
        store = stores.filtered(lambda s: s.id == int(store_id or 0))[:1] or stores[:1]
        slines = mlines.filtered(lambda l: l.store_id == store)
        wlines = slines.filtered(lambda l: a <= l.work_date <= b)
        checks = self.search([('schedule_line_id', 'in', wlines.ids), ('kind', 'in', ('cht', 'nvbh'))], order='work_date, id')
        visit = fields.Date.to_date(visit_date) if visit_date else None
        if not visit:
            visit = min(max(today, a), b) if today >= a else a
        visit = min(max(visit, a), today) if today >= a else a
        carried = self.browse()
        if store:
            carried = self.search([('kind', 'in', ('cht', 'nvbh')), ('state', '=', 'pending_review'), ('store_id', '=', store.id),
                                   ('work_date', '<', a), ('work_date', '>=', a - timedelta(days=42))], order='work_date, id')
            carried = carried.filtered(lambda c: c._sw_asm_step())
        in_scope = checks.filtered(lambda c: c.work_date <= visit) | carried
        evaluable = in_scope.filtered(lambda c: c._sw_asm_step())
        later = checks.filtered(lambda c: c.work_date > visit and c.state != 'approved')
        return {'start': start, 'weeks': weeks, 'week': week, 'a': a, 'b': b, 'mlines': mlines, 'stores': stores, 'store': store,
                'slines': slines, 'checks': checks, 'visit': visit, 'carried': carried, 'evaluable': evaluable, 'later': later}

    @api.model
    def _sw_person(self, line):
        pos = (line.position or ('CHT' if self._schedule_kind(line) == 'cht' else 'NVBH')).strip().upper()
        kind = self._schedule_kind(line)
        name = (line.staff_name or '').strip()
        short = name.split()[-1].capitalize() if name else '?'
        return {'key': self._cht_line_key(line), 'name': name, 'short': short, 'pos': pos, 'is_cht': kind == 'cht'}

    @api.model
    def _sw_store_label(self, store, lines):
        people, seen = [], set()
        for l in lines.filtered(lambda x: x.store_id == store).sorted(lambda x: (self._schedule_kind(x) != 'cht', x.staff_name or '')):
            p = self._sw_person(l)
            if p['key'] in seen:
                continue
            seen.add(p['key'])
            people.append('%s - %s' % (p['short'], 'CHT' if p['is_cht'] else p['pos']))
        label = store.code or store.name or ''
        if people:
            label += ' (%s%s)' % (' & '.join(people[:3]), ' …' if len(people) > 3 else '')
        return label

    # ------------------------------------------------------------------
    # trang Đánh giá Checklist toàn cửa hàng
    # ------------------------------------------------------------------
    @api.model
    def get_store_week(self, month=None, week=None, store_id=None, visit_date=None):
        sc = self._sw_scope(month, week, store_id, visit_date)
        store, checks, carried, evaluable = sc['store'], sc['checks'], sc['carried'], sc['evaluable']
        res = {
            'month': sc['start'].strftime('%Y-%m'), 'week': sc['week'],
            'weeks': [{'idx': i, 'label': 'Tuần %s' % (i + 1), 'range': '%s – %s' % (a.strftime('%d'), b.strftime('%d/%m')),
                       'full': '%s – %s' % (a.strftime('%d'), b.strftime('%d/%m/%Y'))} for i, (a, b) in enumerate(sc['weeks'])],
            'stores': [{'id': s.id, 'label': self._sw_store_label(s, sc['mlines'])} for s in sc['stores']],
            'store_id': store.id or False, 'store_code': store.code or store.name or '',
            'visit_date': str(sc['visit']), 'groups': [], 'people': [], 'kpi': {}, 'carried': [], 'can_eval': False,
            'n_pending': 0, 'n_reedit': 0, 'n_later': 0, 'reedit_until': '', 'locked_at': '', 'comment': '', 'notes': {},
            'can_comment': False, 'today': False,
        }
        if not store:
            return res
        grp_seq = {}
        for g in self.env['store.cht.task.group'].sudo().with_context(active_test=False).search([]):
            grp_seq.setdefault(group_norm(g.name), (0, g.sequence, g.id))
        for g in self.env['store.nvbh.task.group'].sudo().with_context(active_test=False).search([]):
            grp_seq.setdefault(group_norm(g.name), (0, g.sequence, g.id))
        for i, (_k, label) in enumerate(TASK_GROUPS):
            grp_seq.setdefault(group_norm(label), (1, i, 0))
        groups = {}
        people = {}
        for c in checks | carried:
            own = c in checks
            line = c.schedule_line_id
            p = self._sw_person(line) if line else {'key': (c.staff_name or '').casefold(), 'name': c.staff_name or '', 'short': c.staff_name or '',
                                                     'pos': '', 'is_cht': c.kind == 'cht'}
            pp = people.setdefault(p['key'], dict(
                p, n_checks=0, n_checked=0, tasks=0, done=0, errors=0, hours=0.0, points=0.0, std_points=0.0,
                n_eval=0, cht_sum=0.0, cht_cnt=0, asm_sum=0.0, asm_cnt=0, dates=set(),
                uncheck_dates=set(), uneval_dates=set(),
                pending=0, wait_cht=0, approved=0, not_sent=0,
            ))
            if own:
                pp['n_checks'] += 1
                if c.cnt_done > 0:
                    pp['n_checked'] += 1
                    if c.work_date:
                        pp['dates'].add(c.work_date)
                elif c.work_date:
                    pp['uncheck_dates'].add(c.work_date)
                pp['tasks'] += c.cnt_total
                pp['done'] += c.cnt_done
                pp['errors'] += c.error_total
                pp['hours'] += c.shift_id.hours or 0.0
                p_cht = c._step_points('CHT')
                if p_cht is not None:
                    pp['cht_sum'] += p_cht
                    pp['cht_cnt'] += 1
                p_asm = c._step_points('ASM')
                if p_asm is not None:
                    pp['asm_sum'] += p_asm
                    pp['asm_cnt'] += 1
                if c._fully_evaluated() or p_asm is not None:
                    pp['points'] += c.points if c._fully_evaluated() else p_asm
                    pp['std_points'] += sum(c.line_ids.mapped('max_score'))
                    pp['n_eval'] += 1
                elif c.work_date and c.cnt_done > 0:
                    pp['uneval_dates'].add(c.work_date)
            if c in evaluable and c.state == 'pending_review':
                pp['pending'] += 1
            elif c.state == 'pending_review':
                pp['wait_cht'] += 1
            elif c.state == 'approved':
                pp['approved'] += 1
            else:
                pp['not_sent'] += 1
            pre = c._sw_asm_prefix()
            # Bảng 2 chỉ hiển thị các dòng chưa được ASM chấm (chưa có asm_eval_result) của các phiếu đến ngày ghé thăm
            if c.work_date and c.work_date > sc['visit'] and own:
                continue
            if not (c.submitted or c.cnt_done > 0):
                continue
            for l in c.line_ids:
                if c._asm_line_result(l)[0]:  # ASM đã chấm (trong phiếu hoặc tuần trước)
                    continue
                gk = group_norm(l.sub_category)
                g = groups.setdefault(gk, {'key': gk, 'name': l.sub_category or 'Khác', 'rows': {}, 'tasks': []})
                row = g['rows'].setdefault(p['key'], {'key': '%s|%s' % (gk, p['key']), 'person': p['key'], 'lines': 0, 'done': 0, 'max': 0.0,
                                                      'pts': 0.0, 'errors': 0, 'results': set(), 'max_eval': 0.0, 'max_done_eval': 0.0, 'n_eval': 0})
                if own:
                    row['lines'] += 1
                    row['done'] += 1 if l.is_done else 0
                    row['max'] += l.max_score or 0.0
                    row['pts'] += l.actual_score or 0.0
                    row['errors'] += l.error_count or 0
                    if l.name not in g['tasks']:
                        g['tasks'].append(l.name)
                if c in evaluable:
                    row['n_eval'] += 1
                    row['max_eval'] += l.max_score or 0.0
                    row['max_done_eval'] += (l.max_score or 0.0) if l.is_done else 0.0
                    row['results'].add(l[pre + 'eval_result'] or '' if pre is not None else '')
        order = lambda k: (not people[k]['is_cht'], people[k]['name'].casefold())  # noqa: E731
        Rating = self.env['store.nvbh.rating']
        visit = self._sw_visit(sc, create=False)
        is_asm = self._sw_is_asm(store)
        out = []
        for g in sorted(groups.values(), key=lambda g: grp_seq.get(g['key'], (2, 0, 0)) + (g['name'],)):
            rows = []
            g_pts = g_max = 0.0
            g_err = 0
            for pk in sorted(g['rows'], key=order):
                r = g['rows'][pk]
                g_pts += r['pts']
                g_max += r['max']
                g_err += r.get('errors', 0)
                rs = r.pop('results') - {''}
                res_val = rs.pop() if len(rs) == 1 else ''
                rows.append(dict(r, result=res_val, rate=round(100.0 * r['pts'] / r['max'], 1) if r['max'] else 0.0,
                                 pts=round(r['pts'], 2), name=people[pk]['short'], full=people[pk]['name'], pos=people[pk]['pos'],
                                 is_cht=people[pk]['is_cht'], can_eval=r['n_eval'] > 0 or is_asm))
            g_rate = round(100.0 * g_pts / g_max, 1) if g_max else 0.0
            lvl = Rating.rating_for(g_rate) if g_max else Rating.browse()
            out.append({
                'key': g['key'], 'name': g['name'], 'desc': ', '.join(g['tasks'][:3]), 'rows': rows,
                'errors': g_err, 'rank_label': lvl.name if lvl else '', 'rank_tone': lvl.tone if lvl else '',
            })
        res['groups'] = out
        plist = sorted(people.values(), key=lambda p: (not p['is_cht'], p['name'].casefold()))
        for p in plist:
            p['dates'] = [d.strftime('%d/%m') for d in sorted(p['dates'])]
            uncheck = [d.strftime('%d/%m') for d in sorted(p.pop('uncheck_dates'))]
            uneval = [d.strftime('%d/%m') for d in sorted(p.pop('uneval_dates'))]
            parts = []
            if uneval:
                parts.append('Ngày %s chưa đánh giá' % ', '.join(uneval))
            if uncheck:
                parts.append('Ngày %s chưa check list' % ', '.join(uncheck))
            p['note'] = '; '.join(parts)
            p['n_uneval'] = len(uneval) + len(uncheck)
            p['hours'] = round(p['hours'], 1)
            p['std_points'] = round(p['std_points'], 1)
            p['points'] = round(p['points'], 1) if p['n_eval'] else None
            p['pts_cht'] = round(p['cht_sum'], 1) if p['cht_cnt'] else None
            p['pts_asm'] = round(p['asm_sum'], 1) if p['asm_cnt'] else None
        res['people'] = plist
        pts_vals = [p['points'] for p in plist if p['points'] is not None]
        cht_vals = [p['pts_cht'] for p in plist if p['pts_cht'] is not None]
        asm_vals = [p['pts_asm'] for p in plist if p['pts_asm'] is not None]
        res['people_total'] = {
            'n_checks': sum(p['n_checks'] for p in plist),
            'n_checked': sum(p['n_checked'] for p in plist),
            'tasks': sum(p['tasks'] for p in plist),
            'done': sum(p['done'] for p in plist),
            'errors': sum(p['errors'] for p in plist),
            'hours': round(sum(p['hours'] for p in plist), 1),
            'points': round(sum(pts_vals), 1) if pts_vals else None,
            'std_points': round(sum(p['std_points'] for p in plist), 1),
            'pts_cht': round(sum(cht_vals), 1) if cht_vals else None,
            'pts_asm': round(sum(asm_vals), 1) if asm_vals else None,
            'n_uneval': sum(p['n_uneval'] for p in plist),
        }
        approved = checks.filtered(lambda c: c._fully_evaluated())
        res['kpi'] = {
            'tasks': sum(checks.mapped('cnt_total')), 'hours': round(sum(c.shift_id.hours or 0.0 for c in checks), 2),
            'done': sum(checks.mapped('cnt_done')), 'errors': sum(checks.mapped('error_total')),
            'points': round(sum(approved.mapped('points')), 2), 'max_points': sum(sum(c.line_ids.mapped('max_score')) for c in approved),
            'done_by': ' | '.join('%s: %s' % (p['short'], p['done']) for p in res['people'] if p['n_checks']),
        }
        reedit = evaluable.filtered(lambda c: c.state == 'approved')
        res['can_eval'] = bool(evaluable) or (is_asm and bool(out))
        res['n_pending'] = len(evaluable - reedit) or (len(out) if (is_asm and out) else 0)
        res['n_reedit'] = len(reedit)
        res['n_carried'] = len(carried.filtered(lambda c: c in evaluable))
        res['n_later'] = len(sc['later'].filtered(lambda c: c.state == 'pending_review'))
        until = [u for u in (c._reedit_until(c.step_done) for c in reedit) if u]
        res['reedit_until'] = fields.Datetime.context_timestamp(self, min(until)).strftime('%H:%M %d/%m') if until else ''
        locked = []
        for c in checks.filtered(lambda c: c.state == 'approved') - reedit:
            log = c.step_log_ids.filtered(lambda l: l.step_no == c.step_done and l.user_id == self.env.user)
            u = c._reedit_until(c.step_done) if log else False
            if u:
                locked.append(u)
        res['locked_at'] = fields.Datetime.context_timestamp(self, max(locked)).strftime('%H:%M %d/%m') if locked else ''
        res['carried'] = [{'id': c.id, 'date': c.work_date.strftime('%d/%m'), 'name': c.staff_name or '',
                           'week_label': self._cht_week_label(c.work_date)} for c in carried]
        res['can_comment'] = is_asm or self._sw_can_comment(checks | carried)
        res['comment'] = visit.comment or '' if visit else ''
        res['notes'] = {r.row_key: r.comment or '' for r in visit.row_ids} if visit else {}
        res['visits'] = [{'date': v.visit_date.strftime('%d/%m/%Y'), 'user': v.user_id.name or '', 'comment': v.comment or ''}
                         for v in self.env['store.cht.visit'].sudo().search([('staff_key', '=', 'store:%s' % store.id),
                                                                            ('visit_date', '>=', sc['a']), ('visit_date', '<=', sc['b'])],
                                                                           order='visit_date, id')]
        # ASM phụ trách cửa hàng (manager_id trên hr.store), không có thì người đăng nhập
        asm = (store.manager_id.name if store and store.manager_id else '') or next(
            (st['employee'].name for c in (checks | carried) for st in c._approval_chain() if st['code'] == 'ASM' and st.get('employee')), '')
        res['asm_name'] = asm or self.env.user.name
        res['people_text'] = ' & '.join(('CHT ' if p['is_cht'] else '%s ' % (p['pos'] or 'NVBH')) + (p['name'] or '').title()
                                        for p in res['people'])
        # CHT của cửa hàng (mở Bảng checklist tháng / check list hôm nay)
        cht = next((p for p in res['people'] if p['is_cht']), None)
        res['cht_key'] = cht['key'] if cht else ''
        today = fields.Date.context_today(self)
        tl = sc['slines'].filtered(lambda l: l.work_date == today and self._schedule_kind(l) == 'cht')[:1]
        res['today'] = {'line_id': tl.id, 'store_id': tl.store_id.id, 'ymd': str(today)} if tl else False
        return res

    @api.model
    def _sw_is_asm(self, store):
        """Người đăng nhập có quyền ASM đánh giá tổng theo tuần cho cửa hàng (Admin / Quản lý / ASM phụ trách cửa hàng / nhân sự cấp ASM trở lên)."""
        user = self.env.user
        if user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager'):
            return True
        if store and store.manager_id and store.manager_id.user_id and store.manager_id.user_id.id == user.id:
            return True
        emp = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        return bool(emp and emp._checklist_effective_level() >= 3)

    @api.model
    def _sw_can_comment(self, checks):
        user = self.env.user
        if user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager'):
            return bool(checks)
        if any(c.store_id and self._sw_is_asm(c.store_id) for c in checks):
            return True
        for c in checks:
            for st in c._approval_chain():
                if st['code'] == 'ASM' and st.get('user') and st['user'].id == user.id:
                    return True
        return False

    @api.model
    def _sw_visit(self, sc, create=True):
        Visit = self.env['store.cht.visit'].sudo()
        key = 'store:%s' % sc['store'].id
        v = Visit.search([('staff_key', '=', key), ('visit_date', '=', sc['visit']), ('user_id', '=', self.env.user.id)], order='id desc', limit=1)
        if not v and not create:
            v = Visit.search([('staff_key', '=', key), ('visit_date', '>=', sc['a']), ('visit_date', '<=', sc['b'])], order='visit_date desc, id desc', limit=1)
        if not v and create:
            v = Visit.create({'staff_key': key, 'staff_name': sc['store'].display_name, 'store_id': sc['store'].id,
                              'visit_date': sc['visit'], 'user_id': self.env.user.id})
        return v

    @api.model
    def _sw_save_visit(self, sc, comment, notes, results, evaluated):
        v = self._sw_visit(sc)
        text = '\n'.join(ln.rstrip() for ln in (comment or '').strip().splitlines()) or False
        vals = {'comment': text}
        if evaluated:
            vals['check_ids'] = [(4, c.id) for c in evaluated]
        v.write(vals)
        keys = set(notes or {}) | set(results or {})
        valid = {k for k, _l in EVAL_RESULTS}
        old = {r.row_key: r for r in v.row_ids}
        for k in keys:
            vals = {'comment': ((notes or {}).get(k) or '').strip() or False}
            if (results or {}).get(k) in valid:
                vals['result'] = results[k]
            if k in old:
                old[k].write(vals)
            elif vals['comment'] or vals.get('result'):
                v.write({'row_ids': [(0, 0, dict(vals, row_key=k, group_name=k.split('|')[0], person=k.split('|', 1)[-1]))]})
        if text and evaluated:
            evaluated.sudo().write({'week_comment': text})
        return v

    @api.model
    def save_store_week(self, month, week, store_id, results, notes=None, comment=None, visit_date=None):
        """Lưu lần ASM ghé thăm cửa hàng: áp KQ Đạt / T.Bình / Không đạt theo (nhóm, nhân sự) cho mọi dòng của các phiếu CHT / NVBH
        trong phạm vi (đã gửi đến ngày ghé + chuyển tiếp từ tuần trước) đang đến lượt ASM; lưu nhận xét theo nhóm và nhận xét chung."""
        valid = {k for k, _l in EVAL_RESULTS}
        results = {k: v for k, v in (results or {}).items() if v in valid}
        sc = self._sw_scope(month, week, store_id, visit_date)
        if not sc['store']:
            raise UserError(_('Chưa chọn cửa hàng.'))
        evaluated = self.browse()
        for c in sc['evaluable']:
            step = c._sw_asm_step()
            if not step:
                continue
            pkey = self._cht_line_key(c.schedule_line_id) if c.schedule_line_id else (c.staff_name or '').casefold()
            pre = STEP_PREFIX[step['no'] - 1]
            changes, missing = [], set()
            for l in c.line_ids:
                k = '%s|%s' % (group_norm(l.sub_category), pkey)
                if k not in results:
                    missing.add('%s – %s' % (l.sub_category or 'Khác', c.staff_name or ''))
                    continue
                changes.append({'id': l.id, 'result': results[k], 'detail': l[pre + 'error_detail'] or ''})
            if missing:
                raise UserError(_('Chưa chọn KQ đánh giá cho: %s') % '; '.join(sorted(missing)))
            self.save_step_evaluation(c.id, step['no'], changes)
            evaluated |= c
        if not evaluated:
            if not self._sw_is_asm(sc['store']) and not self._sw_can_comment(sc['checks'] | sc['carried']):
                raise AccessError(_('Không có phiếu nào đến ngày ghé thăm đang chờ bạn đánh giá.'))
            # Luồng mới: ASM đánh giá tổng theo tuần -> ghi kết quả vào cột bước ASM ('asm_eval_result')
            # của các phiếu CHT / NVBH trong tuần để Bảng checklist Tổng & Danh sách checklist NV tự cập nhật Điểm ASM đánh giá
            if results:
                in_scope = sc['checks'].filtered(lambda c: c.work_date <= sc['visit']) | sc['carried']
                for c in in_scope:
                    if not (c.submitted or c.cnt_done > 0):
                        continue
                    pkey = self._cht_line_key(c.schedule_line_id) if c.schedule_line_id else (c.staff_name or '').casefold()
                    touched = False
                    for l in c.line_ids:
                        if c._asm_line_result(l)[0]:  # đã chấm ở lần trước -> giữ nguyên, không ghi đè
                            continue
                        k = '%s|%s' % (group_norm(l.sub_category), pkey)
                        if k in results:
                            l.sudo().write({'asm_eval_result': results[k], 'asm_reviewer_id': self.env.user.id})
                            touched = True
                    if touched:
                        if c.state != 'approved' and c.line_ids and all(c._asm_line_result(l)[0] for l in c.line_ids):
                            c.sudo().write({'state': 'approved', 'approved_date': fields.Datetime.now()})
                        evaluated |= c
        self._sw_save_visit(sc, comment, notes, results, evaluated or sc['checks'])
        return {'done': len(evaluated), 'dates': sorted({c.work_date.strftime('%d/%m') for c in evaluated})}
