# -*- coding: utf-8 -*-
import base64
import calendar
from datetime import date, datetime, time, timedelta
import io
import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_audit_staff import CHECK_MENUS


class StoreNvbhRevenue(models.Model):
    """Doanh thu hằng ngày & tổng hợp tháng của cửa hàng (Checklist NVBH > Doanh thu):
    - Tab 1 (Doanh thu theo ngày): tự động lấy Họ và tên NV + ID từ Lịch xếp ca hằng ngày,
      nhập doanh thu xong bấm nút Lưu mới ghi nhận, bấm vào tên NV hiện nút Chỉnh sửa, tự khóa sau 48h.
    - Tab 2 (Doanh Thu Tháng): thể hiện tất cả doanh thu cửa hàng trong tháng (kèm chi tiết NV & ngày)."""
    _name = 'store.nvbh.revenue'
    _inherit = 'store.perm.mixin'
    _description = 'Doanh thu nhân viên bán hàng theo ngày'
    _order = 'work_date desc, store_id, sequence, id'
    _perm_manager_ops = ('unlink',)
    LOCK_HOURS = 48

    def _perm_key(self):
        return 'nvbh_revenue'

    @api.model
    def _perm_key_vals(self, vals):
        return 'nvbh_revenue'

    @api.model
    def _check_perm(self, op):
        rights = self.env['store.perm.rule']._rights()
        if rights is not None and not (rights.get('nvbh_revenue') or {}).get(op):
            raise AccessError(_('Bạn không có quyền thực hiện thao tác này tại mục Doanh thu.'))

    schedule_line_id = fields.Many2one('store.nvbh.schedule.line', string='Dòng lịch xếp ca', ondelete='set null', index=True)
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True)
    mien = fields.Selection(related='store_id.mien', string='Miền', store=True, index=True)
    work_date = fields.Date(string='Ngày', required=True, default=fields.Date.context_today, index=True)
    staff_name = fields.Char(string='Họ và tên NV', required=True, index=True)
    employee_code = fields.Char(string='ID', index=True)
    position = fields.Char(string='Chức vụ')
    shift_code = fields.Char(string='Mã ca')
    sequence = fields.Integer(string='Thứ tự', default=10)
    revenue = fields.Float(string='Doanh thu', digits=(16, 0), default=0.0)
    is_saved = fields.Boolean(string='Đã lưu', default=False, index=True)
    first_saved_at = fields.Datetime(string='Lưu lần đầu lúc', readonly=True)
    saved_at = fields.Datetime(string='Cập nhật lúc', readonly=True)
    saved_by = fields.Many2one('res.users', string='Người lưu', readonly=True)

    def init(self):
        self.env.cr.execute("""
            UPDATE store_nvbh_revenue
               SET is_saved = TRUE,
                   first_saved_at = COALESCE(first_saved_at, write_date, NOW() AT TIME ZONE 'UTC'),
                   saved_at = COALESCE(saved_at, write_date, NOW() AT TIME ZONE 'UTC'),
                   saved_by = COALESCE(saved_by, write_uid)
             WHERE COALESCE(revenue, 0) > 0 AND COALESCE(is_saved, FALSE) = FALSE
        """)

    @api.model
    def _user_tz(self):
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'Asia/Ho_Chi_Minh'
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.timezone('Asia/Ho_Chi_Minh')

    @api.model
    def _fmt_dt(self, dt_utc, tz=None):
        if not dt_utc:
            return ''
        tz = tz or self._user_tz()
        return pytz.utc.localize(dt_utc).astimezone(tz).strftime('%H:%M %d/%m/%Y')

    def _lock_info(self, now_utc=None, tz=None):
        """Trả về (is_locked, deadline_utc, lock_label): tự động khóa sau 48h."""
        self.ensure_one()
        now_utc = now_utc or fields.Datetime.now()
        tz = tz or self._user_tz()
        if self.is_saved and self.first_saved_at:
            deadline_utc = self.first_saved_at + timedelta(hours=self.LOCK_HOURS)
        else:
            end_local = tz.localize(datetime.combine(self.work_date + timedelta(days=2), time(23, 59, 59)))
            deadline_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return (now_utc >= deadline_utc), deadline_utc, self._fmt_dt(deadline_utc, tz)

    def _row_payload(self, now_utc=None, tz=None):
        self.ensure_one()
        now_utc = now_utc or fields.Datetime.now()
        tz = tz or self._user_tz()
        st = self.store_id
        sname = st.display_name or st.name or '-'
        is_locked, _dl, lock_label = self._lock_info(now_utc=now_utc, tz=tz)
        return {
            'id': self.id,
            'staff_name': self.staff_name or '',
            'employee_code': self.employee_code or '',
            'store_id': st.id,
            'store': sname,
            'mien': st.mien or '',
            'shift_code': self.shift_code or '',
            'position': self.position or '',
            'revenue': round(self.revenue or 0.0),
            'work_date': self.work_date.strftime('%Y-%m-%d'),
            'date_label': self.work_date.strftime('%d/%m/%Y'),
            'is_saved': bool(self.is_saved),
            'is_locked': bool(is_locked),
            'lock_until': lock_label,
            'saved_at': self._fmt_dt(self.saved_at, tz),
            'saved_by': self.saved_by.name or '',
        }

    @api.model
    def _sync_date(self, target_date=None):
        """Đồng bộ danh sách nhân sự đi làm trong ngày `target_date` từ Lịch xếp ca sang bảng Doanh thu."""
        day = fields.Date.to_date(target_date) if target_date else fields.Date.context_today(self)
        Line = self.env['store.nvbh.schedule.line'].sudo()
        Check = self.env['store.nvbh.check'].sudo()
        sched_lines = Line.search([('work_date', '=', day)], order='store_id, sequence, id')

        active_map = {}  # (store_id, staff_name_norm) -> schedule_line
        for ln in sched_lines:
            if not ln.store_id:
                continue
            scode = (ln.shift_id.code or '').strip().upper()
            if not scode or scode == 'OFF':
                continue
            if Check._schedule_kind(ln) not in ('nvbh', 'cht'):
                continue
            nm = (ln.staff_name or '').strip()
            if not nm:
                continue
            key = (ln.store_id.id, nm.casefold())
            if key not in active_map:
                active_map[key] = ln

        existing = self.sudo().search([('work_date', '=', day)])
        by_key = {}
        for rec in existing:
            key = (rec.store_id.id, (rec.staff_name or '').strip().casefold())
            by_key.setdefault(key, []).append(rec)

        to_create = []
        for key, ln in active_map.items():
            nm = (ln.staff_name or '').strip()
            code = (ln.employee_code or '').strip()
            pos = (ln.position or '').strip()
            sh = (ln.shift_id.code or '').strip()
            recs = by_key.pop(key, None)
            if recs:
                main = recs[0]
                upd = {}
                if main.schedule_line_id.id != ln.id:
                    upd['schedule_line_id'] = ln.id
                if main.staff_name != nm:
                    upd['staff_name'] = nm
                if (main.employee_code or '') != code:
                    upd['employee_code'] = code
                if (main.position or '') != pos:
                    upd['position'] = pos
                if (main.shift_code or '') != sh:
                    upd['shift_code'] = sh
                if main.sequence != (ln.sequence or 10):
                    upd['sequence'] = ln.sequence or 10
                if upd:
                    main.sudo().write(upd)
            else:
                to_create.append({
                    'schedule_line_id': ln.id,
                    'store_id': ln.store_id.id,
                    'work_date': day,
                    'staff_name': nm,
                    'employee_code': code,
                    'position': pos,
                    'shift_code': sh,
                    'sequence': ln.sequence or 10,
                    'revenue': 0.0,
                    'is_saved': False,
                })
        if to_create:
            self.sudo().create(to_create)

        stale = self.browse()
        for leftover in by_key.values():
            for rec in leftover:
                if not rec.revenue and not rec.is_saved:
                    stale |= rec
        if stale:
            stale.sudo().unlink()

    @api.model
    def _cron_sync_today_revenue(self):
        """Cron hằng ngày: tự điền sẵn Họ và tên NV + ID vào bảng Doanh thu của ngày hôm nay theo Lịch xếp ca."""
        self._sync_date(fields.Date.context_today(self))

    @api.model
    def _scope_domain(self):
        rule = self.env['store.staff.view.rule']._staff_domain(CHECK_MENUS)
        if rule is not None:
            return rule
        scope = self.env['store.audit']._user_store_scope()
        if scope is not None:
            return [('store_id', 'in', scope)]
        return []

    @api.model
    def _allowed_stores(self):
        Store = self.env['hr.store'].sudo()
        ids = self.env['store.staff.view.rule']._scope_store_ids(CHECK_MENUS)
        if ids is True:
            return Store.search([], order='name')
        if ids is not None:
            return Store.search([('id', 'in', list(ids))], order='name')
        scope = self.env['store.audit']._user_store_scope()
        if scope is not None:
            return Store.search([('id', 'in', scope)], order='name')
        return Store.search([], order='name')

    @api.model
    def _month_bounds(self, month_str=None):
        today = fields.Date.context_today(self)
        y, m = today.year, today.month
        if month_str and '-' in str(month_str):
            try:
                parts = str(month_str).strip().split('-')
                y, m = int(parts[0]), int(parts[1])
            except Exception:
                pass
        last_day = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last_day), '%04d-%02d' % (y, m), '%02d/%04d' % (m, y), last_day

    @api.model
    def get_revenue_page(self, work_date=None, mien=None, store_id=None):
        self._check_perm('read')
        day = fields.Date.to_date(work_date) if work_date else fields.Date.context_today(self)
        self._sync_date(day)

        base_dom = [('work_date', '=', day)] + list(self._scope_domain())
        all_day = self.sudo().search(base_dom, order='store_id, sequence, id')
        now_utc = fields.Datetime.now()
        tz = self._user_tz()

        store_opts_map = {}
        rows = []
        for rec in all_day:
            st = rec.store_id
            smien = st.mien or ''
            if mien and smien != mien:
                continue
            sname = st.display_name or st.name or '-'
            store_opts_map[st.id] = sname
            if store_id and st.id != int(store_id):
                continue
            rows.append(rec._row_payload(now_utc=now_utc, tz=tz))

        rows.sort(key=lambda r: (r['store'].casefold(), r['staff_name'].casefold(), r['id']))
        for idx, r in enumerate(rows, 1):
            r['stt'] = idx

        rights = self.env['store.perm.rule']._rights()
        is_mgr = self.env.user.has_group('base.group_system') or self.env.user.has_group('store_checklist.group_store_manager')
        can_edit = bool(is_mgr or (rights is None) or (rights.get('nvbh_revenue') or {}).get('write'))
        can_export = bool(is_mgr or (rights is None) or (rights.get('nvbh_revenue') or {}).get('export'))

        return {
            'date': day.strftime('%Y-%m-%d'),
            'date_label': day.strftime('%d/%m/%Y'),
            'can_edit': can_edit,
            'can_export': can_export,
            'lock_hours': self.LOCK_HOURS,
            'store_opts': [{'id': k, 'name': v} for k, v in sorted(store_opts_map.items(), key=lambda x: x[1].casefold())],
            'rows': rows,
        }

    @api.model
    def get_revenue_month(self, month=None, mien=None, store_id=None):
        """Tab 2 — Doanh Thu Tháng: thể hiện tất cả doanh thu cửa hàng trong tháng."""
        self._check_perm('read')
        start_d, end_d, m_key, m_label, days_in_month = self._month_bounds(month)
        allowed = self._allowed_stores()
        if mien:
            allowed = allowed.filtered(lambda s: (s.mien or '') == mien)

        store_opts = [{'id': s.id, 'name': s.display_name or s.name or '-'}
                      for s in sorted(allowed, key=lambda x: (x.display_name or x.name or '').casefold())]

        target_stores = allowed
        if store_id:
            target_stores = allowed.filtered(lambda s: s.id == int(store_id))

        recs = self.sudo().search([
            ('work_date', '>=', start_d),
            ('work_date', '<=', end_d),
            ('store_id', 'in', target_stores.ids),
        ], order='work_date, store_id, sequence, id') if target_stores else self.browse()

        # Cũng lấy số nhân sự được xếp ca trong tháng theo từng cửa hàng để hiển thị đầy đủ
        sched_lines = self.env['store.nvbh.schedule.line'].sudo().search([
            ('work_date', '>=', start_d),
            ('work_date', '<=', end_d),
            ('store_id', 'in', target_stores.ids),
        ]) if target_stores else self.env['store.nvbh.schedule.line'].browse()
        Check = self.env['store.nvbh.check'].sudo()
        sched_staff_by_store = {}
        for ln in sched_lines:
            scode = (ln.shift_id.code or '').strip().upper()
            if not scode or scode == 'OFF':
                continue
            if Check._schedule_kind(ln) not in ('nvbh', 'cht'):
                continue
            nm = (ln.staff_name or '').strip()
            if nm:
                sched_staff_by_store.setdefault(ln.store_id.id, set()).add(nm.casefold())

        by_store = {s.id: [] for s in target_stores}
        for rec in recs:
            if rec.store_id.id in by_store:
                by_store[rec.store_id.id].append(rec)

        store_rows = []
        grand_total = 0
        for st in target_stores:
            s_recs = by_store.get(st.id, [])
            sname = st.display_name or st.name or '-'
            smien = st.mien or ''
            asm_name = st.manager_id.name or ''

            staff_agg = {}  # norm_name -> {'staff_name', 'employee_code', 'days': set(), 'revenue': int}
            day_agg = {}    # work_date -> {'date_label', 'staff': set(), 'revenue': int, 'has_saved': bool}
            st_rev = 0

            for rec in s_recs:
                rv_amt = round(rec.revenue or 0.0)
                st_rev += rv_amt
                nm = (rec.staff_name or '').strip() or '-'
                nkey = nm.casefold()
                sp = staff_agg.setdefault(nkey, {
                    'staff_name': nm,
                    'employee_code': rec.employee_code or '',
                    'days': set(),
                    'revenue': 0,
                })
                if not sp['employee_code'] and rec.employee_code:
                    sp['employee_code'] = rec.employee_code
                sp['revenue'] += rv_amt
                if rec.is_saved or rv_amt > 0:
                    sp['days'].add(rec.work_date)

                dp = day_agg.setdefault(rec.work_date, {
                    'work_date': rec.work_date.strftime('%Y-%m-%d'),
                    'date_label': rec.work_date.strftime('%d/%m/%Y'),
                    'staff': set(),
                    'revenue': 0,
                    'has_saved': False,
                })
                dp['staff'].add(nkey)
                dp['revenue'] += rv_amt
                if rec.is_saved or rv_amt > 0:
                    dp['has_saved'] = True

            grand_total += st_rev
            all_staff_keys = set(staff_agg.keys()) | sched_staff_by_store.get(st.id, set())

            staff_list = sorted(
                [
                    {
                        'staff_name': v['staff_name'],
                        'employee_code': v['employee_code'],
                        'days': len(v['days']),
                        'revenue': v['revenue'],
                    }
                    for v in staff_agg.values()
                ],
                key=lambda x: (-x['revenue'], x['staff_name'].casefold()),
            )
            for idx, sr in enumerate(staff_list, 1):
                sr['stt'] = idx

            day_list = [
                {
                    'work_date': d['work_date'],
                    'date_label': d['date_label'],
                    'staff_count': len(d['staff']),
                    'revenue': d['revenue'],
                }
                for _dt, d in sorted(day_agg.items(), key=lambda x: x[0])
                if d['has_saved'] or d['revenue'] > 0
            ]

            store_rows.append({
                'id': st.id,
                'store': sname,
                'mien': smien,
                'asm': asm_name,
                'staff_count': len(all_staff_keys),
                'days_with_rev': len(day_list),
                'days_in_month': days_in_month,
                'revenue': st_rev,
                'staff_rows': staff_list,
                'day_rows': day_list,
            })

        store_rows.sort(key=lambda r: (0 if r['revenue'] > 0 else 1, -r['revenue'], r['store'].casefold()))
        for idx, r in enumerate(store_rows, 1):
            r['stt'] = idx
            r['share_pct'] = round(r['revenue'] * 100.0 / grand_total, 1) if grand_total > 0 else 0.0

        rights = self.env['store.perm.rule']._rights()
        is_mgr = self.env.user.has_group('base.group_system') or self.env.user.has_group('store_checklist.group_store_manager')
        can_export = bool(is_mgr or (rights is None) or (rights.get('nvbh_revenue') or {}).get('export'))

        return {
            'month': m_key,
            'month_label': m_label,
            'days_in_month': days_in_month,
            'can_export': can_export,
            'total_revenue': grand_total,
            'active_store_count': sum(1 for r in store_rows if r['revenue'] > 0),
            'total_store_count': len(store_rows),
            'store_opts': store_opts,
            'stores': store_rows,
        }

    @api.model
    def save_revenue_batch(self, items):
        """Lưu danh sách doanh thu khi người dùng bấm nút Lưu; chặn nếu đã quá 48h."""
        self._check_perm('write')
        if not items:
            return {'rows': []}

        scope_dom = self._scope_domain()
        now_utc = fields.Datetime.now()
        tz = self._user_tz()
        validated = []

        for item in items:
            rec_id = int(item.get('id') or 0)
            rec = self.sudo().browse(rec_id).exists()
            if not rec:
                raise UserError(_('Không tìm thấy dòng doanh thu (ID=%s).') % rec_id)
            if scope_dom and not self.sudo().search_count([('id', '=', rec.id)] + list(scope_dom)):
                raise UserError(_('Bạn không có quyền cập nhật cửa hàng của nhân viên "%s".') % rec.staff_name)
            is_locked, _dl, lock_label = rec._lock_info(now_utc=now_utc, tz=tz)
            if is_locked:
                raise UserError(_('Doanh thu của "%s" đã tự động khóa sau 48h (khóa lúc %s), không thể chỉnh sửa.') % (rec.staff_name, lock_label))
            val = max(0.0, round(float(item.get('revenue') or 0.0)))
            validated.append((rec, val))

        updated = []
        for rec, val in validated:
            vals = {
                'revenue': val,
                'is_saved': True,
                'saved_at': now_utc,
                'saved_by': self.env.user.id,
            }
            if not rec.first_saved_at:
                vals['first_saved_at'] = now_utc
            rec.sudo().write(vals)
            updated.append(rec._row_payload(now_utc=now_utc, tz=tz))

        return {'rows': updated}

    @api.model
    def save_revenue(self, rec_id, revenue):
        res = self.save_revenue_batch([{'id': rec_id, 'revenue': revenue}])
        return res['rows'][0] if res['rows'] else {'id': int(rec_id), 'revenue': int(round(float(revenue or 0.0)))}

    @api.model
    def export_revenue_xlsx(self, work_date=None, mien=None, store_id=None, q=None):
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        data = self.get_revenue_page(work_date, mien, store_id)
        rows = data['rows']
        if q:
            kw = q.strip().casefold()
            rows = [r for r in rows if kw in ('%s %s %s' % (r['staff_name'], r['employee_code'], r['store'])).casefold()]
        if not rows:
            raise UserError(_('Không có dữ liệu doanh thu để xuất.'))

        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = book.add_worksheet('Doanh thu ngay')
        f_title = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 14, 'font_color': '#163363', 'align': 'center', 'valign': 'vcenter'})
        f_head = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center', 'valign': 'vcenter', 'border': 1})
        f_c = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        f_l = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'left', 'valign': 'vcenter', 'border': 1})
        f_money = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'right', 'valign': 'vcenter', 'border': 1, 'num_format': '#,##0'})
        f_tot_lbl = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#EFF6FF', 'border': 1})
        f_tot_val = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'align': 'right', 'valign': 'vcenter', 'bg_color': '#EFF6FF', 'font_color': '#1D4ED8', 'border': 1, 'num_format': '#,##0'})

        headers = ['STT', 'Họ và tên NV', 'ID', 'Cửa hàng', 'Doanh thu', 'Ngày', 'Trạng thái']
        widths = [8, 32, 14, 18, 18, 15, 22]
        ws.merge_range(0, 0, 0, len(headers) - 1, 'BẢNG DOANH THU NHÂN VIÊN BÁN HÀNG · NGÀY %s' % data['date_label'], f_title)
        ws.set_row(0, 28)
        for c, (h, w) in enumerate(zip(headers, widths)):
            ws.write(2, c, h, f_head)
            ws.set_column(c, c, w)
        ws.set_row(2, 28)

        total_rev = 0
        r_idx = 3
        for idx, r in enumerate(rows, 1):
            st_txt = 'Đã khóa (quá 48h)' if r.get('is_locked') else ('Đã lưu' if r.get('is_saved') else 'Chưa lưu')
            ws.write_number(r_idx, 0, idx, f_c)
            ws.write_string(r_idx, 1, r['staff_name'], f_l)
            ws.write_string(r_idx, 2, r['employee_code'] or '-', f_c)
            ws.write_string(r_idx, 3, r['store'] or '-', f_c)
            ws.write_number(r_idx, 4, r['revenue'] or 0, f_money)
            ws.write_string(r_idx, 5, r['date_label'], f_c)
            ws.write_string(r_idx, 6, st_txt, f_c)
            ws.set_row(r_idx, 24)
            total_rev += r['revenue'] or 0
            r_idx += 1

        ws.merge_range(r_idx, 0, r_idx, 3, 'TỔNG CỘNG DOANH THU', f_tot_lbl)
        ws.write_number(r_idx, 4, total_rev, f_tot_val)
        ws.write_string(r_idx, 5, data['date_label'], f_tot_lbl)
        ws.write_string(r_idx, 6, '', f_tot_lbl)
        ws.set_row(r_idx, 26)
        ws.freeze_panes(3, 0)
        book.close()
        return {
            'name': 'Doanh_thu_NVBH_%s.xlsx' % data['date'].replace('-', ''),
            'data': base64.b64encode(buf.getvalue()).decode(),
        }

    @api.model
    def export_revenue_month_xlsx(self, month=None, mien=None, store_id=None, q=None, only_has_rev=False):
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        data = self.get_revenue_month(month=month, mien=mien, store_id=store_id)
        stores = data['stores']
        if only_has_rev:
            stores = [s for s in stores if (s['revenue'] or 0) > 0]
        if q:
            kw = q.strip().casefold()
            stores = [
                s for s in stores
                if kw in ('%s %s %s' % (s['store'], s['mien'], s['asm'])).casefold()
                or any(kw in ('%s %s' % (sr['staff_name'], sr['employee_code'])).casefold() for sr in s['staff_rows'])
            ]
        if not stores:
            raise UserError(_('Không có dữ liệu doanh thu tháng để xuất.'))

        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        f_title = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 14, 'font_color': '#163363', 'align': 'center', 'valign': 'vcenter'})
        f_head = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center', 'valign': 'vcenter', 'border': 1})
        f_c = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        f_l = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'left', 'valign': 'vcenter', 'border': 1})
        f_money = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'right', 'valign': 'vcenter', 'border': 1, 'num_format': '#,##0'})
        f_pct = book.add_format({'font_name': 'Times New Roman', 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.0"%"'})
        f_tot_lbl = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#EFF6FF', 'border': 1})
        f_tot_val = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 12, 'align': 'right', 'valign': 'vcenter', 'bg_color': '#EFF6FF', 'font_color': '#1D4ED8', 'border': 1, 'num_format': '#,##0'})

        # Sheet 1: Tổng hợp doanh thu cửa hàng trong tháng
        ws = book.add_worksheet('Doanh thu Thang CH')
        headers = ['STT', 'Cửa hàng', 'Miền', 'Quản lý (ASM)', 'Số nhân sự', 'Số ngày có DT', 'Doanh thu tháng']
        widths = [8, 28, 12, 24, 14, 16, 20]
        ws.merge_range(0, 0, 0, len(headers) - 1, 'DOANH THU TẤT CẢ CỬA HÀNG · THÁNG %s' % data['month_label'], f_title)
        ws.set_row(0, 28)
        for c, (h, w) in enumerate(zip(headers, widths)):
            ws.write(2, c, h, f_head)
            ws.set_column(c, c, w)
        ws.set_row(2, 28)

        tot_rev = sum(s['revenue'] or 0 for s in stores)
        tot_staff = sum(s['staff_count'] or 0 for s in stores)
        r_idx = 3
        for idx, s in enumerate(stores, 1):
            ws.write_number(r_idx, 0, idx, f_c)
            ws.write_string(r_idx, 1, s['store'], f_l)
            ws.write_string(r_idx, 2, s['mien'] or '-', f_c)
            ws.write_string(r_idx, 3, s['asm'] or '-', f_l)
            ws.write_number(r_idx, 4, s['staff_count'] or 0, f_c)
            ws.write_string(r_idx, 5, '%s/%s' % (s['days_with_rev'], s['days_in_month']), f_c)
            ws.write_number(r_idx, 6, s['revenue'] or 0, f_money)
            ws.set_row(r_idx, 24)
            r_idx += 1

        ws.merge_range(r_idx, 0, r_idx, 3, 'TỔNG CỘNG (%s cửa hàng)' % len(stores), f_tot_lbl)
        ws.write_number(r_idx, 4, tot_staff, f_tot_lbl)
        ws.write_string(r_idx, 5, 'Tháng %s' % data['month_label'], f_tot_lbl)
        ws.write_number(r_idx, 6, tot_rev, f_tot_val)
        ws.set_row(r_idx, 26)
        ws.freeze_panes(3, 0)

        # Sheet 2: Chi tiết theo nhân viên trong tháng
        ws2 = book.add_worksheet('Chi tiet NV Thang')
        h2 = ['STT', 'Cửa hàng', 'Miền', 'Họ và tên NV', 'ID', 'Số ngày có DT', 'Doanh thu tháng NV']
        w2 = [8, 26, 12, 30, 14, 16, 20]
        ws2.merge_range(0, 0, 0, len(h2) - 1, 'CHI TIẾT DOANH THU NHÂN VIÊN THEO CỬA HÀNG · THÁNG %s' % data['month_label'], f_title)
        ws2.set_row(0, 28)
        for c, (h, w) in enumerate(zip(h2, w2)):
            ws2.write(2, c, h, f_head)
            ws2.set_column(c, c, w)
        ws2.set_row(2, 28)

        r2 = 3
        seq2 = 0
        for s in stores:
            for sr in s['staff_rows']:
                seq2 += 1
                ws2.write_number(r2, 0, seq2, f_c)
                ws2.write_string(r2, 1, s['store'], f_l)
                ws2.write_string(r2, 2, s['mien'] or '-', f_c)
                ws2.write_string(r2, 3, sr['staff_name'], f_l)
                ws2.write_string(r2, 4, sr['employee_code'] or '-', f_c)
                ws2.write_number(r2, 5, sr['days'] or 0, f_c)
                ws2.write_number(r2, 6, sr['revenue'] or 0, f_money)
                ws2.set_row(r2, 23)
                r2 += 1
        ws2.freeze_panes(3, 0)

        book.close()
        return {
            'name': 'Doanh_thu_Thang_%s.xlsx' % data['month'].replace('-', ''),
            'data': base64.b64encode(buf.getvalue()).decode(),
        }


class StoreNvbhScheduleLineRevenueSync(models.Model):
    _inherit = 'store.nvbh.schedule.line'

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        today = fields.Date.context_today(self)
        for d in {r.work_date for r in recs if r.work_date and r.work_date <= today}:
            self.env['store.nvbh.revenue'].sudo()._sync_date(d)
        return recs

    def write(self, vals):
        old_dates = {r.work_date for r in self if r.work_date}
        res = super().write(vals)
        if {'staff_name', 'employee_code', 'shift_id', 'work_date', 'store_id', 'position'} & set(vals):
            today = fields.Date.context_today(self)
            new_dates = {r.work_date for r in self if r.work_date}
            for d in (old_dates | new_dates):
                if d <= today:
                    self.env['store.nvbh.revenue'].sudo()._sync_date(d)
        return res
