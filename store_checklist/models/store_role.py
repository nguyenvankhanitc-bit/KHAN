import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_audit_staff import CHECK_MENUS
from markupsafe import Markup

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
# Thời hạn (tham số hệ thống ghi đè được: store_checklist.staff_window_days / store_checklist.review_window_days)
EDIT_WINDOW_DAYS = 4    # NVBH: check list từ ngày làm việc (D) đến hết ngày D+4; quá hạn thì khóa, không ghi nhận (0đ)
REVIEW_WINDOW_DAYS = 4  # mỗi cấp đánh giá (CHT, ASM...): 4 ngày kể từ khi đến lượt; quá hạn thì khóa, điểm cấp đó tính 0đ
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
    staff_done_date = fields.Datetime(string='NV hoàn thành lúc', copy=False,
                                      help='Lúc nhân viên tích xong mọi công việc: mốc bắt đầu tính hạn đánh giá của cấp đầu tiên (CHT)')

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
        line = self.schedule_line_id
        code = (line.employee_code or '').strip() if line else ''
        name = (self.staff_name or '').strip().casefold()
        cache = self.env.cr.cache.setdefault('store_subject_emp', {})
        ck = (self.asm_employee_id.id or 0, self.store_id.id or 0, code, name)
        if ck in cache:
            return self.env['hr.employee'].sudo().browse(cache[ck])
        emp = self._subject_employee_uncached(code, name)
        cache[ck] = emp.id or False
        return emp

    def _subject_employee_uncached(self, code, name):
        Employee = self.env['hr.employee'].sudo()
        if self.asm_employee_id:  # check list ASM: gắn thẳng hồ sơ ASM
            return self.asm_employee_id.sudo()
        for fname in ('barcode', 'ma_cham_cong', 'ma_nv_ke_toan'):
            if code and fname in Employee._fields:
                emp = Employee.search([(fname, '=', code)], limit=1)
                if emp:
                    return emp
        if not name:
            return Employee
        members = self.store_id.sudo().member_ids if 'member_ids' in self.store_id._fields else Employee
        for emp in members:
            if (emp.name or '').strip().casefold() == name:
                return emp
        safe = (self.staff_name or '').strip().replace('%', r'\%').replace('_', r'\_')
        emp = Employee.search([('name', '=ilike', safe)], limit=1)
        if emp:
            return emp
        # ILIKE của PostgreSQL không đổi hoa/thường chữ có dấu (vd. "CAO NGỌC NHI" ≠ "Cao Ngọc Nhi") -> lọc sơ bằng các từ
        # không dấu (CAO, NHI) rồi so khớp họ tên (casefold) ở Python
        words = [w for w in (self.staff_name or '').split() if w.isascii() and w.isalpha()]
        domain = [('name', 'ilike', w) for w in words]
        for emp in Employee.search(domain, limit=None if domain else 5000):
            if (emp.name or '').strip().casefold() == name:
                return emp
        return Employee

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
        if self.kind == 'asm' and not self.schedule_line_id:
            return 'ASM', 3
        line = self.schedule_line_id
        code = ((line.position if line else '') or 'NVBH').strip().upper()
        return code, ROLE_LEVEL_MAP.get(code, 1)

    def _approval_chain(self):
        """Luồng đánh giá động: đi ngược Sơ đồ tổ chức từ người thực hiện, mỗi cấp bậc cao hơn (CHT -> ASM -> RSM) là một bước;
        cấp không có người (hoặc đồng cấp / cấp thấp hơn) tự bị bỏ qua. Luồng theo loại phiếu: NVBH -> CHT; CHT -> ASM;
        ASM -> RSM (nếu có) -> Admin / Admin tổng (nếu có). Trả về list dict {code, level, employee, user, admin_only}."""
        self.ensure_one()
        line = self.schedule_line_id
        cache = self.env.cr.cache.setdefault('store_approval_chain', {})
        ck = (self.asm_employee_id.id or 0, self.store_id.id or 0, self.kind or '',
              (self.staff_name or '').strip().casefold(),
              (line.employee_code or '').strip() if line else '',
              (line.position or '').strip().upper() if line else '')
        if ck in cache:
            return [dict(s) for s in cache[ck]]
        chain = self._approval_chain_uncached()
        cache[ck] = chain
        return [dict(s) for s in chain]

    def _approval_chain_uncached(self):
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
        if self.kind == 'asm':
            # check list ASM: RSM đánh giá (nếu có) -> Admin / Admin tổng duyệt kết quả cuối cùng (nếu có user chức vụ Admin)
            chain = [c for c in chain if c['code'] == 'RSM'][:1]
            if self._admin_title_employees():
                chain.append(self._admin_title_step(subject))
            return chain
        # CHT tự đánh giá checklist của mình (ASM đánh giá tổng theo tuần ở trang Đánh giá Toàn Cửa Hàng)
        if self.kind == 'cht':
            if subject:
                return [{'code': 'CHT', 'level': 2, 'employee': subject, 'user': subject.user_id, 'admin_only': False}]
            return chain[:1]
        # NVBH check list -> CHT đánh giá, chốt điểm cuối cùng (không chờ ASM duyệt từng ngày; ASM đánh giá tổng theo tuần)
        return chain[:1]

    @api.model
    def _admin_title_employees(self):
        """Nhân sự có chức vụ (Chức danh) Admin / Admin tổng và có User Odoo."""
        emps = self.env['hr.employee'].sudo().search([('job_title', '=ilike', 'admin%'), ('user_id', '!=', False)])
        return emps.filtered(lambda e: (e.job_title or '').strip().casefold() in ('admin', 'admin tổng', 'admin tong'))

    def _admin_title_step(self, subject):
        """Bước Admin duyệt cuối của check list ASM: mọi user có chức vụ Admin / Admin tổng được duyệt;
        người hiển thị / nhận thông báo chính là Admin gần nhất trong Sơ đồ tổ chức của người thực hiện."""
        emps = self._admin_title_employees()
        main = self.env['hr.employee']
        node, hops = (subject.parent_id if subject else main), 0
        while node and hops < 8:
            if node in emps:
                main = node
                break
            node, hops = node.parent_id, hops + 1
        main = main or emps[:1]
        return {'code': 'Admin', 'level': 5, 'employee': main, 'user': main.user_id, 'admin_only': False,
                'admin_title': True, 'users': emps.mapped('user_id')}

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
        # thời hạn: NVBH đến hết ngày D+4; mỗi cấp đánh giá 4 ngày kể từ khi đến lượt. Quá hạn -> hệ thống khóa
        # (Quản trị / Quản lý Checklist vẫn chỉnh được)
        privileged = is_admin or user.has_group('store_checklist.group_store_manager')
        locked_expired = bool(self._late_stage()) and not privileged
        staff_locked = not privileged and self._staff_late()
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
        may_reedit = self._can_reedit_right()
        for i, st in enumerate(chain, 1):
            u = st['user']
            if st['admin_only']:
                mine = is_admin
                can_edit = cur == i and is_admin and not locked_expired
            else:
                # chỉ người được phân công đúng cấp (hoặc Quản trị viên) mới đánh giá; cấp dưới không đánh giá cấp trên;
                # cấp chưa có User Odoo thì nhóm Quản lý Checklist thay thế
                mine = bool(u and u.id == user.id) or (not u and user.has_group('store_checklist.group_store_manager') and not shared)
                if st.get('admin_title'):  # duyệt cuối check list ASM: mọi user chức vụ Admin / Admin tổng
                    mine = mine or user in st['users']
                can_edit = cur == i and (is_admin or mine) and not locked_expired
            # sửa lại đánh giá: cấp vừa hoàn tất gần nhất (cấp sau chưa đánh giá), người của cấp đó có quyền Sửa,
            # được sửa đến 23h55 ngày đánh giá xong; sau giờ đó hệ thống khóa
            # check list CHT: chính ASM đã chấm được sửa lại đánh giá của mình đến 23h55 ngày chấm (không cần quyền Sửa menu)
            reedit_until = self._reedit_until(i) if (i == self.step_done and (is_admin or mine)
                                                     and (may_reedit or (self.kind in ('cht', 'nvbh') and mine and st['code'] == 'ASM'))) else False
            reedit = bool(reedit_until) and fields.Datetime.now() <= reedit_until
            steps.append(dict(st, no=i, done=i <= self.step_done, current=cur == i, can_edit=can_edit or reedit,
                              reedit=reedit, reedit_until=reedit_until if reedit else False))
        first = steps[0] if steps else {}
        # người thực hiện sửa lại check list của mình sau khi đã gửi (kể cả khi cấp trên đã đánh giá): đến 23h55 ngày gửi,
        # sau giờ đó hệ thống khóa
        self_until = False
        if may_execute and self.state in ('pending_review', 'approved') and not locked_expired:
            sent = max([d for d in (self.review_sent_date, self.staff_done_date, self.submit_date) if d] or [False]) or False
            self_until = self._cutoff_2355(sent) if sent else False
        self_reedit = bool(self_until) and fields.Datetime.now() <= self_until
        return {
            'chain': steps, 'cur': cur, 'wait_staff': wait_staff, 'role_code': code, 'level': level, 'subject': subject,
            'reviewer': first.get('employee') or self.env['hr.employee'], 'reviewer_user': first.get('user') or self.env['res.users'],
            # tick / ghi chú: chỉ khi đang thực hiện (sau khi gửi cấp trên thì khóa)
            'can_execute': (may_execute and self.state == 'draft' and not staff_locked and not locked_expired) or self_reedit,
            'self_reedit_until': self_until if self_reedit else False,
            'can_submit': may_execute and self.state == 'draft' and not staff_locked and not locked_expired,
            'shared': shared,
            'locked_expired': locked_expired,
            'staff_locked': staff_locked,
        }

    @api.model
    def _can_reedit_right(self):
        """Quyền Sửa ở "Danh sách checklist NV" hoặc "Quản lý & đánh giá" (Quản trị / Quản lý / user không áp ma trận: có)."""
        rights = self.env['store.perm.rule']._rights()
        if rights is None:
            return True
        return any(rights.get(k, {}).get('write') for k in ('nvbh_done', 'nvbh_mg'))

    def _self_edit_open(self):
        """Phiếu đã gửi còn trong hạn người thực hiện sửa lại (đến 23h55 ngày gửi)."""
        self.ensure_one()
        if self.state not in ('pending_review', 'approved'):
            return False
        sent = max([d for d in (self.review_sent_date, self.staff_done_date, self.submit_date) if d] or [False]) or False
        return bool(sent) and fields.Datetime.now() <= self._cutoff_2355(sent)

    def _cutoff_2355(self, dt):
        """23h55 (giờ Việt Nam / múi giờ của user) của ngày chứa mốc dt (UTC), trả về UTC."""
        import pytz
        from datetime import datetime, time
        tz = pytz.timezone(self.env.user.tz or 'Asia/Ho_Chi_Minh')
        local_day = pytz.utc.localize(dt).astimezone(tz).date()
        return tz.localize(datetime.combine(local_day, time(23, 55))).astimezone(pytz.utc).replace(tzinfo=None)

    def _reedit_until(self, step_no):
        """Hạn sửa lại đánh giá của cấp step_no: 23h55 (giờ Việt Nam) của ngày cấp đó đánh giá xong, đổi ra UTC; False nếu chưa có."""
        self.ensure_one()
        import pytz
        from datetime import datetime, time
        logs = self.step_log_ids.filtered(lambda s: s.step_no == step_no and s.done_date)
        if not logs:
            return False
        return self._cutoff_2355(max(logs.mapped('done_date')))

    # ------------------------------------------------------------------
    # Thời hạn: NVBH (ngày D -> hết D+4) · CHT (4 ngày sau khi NV hoàn thành) · ASM (4 ngày sau khi CHT đánh giá xong)
    # ------------------------------------------------------------------
    @api.model
    def _window_days(self, key, default):
        try:
            return max(int(self.env['ir.config_parameter'].sudo().get_param(key, default)), 0)
        except (TypeError, ValueError):
            return default

    @api.model
    def _staff_days(self):
        return self._window_days('store_checklist.staff_window_days', EDIT_WINDOW_DAYS)

    @api.model
    def _review_days(self):
        return self._window_days('store_checklist.review_window_days', REVIEW_WINDOW_DAYS)

    @api.model
    def _edit_cutoff(self):
        """Ngày làm việc cũ nhất NVBH còn được check list (hôm nay lùi số ngày hạn của NVBH)."""
        return fields.Date.context_today(self) - timedelta(days=self._staff_days())

    def _local_date(self, dt):
        return fields.Datetime.context_timestamp(self, dt).date() if dt else False

    def _staff_finished(self):
        self.ensure_one()
        return bool(self.line_ids) and all(self.line_ids.mapped('is_done'))

    def _staff_deadline(self):
        """Hạn check list của nhân viên: hết ngày D + 4."""
        self.ensure_one()
        return self.work_date + timedelta(days=self._staff_days()) if self.work_date else False

    def _staff_late(self):
        self.ensure_one()
        dl = self._staff_deadline()
        return bool(dl) and fields.Date.context_today(self) > dl

    def _step_start(self, no):
        """Ngày cấp đánh giá thứ `no` đến lượt: cấp 1 = ngày nhân viên hoàn thành checklist; cấp sau = ngày cấp trước đánh giá xong.
        False nếu chưa đến lượt."""
        self.ensure_one()
        if no <= 1:
            if self.state == 'draft' and not self._staff_finished():
                return False
            start = self._local_date(self.staff_done_date or self.review_sent_date or self.submit_date) or self.work_date
            return max(start, self.work_date) if self.work_date else start
        if self.step_done < no - 1:
            return False
        logs = self.step_log_ids.filtered(lambda s: s.step_no == no - 1 and s.done_date)
        dt = max(logs.mapped('done_date')) if logs else (self.approved_date or self.review_sent_date)
        return self._local_date(dt) or self.work_date

    def _step_deadline(self, no):
        """Hạn đánh giá của cấp thứ `no`: hết ngày (ngày đến lượt + 4).
        Check list CHT: ASM đánh giá theo lần ghé thăm, phiếu sau ngày ghé chuyển sang tuần kế tiếp -> hạn là hết Chủ nhật
        của tuần kế tiếp (tuần N+1) tính từ ngày làm việc (không sớm hơn hạn 4 ngày)."""
        start = self._step_start(no)
        if not start:
            return False
        dl = start + timedelta(days=self._review_days())
        if self.kind in ('cht', 'nvbh') and self.work_date:
            # bước ASM (chấm theo lần ghé thăm): hạn đến hết tuần kế tiếp của ngày làm việc
            chain = self._approval_chain()
            if no <= len(chain) and chain[no - 1]['code'] == 'ASM':
                dl = max(dl, self.work_date - timedelta(days=self.work_date.weekday()) + timedelta(days=13))
        return dl

    def _late_stage(self):
        """Phiếu đã bị hệ thống khóa vì quá hạn: 'staff' = nhân viên chưa hoàn thành khi hết hạn (không ghi nhận);
        số bước (1, 2...) = cấp đánh giá đó trễ hạn (điểm cấp đó 0đ); False = chưa quá hạn / đã hoàn tất."""
        self.ensure_one()
        if self.state == 'approved' or not self.work_date:
            return False
        if self.state == 'draft' and not self._staff_finished():
            return 'staff' if self._staff_late() else False
        no = self.step_done + 1 if self.state == 'pending_review' else 1
        dl = self._step_deadline(no)
        return no if dl and fields.Date.context_today(self) > dl else False

    def _late_code(self):
        """'NVBH' / 'CHT' / 'ASM'... : cấp đã trễ hạn khiến phiếu bị khóa; '' nếu không."""
        self.ensure_one()
        st = self._late_stage()
        if not st:
            return ''
        if st == 'staff':
            return 'NVBH'
        chain = self._approval_chain()
        return chain[st - 1]['code'] if st <= len(chain) else 'CHT'

    def _is_expired(self):
        """Quá hạn (hệ thống đã khóa): phiếu được chốt với điểm hiện có, phần chưa đánh giá tính 0đ."""
        self.ensure_one()
        return bool(self._late_stage())

    def _fmt_date(self, d):
        return d.strftime('%d/%m/%Y') if d else ''

    def _staff_lock_message(self):
        return _('Đã hết hạn check list của ngày %s (hạn đến hết ngày %s) nên hệ thống tự khóa, nhân viên không chỉnh sửa được nữa.') % (
            self._fmt_date(self.work_date), self._fmt_date(self._staff_deadline()))

    def _expired_message(self):
        self.ensure_one()
        st = self._late_stage()
        if st == 'staff':
            return _('Nhân viên chưa hoàn thành checklist ngày %s trước hạn (hết ngày %s) nên hệ thống đã khóa: '
                     'checklist không được ghi nhận, điểm tính 0đ.') % (self._fmt_date(self.work_date), self._fmt_date(self._staff_deadline()))
        if st:
            code = self._late_code()
            return _('%s không đánh giá trong %d ngày (hạn đến hết ngày %s) nên hệ thống đã khóa: ghi nhận %s trễ hạn, '
                     'điểm %s đánh giá tính 0đ.') % (code, self._review_days(), self._fmt_date(self._step_deadline(st)), code, code)
        return _('Phiếu đã bị khóa.')

    def _stamp_staff_done(self):
        """Ghi lại lúc nhân viên tích xong mọi công việc (mốc tính hạn đánh giá của CHT); bỏ tích lại thì xóa mốc."""
        for c in self.sudo():
            fin = c._staff_finished()
            if fin and not c.staff_done_date:
                c.write({'staff_done_date': fields.Datetime.now()})
            elif not fin and c.staff_done_date and c.state == 'draft':
                c.write({'staff_done_date': False})

    @api.model
    def save_checklist(self, check_id, changes):
        check = self.browse(int(check_id)).exists()
        before = check._line_state()
        super().save_checklist(check_id, changes)
        check._stamp_staff_done()
        check._after_staff_edit(before)
        return check._checklist_payload()

    @api.model
    def toggle_line(self, line_id, done):
        check = self.env['store.nvbh.check.line'].browse(int(line_id)).exists().check_id
        before = check._line_state()
        super().toggle_line(line_id, done)
        check._after_staff_edit(before)
        return check._checklist_payload()

    @api.model
    def save_note(self, line_id, note):
        check = self.env['store.nvbh.check.line'].browse(int(line_id)).exists().check_id
        before = check._line_state()
        super().save_note(line_id, note)
        check._after_staff_edit(before)
        return check._checklist_payload()

    @api.model
    def toggle_all(self, check_id, done):
        check = self.browse(int(check_id)).exists()
        before = check._line_state()
        super().toggle_all(check_id, done)
        check._after_staff_edit(before)
        return check._checklist_payload()

    @api.model
    def _fix_cht_kind(self):
        """Dữ liệu cũ: phiếu tạo trước khi có check list CHT nhưng người làm là CHT (lịch ca chức vụ cấp 2) vẫn mang loại
        'nvbh' -> nhân viên vẫn thấy. Gán lại loại 'cht' (giữ nguyên dòng việc và kết quả đánh giá)."""
        checks = self.sudo().search([('kind', '=', 'nvbh'), ('schedule_line_id', '!=', False)])
        for kind in ('cht', 'asm'):
            todo = checks.filtered(lambda c: self._schedule_kind(c.schedule_line_id) == kind)
            if todo:
                todo.write({'kind': kind})

    @api.model
    def _clear_edited_evals(self):
        """Dữ liệu cũ: dòng đã chỉnh sửa (chờ chấm lại) mà còn kết quả đánh giá cũ thì xóa (chạy mỗi lần nâng cấp, không đổi gì nếu đã đúng)."""
        lines = self.env['store.nvbh.check.line'].sudo().search([('staff_edited', '=', True)])
        vals = {}
        for p in STEP_PREFIX:
            vals.update({p + 'eval_result': False, p + 'error_detail': False})
        todo = lines.filtered(lambda l: any(l[p + 'eval_result'] or l[p + 'error_detail'] for p in STEP_PREFIX))
        if todo:
            todo.write(vals)

    def _line_state(self):
        """Ảnh chụp (đã làm, ghi chú) của từng dòng khi phiếu đã gửi cấp trên; phiếu còn đang thực hiện thì rỗng."""
        if not self or self.state == 'draft':
            return {}
        return {l.id: (bool(l.is_done), (l.note or '').strip()) for l in self.line_ids}

    def _after_staff_edit(self, before):
        """Người thực hiện sửa check list sau khi đã gửi: dòng thay đổi tô cam, phiếu quay về chờ cấp đánh giá đầu tiên
        chấm lại (kết quả chấm cũ giữ nguyên để sửa nhanh), gửi Odoo Bot cho cấp trên kèm các dòng đã sửa."""
        self.ensure_one()
        if not before:
            return
        changed = self.line_ids.filtered(lambda l: l.id in before and before[l.id] != (bool(l.is_done), (l.note or '').strip()))
        if not changed:
            return
        chain = self._approval_chain()
        was_done = self.step_done
        # dòng đã sửa: kết quả đánh giá cũ của mọi cấp không còn hiệu lực -> xóa, cấp trên phải tích lại
        vals = {'staff_edited': True}
        for p in STEP_PREFIX:
            vals.update({p + 'eval_result': False, p + 'error_detail': False})
        changed.sudo().write(vals)
        self.sudo().write({'state': 'pending_review', 'step_done': 0, 'approved_date': False,
                           'review_sent_date': fields.Datetime.now()})
        if not chain:
            return
        users = self.env['res.users']
        for i, st in enumerate(chain, 1):
            if st['user'] and (i == 1 or i <= was_done):
                users |= st.get('users') or st['user']
        order = {l.id: n for n, l in enumerate(self.line_ids.sorted(lambda x: (x.sequence, x.id)), 1)}
        detail = Markup('<br/>').join(
            Markup('• %s — %s%s') % (l.name, 'Đã làm' if l.is_done else 'Chưa làm', (' · Ghi chú: %s' % l.note) if l.note else '')
            for l in changed.sorted(lambda x: order.get(x.id, 0)))
        bot_send(self.env, users, card('CHECKLIST ĐÃ CHỈNH SỬA — CHỜ %s ĐÁNH GIÁ LẠI' % chain[0]['code'], [
            ('Người thực hiện', self.staff_name or ''),
            ('Cửa hàng', self.store_id.display_name),
            ('Ngày', self.work_date.strftime('%d/%m/%Y') if self.work_date else ''),
            ('Số dòng đã sửa', str(len(changed))),
            ('Dòng đã sửa', Markup('<br/>') + detail),
        ], label='Mở để đánh giá lại', check_id=self.id))

    def _assert_can_execute(self):
        for check in self:
            info = check._role_info()
            if info['can_execute']:
                continue
            if info['locked_expired']:
                raise AccessError(check._expired_message())
            if info['staff_locked']:
                raise AccessError(check._staff_lock_message())
            if check.state != 'draft':
                raise AccessError(_('Checklist này đã gửi cấp trên đánh giá nên không thể sửa nữa.'))
            raise AccessError(_('Bạn không có quyền thực hiện checklist này: tài khoản chung CH_ chỉ tick cho Cấp 1 '
                                '(NVBH, NV, NT, NTTT, PT); từ Cấp 2 trở lên phải đăng nhập User cá nhân.'))

    def _checklist_payload(self):
        payload = super()._checklist_payload()
        info = self._role_info()
        steps = info['chain']
        # người đánh giá chỉ thấy các cấp từ cấp của mình trở xuống (vd. CHT không thấy cột ASM Đánh giá);
        # Quản trị / Quản lý Checklist thấy đủ mọi cấp
        user = self.env.user
        if not (user.has_group('base.group_system') or user.has_group('store_checklist.group_store_manager')):
            mine = [i for i, st in enumerate(steps) if not st['admin_only'] and (
                (st['user'] and st['user'].id == user.id) or (st.get('admin_title') and user in st['users']))]
            if mine:
                steps = steps[:mine[-1] + 1]
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
                'deadline': self._fmt_date(self._step_deadline(s['no'])) if not s['done'] else '',
                'reedit': s.get('reedit', False),
                'reedit_until': fields.Datetime.context_timestamp(
                    self.with_context(tz=self.env.user.tz or 'Asia/Ho_Chi_Minh'), s['reedit_until']).strftime('%H:%M %d/%m/%Y')
                if s.get('reedit_until') else '',
            } for s in steps],
            'staff_deadline': self._fmt_date(self._staff_deadline()),
            'staff_locked': info['staff_locked'],
            'late_code': self._late_code(),
            'lock_msg': self._expired_message() if self._late_stage() else (self._staff_lock_message() if self._staff_late() and self.state == 'draft' else ''),
            'can_execute': info['can_execute'],
            'self_reedit_until': fields.Datetime.context_timestamp(
                self.with_context(tz=self.env.user.tz or 'Asia/Ho_Chi_Minh'), info['self_reedit_until']).strftime('%H:%M %d/%m/%Y')
            if info.get('self_reedit_until') else '',
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
        to = (step.get('users') or step.get('user')) if step else False  # duyệt cuối ASM: báo mọi Admin / Admin tổng
        if not to:
            return
        bot_send(self.env, to, card('CHECKLIST CHỜ %s ĐÁNH GIÁ' % step['code'], [
            ('Người thực hiện', self.staff_name or ''),
            ('Cửa hàng', self.store_id.display_name),
            ('Ngày', self.work_date.strftime('%d/%m/%Y') if self.work_date else ''),
            ('Ca', self.shift_id.code or ''),
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
        check._stamp_staff_done()
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
        # dòng người thực hiện chưa tích "Có làm": cấp trên không đánh giá được, tự tính Không đạt (0đ)
        undone = check.line_ids.filtered(lambda l: not l.is_done)
        if undone:
            undone.write({pre + 'reviewer_id': assigned, pre + 'eval_result': 'bad', pre + 'error_detail': False})
        if step_no == 1 and check.line_ids and all(check.line_ids.mapped('eval_result')):
            check.line_ids.filtered('staff_edited').write({'staff_edited': False})
        if step.get('reedit') and step_no <= check.step_done:
            # sửa lại đánh giá đã hoàn tất: phải chấm đủ mọi đầu việc; cập nhật điểm / kết quả trong lịch sử của cấp đó
            if not all(check.line_ids.mapped(pre + 'eval_result')):
                raise UserError(_('Sửa lại đánh giá phải chấm đủ KQ đánh giá cho mọi công việc.'))
            log = check.step_log_ids.filtered(lambda s: s.step_no == step_no).sorted('id')[-1:]
            log.write({'points': check.points, 'user_id': self.env.user.id,
                       'result_summary': _('%s lỗi') % check.error_total if check.error_total else _('Không lỗi')})
            return check._checklist_payload()
        if check.line_ids and all(check.line_ids.mapped(pre + 'eval_result')):
            check._finish_step(step_no, step, info['chain'])
        return check._checklist_payload()

    def _step_prefix_for(self, code):
        """Trả về (step_no, prefix) cho cấp `code` (CHT / ASM / RSM): ưu tiên theo luồng duyệt;
        riêng ASM (đánh giá tổng theo tuần ở Đánh giá Toàn Cửa Hàng) luôn đọc cột bước 2 ('asm_')."""
        for i, st in enumerate(self._approval_chain(), 1):
            if st['code'] == code:
                return i, STEP_PREFIX[i - 1]
        if code == 'ASM':
            return 2, 'asm_'
        return None, None

    def _step_points(self, code):
        """Điểm do cấp đánh giá có mã `code` (CHT / ASM / RSM) chấm cho phiếu; None nếu phiếu không có cấp đó hoặc cấp đó chưa chấm đủ."""
        self.ensure_one()
        i, pre = self._step_prefix_for(code)
        if pre is None:
            return None
        lines = self.line_ids
        if not lines or not all(l[pre + 'eval_result'] for l in lines):
            # cấp này trễ hạn đánh giá (hệ thống đã khóa): điểm cấp đó tính 0đ
            return 0.0 if self._late_stage() == i else None
        return round(sum(eval_score(l.max_score, l[pre + 'eval_result'], count_errors(l[pre + 'error_detail'])) for l in lines), 2)

    def _step_errors(self, code):
        """Số lỗi do cấp `code` (CHT / ASM / RSM) ghi ở cột Chi tiết lỗi (mỗi dòng là một lỗi);
        None nếu phiếu không có cấp đó hoặc cấp đó chưa đánh giá dòng nào."""
        self.ensure_one()
        _i, pre = self._step_prefix_for(code)
        if pre is None:
            return None
        lines = self.line_ids
        if not any(l[pre + 'eval_result'] or l[pre + 'error_detail'] for l in lines):
            return None
        return sum(count_errors(l[pre + 'error_detail']) for l in lines)

    def _step_error_text(self, code):
        """Nội dung Chi tiết lỗi do cấp `code` (CHT / ASM / RSM) ghi nhận (mỗi lỗi một dòng);
        None nếu phiếu không có cấp đó hoặc cấp đó chưa đánh giá dòng nào."""
        self.ensure_one()
        _i, pre = self._step_prefix_for(code)
        if pre is None:
            return None
        # cùng thứ tự / STT như popup Checklist công việc (theo nhóm rồi thứ tự công việc)
        from .store_nvbh_task import TASK_GROUPS
        order = {label: n for n, (_k, label) in enumerate(TASK_GROUPS)}
        lines = self.line_ids.sorted(lambda l: (order.get(l.sub_category, len(order)), l.sequence, l.id))
        if not any(l[pre + 'eval_result'] or l[pre + 'error_detail'] for l in lines):
            return None
        out = []
        for stt, l in enumerate(lines, 1):
            for ln in (l[pre + 'error_detail'] or '').splitlines():
                if ln.strip():
                    out.append(ln.strip())  # chỉ lấy nội dung Chi tiết lỗi đúng như ô trong popup
        return chr(10).join(out)

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
        if not last and not (self.kind == 'nvbh' and chain[step_no]['code'] == 'ASM'):
            # NVBH: CHT chấm xong không nhắn ASM từng phiếu (ASM chấm gộp theo tuần ở trang Đánh giá toàn cửa hàng)
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
