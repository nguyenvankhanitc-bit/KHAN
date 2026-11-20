import base64
import calendar
import logging
import io
import re
from datetime import date

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .store_audit_staff import CHECK_MENUS
from .store_notify import SHELL_URL, bot_send


_logger = logging.getLogger(__name__)


class StoreNvbhSchedule(models.Model):
    """Lịch làm việc NVBH: 1 cửa hàng / 1 ngày, mỗi dòng gắn một nhân sự (bảng Nhân sự) với một Mã ca (Cài đặt > Mã ca)."""
    _name = 'store.nvbh.schedule'
    _description = 'Lịch xếp ca NVBH'
    _order = 'work_date desc, id desc'

    name = fields.Char(string='Mã lịch', required=True, copy=False, readonly=True, default='New')
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True)
    work_date = fields.Date(string='Ngày', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many('store.nvbh.schedule.line', 'schedule_id', string='Lịch xếp ca', copy=True)
    is_past = fields.Boolean('Lịch quá khứ', compute='_compute_is_past')  # khóa form: không sửa lịch của ngày đã qua

    @api.depends('work_date')
    def _compute_is_past(self):
        today = self.env['store.nvbh.schedule.line']._import_ref_date()
        for rec in self:
            rec.is_past = bool(rec.work_date) and rec.work_date < today

    def _guard_past(self, action):
        """Không thêm / sửa / xóa lịch ca của ngày đã qua (theo giờ Việt Nam); luồng nội bộ chạy sudo được bỏ qua."""
        if self.env.su:
            return
        today = self.env['store.nvbh.schedule.line']._import_ref_date()
        past = self.filtered(lambda r: r.work_date and r.work_date < today)
        if past:
            raise UserError('Không được %s lịch ca quá khứ (ngày %s). Chỉ được chỉnh lịch từ hôm nay trở đi.' % (
                action, ', '.join(sorted({d.strftime('%d/%m/%Y') for d in past.mapped('work_date')}))))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self._next_name(vals.get('store_id'), vals.get('work_date'))
        recs = super().create(vals_list)
        recs._guard_past('thêm')
        return recs

    def write(self, vals):
        if {'store_id', 'work_date'} & set(vals):
            self._guard_past('sửa')
        res = super().write(vals)
        if 'work_date' in vals:
            self._guard_past('chuyển sang')
        return res

    def unlink(self):
        self._guard_past('xóa')
        if not self.env.su:
            self.line_ids._guard_locked('xóa')
        return super().unlink()

    def _next_name(self, store_id, work_date):
        store = self.env['hr.store'].browse(store_id)
        day = fields.Date.to_date(work_date) or fields.Date.context_today(self)
        prefix = 'LLV/%s/%s' % (store.code or store.display_name or 'CH', day.strftime('%d%m%Y'))
        n = self.search_count([('name', '=like', prefix + '\\_%')]) + 1
        while self.search_count([('name', '=', '%s_%d' % (prefix, n))]):
            n += 1
        return '%s_%d' % (prefix, n)


class StoreNvbhScheduleLine(models.Model):
    _name = 'store.nvbh.schedule.line'
    _description = 'Dòng lịch làm việc NVBH'
    _order = 'work_date desc, schedule_id desc, sequence, id'

    schedule_id = fields.Many2one('store.nvbh.schedule', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    stt = fields.Integer(string='STT', compute='_compute_stt')
    # Họ và tên NV nhập tay (bắt buộc ở giao diện); staff_id chỉ còn để giữ dữ liệu cũ lấy từ bảng Nhân sự
    staff_name = fields.Char(string='Họ và tên NV')
    staff_id = fields.Many2one('store.audit.staff', string='Nhân sự (cũ)')
    employee_code = fields.Char(string='ID')
    position = fields.Char(string='Chức vụ', default='NVBH', help='Mã chức vụ theo file xếp ca: NVBH, NT, CHT, ASMTT, PT...')

    @api.model
    def _search(self, domain, *args, **kwargs):
        # lịch xếp ca: cùng phạm vi cửa hàng và phạm vi theo người như phiếu checklist
        today_view = self.env.context.get('store_today_shift')
        if today_view:
            # Checklist NVBH > Lịch ca hôm nay: chỉ các dòng ca của ngày hôm nay, xem cả cửa hàng (không giới hạn theo người)
            domain = [('work_date', '=', fields.Date.context_today(self))] + list(domain or [])
        rule = self.env['store.staff.view.rule']._staff_domain(CHECK_MENUS)
        if rule is not None:  # Phân quyền xem nhân sự (Công việc / Danh sách checklist NV / Quản lý & đánh giá)
            return super(StoreNvbhScheduleLine, self.sudo())._search(rule + list(domain or []), *args, **kwargs)
        scope = self.env['store.audit']._user_store_scope()
        if today_view and scope is None and self._today_store_bound():
            scope = []  # NVBH / CHT / ASM / RSM chưa được gán cửa hàng nào: không thấy lịch ca
        extra = [] if today_view else list(self.env['store.nvbh.check']._user_person_domain(False))
        if scope is not None:
            extra = [('store_id', 'in', scope)] + extra
        if extra:
            domain = extra + list(domain or [])
        return super()._search(domain, *args, **kwargs)

    TODAY_HEADERS = ['STT', 'Miền', 'Mã bộ phận', 'ID HRM', 'Họ và tên', 'Mã chức vụ', 'N (ca hôm nay)']

    @api.model
    def get_today_rows(self, mien=None, store_id=None):
        """Lịch ca hôm nay cho bộ lọc / In / Xuất Excel: các dòng ca ngày hôm nay trong phạm vi user được xem,
        lọc thêm theo Miền và / hoặc Cửa hàng (rỗng = tất cả). Trả kèm danh sách miền / cửa hàng có ca hôm nay."""
        today = fields.Date.context_today(self)
        lines = self.with_context(store_today_shift=True).search([], order='mien, store_id, sequence, id')
        mien_labels = dict(self._fields['mien']._description_selection(self.env))
        stores = lines.store_id.sorted('name')
        options = {
            'miens': [{'id': m, 'name': mien_labels.get(m, m)} for m in sorted({l.mien for l in lines if l.mien})],
            'stores': [{'id': s.id, 'name': s.display_name, 'mien': s.mien or ''} for s in stores],
        }
        if mien:
            lines = lines.filtered(lambda l: l.mien == mien)
        if store_id:
            lines = lines.filtered(lambda l: l.store_id.id == int(store_id))
        rows = [[i, mien_labels.get(l.mien, l.mien or ''), l.store_id.display_name or '', l.employee_code or '',
                 l.staff_name or '', l.position or '', l.shift_id.code or '']
                for i, l in enumerate(lines, 1)]
        scope = (mien_labels.get(mien, mien) if mien else 'Tất cả miền') + ' | ' + (
            self.env['hr.store'].sudo().browse(int(store_id)).display_name if store_id else 'Tất cả cửa hàng')
        return {
            'date': today.strftime('%d/%m/%Y'), 'headers': self.TODAY_HEADERS, 'rows': rows,
            'subtitle': 'Ngày %s | %s | %s nhân viên' % (today.strftime('%d/%m/%Y'), scope, len(rows)),
            **options,
        }

    @api.model
    def export_today_xlsx(self, mien=None, store_id=None):
        """Xuất Excel Lịch ca hôm nay theo Miền / Cửa hàng / Tất cả."""
        self.env['store.perm.rule'].check_export()
        data = self.get_today_rows(mien, store_id)
        if not data['rows']:
            raise UserError(_('Không có ca làm việc hôm nay trong phạm vi đã chọn.'))
        sheet = {'name': 'Lich ca hom nay', 'title': 'LỊCH CA HÔM NAY - %s' % data['date'], 'subtitle': data['subtitle'],
                 'headers': data['headers'], 'rows': data['rows'], 'foot': None}
        return self.env['store.nvbh.check']._xlsx_book([sheet], 'Lich_ca_%s' % data['date'].replace('/', '-'))

    # ------------------------------------------------------------------
    # Thông báo Lịch ca hôm nay cho ASM / RSM (OdooBot, chạy tự động mỗi sáng)
    # ------------------------------------------------------------------
    @api.model
    def _store_area_managers(self, store):
        """ASM (cấp 3) và RSM (cấp 4) phụ trách cửa hàng: Quản lý cửa hàng, nhân sự gắn với cửa hàng,
        rồi đi ngược Sơ đồ tổ chức (Quản lý trực tiếp) từ những người đó. Trả về hr.employee."""
        Employee = self.env['hr.employee'].sudo()
        store = store.sudo()
        base = [('checklist_store_ids', 'in', store.id), ('store_id', '=', store.id),
                ('id', 'in', store.member_ids.ids), ('id', '=', store.manager_id.id or 0)]
        if 'ma_bo_phan' in Employee._fields:
            base.append(('ma_bo_phan', '=ilike', store.code or '-'))
        found = Employee
        for emp in Employee.search(['|'] * (len(base) - 1) + base) | store.manager_id:
            node, hops = emp, 0
            while node and hops < 8:
                if node.active and node._checklist_effective_level() in (3, 4):
                    found |= node
                node, hops = node.parent_id, hops + 1
        return found

    @api.model
    def _today_shift_body(self, day, store_lines):
        """Nội dung tin: mỗi cửa hàng một bảng Họ và tên / Mã chức vụ / Ca hôm nay + nút mở ứng dụng."""
        total = sum(len(lines) for _st, lines in store_lines)
        body = Markup('<b>LỊCH CA HÔM NAY - %s</b><br/>%s cửa hàng · %s nhân viên<br/>') % (
            day.strftime('%d/%m/%Y'), len(store_lines), total)
        cell = 'border:1px solid #cbd5e1;padding:3px 8px;'
        for store, lines in store_lines:
            body += Markup('<br/><b>%s</b> (%s nhân viên)<br/><table style="border-collapse:collapse;font-size:13px;">'
                           '<tr style="background:#e0e7ff;"><th style="%s">Họ và tên</th><th style="%s">Mã chức vụ</th>'
                           '<th style="%s">Ca</th></tr>') % (store.display_name, len(lines), cell, cell, cell)
            for ln in lines:
                body += Markup('<tr><td style="%s">%s</td><td style="%s;text-align:center;">%s</td>'
                               '<td style="%s;text-align:center;font-weight:700;color:#1d4ed8;">%s</td></tr>') % (
                    cell, ln.staff_name or '', cell, ln.position or '', cell, ln.shift_id.code or '')
            body += Markup('</table>')
        return body + Markup(
            '<a href="%s" target="_self" style="display:inline-block;margin-top:10px;padding:8px 18px;'
            'background-color:#714B67;color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600;">'
            'Xem lịch ca hôm nay</a>') % SHELL_URL

    @api.model
    def send_today_shift_notify(self, force=False):
        """Gửi Lịch ca hôm nay cho ASM / RSM của từng cửa hàng có ca trong ngày (mỗi người một tin gộp các cửa hàng mình phụ trách).
        Cron chạy mỗi sáng; force=True (nút Gửi ngay) gửi lại kể cả khi hôm nay đã gửi. Trả về số người nhận."""
        if force and not (self.env.user.has_group('store_checklist.group_store_manager') or self.env.is_admin()):
            raise AccessError(_('Chỉ Quản lý mới được gửi thông báo lịch ca.'))
        params = self.env['ir.config_parameter'].sudo()
        day = fields.Date.context_today(self)
        if not force and params.get_param('store_checklist.today_shift_sent') == str(day):
            return 0
        lines = self.sudo().search([('work_date', '=', day)], order='store_id, sequence, id')
        per_user = {}
        for store in lines.store_id:
            store_lines = lines.filtered(lambda l, s=store: l.store_id == s)
            for emp in self._store_area_managers(store):
                if emp.user_id:
                    per_user.setdefault(emp.user_id, []).append((store, store_lines))
        for user, store_lines in per_user.items():
            bot_send(self.env, user, self._today_shift_body(day, store_lines))
        params.set_param('store_checklist.today_shift_sent', str(day))
        _logger.info('store_checklist: đã gửi Lịch ca %s cho %s ASM/RSM', day, len(per_user))
        return len(per_user)

    @api.model
    def _cron_send_today_shift(self):
        # cron chạy lúc 23:00 UTC: tính "hôm nay" theo giờ Việt Nam
        self.with_context(tz='Asia/Ho_Chi_Minh').send_today_shift_notify()

    @api.model
    def _today_store_bound(self):
        """True: user là NVBH / CHT / ASM / RSM (cấp 1-4) -> Lịch ca hôm nay chỉ được xem cửa hàng mình quản lý."""
        user = self.env.user
        if self.env.su or user._is_admin() or user.has_group('store_checklist.group_store_manager'):
            return False
        if getattr(user.sudo(), 'lug_data_scope', False) == 'company':
            return False
        emp = user.sudo().employee_id
        return bool(emp) and 1 <= emp._checklist_effective_level() <= 4
    work_status = fields.Char(string='Trạng thái nhân viên')
    shift_id = fields.Many2one('store.shift', string='Mã ca', required=True)
    # ô thay đổi ở lần nhập Excel gần nhất (tô màu trên lưới Lịch xếp ca); mã ca cũ để hiện khi rê chuột
    import_changed = fields.Boolean('Thay đổi ở lần nhập gần nhất', copy=False)
    import_prev_code = fields.Char('Mã ca trước khi nhập', copy=False)
    is_locked = fields.Boolean('Khóa chỉnh sửa', compute='_compute_is_locked')  # ngày đã qua / đã check list -> chỉ xem
    # thông tin phiếu mẹ để lọc / hiển thị trong danh sách
    store_id = fields.Many2one('hr.store', related='schedule_id.store_id', string='Cửa hàng', store=True, index=True)
    mien = fields.Selection(related='schedule_id.store_id.mien', string='Miền', store=True, index=True)  # lưu để group theo Miền
    work_date = fields.Date(related='schedule_id.work_date', string='Ngày', store=True, index=True)

    def init(self):
        """Dòng lịch cũ chọn nhân sự từ bảng Nhân sự -> chép họ tên / ID / chức vụ sang các ô nhập tay (chạy một lần)."""
        cr = self.env.cr
        cr.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'store_nvbh_schedule_line' "
                   "AND column_name IN ('staff_name', 'employee_code', 'position', 'staff_id')")
        if cr.fetchone()[0] < 4:
            return
        cr.execute("""
            UPDATE store_nvbh_schedule_line l
               SET staff_name = s.name, employee_code = s.employee_code, position = s.position
              FROM store_audit_staff s
             WHERE s.id = l.staff_id AND (l.staff_name IS NULL OR l.staff_name = '')
        """)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._guard_locked('thêm')
        if not self.env.context.get('schedule_import'):
            # thêm ca bằng tay (form): tô màu "ca mới" như khi nhập Excel
            lines.with_context(schedule_import=True).write({'import_changed': True, 'import_prev_code': False})
        if not self.env.context.get('no_staff_sync'):
            lines._sync_staff_from_lines()
        return lines

    # chỉ là dấu tô màu của lần nhập Excel: ghi được cả trên dòng đã khóa
    _GUARD_FREE = {'import_changed', 'import_prev_code', 'sequence'}

    @api.depends('work_date')
    def _compute_is_locked(self):
        today = self._import_ref_date()
        states = self._import_check_state(self.filtered('id'))
        for ln in self:
            ln.is_locked = bool(ln.work_date and ln.work_date < today) or states.get(ln.id) == 'locked'

    def _guard_locked(self, action):
        """Dòng lịch ngày đã qua, hoặc nhân viên đã check list / bấm Lưu / đã duyệt: không được thêm / sửa / xóa."""
        if self.env.su or not self:
            return
        today = self._import_ref_date()
        past = self.filtered(lambda l: l.work_date and l.work_date < today)
        if past:
            raise UserError('Không được %s lịch ca quá khứ (ngày %s). Chỉ được chỉnh lịch từ hôm nay trở đi.' % (
                action, ', '.join(sorted({d.strftime('%d/%m/%Y') for d in past.mapped('work_date')}))))
        states = self._import_check_state(self)
        done = self.filtered(lambda l: states.get(l.id) == 'locked')
        if done:
            raise UserError('Không được %s ca của %s: nhân viên đã check list / bấm Lưu (hoặc đã duyệt) cho ca này.' % (
                action, ', '.join('%s ngày %s' % (l.staff_name or '', l.work_date.strftime('%d/%m/%Y')) for l in done[:5])))

    def unlink(self):
        self._guard_locked('xóa')
        return super().unlink()

    def write(self, vals):
        if set(vals) - self._GUARD_FREE:
            self._guard_locked('sửa')
        # đổi Mã ca bằng tay (form): ghi lại mã ca cũ để tô màu ô trên lưới như khi nhập Excel
        track = 'shift_id' in vals and not self.env.context.get('schedule_import')
        prev = {ln.id: ln.shift_id.code or '' for ln in self} if track else {}
        res = super().write(vals)
        if track:
            for ln in self.filtered(lambda l: prev[l.id] != (l.shift_id.code or '')):
                # đổi nhiều lần: giữ mã ca ban đầu; đổi về đúng mã ca ban đầu thì bỏ tô màu
                origin = ln.import_prev_code if ln.import_changed else prev[ln.id]
                back = bool(origin) and origin == (ln.shift_id.code or '')
                super(StoreNvbhScheduleLine, ln).write({'import_changed': not back, 'import_prev_code': False if back else (origin or False)})
        if 'schedule_id' in vals:
            self._guard_locked('chuyển')
        if not self.env.context.get('no_staff_sync') and {'staff_name', 'employee_code', 'position', 'work_status'} & set(vals):
            self._sync_staff_from_lines()
        return res

    def _sync_staff_from_lines(self):
        """Nhân sự luôn lấy thông tin mới nhất từ Lịch làm việc: dòng lịch mới nhất của mỗi nhân viên (theo ngày) quyết định
        Họ tên / Chức vụ / Trạng thái trong Checklist NVBH > Nhân sự."""
        people = {}
        for ln in self.filtered(lambda l: l.store_id and (l.staff_name or '').strip()).sorted(lambda l: (l.work_date or date.min, l.id)):
            name = ln.staff_name.strip()
            emp_id = (ln.employee_code or '').strip()
            people[(ln.store_id.id, emp_id or name.casefold())] = {
                'store': ln.store_id, 'name': name, 'emp_id': emp_id, 'position': ln.position or 'NVBH',
                'work_status': (ln.work_status or '').strip()}
        if people:
            errors = []
            self.sudo()._sync_staff(people, errors)
            for e in errors:
                _logger.warning('Đồng bộ nhân sự từ lịch làm việc: %s', e)

    @api.model
    def resync_all_staff(self):
        """Đồng bộ lại toàn bộ Nhân sự từ Lịch làm việc (dùng khi cần đồng bộ dữ liệu có sẵn)."""
        self.search([])._sync_staff_from_lines()
        return True

    @api.depends('schedule_id.line_ids', 'schedule_id.line_ids.sequence')
    def _compute_stt(self):
        for rec in self:
            rows = rec.schedule_id.line_ids.sorted('sequence')
            rec.stt = (list(rows).index(rec) + 1) if rec in rows else 0

    @api.model
    def _month_range(self, month):
        """'YYYY-MM' -> (ngày đầu tháng, số ngày trong tháng)."""
        try:
            y, m = [int(x) for x in (month or '').split('-')]
            return date(y, m, 1), calendar.monthrange(y, m)[1]
        except Exception:
            raise UserError(_('Hãy chọn một tháng cụ thể ở bộ lọc "Tháng" trước khi nhập / xuất Excel.'))

    @api.model
    def get_matrix(self, domain, month):
        """Dữ liệu lưới "Xếp ca" cho màn hình: mỗi cửa hàng một dòng tiêu đề, dưới là mỗi nhân viên một dòng với Mã ca từng ngày."""
        first, ndays = self._month_range(month)
        lines = self.search(domain or [], order='store_id, sequence, id')
        states = self._import_check_state(lines)
        rows = []
        for store in lines.store_id.sorted('name'):
            rows.append({'kind': 'store', 'key': 's%s' % store.id, 'mien': store.mien or '', 'store_code': store.code or '',
                         'store_name': store.name or ''})
            people = {}
            for ln in lines.filtered(lambda l: l.store_id == store):
                key = (ln.employee_code or '').strip() or (ln.staff_name or '').strip().casefold()
                person = people.setdefault(key, {
                    'kind': 'emp', 'key': 'e%s_%s' % (store.id, len(people)), 'mien': store.mien or '',
                    'store_code': store.code or '', 'employee_code': ln.employee_code or '',
                    'staff_name': ln.staff_name or '', 'position': ln.position or '', 'work_status': ln.work_status or '', 'days': {}})
                person['days'][ln.work_date.day] = {'code': ln.shift_id.code or '', 'schedule_id': ln.schedule_id.id,
                                                    'changed': ln.import_changed, 'prev': ln.import_prev_code or '',
                                                    'locked': states.get(ln.id) == 'locked'}
            rows.extend(people.values())
        today = self._import_ref_date()
        # số ngày đầu tháng đã qua (làm mờ trên lưới): cả tháng đã qua = ndays, tháng tương lai = 0
        past_days = ndays if first.replace(day=ndays) < today else (today.day - 1 if first <= today else 0)
        return {'ndays': ndays, 'rows': rows, 'month': month, 'past_days': past_days}

    @api.model
    def export_xlsx(self, domain, month):
        """Xuất Lịch làm việc của tháng đang chọn theo mẫu "Xếp ca": mỗi nhân viên một dòng, cột N1..Nn là Mã ca từng ngày.
        File xuất ra nhập lại được."""
        self.env['store.perm.rule'].check_export()
        import xlsxwriter
        first, ndays = self._month_range(month)
        lines = self.search(domain or [], order='store_id, sequence, id')
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        sheet = book.add_worksheet('Xep ca')
        bold = book.add_format({'bold': True})
        title = book.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        head = book.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        cell = book.add_format({'border': 1})
        store_fmt = book.add_format({'border': 1, 'bold': True})
        company = self.env.company
        sheet.write(0, 0, company.name or '', bold)
        sheet.write(1, 0, ', '.join(x for x in [company.street, company.street2, company.city] if x), bold)
        ncol = 6 + ndays
        sheet.merge_range(2, 0, 2, ncol - 1, 'Xếp ca - Tháng %02d/%d' % (first.month, first.year), title)
        heads = ['Miền', 'Mã bộ phận', 'ID HRM', 'HỌ VÀ TÊN (dấu)', 'Mã chức vụ', 'TRẠNG THÁI NHÂN VIÊN'] + ['N%d' % d for d in range(1, ndays + 1)]
        for i, h in enumerate(heads):
            sheet.write(3, i, h, head)
        sheet.set_column(0, 2, 12)
        sheet.set_column(3, 3, 30)
        sheet.set_column(4, 4, 12)
        sheet.set_column(5, 5, 22)
        sheet.set_column(6, ncol - 1, 6)
        row = 4
        for store in lines.store_id:
            sheet.write(row, 0, store.mien or '', store_fmt)
            sheet.write(row, 1, store.code or store.name or '', store_fmt)
            sheet.write(row, 2, '', store_fmt)
            sheet.write(row, 3, store.name or '', store_fmt)
            for c in range(4, ncol):
                sheet.write(row, c, '', cell)
            row += 1
            people = {}
            for ln in lines.filtered(lambda l: l.store_id == store):
                key = (ln.employee_code or '').strip() or (ln.staff_name or '').strip().casefold()
                person = people.setdefault(key, {'line': ln, 'days': {}})
                person['days'][ln.work_date.day] = ln.shift_id.code or ''
            for person in people.values():
                ln = person['line']
                sheet.write(row, 0, store.mien or '', cell)
                sheet.write(row, 1, store.code or store.name or '', cell)
                sheet.write(row, 2, ln.employee_code or '', cell)
                sheet.write(row, 3, ln.staff_name or '', cell)
                sheet.write(row, 4, ln.position or '', cell)
                sheet.write(row, 5, ln.work_status or '', cell)
                for d in range(1, ndays + 1):
                    sheet.write(row, 5 + d, person['days'].get(d, ''), cell)
                row += 1
        sheet.freeze_panes(4, 4)
        book.close()
        return {'name': 'Xep_ca_%s.xlsx' % month, 'data': base64.b64encode(buf.getvalue()).decode()}

    # ------------------------------------------------------------------
    # Nhập Excel có bảo vệ ngày đã check list / đã lưu / đã duyệt
    # ------------------------------------------------------------------
    @api.model
    def _import_ref_date(self):
        """Ngày mốc của luồng nhập Excel: hôm nay theo giờ Việt Nam (+07), không phụ thuộc múi giờ user / pytz."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()

    @api.model
    def _import_check_state(self, lines):
        """Phân loại phiếu checklist của các dòng lịch: {line_id: 'locked' | 'empty'}.
        locked = đã check list (đã tick / ghi chú), đã bấm Lưu (submitted) hoặc đã gửi / đã duyệt (state khác draft);
        empty  = phiếu mới mở, chưa làm gì -> đổi ca được (phiếu được tạo lại theo ca mới)."""
        res = {}
        if not lines:
            return res
        for chk in self.env['store.nvbh.check'].sudo().search([('schedule_line_id', 'in', lines.ids)]):
            busy = chk.submitted or chk.state != 'draft' or any(l.is_done or l.note for l in chk.line_ids)
            lid = chk.schedule_line_id.id
            res[lid] = 'locked' if busy or res.get(lid) == 'locked' else 'empty'
        return res

    @api.model
    def import_xlsx(self, data, month):
        """Nhập Lịch làm việc theo mẫu "Xếp ca" cho tháng đang chọn: mỗi dòng một nhân viên (Mã bộ phận, ID HRM, Họ và tên,
        Mã chức vụ), cột N1..N31 là Mã ca từng ngày (ô trống = không xếp ca, giữ nguyên). Các cột khác (Miền, Trạng thái,
        Ngày vào làm...) và dòng tên cửa hàng được bỏ qua. Dòng lỗi được bỏ qua và báo lại.
        Bảo vệ dữ liệu theo ngày mốc (hôm nay giờ Việt Nam):
        - ngày trước ngày mốc: giữ nguyên 100%, file có sửa cũng không ghi đè / không xóa;
        - từ ngày mốc trở đi: cập nhật theo file, trừ dòng đã check list (đã tick / ghi chú), đã Lưu, đã gửi hoặc đã duyệt;
        - phiếu đã mở nhưng chưa làm gì: đổi ca thì phiếu được tạo lại theo ca mới.
        Luồng này tách riêng với hạn chỉnh sửa phiếu checklist (EDIT_WINDOW_DAYS), không dùng điều kiện đó."""
        self = self.with_context(no_staff_sync=True)
        if not self.env['store.nvbh.schedule'].has_access('create'):
            raise UserError(_('Bạn không có quyền nhập Lịch xếp ca.'))
        first, ndays = self._month_range(month)
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise UserError(_('Máy chủ chưa cài thư viện openpyxl để đọc file Excel.'))
        try:
            wb = load_workbook(io.BytesIO(base64.b64decode(data)), data_only=True, read_only=True)
            rows = list(wb.worksheets[0].iter_rows(values_only=True))
        except Exception:
            raise UserError(_('Không đọc được file. Hãy dùng file .xlsx theo mẫu Xếp ca.'))

        def txt(v):
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return ('%s' % v).strip() if v is not None else ''

        hi = next((i for i, r in enumerate(rows) if 'mã bộ phận' in [txt(c).casefold() for c in r]), None)
        if hi is None:
            raise UserError(_('Không tìm thấy dòng tiêu đề có cột "Mã bộ phận".'))
        col = {txt(c).casefold(): i for i, c in enumerate(rows[hi]) if txt(c)}
        name_col = next((i for k, i in col.items() if k.startswith('họ và tên')), None)
        if name_col is None:
            raise UserError(_('Thiếu cột "HỌ VÀ TÊN".'))
        id_col = col.get('id hrm', col.get('id'))
        status_col = next((i for k, i in col.items() if k.startswith('trạng thái')), None)
        pos_col = next((i for k, i in col.items() if k.startswith('mã chức vụ') or k == 'chức vụ'), None)
        day_cols = {}
        for k, i in col.items():
            m = re.fullmatch(r'n(\d{1,2})', k)
            if m and 1 <= int(m.group(1)) <= 31:
                day_cols[int(m.group(1))] = i
        if not day_cols:
            raise UserError(_('Không thấy các cột ngày N1, N2, ...'))

        def cell(r, i):
            return txt(r[i]) if i is not None and i < len(r) else ''

        stores = {}
        for st in self.env['hr.store'].search([]):
            for k in (st.code, st.name):
                if k:
                    stores.setdefault(k.strip().casefold(), st)
        shifts = {sh.code.strip().casefold(): sh for sh in self.env['store.shift'].search([]) if sh.code}
        Schedule = self.env['store.nvbh.schedule']
        schedules = {}
        created = updated = unchanged = 0
        changed = {}  # line id -> mã ca trước khi nhập ('' = ô mới)
        skipped_past = skipped_locked = 0
        ref = self._import_ref_date()  # vd. 20/11/2026: 01-19/11 giữ nguyên, 20/11 chỉ cập nhật nếu chưa check list, 21/11+ cập nhật
        errors = []
        store = None
        kept = self.browse()
        people = {}
        file_stores = self.env['hr.store']
        for n, r in enumerate(rows[hi + 1:], hi + 2):
            code = cell(r, col['mã bộ phận'])
            emp_id = cell(r, id_col)
            name = cell(r, name_col)
            cells = {d: cell(r, i) for d, i in day_cols.items() if d <= ndays and cell(r, i)}
            if code:
                store = stores.get(code.casefold())
                if not store:
                    errors.append('Dòng %s: không tìm thấy cửa hàng "%s"' % (n, code))
                    continue
            if not emp_id and not cells:
                continue  # dòng tên cửa hàng / dòng trống
            if store is None:
                errors.append('Dòng %s: chưa có Mã bộ phận' % n)
                continue
            if not name:
                errors.append('Dòng %s: thiếu Họ và tên' % n)
                continue
            pos = cell(r, pos_col).upper()
            status = cell(r, status_col)
            people[(store.id, emp_id or name.casefold())] = {
                'store': store, 'name': name, 'emp_id': emp_id, 'position': pos or 'NVBH', 'work_status': status}
            for d, sc in sorted(cells.items()):
                shift = shifts.get(sc.casefold())
                if not shift:
                    errors.append('Dòng %s, N%s: Mã ca "%s" không tồn tại' % (n, d, sc))
                    continue
                day = first.replace(day=d)
                if day < ref:
                    skipped_past += 1  # ngày đã qua: giữ nguyên dữ liệu trên hệ thống, file sửa cũng không ghi đè
                    continue
                vals = {'staff_name': name, 'employee_code': emp_id, 'shift_id': shift.id}
                if pos:
                    vals['position'] = pos
                if status:
                    vals['work_status'] = status
                try:
                    with self.env.cr.savepoint():
                        key = (store.id, day)
                        if key not in schedules:
                            schedules[key] = Schedule.search([('store_id', '=', store.id), ('work_date', '=', day)], limit=1) \
                                or Schedule.create({'store_id': store.id, 'work_date': day})
                        sch = schedules[key]
                        line = sch.line_ids.filtered(
                            lambda l: (emp_id and l.employee_code == emp_id) or (not emp_id and (l.staff_name or '').casefold() == name.casefold()))[:1]
                        if line:
                            chk_state = self._import_check_state(line).get(line.id)
                            if chk_state == 'locked':
                                skipped_locked += 1  # đã check list / đã lưu / đã duyệt: không cập nhật
                                kept |= line
                                file_stores |= store
                                continue
                            if line.shift_id == shift and all(
                                    (line[f] or '') == (v or '') for f, v in vals.items() if f != 'shift_id'):
                                unchanged += 1
                            else:
                                if chk_state == 'empty' and line.shift_id != shift:
                                    # phiếu mở sẵn nhưng chưa làm: xóa để tạo lại theo công việc của ca mới
                                    self.env['store.nvbh.check'].sudo().search([('schedule_line_id', '=', line.id)]).unlink()
                                prev_code = line.shift_id.code or ''
                                line.with_context(schedule_import=True).write(vals)
                                updated += 1
                                if prev_code != (shift.code or ''):
                                    changed[line.id] = prev_code
                        else:
                            vals['sequence'] = max(sch.line_ids.mapped('sequence') or [0]) + 10
                            vals['schedule_id'] = sch.id
                            line = self.with_context(schedule_import=True).create(vals)
                            created += 1
                            changed[line.id] = ''
                        kept |= line
                        file_stores |= store
                except Exception as e:  # lỗi quyền / dữ liệu: bỏ qua ô và báo lại
                    errors.append('Dòng %s, N%s: %s' % (n, d, getattr(e, 'args', [e])[0]))
        # File là lịch mới nhất: với các cửa hàng có trong file, xóa các dòng lịch không còn trong file —
        # chỉ từ ngày mốc trở đi và chỉ dòng chưa check list / lưu / duyệt (ngày đã qua, ngày đã khóa giữ nguyên)
        removed = 0
        removed_rows = []
        last = first.replace(day=ndays)
        if file_stores and last >= ref:
            old = self.search([('store_id', 'in', file_stores.ids), ('work_date', '>=', max(first, ref)), ('work_date', '<=', last)]) - kept
            states = self._import_check_state(old)
            locked_old = old.filtered(lambda l: states.get(l.id) == 'locked')
            skipped_locked += len(locked_old)
            old -= locked_old
            self.env['store.nvbh.check'].sudo().search([('schedule_line_id', 'in', old.ids)]).unlink()  # phiếu rỗng của dòng bị xóa
            schedules_touched = old.schedule_id
            removed = len(old)
            removed_rows = [{'kind': 'removed', 'store': l.store_id.code or l.store_id.name or '', 'name': l.staff_name or '',
                             'date': l.work_date.strftime('%d/%m/%Y'), 'sort': (l.store_id.code or '', l.staff_name or '', l.work_date),
                             'old': l.shift_id.code or '', 'new': ''} for l in old]
            old.unlink()
            schedules_touched.filtered(lambda sc: not sc.line_ids).unlink()
        # tô màu ô: chỉ giữ dấu của lần nhập này (bỏ dấu của lần nhập trước) trong tháng / cửa hàng của file
        if file_stores:
            self.sudo().search([('store_id', 'in', file_stores.ids), ('work_date', '>=', first), ('work_date', '<=', last),
                                ('import_changed', '=', True), ('id', 'not in', list(changed))]).write(
                {'import_changed': False, 'import_prev_code': False})
        details = list(removed_rows)
        for line in self.sudo().browse(list(changed)).exists():
            line.write({'import_changed': True, 'import_prev_code': changed[line.id] or False})
            details.append({'kind': 'changed' if changed[line.id] else 'new', 'store': line.store_id.code or line.store_id.name or '',
                            'name': line.staff_name or '', 'date': line.work_date.strftime('%d/%m/%Y'),
                            'sort': (line.store_id.code or '', line.staff_name or '', line.work_date),
                            'old': changed[line.id], 'new': line.shift_id.code or ''})
        details.sort(key=lambda r: r.pop('sort'))
        staff_new, staff_upd = self._sync_staff(people, errors)
        return {'created': created, 'updated': updated, 'unchanged': unchanged, 'removed': removed,
                'skipped_past': skipped_past, 'skipped_locked': skipped_locked, 'ref_date': ref.strftime('%d/%m/%Y'),
                'staff_created': staff_new, 'staff_updated': staff_upd,
                'details': details[:1000], 'detail_count': len(details),
                'errors': errors[:20], 'error_count': len(errors)}

    @api.model
    def preview_import_xlsx(self, data, month):
        """Xem trước file nhập: chạy đúng luồng import_xlsx trong savepoint rồi hoàn tác toàn bộ, trả về số liệu + danh sách ô
        sẽ thay đổi. Chỉ khi user bấm Lưu (gọi import_xlsx) dữ liệu mới được ghi."""
        class _Rollback(Exception):
            pass
        res = {}
        try:
            with self.env.cr.savepoint():
                res = self.import_xlsx(data, month)
                raise _Rollback()
        except _Rollback:
            pass
        finally:
            self.env.invalidate_all()
        res['preview'] = True
        return res

    @api.model
    def _sync_staff(self, people, errors):
        """Đồng bộ Checklist NVBH > Nhân sự theo lịch ca vừa nhập: nhân viên (cửa hàng + ID HRM, hoặc họ tên) đã có thì cập nhật
        Họ tên / Chức vụ / Trạng thái, chưa có thì thêm vào phiếu nhân sự của cửa hàng (tự tạo phiếu nếu cửa hàng chưa có)."""
        Staff = self.env['store.audit.staff']
        Audit = self.env['store.audit'].with_context(store_audit_type='nvbh', staff_form=True)
        audits = {}
        created = updated = 0
        for p in people.values():
            store = p['store']
            status = p['work_status']
            inactive = any(w in status.casefold() for w in ('nghỉ', 'ngừng'))
            vals = {'name': p['name'], 'position': p['position'], 'employee_code': p['emp_id'], 'work_status': status,
                    'staff_state': 'inactive' if inactive else 'active'}
            try:
                with self.env.cr.savepoint():
                    who = [('employee_code', '=', p['emp_id'])] if p['emp_id'] else [('name', '=ilike', p['name'])]
                    staff = Staff.search([('store_id', '=', store.id), ('audit_id.audit_type', '=', 'nvbh')] + who, limit=1)
                    if staff:
                        upd = {k: v for k, v in vals.items() if v or k == 'name'}
                        if not status:
                            upd.pop('staff_state', None)
                        staff.write(upd)
                        updated += 1
                    else:
                        if store.id not in audits:
                            audits[store.id] = Audit.search([('store_id', '=', store.id), ('audit_type', '=', 'nvbh')], order='id', limit=1) \
                                or Audit.create({'store_id': store.id})
                        Staff.create(dict(vals, audit_id=audits[store.id].id))
                        created += 1
            except Exception as e:
                errors.append('Nhân sự %s: %s' % (p['name'], getattr(e, 'args', [e])[0]))
        return created, updated
