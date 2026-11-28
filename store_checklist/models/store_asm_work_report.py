# -*- coding: utf-8 -*-
import calendar
import ipaddress
import logging
import math
import re
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

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

LOC_STATUS_SELECTION = [
    ('verified', 'Hợp lệ (GPS + Wifi)'),
    ('valid', 'Hợp lệ (GPS)'),
    ('network', 'Hợp lệ theo mạng'),
    ('verify', 'Cần xác minh'),
    ('invalid', 'Không hợp lệ'),
    ('unknown', 'Không xác minh được'),
]
LOC_STATUS_LABELS = dict(LOC_STATUS_SELECTION)

# Bán kính hợp lệ quanh cửa hàng (m), chỉnh qua tham số hệ thống
RADIUS_PARAM = 'store_checklist.asm_checkin_radius_m'
DEFAULT_RADIUS_M = 150
# GPS sai số lớn hơn mức này coi như không dùng được để kết luận
MAX_GPS_ACCURACY_M = 500
# Cộng thêm tối đa phần sai số GPS vào bán kính (tránh báo sai khi GPS dao động)
MAX_ACCURACY_BONUS_M = 100
# Tọa độ cửa hàng chỉ tin cậy khi do geopy tính hoặc nhập tay (không dùng tọa độ ước tính theo IP)
RELIABLE_GEOCODE = ('success', 'manual')
# Tự Check in/out theo wifi cửa hàng: chức vụ áp dụng, số phút mất tín hiệu thì tự Check out
AUTO_CHECK_ROLES = ('ASM', 'ASMTT')
AUTO_CHECKOUT_PARAM = 'store_checklist.asm_auto_checkout_minutes'
AUTO_CHECKOUT_MINUTES = 30


def _haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _client_ip():
    """IP công khai của người dùng (sau nginx: IP cuối trong X-Forwarded-For)."""
    try:
        from odoo.http import request
        hr = request.httprequest
    except Exception:
        return ''
    ip = (hr.remote_addr or '').strip()
    try:
        addr = ipaddress.ip_address(ip)
        private = addr.is_private or addr.is_loopback
    except ValueError:
        private = True
    if private:
        xff = [x.strip() for x in (hr.headers.get('X-Forwarded-For') or '').split(',') if x.strip()]
        if xff:
            ip = xff[-1]
        elif hr.headers.get('X-Real-IP'):
            ip = hr.headers['X-Real-IP'].strip()
    return ip

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
    check_in_at = fields.Datetime('Check in')
    check_in_lat = fields.Float('Vĩ độ Check in', digits=(10, 6))
    check_in_lng = fields.Float('Kinh độ Check in', digits=(10, 6))
    check_out_at = fields.Datetime('Check out')
    check_out_lat = fields.Float('Vĩ độ Check out', digits=(10, 6))
    check_out_lng = fields.Float('Kinh độ Check out', digits=(10, 6))
    # Xác thực vị trí: GPS so với tọa độ cửa hàng + IP truy cập so với IP WAN (DDNS) cửa hàng
    check_in_accuracy = fields.Integer('Sai số GPS Check in (m)')
    check_in_distance = fields.Integer('Khoảng cách Check in (m)')
    check_in_ip = fields.Char('IP Check in')
    check_in_status = fields.Selection(LOC_STATUS_SELECTION, string='Xác thực Check in')
    check_in_note = fields.Char('Chi tiết xác thực Check in')
    check_out_accuracy = fields.Integer('Sai số GPS Check out (m)')
    check_out_distance = fields.Integer('Khoảng cách Check out (m)')
    check_out_ip = fields.Char('IP Check out')
    check_out_status = fields.Selection(LOC_STATUS_SELECTION, string='Xác thực Check out')
    check_out_note = fields.Char('Chi tiết xác thực Check out')
    # Tự Check in/out theo tín hiệu Odoo đang mở trên mạng (wifi) cửa hàng
    check_in_auto = fields.Boolean('Check in tự động')
    check_out_auto = fields.Boolean('Check out tự động')
    last_seen_at = fields.Datetime('Lần cuối thấy trên mạng cửa hàng')
    last_seen_lat = fields.Float('Vĩ độ lần cuối', digits=(10, 6))
    last_seen_lng = fields.Float('Kinh độ lần cuối', digits=(10, 6))
    last_seen_accuracy = fields.Integer('Sai số GPS lần cuối (m)')
    last_seen_ip = fields.Char('IP lần cuối')

    @api.model
    def _is_manager(self):
        u = self.env.user
        return self.env.su or u.has_group('base.group_system') or u.has_group('store_checklist.group_store_manager')

    def _fmt_check(self, dt_val, lat, lng):
        if not dt_val:
            return {'at': '', 'time': '', 'date': '', 'gps': '', 'map_url': ''}
        local_dt = fields.Datetime.context_timestamp(self, dt_val)
        has_gps = bool(lat or lng)
        gps_str = f'{lat:.6f}, {lng:.6f}' if has_gps else ''
        return {
            'at': local_dt.strftime('%H:%M %d/%m/%Y'),
            'time': local_dt.strftime('%H:%M'),
            'date': local_dt.strftime('%d/%m/%Y'),
            'gps': gps_str,
            'map_url': f'https://www.google.com/maps?q={lat:.6f},{lng:.6f}' if has_gps else '',
        }

    def _serialize(self):
        self.ensure_one()
        uid = self.env.uid
        is_mgr = self._is_manager()
        d = self.work_date
        ci = self._fmt_check(self.check_in_at, self.check_in_lat, self.check_in_lng)
        co = self._fmt_check(self.check_out_at, self.check_out_lat, self.check_out_lng)
        return {
            'id': self.id,
            'work_date': d.strftime('%Y-%m-%d') if d else '',
            'date_label': d.strftime('%d/%m/%Y') if d else '',
            'time_in': self.time_in or '',
            'time_out': self.time_out or '',
            'check_in_at': ci['at'],
            'check_in_time': ci['time'],
            'check_in_date': ci['date'],
            'check_in_gps': ci['gps'],
            'check_in_map_url': ci['map_url'],
            'check_out_at': co['at'],
            'check_out_time': co['time'],
            'check_out_date': co['date'],
            'check_out_gps': co['gps'],
            'check_out_map_url': co['map_url'],
            'check_in_status': self.check_in_status or '',
            'check_in_status_label': LOC_STATUS_LABELS.get(self.check_in_status, ''),
            'check_in_note': self.check_in_note or '',
            'check_out_status': self.check_out_status or '',
            'check_out_status_label': LOC_STATUS_LABELS.get(self.check_out_status, ''),
            'check_out_note': self.check_out_note or '',
            'check_in_auto': bool(self.check_in_auto),
            'check_out_auto': bool(self.check_out_auto),
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

    def _verify_location(self, lat, lng, accuracy, ip):
        """Đánh giá vị trí Check in/out: GPS so với tọa độ cửa hàng + IP so với IP WAN cửa hàng.
        Trả về dict(status, distance, note). Chỉ gắn nhãn, không chặn thao tác."""
        self.ensure_one()
        store = self.store_id.sudo()
        sf = store._fields
        try:
            radius = int(self.env['ir.config_parameter'].sudo().get_param(RADIUS_PARAM) or DEFAULT_RADIUS_M)
        except (TypeError, ValueError):
            radius = DEFAULT_RADIUS_M
        notes = []

        # 1) GPS: in = trong bán kính, out = ngoài bán kính, None = không kết luận được
        gps = None
        distance = 0
        s_lat = store.latitude if 'latitude' in sf else 0.0
        s_lng = store.longitude if 'longitude' in sf else 0.0
        geo_ok = bool(s_lat or s_lng) and ('geocode_status' not in sf or store.geocode_status in RELIABLE_GEOCODE)
        if not (lat or lng):
            notes.append('Không lấy được GPS')
        elif not geo_ok:
            notes.append('Cửa hàng chưa có tọa độ chuẩn (geopy/nhập tay)')
        else:
            distance = int(round(_haversine_m(lat, lng, s_lat, s_lng)))
            if accuracy and accuracy > MAX_GPS_ACCURACY_M:
                notes.append('GPS cách %s m, sai số ±%s m (quá lớn)' % (distance, accuracy))
            else:
                allowed = radius + min(accuracy or 0, MAX_ACCURACY_BONUS_M)
                gps = distance <= allowed
                notes.append('GPS cách cửa hàng %s m%s (cho phép %s m)' % (
                    distance, ' ±%s m' % accuracy if accuracy else '', allowed))

        # 2) IP: so IP truy cập với IP WAN (DDNS) của cửa hàng; lệch thì tra lại DDNS 1 lần
        ip_match = False
        if 'wan_ip' in sf and ip:
            ip_match = bool(store.wan_ip) and store.wan_ip == ip
            if not ip_match and store.ddns_domain and hasattr(store, '_sync_wan_ip'):
                try:
                    store._sync_wan_ip()
                    ip_match = bool(store.wan_ip) and store.wan_ip == ip
                except Exception as e:
                    _logger.warning('Không tra lại được DDNS cửa hàng %s: %s', store.display_name, e)
            if not store.wan_ip:
                notes.append('Cửa hàng chưa có IP WAN')
            else:
                notes.append('IP %s %s mạng cửa hàng (%s)' % (ip, 'khớp' if ip_match else 'không khớp', store.wan_ip))

        # 3) Kết luận
        if gps is True:
            status = 'verified' if ip_match else 'valid'
        elif gps is False:
            status = 'verify' if ip_match else 'invalid'
        else:
            status = 'network' if ip_match else 'unknown'
        return {'status': status, 'distance': distance, 'note': '; '.join(notes)[:250]}

    @api.model
    def do_asm_check(self, rec_id, action_type, lat=False, lng=False, accuracy=False):
        rec = self.sudo().browse(int(rec_id or 0)).exists()
        if not rec:
            raise UserError('Không tìm thấy phiếu báo cáo.')
        if not self._is_manager() and rec.user_id.id != self.env.uid:
            raise AccessError('Bạn không có quyền Check in / Check out phiếu này.')
        try:
            f_lat = float(lat) if lat not in (False, None, '') else 0.0
            f_lng = float(lng) if lng not in (False, None, '') else 0.0
        except (TypeError, ValueError):
            f_lat, f_lng = 0.0, 0.0
        try:
            f_acc = int(round(float(accuracy))) if accuracy not in (False, None, '') else 0
        except (TypeError, ValueError):
            f_acc = 0
        now = fields.Datetime.now()
        if action_type == 'in':
            if rec.check_in_at:
                raise UserError('Phiếu này đã Check in rồi.')
        elif action_type == 'out':
            if not rec.check_in_at:
                raise UserError('Vui lòng Check in trước khi Check out.')
            if rec.check_out_at:
                raise UserError('Phiếu này đã Check out rồi.')
        else:
            raise UserError('Thao tác không hợp lệ.')
        ip = _client_ip()
        res = rec._verify_location(f_lat, f_lng, f_acc, ip)
        p = 'check_%s_' % action_type
        rec.write({
            p + 'at': now, p + 'lat': f_lat, p + 'lng': f_lng,
            p + 'accuracy': f_acc, p + 'distance': res['distance'], p + 'ip': ip or False,
            p + 'status': res['status'], p + 'note': res['note'],
        })
        return rec._serialize()

    # ------------------------------------------------------------------
    # Tự Check in / Check out: Odoo đang mở trên điện thoại ASM gửi tín hiệu (IP + GPS) định kỳ
    # (hr_employee_location /update_position). IP trùng IP WAN cửa hàng = đang ở cửa hàng.
    # ------------------------------------------------------------------
    def _auto_close(self, reason):
        """Check out tự động tại thời điểm lần cuối thấy trên mạng cửa hàng."""
        for rec in self:
            if rec.check_out_at or not rec.check_in_at:
                continue
            at = max(rec.last_seen_at or rec.check_in_at, rec.check_in_at)
            res = rec._verify_location(rec.last_seen_lat, rec.last_seen_lng, rec.last_seen_accuracy, rec.last_seen_ip)
            rec.write({
                'check_out_at': at, 'check_out_lat': rec.last_seen_lat, 'check_out_lng': rec.last_seen_lng,
                'check_out_accuracy': rec.last_seen_accuracy, 'check_out_distance': res['distance'],
                'check_out_ip': rec.last_seen_ip, 'check_out_status': res['status'],
                'check_out_note': ('Tự động (%s); %s' % (reason, res['note']))[:250],
                'check_out_auto': True,
            })

    @api.model
    def _presence_ping(self, user, ip, lat=False, lng=False, accuracy=False):
        """Gọi (sudo) mỗi lần Odoo của user gửi tín hiệu vị trí. Chỉ áp dụng chức vụ ASM / ASMTT."""
        if not user or not ip:
            return False
        emp = user.sudo().employee_id
        if not emp or (emp.checklist_role_code or '') not in AUTO_CHECK_ROLES:
            return False
        try:
            f_lat = float(lat) if lat not in (False, None, '') else 0.0
            f_lng = float(lng) if lng not in (False, None, '') else 0.0
            f_acc = int(round(float(accuracy))) if accuracy not in (False, None, '') else 0
        except (TypeError, ValueError):
            f_lat, f_lng, f_acc = 0.0, 0.0, 0
        now = fields.Datetime.now()
        Rep = self.sudo()
        tz_ctx = {'tz': user.tz or 'Asia/Ho_Chi_Minh'}
        today = fields.Date.context_today(Rep.with_context(**tz_ctx))

        # Cửa hàng có IP WAN trùng, trong phạm vi cửa hàng ASM được xem
        Store = self.env['hr.store'].sudo()
        if 'wan_ip' not in Store._fields:
            return False
        stores = Store.search([('wan_ip', '=', ip)])
        scope = self.env['store.audit'].with_user(user)._user_store_scope()
        if scope is not None:
            stores = stores.filtered(lambda s: s.id in scope)
        if len(stores) > 1 and (f_lat or f_lng):
            # Nhiều cửa hàng chung mạng: chọn cửa hàng gần GPS nhất
            stores = stores.sorted(lambda s: _haversine_m(f_lat, f_lng, s.latitude, s.longitude)
                                   if (s.latitude or s.longitude) else 1e9)
        store = stores[:1]

        # Phiếu đang mở (đã Check in, chưa Check out) của ASM
        open_recs = Rep.search([('user_id', '=', user.id), ('check_in_at', '!=', False),
                                ('check_out_at', '=', False), ('last_seen_at', '!=', False)])
        # Đã sang mạng khác / cửa hàng khác -> Check out cửa hàng cũ
        leaving = open_recs.filtered(lambda r: r.store_id != store)
        if leaving:
            leaving._auto_close('rời mạng cửa hàng')
        if not store:
            return False

        seen = {'last_seen_at': now, 'last_seen_lat': f_lat, 'last_seen_lng': f_lng,
                'last_seen_accuracy': f_acc, 'last_seen_ip': ip}
        here = Rep.search([('user_id', '=', user.id), ('store_id', '=', store.id), ('work_date', '=', today)],
                          order='id')
        current = here.filtered(lambda r: r.check_in_at and not r.check_out_at)[:1]
        if current:
            current.write(seen)
            return current.id
        if here and all(r.check_out_at for r in here):
            return False  # hôm nay đã Check in/out xong tại cửa hàng này
        rec = here.filtered(lambda r: not r.check_in_at)[:1]
        if not rec:
            rec = Rep.create({'store_id': store.id, 'user_id': user.id, 'work_date': today, 'state': 'draft'})
        res = rec._verify_location(f_lat, f_lng, f_acc, ip)
        rec.write(dict(seen, **{
            'check_in_at': now, 'check_in_lat': f_lat, 'check_in_lng': f_lng,
            'check_in_accuracy': f_acc, 'check_in_distance': res['distance'], 'check_in_ip': ip,
            'check_in_status': res['status'], 'check_in_note': ('Tự động; %s' % res['note'])[:250],
            'check_in_auto': True,
        }))
        return rec.id

    @api.model
    def _cron_auto_check_out(self):
        """Quá AUTO_CHECKOUT_MINUTES không còn tín hiệu trên mạng cửa hàng -> tự Check out."""
        try:
            minutes = int(self.env['ir.config_parameter'].sudo().get_param(AUTO_CHECKOUT_PARAM) or AUTO_CHECKOUT_MINUTES)
        except (TypeError, ValueError):
            minutes = AUTO_CHECKOUT_MINUTES
        limit = fields.Datetime.now() - timedelta(minutes=minutes)
        recs = self.sudo().search([('check_in_at', '!=', False), ('check_out_at', '=', False),
                                   ('last_seen_at', '!=', False), ('last_seen_at', '<', limit)])
        recs._auto_close('mất tín hiệu %s phút' % minutes)

    @api.model
    def delete_asm_work_report(self, rec_id):
        rec = self.sudo().browse(int(rec_id or 0)).exists()
        if not rec:
            return True
        if not self._is_manager() and rec.user_id.id != self.env.uid:
            raise AccessError('Bạn không có quyền xóa phiếu báo cáo này.')
        rec.unlink()
        return True
