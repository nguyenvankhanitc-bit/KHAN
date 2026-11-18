import base64
import calendar
import io
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_nvbh_task import TASK_GROUPS
from .store_shift import SHIFT_TYPES

WORKDAY_QUOTA = 26  # định mức ngày công / tháng để tính điểm trung bình
# tiền tố cột kết quả đánh giá theo thứ tự bước trong luồng: bước 1 = eval_result, bước 2 = asm_eval_result, ...
STEP_PREFIX = ['', 'asm_', 'rsm_', 'adm_']

EVAL_RESULTS = [
    ('good', 'Đạt'),
    ('avg', 'T.Bình'),
    ('bad', 'Không đạt'),
]

# Quy tắc điểm khi quản lý đánh giá: Đạt = điểm chuẩn; T.Bình = điểm chuẩn / 2; Không đạt = 0; chưa đánh giá = 0
EVAL_SCORE_RATE = {'good': 1.0, 'avg': 0.5, 'bad': 0.0}


def count_errors(text):
    """Số lỗi = số dòng có nội dung trong Chi tiết lỗi (1 dòng = 1 lỗi)."""
    return len([ln for ln in (text or '').splitlines() if ln.strip()])


def eval_score(max_score, result, errors=0):
    """Đạt = điểm chuẩn; T.Bình = điểm chuẩn / 2; Không đạt hoặc chưa đánh giá = 0; có ghi lỗi thì điểm = 0."""
    if errors:
        return 0.0
    return round((max_score or 0.0) * EVAL_SCORE_RATE.get(result or '', 0.0), 2)


LINE_STATES = [
    ('todo', 'Chưa làm'),
    ('doing', 'Đang làm'),
    ('done', 'Đã làm'),
]


class StoreNvbhCheck(models.Model):
    """Checklist công việc NVBH của một nhân viên trong một ngày: lấy theo Lịch làm việc (cửa hàng / ngày / nhân viên / Mã ca).
    Hệ thống tự tạo khi mở trang; các dòng công việc lấy từ Cài đặt > Danh sách công việc NVBH theo Loại ca của Mã ca."""
    _name = 'store.nvbh.check'
    _description = 'Checklist công việc NVBH'
    _order = 'work_date desc, id desc'

    name = fields.Char(string='Mã phiếu', required=True, copy=False, readonly=True, default='New')
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True)
    mien = fields.Selection(related='store_id.mien', string='Miền')
    shift_id = fields.Many2one('store.shift', string='Ca', help='Mã ca của nhân viên trong Lịch làm việc')
    shift_type = fields.Selection(SHIFT_TYPES, related='shift_id.shift_type', string='Loại ca', store=True, readonly=True)
    work_date = fields.Date(string='Ngày', required=True, default=fields.Date.context_today)
    staff_name = fields.Char(string='Nhân viên')
    schedule_line_id = fields.Many2one('store.nvbh.schedule.line', string='Dòng lịch làm việc', ondelete='set null', index=True)
    staff_id = fields.Many2one('store.audit.staff', string='NVBH (cũ)')
    line_ids = fields.One2many('store.nvbh.check.line', 'check_id', string='Công việc')
    # Đã lưu checklist (bấm Lưu ở trang Check list công việc) -> hiện trong Danh sách checklist NV
    submitted = fields.Boolean(string='Đã check list', default=False, index=True)
    submit_date = fields.Datetime(string='Lưu lúc')
    submitted_by = fields.Many2one('res.users', string='Người lưu')
    points = fields.Float(string='Điểm đạt', compute='_compute_points')
    error_total = fields.Integer(string='Số lỗi', compute='_compute_points')

    cnt_total = fields.Integer(string='Tổng việc', compute='_compute_counts')
    cnt_doing = fields.Integer(string='Đang làm', compute='_compute_counts')
    cnt_done = fields.Integer(string='Đã làm', compute='_compute_counts')
    cnt_todo = fields.Integer(string='Chưa làm', compute='_compute_counts')

    @api.depends('line_ids.actual_score', 'line_ids.error_count')
    def _compute_points(self):
        # điểm đạt của nhân viên = tổng điểm theo kết quả quản lý đánh giá (Đạt / T.Bình / Không đạt)
        for rec in self:
            rec.points = sum(rec.line_ids.mapped('actual_score'))
            rec.error_total = sum(rec.line_ids.mapped('error_count'))

    @api.depends('line_ids.status')
    def _compute_counts(self):
        for rec in self:
            lines = rec.line_ids
            rec.cnt_total = len(lines)
            rec.cnt_doing = len(lines.filtered(lambda l: l.status == 'doing'))
            rec.cnt_done = len(lines.filtered(lambda l: l.status == 'done'))
            rec.cnt_todo = len(lines.filtered(lambda l: l.status == 'todo'))

    @api.model
    def _task_line_commands(self, shift):
        """Một dòng cho mỗi công việc áp dụng cho Loại ca của Mã ca (theo thứ tự trong bảng công việc NVBH)."""
        groups = dict(TASK_GROUPS)
        if not shift or not shift.shift_type_id:
            return []
        tasks = self.env['store.nvbh.task'].search([('shift_type_ids', 'in', shift.shift_type_id.id)], order='task_group, sequence, id')
        return [Command.create({
            'task_id': t.id,
            'sequence': t.sequence,
            'name': t.name,
            'sub_category': groups.get(t.task_group) or 'Khác',
            'time_slot': t.time_slot,
            'controller': t.controller,
            'max_score': t.score,
            'is_done': False,
        }) for t in tasks]

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        # chọn Ca -> nạp công việc áp dụng cho Mã ca đó (chỉ khi phiếu mới)
        if not self._origin.id:
            self.line_ids = [Command.clear()] + self._task_line_commands(self.shift_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self._next_name(vals.get('store_id'), vals.get('work_date'), vals.get('shift_id'))
        return super().create(vals_list)

    def _next_name(self, store_id, work_date, shift_id=None):
        store = self.env['hr.store'].browse(store_id)
        day = fields.Date.to_date(work_date) or fields.Date.context_today(self)
        prefix = 'CV/%s/%s' % (store.code or store.display_name or 'CH', day.strftime('%d%m%Y'))
        n = self.search_count([('name', '=like', prefix + '\\_%')]) + 1
        while self.search_count([('name', '=', '%s_%d' % (prefix, n))]):
            n += 1
        return '%s_%d' % (prefix, n)

    # ------------------------------------------------------------------
    # Trang "Check list công việc": chọn Ngày + Cửa hàng + Nhân viên (từ Lịch làm việc), không cần Thêm mới
    # ------------------------------------------------------------------
    @api.model
    def get_user_store(self):
        """Cửa hàng của người dùng đang đăng nhập (theo nhân sự / phân quyền cửa hàng); chỉ trả về khi tra được đúng 1 cửa hàng, ngược lại False."""
        try:
            ids = set(self.env.user._linkq_allowed_hr_store_ids())
        except Exception:
            return False
        stores = self.env['hr.store'].sudo().browse(list(ids)).exists()
        return stores.id if len(stores) == 1 else False

    @api.model
    def get_job_overview(self, store_id, work_date):
        """Trang Check list công việc: tất cả nhân viên có lịch làm việc trong ngày kèm tiến độ (đã làm / tổng việc, điểm, đã check list chưa),
        và danh sách nhân viên của cửa hàng không có lịch (nghỉ OFF)."""
        if not store_id or not work_date:
            return {'staff': [], 'off': [], 'store_staff': 0}
        lines = self.env['store.nvbh.schedule.line'].search(
            [('store_id', '=', int(store_id)), ('work_date', '=', work_date)], order='schedule_id, sequence, id')
        checks = {c.schedule_line_id.id: c for c in self.search([('schedule_line_id', 'in', lines.ids)])}
        staff = []
        for i, l in enumerate(lines, 1):
            c = checks.get(l.id)
            total = c.cnt_total if c else len(self._task_line_commands(l.shift_id))
            staff.append({
                'id': l.id, 'stt': i, 'name': l.staff_name or '', 'shift': l.shift_id.code or '',
                'done': c.cnt_done if c else 0, 'total': total, 'points': c.points if c else 0.0,
                'finished': bool(c and c.submitted and total and c.cnt_todo == 0),
            })
        scheduled = {(s['name'] or '').strip().casefold() for s in staff}
        roster = self.env['store.audit.staff'].search([('store_id', '=', int(store_id)), ('staff_state', '=', 'active'),
                                                        ('position', 'not in', ['ASM', 'RSM'])])
        names = {}
        for r in roster:
            names.setdefault((r.name or '').strip().casefold(), (r.name or '').strip())
        off = sorted(n for k, n in names.items() if k not in scheduled)
        return {'staff': staff, 'off': off, 'store_staff': len(set(names) | scheduled)}

    @api.model
    def get_staff_options(self, store_id, work_date):
        """Nhân viên có lịch làm việc ở cửa hàng / ngày đã chọn, kèm Mã ca: "Tên - Ca F1 (FULL)"."""
        if not store_id or not work_date:
            return []
        types = dict(SHIFT_TYPES)
        lines = self.env['store.nvbh.schedule.line'].search(
            [('store_id', '=', int(store_id)), ('work_date', '=', work_date)], order='schedule_id, sequence, id')
        return [{
            'id': l.id,
            'label': '%s - Ca %s (%s)' % (l.staff_name or '', l.shift_id.code, types.get(l.shift_id.shift_type, '')),
        } for l in lines]

    @api.model
    def get_checklist(self, schedule_line_id):
        """Checklist của nhân viên (một dòng Lịch làm việc); chưa có thì tự tạo theo Mã ca của dòng lịch."""
        line = self.env['store.nvbh.schedule.line'].browse(int(schedule_line_id)).exists()
        if not line:
            return False
        check = self.search([('schedule_line_id', '=', line.id)], limit=1)
        if not check:
            check = self.create({
                'store_id': line.store_id.id,
                'work_date': line.work_date,
                'shift_id': line.shift_id.id,
                'staff_name': line.staff_name,
                'schedule_line_id': line.id,
                'line_ids': self._task_line_commands(line.shift_id),
            })
        return check._checklist_payload()

    def _checklist_payload(self):
        self.ensure_one()
        order = {label: i for i, (_k, label) in enumerate(TASK_GROUPS)}
        # theo nhóm công việc (I, II, III...) rồi theo thứ tự trong bảng công việc NVBH
        lines = self.line_ids.sorted(lambda l: (order.get(l.sub_category, len(order)), l.sequence, l.id))
        return {
            'id': self.id,
            'name': self.name,
            'staff_name': self.staff_name or '',
            'store': self.store_id.display_name or '',
            'date': self.work_date.strftime('%d/%m/%Y') if self.work_date else '',
            'shift': ('%s (%s)' % (self.shift_id.code, dict(SHIFT_TYPES).get(self.shift_id.shift_type, ''))) if self.shift_id else '',
            'points': self.points,
            'error_total': self.error_total,
            'max_points': sum(self.line_ids.mapped('max_score')),
            'kpi': {'total': self.cnt_total, 'doing': self.cnt_doing, 'done': self.cnt_done, 'todo': self.cnt_todo},
            'lines': [{
                'id': l.id, 'stt': i, 'name': l.name, 'group': l.sub_category or 'Khác', 'time_slot': l.time_slot or '', 'score': l.max_score,
                'is_done': l.is_done, 'status': l.status, 'note': l.note or '',
                'reviewer_id': l.reviewer_id.id or 0, 'eval_result': l.eval_result or '', 'error_detail': l.error_detail or '',
                'actual_score': l.actual_score, 'error_count': l.error_count,
                'ev': [{'result': l[p + 'eval_result'] or '', 'detail': l[p + 'error_detail'] or '',
                        'reviewer_id': l[p + 'reviewer_id'].id or 0} for p in STEP_PREFIX],
            } for i, l in enumerate(lines, 1)],
        }

    @api.model
    def save_checklist(self, check_id, changes):
        """Lưu một lượt: changes = [{id, is_done, note}, ...] (nút Lưu của trang Check list công việc)."""
        check = self.browse(int(check_id)).exists()
        check._assert_can_execute()
        lines = {l.id: l for l in check.line_ids}
        for ch in changes or []:
            line = lines.get(int(ch.get('id') or 0))
            if not line:
                continue
            vals = {'is_done': bool(ch.get('is_done')), 'note': (ch.get('note') or '').strip() or False}
            if line.is_done != vals['is_done'] or (line.note or False) != vals['note']:
                line.write(vals)
        if not check.submitted:
            check.write({'submitted': True, 'submit_date': fields.Datetime.now(), 'submitted_by': self.env.user.id})
        return check._checklist_payload()

    @api.model
    def get_reviewer_options(self):
        """Người dùng có thể làm Người đánh giá (CHT): thành viên nhóm sử dụng Checklist Audit."""
        group = self.env.ref('store_checklist.group_store_user')
        users = group.all_user_ids if 'all_user_ids' in group._fields else group.users
        users = users.filtered(lambda u: u.active and not u.share).sorted('name')
        return [{'id': u.id, 'name': u.name} for u in users]

    @api.model
    def get_store_staff_options(self, month=None, store_id=None):
        """Toàn bộ nhân viên của cửa hàng (lịch xếp ca trong tháng + danh sách Nhân sự), kể cả người chưa có checklist nào."""
        out = {}
        Line = self.env['store.nvbh.schedule.line']
        domain = []
        if store_id:
            domain.append(('store_id', '=', int(store_id)))
        if month:
            y, m = [int(x) for x in month.split('-')]
            start = fields.Date.to_date('%04d-%02d-01' % (y, m))
            end = fields.Date.to_date('%04d-%02d-01' % (y + 1, 1) if m == 12 else '%04d-%02d-01' % (y, m + 1))
            domain += [('work_date', '>=', start), ('work_date', '<', end)]
        for line in Line.search(domain, order='work_date desc, id desc'):
            name = (line.staff_name or '').strip()
            if name and (name.casefold() not in out or (not out[name.casefold()]['code'] and line.employee_code)):
                out[name.casefold()] = {'name': name, 'code': line.employee_code or ''}
        sdomain = [('store_id', '=', int(store_id))] if store_id else []
        for st in self.env['store.audit.staff'].search(sdomain):
            name = (st.name or '').strip()
            if name and name.casefold() not in out:
                out[name.casefold()] = {'name': name, 'code': st.employee_code or ''}
        return sorted(out.values(), key=lambda o: o['name'].casefold())

    @api.model
    def get_done_summary(self, month=None, store_id=None, mien=None, search=None, today=False, errors=False):
        """Danh sách checklist nhân viên: tổng hợp theo nhân viên trong tháng, mỗi nhân viên kèm các ngày công (mới nhất trước)."""
        domain = []  # hiển thị tất cả các phiếu (kể cả phiếu đang thực hiện, chưa gửi cấp trên)
        if month:
            y, m = [int(x) for x in month.split('-')]
            start = fields.Date.to_date('%04d-%02d-01' % (y, m))
            end = fields.Date.to_date('%04d-%02d-01' % (y + 1, 1) if m == 12 else '%04d-%02d-01' % (y, m + 1))
            domain += [('work_date', '>=', start), ('work_date', '<', end)]
        if store_id:
            domain.append(('store_id', '=', int(store_id)))
        if mien == 'other':
            domain += ['|', ('mien', '=', False), ('mien', 'not in', ['Nam', 'ĐTT', 'Bắc'])]
        elif mien:
            domain.append(('mien', '=', mien))
        if today:
            domain.append(('work_date', '=', fields.Date.context_today(self)))
        if search:
            domain.append(('staff_name', 'ilike', search))
        checks = self.search(domain, order='work_date desc, id desc')
        if errors:
            checks = checks.filtered(lambda c: c.error_total > 0)

        Rating = self.env['store.nvbh.rating']

        def rating(points, max_points, evaluated):
            """Xếp loại theo bảng Cài đặt > Công việc checklist NVBH > Xếp loại; chưa có ngày nào được duyệt thì Chờ duyệt."""
            if not evaluated:
                return 'Chờ đánh giá', 'wait'
            level = Rating.rating_for(100.0 * points / max_points if max_points else 0.0)
            return (level.name, level.tone) if level else ('', 'wait')

        groups = {}
        for c in checks:
            key = '%s|%s' % ((c.staff_name or '').strip().casefold(), c.store_id.id)
            g = groups.setdefault(key, {'key': key, 'name': (c.staff_name or '').strip(), 'code': c.schedule_line_id.employee_code or '', 'store': c.store_id.display_name or '',
                                        'days': [], 'done': 0, 'total': 0, 'errors': 0, 'points': 0.0, 'max_points': 0.0,
                                        'evaluated': 0})
            max_points = sum(c.line_ids.mapped('max_score'))
            evaluated = bool(c.line_ids) and all(l._final_eval()[0] for l in c.line_ids)  # đã đánh giá đủ mọi dòng
            pct = 100.0 * c.points / max_points if max_points else 0.0
            g['days'].append({
                'id': c.id,
                'date': c.work_date.strftime('%d/%m/%Y') if c.work_date else '',
                'shift': ('Ca %s' % c.shift_id.code) if c.shift_id else '',
                'done': c.cnt_done, 'total': c.cnt_total, 'errors': c.error_total,
                'points': c.points, 'max_points': max_points,
                # Điểm chuẩn lấy theo Cài đặt > Công việc checklist NVBH (dòng không còn gắn công việc thì dùng điểm đã lưu)
                'std_points': sum((l.task_id.score if l.task_id else l.max_score) or 0 for l in c.line_ids),
                'status': 'Đã đánh giá' if evaluated else 'Chờ đánh giá',
                'evaluated': evaluated,
                'asm_done': c.state == 'approved',
                'state': c.state,
                'pct': round(pct) if evaluated else None,
                'rating': rating(c.points, max_points, evaluated)[0] if evaluated else '',  # cùng bảng Cài đặt > Xếp loại với xếp loại theo tháng
            })
            g['done'] += c.cnt_done
            g['total'] += c.cnt_total
            g['errors'] += c.error_total
            if evaluated:  # ngày chưa đánh giá không tính vào điểm / tỷ lệ (tránh bị kéo xuống 0)
                g['points'] += c.points
                g['max_points'] += max_points
            g['evaluated'] += 1 if evaluated else 0
        rows = []
        for g in groups.values():
            label, tone = rating(g['points'], g['max_points'], g['evaluated'])
            g['pct'] = round(100.0 * g['points'] / g['max_points'], 1) if g['max_points'] else 0.0
            g['rating'], g['rating_key'] = label, tone
            g['day_count'] = len(g['days'])
            g['quota'] = WORKDAY_QUOTA  # định mức cố định theo quy định công ty, không chia theo số ngày đã làm
            g['avg'] = round(g['points'] / WORKDAY_QUOTA, 2)
            g['avg_pct'] = round(100.0 * g['avg'] / WORKDAY_QUOTA)  # thanh tiến độ theo mẫu: điểm TB / 26
            g['status'] = 'Đã đánh giá' if g['evaluated'] and g['evaluated'] == len(g['days']) else 'Chờ đánh giá'
            del g['evaluated']
            rows.append(g)
        rows.sort(key=lambda r: (r['name'].casefold(), r['store']))
        return rows

    # ------------------------------------------------------------------
    # Màn "Quản lý & đánh giá checklist NVBH": Bảng Nhân viên (theo tháng) / Bảng Đánh giá (theo ngày)
    # ------------------------------------------------------------------
    @api.model
    def _month_range(self, month):
        today = fields.Date.context_today(self)
        y, m = [int(x) for x in month.split('-')] if month else (today.year, today.month)
        start = fields.Date.to_date('%04d-%02d-01' % (y, m))
        end = fields.Date.to_date('%04d-01-01' % (y + 1) if m == 12 else '%04d-%02d-01' % (y, m + 1))
        return start, end, calendar.monthrange(y, m)[1]

    @api.model
    def _rating_of(self, points, max_points):
        level = self.env['store.nvbh.rating'].rating_for(100.0 * points / max_points if max_points else 0.0)
        return (level.name, level.tone) if level else ('', 'wait')

    @api.model
    def get_manage_staff(self, month=None, store_id=None, search=None, errors_only=False, active_only=True):
        """Bảng Nhân viên: mỗi nhân viên có lịch làm việc trong tháng (theo cửa hàng) kèm ngày công, tiến độ, lỗi, điểm TB tháng, xếp loại."""
        start, end, days_in_month = self._month_range(month)
        types = dict(SHIFT_TYPES)
        sdomain = [('work_date', '>=', start), ('work_date', '<', end)]
        if store_id:
            sdomain.append(('store_id', '=', int(store_id)))
        if search:
            sdomain.append(('staff_name', 'ilike', search))
        sched = self.env['store.nvbh.schedule.line'].search(sdomain, order='work_date desc, id desc')
        by_line = {c.schedule_line_id.id: c for c in self.search([('schedule_line_id', 'in', sched.ids)])}
        inactive = set()
        if active_only:
            for st in self.env['store.audit.staff'].search([('staff_state', '=', 'inactive')]):
                inactive.add('%s|%s' % ((st.name or '').strip().casefold(), st.store_id.id))
        groups = {}
        for l in sched:
            key = '%s|%s' % ((l.staff_name or '').strip().casefold(), l.store_id.id)
            if key in inactive:
                continue
            shift_type = types.get(l.shift_id.shift_type, '')
            g = groups.setdefault(key, {
                'key': key, 'code': l.employee_code or '', 'name': (l.staff_name or '').strip(), 'store': l.store_id.display_name or '',
                'role': '%s · Ca %s%s' % (l.position or 'NVBH', l.shift_id.code or '', (' / ' + shift_type) if shift_type else ''),
                'position': l.position or 'NVBH', 'shift': l.shift_id.code or '',
                'dates': set(), 'done': 0, 'total': 0, 'errors': 0, 'pct_sum': 0.0, 'pct_n': 0, 'points': 0.0, 'max_points': 0.0})
            if not g['code'] and l.employee_code:
                g['code'] = l.employee_code
            c = by_line.get(l.id)
            if c:
                g['dates'].add(l.work_date)  # ngày công = ngày đã có phiếu check list (không tính ngày chỉ có trong lịch xếp ca)
                mp = sum(c.line_ids.mapped('max_score'))
                g['done'] += c.cnt_done
                g['total'] += c.cnt_total
                g['errors'] += c.error_total
                if c.line_ids and all(x._final_eval()[0] for x in c.line_ids) and mp:
                    g['pct_n'] += 1
                    g['points'] += c.points
                    g['max_points'] += mp
        rows = []
        for g in groups.values():
            if errors_only and not g['errors']:
                continue
            avg = round(100.0 * g['points'] / g['max_points'], 1) if g['pct_n'] and g['max_points'] else None
            label, tone = self._rating_of(g['points'], g['max_points']) if g['pct_n'] else ('Chưa đánh giá', 'wait')
            rows.append({
                'key': g['key'], 'code': g['code'], 'name': g['name'], 'store': g['store'], 'role': g['role'], 'position': g['position'], 'shift': g['shift'],
                'work_days': len(g['dates']), 'days_in_month': days_in_month,
                'done': g['done'], 'total': g['total'], 'errors': g['errors'],
                'avg': avg, 'rating': label, 'rating_key': tone,
            })
        rows.sort(key=lambda r: (r['store'], r['name'].casefold()))
        for i, r in enumerate(rows, 1):
            r['stt'] = i
        return rows

    @api.model
    def get_manage_eval(self, work_date=None, store_id=None, search=None):
        """Bảng Đánh giá: nhân viên có lịch làm việc trong ngày / cửa hàng, kèm tiến độ khai báo, minh chứng, lỗi, điểm CHT chấm, trạng thái duyệt."""
        day = fields.Date.to_date(work_date) or fields.Date.context_today(self)
        domain = [('work_date', '=', day)]
        if store_id:
            domain.append(('store_id', '=', int(store_id)))
        if search:
            domain.append(('staff_name', 'ilike', search))
        sched = self.env['store.nvbh.schedule.line'].search(domain, order='store_id, schedule_id, sequence, id')
        by_line = {c.schedule_line_id.id: c for c in self.search([('schedule_line_id', 'in', sched.ids)])}
        Attachment = self.env['ir.attachment']
        rows = []
        for i, l in enumerate(sched, 1):
            c = by_line.get(l.id)
            row = {
                'stt': i, 'line_id': l.id, 'check_id': c.id if c else 0, 'name': l.staff_name or '', 'store': l.store_id.display_name or '',
                'shift': ('Ca %s' % l.shift_id.code) if l.shift_id else '',
                'done': 0, 'total': 0, 'pct': 0, 'photos': 0, 'errors': 0, 'points': 0.0, 'max_points': 0.0, 'state': 'wait',
            }
            if c:
                lines = c.line_ids
                evaluated = lines.filtered(lambda x: x._final_eval()[0])
                row.update({
                    'done': c.cnt_done, 'total': c.cnt_total, 'pct': round(100.0 * c.cnt_done / c.cnt_total) if c.cnt_total else 0,
                    'photos': Attachment.search_count([('res_model', '=', 'store.nvbh.check.line'), ('res_id', 'in', lines.ids)]) if lines else 0,
                    'errors': c.error_total, 'points': c.points, 'max_points': sum(lines.mapped('max_score')),
                    'state': 'approved' if lines and len(evaluated) == len(lines) else 'wait',
                })
            rows.append(row)
        return rows

    @api.model
    def get_manage_week(self, work_date=None, store_id=None, search=None):
        """Bảng Đánh giá theo tuần: mỗi nhân viên một dòng, mỗi ngày (Thứ 2 -> Chủ nhật) một ô trạng thái:
        ok = đã duyệt / làm đủ không lỗi, bad = có lỗi, wait = chờ duyệt, off = không có lịch (nghỉ)."""
        day = fields.Date.to_date(work_date) or fields.Date.context_today(self)
        monday = day - timedelta(days=day.weekday())
        dates = [monday + timedelta(days=i) for i in range(7)]
        domain = [('work_date', '>=', dates[0]), ('work_date', '<=', dates[-1])]
        if store_id:
            domain.append(('store_id', '=', int(store_id)))
        if search:
            domain.append(('staff_name', 'ilike', search))
        sched = self.env['store.nvbh.schedule.line'].search(domain, order='store_id, schedule_id, sequence, id')
        by_line = {c.schedule_line_id.id: c for c in self.search([('schedule_line_id', 'in', sched.ids)])}
        people = {}
        for l in sched:
            key = '%s|%s' % ((l.staff_name or '').strip().casefold(), l.store_id.id)
            p = people.setdefault(key, {'key': key, 'name': (l.staff_name or '').strip(), 'store': l.store_id.display_name or '', 'cells': {}})
            c = by_line.get(l.id)
            if not c or not c.line_ids:
                st = 'wait'
            elif c.error_total:
                st = 'bad'
            elif all(x._final_eval()[0] for x in c.line_ids):
                st = 'ok'
            else:
                st = 'wait'
            p['cells'][l.work_date] = st
        labels = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']
        rows = [{'key': p['key'], 'name': p['name'], 'store': p['store'], 'cells': [p['cells'].get(d, 'off') for d in dates]}
                for p in sorted(people.values(), key=lambda p: (p['store'], p['name'].casefold()))]
        return {
            'days': [{'label': labels[i], 'date': d.strftime('%d/%m')} for i, d in enumerate(dates)],
            'week_label': '%s - %s' % (dates[0].strftime('%d/%m/%Y'), dates[-1].strftime('%d/%m/%Y')),
            'rows': rows,
        }

    @api.model
    def get_done_monthly(self, month=None, staff_name=None, store_id=None):
        """Bảng checklist Tổng: từng ngày trong tháng của một nhân viên (ngày không có lịch = nghỉ theo lịch) kèm dòng tổng cộng lũy kế."""
        start, end, days_in_month = self._month_range(month)
        types = dict(SHIFT_TYPES)
        weekdays = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']
        name = (staff_name or '').strip()
        if not name:
            return {'staff': '', 'rows': [], 'total': False}
        base = [('work_date', '>=', start), ('work_date', '<', end), ('staff_name', '=ilike', name)]
        if store_id:
            base.append(('store_id', '=', int(store_id)))
        checks = self.search(base, order='work_date, id')
        sched = self.env['store.nvbh.schedule.line'].search(base)
        by_date = {}
        for c in checks:
            by_date.setdefault(c.work_date, []).append(c)
        sched_by_date = {}
        for l in sched:
            sched_by_date.setdefault(l.work_date, l)
        rows = []
        tot = {'total': 0, 'done': 0, 'todo': 0, 'errors': 0, 'points': 0.0, 'max_points': 0.0, 'days': 0, 'valid': 0,
               'pts_cht': 0.0, 'pts_asm': 0.0}
        avg_src = {'points': [], 'cht': [], 'asm': [], 'pct': []}  # dòng cuối bảng dùng AVERAGE: chỉ tính các ngày có số liệu
        day_set = set()
        store_name = (sched[:1].store_id.display_name or checks[:1].store_id.display_name or '')
        for i in range(days_in_month):
            day = start + timedelta(days=i)
            base_row = {'date': day.strftime('%d/%m/%Y'), 'weekday': weekdays[day.weekday()], 'pts_cht': None, 'pts_asm': None}
            items = by_date.get(day)
            if not items:
                line = sched_by_date.get(day)
                if line:
                    rows.append(dict(base_row, kind='pending', code='-', store=line.store_id.display_name or '',
                                     shift=line.shift_id.code or '-',
                                     status='Chưa check list', total=0, done=0, todo=0, errors=0, points=0, max_points=0, pct=0,
                                     control='Chờ đánh giá', note=''))
                    store_name = store_name or (line.store_id.display_name or '')
                else:
                    rows.append(dict(base_row, kind='off', code='-', store=store_name, shift='OFF', status='Nghỉ theo lịch', total=0, done=0,
                                     todo=0, errors=0, points=0, max_points=0, pct=0, control='-',
                                     note=''))
                continue
            for c in items:
                lines = c.line_ids
                mp = sum(lines.mapped('max_score'))
                evaluated = bool(lines) and all(x._final_eval()[0] for x in lines)  # đã đánh giá đủ mọi dòng
                pct = round(100.0 * c.points / mp, 1) if mp else 0.0
                done_all = bool(c.cnt_total) and c.cnt_todo == 0
                # Ghi chú / Tóm tắt công việc (lấy từ các dòng checklist công việc của phiếu)
                order = {label: n for n, (_k, label) in enumerate(TASK_GROUPS)}
                ordered = lines.sorted(lambda x: (order.get(x.sub_category, len(order)), x.sequence, x.id))
                tags = {'avg': 'T.Bình', 'bad': 'không đạt'}

                def tag(x):
                    return 'lỗi' if x.error_count else 'chưa làm' if x.status == 'todo' else tags.get(x._final_eval()[0], '')

                if evaluated:  # việc bị trừ điểm: T.Bình / không đạt / có lỗi (điểm đạt < điểm chuẩn)
                    short = [x for x in ordered if (x.actual_score or 0.0) < (x.max_score or 0.0)]
                else:
                    short = [x for x in ordered if x.error_count or x.status == 'todo']
                lost = sum((x.max_score or 0.0) - (x.actual_score or 0.0) for x in short) if evaluated else 0.0
                if not short and done_all:
                    note = 'Hoàn thành đầy đủ %d/%d công việc trong ca' % (c.cnt_total, c.cnt_total) + ('' if evaluated else ' (chờ đánh giá)')
                else:
                    note = ('Đạt %d/%d việc' % (len(ordered) - len(short), len(ordered))) if evaluated \
                        else 'Đã làm %d/%d việc' % (c.cnt_done, c.cnt_total)
                    if short:
                        note += '; cần xử lý: %s%s' % (
                            ', '.join('%s (%s)' % (x.name, tag(x)) if tag(x) else x.name for x in short),
                            (' (-%gđ)' % round(lost, 2)) if evaluated and lost else '')
                if not evaluated:
                    control = 'Chờ đánh giá'
                else:
                    control = 'Đã đánh giá'
                store_name = store_name or (c.store_id.display_name or '')
                pts_cht, pts_asm = c._step_points('CHT'), c._step_points('ASM')
                rows.append(dict(
                    base_row, pts_cht=pts_cht, pts_asm=pts_asm, kind='error' if (c.error_total or not done_all or (evaluated and c.points < mp)) else 'ok',
                    evaluated=evaluated, id=c.id, code=c.name or '-',
                    store=c.store_id.display_name or '',
                    shift=c.shift_id.code or '-',
                    status='Hoàn thành' if done_all else 'Chưa hoàn thành', total=c.cnt_total, done=c.cnt_done, todo=c.cnt_todo,
                    errors=c.error_total, points=c.points, max_points=mp, pct=pct, control=control, note=note))
                tot['total'] += c.cnt_total
                tot['done'] += c.cnt_done
                tot['todo'] += c.cnt_todo
                tot['errors'] += c.error_total
                tot['pts_cht'] += pts_cht or 0.0
                tot['pts_asm'] += pts_asm or 0.0
                if evaluated:
                    avg_src['points'].append(c.points)
                    avg_src['pct'].append(pct)
                if pts_cht is not None:
                    avg_src['cht'].append(pts_cht)
                if pts_asm is not None:
                    avg_src['asm'].append(pts_asm)
                if evaluated:  # ngày chưa đánh giá không tính vào điểm lũy kế / tỷ lệ
                    tot['points'] += c.points
                    tot['max_points'] += mp
                day_set.add(day)
                tot['valid'] += 1 if evaluated else 0
        tot['days'] = len(day_set)

        def average(values):  # như hàm AVERAGE() của Excel: bỏ qua ô trống; không có số nào thì None
            return round(sum(values) / len(values), 2) if values else None

        tot['avg_points'] = average(avg_src['points'])
        tot['avg_cht'] = average(avg_src['cht'])
        tot['avg_asm'] = average(avg_src['asm'])
        tot['avg_pct'] = average(avg_src['pct'])
        tot['pct'] = round(100.0 * tot['points'] / tot['max_points'], 1) if tot['max_points'] else 0.0
        return {'staff': name, 'days_in_month': days_in_month, 'rows': rows, 'total': tot}

    @api.model
    def _xlsx_book(self, sheets, filename):
        """Dựng file Excel: mỗi phần tử của sheets (name, title, subtitle, headers, rows, foot) là một sheet."""
        import re
        import xlsxwriter
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        f_title = book.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'font_color': '#1E3A6E'})
        f_sub = book.add_format({'italic': True, 'align': 'center', 'font_color': '#475569'})
        f_head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1E3A6E', 'align': 'center', 'valign': 'vcenter',
                                  'border': 1, 'text_wrap': True})
        f_cell = book.add_format({'border': 1, 'valign': 'vcenter', 'text_wrap': True})
        f_mid = book.add_format({'border': 1, 'valign': 'vcenter', 'align': 'center', 'text_wrap': True})
        f_num = book.add_format({'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '#,##0.##'})
        f_foot = book.add_format({'bold': True, 'border': 1, 'bg_color': '#DBE7F5', 'valign': 'vcenter', 'text_wrap': True})
        f_foot_num = book.add_format({'bold': True, 'border': 1, 'bg_color': '#DBE7F5', 'align': 'center', 'num_format': '#,##0.##'})
        used = set()
        for sh in sheets:
            name = re.sub(r'[\[\]:*?/\\]', ' ', sh.get('name') or 'Bang checklist').strip()[:31] or 'Bang checklist'
            base, k = name, 2
            while name.lower() in used:
                suffix = ' (%d)' % k
                name, k = base[:31 - len(suffix)] + suffix, k + 1
            used.add(name.lower())
            sheet = book.add_worksheet(name)
            headers = sh.get('headers') or []
            n = max(len(headers), 1)
            sheet.merge_range(0, 0, 0, n - 1, sh.get('title') or '', f_title)
            sheet.merge_range(1, 0, 1, n - 1, sh.get('subtitle') or '', f_sub)
            sheet.set_row(0, 28)
            for c, h in enumerate(headers):
                sheet.write(3, c, h, f_head)
            sheet.set_row(3, 34)
            widths = [len(str(h)) for h in headers]

            def put(r, c, v, text_fmt, num_fmt):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    sheet.write_number(r, c, v, num_fmt)
                    size = len(str(v))
                else:
                    v = '' if v is None else str(v)
                    sheet.write_string(r, c, v, text_fmt if len(v) > 14 else (f_mid if text_fmt is f_cell else text_fmt))
                    size = min(len(v), 60)
                widths[c] = max(widths[c], size)

            r = 4
            for row in sh.get('rows') or []:
                for c, v in enumerate(row[:n]):
                    put(r, c, v, f_cell, f_num)
                r += 1
            if sh.get('foot'):
                for c, v in enumerate(sh['foot'][:n]):
                    put(r, c, v, f_foot, f_foot_num)
            for c, w in enumerate(widths):
                sheet.set_column(c, c, max(8, min(w + 2, 60)))
            sheet.freeze_panes(4, 0)
            sheet.set_landscape()
            sheet.set_paper(9)
            sheet.fit_to_pages(1, 0)
            sheet.repeat_rows(3)
        book.close()
        return {'name': '%s_%s.xlsx' % (filename, fields.Date.context_today(self).strftime('%Y%m%d')),
                'data': base64.b64encode(buf.getvalue()).decode()}

    @api.model
    def export_table_xlsx(self, title, subtitle, headers, rows, foot=None, filename='Bang_checklist'):
        """Xuất bảng đang hiển thị (Bảng Nhân viên / Bảng Đánh giá) ra Excel: tiêu đề, dòng tiêu đề cột, dữ liệu, dòng tổng."""
        self.env['store.perm.rule'].check_export()
        return self._xlsx_book([{'name': 'Bang checklist', 'title': title, 'subtitle': subtitle, 'headers': headers, 'rows': rows, 'foot': foot}], filename)

    _MONTHLY_HEADERS = ['Ngày', 'Cửa hàng', 'Mã ca', 'Trạng thái ngày', 'Tổng việc ca', 'Đã làm', 'Số lỗi', 'Điểm đạt', 'Điểm chuẩn ca',
                        'Điểm CHT đánh giá', 'Điểm ASM đánh giá', 'Tỷ lệ đạt (%)', 'Kết quả', 'Ghi chú / Tóm tắt công việc']

    @api.model
    def export_done_monthly_xlsx(self, month=None, staff_names=None, store_id=None, only_work=True):
        """Bảng checklist Tổng: xuất Excel cho các nhân viên được chọn, mỗi nhân viên một sheet."""
        self.env['store.perm.rule'].check_export()
        start, _end, days_in_month = self._month_range(month)
        label = start.strftime('%m/%Y')
        sheets = []
        for name in staff_names or []:
            data = self.get_done_monthly(month, name, store_id)
            tot = data.get('total') or {}
            rows = [[r['date'], r['store'] or '-', 'OFF' if r['kind'] == 'off' else r['shift'], r['status'], r['total'], r['done'], r['errors'],
                     r['points'] if (r['kind'] == 'off' or r.get('evaluated')) else '-', r['max_points'],
                     '-' if r.get('pts_cht') is None else r['pts_cht'], '-' if r.get('pts_asm') is None else r['pts_asm'],
                     ('%s%%' % ('%g' % r['pct']).replace('.', ',')) if (r['kind'] == 'off' or r.get('evaluated')) else '-', r['control'], r['note'] or '-']
                    for r in data['rows'] if not (only_work and r['kind'] == 'off')]
            foot = ['TỔNG CỘNG KỲ %s (%s ngày công thực tế)' % (label, tot.get('days', 0)), '', '', '', tot.get('total', 0), tot.get('done', 0),
                    tot.get('errors', 0), tot.get('avg_points') if tot.get('avg_points') is not None else '-', tot.get('max_points', 0),
                    tot.get('avg_cht') if tot.get('avg_cht') is not None else '-', tot.get('avg_asm') if tot.get('avg_asm') is not None else '-',
                    ('%s%%' % ('%g' % tot['avg_pct']).replace('.', ',')) if tot.get('avg_pct') is not None else '-',
                    '%s/%s công hợp lệ' % (tot.get('valid', 0), tot.get('days', 0)), 'Tự động liên kết sang dữ liệu Odoo']
            sheets.append({'name': name, 'title': 'BẢNG CHECKLIST TỔNG', 'subtitle': 'Nhân viên: %s | Tháng: %s' % (name, label),
                           'headers': self._MONTHLY_HEADERS, 'rows': rows, 'foot': foot})
        if not sheets:
            raise UserError(_('Chưa chọn nhân viên nào để xuất.'))
        return self._xlsx_book(sheets, 'Bang_checklist_tong')

    @api.model
    def read_checklist(self, check_id):
        """Nội dung một checklist đã lưu (popup ở Danh sách checklist NV)."""
        check = self.browse(int(check_id)).exists()
        return check._checklist_payload() if check else False

    @api.model
    def delete_checks(self, check_ids):
        """Quản trị viên xóa checklist đã lưu (Danh sách checklist NV)."""
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Chỉ Quản trị viên mới được xóa checklist.'))
        self.sudo().browse([int(i) for i in check_ids]).exists().unlink()
        return True

    @api.model
    def toggle_line(self, line_id, done):
        line = self.env['store.nvbh.check.line'].browse(int(line_id)).exists()
        line.check_id._assert_can_execute()
        line.is_done = bool(done)
        return line.check_id._checklist_payload()

    @api.model
    def save_note(self, line_id, note):
        line = self.env['store.nvbh.check.line'].browse(int(line_id)).exists()
        line.check_id._assert_can_execute()
        line.note = (note or '').strip() or False
        return line.check_id._checklist_payload()

    @api.model
    def toggle_all(self, check_id, done):
        check = self.browse(int(check_id)).exists()
        check._assert_can_execute()
        check.line_ids.write({'is_done': bool(done)})
        return check._checklist_payload()


    def init(self):
        cr = self.env.cr
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'store_nvbh_check' AND column_name = 'submitted'")
        if cr.fetchone():
            cr.execute("""
                UPDATE store_nvbh_check c SET submitted = TRUE, submit_date = COALESCE(c.submit_date, c.write_date)
                 WHERE c.submitted IS NOT TRUE AND EXISTS (
                     SELECT 1 FROM store_nvbh_check_line l WHERE l.check_id = c.id
                        AND (l.is_done OR COALESCE(btrim(l.note), '') <> ''))
            """)


class StoreNvbhCheckLine(models.Model):
    _name = 'store.nvbh.check.line'
    _description = 'Dòng checklist công việc NVBH'
    _order = 'sequence, id'

    check_id = fields.Many2one('store.nvbh.check', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    task_id = fields.Many2one('store.nvbh.task', string='Công việc', ondelete='set null')
    name = fields.Char(string='Công việc', required=True)
    sub_category = fields.Char(string='Nhóm công việc')
    time_slot = fields.Char(string='Thời gian')
    controller = fields.Char(string='Người kiểm soát')
    max_score = fields.Float(string='Điểm')
    is_done = fields.Boolean(string='Có làm', default=False)
    note = fields.Char(string='Ghi chú')
    # Đánh giá của CHT / người kiểm soát (popup ở Danh sách checklist NV)
    reviewer_id = fields.Many2one('res.users', string='Người đánh giá (CHT)')
    eval_result = fields.Selection(EVAL_RESULTS, string='KQ đánh giá')
    error_detail = fields.Text(string='Chi tiết lỗi')
    # Đánh giá của các cấp tiếp theo trong luồng (bước 2, 3, 4): mỗi cấp lưu độc lập; điểm chính thức lấy ở cấp cuối cùng đã xong
    asm_reviewer_id = fields.Many2one('res.users', string='Người đánh giá (bước 2)')
    asm_eval_result = fields.Selection(EVAL_RESULTS, string='KQ đánh giá (bước 2)')
    asm_error_detail = fields.Text(string='Chi tiết lỗi (bước 2)')
    rsm_reviewer_id = fields.Many2one('res.users', string='Người đánh giá (bước 3)')
    rsm_eval_result = fields.Selection(EVAL_RESULTS, string='KQ đánh giá (bước 3)')
    rsm_error_detail = fields.Text(string='Chi tiết lỗi (bước 3)')
    adm_reviewer_id = fields.Many2one('res.users', string='Người duyệt (bước 4)')
    adm_eval_result = fields.Selection(EVAL_RESULTS, string='KQ đánh giá (bước 4)')
    adm_error_detail = fields.Text(string='Chi tiết lỗi (bước 4)')
    error_count = fields.Integer(string='Số lỗi', compute='_compute_error_count', store=True,
                                 help='Mỗi dòng trong Chi tiết lỗi là một lỗi')
    actual_score = fields.Float(string='Điểm đạt', compute='_compute_actual_score', store=True,
                                help='Đạt = điểm chuẩn; T.Bình = điểm chuẩn / 2; Không đạt, chưa đánh giá hoặc có ghi lỗi = 0')

    def _final_eval(self):
        """(KQ, chi tiết lỗi) dùng để tính điểm: lấy kết quả của cấp đánh giá cuối cùng đã hoàn tất trong luồng của phiếu."""
        self.ensure_one()
        for i in range(min(self.check_id.step_done, len(STEP_PREFIX)), 0, -1):
            pre = STEP_PREFIX[i - 1]
            if self[pre + 'eval_result']:
                return self[pre + 'eval_result'], self[pre + 'error_detail']
        return False, False

    @api.depends('error_detail', 'asm_error_detail', 'asm_eval_result', 'rsm_error_detail', 'rsm_eval_result',
                 'adm_error_detail', 'adm_eval_result', 'eval_result', 'check_id.step_done')
    def _compute_error_count(self):
        for rec in self:
            rec.error_count = count_errors(rec._final_eval()[1])

    def _init_scores(self):
        # tính lại Số lỗi và Điểm đạt cho dữ liệu cũ (1 dòng chi tiết lỗi = 1 lỗi; có lỗi thì điểm = 0)
        cr = self.env.cr
        cr.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'store_nvbh_check_line' "
                   "AND column_name IN ('error_detail', 'error_count', 'actual_score', 'eval_result')")
        if cr.fetchone()[0] == 4:
            cr.execute(r'''
                UPDATE store_nvbh_check_line l SET error_count = COALESCE((
                    SELECT count(*) FROM regexp_split_to_table(COALESCE(l.error_detail, ''), E'\n') AS t WHERE btrim(t, E' \t\r') <> ''), 0)
                WHERE l.error_count IS NULL
            ''')
            cr.execute('''
                UPDATE store_nvbh_check_line SET actual_score = CASE
                    WHEN error_count > 0 THEN 0 WHEN eval_result = 'good' THEN COALESCE(max_score, 0)
                    WHEN eval_result = 'avg' THEN round((COALESCE(max_score, 0) / 2)::numeric, 2) ELSE 0 END
                WHERE actual_score IS NULL
            ''')

    @api.depends('eval_result', 'max_score', 'error_detail', 'asm_eval_result', 'asm_error_detail', 'rsm_eval_result',
                 'rsm_error_detail', 'adm_eval_result', 'adm_error_detail', 'check_id.step_done')
    def _compute_actual_score(self):
        for rec in self:
            result, detail = rec._final_eval()
            rec.actual_score = eval_score(rec.max_score, result, count_errors(detail))
    # Đã làm = tích Có làm; Đang làm = chưa tích nhưng có ghi chú; còn lại Chưa làm
    status = fields.Selection(LINE_STATES, string='Trạng thái', compute='_compute_status', store=True)

    @api.depends('is_done', 'note')
    def _compute_status(self):
        for rec in self:
            rec.status = 'done' if rec.is_done else ('doing' if (rec.note or '').strip() else 'todo')

    def init(self):
        # trạng thái cũ (chỉ Chưa làm / Đang làm = có làm) quy lại theo quy tắc mới: Đã làm / Đang làm / Chưa làm
        cr = self.env.cr
        cr.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'store_nvbh_check_line' "
                   "AND column_name IN ('is_done', 'note', 'status')")
        if cr.fetchone()[0] == 3:
            cr.execute("UPDATE store_nvbh_check_line SET status = CASE WHEN is_done THEN 'done' "
                       "WHEN COALESCE(btrim(note), '') <> '' THEN 'doing' ELSE 'todo' END")
        self._init_scores()
