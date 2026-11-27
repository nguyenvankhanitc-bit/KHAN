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


# loại check list -> (model Danh sách công việc, trường liên kết trên dòng check list)
TASK_SOURCES = {'cht': ('store.cht.task', 'cht_task_id'), 'asm': ('store.asm.task', 'asm_task_id')}

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
    shift_type = fields.Selection(related='shift_id.shift_type', string='Loại ca', store=True, readonly=True)
    work_date = fields.Date(string='Ngày', required=True, default=fields.Date.context_today)
    staff_name = fields.Char(string='Nhân viên')
    schedule_line_id = fields.Many2one('store.nvbh.schedule.line', string='Dòng lịch làm việc', ondelete='set null', index=True)
    # check list ASM: không theo lịch xếp ca, mỗi ASM (hồ sơ nhân viên chức vụ ASM) một phiếu mỗi ngày
    asm_employee_id = fields.Many2one('hr.employee', string='ASM', ondelete='set null', index=True)
    # Đánh giá Checklist CHT theo tuần: nhận xét tổng quan của ASM, lưu vào các phiếu được duyệt trong tuần
    week_comment = fields.Text(string='Nhận xét đánh giá tuần (ASM)')
    staff_id = fields.Many2one('store.audit.staff', string='NVBH (cũ)')
    # NVBH: công việc lấy từ Danh sách công việc NVBH; CHT: người trên lịch xếp ca có chức vụ cấp 2 (CHT...),
    # công việc lấy từ Danh sách công việc CHT, luồng CHT check list -> ASM đánh giá -> Admin phê duyệt (nếu bật)
    # ASM: người trên lịch xếp ca có chức vụ cấp 3 (ASM), công việc theo Danh sách công việc ASM,
    # luồng ASM check list -> RSM đánh giá (nếu có) -> Admin / Admin tổng duyệt kết quả cuối cùng
    kind = fields.Selection([('nvbh', 'NVBH'), ('cht', 'CHT'), ('asm', 'ASM')], string='Loại check list', default='nvbh', required=True, index=True)
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

    def _waiting_code(self):
        """Phiếu đang chờ ai: 'NV' (người thực hiện chưa làm xong), mã cấp đang đến lượt đánh giá (CHT / ASM / RSM) hoặc 'Admin';
        rỗng nếu đã hoàn tất."""
        self.ensure_one()
        if self.state == 'approved':
            return ''
        chain = self._approval_chain()
        staff_done = bool(self.line_ids) and all(self.line_ids.mapped('is_done'))
        if self.state == 'draft':
            if not staff_done:
                return 'NV'
            idx = 0
        elif not staff_done and self._self_edit_open():
            # người thực hiện sửa lại sau khi gửi, còn dòng chưa tích "Có làm" và vẫn trong hạn sửa (đến 23h55): đang chờ người thực hiện
            return 'NV'
        else:
            idx = self.step_done
        if idx >= len(chain):
            return ''
        st = chain[idx]
        return 'Admin' if st['admin_only'] else (st['code'] or '')

    @api.model
    def _hide_cht(self):
        """True: người dùng không có quyền Xem mục "Checklist CV CHT" -> không thấy phiếu / người làm check list CHT ở mọi trang
        (vd. tài khoản cửa hàng CH_..., nhân viên). Quản trị / Quản lý / user không áp ma trận quyền thì thấy."""
        rights = self.env['store.perm.rule']._rights()
        return rights is not None and not rights.get('nvbh_cht', {}).get('read')

    @api.model
    def _hide_asm(self):
        """True: người dùng không có quyền Xem mục "Checklist CV ASM" -> không thấy phiếu / người làm check list ASM."""
        rights = self.env['store.perm.rule']._rights()
        if rights is None or rights.get('nvbh_asmcv', {}).get('read'):
            return False
        # Admin / Admin tổng duyệt kết quả cuối cùng nên luôn xem được
        return self.env.user not in self._admin_title_employees().mapped('user_id')

    @api.model
    def _hidden_kinds(self):
        """Các loại check list người dùng hiện tại không được xem (cht / asm)."""
        return [k for k, hide in (('cht', self._hide_cht), ('asm', self._hide_asm)) if hide()]

    def _assert_cht_visible(self):
        hidden = self._hidden_kinds()
        if any(c.kind in hidden for c in self):
            raise AccessError(_('Bạn không có quyền xem check list %s.') % ', '.join(sorted({c.kind.upper() for c in self if c.kind in hidden})))

    @api.model
    def _schedule_kind(self, schedule_line):
        """Loại check list của một dòng lịch xếp ca: chức vụ cấp 2 (CHT, CHTTT, ASMTT) -> 'cht', cấp 3 (ASM) -> 'asm', còn lại 'nvbh'."""
        from .store_role import role_level
        return {2: 'cht', 3: 'asm'}.get(role_level((schedule_line.position or '').strip().upper()), 'nvbh')

    @api.model
    def _cht_line_commands(self, work_date=None, kind='cht'):
        """Dòng công việc CHT / ASM: mọi việc trong Danh sách công việc CHT (ASM) đến hạn ngày work_date (theo tần suất / thứ / ngày trong tháng)."""
        model, fk = TASK_SOURCES[kind]
        tasks = self.env[model].sudo().search([])
        if work_date:
            tasks = tasks.filtered(lambda t: t.runs_on(work_date))
        tasks = tasks.sorted(lambda t: (t.group_id.sequence if t.group_id else 9999, t.group_id.id or 0, t.sequence, t.id))
        return [Command.create({
            fk: t.id,
            'sequence': t.sequence,
            'name': t.name,
            'sub_category': t.group_id.name or 'Khác',
            'time_slot': t.time_slot,
            'controller': t.controller,
            'max_score': t.score,
            'is_done': False,
        }) for t in tasks]

    @api.model
    def _task_line_commands(self, shift, work_date=None, kind='nvbh'):
        """Một dòng cho mỗi công việc áp dụng cho Loại ca của Mã ca và cho Thứ của ngày làm việc (theo thứ tự trong bảng công việc NVBH).
        kind = 'cht': lấy theo Danh sách công việc CHT (không phụ thuộc ca)."""
        if kind in TASK_SOURCES:
            return self._cht_line_commands(work_date, kind)
        groups = dict(TASK_GROUPS)
        if not shift or not shift.shift_type_id:
            return []
        tasks = self.env['store.nvbh.task'].search([('shift_type_ids', 'in', shift.shift_type_id.id)], order='sequence, id')
        tasks = tasks.filtered(lambda t: t.runs_on(work_date)).sorted(
            lambda t: (t.group_id.sequence if t.group_id else 9999, t.group_id.id or 0, t.task_group or '', t.sequence, t.id))
        return [Command.create({
            'task_id': t.id,
            'sequence': t.sequence,
            'name': t.name,
            'sub_category': t.group_id.name or groups.get(t.task_group) or 'Khác',
            'time_slot': t.time_slot,
            'controller': t.controller,
            'max_score': t.score,
            'is_done': False,
        }) for t in tasks]

    def _fully_evaluated(self):
        """Phiếu đã được đánh giá xong ở MỌI cấp trong luồng (CHT -> ASM -> ...), nghĩa là trạng thái "Đã hoàn tất đánh giá" và mọi dòng đã có kết quả.
        Phiếu mới qua cấp 1 (CHT) mà cấp trên (ASM) chưa đánh giá vẫn tính là "Chờ đánh giá"."""
        self.ensure_one()
        if not self.line_ids:
            return False
        if self.state == 'approved' and all(ln._final_eval()[0] for ln in self.line_ids):
            return True
        # quá hạn chỉnh sửa (hệ thống đã tự khóa) mà chưa đánh giá xong: chốt với điểm hiện có, chưa đánh giá thì mặc định 0đ
        return self._is_expired()

    @api.model
    def _sync_open_checks_by_weekday(self, domain=None):
        """Cập nhật lại các phiếu "Đang thực hiện" theo Thứ áp dụng của công việc (Cài đặt > Danh sách công việc NVBH):
        bỏ các dòng công việc không áp dụng cho thứ của ngày làm việc và thêm các dòng còn thiếu.
        Dòng nhân viên đã tích / ghi chú / đã được đánh giá thì giữ nguyên để không mất dữ liệu. Trả về (số dòng bỏ, số dòng thêm)."""
        removed = added = 0
        checks = self.sudo().search([('state', '=', 'draft'), ('submitted', '=', False)] + list(domain or []))
        for chk in checks:
            if chk.kind not in TASK_SOURCES and (not chk.shift_id or not chk.shift_id.shift_type_id):
                continue
            fk = TASK_SOURCES[chk.kind][1] if chk.kind in TASK_SOURCES else 'task_id'
            wanted = self._task_line_commands(chk.shift_id, chk.work_date, chk.kind)
            wanted_ids = {cmd[2][fk] for cmd in wanted}
            have = {ln[fk].id: ln for ln in chk.line_ids if ln[fk]}
            drop = chk.line_ids.filtered(
                lambda ln: ln[fk] and ln[fk].id not in wanted_ids
                and not (ln.is_done or ln.note or ln.eval_result or ln.asm_eval_result or ln.rsm_eval_result or ln.adm_eval_result or ln.error_detail))
            missing = [cmd for cmd in wanted if cmd[2][fk] not in have]
            if drop or missing:
                chk.write({'line_ids': [Command.delete(ln.id) for ln in drop] + missing})
                removed += len(drop)
                added += len(missing)
        return removed, added

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        # chọn Ca -> nạp công việc áp dụng cho Mã ca đó (chỉ khi phiếu mới)
        if not self._origin.id:
            self.line_ids = [Command.clear()] + self._task_line_commands(self.shift_id, self.work_date)

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
    def get_job_overview(self, store_id, work_date, kind='nvbh'):
        """Trang Check list công việc: tất cả nhân viên có lịch làm việc trong ngày kèm tiến độ (đã làm / tổng việc, điểm, đã check list chưa),
        và danh sách nhân viên của cửa hàng không có lịch (nghỉ OFF)."""
        if kind == 'asm' and work_date and kind not in self._hidden_kinds():
            return self._asm_overview(work_date)
        if not store_id or not work_date or kind in self._hidden_kinds():
            return {'staff': [], 'off': [], 'store_staff': 0}
        lines = self.env['store.nvbh.schedule.line'].search(
            [('store_id', '=', int(store_id)), ('work_date', '=', work_date)], order='schedule_id, sequence, id')
        # trang NVBH: mọi người trên lịch trừ CHT (cấp 2); trang CHT: chỉ người có chức vụ cấp 2
        lines = lines.filtered(lambda l: self._schedule_kind(l) == kind)
        checks = {c.schedule_line_id.id: c for c in self.search([('schedule_line_id', 'in', lines.ids)])}
        staff = []
        for i, l in enumerate(lines, 1):
            c = checks.get(l.id)
            total = c.cnt_total if c and c.kind == kind else len(self._task_line_commands(l.shift_id, work_date, kind))
            staff.append({
                'id': l.id, 'stt': i, 'name': l.staff_name or '', 'shift': l.shift_id.code or '',
                'done': c.cnt_done if c else 0, 'total': total, 'points': c.points if c else 0.0,
                'finished': bool(c and c.submitted and total and c.cnt_todo == 0),
            })
        scheduled = {(s['name'] or '').strip().casefold() for s in staff}
        from .store_role import role_level
        roster = self.env['store.audit.staff'].search([('store_id', '=', int(store_id)), ('staff_state', '=', 'active'),
                                                        ('position', '!=', 'RSM')])
        want = {'cht': 2, 'asm': 3}.get(kind)
        roster = roster.filtered(lambda r: role_level((r.position or '').strip().upper()) == want if want
                                 else role_level((r.position or '').strip().upper()) not in (2, 3))
        names = {}
        for r in roster:
            names.setdefault((r.name or '').strip().casefold(), (r.name or '').strip())
        off = sorted(n for k, n in names.items() if k not in scheduled)
        return {'staff': staff, 'off': off, 'store_staff': len(set(names) | scheduled)}

    @api.model
    def _asm_employees(self):
        """ASM hiển thị ở trang Checklist CV ASM: người đăng nhập là ASM -> chỉ chính mình; còn lại (RSM, Admin, Quản lý...) -> mọi ASM có User Odoo."""
        emps = self.env['hr.employee'].sudo().search([('checklist_level', '=', 3), ('user_id', '!=', False)])
        emps = emps.filtered(lambda e: e._checklist_effective_level() == 3)
        me = emps.filtered(lambda e: e.user_id == self.env.user)
        return (me or emps).sorted(lambda e: (e.name or '').casefold())

    @api.model
    def _asm_schedule_line(self, emp, day):
        """Dòng lịch xếp ca (chức vụ ASM, không phải ca OFF) của ASM trong ngày; khớp theo ID HRM rồi theo họ tên."""
        lines = self.env['store.nvbh.schedule.line'].sudo().search(
            [('work_date', '=', day), ('position', '=ilike', 'ASM')], order='id')
        lines = lines.filtered(lambda l: (l.shift_id.code or '').strip().upper() != 'OFF')
        codes = {str(emp[f]).strip() for f in ('barcode', 'ma_cham_cong', 'ma_nv_ke_toan') if f in emp._fields and emp[f]}
        name = (emp.name or '').strip().casefold()
        return (lines.filtered(lambda l: (l.employee_code or '').strip() in codes) if codes else lines.browse()) \
            or lines.filtered(lambda l: (l.staff_name or '').strip().casefold() == name)

    @api.model
    def _asm_overview(self, work_date):
        """Thẻ ASM có lịch làm trong ngày (Lịch xếp ca, chức vụ ASM); ASM không có lịch / ca OFF -> danh sách Nghỉ OFF."""
        day = fields.Date.to_date(work_date)
        emps = self._asm_employees()
        checks = {c.asm_employee_id.id: c for c in self.sudo().search(
            [('kind', '=', 'asm'), ('work_date', '=', day), ('asm_employee_id', 'in', emps.ids)])}
        n_tasks = len(self._cht_line_commands(day, 'asm'))
        staff, off = [], []
        for e in emps:
            line = self._asm_schedule_line(e, day)[:1]
            if not line:
                off.append(e.name or '')
                continue
            c = checks.get(e.id)
            total = c.cnt_total if c else n_tasks
            staff.append({
                'id': -e.id, 'stt': len(staff) + 1, 'name': e.name or '', 'shift': line.shift_id.code or '',
                'done': c.cnt_done if c else 0, 'total': total, 'points': c.points if c else 0.0,
                'finished': bool(c and c.submitted and total and c.cnt_todo == 0),
            })
        return {'staff': staff, 'off': off, 'store_staff': len(emps)}

    @api.model
    def _asm_store(self, emp):
        """Cửa hàng gắn với phiếu ASM (chỉ để lưu / lọc theo miền): cửa hàng đầu tiên ASM phụ trách."""
        Store = self.env['hr.store'].sudo()
        ids = []
        try:
            ids = sorted(emp.user_id._linkq_allowed_hr_store_ids()) if emp.user_id else []
        except Exception:
            ids = []
        store = Store.browse(ids[:1]).exists() or emp.checklist_store_ids[:1]
        if not store and 'store_id' in emp._fields and emp.store_id and emp.store_id._name == 'hr.store':
            store = emp.store_id
        return store or Store.search([], limit=1)

    @api.model
    def get_asm_checklist(self, employee_id, work_date):
        """Phiếu check list ASM của một ASM trong ngày; chưa có thì tự tạo theo Danh sách công việc ASM."""
        if 'asm' in self._hidden_kinds():
            raise AccessError(_('Bạn không có quyền xem check list ASM.'))
        emp = self.env['hr.employee'].sudo().browse(abs(int(employee_id))).exists()
        day = fields.Date.to_date(work_date)
        if not emp or not day:
            return False
        if emp not in self._asm_employees():
            raise AccessError(_('Bạn không có quyền xem check list ASM của %s.') % emp.name)
        check = self.sudo().search([('kind', '=', 'asm'), ('asm_employee_id', '=', emp.id), ('work_date', '=', day)], limit=1)
        line = self._asm_schedule_line(emp, day)[:1]
        if not check:
            # như NVBH: chỉ ASM có lịch làm trong ngày (Lịch xếp ca, chức vụ ASM) mới có check list
            if not line:
                raise UserError(_('%s không có lịch làm ngày %s (Lịch xếp ca chức vụ ASM) nên chưa có check list.')
                                % (emp.name, day.strftime('%d/%m/%Y')))
            check = self.sudo().create({
                'store_id': line.store_id.id, 'work_date': day, 'staff_name': emp.name, 'asm_employee_id': emp.id, 'kind': 'asm',
                'shift_id': line.shift_id.id, 'schedule_line_id': line.id,
                'line_ids': self._cht_line_commands(day, 'asm'),
            })
        elif line and not check.schedule_line_id:
            check.sudo().write({'schedule_line_id': line.id, 'shift_id': line.shift_id.id})
        return self.browse(check.id)._checklist_payload()

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
        kind = self._schedule_kind(line)
        if kind in self._hidden_kinds():
            raise AccessError(_('Bạn không có quyền xem check list %s.') % kind.upper())
        check = self.search([('schedule_line_id', '=', line.id)], limit=1)
        if not check:
            check = self.create({
                'store_id': line.store_id.id,
                'work_date': line.work_date,
                'shift_id': line.shift_id.id,
                'staff_name': line.staff_name,
                'schedule_line_id': line.id,
                'kind': kind,
                'line_ids': self._task_line_commands(line.shift_id, line.work_date, kind),
            })
        elif check.kind != kind and check.state == 'draft' and not check.submitted and not any(
                l.is_done or l.note or l.eval_result for l in check.line_ids):
            # phiếu cũ của CHT / ASM tạo theo công việc NVBH, chưa làm gì: đổi sang công việc CHT / ASM
            check.sudo().write({'kind': kind, 'line_ids': [Command.clear()] + self._task_line_commands(line.shift_id, line.work_date, kind)})
        return check._checklist_payload()

    def _checklist_payload(self):
        self.ensure_one()
        if self.kind in TASK_SOURCES:  # nhóm công việc CHT / ASM theo thứ tự trong danh mục nhóm
            order = {g.name: i for i, g in enumerate(self.env[TASK_SOURCES[self.kind][0] + '.group'].sudo().search([]))}
        else:
            order = {label: i for i, (_k, label) in enumerate(TASK_GROUPS)}
        # theo nhóm công việc (I, II, III...) rồi theo thứ tự trong bảng công việc NVBH
        lines = self.line_ids.sorted(lambda l: (order.get(l.sub_category, len(order)), l.sequence, l.id))
        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
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
                'is_done': l.is_done, 'status': l.status, 'note': l.note or '', 'staff_edited': l.staff_edited,
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
        # chỉ nhân viên thuộc các cửa hàng user được xem (vd. ASM chỉ thấy nhân viên cửa hàng mình phụ trách)
        scope = self.env['store.audit']._user_store_scope()
        if store_id:
            if scope is not None and int(store_id) not in scope:
                return []
            domain.append(('store_id', '=', int(store_id)))
        elif scope is not None:
            domain.append(('store_id', 'in', scope))
        if month:
            y, m = [int(x) for x in month.split('-')]
            start = fields.Date.to_date('%04d-%02d-01' % (y, m))
            end = fields.Date.to_date('%04d-%02d-01' % (y + 1, 1) if m == 12 else '%04d-%02d-01' % (y, m + 1))
            domain += [('work_date', '>=', start), ('work_date', '<', end)]
        for line in Line.search(domain, order='work_date desc, id desc'):
            name = (line.staff_name or '').strip()
            if name and (name.casefold() not in out or (not out[name.casefold()]['code'] and line.employee_code)):
                out[name.casefold()] = {'name': name, 'code': line.employee_code or ''}
        sdomain = [('store_id', '=', int(store_id))] if store_id else ([('store_id', 'in', scope)] if scope is not None else [])
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
        hidden = self._hidden_kinds()
        if hidden:
            domain.append(('kind', 'not in', hidden))
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
                                        'store_id': c.store_id.id, 'mien': c.store_id.mien or '',
                                        'days': [], 'done': 0, 'total': 0, 'errors': 0, 'points': 0.0, 'max_points': 0.0,
                                        'evaluated': 0, 'asm_vals': [], 'rate_vals': []})
            max_points = sum(c.line_ids.mapped('max_score'))
            evaluated = c._fully_evaluated()  # đã đánh giá xong ở mọi cấp trong luồng
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
                'wait': '' if evaluated else c._waiting_code(),  # đang chờ ai: NV / CHT / ASM / RSM / Admin
                'edited': any(c.line_ids.mapped('staff_edited')),  # người thực hiện đã chỉnh sửa sau khi gửi, chờ chấm lại
                'rating': rating(c.points, max_points, evaluated)[0] if evaluated else '',  # cùng bảng Cài đặt > Xếp loại với xếp loại theo tháng
            })
            # như Bảng checklist Tổng: AVERAGE(Điểm ASM đánh giá) các ngày ASM chấm đủ, AVERAGE(Tỷ lệ đạt %) các ngày đã đánh giá xong
            # check list ASM: không có cấp ASM đánh giá -> lấy điểm kết quả cuối cùng (Admin duyệt)
            pts_asm = c._step_points('ASM') if c.kind != 'asm' else (c.points if evaluated else None)
            if pts_asm is not None:
                g['asm_vals'].append(pts_asm)
            if evaluated:
                g['rate_vals'].append(round(pct, 1))
            g['done'] += c.cnt_done
            g['total'] += c.cnt_total
            g['errors'] += c.error_total
            if evaluated:  # ngày chưa đánh giá không tính vào điểm / tỷ lệ (tránh bị kéo xuống 0)
                g['points'] += c.points
                g['max_points'] += max_points
            g['evaluated'] += 1 if evaluated else 0
        # 3 ngày gần nhất: ngày không có lịch làm việc (hoặc ca OFF) -> hiển thị OFF thay vì "Chưa có"
        today_d = fields.Date.context_today(self)
        recent = [today_d - timedelta(days=i) for i in (2, 1, 0)]
        sched_ok = {((c.staff_name or '').strip().casefold(), c.store_id.id, c.work_date) for c in checks}
        for ln in self.env['store.nvbh.schedule.line'].search([('work_date', 'in', recent)]):
            if (ln.shift_id.code or '').strip().upper() != 'OFF':
                sched_ok.add(((ln.staff_name or '').strip().casefold(), ln.store_id.id, ln.work_date))
        for key, g in groups.items():
            nm, sid = key.rsplit('|', 1)
            g['off_dates'] = [d.strftime('%d/%m/%Y') for d in recent if (nm, int(sid), d) not in sched_ok]
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
            asm_vals, rate_vals = g.pop('asm_vals'), g.pop('rate_vals')
            g['asm_avg'] = round(sum(asm_vals) / len(asm_vals), 2) if asm_vals else None
            g['rate_avg'] = round(sum(rate_vals) / len(rate_vals), 2) if rate_vals else None
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
        hidden = self._hidden_kinds()
        if hidden:
            sched = sched.filtered(lambda l: self._schedule_kind(l) not in hidden)
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
                if c._fully_evaluated() and mp:
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
        hidden = self._hidden_kinds()
        if hidden:
            sched = sched.filtered(lambda l: self._schedule_kind(l) not in hidden)
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
        hidden = self._hidden_kinds()
        if hidden:
            sched = sched.filtered(lambda l: self._schedule_kind(l) not in hidden)
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
            elif c._fully_evaluated():
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
        checks = self.search(base + ([('kind', 'not in', self._hidden_kinds())] if self._hidden_kinds() else []), order='work_date, id')
        sched = self.env['store.nvbh.schedule.line'].search(base)
        hidden = self._hidden_kinds()
        if hidden:
            sched = sched.filtered(lambda l: self._schedule_kind(l) not in hidden)
        by_date = {}
        for c in checks:
            by_date.setdefault(c.work_date, []).append(c)
        sched_by_date = {}
        for l in sched:
            sched_by_date.setdefault(l.work_date, l)
        rows = []
        tot = {'total': 0, 'done': 0, 'todo': 0, 'errors': 0, 'points': 0.0, 'max_points': 0.0, 'days': 0, 'valid': 0,
               'pts_cht': 0.0, 'pts_asm': 0.0, 'hours': 0.0, 'err_cht': 0, 'err_asm': 0}
        avg_src = {'points': [], 'cht': [], 'asm': [], 'pct': []}  # dòng cuối bảng dùng AVERAGE: chỉ tính các ngày có số liệu
        day_set = set()
        store_name = (sched[:1].store_id.display_name or checks[:1].store_id.display_name or '')
        for i in range(days_in_month):
            day = start + timedelta(days=i)
            base_row = {'date': day.strftime('%d/%m/%Y'), 'weekday': weekdays[day.weekday()], 'pts_cht': None, 'pts_asm': None,
                        'err_cht': None, 'err_asm': None, 'txt_cht': None, 'txt_asm': None}
            items = by_date.get(day)
            if not items:
                line = sched_by_date.get(day)
                if line:
                    hrs = 0.0  # chưa check list: chưa tính giờ (Tổng giờ chỉ tính ngày nhân viên đã check list)
                    rows.append(dict(base_row, kind='pending', code='-', store=line.store_id.display_name or '',
                                     shift=line.shift_id.code or '-', hours=hrs,
                                     status='Chưa check list', total=0, done=0, todo=0, errors=0, points=0, max_points=0, pct=0,
                                     control='Chưa đánh giá', note=''))
                    store_name = store_name or (line.store_id.display_name or '')
                else:
                    rows.append(dict(base_row, kind='off', code='-', store=store_name, shift='OFF', hours=0.0, status='Nghỉ theo lịch', total=0, done=0,
                                     todo=0, errors=0, points=0, max_points=0, pct=0, control='-',
                                     note=''))
                continue
            for c in items:
                lines = c.line_ids
                mp = sum(lines.mapped('max_score'))
                evaluated = c._fully_evaluated()  # đã đánh giá xong ở mọi cấp trong luồng
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
                untouched = c.state == 'draft' and not c.cnt_done  # có phiếu nhưng nhân viên chưa tích việc nào
                late = c._late_code()  # quá hạn: NVBH -> không ghi nhận; CHT / ASM -> ghi nhận trễ hạn
                if late == 'NVBH':
                    control = 'Quá hạn - không ghi nhận'
                elif late:
                    control = '%s trễ hạn' % late
                elif evaluated:
                    control = 'Đã đánh giá'
                elif untouched:
                    control = 'Chưa đánh giá'
                else:
                    control = 'Chờ đánh giá'
                store_name = store_name or (c.store_id.display_name or '')
                pts_cht, pts_asm = c._step_points('CHT'), c._step_points('ASM')
                err_cht, err_asm = c._step_errors('CHT'), c._step_errors('ASM')
                txt_cht, txt_asm = c._step_error_text('CHT'), c._step_error_text('ASM')
                rows.append(dict(
                    base_row, pts_cht=pts_cht, pts_asm=pts_asm, err_cht=err_cht, err_asm=err_asm, txt_cht=txt_cht, txt_asm=txt_asm, kind='error' if (c.error_total or not done_all or (evaluated and c.points < mp)) else 'ok',
                    evaluated=evaluated, id=c.id, code=c.name or '-',
                    store=c.store_id.display_name or '',
                    shift=c.shift_id.code or '-', hours=c.shift_id.hours or 0.0,
                    status='Hoàn thành' if done_all else ('Chưa check list' if untouched else 'Chưa hoàn thành'), total=c.cnt_total, done=c.cnt_done, todo=c.cnt_todo,
                    errors=c.error_total, points=c.points, max_points=mp, pct=pct, control=control, note=note))
                tot['hours'] += c.shift_id.hours or 0.0
                tot['total'] += c.cnt_total
                tot['done'] += c.cnt_done
                tot['todo'] += c.cnt_todo
                tot['errors'] += c.error_total
                tot['pts_cht'] += pts_cht or 0.0
                tot['pts_asm'] += pts_asm or 0.0
                tot['err_cht'] += err_cht or 0
                tot['err_asm'] += err_asm or 0
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
                if c.cnt_done > 0:
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
    def get_cht_month(self, month=None, store_id=None, staff_key=None):
        """Trang Checklist CV CHT (dạng Bảng Checklist Tổng): danh sách CHT có lịch trong tháng (theo quyền xem lịch xếp ca),
        người đang chọn và bảng từng ngày của người đó (get_done_monthly), mỗi ngày kèm dòng lịch để mở check list ngày."""
        start, end, _n = self._month_range(month)
        empty = {'options': [], 'key': '', 'staff': False, 'month': start.strftime('%Y-%m'), 'data': False}
        options, key, mine = self._cht_staff_pick(start, end, store_id, staff_key)
        if not options:
            return empty
        last = mine[-1:]
        data = self.get_done_monthly(start.strftime('%Y-%m'), last.staff_name, store_id or False)
        by_day = {l.work_date.strftime('%d/%m/%Y'): l for l in mine}
        for r in data.get('rows') or []:
            l = by_day.get(r['date'])
            r['line_id'] = l.id if l else False
            r['store_id'] = l.store_id.id if l else False
            r['store_code'] = (l.store_id.code if l else '') or r.get('store') or ''
            r['ymd'] = '%s-%s-%s' % tuple(reversed(r['date'].split('/')))
            r['week_comment'] = (self.browse(r['id']).week_comment or '') if r.get('id') else ''
        return {
            'options': options, 'key': key, 'month': start.strftime('%Y-%m'), 'data': data,
            'staff': self._cht_staff_info(last),
        }

    @api.model
    def _cht_staff_info(self, line):
        return {'name': line.staff_name or '', 'code': line.employee_code or '', 'status': line.work_status or '',
                'position': line.position or 'CHT', 'store': line.store_id.code or line.store_id.display_name or ''}

    @api.model
    def _cht_staff_pick(self, start, end, store_id=None, staff_key=None):
        """CHT có lịch xếp ca trong [start, end) theo quyền xem lịch: (danh sách lựa chọn, khóa đang chọn, dòng lịch của người đó).
        Người đăng nhập là CHT trên lịch thì chỉ thấy chính mình."""
        Line = self.env['store.nvbh.schedule.line']
        lines = self._cht_lines(start, end, store_id)
        groups = {}
        for l in lines:
            groups.setdefault(self._cht_line_key(l), Line)
            groups[self._cht_line_key(l)] |= l
        options = sorted(({'key': k, 'name': ls[-1:].staff_name or '', 'code': ls[-1:].employee_code or '',
                           'store': ls[-1:].store_id.code or ls[-1:].store_id.display_name or ''}
                          for k, ls in groups.items()), key=lambda o: o['name'].casefold())
        if not options:
            return [], '', Line
        key = staff_key if staff_key in groups else options[0]['key']
        return options, key, groups[key]

    @api.model
    def _cht_lines(self, start, end, store_id=None):
        """Dòng lịch xếp ca chức vụ CHT trong [start, end) theo quyền xem lịch, lọc cửa hàng / miền (context cht_mien);
        người đăng nhập là CHT trên lịch thì chỉ dòng của chính mình."""
        Line = self.env['store.nvbh.schedule.line']
        if 'cht' in self._hidden_kinds():
            return Line
        dom = [('work_date', '>=', start), ('work_date', '<', end)]
        if store_id:
            dom.append(('store_id', '=', int(store_id)))
        # lọc theo miền (ô Miền trên trang CHT, truyền qua context): Nam / ĐTT / Bắc / other = cửa hàng chưa gắn miền
        mien = self.env.context.get('cht_mien')
        if mien == 'other':
            dom.append(('store_id.mien', 'not in', ['Nam', 'ĐTT', 'Bắc']))
        elif mien:
            dom.append(('store_id.mien', '=', mien))
        lines = self.env['store.nvbh.schedule.line'].search(dom, order='work_date, id')
        lines = lines.filtered(lambda l: self._schedule_kind(l) == 'cht')

        def key_of(l):
            return (l.employee_code or '').strip() or (l.staff_name or '').strip().casefold()

        # người đăng nhập là CHT trên lịch: chỉ thấy chính mình
        emp = self.env.user.employee_id
        if emp:
            codes = {str(emp[f]).strip() for f in ('barcode', 'ma_cham_cong', 'ma_nv_ke_toan') if f in emp._fields and emp[f]}
            name = (emp.name or '').strip().casefold()
            mine = lines.filtered(lambda l: (l.employee_code or '').strip() in codes
                                  or (l.staff_name or '').strip().casefold() == name)
            if mine:
                lines = mine
        return lines

    @api.model
    def get_cht_overview(self, month=None, week=None):
        """Danh sách tổng Đánh giá Checklist CHT (người xem nhiều CHT, vd. Quản trị / Admin): Miền > Cửa hàng > CHT,
        mỗi CHT kèm tình hình tuần (việc ca, đã làm, lỗi, điểm đã đánh giá, số phiếu chờ ASM / chưa gửi / đã đánh giá)."""
        start, end, _n = self._month_range(month)
        weeks = self._month_weeks(start, end)
        today = fields.Date.context_today(self)
        if week is None or week == '' or week is False:
            week = next((i for i, (a, b) in enumerate(weeks) if a <= today <= b), 0)
        week = max(0, min(int(week), len(weeks) - 1))
        a, b = weeks[week]
        month_lines = self._cht_lines(start, end)
        week_lines = month_lines.filtered(lambda l: a <= l.work_date <= b)
        checks = self.search([('schedule_line_id', 'in', week_lines.ids), ('kind', '=', 'cht')])
        by_line = {c.schedule_line_id.id: c for c in checks}
        labels = {'Nam': 'Miền Nam', 'ĐTT': 'Miền ĐTT', 'Bắc': 'Miền Bắc'}
        staff = {}
        for l in month_lines:
            k = self._cht_line_key(l)
            st = staff.setdefault(k, {'key': k, 'name': l.staff_name or '', 'code': l.employee_code or '', 'store': l.store_id,
                                      'checks': self.browse(), 'days': 0})
            st['store'] = l.store_id  # cửa hàng của dòng lịch gần nhất trong tháng
            if a <= l.work_date <= b:
                st['days'] += 1
                if l.id in by_line:
                    st['checks'] |= by_line[l.id]
        miens = {}
        for st in staff.values():
            cs = st['checks']
            approved = cs.filtered(lambda c: c._fully_evaluated())
            row = {
                'key': st['key'], 'name': st['name'], 'code': st['code'], 'days': st['days'], 'n_checks': len(cs),
                'tasks': sum(cs.mapped('cnt_total')), 'done': sum(cs.mapped('cnt_done')), 'errors': sum(cs.mapped('error_total')),
                'points': round(sum(approved.mapped('points')), 2),
                'max_points': sum(sum(c.line_ids.mapped('max_score')) for c in approved),
                'pending': len(cs.filtered(lambda c: c.state == 'pending_review')),
                'not_sent': len(cs.filtered(lambda c: c.state == 'draft')), 'evaluated': len(approved),
            }
            store = st['store']
            mk = store.mien if store.mien in labels else 'other'
            m = miens.setdefault(mk, {'key': mk, 'label': labels.get(mk, 'Khác (chưa gắn miền)'), 'stores': {}})
            sg = m['stores'].setdefault(store.id, {'id': store.id, 'code': store.code or '', 'name': store.name or '', 'staff': []})
            sg['staff'].append(row)

        def sums(rows):
            return {f: sum(r[f] for r in rows) for f in ('pending', 'not_sent', 'evaluated', 'n_checks', 'errors')}

        out = []
        for mk in ('Nam', 'ĐTT', 'Bắc', 'other'):
            m = miens.get(mk)
            if not m:
                continue
            stores = []
            for sg in sorted(m['stores'].values(), key=lambda x: (x['code'] or x['name']).casefold()):
                sg['staff'].sort(key=lambda r: r['name'].casefold())
                stores.append(dict(sg, n_cht=len(sg['staff']), **sums(sg['staff'])))
            rows = [r for sg in stores for r in sg['staff']]
            out.append({'key': mk, 'label': m['label'], 'stores': stores, 'n_stores': len(stores), 'n_cht': len(rows), **sums(rows)})
        all_rows = [r for m in out for sg in m['stores'] for r in sg['staff']]
        return {
            'month': start.strftime('%Y-%m'), 'week': week,
            'weeks': [{'idx': i, 'label': 'Tuần %s' % (i + 1), 'range': '%s – %s' % (x.strftime('%d'), y.strftime('%d/%m')),
                       'full': '%s – %s' % (x.strftime('%d'), y.strftime('%d/%m/%Y'))} for i, (x, y) in enumerate(weeks)],
            'miens': out, 'n_cht': len(all_rows), 'totals': sums(all_rows),
        }

    # ------------------------------------------------------------------
    # Đánh giá Checklist Cửa hàng trưởng theo tuần (ASM chấm theo nhóm công việc)
    # ------------------------------------------------------------------
    @api.model
    def _month_weeks(self, start, end):
        """Các tuần (thứ Hai - Chủ nhật) trong tháng; tuần lẻ đầu / cuối tháng dưới 4 ngày gộp vào tuần liền kề."""
        weeks, day = [], start
        while day < end:
            stop = min(day + timedelta(days=6 - day.weekday()), end - timedelta(days=1))
            weeks.append([day, stop])
            day = stop + timedelta(days=1)
        if len(weeks) > 1 and (weeks[0][1] - weeks[0][0]).days < 3:
            weeks[1][0] = weeks[0][0]
            weeks.pop(0)
        if len(weeks) > 1 and (weeks[-1][1] - weeks[-1][0]).days < 3:
            weeks[-2][1] = weeks[-1][1]
            weeks.pop()
        return weeks

    @staticmethod
    def _slot_hours(text):
        """Số giờ của khung giờ dạng "15h-16h", "8h-10h", "12h-12h30"; không đọc được (Phát sinh...) = 0."""
        import re
        m = re.search(r'(\d{1,2})\s*h\s*(\d{1,2})?\s*[-–]\s*(\d{1,2})\s*h?\s*(\d{1,2})?', text or '')
        if not m:
            return 0.0
        a = int(m.group(1)) + int(m.group(2) or 0) / 60.0
        b = int(m.group(3)) + int(m.group(4) or 0) / 60.0
        return round(b - a, 2) if b > a else 0.0

    @api.model
    def _cht_week_checks(self, month, week, store_id, staff_key):
        start, end, _n = self._month_range(month)
        weeks = self._month_weeks(start, end)
        today = fields.Date.context_today(self)
        if week is None or week == '' or week is False:
            week = next((i for i, (a, b) in enumerate(weeks) if a <= today <= b), 0)
        week = max(0, min(int(week), len(weeks) - 1))
        options, key, mine = self._cht_staff_pick(start, end, store_id, staff_key)
        a, b = weeks[week]
        lines = mine.filtered(lambda l: a <= l.work_date <= b)
        checks = self.search([('schedule_line_id', 'in', lines.ids), ('kind', '=', 'cht')], order='work_date, id')
        return start, weeks, week, options, key, mine, lines, checks

    @staticmethod
    def _cht_line_key(line):
        return (line.employee_code or '').strip() or (line.staff_name or '').strip().casefold()

    def _cht_my_step(self):
        """Bước người đăng nhập được chấm trên phiếu: bước đang đến lượt (phiếu chờ đánh giá), hoặc bước mình vừa chấm xong
        còn trong hạn sửa lại (đến 23h55 ngày chấm, sau giờ đó hệ thống tự khóa); không có thì None."""
        self.ensure_one()
        if self.state not in ('pending_review', 'approved'):
            return None
        info = self._role_info()
        if self.state == 'pending_review':
            st = next((st for st in info['chain'] if st['current'] and st['can_edit']), None)
            if st:
                return st
        return next((st for st in info['chain'] if st.get('reedit') and st['can_edit']), None)

    @api.model
    def _cht_visit_scope(self, month, week, store_id, staff_key, visit_date=None):
        """Phạm vi một lần ASM ghé thăm (quy trình đánh giá CHT theo tuần):
        - tuần N = tuần đang xem [a, b]; ngày ghé thăm X (mặc định hôm nay, không quá hôm nay, không trước đầu tuần);
        - chấm lần này: phiếu đã gửi của tuần N có ngày làm việc <= X + phiếu chuyển tiếp (tuần trước, đã gửi, chưa chấm);
        - phiếu tuần N sau ngày X: chuyển sang hàng chờ của tuần N+1 (lần ghé sau chấm gộp)."""
        start, weeks, week, options, key, mine, lines, checks = self._cht_week_checks(month, week, store_id, staff_key)
        a, b = weeks[week]
        today = fields.Date.context_today(self)
        visit = fields.Date.to_date(visit_date) if visit_date else None
        if not visit:
            visit = min(max(today, a), b) if today >= a else a
        visit = min(max(visit, a), today) if today >= a else a
        carried = self.browse()
        if key:
            carried = self.search([('kind', '=', 'cht'), ('state', '=', 'pending_review'), ('work_date', '<', a),
                                   ('work_date', '>=', a - timedelta(days=42))], order='work_date, id')
            carried = carried.filtered(lambda c: c.schedule_line_id and self._cht_line_key(c.schedule_line_id) == key)
        in_scope = checks.filtered(lambda c: c.work_date <= visit) | carried
        evaluable = in_scope.filtered(lambda c: c._cht_my_step())
        later = checks.filtered(lambda c: c.work_date > visit and c.state != 'approved')
        return {'start': start, 'weeks': weeks, 'week': week, 'a': a, 'b': b, 'options': options, 'key': key, 'mine': mine,
                'lines': lines, 'checks': checks, 'visit': visit, 'carried': carried, 'evaluable': evaluable, 'later': later}

    @api.model
    def get_cht_week(self, month=None, week=None, store_id=None, staff_key=None, visit_date=None):
        """Trang Đánh giá Checklist CHT theo tuần: KPI tuần (khớp Bảng checklist Tổng), bảng theo nhóm công việc, phạm vi lần ghé thăm
        của ASM (phiếu chấm lần này / chuyển tiếp từ tuần trước / chờ lần ghé sau) và nhận xét của các lần ghé."""
        sc = self._cht_visit_scope(month, week, store_id, staff_key, visit_date)
        checks, mine, evaluable, carried = sc['checks'], sc['mine'], sc['evaluable'], sc['carried']
        res = {
            'month': sc['start'].strftime('%Y-%m'), 'week': sc['week'], 'options': sc['options'], 'key': sc['key'],
            'weeks': [{'idx': i, 'label': 'Tuần %s' % (i + 1), 'range': '%s – %s' % (a.strftime('%d'), b.strftime('%d/%m')),
                       'full': '%s – %s' % (a.strftime('%d'), b.strftime('%d/%m/%Y'))} for i, (a, b) in enumerate(sc['weeks'])],
            'staff': self._cht_staff_info(mine[-1:]) if mine else False,
            'visit_date': str(sc['visit']), 'week_start': str(sc['a']), 'today_ymd': str(fields.Date.context_today(self)),
            'groups': [], 'kpi': {}, 'checks': [], 'carried': [], 'visits': [], 'can_eval': False, 'today': False,
            'comment': '', 'can_comment': False, 'n_scope': 0, 'n_later': 0, 'n_pending': 0, 'n_reedit': 0, 'reedit_until': '', 'locked_at': '',
        }
        if not mine:
            return res
        grp_seq = {g.name: (g.sequence, g.id) for g in self.env['store.cht.task.group'].sudo().with_context(active_test=False).search([])}
        groups = {}

        def new_group(name):
            return {'name': name, 'tasks': {}, 'lines': 0, 'done': 0, 'hours': 0.0, 'max_total': 0.0, 'max_done': 0.0,
                    'results': set(), 'errors': 0, 'max_eval': 0.0, 'max_done_eval': 0.0}

        def row_of(c, scope):
            st = c._cht_my_step()
            if c.state == 'approved':
                state = ('Đã đánh giá · sửa được đến %s' % fields.Datetime.context_timestamp(self, st['reedit_until']).strftime('%H:%M')
                         if st and st.get('reedit_until') else 'Đã đánh giá')
            elif c.state == 'pending_review':
                state = {'in': 'Chấm lần này' if st else 'Chờ đánh giá', 'later': 'Chờ lần ghé sau',
                         'carried': 'Chuyển tiếp'}.get(scope, 'Chờ đánh giá')
            else:
                state = 'Chưa gửi (%s/%s việc)' % (c.cnt_done, c.cnt_total)
            dl = c._step_deadline(c.step_done + 1) if c.state == 'pending_review' else False
            return {'id': c.id, 'date': c.work_date.strftime('%d/%m'), 'state': state, 'points': c.points, 'scope': scope,
                    'max_points': sum(c.line_ids.mapped('max_score')), 'can_eval': c in evaluable, 'reedit': bool(st and st.get('reedit')),
                    'deadline': dl.strftime('%d/%m') if dl else '',
                    'line_id': c.schedule_line_id.id, 'store_id': c.store_id.id, 'ymd': str(c.work_date)}

        # thống kê nhóm: chỉ phiếu của tuần (khớp Bảng checklist Tổng); phiếu chuyển tiếp chỉ góp vào phần chấm / tạm tính
        for c in checks | carried:
            own = c in checks
            info = c._role_info()
            pre = STEP_PREFIX[min(max(info['cur'], c.step_done, 1), len(STEP_PREFIX)) - 1]
            per_line = (c.shift_id.hours or 0.0) / len(c.line_ids) if c.line_ids else 0.0
            for l in c.line_ids:
                g = groups.setdefault(l.sub_category or 'Khác', new_group(l.sub_category or 'Khác'))
                if own:
                    tk = l.cht_task_id.id or ('n', l.name)
                    t = g['tasks'].setdefault(tk, {'name': l.name, 'time_slot': l.time_slot or '', 'score': l.max_score, 'days': [], 'all_done': True})
                    t['days'].append({'date': c.work_date.strftime('%d/%m'), 'done': l.is_done,
                                      'result': l[pre + 'eval_result'] or '', 'error': bool(l.error_count)})
                    t['all_done'] = t['all_done'] and l.is_done and not l.error_count
                    g['lines'] += 1
                    g['done'] += 1 if l.is_done else 0
                    g['hours'] += per_line
                    g['max_total'] += l.max_score or 0.0
                    g['max_done'] += (l.max_score or 0.0) if l.is_done else 0.0
                    g['errors'] += l.error_count or 0
                if c in evaluable:
                    g['max_eval'] += l.max_score or 0.0
                    g['max_done_eval'] += (l.max_score or 0.0) if l.is_done else 0.0
                    g['results'].add(l[pre + 'eval_result'] or '')
                elif own and c.state == 'approved' and not evaluable:
                    g['results'].add(l[pre + 'eval_result'] or '')
        out = []
        for g in sorted(groups.values(), key=lambda g: grp_seq.get(g['name'], (9999, 0)) + (g['name'],)):
            tasks = list(g['tasks'].values())
            res_set = g['results'] - {''}
            out.append({
                'name': g['name'], 'desc': ', '.join(t['name'] for t in tasks[:3]), 'n_tasks': len(tasks),
                'tasks_done': sum(1 for t in tasks if t['all_done']), 'lines': g['lines'], 'done': g['done'],
                'rate': round(100.0 * g['done'] / g['lines'], 1) if g['lines'] else 0.0, 'hours': round(g['hours'], 1),
                'max_total': g['max_total'], 'max_done': g['max_done'], 'errors': g['errors'],
                'max_eval': g['max_eval'], 'max_done_eval': g['max_done_eval'],
                'result': res_set.pop() if len(res_set) == 1 and '' not in g['results'] else '',
                'task_rows': tasks, 'carried_only': not g['lines'],
            })
        res['groups'] = out
        approved = checks.filtered(lambda c: c._fully_evaluated())
        res['kpi'] = {
            'tasks': sum(checks.mapped('cnt_total')), 'hours': round(sum(c.shift_id.hours or 0.0 for c in checks), 2),
            'done': sum(checks.mapped('cnt_done')), 'errors': sum(checks.mapped('error_total')),
            'points': round(sum(approved.mapped('points')), 2),
            'max_points': sum(sum(c.line_ids.mapped('max_score')) for c in approved),
            'n_checks': len(checks), 'n_eval': len(evaluable), 'n_lines': len(sc['lines']),
        }
        res['checks'] = [row_of(c, 'later' if c in sc['later'] else 'in') for c in checks]
        res['carried'] = [dict(row_of(c, 'carried'), week_label=self._cht_week_label(c.work_date)) for c in carried]
        res['can_eval'] = bool(evaluable)
        res['n_scope'] = len(evaluable)
        # sửa lại đánh giá: phiếu mình đã chấm còn trong hạn (đến 23h55 ngày chấm) -> nút Chỉnh sửa; hết hạn -> báo đã khóa
        reedit = evaluable.filtered(lambda c: c.state == 'approved')
        res['n_pending'] = len(evaluable - reedit)
        res['n_reedit'] = len(reedit)
        until = [u for u in (c._reedit_until(c.step_done) for c in reedit) if u]
        res['reedit_until'] = fields.Datetime.context_timestamp(self, min(until)).strftime('%H:%M %d/%m') if until else ''
        locked = []
        for c in checks.filtered(lambda c: c.state == 'approved') - reedit:
            log = c.step_log_ids.filtered(lambda l: l.step_no == c.step_done and l.user_id == self.env.user)
            u = c._reedit_until(c.step_done) if log else False
            if u:
                locked.append(u)
        res['locked_at'] = fields.Datetime.context_timestamp(self, max(locked)).strftime('%H:%M %d/%m') if locked else ''
        res['n_later'] = len(sc['later'].filtered(lambda c: c.state == 'pending_review'))
        res['can_comment'] = self._cht_week_can_comment(checks | carried)
        # nhận xét theo từng lần ghé thăm (của tuần này hoặc có chấm phiếu của tuần này)
        Visit = self.env['store.cht.visit'].sudo()
        visits = Visit.search([('staff_key', '=', sc['key']), '|', '&', ('visit_date', '>=', sc['a']), ('visit_date', '<=', sc['b']),
                               ('check_ids', 'in', checks.ids)], order='visit_date, id')
        res['visits'] = [{'id': v.id, 'date': v.visit_date.strftime('%d/%m/%Y'), 'user': v.user_id.name or '', 'comment': v.comment or '',
                          'days': ', '.join(d.strftime('%d/%m') for d in sorted(set(v.check_ids.mapped('work_date')))),
                          'mine': v.user_id == self.env.user} for v in visits]
        cur = visits.filtered(lambda v: v.visit_date == sc['visit'] and v.user_id == self.env.user)[-1:]
        res['comment'] = cur.comment or ''
        today = fields.Date.context_today(self)
        tl = mine.filtered(lambda l: l.work_date == today)[:1]
        res['today'] = {'line_id': tl.id, 'store_id': tl.store_id.id, 'ymd': str(today)} if tl else False
        return res

    @api.model
    def _cht_week_label(self, day):
        start, end, _n = self._month_range(day.strftime('%Y-%m'))
        for i, (a, b) in enumerate(self._month_weeks(start, end)):
            if a <= day <= b:
                return 'Tuần %s (%s – %s)' % (i + 1, a.strftime('%d'), b.strftime('%d/%m'))
        return ''

    @api.model
    def _cht_week_can_comment(self, checks):
        """Người được viết nhận xét: người đánh giá trong luồng của các phiếu (ASM phụ trách, Admin chức vụ nếu có bước đó)
        hoặc Quản trị viên; không phụ thuộc phiếu đã duyệt hay chưa."""
        user = self.env.user
        if user.has_group('base.group_system'):
            return bool(checks)
        for c in checks:
            for st in c._approval_chain():
                if st.get('user') and st['user'].id == user.id:
                    return True
                if st.get('admin_title') and user in st.get('users', self.env['res.users']):
                    return True
        return False

    @api.model
    def _cht_save_visit(self, sc, comment, evaluated):
        """Ghi / cập nhật lần ghé thăm (người đăng nhập + ngày ghé + CHT): nhận xét và các phiếu đã chấm trong lần ghé đó."""
        text = '\n'.join(ln.rstrip() for ln in (comment or '').strip().splitlines()) or False
        Visit = self.env['store.cht.visit'].sudo()
        v = Visit.search([('staff_key', '=', sc['key']), ('visit_date', '=', sc['visit']), ('user_id', '=', self.env.user.id)],
                         order='id desc', limit=1)
        vals = {'comment': text}
        if evaluated:
            vals['check_ids'] = [(4, c.id) for c in evaluated]
        if v:
            v.write(vals)
        else:
            staff = sc['mine'][-1:]
            v = Visit.create(dict(vals, staff_key=sc['key'], staff_name=staff.staff_name or '', store_id=staff.store_id.id or False,
                                  visit_date=sc['visit'], user_id=self.env.user.id))
        # nhận xét hiện ở chi tiết từng ngày của Bảng checklist tháng
        if text and v.check_ids:
            v.check_ids.sudo().write({'week_comment': text})
        return v

    @api.model
    def save_cht_week_comment(self, month, week, store_id, staff_key, comment, visit_date=None):
        """Lưu nhận xét của lần ghé thăm (không có phiếu cần chấm)."""
        sc = self._cht_visit_scope(month, week, store_id, staff_key, visit_date)
        if not sc['checks'] and not sc['carried']:
            raise UserError(_('Tuần này chưa có phiếu check list nào để lưu nhận xét.'))
        if not self._cht_week_can_comment(sc['checks'] | sc['carried']):
            raise AccessError(_('Chỉ người đánh giá (ASM phụ trách) mới được nhận xét tuần này.'))
        self._cht_save_visit(sc, comment, self.browse())
        return True

    @api.model
    def save_cht_week(self, month, week, store_id, staff_key, results, comment=None, visit_date=None):
        """Lưu lần ASM ghé thăm: áp KQ đánh giá theo nhóm (results = {tên nhóm: good / avg / bad}) cho các phiếu trong phạm vi
        (phiếu đã gửi của tuần đến ngày ghé thăm + phiếu chuyển tiếp từ tuần trước) đang đến lượt người đăng nhập chấm.
        Điểm tự tính về đúng ngày / tuần / tháng gốc của từng phiếu. Việc CHT chưa làm tính Không đạt; dòng có ghi lỗi giữ lỗi."""
        valid = {k for k, _l in EVAL_RESULTS}
        results = {k: v for k, v in (results or {}).items() if v in valid}
        sc = self._cht_visit_scope(month, week, store_id, staff_key, visit_date)
        evaluated = self.browse()
        for c in sc['evaluable']:
            step = c._cht_my_step()
            if not step:
                continue
            missing = {l.sub_category or 'Khác' for l in c.line_ids} - set(results)
            if missing:
                raise UserError(_('Chưa chọn KQ đánh giá cho nhóm: %s') % ', '.join(sorted(missing)))
            pre = STEP_PREFIX[step['no'] - 1]
            changes = [{'id': l.id, 'result': results[l.sub_category or 'Khác'], 'detail': l[pre + 'error_detail'] or ''}
                       for l in c.line_ids]
            self.save_step_evaluation(c.id, step['no'], changes)
            evaluated |= c
        if not evaluated:
            raise UserError(_('Không có phiếu nào đến ngày ghé thăm đang chờ bạn đánh giá.'))
        self._cht_save_visit(sc, comment, evaluated)
        return {'done': len(evaluated), 'dates': [c.work_date.strftime('%d/%m') for c in evaluated]}

    # ------------------------------------------------------------------
    # Nhắc quá hạn: phiếu CHT ASM chưa đánh giá đến hết tuần N+1 -> hệ thống khóa (ASM trễ hạn), báo cấp trên của ASM và Admin
    # ------------------------------------------------------------------
    @api.model
    def _cron_notify_cht_asm_late(self):
        from .store_notify import bot_send, card
        today = fields.Date.context_today(self)
        checks = self.sudo().search([('kind', '=', 'cht'), ('state', '=', 'pending_review'),
                                     ('work_date', '>=', today - timedelta(days=45))])
        admins = self._admin_title_employees().mapped('user_id')
        for c in checks:
            no = c.step_done + 1
            dl = c._step_deadline(no)
            if not dl or dl != today - timedelta(days=1):
                continue  # chỉ báo một lần, ngày ngay sau khi hết hạn
            chain = c._approval_chain()
            step = chain[no - 1] if no <= len(chain) else {}
            boss = step.get('employee') and step['employee'].parent_id.user_id or self.env['res.users']
            to = (boss | admins) - (step.get('user') or self.env['res.users'])
            if not to:
                continue
            bot_send(self.env, to, card('CHECKLIST CHT QUÁ HẠN %s ĐÁNH GIÁ' % (step.get('code') or 'ASM'), [
                ('Cửa hàng trưởng', c.staff_name or ''),
                ('Cửa hàng', c.store_id.display_name),
                ('Ngày', c.work_date.strftime('%d/%m/%Y')),
                ('Người đánh giá', step.get('employee') and step['employee'].name or ''),
                ('Hạn đánh giá', dl.strftime('%d/%m/%Y')),
            ], label='Mở phiếu', check_id=c.id))

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
        f_num = book.add_format({'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '#,##0;-#,##0;"-"'})
        f_num_dec = book.add_format({'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '#,##0.0#;-#,##0.0#;"-"'})
        f_foot = book.add_format({'bold': True, 'border': 1, 'bg_color': '#DBE7F5', 'valign': 'vcenter', 'text_wrap': True})
        f_foot_num = book.add_format({'bold': True, 'border': 1, 'bg_color': '#DBE7F5', 'align': 'center', 'num_format': '#,##0;-#,##0;"-"'})
        f_foot_dec = book.add_format({'bold': True, 'border': 1, 'bg_color': '#DBE7F5', 'align': 'center', 'num_format': '#,##0.0#;-#,##0.0#;"-"'})
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
                    # số nguyên: không hiện dấu thập phân thừa ("8," -> "8"); số 0 hiện "-"
                    if v != int(v):
                        num_fmt = f_foot_dec if num_fmt is f_foot_num else f_num_dec
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

    @api.model
    def export_sheets_xlsx(self, sheets, filename='Bang_checklist'):
        """Xuất nhiều sheet (mỗi sheet gồm name, title, subtitle, headers, rows, foot) ra một file Excel."""
        self.env['store.perm.rule'].check_export()
        return self._xlsx_book(sheets, filename)

    _MONTHLY_HEADERS = ['Ngày', 'Cửa hàng', 'Mã ca', 'Trạng thái ngày', 'Tổng việc ca', 'Đã làm', 'Số lỗi', 'Tổng giờ', 'Điểm đạt', 'Điểm chuẩn ca',
                        'Điểm CHT đánh giá', 'Điểm ASM đánh giá', 'Lỗi CHT đánh giá', 'Lỗi ASM đánh giá', 'Tỷ lệ đạt (%)', 'Kết quả',
                        'Ghi chú / Tóm tắt công việc']

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
                     r.get('hours') or 0, r['points'] if (r['kind'] == 'off' or r.get('evaluated')) else '-', r['max_points'],
                     '-' if r.get('pts_cht') is None else r['pts_cht'], '-' if r.get('pts_asm') is None else r['pts_asm'],
                     r.get('txt_cht') or '-', r.get('txt_asm') or '-',
                     ('%s%%' % ('%g' % r['pct']).replace('.', ',')) if (r['kind'] == 'off' or r.get('evaluated')) else '-', r['control'], r['note'] or '-']
                    for r in data['rows'] if not (only_work and r['kind'] == 'off')]
            foot = ['TỔNG CỘNG KỲ %s (%s ngày công thực tế)' % (label, tot.get('days', 0)), '', '', '', tot.get('total', 0), tot.get('done', 0),
                    tot.get('errors', 0), tot.get('hours', 0), tot.get('avg_points') if tot.get('avg_points') is not None else '-', tot.get('max_points', 0),
                    tot.get('avg_cht') if tot.get('avg_cht') is not None else '-', tot.get('avg_asm') if tot.get('avg_asm') is not None else '-',
                    '%s lỗi' % tot.get('err_cht', 0), '%s lỗi' % tot.get('err_asm', 0),
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
        check._assert_cht_visible()
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
        line.check_id._stamp_staff_done()  # mốc tính hạn đánh giá của CHT
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
        check._stamp_staff_done()  # mốc tính hạn đánh giá của CHT
        return check._checklist_payload()


    def init(self):
        cr = self.env.cr
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'store_nvbh_check' AND column_name = 'submitted'")
        has_col = cr.fetchone()
        # bảng dòng có thể chưa được tạo (nâng cấp từ bản cũ) -> bỏ qua, lần nâng cấp sau sẽ chạy
        cr.execute("SELECT to_regclass('store_nvbh_check_line')")
        has_line = cr.fetchone()[0]
        if has_col and has_line:
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
    cht_task_id = fields.Many2one('store.cht.task', string='Công việc CHT', ondelete='set null', index=True)
    asm_task_id = fields.Many2one('store.asm.task', string='Công việc ASM', ondelete='set null', index=True)
    # người thực hiện sửa dòng này sau khi đã gửi cấp trên -> tô cam, chờ cấp đánh giá đầu tiên chấm lại
    staff_edited = fields.Boolean(string='Đã chỉnh sửa sau khi gửi', copy=False)
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


class StoreChtVisit(models.Model):
    """Một lần ASM ghé thăm cửa hàng để đánh giá check list CHT: ngày ghé, người chấm, nhận xét, các phiếu đã chấm."""
    _name = 'store.cht.visit'
    _description = 'Lần ASM ghé thăm đánh giá CHT'
    _order = 'visit_date desc, id desc'

    staff_key = fields.Char(string='Khóa CHT (ID / họ tên)', index=True, required=True)
    staff_name = fields.Char(string='Cửa hàng trưởng')
    store_id = fields.Many2one('hr.store', string='Cửa hàng', ondelete='set null')
    visit_date = fields.Date(string='Ngày ghé thăm', required=True, index=True)
    user_id = fields.Many2one('res.users', string='Người đánh giá', required=True, default=lambda self: self.env.user, ondelete='cascade')
    comment = fields.Text(string='Nhận xét')
    check_ids = fields.Many2many('store.nvbh.check', 'store_cht_visit_check_rel', 'visit_id', 'check_id', string='Phiếu đã chấm')
