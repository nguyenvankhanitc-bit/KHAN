import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_audit_staff import CHECK_MENUS
from .store_notify import bot_send, card
from .store_nvbh_check import EVAL_RESULTS, STEP_PREFIX, count_errors, eval_score

# Bảng quy đổi Mã chức vụ -> Cấp bậc (1 -> 6). Cùng cấp = đồng cấp, không kiểm tra lẫn nhau.
ROLE_LEVEL_MAP = {
    # Cấp 1: nhân viên cửa hàng
    'NVBH': 1, 'NV': 1, 'NT': 1, 'NTTT': 1, 'PT': 1,
    # Cấp 2: cửa hàng trưởng (ASMTT = ASM trung tâm thương mại, thấp hơn ASM nên cùng cấp CHT)
    'CHTTT': 2, 'CHT': 2, 'ASMTT': 2,
    # Cấp 3: quản lý khu vực
    'ASM': 3,
    # Cấp 4: quản lý vùng
    'RSM': 4,
    # Cấp 5: giám sát
    'GSTT': 5, 'GS': 5,
    # Cấp 6: quản lý bán hàng
    'QLBH': 6,
}
MAX_LEVEL = 6
EDIT_WINDOW_DAYS = 4  # chỉ được check list / đánh giá trong ngày hôm nay và 3 ngày trước đó (ví dụ hôm nay 19/11 thì lùi được tới 16/11)
LEVEL1_CODES = [c for c, lv in ROLE_LEVEL_MAP.items() if lv == 1]  # NVBH, NV, NT, NTTT, PT
# mã dài khớp trước (ASMTT trước ASM, CHTTT trước CHT, NTTT trước NT, GSTT trước GS)
_CODES_LONG_FIRST = sorted(ROLE_LEVEL_MAP, key=len, reverse=True)
# Chức danh (job_title) viết bằng chữ -> mã chức vụ, dùng khi chức danh không chứa sẵn mã
TITLE_KEYWORDS = [
    ('quản lý bán hàng', 'QLBH'),
    ('giám sát', 'GS'),
    ('quản lý vùng', 'RSM'),
    ('quản lý khu vực', 'ASM'),
    ('cửa hàng trưởng', 'CHT'),
    ('nhóm trưởng', 'NT'),
    ('trưởng nhóm', 'NT'),
    ('nhân viên bán hàng', 'NVBH'),
    ('nhân viên ch', 'NVBH'),
]


# Tên hiển thị của mã chức vụ trên giao diện (mã dùng để tính cấp bậc giữ nguyên)
# (khớp danh sách Chức danh trong hồ sơ nhân viên: Nhân viên CH, Nhóm trưởng, Cửa hàng trưởng, ASM, RSM, Giám sát...)
ROLE_LABELS = {
    'NVBH': 'Nhân viên CH', 'NV': 'Nhân viên CH', 'NT': 'Nhóm trưởng', 'NTTT': 'Nhóm trưởng TTTM', 'PT': 'Nhân viên thời vụ',
    'CHT': 'Cửa hàng trưởng', 'CHTTT': 'Cửa hàng trưởng TTTM', 'ASMTT': 'ASM TTTM',
    'ASM': 'ASM', 'RSM': 'RSM', 'GS': 'Giám sát', 'GSTT': 'Giám sát TTTM', 'QLBH': 'Quản lý bán hàng',
}


def role_label(code):
    code = (code or '').strip().upper()
    return ROLE_LABELS.get(code, code)


def is_shared_store_user(user):
    """Tài khoản chung của cửa hàng: tên hoặc login bắt đầu bằng CH_ (vd. CH_LUG_KDV)."""
    return (user.name or '').upper().startswith('CH_') or (user.login or '').upper().startswith('CH_')


def role_code_from_title(title):
    """Suy ra Mã chức vụ từ Chức danh: ưu tiên mã có sẵn trong chức danh (vd. "ASM", "GS"), rồi tới từ khóa tiếng Việt."""
    text = (title or '').strip().lower()
    if not text:
        return ''
    tokens = set(re.findall(r'[^\W_]+', text.upper()))
    for code in _CODES_LONG_FIRST:
        if code in tokens:
            return code
    for keyword, code in TITLE_KEYWORDS:
        if keyword in text:
            return code
    return ''


def role_level(code):
    return ROLE_LEVEL_MAP.get((code or '').strip().upper(), 0)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    checklist_role_code = fields.Char(string='Mã chức vụ Checklist', compute='_compute_checklist_role', store=True,
                                      help='Suy ra từ Chức danh (NVBH, CHT, ASM, RSM, GS, QLBH...)')
    checklist_role_label = fields.Char(string='Chức vụ Checklist', compute='_compute_checklist_role_label')
    checklist_level = fields.Integer(string='Cấp bậc Checklist (1-6)', compute='_compute_checklist_role', store=True,
                                     help='0 = chức danh không thuộc hệ thống 6 cấp, không được chỉ định làm người kiểm tra')
    checklist_store_ids = fields.Many2many('hr.store', 'store_checklist_employee_store_rel', 'employee_id', 'store_id',
                                           string='Cửa hàng phụ trách (Checklist)',
                                           help='Dùng khi Sơ đồ tổ chức (Quản lý trực tiếp) chưa gắn đủ: người kiểm tra cấp cao hơn được tìm tiếp theo danh sách này.')

    @api.depends('job_title')
    def _compute_checklist_role(self):
        for emp in self:
            code = role_code_from_title(emp.job_title)
            emp.checklist_role_code = code
            emp.checklist_level = role_level(code)

    @api.model
    def _recompute_checklist_roles(self):
        """Tính lại Mã chức vụ Checklist theo Chức danh hiện tại (chạy mỗi lần nâng cấp module, khi bảng quy đổi thay đổi)."""
        emps = self.sudo().with_context(active_test=False).search([])
        emps._compute_checklist_role()
        emps.flush_recordset(['checklist_role_code', 'checklist_level'])

    @api.depends('checklist_role_code')
    def _compute_checklist_role_label(self):
        for emp in self:
            emp.checklist_role_label = role_label(emp.checklist_role_code)

    def _checklist_effective_level(self):
        """Cấp bậc thực tế: ưu tiên Mã chức vụ ở dòng Lịch xếp ca mới nhất của chính người này (vd. ASMTT), không có thì theo Chức danh."""
        self.ensure_one()
        line = self.env['store.nvbh.schedule.line'].sudo().search(
            [('staff_name', '=ilike', (self.name or '').replace('%', r'\%').replace('_', r'\_'))],
            order='work_date desc, id desc', limit=1)
        return role_level(line.position) or self.checklist_level

# Tên bước đánh giá theo cấp bậc người đánh giá (cấp 2 = CHT, 3 = ASM, 4 = RSM); bước cuối tùy chọn là Admin duyệt
STEP_CODES = {2: 'CHT', 3: 'ASM', 4: 'RSM'}
MAX_STEPS = 4


class StoreNvbhCheckStep(models.Model):
    """Lịch sử từng cấp đánh giá: ai đánh giá, lúc nào, điểm và kết quả."""
    _name = 'store.nvbh.check.step'
    _description = 'Lịch sử cấp đánh giá checklist NVBH'
    _order = 'check_id, step_no'

    check_id = fields.Many2one('store.nvbh.check', required=True, ondelete='cascade', index=True)
    step_no = fields.Integer(string='Bước')
    code = fields.Char(string='Cấp đánh giá')
    user_id = fields.Many2one('res.users', string='Người đánh giá')
    done_date = fields.Datetime(string='Hoàn tất lúc')
    points = fields.Float(string='Điểm')
    max_points = fields.Float(string='Điểm tối đa')
    result_summary = fields.Char(string='Kết quả')


class StoreNvbhCheckRole(models.Model):
    _inherit = 'store.nvbh.check'

    # Người thực hiện tick (draft) -> Gửi -> lần lượt từng cấp đánh giá (pending_review, step_done = số cấp đã xong) -> Hoàn tất (approved)
    state = fields.Selection([
        ('draft', 'Đang thực hiện'),
        ('pending_review', 'Chờ cấp trên đánh giá'),
        ('approved', 'Đã hoàn tất đánh giá'),
    ], string='Trạng thái phiếu', default='draft', required=True, index=True)
    review_sent_date = fields.Datetime(string='Gửi đánh giá lúc')
    approved_date = fields.Datetime(string='Hoàn tất đánh giá lúc')
    step_done = fields.Integer(string='Số cấp đã đánh giá xong', default=0)
    step_log_ids = fields.One2many('store.nvbh.check.step', 'check_id', string='Lịch sử đánh giá')

    @api.model
    def _user_person_domain(self, on_check=True):
        """Giới hạn theo NGƯỜI (cộng thêm giới hạn cửa hàng):
        - Nhân viên (NVBH, NT, PT...) chỉ thấy dữ liệu của chính mình;
        - CHT chỉ thấy dữ liệu của chính mình + nhân viên cấp 1 (NVBH / NT / PT) tại cửa hàng mình;
        - ASM, RSM, GS, QLBH...: theo phạm vi cửa hàng; Quản lý / Admin / phạm vi COMPANY: không giới hạn.
        on_check=True: domain cho phiếu checklist; False: domain cho dòng Lịch xếp ca."""
        user = self.env.user
        if self.env.su or user._is_admin() or user.has_group('store_checklist.group_store_manager'):
            return []
        if getattr(user.sudo(), 'lug_data_scope', False) == 'company':
            return []
        if is_shared_store_user(user):
            return []  # tài khoản chung CH_: xem mọi nhân viên của cửa hàng mình (phạm vi cửa hàng vẫn áp dụng)
        emp = user.sudo().employee_id
        if not emp:
            return []
        level = role_level(emp.sudo().checklist_role_code)
        if level not in (1, 2):
            return []
        # so khớp họ tên không phân biệt hoa/thường (so ở Python vì ILIKE của PostgreSQL không đổi hoa/thường chữ có dấu theo locale)
        key = (emp.name or '').strip().casefold()
        variants = {(n or '').strip() for n in
                    [g[0] for g in self.env['store.nvbh.schedule.line'].sudo()._read_group([], ['staff_name'])]
                    + [g[0] for g in self.sudo()._read_group([], ['staff_name'])]}
        names = sorted(n for n in variants if n and n.casefold() == key) or [emp.name or '']
        own = ('staff_name', 'in', names)
        if level == 1:
            return [own]
        pos = ('schedule_line_id.position' if on_check else 'position', 'in', LEVEL1_CODES)
        return ['|', own, pos]

    @api.model
    def _search(self, domain, *args, **kwargs):
        # phiếu checklist: giới hạn theo cửa hàng (gồm Mã bộ phận được xem) và theo người (NVBH chỉ của mình, CHT: mình + NVBH/PT)
        rule = self.env['store.staff.view.rule']._staff_domain(CHECK_MENUS)
        if rule is not None:
            # Phân quyền xem nhân sự: đúng Miền / Cửa hàng được cấp, thay cho phạm vi mặc định (cửa hàng + theo người)
            return super(StoreNvbhCheckRole, self.sudo())._search(rule + list(domain or []), *args, **kwargs)
        scope = self.env['store.audit']._user_store_scope()
        extra = list(self._user_person_domain(True))
        if scope is not None:
            extra = [('store_id', 'in', scope)] + extra
        if extra:
            domain = extra + list(domain or [])
        return super()._search(domain, *args, **kwargs)

    @api.model
    def my_checklist_role(self):
        """Mã chức vụ Checklist của người dùng đang đăng nhập (NVBH, CHT, ASM, RSM...); rỗng nếu không có hồ sơ nhân viên."""
        emp = self.env.user.sudo().employee_id
        return (emp.sudo().checklist_role_code or '') if emp else ''

    @api.model
    def get_store_check_status(self, month=None):
        """Tình trạng check list của từng cửa hàng trong tháng: {store_id: 'done' | 'pending'}; cửa hàng chưa gửi phiếu nào thì không có trong kết quả (màu trắng).
        pending (cam) = đã gửi check list, còn phiếu chờ đánh giá; done (xanh lá) = mọi phiếu đã gửi đều được đánh giá xong ở mọi cấp."""
        start, end, _days = self._month_range(month)
        groups = self._read_group([('work_date', '>=', start), ('work_date', '<', end), ('submitted', '=', True)],
                                  ['store_id', 'state'], ['__count'])
        ok = {}
        for store, state, _count in groups:
            if store:
                ok[store.id] = ok.get(store.id, True) and state == 'approved'
        return {str(k): ('done' if v else 'pending') for k, v in ok.items()}

    @api.model
    def get_my_stores(self):
        """Danh sách cửa hàng cho các ô lọc: người dùng chỉ thấy cửa hàng của mình (admin / không giới hạn thì thấy hết)."""
        ids = self.env['store.staff.view.rule']._scope_store_ids(CHECK_MENUS)
        if ids is None:
            stores = self.env['store.audit']._filter_stores_for_user(self.env['hr.store'].search([], order='name'))
        else:  # Phân quyền xem nhân sự: ô lọc liệt kê đúng các cửa hàng được cấp
            Store = self.env['hr.store'].sudo()
            stores = Store.search([], order='name') if ids is True else Store.search([('id', 'in', list(ids))], order='name')
        return [{'id': st.id, 'display_name': st.display_name, 'mien': st.mien or ''} for st in stores]

    # ------------------------------------------------------------------
    # Phân tầng: người thực hiện -> các cấp đánh giá (luồng động theo Sơ đồ tổ chức)
    # ------------------------------------------------------------------
    def _subject_employee(self):
        """Hồ sơ nhân viên của người thực hiện checklist (khớp theo ID, rồi theo họ tên trong cửa hàng, rồi toàn công ty)."""
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        line = self.schedule_line_id
        code = (line.employee_code or '').strip() if line else ''
        for fname in ('barcode', 'ma_cham_cong', 'ma_nv_ke_toan'):
            if code and fname in Employee._fields:
                emp = Employee.search([(fname, '=', code)], limit=1)
                if emp:
                    return emp
        name = (self.staff_name or '').strip().casefold()
        if not name:
            return Employee
        members = self.store_id.sudo().member_ids if 'member_ids' in self.store_id._fields else Employee
        for emp in members:
            if (emp.name or '').strip().casefold() == name:
                return emp
        safe = (self.staff_name or '').strip().replace('%', r'\%').replace('_', r'\_')
        return Employee.search([('name', '=ilike', safe)], limit=1)

    def _find_reviewer(self, level, subject):
        """Người đánh giá đầu tiên:
        1. Ưu tiên Quản lý trực tiếp (parent_id) trong Sơ đồ tổ chức của người thực hiện.
        2. Hồ sơ chưa gắn Quản lý: quét nhân sự phụ trách cửa hàng có cấp cao hơn (cấp trống / đồng cấp tự bị bỏ qua)."""
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        parent = subject.parent_id if subject else Employee
        if parent and parent.active and parent != subject:
            return parent
        store = self.store_id.sudo()
        base = [('checklist_store_ids', 'in', store.id), ('store_id', '=', store.id),
                ('id', 'in', store.member_ids.ids), ('id', '=', store.manager_id.id or 0)]
        if 'ma_bo_phan' in Employee._fields:
            base.append(('ma_bo_phan', '=ilike', store.code or '-'))
        domain = ['|'] * (len(base) - 1) + base
        cands = Employee.search(domain).filtered(lambda e: e != subject and e._checklist_effective_level() > level)
        return cands.sorted(lambda e: (e._checklist_effective_level(), e.id))[:1]

    def _subject_level(self):
        self.ensure_one()
        line = self.schedule_line_id
        code = ((line.position if line else '') or 'NVBH').strip().upper()
        return code, ROLE_LEVEL_MAP.get(code, 1)

    def _approval_chain(self):
        """Luồng đánh giá động: đi ngược Sơ đồ tổ chức từ người thực hiện, mỗi cấp bậc cao hơn (CHT -> ASM -> RSM) là một bước;
        cấp không có người (hoặc đồng cấp / cấp thấp hơn) tự bị bỏ qua. Bước Admin duyệt chỉ thêm khi bật tham số
        store_checklist.admin_approval = 1. Trả về list dict {code, level, employee, user, admin_only}."""
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        subject = self._subject_employee()
        _code, level = self._subject_level()
        chain = []
        last = level

        def add(emp, lvl):
            chain.append({'code': STEP_CODES.get(min(max(lvl, 2), 4)), 'level': lvl, 'employee': emp,
                          'user': emp.user_id, 'admin_only': False})

        node = subject.parent_id if subject and subject.parent_id else Employee
        if not node:
            first = self._find_reviewer(level, subject)
            if first:
                lvl = first._checklist_effective_level() or (level + 1)
                add(first, lvl)
                last = lvl
                node = first.parent_id
        hops = 0
        while node and hops < 8 and len(chain) < MAX_STEPS:
            if node.active and node != subject:
                lvl = node._checklist_effective_level()
                if lvl > last and lvl in STEP_CODES:
                    add(node, lvl)
                    last = lvl
            node = node.parent_id
            hops += 1
        if len(chain) < MAX_STEPS and self.env['ir.config_parameter'].sudo().get_param('store_checklist.admin_approval') == '1':
            chain.append({'code': 'ADM', 'level': 5, 'employee': Employee, 'user': self.env['res.users'], 'admin_only': True})
        return chain

    def _role_info(self):
        """Mã chức vụ + cấp bậc người thực hiện, luồng đánh giá và quyền của người dùng hiện tại theo từng bước."""
        self.ensure_one()
        user = self.env.user
        code, level = self._subject_level()
        subject = self._subject_employee()
        is_admin = user.has_group('base.group_system')
        shared = is_shared_store_user(user)
        subject_user = subject.user_id if subject else False
        own = bool(subject_user and subject_user.id == user.id)
        if is_admin:
            may_execute = True
        elif level == 1:
            # tài khoản chung CH_ chỉ tick cho Cấp 1 và chỉ ở cửa hàng của mình
            allowed = set(user._linkq_allowed_hr_store_ids()) if hasattr(user, '_linkq_allowed_hr_store_ids') else set()
            may_execute = own or (shared and (not allowed or self.store_id.id in allowed))
        else:
            # từ Cấp 2: bắt buộc User Odoo cá nhân của chính người đó, tài khoản CH_ bị khóa
            may_execute = own and not shared
        # quá hạn chỉnh sửa (> 4 ngày so với hôm nay): khóa mọi người, trừ Quản trị / Quản lý Checklist
        locked_expired = self._is_expired() and not (is_admin or user.has_group('store_checklist.group_store_manager'))
        chain = self._approval_chain()
        # bước đang đến lượt: phiếu đã gửi -> cấp kế tiếp; phiếu còn "Đang thực hiện" -> cấp đầu tiên chỉ được đánh giá khi
        # người thực hiện đã làm xong mọi công việc (chưa làm xong thì cấp trên chưa được tích đánh giá; Quản trị viên vẫn được)
        staff_done = bool(self.line_ids) and all(self.line_ids.mapped('is_done'))
        wait_staff = self.state == 'draft' and bool(chain) and not staff_done
        if self.state == 'pending_review' and self.step_done < len(chain):
            cur = self.step_done + 1
        elif self.state == 'draft' and chain and (staff_done or is_admin):
            cur = 1
        else:
            cur = 0
        steps = []
        for i, st in enumerate(chain, 1):
            u = st['user']
            if st['admin_only']:
                can_edit = cur == i and is_admin and not locked_expired
            else:
                # chỉ người được phân công đúng cấp (hoặc Quản trị viên) mới đánh giá; cấp dưới không đánh giá cấp trên;
                # cấp chưa có User Odoo thì nhóm Quản lý Checklist thay thế
                mine = bool(u and u.id == user.id) or (not u and user.has_group('store_checklist.group_store_manager') and not shared)
                can_edit = cur == i and (is_admin or mine) and not locked_expired
            steps.append(dict(st, no=i, done=i <= self.step_done, current=cur == i, can_edit=can_edit))
        first = steps[0] if steps else {}
        return {
            'chain': steps, 'cur': cur, 'wait_staff': wait_staff, 'role_code': code, 'level': level, 'subject': subject,
            'reviewer': first.get('employee') or self.env['hr.employee'], 'reviewer_user': first.get('user') or self.env['res.users'],
            # tick / ghi chú: chỉ khi đang thực hiện (sau khi gửi cấp trên thì khóa)
            'can_execute': may_execute and self.state == 'draft' and not locked_expired,
            'can_submit': may_execute and self.state == 'draft' and not locked_expired,
            'shared': shared,
            'locked_expired': locked_expired,
        }

    @api.model
    def _edit_cutoff(self):
        """Ngày cũ nhất còn được chỉnh sửa (hôm nay lùi EDIT_WINDOW_DAYS - 1 ngày)."""
        return fields.Date.context_today(self) - timedelta(days=EDIT_WINDOW_DAYS - 1)

    def _is_expired(self):
        """Quá hạn chỉnh sửa: ngày check list cách hôm nay quá 4 ngày -> hệ thống tự khóa, điểm mặc định 0đ nếu chưa được đánh giá."""
        self.ensure_one()
        return bool(self.work_date) and self.work_date < self._edit_cutoff()

    def _expired_message(self):
        return _('Đã quá %d ngày so với ngày check list (%s) nên hệ thống tự khóa, không chỉnh sửa hay đánh giá được nữa; '
                 'phiếu chưa được đánh giá tính điểm mặc định 0đ. Hạn chỉnh sửa hiện tại: từ ngày %s.') % (
                     EDIT_WINDOW_DAYS, self.work_date.strftime('%d/%m/%Y') if self.work_date else '', self._edit_cutoff().strftime('%d/%m/%Y'))

    def _assert_can_execute(self):
        for check in self:
            info = check._role_info()
            if info['can_execute']:
                continue
            if info['locked_expired']:
                raise AccessError(check._expired_message())
            if check.state != 'draft':
                raise AccessError(_('Checklist này đã gửi cấp trên đánh giá nên không thể sửa nữa.'))
            raise AccessError(_('Bạn không có quyền thực hiện checklist này: tài khoản chung CH_ chỉ tick cho Cấp 1 '
                                '(NVBH, NV, NT, NTTT, PT); từ Cấp 2 trở lên phải đăng nhập User cá nhân.'))

    def _checklist_payload(self):
        payload = super()._checklist_payload()
        info = self._role_info()
        steps = info['chain']
        payload.update({
            'state': self.state,
            'role_code': info['role_code'],
            'role_label': role_label(info['role_code']),
            'level': info['level'],
            'step_done': self.step_done,
            'steps': [{
                'no': s['no'], 'code': s['code'], 'label': '%s Đánh giá' % s['code'],
                'name': s['employee'].name if s['employee'] else ('Admin' if s['admin_only'] else ''),
                'user_id': s['user'].id if s['user'] else 0, 'done': s['done'], 'current': s['current'], 'can_edit': s['can_edit'],
            } for s in steps],
            'can_execute': info['can_execute'],
            'can_submit': info['can_submit'],
            'locked_expired': info['locked_expired'],
            'wait_staff': info['wait_staff'],
            'staff_done': len(self.line_ids.filtered('is_done')), 'staff_total': len(self.line_ids),
            'edit_deadline': self._edit_cutoff().strftime('%d/%m/%Y'),
            'reviewer_name': steps[0]['employee'].name if steps and steps[0]['employee'] else '',
            'reviewer_role': steps[0]['code'] if steps else '',
        })
        return payload

    # ------------------------------------------------------------------
    # Luồng chuyển tiếp: Gửi -> cấp 1 -> cấp 2 -> ... -> Hoàn tất
    # ------------------------------------------------------------------
    def _notify_step(self, step):
        """Thông báo cho người ở bước đánh giá tiếp theo."""
        self.ensure_one()
        if not step or not step.get('user'):
            return
        bot_send(self.env, step['user'], card('CHECKLIST CHỜ %s ĐÁNH GIÁ' % step['code'], [
            ('Người thực hiện', self.staff_name or ''),
            ('Cửa hàng', self.store_id.display_name),
            ('Ngày', self.work_date.strftime('%d/%m/%Y') if self.work_date else ''),
            ('Ca', self.shift_id.code),
        ], label='Mở để đánh giá', check_id=self.id))

    @api.model
    def submit_to_reviewer(self, check_id):
        """Nút "Gửi cấp trên đánh giá": chốt phần làm của người thực hiện, chuyển cho cấp đánh giá đầu tiên."""
        check = self.browse(int(check_id)).exists()
        if not check:
            return False
        info = check._role_info()
        if not info['can_submit']:
            check._assert_can_execute()
            raise AccessError(_('Bạn không có quyền gửi checklist này.'))
        chain = info['chain']
        if not chain:
            raise UserError(_('Chưa xác định được người quản lý cấp trên của %s: hãy gắn Quản lý trong hồ sơ nhân viên '
                              'hoặc "Cửa hàng phụ trách" cho người kiểm tra cấp trên.') % (check.staff_name or ''))
        total = len(check.line_ids)
        done = len(check.line_ids.filtered('is_done'))
        if done < total:
            raise UserError(_('Mới hoàn thành %s/%s công việc. Hãy hoàn tất trước khi gửi cấp trên đánh giá.') % (done, total))
        first = chain[0]
        check = check.sudo()  # quyền đã kiểm tra ở trên
        check.line_ids.write({'reviewer_id': first['user'].id if first['user'] else False})  # tự gán, không cho chọn tay
        check.write({'state': 'pending_review', 'step_done': 0, 'review_sent_date': fields.Datetime.now(), 'submitted': True,
                     'submit_date': check.submit_date or fields.Datetime.now(),
                     'submitted_by': check.submitted_by.id or self.env.user.id})
        check._notify_step(first)
        return check._checklist_payload()

    @api.model
    def save_step_evaluation(self, check_id, step_no, changes):
        """Lưu đánh giá của một cấp: changes = [{id, result, detail}, ...]. Chỉ người được phân công cho đúng bước hiện tại
        (hoặc Quản trị viên) mới lưu được. Chấm đủ mọi đầu việc thì hoàn tất bước, chuyển cho cấp tiếp theo (hoặc hoàn tất phiếu)."""
        check = self.browse(int(check_id)).exists()
        if not check:
            return False
        step_no = int(step_no)
        info = check._role_info()
        step = next((s for s in info['chain'] if s['no'] == step_no), None)
        if not step or not step['can_edit']:
            if info['locked_expired']:
                raise AccessError(check._expired_message())
            if check.state == 'draft':
                raise AccessError(_('Nhân viên chưa hoàn thành checklist (%s/%s công việc) nên cấp trên chưa được đánh giá.')
                                  % (len(check.line_ids.filtered('is_done')), len(check.line_ids)))
            if check.state == 'approved':
                raise AccessError(_('Phiếu đã hoàn tất đánh giá và bị khóa.'))
            raise AccessError(_('Chưa đến lượt hoặc bạn không phải người được phân công đánh giá ở cấp này '
                                '(cấp dưới không được đánh giá cấp trên; phải chờ cấp trước lưu đánh giá).'))
        pre = STEP_PREFIX[step_no - 1]
        assigned = step['user'].id if step['user'] else self.env.user.id
        check = check.sudo()  # quyền đã kiểm tra ở trên
        if check.state == 'draft':  # cấp đầu tiên đánh giá khi người thực hiện chưa gửi: tự chuyển sang giai đoạn đánh giá
            check.write({'state': 'pending_review', 'step_done': 0, 'review_sent_date': fields.Datetime.now(), 'submitted': True,
                         'submit_date': check.submit_date or fields.Datetime.now(),
                         'submitted_by': check.submitted_by.id or self.env.user.id})
        lines = {l.id: l for l in check.line_ids}
        valid = {k for k, _l in EVAL_RESULTS}
        for ch in changes or []:
            line = lines.get(int(ch.get('id') or 0))
            if not line:
                continue
            detail = '\n'.join(ln.strip() for ln in (ch.get('detail') or '').splitlines() if ln.strip())
            result = 'bad' if detail else (ch.get('result') or False)  # có ghi chi tiết lỗi thì KQ đánh giá là Không đạt
            line.write({
                pre + 'reviewer_id': assigned,
                pre + 'eval_result': result if result in valid else False,
                pre + 'error_detail': detail or False,
            })
        if check.line_ids and all(check.line_ids.mapped(pre + 'eval_result')):
            check._finish_step(step_no, step, info['chain'])
        return check._checklist_payload()

    def _step_points(self, code):
        """Điểm do cấp đánh giá có mã `code` (CHT / ASM / RSM) chấm cho phiếu; None nếu phiếu không có cấp đó hoặc cấp đó chưa chấm đủ."""
        self.ensure_one()
        for i, st in enumerate(self._approval_chain(), 1):
            if st['code'] != code:
                continue
            pre = STEP_PREFIX[i - 1]
            lines = self.line_ids
            if not lines or not all(l[pre + 'eval_result'] for l in lines):
                return None
            return round(sum(eval_score(l.max_score, l[pre + 'eval_result'], count_errors(l[pre + 'error_detail'])) for l in lines), 2)
        return None

    def _step_errors(self, code):
        """Số lỗi do cấp `code` (CHT / ASM / RSM) ghi ở cột Chi tiết lỗi (mỗi dòng là một lỗi);
        None nếu phiếu không có cấp đó hoặc cấp đó chưa đánh giá dòng nào."""
        self.ensure_one()
        for i, st in enumerate(self._approval_chain(), 1):
            if st['code'] != code:
                continue
            pre = STEP_PREFIX[i - 1]
            lines = self.line_ids
            if not any(l[pre + 'eval_result'] or l[pre + 'error_detail'] for l in lines):
                return None
            return sum(count_errors(l[pre + 'error_detail']) for l in lines)
        return None

    def _finish_step(self, step_no, step, chain):
        """Hoàn tất một cấp: ghi lịch sử, khóa cấp đó, chuyển cho cấp tiếp theo hoặc hoàn tất phiếu."""
        self.ensure_one()
        now = fields.Datetime.now()
        vals = {'step_done': step_no}
        last = step_no >= len(chain)
        if last:
            vals.update({'state': 'approved', 'approved_date': now})
        self.write(vals)
        self.env['store.nvbh.check.step'].create({
            'check_id': self.id, 'step_no': step_no, 'code': step['code'],
            'user_id': self.env.user.id, 'done_date': now, 'points': self.points,
            'max_points': sum(self.line_ids.mapped('max_score')),
            'result_summary': _('%s lỗi') % self.error_total if self.error_total else _('Không lỗi'),
        })
        if not last:
            self._notify_step(chain[step_no])  # chain[step_no] = bước kế tiếp (đánh số từ 1)

    # ------------------------------------------------------------------
    # Dữ liệu cũ: quy đổi sang luồng nhiều cấp (chạy một lần)
    # ------------------------------------------------------------------
    @api.model
    def _migrate_workflow_steps(self):
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('store_checklist.workflow_steps_migrated') == '1':
            return
        cr = self.env.cr
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'store_nvbh_check' AND column_name = 'asm_done'")
        has_old = bool(cr.fetchone())
        asm_done_ids = set()
        if has_old:
            cr.execute("SELECT id FROM store_nvbh_check WHERE asm_done")
            asm_done_ids = {r[0] for r in cr.fetchall()}
        for check in self.sudo().search([('state', '!=', 'draft')]):
            n = len(check._approval_chain()) or 1
            if check.id in asm_done_ids:
                done = min(2, n)
            elif check.state == 'approved':
                done = 1
            else:
                done = 0
            vals = {'step_done': done}
            if done >= n:
                vals['state'] = 'approved'
            elif check.state == 'approved':
                vals['state'] = 'pending_review'
            check.write(vals)
        self.env['store.nvbh.check.line'].sudo().search([])._compute_error_count()
        self.env['store.nvbh.check.line'].sudo().search([])._compute_actual_score()
        ICP.set_param('store_checklist.workflow_steps_migrated', '1')
