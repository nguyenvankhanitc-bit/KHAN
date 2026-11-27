from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .store_nvbh_task import TASK_GROUPS

# Phiếu đánh giá năng suất & tính KPI cá nhân (thang 100 điểm)
# Tiêu chí 1: Checklist 5 nhóm nghiệp vụ (tổng 40đ); tiêu chí 2-5 lấy theo trọng số dưới đây
KPI_GROUPS = [  # (mã nhóm công việc, tên hiển thị, trọng số %, chỉ tiêu chuẩn %)
    ('I', 'Nhóm I: Trang thiết bị, vệ sinh, mở/đóng cửa', 7.0, 95.0),
    ('II', 'Nhóm II: Hàng hóa, trưng bày, tem giá, kho', 12.0, 95.0),
    ('III', 'Nhóm III: Tác phong, đồng phục, tư vấn bán hàng', 10.5, 95.0),
    ('IV', 'Nhóm IV: Email, bàn giao ca, chứng từ, nộp tiền', 6.5, 95.0),
    ('V', 'Nhóm V: Media, TV/LED, báo cáo Lark, FB/GGB', 4.0, 95.0),
    ]
W_COMPLETE = 15.0   # 2. Tỷ lệ hoàn thành đầu việc
W_DISCIPLINE = 15.0  # 3. Kỷ luật vận hành & không phát sinh lỗi vi phạm
W_SALES = 20.0      # 4. Hoàn thành chỉ tiêu doanh số (nhập tay)
W_ATTITUDE = 10.0   # 5. Thái độ phục vụ & phối hợp đội nhóm (nhập tay)
ERROR_PENALTY_PCT = 10.0  # mỗi lỗi vi phạm trừ 10% điểm của tiêu chí kỷ luật
# xếp loại KPI tháng: (điểm tối thiểu, tên, hệ số thưởng %)
KPI_RANKS = [(95.0, 'HẠNG A - XUẤT SẮC', 120), (85.0, 'HẠNG B - TỐT', 100), (75.0, 'HẠNG C - ĐẠT', 80), (0.0, 'HẠNG D - CHƯA ĐẠT', 0)]

# Hai báo cáo dùng chung bộ máy tính: 'kpi' (phiếu KPI cá nhân, có doanh số & thái độ nhập tay) và
# 'productivity' (báo cáo năng suất theo tiêu chí công việc, tính tự động 100% từ checklist)
PROFILES = {
    'kpi': {
        'groups': KPI_GROUPS, 'w_complete': W_COMPLETE, 'w_discipline': W_DISCIPLINE, 'manual': True, 'ranks': KPI_RANKS,
        'group_prefix': 'Checklist ',
        'complete_title': 'Tỷ lệ hoàn thành đầu việc được giao trong các ca đã làm', 'complete_source': 'Tự động Odoo',
        'discipline_title': 'Kỷ luật vận hành & Không phát sinh lỗi vi phạm / trễ hạn', 'discipline_source': 'Biên bản lỗi Odoo',
        'discipline_note': 'lỗi vi phạm / trễ hạn',
        'labels': {
            'title': 'PHIẾU ĐÁNH GIÁ NĂNG SUẤT & TÍNH KPI CÁ NHÂN', 'subtitle_extra': '',
            'col_first': 'Tiêu chí đánh giá năng suất & KPI', 'col_source': 'Nguồn dữ liệu / Phúc tra', 'col_kpi': 'ĐIỂM KPI QUY ĐỔI',
            'sub_label': 'CỘNG NHÓM 1: CHẤT LƯỢNG THỰC HIỆN CHECKLIST (5 NHÓM NGHIỆP VỤ)',
            'total_label': 'TỔNG ĐIỂM KPI THÁNG %s (THANG %d ĐIỂM)',
            'rank_label': 'XẾP LOẠI NĂNG SUẤT & KPI THÁNG', 'bonus_label': 'HỆ SỐ HƯỞNG QUỸ THƯỞNG KPI CÁ NHÂN (%)',
            'status_label': 'Trạng thái phiếu', 'file': 'Phieu_KPI_NVBH', 'show_bonus': True,
            'total_note': 'Số liệu lấy từ Bảng checklist Tổng; tự động liên kết sang Bảng So Sánh Tổng Thể',
        },
    },
    'productivity': {
        'groups': [
            ('I', 'Nhóm I: Trang thiết bị, vệ sinh, mở/đóng cửa, tài sản', 12.2, 95.0),
            ('II', 'Nhóm II: Hàng hóa, trưng bày, bảng sale, tem giá, kho', 21.0, 95.0),
            ('III', 'Nhóm III: Chấm công, đồng phục, tác phong, tư vấn bán hàng', 18.4, 95.0),
            ('IV', 'Nhóm IV: Email, bàn giao ca, chứng từ, đối chiếu công nợ, nộp tiền', 11.4, 95.0),
            ('V', 'Nhóm V: Media, TV/LED, báo cáo Lark, trình chiếu TTTM, FB/GGB', 7.0, 95.0),
        ],
        'w_complete': 15.0, 'w_discipline': 15.0, 'manual': False,
        'ranks': [(95.0, 'HẠNG A - XUẤT SẮC', 120), (85.0, 'HẠNG B - ĐẠT TỐT', 100), (75.0, 'HẠNG C - ĐẠT', 80), (0.0, 'HẠNG D - CHƯA ĐẠT', 0)],
        'group_prefix': '',
        'complete_title': 'Trụ cột 2: Tỷ lệ hoàn thành đầy đủ đầu việc được giao trong ca', 'complete_source': 'Tự động Odoo Checklist',
        'discipline_title': 'Trụ cột 3: Kỷ luật vận hành & Điểm hậu kiểm phòng ban (Không lỗi)', 'discipline_source': 'Hậu kiểm ADMIN / KHO / MKT / KTDT',
        'discipline_note': 'lỗi vi phạm / hậu kiểm phòng ban (ADMIN, KHO, MKT, KTDT)',
        'labels': {
            'title': 'BÁO CÁO ĐÁNH GIÁ NĂNG SUẤT THEO TIÊU CHÍ CÔNG VIỆC', 'subtitle_extra': 'Tính tự động 100% từ Checklist',
            'col_first': 'Tiêu chí đánh giá năng suất theo công việc Checklist', 'col_source': 'Bộ phận phúc tra / Nguồn dữ liệu',
            'col_kpi': 'ĐIỂM NĂNG SUẤT QUY ĐỔI',
            'sub_label': 'CỘNG TRỤ CỘT 1: CHẤT LƯỢNG THỰC HIỆN 5 NHÓM CÔNG VIỆC (TỔNG 70 ĐIỂM)',
            'total_label': 'TỔNG ĐIỂM NĂNG SUẤT CÔNG VIỆC THÁNG %s (THANG %d ĐIỂM)',
            'rank_label': 'XẾP LOẠI NĂNG SUẤT CÔNG VIỆC THÁNG', 'bonus_label': 'HỆ SỐ HƯỞNG THƯỞNG VẬN HÀNH / CHUYÊN CẦN (%)',
            'status_label': 'Trạng thái dữ liệu', 'file': 'BC_Nang_suat_NVBH', 'show_bonus': False,
            'total_note': 'Số liệu lấy từ Bảng checklist Tổng; tự động 100% từ Checklist',
        },
    },
}


class StoreNvbhKpiInput(models.Model):
    """Dữ liệu nhập tay cho phiếu KPI cá nhân: % hoàn thành doanh số (POS) và điểm thái độ phục vụ, theo tháng."""
    _name = 'store.nvbh.kpi.input'
    _description = 'Nhập tay KPI cá nhân NVBH'
    _order = 'month desc, id desc'

    month = fields.Char(string='Tháng', required=True, index=True, help='Dạng YYYY-MM')
    store_id = fields.Many2one('hr.store', string='Cửa hàng', required=True, index=True)
    staff_name = fields.Char(string='Nhân viên', required=True, index=True)
    sales_pct = fields.Float(string='% hoàn thành doanh số')
    sales_note = fields.Char(string='Ghi chú doanh số')
    attitude_pct = fields.Float(string='% thái độ phục vụ')
    attitude_note = fields.Char(string='Ghi chú thái độ')
    has_sales = fields.Boolean(string='Đã nhập doanh số')
    has_attitude = fields.Boolean(string='Đã nhập thái độ')

    _sql_constraints = [('kpi_input_uniq', 'unique(month, store_id, staff_name)', 'Mỗi nhân viên chỉ có một phiếu nhập tay mỗi tháng.')]


def _vn(n, digits=1):
    return ('%.*f' % (digits, n)).replace('.', ',')


def _norm_grp(s):
    return ' '.join((s or '').replace('–', '-').replace('—', '-').split()).casefold()


class StoreNvbhCheckKpi(models.Model):
    _inherit = 'store.nvbh.check'

    @api.model
    def get_kpi_staff(self, month=None, store_id=None, mien=None):
        """Nhân viên có lịch làm việc hoặc checklist trong tháng (của cửa hàng) để chọn lập phiếu KPI."""
        start, end, _days = self._month_range(month)
        dom = [('work_date', '>=', start), ('work_date', '<', end)]
        if store_id:
            dom.append(('store_id', '=', int(store_id)))
        elif mien:
            dom.append(('store_id.mien', '=', mien))
        out = {}

        def add(name, code):
            name = (name or '').strip()
            if name:
                cur = out.setdefault(name.casefold(), {'name': name, 'code': ''})
                cur['code'] = cur['code'] or code or ''

        for line in self.env['store.nvbh.schedule.line'].search(dom):
            add(line.staff_name, line.employee_code)
        for chk in self.search(dom):
            add(chk.staff_name, chk.schedule_line_id.employee_code)
        return sorted(out.values(), key=lambda o: o['name'])

    @api.model
    def _dynamic_kpi_groups(self, profile='kpi'):
        """Lấy danh sách nhóm công việc hiện tại từ Cài đặt > Danh sách công việc NVBH (store.nvbh.task.group),
        tự động phân bổ trọng số (40đ cho KPI / 70đ cho Năng suất) tỷ lệ thuận theo tổng điểm chuẩn của từng nhóm.
        Mỗi khi thay đổi nhóm hoặc điểm chuẩn công việc ở Cài đặt, mọi báo cáo sẽ tự động cập nhật theo."""
        cache = self.env.cr.cache.setdefault('store_dyn_kpi_groups', {})
        if profile in cache:
            return cache[profile]
        prof = PROFILES.get(profile) or PROFILES['kpi']
        total_w = round(sum(g[2] for g in prof['groups']), 1)
        groups = self.env['store.nvbh.task.group'].sudo().search([], order='sequence, id')
        tasks = self.env['store.nvbh.task'].sudo().search([('group_id', 'in', groups.ids)])
        by_grp = {}
        for t in tasks:
            by_grp[t.group_id.id] = by_grp.get(t.group_id.id, 0) + (t.score or 1)
        scored = [(g.name, by_grp[g.id]) for g in groups if g.id in by_grp]
        if not scored:
            labels = dict(TASK_GROUPS)
            out = [(labels.get(c, t), t, w, tg) for c, t, w, tg in prof['groups']]
            cache[profile] = out
            return out
        total_pts = sum(p for _n, p in scored) or 1.0
        out = []
        acc = 0.0
        for i, (gname, pts) in enumerate(scored):
            if i == len(scored) - 1:
                w = round(max(total_w - acc, 0.0), 1)
            else:
                w = round(total_w * pts / total_pts, 1)
                acc = round(acc + w, 1)
            out.append((gname, gname, w, 95.0))
        cache[profile] = out
        return out

    @api.model
    def get_kpi_report(self, month=None, store_id=None, staff_name=None, profile='kpi'):
        """Phiếu đánh giá năng suất & tính KPI cá nhân của một nhân viên trong tháng."""
        prof = PROFILES.get(profile) or PROFILES['kpi']
        groups_cfg = self._dynamic_kpi_groups(profile)
        labels_cfg = dict(prof['labels'])
        n_grp = len(groups_cfg)
        labels_cfg['sub_label'] = (
            'CỘNG NHÓM 1: CHẤT LƯỢNG THỰC HIỆN CHECKLIST (%d NHÓM NGHIỆP VỤ)' % n_grp
            if profile == 'kpi' else
            'CỘNG TRỤ CỘT 1: CHẤT LƯỢNG THỰC HIỆN %d NHÓM CÔNG VIỆC (TỔNG 70 ĐIỂM)' % n_grp
        )
        start, end, _days = self._month_range(month)
        name = (staff_name or '').strip()
        if not name:
            return False
        mkey = start.strftime('%Y-%m')
        dom = [('work_date', '>=', start), ('work_date', '<', end), ('staff_name', '=ilike', name)]
        if store_id:
            dom.append(('store_id', '=', int(store_id)))
        checks = self.search(dom, order='work_date, id')
        sched = self.env['store.nvbh.schedule.line'].search(dom)
        store = checks[:1].store_id or sched[:1].store_id or (self.env['hr.store'].browse(int(store_id)) if store_id else self.env['hr.store'])
        code = next((l.employee_code for l in sched if l.employee_code), '') or next((c.schedule_line_id.employee_code for c in checks if c.schedule_line_id.employee_code), '')

        # Số liệu lấy từ chính Bảng checklist Tổng (get_done_monthly) để hai bảng luôn ra cùng số
        monthly = self.get_done_monthly(mkey, name, store.id or (int(store_id) if store_id else False))
        tot = monthly['total'] or {}
        evaluated = self.browse([r['id'] for r in monthly['rows'] if r.get('evaluated') and r.get('id')])
        lines = evaluated.mapped('line_ids')
        n_sched = len({l.work_date for l in sched}) or tot.get('days', 0)
        total_jobs = tot.get('total', 0)
        done_jobs = tot.get('done', 0)
        pts = tot.get('points', 0.0)
        max_pts = tot.get('max_points', 0.0)
        errors = tot.get('errors', 0)
        productivity = tot.get('pct', 0.0)
        complete_pct = 100.0 * done_jobs / total_jobs if total_jobs else 0.0
        avg_per_shift = tot.get('avg_points') or 0.0
        saved = evaluated  # ca đã check list & đánh giá đủ
        n_days = tot.get('days', 0)

        crit = []
        kpi_checklist = 0.0
        for code_g, title, weight, target in groups_cfg:
            target_key = _norm_grp(code_g)
            glines = lines.filtered(lambda l, k=target_key: _norm_grp(l.sub_category) == k)
            g_max = sum(glines.mapped('max_score'))
            g_pts = sum(glines.mapped('actual_score'))
            pct = 100.0 * g_pts / g_max if g_max else 0.0
            kpi = round(weight * round(pct, 1) / 100.0, 2)  # tính trên tỷ lệ đã làm tròn 1 số lẻ như hiển thị
            kpi_checklist += kpi
            n_tasks = len({l.task_id.id or l.name for l in glines})
            lost = []
            for l in glines:
                if (l.actual_score or 0.0) < (l.max_score or 0.0):
                    nm = '%s (%s)' % (l.name, l.check_id.work_date.strftime('%d/%m'))
                    if nm not in lost:
                        lost.append(nm)
            if not g_max:
                note = 'Chưa có dữ liệu đã đánh giá trong kỳ'
            elif pct >= 99.995:
                note = 'Đạt tuyệt đối 100%% - %s' % title.split(': ', 1)[-1]
            else:
                note = 'Đạt %s%%' % _vn(pct) + (' (trừ: %s%s)' % (', '.join(lost[:3]), '…' if len(lost) > 3 else '') if lost else '')
            sources = sorted({(c or '').strip() for c in glines.mapped('controller') if c})
            crit.append({
                'no': '1.%d' % (len(crit) + 1), 'title': prof['group_prefix'] + '%s (%d việc · %s/%sđ)' % (title, n_tasks, _vn(g_pts, 0 if g_pts == int(g_pts) else 1), _vn(g_max, 0 if g_max == int(g_max) else 1)),
                'source': ' / '.join(sources) or 'CHT', 'weight': weight, 'max': weight, 'pct': round(pct, 1),
                'kpi': kpi, 'target': '≥ %s%%' % _vn(target), 'note': note, 'group': True,
            })
        kpi_checklist = round(kpi_checklist, 2)
        g_weight = sum(g[2] for g in groups_cfg)
        sub = {
            'weight': g_weight, 'max': g_weight, 'kpi': kpi_checklist,
            'pct': round(100.0 * kpi_checklist / g_weight, 1), 'target': '≥ %s đ' % _vn(g_weight * 0.95, 2),
            'note': ('Tổng điểm quy đổi từ %d đầu việc Checklist vận hành' if profile == 'kpi' else 'Quy đổi tỷ trọng chuẩn từ %d đầu việc Checklist') % len({l.task_id.id or l.name for l in lines}),
        }

        manual = self.env['store.nvbh.kpi.input'].search([('month', '=', mkey), ('store_id', '=', store.id), ('staff_name', '=ilike', name)], limit=1)
        discipline_pct = max(0.0, 100.0 - ERROR_PENALTY_PCT * errors) if n_days else 0.0
        rows2 = [
            {'no': '2', 'title': prof['complete_title'], 'source': prof['complete_source'], 'weight': prof['w_complete'],
             'pct': round(complete_pct, 1), 'note': 'Hoàn thành %d/%d đầu việc được giao trong %d ca thực tế' % (done_jobs, total_jobs, n_days)},
            {'no': '3', 'title': prof['discipline_title'], 'source': prof['discipline_source'], 'weight': prof['w_discipline'],
             'pct': round(discipline_pct, 1), 'extra': '%d lỗi' % errors,
             'note': ('%d %s trong kỳ (mỗi lỗi trừ %s%%)' % (errors, prof['discipline_note'], '%g' % ERROR_PENALTY_PCT)) if errors else '0 %s trong kỳ' % prof['discipline_note']},
            {'no': '4', 'title': 'Hoàn thành chỉ tiêu doanh số cửa hàng / hỗ trợ bán hàng', 'source': 'Dữ liệu POS (nhập tay)', 'weight': W_SALES,
             'pct': round(manual.sales_pct, 1) if manual.has_sales else None, 'manual': 'sales', 'note': manual.sales_note or ('' if manual.has_sales else 'Chưa nhập')},
            {'no': '5', 'title': 'Thái độ phục vụ khách hàng & Phối hợp đội nhóm', 'source': 'Quản lý chấm (nhập tay)', 'weight': W_ATTITUDE,
             'pct': round(manual.attitude_pct, 1) if manual.has_attitude else None, 'manual': 'attitude', 'note': manual.attitude_note or ('' if manual.has_attitude else 'Chưa nhập')},
        ]
        if not prof['manual']:
            rows2 = rows2[:2]
        for r in rows2:
            r['max'] = r['weight']
            r['kpi'] = round(r['weight'] * (r['pct'] or 0.0) / 100.0, 2)
            r['target'] = '%s%%' % _vn(100.0, 2).rstrip('0').rstrip(',') if r['no'] in ('2', '3') else ''
        total_kpi = round(kpi_checklist + sum(r['kpi'] for r in rows2), 2)
        total_weight = sub['weight'] + sum(r['weight'] for r in rows2)
        rank = next(r for r in prof['ranks'] if total_kpi >= r[0])

        # cấp đánh giá: người chấm bước 2 (ASM) gần nhất
        asm = next((l.asm_reviewer_id for c in reversed(list(evaluated)) for l in c.line_ids if l.asm_reviewer_id), self.env['res.users'])
        today = fields.Date.context_today(self)
        return {
            'month': mkey, 'month_label': start.strftime('%m/%Y'), 'store': store.display_name or '', 'store_id': store.id or 0,
            'staff': name, 'code': code or '', 'asm': asm.name or '',
            'summary': {
                'shifts_pct': round(100.0 * tot.get('valid', 0) / n_sched, 1) if n_sched else 0.0, 'jobs_pct': round(complete_pct, 1),
                'shifts': '%d/%d ca' % (tot.get('valid', 0), n_sched), 'jobs': '%d/%d việc' % (done_jobs, total_jobs),
                'complete': _vn(complete_pct) + '%', 'points': '%s/%s đ' % (_vn(pts, 0), _vn(max_pts, 0)),
                'productivity': _vn(productivity) + '%', 'errors': errors, 'avg': _vn(avg_per_shift),
                'status': ('Chờ chốt cuối tháng' if end > today else 'Đã chốt') if profile == 'kpi' else 'Tự động (Real-time)',
            },
            'groups': crit, 'sub': sub, 'others': rows2,
            'total': {'weight': total_weight, 'max': total_weight, 'kpi': total_kpi, 'pct': round(100.0 * total_kpi / total_weight, 1) if total_weight else 0.0,
                      'target': '%s đ' % _vn(total_weight, 2), 'note': labels_cfg['total_note']},
            'rank': rank[1], 'bonus': rank[2], 'profile': profile, 'labels': labels_cfg, 'manual': prof['manual'],
        }

    @api.model
    def get_kpi_overview(self, month=None, store_id=None, mien=None):
        """Bảng So Sánh Tổng Thể: KPI tháng của toàn bộ nhân viên (xếp hạng theo tổng điểm KPI giảm dần)."""
        rows = []
        for o in self.get_kpi_staff(month, store_id, mien):
            d = self.get_kpi_report(month, store_id, o['name'])
            if not d:
                continue
            other = {r['no']: r for r in d['others']}
            rows.append({
                'name': d['staff'], 'code': d['code'], 'store': d['store'], 'shifts': d['summary']['shifts'], 'jobs': d['summary']['jobs'],
                'productivity': d['summary']['productivity'], 'errors': d['summary']['errors'],
                'kpi_checklist': d['sub']['kpi'], 'kpi_complete': other['2']['kpi'], 'kpi_discipline': other['3']['kpi'],
                'kpi_sales': other['4']['kpi'], 'kpi_attitude': other['5']['kpi'], 'kpi_total': d['total']['kpi'],
                'rank': d['rank'], 'bonus': d['bonus'],
            })
        rows.sort(key=lambda r: (-r['kpi_total'], r['name']))
        for i, r in enumerate(rows, 1):
            r['stt'] = i
        start, _end, _d = self._month_range(month)
        return {'month_label': start.strftime('%m/%Y'), 'rows': rows}

    @api.model
    def export_kpi_overview_xlsx(self, month=None, store_id=None, mien=None, stores=None):
        """Xuất Bảng So Sánh Tổng Thể; `stores` = tên các cửa hàng được chọn, mỗi cửa hàng một sheet."""
        self.env['store.perm.rule'].check_export()
        data = self.get_kpi_overview(month, store_id, mien)
        if stores:
            data['rows'] = [r for r in data['rows'] if r['store'] in stores]
        if not data['rows']:
            raise UserError(_('Không có dữ liệu để xuất.'))
        headers = ['Hạng', 'Nhân viên', 'Mã NV', 'Cửa hàng', 'Ca hoàn thành / Lịch', 'Việc đã làm / Giao', 'Năng suất Checklist', 'Số lỗi',
                   'KPI Checklist (40)', 'KPI Hoàn thành việc (15)', 'KPI Kỷ luật (15)', 'KPI Doanh số (20)', 'KPI Thái độ (10)', 'TỔNG KPI (100)',
                   'Xếp loại', 'Hệ số thưởng (%)']
        sheets, used = [], set()
        for store in sorted({r['store'] for r in data['rows']}):  # mỗi cửa hàng một sheet, hạng tính trong từng cửa hàng
            grp = [r for r in data['rows'] if r['store'] == store]
            rows = [[i, r['name'], r['code'] or '-', r['store'], r['shifts'], r['jobs'], r['productivity'], r['errors'], r['kpi_checklist'],
                     r['kpi_complete'], r['kpi_discipline'], r['kpi_sales'], r['kpi_attitude'], r['kpi_total'], r['rank'], r['bonus']]
                    for i, r in enumerate(grp, 1)]
            n = len(grp)
            foot = ['', 'TRUNG BÌNH (%d nhân viên)' % n, '', '', '', '', '', '', *[round(sum(r[k] for r in grp) / n, 2) for k in (
                'kpi_checklist', 'kpi_complete', 'kpi_discipline', 'kpi_sales', 'kpi_attitude', 'kpi_total')], '', '']
            name = ''.join(ch for ch in (store or 'Khac') if ch not in '[]:*?/\\')[:31] or 'Khac'
            base, k = name, 2
            while name.lower() in used:
                name = '%s %d' % (base[:28], k)
                k += 1
            used.add(name.lower())
            sheets.append({'name': name, 'title': 'BẢNG SO SÁNH TỔNG THỂ KPI NHÂN VIÊN BÁN HÀNG - CỬA HÀNG %s' % (store or '-'),
                           'subtitle': 'Tháng %s' % data['month_label'], 'headers': headers, 'rows': rows, 'foot': foot})
        return self._xlsx_book(sheets, 'Bang_so_sanh_tong_the')

    @api.model
    def save_kpi_input(self, month, store_id, staff_name, field, pct, note=''):
        """Lưu số nhập tay của tiêu chí 4 (doanh số) hoặc 5 (thái độ) - chỉ Quản lý."""
        if not self.env.user.has_group('store_checklist.group_store_manager'):
            raise UserError(_('Chỉ Quản lý mới được nhập số liệu KPI.'))
        if field not in ('sales', 'attitude'):
            raise UserError(_('Tiêu chí không hợp lệ.'))
        start, _end, _d = self._month_range(month)
        Input = self.env['store.nvbh.kpi.input']
        mkey = start.strftime('%Y-%m')
        rec = Input.search([('month', '=', mkey), ('store_id', '=', int(store_id)), ('staff_name', '=ilike', staff_name.strip())], limit=1)
        has = pct not in (None, '', False) or pct == 0
        vals = {field + '_pct': min(max(float(pct or 0.0), 0.0), 100.0), field + '_note': (note or '').strip() or False, 'has_' + field: bool(has)}
        if rec:
            rec.write(vals)
        else:
            Input.create(dict(vals, month=mkey, store_id=int(store_id), staff_name=staff_name.strip()))
        return self.get_kpi_report(mkey, store_id, staff_name)

    @api.model
    def export_kpi_xlsx(self, month=None, store_id=None, staff_names=None, profile='kpi'):
        """Xuất Phiếu đánh giá năng suất & KPI cá nhân ra Excel, mỗi nhân viên một sheet."""
        import io
        import xlsxwriter
        self.env['store.perm.rule'].check_export()
        if not staff_names:
            raise UserError(_('Chưa chọn nhân viên nào để xuất.'))
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        navy, mid = '#1E3A6E', '#2F5D8C'

        def fmt(**kw):
            base = {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter', 'border': 1}
            base.update(kw)
            return book.add_format(base)

        f_title = fmt(bold=True, font_size=16, font_color='#FFFFFF', bg_color=navy, border=0)
        f_sub = fmt(italic=True, font_color='#FFFFFF', bg_color=mid, border=0)
        f_lab = fmt(bold=True, font_color='#000000', bg_color='#F1F5FB', align='center', text_wrap=True, font_size=10)
        f_val = fmt(bold=True, font_color='#000000', bg_color='#EAF2FC', align='center')
        f_head = fmt(bold=True, font_color='#FFFFFF', bg_color=navy, align='center', text_wrap=True)
        f_c = fmt(align='center')
        f_l = fmt(text_wrap=True)
        f_pct = fmt(align='center', num_format='0.0"%"')
        f_num = fmt(align='center', num_format='0.00')
        f_numb = fmt(align='center', num_format='0.00', bold=True)
        f_sec = fmt(bold=True, bg_color='#EAF2FC')
        f_sec_c = fmt(bold=True, bg_color='#EAF2FC', align='center', num_format='0.00')
        f_sec_p = fmt(bold=True, bg_color='#EAF2FC', align='center', num_format='0.0"%"')
        f_tot = fmt(bold=True, bg_color='#DBE7F5', font_size=12)
        f_tot_c = fmt(bold=True, bg_color='#DBE7F5', align='center', num_format='0.00')
        f_tot_p = fmt(bold=True, bg_color='#DBE7F5', align='center', num_format='0.0"%"')
        f_rank = fmt(bold=True, bg_color='#D9F2E3', font_color='#15803D', align='center')
        f_right = fmt(bold=True, align='right', border=0)
        used = set()
        for nm in staff_names:
            d = self.get_kpi_report(month, store_id, nm, profile)
            if not d:
                continue
            lb = d['labels']
            title = ''.join(ch for ch in d['staff'] if ch not in '[]:*?/\\')[:31] or 'KPI'
            base, k = title, 2
            while title.lower() in used:
                title = '%s %d' % (base[:28], k)
                k += 1
            used.add(title.lower())
            ws = book.add_worksheet(title)
            ws.hide_gridlines(2)
            ws.set_column('A:A', 7)
            ws.set_column('B:B', 58)
            ws.set_column('C:C', 22)
            ws.set_column('D:H', 13)
            ws.set_column('I:I', 62)
            ws.merge_range('A1:I1', '%s — %s%s' % (lb['title'], d['staff'].upper(), ' (ASM)' if d['asm'] else ''), f_title)
            ws.set_row(0, 30)
            ws.merge_range('A2:I2', 'Cửa hàng: %s | Mã NV: %s | Kỳ: Tháng %s%s' % (
                d['store'], d['code'] or '-', d['month_label'], (' | Cấp đánh giá: %s (ASM)' % d['asm']) if d['asm'] else '') + ((' | ' + lb['subtitle_extra']) if lb['subtitle_extra'] else ''), f_sub)
            s = d['summary']
            ws.set_row(3, 30)
            ws.write(3, 0, 'Mã NV', f_lab)
            ws.write(4, 0, d['code'] or '-', f_val)
            ws.write(3, 1, 'Số ca hoàn thành / Lịch', f_lab)
            ws.write(4, 1, s['shifts'], f_val)
            ws.write(3, 2, 'Tổng việc đã làm / Giao', f_lab)
            ws.write(4, 2, s['jobs'], f_val)
            for i, (lab, vl) in enumerate([('Tỷ lệ HT đầu việc', s['complete']), ('Điểm đạt / Điểm chuẩn', s['points']), ('Năng suất Checklist', s['productivity']),
                                          ('Số lỗi vi phạm', s['errors']), ('Điểm TB / Ca', s['avg'])]):
                if i < 5:
                    ws.write(3, 3 + i, lab, f_lab)
                    ws.write(4, 3 + i, vl, f_val)
            ws.write(3, 8, lb['status_label'], f_lab)
            ws.write(4, 8, s['status'], f_val)
            heads = ['STT', lb['col_first'], lb['col_source'], 'Trọng số (%)', 'Điểm tối đa (Thang 100)',
                     'Tỷ lệ đạt thực tế (%)', lb['col_kpi'], 'Chỉ tiêu chuẩn', 'Ghi chú & Diễn giải kết quả']
            ws.set_row(6, 36)
            for c, h in enumerate(heads):
                ws.write(6, c, h, f_head)
            r = 7
            for g in d['groups']:
                ws.write(r, 0, g['no'], f_c)
                ws.write(r, 1, g['title'], f_l)
                ws.write(r, 2, g['source'], f_c)
                ws.write(r, 3, g['weight'], f_pct)
                ws.write(r, 4, g['max'], f_num)
                ws.write(r, 5, g['pct'] if g['pct'] is not None else '-', f_pct)
                ws.write(r, 6, g['kpi'], f_numb)
                ws.write(r, 7, g['target'], f_c)
                ws.write(r, 8, g['note'], f_l)
                r += 1
            sb = d['sub']
            ws.write(r, 0, '', f_sec)
            ws.write(r, 1, lb['sub_label'], f_sec)
            ws.write(r, 2, '', f_sec)
            ws.write(r, 3, sb['weight'], f_sec_p)
            ws.write(r, 4, sb['max'], f_sec_c)
            ws.write(r, 5, sb['pct'], f_sec_p)
            ws.write(r, 6, sb['kpi'], f_sec_c)
            ws.write(r, 7, sb['target'], f_sec_c)
            ws.write(r, 8, sb['note'], f_sec)
            r += 1
            for o in d['others']:
                ws.write(r, 0, o['no'], f_c)
                ws.write(r, 1, o['title'], f_l)
                ws.write(r, 2, o['source'], f_c)
                ws.write(r, 3, o['weight'], f_pct)
                ws.write(r, 4, o['max'], f_num)
                if o['pct'] is None:
                    ws.write(r, 5, '-', f_c)
                elif o.get('extra'):
                    ws.write(r, 5, '%s (%s%%)' % (o['extra'], _vn(o['pct'], 0 if o['pct'] == int(o['pct']) else 1)), f_c)
                else:
                    ws.write(r, 5, o['pct'], f_pct)
                ws.write(r, 6, o['kpi'], f_numb)
                ws.write(r, 7, o['target'], f_c)
                ws.write(r, 8, o['note'], f_l)
                ws.set_row(r, 22)
                r += 1
            t = d['total']
            ws.write(r, 0, '', f_tot)
            ws.write(r, 1, lb['total_label'] % (d['month_label'], t['weight']), f_tot)
            ws.write(r, 2, '', f_tot)
            ws.write(r, 3, t['weight'], f_tot_p)
            ws.write(r, 4, t['max'], f_tot_c)
            ws.write(r, 5, t['pct'], f_tot_p)
            ws.write(r, 6, t['kpi'], f_tot_c)
            ws.write(r, 7, t['target'], f_tot_c)
            ws.write(r, 8, t['note'], f_tot)
            ws.set_row(r, 24)
            r += 2
            ws.merge_range(r, 1, r, 5, lb['rank_label'], f_right)
            ws.write(r, 6, d['rank'], f_rank)
            ws.merge_range(r, 7, r, 8, 'Ngưỡng chuẩn: ≥95đ Hạng A | 85–94.9đ Hạng B | 75–84.9đ Hạng C | <75đ Hạng D', fmt(border=0))
            ws.set_row(r, 24)
            if lb.get('show_bonus'):
                r += 1
                ws.merge_range(r, 1, r, 5, lb['bonus_label'], f_right)
                ws.write(r, 6, '%d%%' % d['bonus'], fmt(bold=True, align='center'))
                ws.merge_range(r, 7, r, 8, 'Hạng A: 120% | Hạng B: 100% | Hạng C: 80% | Hạng D: 0%', fmt(border=0))
            ws.set_landscape()
            ws.set_paper(9)
            ws.fit_to_pages(1, 0)
        book.close()
        import base64
        return {'name': '%s_%s.xlsx' % (PROFILES.get(profile, PROFILES['kpi'])['labels']['file'], fields.Date.context_today(self).strftime('%Y%m%d')), 'data': base64.b64encode(buf.getvalue()).decode()}


    @api.model
    def get_kpi_asm_report(self, month=None, mien=None, asm_id=None):
        """Báo cáo quản trị khu vực theo ASM: tổng hợp KPI 5 nhóm Checklist + 4 tiêu chí theo từng cửa hàng và từng ASM."""
        start, end, _days = self._month_range(month)
        mkey = start.strftime('%Y-%m')
        dom = [('work_date', '>=', start), ('work_date', '<', end)]
        if mien:
            dom.append(('store_id.mien', '=', mien))

        # Thu thập toàn bộ (store_id, staff_name) có lịch hoặc checklist trong tháng/miền
        pairs = {}
        for ln in self.env['store.nvbh.schedule.line'].search(dom):
            nm = (ln.staff_name or '').strip()
            if nm and ln.store_id:
                pairs.setdefault((ln.store_id.id, nm.casefold()), (ln.store_id, nm))
        for chk in self.search(dom):
            nm = (chk.staff_name or '').strip()
            if nm and chk.store_id:
                pairs.setdefault((chk.store_id.id, nm.casefold()), (chk.store_id, nm))

        dyn_groups = self._dynamic_kpi_groups('kpi')
        n_g = len(dyn_groups)
        g_keys = ['g%d' % (i + 1) for i in range(n_g)]
        g_weights = [g[2] for g in dyn_groups]
        w_chk = sum(g_weights)

        by_store = {}
        for (_sid, _nc), (store, nm) in pairs.items():
            d = self.get_kpi_report(mkey, store.id, nm, 'kpi')
            if not d:
                continue
            other = {r['no']: r for r in d['others']}
            grps = d['groups']
            s_entry = by_store.setdefault(store.id, {'store': store, 'staff': []})
            row_sf = {
                'name': d['staff'], 'code': d['code'],
                'complete': other['2']['kpi'], 'discipline': other['3']['kpi'],
                'sales': other['4']['kpi'], 'attitude': other['5']['kpi'],
                'kpi_total': d['total']['kpi'],
                'shifts_pct': d['summary']['shifts_pct'],
                'rank': d['rank'], 'bonus': d['bonus'],
            }
            for i, gk in enumerate(g_keys):
                row_sf[gk] = grps[i]['kpi'] if i < len(grps) else 0.0
            s_entry['staff'].append(row_sf)

        def avg_key(items, key):
            return round(sum(x[key] for x in items) / len(items), 2) if items else 0.0

        def short_rank(score):
            if score >= 80.0:
                return 'Hạng A', 'A'
            if score >= 70.0:
                return 'Hạng B', 'B'
            return 'Hạng C', 'C'

        asm_map = {}
        for sid, sdata in by_store.items():
            store = sdata['store']
            staff = sdata['staff']
            if not staff:
                continue
            mgr = store.manager_id
            aid = mgr.id or 0
            aname = mgr.name or 'Chưa gán ASM'
            st_row = {
                'store_id': store.id, 'store': store.display_name or store.name or '-',
                'staff_count': len(staff),
                **{gk: avg_key(staff, gk) for gk in g_keys},
                'complete': avg_key(staff, 'complete'), 'discipline': avg_key(staff, 'discipline'),
                'sales': avg_key(staff, 'sales'), 'attitude': avg_key(staff, 'attitude'),
                'kpi_total': avg_key(staff, 'kpi_total'),
                'shifts_pct': avg_key(staff, 'shifts_pct'),
                'staff': sorted(staff, key=lambda x: (-x['kpi_total'], x['name'])),
            }
            st_row['passed'] = st_row['kpi_total'] >= 72.0
            st_row['status'] = 'ĐẠT' if st_row['passed'] else 'CHƯA ĐẠT'
            st_row['rank_short'], st_row['rank_code'] = short_rank(st_row['kpi_total'])
            a = asm_map.setdefault(aid, {'id': aid, 'name': aname, 'stores': []})
            a['stores'].append(st_row)

        all_asms = []
        for aid, a in asm_map.items():
            stores = sorted(a['stores'], key=lambda s: (-s['kpi_total'], s['store']))
            g_avgs = [avg_key(stores, gk) for gk in g_keys]
            comp = avg_key(stores, 'complete')
            disc = avg_key(stores, 'discipline')
            sales = avg_key(stores, 'sales')
            att = avg_key(stores, 'attitude')
            tot = avg_key(stores, 'kpi_total')
            sh_pct = avg_key(stores, 'shifts_pct')
            r_short, r_code = short_rank(tot)
            # N nhóm Checklist (%) + Tổng các nhóm cho biểu đồ xếp hạng ASM
            p_list = [round(100.0 * gv / gw, 1) if gw else 0.0 for gv, gw in zip(g_avgs, g_weights)]
            p_all = round(100.0 * sum(g_avgs) / w_chk, 1) if w_chk else 0.0
            # 6 trục (%) theo chiều kim đồng hồ cho biểu đồ Radar lục giác: Kỷ luật, Thái độ, Tỷ lệ đi ca, Doanh số, Checklist, Hoàn thành
            radar = [
                round(100.0 * disc / W_DISCIPLINE, 1),
                round(100.0 * att / W_ATTITUDE, 1),
                round(min(sh_pct, 100.0), 1),
                round(100.0 * sales / W_SALES, 1),
                p_all,
                round(100.0 * comp / W_COMPLETE, 1),
            ]
            all_asms.append({
                'id': aid, 'name': a['name'],
                'store_count': len(stores), 'staff_count': sum(s['staff_count'] for s in stores),
                **{gk: gv for gk, gv in zip(g_keys, g_avgs)},
                'complete': comp, 'discipline': disc, 'sales': sales, 'attitude': att,
                'kpi_total': tot, 'shifts_pct': sh_pct,
                'rank_short': r_short, 'rank_code': r_code,
                'pillars': [*p_list, p_all],
                'radar': radar,
                'stores': stores,
            })

        all_asms.sort(key=lambda x: (-x['kpi_total'], x['name']))
        for idx, a in enumerate(all_asms, 1):
            a['rank_no'] = idx

        asm_opts = [{'id': a['id'], 'name': a['name']} for a in all_asms]
        if asm_id not in (None, '', False):
            target = int(asm_id)
            asms = [a for a in all_asms if a['id'] == target]
        else:
            asms = all_asms

        all_stores = [s for a in asms for s in a['stores']]
        region = {
            'store_count': len(all_stores),
            'staff_count': sum(s['staff_count'] for s in all_stores),
            'avg_kpi': round(sum(s['kpi_total'] for s in all_stores) / len(all_stores), 2) if all_stores else 0.0,
            'pillar_avgs': [round(sum(a['pillars'][i] for a in all_asms) / len(all_asms), 1) if all_asms else 0.0 for i in range(n_g + 1)],
            'rank_counts': {
                'all': len(asms),
                'A': sum(1 for a in asms if a['rank_code'] == 'A'),
                'B': sum(1 for a in asms if a['rank_code'] == 'B'),
                'C': sum(1 for a in asms if a['rank_code'] == 'C'),
            },
        }

        return {
            'month': mkey, 'month_label': start.strftime('%m/%Y'),
            'updated_at': fields.Date.context_today(self).strftime('%d/%m/%Y'),
            'group_names': [g[1] for g in dyn_groups],
            'weights': {**{gk: gw for gk, gw in zip(g_keys, g_weights)},
                        'complete': W_COMPLETE, 'discipline': W_DISCIPLINE, 'sales': W_SALES, 'attitude': W_ATTITUDE},
            'region': region,
            'asm_opts': asm_opts,
            'asms': asms,
        }

    @api.model
    def export_kpi_asm_xlsx(self, month=None, mien=None, asm_id=None):
        """Xuất Báo cáo Checklist NVBH theo ASM ra Excel: sheet Tổng hợp + mỗi ASM một sheet."""
        self.env['store.perm.rule'].check_export()
        data = self.get_kpi_asm_report(month, mien, asm_id)
        if not data['asms']:
            raise UserError(_('Không có dữ liệu ASM để xuất.'))
        w = data['weights']
        g_keys = ['g%d' % (i + 1) for i in range(len(data['group_names']))]
        headers = [
            'Hạng', 'ASM', 'Cửa hàng',
            *['%s (%gđ)' % (n, w[gk]) for n, gk in zip(data['group_names'], g_keys)],
            'Hoàn thành việc (%gđ)' % w['complete'], 'Kỷ luật (%gđ)' % w['discipline'],
            'Doanh số (%gđ)' % w['sales'], 'Thái độ (%gđ)' % w['attitude'],
            'Tổng KPI (100)', 'Xếp loại',
        ]
        all_rows = []
        for a in data['asms']:
            all_rows.append([
                a['rank_no'], '%s (TB · %d CH, %d NV)' % (a['name'], a['store_count'], a['staff_count']), '',
                *[a.get(gk, 0.0) for gk in g_keys],
                a['complete'], a['discipline'], a['sales'], a['attitude'], a['kpi_total'], a['rank_short'],
            ])
            for s in a['stores']:
                all_rows.append([
                    '', a['name'], '%s (%d NV)' % (s['store'], s['staff_count']),
                    *[s.get(gk, 0.0) for gk in g_keys],
                    s['complete'], s['discipline'], s['sales'], s['attitude'], s['kpi_total'], s['status'],
                ])
        sheets = [{
            'name': 'Tong hop ASM',
            'title': 'BÁO CÁO QUẢN TRỊ KHU VỰC THEO ASM - THÁNG %s' % data['month_label'],
            'subtitle': 'Theo dõi và quản lý hiệu quả hoạt động các cửa hàng theo ASM',
            'headers': headers, 'rows': all_rows, 'foot': None,
        }]
        used = {'tong hop asm'}
        for a in data['asms']:
            srows = [
                [i, a['name'], '%s (%d NV)' % (s['store'], s['staff_count']),
                 *[s.get(gk, 0.0) for gk in g_keys],
                 s['complete'], s['discipline'], s['sales'], s['attitude'], s['kpi_total'], s['status']]
                for i, s in enumerate(a['stores'], 1)
            ]
            foot = [
                '', 'TRUNG BÌNH %s (%d CH, %d NV)' % (a['name'], a['store_count'], a['staff_count']), '',
                *[a.get(gk, 0.0) for gk in g_keys],
                a['complete'], a['discipline'], a['sales'], a['attitude'], a['kpi_total'], a['rank_short'],
            ]
            sname = ''.join(ch for ch in (a['name'] or 'ASM') if ch not in '[]:*?/\\')[:31] or 'ASM'
            base, k = sname, 2
            while sname.lower() in used:
                sname = '%s %d' % (base[:28], k)
                k += 1
            used.add(sname.lower())
            sheets.append({
                'name': sname,
                'title': 'BÁO CÁO KPI CỬA HÀNG - %s (THÁNG %s)' % (a['name'].upper(), data['month_label']),
                'subtitle': '%d cửa hàng · %d nhân viên · TB KPI %s (%s)' % (a['store_count'], a['staff_count'], _vn(a['kpi_total'], 2), a['rank_short']),
                'headers': headers, 'rows': srows, 'foot': foot,
            })
        return self._xlsx_book(sheets, 'Bao_cao_Checklist_NVBH_ASM')

    # ---- Báo cáo hiệu suất NVBH: tổng điểm thực tế ASM đã đánh giá theo từng nhóm công việc ----
    @api.model
    def get_nvbh_perf_report(self, month=None, mien=None, asm_id=None, store_id=None):
        from .store_nvbh_check import count_errors, eval_score
        start, end, _days = self._month_range(month)
        mkey = start.strftime('%Y-%m')
        dom = [('work_date', '>=', start), ('work_date', '<', end), ('kind', 'in', ('nvbh', 'cht'))]
        checks = self.search(dom, order='work_date, id')

        # Cột nhóm công việc = đúng các nhóm có trong checklist NVBH / CHT của tháng (không lấy nhóm cài đặt chưa dùng),
        # sắp theo thứ tự nhóm ở Cài đặt (Danh sách công việc NVBH, rồi CHT)
        seen = {}
        for ln in checks.line_ids:
            k = _norm_grp(ln.sub_category)
            if k and k not in seen:
                seen[k] = (ln.sub_category or '').strip()
        order = {}
        for model in ('store.nvbh.task.group', 'store.cht.task.group'):
            for g in self.env[model].sudo().search([], order='sequence, id'):
                order.setdefault(_norm_grp(g.name), len(order))
        dyn_groups = [(n, n) for k, n in sorted(seen.items(), key=lambda kv: (order.get(kv[0], 9999), kv[1].casefold()))]             or [(g[0], g[1]) for g in self._dynamic_kpi_groups('kpi')]
        group_names = [g[1] for g in dyn_groups]
        g_norm_idx = {_norm_grp(g[0]): i for i, g in enumerate(dyn_groups)}
        g_keys = ['g%d' % (i + 1) for i in range(len(group_names))]

        export_store_map = {}
        asm_opts_map = {}
        store_opts_map = {}
        staff_map = {}
        for c in checks:
            st = c.store_id
            if not st:
                continue
            nm = (c.staff_name or '').strip()
            if not nm:
                continue
            mgr = st.manager_id
            aid = mgr.id or 0
            aname = mgr.name or 'Chưa gán ASM'
            smien = st.mien or ''
            sname = st.code or st.display_name or st.name or '-'  # Mã cửa hàng (LUG_KDV) như mẫu báo cáo
            se = export_store_map.setdefault(st.id, {
                'id': st.id, 'name': sname, 'mien': smien,
                'asm_id': aid, 'asm': aname, 'staff_set': set(),
            })
            se['staff_set'].add(nm.casefold())
            if mien and smien != mien:
                continue
            asm_opts_map[aid] = aname
            if asm_id not in (None, '', False) and aid != int(asm_id):
                continue
            store_opts_map[st.id] = sname
            if store_id and st.id != int(store_id):
                continue
            sk = (st.id, nm.casefold())
            rec = staff_map.setdefault(sk, {
                'name': nm, 'code': '', 'store_id': st.id, 'store': sname, 'mien': smien,
                'asm': aname, 'g_pts': [0.0] * len(g_keys), 'g_max': [0.0] * len(g_keys),
                'done': 0, 'total': 0, 'rate_vals': [], 'is_cht': False,
            })
            if c.kind == 'cht':
                rec['is_cht'] = True
            if not rec['code'] and c.schedule_line_id and c.schedule_line_id.employee_code:
                rec['code'] = c.schedule_line_id.employee_code
            rec['done'] += c.cnt_done
            rec['total'] += c.cnt_total
            mp = sum(l.max_score or 0.0 for l in c.line_ids)
            if c._fully_evaluated():
                rec['rate_vals'].append(round(100.0 * c.points / mp, 1) if mp else 0.0)
            for l in c.line_ids:
                # kết quả ASM chấm: trong phiếu (CHT: bước 1) hoặc ở trang Đánh giá tuần (cột bước 2)
                res, err = c._asm_line_result(l)
                if not res:
                    continue
                idx = g_norm_idx.get(_norm_grp(l.sub_category))
                if idx is None:
                    continue
                pts = eval_score(l.max_score, res, count_errors(err))
                rec['g_pts'][idx] += pts
                rec['g_max'][idx] += l.max_score or 0.0

        Rating = self.env['store.nvbh.rating']
        rating_levels = Rating.sudo().search([], order='min_score desc, id')
        rank_levels = [{
            'code': str(lv.id),
            'name': lv.name,
            'score_range': lv.score_range,
            'tone': lv.tone or 'orange',
            'count': 0,
        } for lv in rating_levels]
        lv_idx_map = {str(lv.id): i for i, lv in enumerate(rating_levels)}
        wait_count = 0

        rows = []
        for rec in staff_map.values():
            g_vals = [round(v, 2) for v in rec['g_pts']]
            tasks_total = round(sum(g_vals), 2)
            max_total = round(sum(rec['g_max']), 2)
            tasks_pct = round(100.0 * tasks_total / max_total, 1) if max_total else 0.0
            avg_pct = round(sum(rec['rate_vals']) / len(rec['rate_vals']), 2) if rec['rate_vals'] else None
            if avg_pct is not None:
                r1 = round(avg_pct, 1)
                rate_label = ('%d%%' % int(r1)) if r1 == int(r1) else ('%s%%' % ('%.1f' % r1).replace('.', ','))
                lvl = Rating.rating_for(avg_pct)
                rank_code = str(lvl.id) if lvl else 'wait'
                rank_short = lvl.name if lvl else 'Chờ đánh giá'
                rank_tone = (lvl.tone or 'orange') if lvl else 'wait'
                passed = bool(lvl and lvl.tone in ('green', 'blue'))
                if rank_code in lv_idx_map:
                    rank_levels[lv_idx_map[rank_code]]['count'] += 1
                else:
                    wait_count += 1
            else:
                rate_label = '-'
                rank_code = 'wait'
                rank_short = 'Chờ đánh giá'
                rank_tone = 'wait'
                passed = False
                wait_count += 1
            row = {
                'name': rec['name'], 'code': rec['code'], 'is_cht': rec.get('is_cht', False),
                'store_id': rec['store_id'], 'store': rec['store'], 'mien': rec.get('mien', ''), 'asm': rec['asm'],
                **{gk: gv for gk, gv in zip(g_keys, g_vals)},
                'tasks_total': tasks_total, 'max_total': max_total, 'tasks_pct': tasks_pct,
                'avg_pct': avg_pct, 'rate_label': rate_label,
                'complete': avg_pct or 0.0, 'complete_label': rate_label,
                'rank_short': rank_short, 'rank_code': rank_code, 'rank_tone': rank_tone, 'passed': passed,
            }
            rows.append(row)

        store_sales = self._perf_attach_sales(rows, mkey, start, end)

        if wait_count:
            rank_levels.append({'code': 'wait', 'name': 'Chờ đánh giá', 'score_range': '', 'tone': 'wait', 'count': wait_count})
        rank_legend = ' · '.join('%s: %s%%' % (lv['name'], lv['score_range']) for lv in rank_levels if lv.get('score_range'))

        rows.sort(key=lambda r: (-r['tasks_total'], -r['complete'], r['name']))
        for i, r in enumerate(rows, 1):
            r['no'] = i
        n = len(rows)
        counts = {lv['code']: lv['count'] for lv in rank_levels}
        # Nhận xét theo tuần của ASM cho từng cửa hàng trong tháng (luôn đủ Tuần 1..N)
        weeks = self._month_weeks(start, end)
        store_ids = list({r['store_id'] for r in rows})
        store_comments = {}
        if store_ids:
            visits = self.env['store.cht.visit'].sudo().search(
                [('store_id', 'in', store_ids), ('visit_date', '>=', start), ('visit_date', '<', end), ('comment', '!=', False)],
                order='visit_date, id')
            by_sw = {}
            for v in visits:
                txt = (v.comment or '').strip()
                if not txt:
                    continue
                wk_idx = next((idx + 1 for idx, (a, b) in enumerate(weeks) if a <= v.visit_date <= b), 0)
                if wk_idx:
                    by_sw.setdefault((v.store_id.id, wk_idx), []).append({
                        'date': v.visit_date.strftime('%d/%m') if v.visit_date else '',
                        'user': v.user_id.name or '',
                        'comment': txt,
                    })
            for sid in store_ids:
                store_comments[sid] = [{
                    'week_num': idx,
                    'label': 'Nhận xét tuần %d' % idx,
                    'range': '%s – %s' % (a.strftime('%d/%m'), b.strftime('%d/%m')),
                    'items': by_sw.get((sid, idx), []),
                } for idx, (a, b) in enumerate(weeks, 1)]
        export_stores = [{
            'id': v['id'], 'name': v['name'], 'mien': v['mien'],
            'asm_id': v['asm_id'], 'asm': v['asm'], 'staff_count': len(v['staff_set']),
        } for v in sorted(export_store_map.values(), key=lambda x: x['name'].casefold())]
        return {
            'month': mkey, 'month_label': start.strftime('%m/%Y'),
            'updated_at': fields.Date.context_today(self).strftime('%d/%m/%Y'),
            'weights': {}, 'group_names': group_names,
            'asm_opts': [{'id': k, 'name': v} for k, v in sorted(asm_opts_map.items(), key=lambda x: x[1])],
            'store_opts': [{'id': k, 'name': v} for k, v in sorted(store_opts_map.items(), key=lambda x: x[1])],
            'export_stores': export_stores,
            'rows': rows,
            'rank_levels': rank_levels,
            'rank_legend': rank_legend,
            'store_comments': store_comments,
            'store_sales': store_sales,
            'summary': {
                'staff_count': n, 'store_count': len({r['store_id'] for r in rows}),
                'avg_kpi': round(sum(r['tasks_total'] for r in rows) / n, 2) if n else 0.0,
                'passed': sum(1 for r in rows if r['passed']), 'counts': counts,
                'avgs': {k: round(sum(r.get(k, 0.0) for r in rows) / n, 2) if n else 0.0
                         for k in (*g_keys, 'tasks_total', 'complete')},
            },
        }

    @api.model
    def _perf_attach_sales(self, rows, mkey, start, end):
        """Gắn Target NV (Phân Bổ Target: Target CH x %) + Doanh thu đạt (Doanh thu theo ngày, đã lưu) + % Đạt Target vào từng dòng
        nhân viên; trả về {store_id: {target, revenue, pct}} cho dòng cửa hàng."""
        import math

        def norm(v):
            return (v or '').strip().casefold()

        def pct(done, tg):
            return math.floor(1000.0 * done / tg + 0.5) / 10 if tg else None

        sids = list({r['store_id'] for r in rows})
        out = {}
        if not sids:
            return out
        targets = {t.store_id.id: t for t in self.env['store.nvbh.target'].sudo().search(
            [('month', '=', mkey), ('store_id', 'in', sids)])}
        revs = self.env['store.nvbh.revenue'].sudo().search([
            ('store_id', 'in', sids), ('work_date', '>=', start), ('work_date', '<', end), ('is_saved', '=', True)])
        rev_code, rev_name, rev_store = {}, {}, {}
        for r in revs:
            sid = r.store_id.id
            v = r.revenue or 0.0
            rev_store[sid] = rev_store.get(sid, 0.0) + v
            if (r.employee_code or '').strip():
                k = (sid, r.employee_code.strip())
                rev_code[k] = rev_code.get(k, 0.0) + v
            else:
                k = (sid, norm(r.staff_name))
                rev_name[k] = rev_name.get(k, 0.0) + v
        for sid in sids:
            t = targets.get(sid)
            tg = round(t.target) if t else 0
            out[sid] = {'target': tg, 'revenue': round(rev_store.get(sid, 0.0)), 'pct': pct(rev_store.get(sid, 0.0), tg)}
        for row in rows:
            sid = row['store_id']
            t = targets.get(sid)
            code = (row.get('code') or '').strip()
            line = False
            if t:
                line = (code and t.line_ids.filtered(lambda l: (l.employee_code or '').strip() == code)[:1]) \
                    or t.line_ids.filtered(lambda l: norm(l.staff_name) == norm(row['name']))[:1]
            tg_nv = round((t.target or 0) * (line.pct or 0) / 100.0) if (t and line) else 0
            rev = (rev_code.get((sid, code), 0.0) if code else 0.0) + rev_name.get((sid, norm(row['name'])), 0.0)
            row['target_nv'] = tg_nv
            row['revenue'] = round(rev)
            row['rev_pct'] = pct(rev, tg_nv)
        return out

    @api.model
    def _perf_xlsx_banner(self, book, ws, ncol, c_right, title, subtitle):
        """Khung tiêu đề giống màn hình: logo công ty | biểu tượng | tiêu đề + mô tả | ảnh minh họa (3 dòng đầu sheet)."""
        import base64
        import io as _io
        from odoo.tools.misc import file_path
        BG = '#EEF4FF'
        f_bg = book.add_format({'bg_color': BG, 'top': 1, 'bottom': 1, 'border_color': '#C7D2FE'})
        f_t = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 18, 'font_color': '#1E3A6E',
                               'bg_color': BG, 'valign': 'bottom', 'top': 1, 'border_color': '#C7D2FE'})
        f_s = book.add_format({'font_name': 'Times New Roman', 'font_size': 11, 'font_color': '#475569',
                               'bg_color': BG, 'valign': 'top', 'bottom': 1, 'border_color': '#C7D2FE', 'text_wrap': True})
        for r in (0, 1, 2):
            ws.set_row(r, 28)
        ws.merge_range(0, 0, 2, 2, '', f_bg)
        ws.merge_range(0, 3, 2, 3, '', f_bg)
        ws.merge_range(0, 4, 1, c_right - 1, title, f_t)
        ws.merge_range(2, 4, 2, c_right - 1, subtitle, f_s)
        ws.merge_range(0, c_right, 2, ncol - 1, '', f_bg)
        H = 78.0

        def put(row, col, raw, max_w=None, x_off=4, y_off=3):
            scale = 1.0
            try:
                from PIL import Image
                w, h = Image.open(_io.BytesIO(raw)).size
                scale = (H - 6) / h
                if max_w and w * scale > max_w:
                    scale = max_w / w
            except Exception:
                pass
            ws.insert_image(row, col, 'img.png', {'image_data': _io.BytesIO(raw), 'x_scale': scale, 'y_scale': scale,
                                                  'x_offset': x_off, 'y_offset': y_off, 'object_position': 2})

        logo = self.env.company.logo_web or self.env.company.logo
        if logo:
            put(0, 0, base64.b64decode(logo), max_w=230)
        for rel, col, mw in (('store_checklist/static/src/shell/img/audit_icon.png', 3, 70),
                             ('store_checklist/static/src/shell/img/banner_bg.jpg', c_right, 300)):
            try:
                with open(file_path(rel), 'rb') as fh:
                    put(0, col, fh.read(), max_w=mw)
            except Exception:
                pass

    @api.model
    def export_nvbh_perf_xlsx(self, month=None, mien=None, asm_id=None, store_id=None, store_ids=None):
        """Xuất Báo cáo hiệu suất NVBH ra Excel: cho phép chọn theo miền / nhiều cửa hàng,
        mỗi cửa hàng xuất thành 1 sheet riêng kèm nhận xét theo tuần của ASM."""
        import base64
        import io as _io
        import re as _re
        import xlsxwriter
        self.env['store.perm.rule'].check_export()
        if store_ids:
            data = self.get_nvbh_perf_report(month)
            wanted_list = [int(x) for x in store_ids if x]
            wanted_set = set(wanted_list)
            rows_src = [r for r in data['rows'] if r['store_id'] in wanted_set]
        else:
            data = self.get_nvbh_perf_report(month, mien, asm_id, store_id)
            wanted_list = []
            rows_src = data['rows']
        if not rows_src:
            raise UserError(_('Không có dữ liệu nhân viên để xuất.'))
        from xlsxwriter.utility import xl_rowcol_to_cell as cell
        g_keys = ['g%d' % (i + 1) for i in range(len(data['group_names']))]
        ng = len(g_keys)
        # Cột theo mẫu: STT | Cửa hàng | Họ và tên NV | ID HRM | Target NV | Doanh thu đạt | % Đạt Target | nhóm checklist |
        # Tổng điểm công việc | Tỷ lệ đạt Checklist | Xếp loại Checklist
        C_TG, C_REV, C_PCT, C_RKT = 4, 5, 6, 7
        C_G0 = 8
        C_TOT, C_RATE, C_RANK = C_G0 + ng, C_G0 + ng + 1, C_G0 + ng + 2
        ncol = C_RANK + 1
        headers = ['STT', 'Cửa hàng', 'Họ và tên nhân viên', 'ID HRM', 'Target NV\n(VNĐ)', 'Doanh thu đạt\n(VNĐ)',
                   '% Đạt Target\n(Doanh số)', 'Xếp loại\nTarget', *data['group_names'], 'Tổng điểm\ncông việc', 'Tỷ lệ đạt\nChecklist (%)', 'Xếp loại\nChecklist']
        widths = [6, 12, 26, 11, 17, 17, 14, 18, *([16] * ng), 13, 14, 16]
        sales = data.get('store_sales') or {}

        groups = {}
        for r in rows_src:
            groups.setdefault(r['store_id'], []).append(r)
        if wanted_list:
            ordered = [groups[sid] for sid in wanted_list if sid in groups]
        else:
            avg = lambda items, k: sum(x[k] for x in items) / len(items)
            ordered = sorted(groups.values(), key=lambda st: (-avg(st, 'tasks_total'), st[0]['store']))

        buf = _io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        base = {'font_name': 'Times New Roman', 'font_size': 12, 'valign': 'vcenter', 'border': 1, 'border_color': '#808080'}
        F = lambda **kw: book.add_format(dict(base, **kw))
        # màu theo mẫu: Thông tin NS (trắng) | Chỉ tiêu & doanh thu (xanh lá) | Điểm checklist (xanh dương) | Tổng hợp (cam)
        C_GREEN, C_BLUE, C_ORANGE = '#00B050', '#5B9BD5', '#E26B0A'
        f_title = book.add_format({'font_name': 'Times New Roman', 'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'})
        f_band_ns = F(bold=True, align='center')
        f_band_sl = F(bold=True, font_color='#FFFFFF', bg_color=C_GREEN, align='center')
        f_band_ck = F(bold=True, font_color='#FFFFFF', bg_color=C_BLUE, align='center')
        f_band_sm = F(bold=True, font_color='#FFFFFF', bg_color=C_ORANGE, align='center')
        f_head_ns = F(bold=True, align='center', text_wrap=True)
        f_head_sl = F(bold=True, font_color='#FFFFFF', bg_color=C_GREEN, align='center', text_wrap=True)
        f_head_ck = F(bold=True, font_color='#FFFFFF', bg_color=C_BLUE, align='center', text_wrap=True)
        f_head_sm = F(bold=True, font_color='#FFFFFF', bg_color=C_ORANGE, align='center', text_wrap=True)
        f_c = F(align='center')
        f_cb = F(align='center', bold=True)
        f_name = F()
        f_money = F(align='right', num_format='#,##0')
        f_pct = F(align='right', bold=True, num_format='0.0%', bg_color='#FFF2CC', font_color='#9C0006')
        f_num = F(align='right', num_format='General')
        f_tot = F(align='right', bold=True, num_format='General')
        f_rate = F(align='right', num_format='0.0%')
        f_rank = F(align='center', bold=True)
        f_rkt = F(align='center', bold=True, font_size=11)
        GRAY = '#D6DCE4'
        f_sum_l = F(bold=True, bg_color=GRAY, align='center', font_color='#1F3864')
        f_sum_m = F(bold=True, bg_color=GRAY, align='right', num_format='#,##0', font_color='#FF0000')
        f_sum_n = F(bold=True, bg_color=GRAY, align='right', num_format='General', font_color='#FF0000')
        f_sum_p = F(bold=True, bg_color='#FFF2CC', align='right', num_format='0.0%', font_color='#9C0006')
        f_sum_r = F(bold=True, bg_color=GRAY, align='right', num_format='0.0%', font_color='#FF0000')
        f_sum_t = F(bold=True, bg_color=GRAY, align='center', text_wrap=True, font_color='#1F3864')
        f_brief = F(bold=True, align='left')
        f_wk_lbl = F(bold=True, font_color='#1F4E79', bg_color='#DDEBF7', align='left', text_wrap=True, font_size=11)
        f_wk_val = F(align='left', text_wrap=True, font_size=11)
        f_wk_empty = F(italic=True, font_color='#7F7F7F', align='left', font_size=11)
        f_foot = book.add_format({'font_name': 'Times New Roman', 'font_size': 10, 'italic': True, 'font_color': '#64748B'})
        f_sign = book.add_format({'font_name': 'Times New Roman', 'font_size': 13, 'bold': True, 'align': 'center'})
        f_sign_note = book.add_format({'font_name': 'Times New Roman', 'font_size': 11, 'italic': True, 'align': 'center', 'font_color': '#64748B'})
        cf_ok = book.add_format({'font_color': '#006100', 'bg_color': '#E2EFDA'})
        cf_rk_ok = book.add_format({'font_color': '#006100'})
        cf_rk_bad = book.add_format({'font_color': '#C00000'})

        used_sheets = set()
        store_comments = data.get('store_comments') or {}
        for staff in ordered:
            st = staff[0]
            sl = sales.get(st['store_id']) or {'target': 0, 'revenue': 0}
            raw_name = _re.sub(r'[\[\]:*?/\\]', ' ', st['store'] or 'Cua hang').strip()[:31] or 'Cua hang'
            sname, idx_dup = raw_name, 2
            while sname.lower() in used_sheets:
                suf = ' (%d)' % idx_dup
                sname = raw_name[:31 - len(suf)] + suf
                idx_dup += 1
            used_sheets.add(sname.lower())

            ws = book.add_worksheet(sname)
            ws.hide_gridlines(2)
            self._perf_xlsx_banner(book, ws, ncol, C_TOT, 'BÁO CÁO HIỆU SUẤT NHÂN VIÊN BÁN HÀNG & DOANH SỐ · THÁNG %s' % data['month_label'],
                                   'Đánh giá hiệu suất từng nhân viên bán hàng: nhóm công việc checklist, hoàn thành việc, kỷ luật, doanh số, thái độ'
                                   ' · Cửa hàng %s · ASM %s' % (st['store'], st['asm']))
            br, hr = 4, 5
            ws.merge_range(br, 0, br, 3, 'THÔNG TIN NHÂN SỰ', f_band_ns)
            ws.merge_range(br, C_TG, br, C_RKT, 'CHỈ TIÊU & DOANH THU THỰC TẾ', f_band_sl)
            if ng > 1:
                ws.merge_range(br, C_G0, br, C_G0 + ng - 1, 'ĐIỂM ĐÁNH GIÁ CHECKLIST CÔNG VIỆC', f_band_ck)
            elif ng == 1:
                ws.write(br, C_G0, 'ĐIỂM CHECKLIST', f_band_ck)
            ws.merge_range(br, C_TOT, br, C_RANK, 'TỔNG HỢP HIỆU SUẤT', f_band_sm)
            ws.set_row(br, 26)
            for c, h in enumerate(headers):
                fmt = f_head_ns if c < C_TG else f_head_sl if c <= C_RKT else f_head_ck if c < C_TOT else f_head_sm
                ws.write(hr, c, h, fmt)
            ws.set_row(hr, 44)
            first = hr + 1
            last = first + len(staff) - 1
            r_sum = last + 1
            r = first
            for i, x in enumerate(staff, 1):
                ws.write_number(r, 0, i, f_c)
                ws.write_string(r, 1, st['store'], f_cb)
                ws.write_string(r, 2, x['name'] + (' (CHT)' if x.get('is_cht') else ''), f_name)
                ws.write_string(r, 3, x.get('code') or '-', f_cb)
                ws.write_number(r, C_TG, x.get('target_nv') or 0, f_money)
                ws.write_number(r, C_REV, x.get('revenue') or 0, f_money)
                ws.write_formula(r, C_PCT, '=IF(%s>0,%s/%s,"")' % (cell(r, C_TG), cell(r, C_REV), cell(r, C_TG)), f_pct)
                ws.write_formula(r, C_RKT, '=IF(%s>0,IF(%s>=1,"ĐẠT","CHƯA ĐẠT"),"-")' % (cell(r, C_TG), cell(r, C_PCT)), f_rkt)
                for j, k in enumerate(g_keys):
                    ws.write_number(r, C_G0 + j, x.get(k) or 0.0, f_num)
                ws.write_formula(r, C_TOT, ('=SUM(%s:%s)' % (cell(r, C_G0), cell(r, C_G0 + ng - 1))) if ng else '=0', f_tot, x.get('tasks_total') or 0.0)
                if x.get('avg_pct') is not None:
                    ws.write_number(r, C_RATE, x['avg_pct'] / 100.0, f_rate)
                else:
                    ws.write_string(r, C_RATE, '-', f_c)
                ws.write_string(r, C_RANK, x.get('rank_short') or '-', f_rank)
                ws.set_row(r, 26)
                r += 1
            # dòng tổng cộng cửa hàng (công thức)
            ws.merge_range(r_sum, 0, r_sum, 3, 'TỔNG CỘNG CỬA HÀNG %s' % st['store'], f_sum_l)
            for c in (C_TG, C_REV):
                ws.write_formula(r_sum, c, '=SUM(%s:%s)' % (cell(first, c), cell(last, c)), f_sum_m)
            ws.write_formula(r_sum, C_PCT, '=IF(%s>0,%s/%s,"")' % (cell(r_sum, C_TG), cell(r_sum, C_REV), cell(r_sum, C_TG)), f_sum_p)
            ws.write_formula(r_sum, C_RKT, '=IF(%s>0,IF(%s>=1,"ĐẠT","CHƯA ĐẠT"),"-")' % (cell(r_sum, C_TG), cell(r_sum, C_PCT)), f_sum_t)
            for c in range(C_G0, C_TOT + 1):
                ws.write_formula(r_sum, c, '=SUM(%s:%s)' % (cell(first, c), cell(last, c)), f_sum_n)
            ws.write_formula(r_sum, C_RATE, '=IFERROR(AVERAGE(%s:%s),"-")' % (cell(first, C_RATE), cell(last, C_RATE)), f_sum_r)
            ws.write_blank(r_sum, C_RANK, None, f_sum_t)
            ws.set_row(r_sum, 34)
            # % >= 100%: nền xanh lá nhạt
            ws.conditional_format('%s:%s' % (cell(first, C_PCT), cell(r_sum, C_PCT)),
                                  {'type': 'cell', 'criteria': '>=', 'value': 1, 'format': cf_ok})
            # Xếp loại Target: xanh = ĐẠT TARGET, đỏ = CHƯA ĐẠT TARGET
            rk = '%s:%s' % (cell(first, C_RKT), cell(r_sum, C_RKT))
            ws.conditional_format(rk, {'type': 'cell', 'criteria': '==', 'value': '"ĐẠT"', 'format': cf_rk_ok})
            ws.conditional_format(rk, {'type': 'cell', 'criteria': '==', 'value': '"CHƯA ĐẠT"', 'format': cf_rk_bad})
            # dòng tóm tắt cửa hàng
            r = r_sum + 1
            pct_txt = ('%s%%' % ('%.1f' % (100.0 * sl['revenue'] / sl['target'])).replace('.', ',').replace(',0%', '%')) if sl['target'] else '-'
            ws.merge_range(r, 0, r, ncol - 1, 'Tóm tắt CH %s: Target %s đ | Thực đạt %s đ | Hoàn thành %s' % (
                st['store'], '{:,.0f}'.format(sl['target'] or 0).replace(',', '.'),
                '{:,.0f}'.format(sl['revenue'] or 0).replace(',', '.'), pct_txt), f_brief)
            ws.set_row(r, 30)
            r += 1
            for wk in store_comments.get(st['store_id']) or []:
                ws.merge_range(r, 0, r, 1, '%s (%s)' % (wk['label'], wk['range']), f_wk_lbl)
                items = wk.get('items') or []
                if items:
                    txt = '\n'.join(
                        ('%s%s: %s' % (cm['user'], (' (%s)' % cm['date']) if cm.get('date') else '', cm['comment'])
                         if cm.get('user') else cm['comment'])
                        for cm in items
                    )
                    ws.merge_range(r, 2, r, ncol - 1, txt, f_wk_val)
                    ws.set_row(r, max(30, 16 * (txt.count('\n') + 1)))
                else:
                    ws.merge_range(r, 2, r, ncol - 1, 'Chưa có nhận xét', f_wk_empty)
                    ws.set_row(r, 30)
                r += 1

            r += 1
            ws.write_string(r, 0, 'Ghi chú: Target NV lấy từ Phân Bổ Target (Target CH x Phân bổ %%); Doanh thu đạt lấy từ Doanh thu theo ngày (đã lưu); '
                                  'các cột %%, tổng tự động tính bằng công thức. Cập nhật: %s' % data['updated_at'], f_foot)
            r += 3
            third = max(1, ncol // 3)
            ws.merge_range(r, 0, r, third - 1, 'NGƯỜI LẬP', f_sign)
            ws.merge_range(r, third, r, 2 * third - 1, 'TRƯỞNG BỘ PHẬN', f_sign)
            ws.merge_range(r, 2 * third, r, ncol - 1, 'BAN GIÁM ĐỐC', f_sign)
            ws.merge_range(r + 1, 0, r + 1, third - 1, '(Ký, ghi rõ họ tên)', f_sign_note)
            ws.merge_range(r + 1, third, r + 1, 2 * third - 1, '(Ký, ghi rõ họ tên)', f_sign_note)
            ws.merge_range(r + 1, 2 * third, r + 1, ncol - 1, '(Ký, ghi rõ họ tên)', f_sign_note)
            for c, w in enumerate(widths[:ncol]):
                ws.set_column(c, c, w)
            ws.freeze_panes(hr + 1, 4)
            ws.set_landscape()
            ws.set_paper(9)
            ws.fit_to_pages(1, 0)
            ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
            ws.repeat_rows(br, hr)
        book.close()
        return {'name': 'Bao_cao_hieu_suat_NVBH_%s.xlsx' % fields.Date.context_today(self).strftime('%Y%m%d'),
                'data': base64.b64encode(buf.getvalue()).decode()}
