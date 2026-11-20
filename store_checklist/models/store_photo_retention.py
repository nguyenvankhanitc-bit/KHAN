"""Lưu trữ hình ảnh & file PDF: xóa cuốn chiếu theo ngày / tháng / năm cho phiếu đánh giá / giám sát cửa hàng.

Hai phần độc lập (bật / tắt và thời gian lưu trữ riêng):
- Hình ảnh: store.audit.line.attachment_ids (bảng nối store_audit_line_attachment_rel) của dòng có Ngày giờ audit trước mốc ảnh.
- File PDF: PDF biên bản đã lưu (cache của báo cáo store_checklist.report_store_audit, tên "Bien-ban-*.pdf", gắn store.audit)
  của phiếu trước mốc PDF, cộng các bản PDF cũ đã lỗi thời (mỗi lần sửa phiếu sinh một bản mới, bản cũ không dùng lại).
Mốc = hôm nay giờ Việt Nam lùi N ngày (timedelta) / tháng / năm (relativedelta).
Giữ nguyên: phiếu, thông tin chung, tiêu chí, điểm, xếp loại, nhận xét, File biên bản tải lên, File khắc phục.
"""
import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
PREFIX = 'store_checklist.'
# (khóa bật/tắt, khóa giá trị, khóa đơn vị) của từng phần; khóa cũ giữ nguyên để không mất cấu hình đã lưu
KEYS = {
    'img': ('photo_purge_enabled', 'photo_retention_value', 'photo_retention_unit'),
    'pdf': ('photo_purge_pdf', 'pdf_retention_value', 'pdf_retention_unit'),
}
P_MONTHS_OLD = PREFIX + 'photo_retention_months'
P_BATCH = PREFIX + 'photo_purge_batch'
P_LAST = PREFIX + 'photo_purge_last'
DEFAULTS = {'img': (False, 24, 'month'), 'pdf': (False, 24, 'month')}
DEFAULT_BATCH = 200
UNITS = {'day': ('Ngày', 3650), 'month': ('Tháng', 240), 'year': ('Năm', 20)}
OTHER_RELS = [('store_audit_action_attachment_rel', 'attachment_id'), ('store_audit_minutes_attachment_rel', 'attachment_id')]
PDF_LIKE = 'Bien-ban-%.pdf'  # tên PDF do báo cáo biên bản tự lưu (xem report/store_audit_report.xml)


def _int(raw, default, lo, hi):
    if raw in (None, False, ''):  # get_param trả False khi chưa có tham số
        return default
    try:
        return min(max(int(raw), lo), hi)
    except (TypeError, ValueError):
        return default


class StorePhotoRetention(models.AbstractModel):
    _name = 'store.photo.retention'
    _description = 'Lưu trữ hình ảnh & file PDF phiếu đánh giá (xóa cuốn chiếu)'

    # ------------------------------------------------------------------ cấu hình
    def _check_admin(self):
        if not (self.env.su or self.env.user.has_group('base.group_system')):
            raise AccessError(_('Chỉ Quản trị viên mới được cấu hình Lưu trữ hình ảnh & file PDF.'))

    @api.model
    def _config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        cfg = {}
        for kind, (k_on, k_val, k_unit) in KEYS.items():
            d_on, d_val, d_unit = DEFAULTS[kind]
            unit = ICP.get_param(PREFIX + k_unit) or d_unit
            unit = unit if unit in UNITS else d_unit
            raw_val = ICP.get_param(PREFIX + k_val) or (ICP.get_param(P_MONTHS_OLD) if kind == 'img' else None) \
                or (ICP.get_param(PREFIX + KEYS['img'][1]) if kind == 'pdf' else None)
            on_raw = ICP.get_param(PREFIX + k_on)
            cfg[kind] = {'enabled': (on_raw == '1') if on_raw is not None else d_on,
                         'value': _int(raw_val, d_val, 1, UNITS[unit][1]), 'unit': unit}
        cfg['batch'] = _int(ICP.get_param(P_BATCH), DEFAULT_BATCH, 10, 5000)
        return cfg

    @api.model
    def _clean(self, vals):
        """Kiểm tra cấu hình gửi từ màn hình: {img: {enabled, value, unit}, pdf: {...}, batch}."""
        out = {}
        for kind, label in (('img', 'hình ảnh'), ('pdf', 'file PDF')):
            part = (vals or {}).get(kind) or {}
            unit = part.get('unit') or 'month'
            if unit not in UNITS:
                raise UserError(_('Đơn vị lưu trữ %s không hợp lệ.') % label)
            try:
                value = int(part.get('value'))
            except (TypeError, ValueError):
                raise UserError(_('Thời gian lưu trữ %s phải là số.') % label)
            if not 1 <= value <= UNITS[unit][1]:
                raise UserError(_('Thời gian lưu trữ %s phải từ 1 đến %s %s.') % (label, UNITS[unit][1], UNITS[unit][0].lower()))
            out[kind] = {'enabled': bool(part.get('enabled')), 'value': value, 'unit': unit}
        try:
            batch = int((vals or {}).get('batch'))
        except (TypeError, ValueError):
            raise UserError(_('Kích thước lô phải là số.'))
        if not 10 <= batch <= 5000:
            raise UserError(_('Kích thước lô (batch) phải từ 10 đến 5000.'))
        out['batch'] = batch
        return out

    @api.model
    def _cutoff(self, value, unit):
        """Mốc cuốn chiếu (giờ VN): Ngày -> timedelta(days), Tháng / Năm -> relativedelta; trả (ngày mốc, datetime UTC naive)."""
        today_vn = datetime.now(VN_TZ).date()
        if unit == 'day':
            cutoff_date = today_vn - timedelta(days=value)
        else:
            cutoff_date = today_vn - relativedelta(**{unit + 's': value})
        cutoff_utc = datetime.combine(cutoff_date, time.min, VN_TZ).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        return cutoff_date, cutoff_utc

    # ------------------------------------------------------------------ tìm đối tượng cần xóa
    @api.model
    def _candidate_line_ids(self, cutoff_utc, limit=None):
        """Dòng đánh giá có ảnh và Ngày giờ audit trước mốc ảnh."""
        self.env['store.audit.line'].flush_model(['audit_date'])
        self.env.cr.execute(
            """SELECT DISTINCT l.id FROM store_audit_line l
                 JOIN store_audit_line_attachment_rel r ON r.line_id = l.id
                WHERE l.audit_date < %s ORDER BY l.id""" + (' LIMIT %d' % int(limit) if limit else ''),
            [cutoff_utc])
        return [r[0] for r in self.env.cr.fetchall()]

    @api.model
    def _candidate_pdf_ids(self, cutoff_utc, limit=None):
        """PDF biên bản đã lưu cần xóa: của phiếu trước mốc PDF, hoặc bản lỗi thời (phiếu còn bản PDF mới hơn).
        Không bao giờ chọn File biên bản do người dùng tải lên."""
        self.env['store.audit'].flush_model(['audit_date'])
        self.env.cr.execute(
            """SELECT a.id FROM ir_attachment a
                 JOIN store_audit s ON s.id = a.res_id
                WHERE a.res_model = 'store.audit' AND a.mimetype = 'application/pdf' AND a.name LIKE %s
                  AND NOT EXISTS (SELECT 1 FROM store_audit_minutes_attachment_rel m WHERE m.attachment_id = a.id)
                  AND (s.audit_date < %s OR EXISTS (
                        SELECT 1 FROM ir_attachment b
                         WHERE b.res_model = 'store.audit' AND b.res_id = a.res_id AND b.mimetype = 'application/pdf'
                           AND b.name LIKE %s AND b.id > a.id))
                ORDER BY a.id""" + (' LIMIT %d' % int(limit) if limit else ''),
            [PDF_LIKE, cutoff_utc, PDF_LIKE])
        return [r[0] for r in self.env.cr.fetchall()]

    @api.model
    def _att_stats(self, att_ids):
        if not att_ids:
            return 0, 0
        self.env.cr.execute('SELECT count(*), coalesce(sum(file_size), 0) FROM ir_attachment WHERE id = ANY(%s)', [att_ids])
        return self.env.cr.fetchone()

    @api.model
    def _stats(self, cfg):
        """Mốc và số lượng sẽ xóa của từng phần theo cấu hình `cfg` (đã lưu hoặc đang xem trước)."""
        img, pdf = dict(cfg['img']), dict(cfg['pdf'])
        cutoff_date, cutoff_utc = self._cutoff(img['value'], img['unit'])
        line_ids = self._candidate_line_ids(cutoff_utc)
        photo_ids = []
        if line_ids:
            self.env.cr.execute('SELECT DISTINCT attachment_id FROM store_audit_line_attachment_rel WHERE line_id = ANY(%s)', [line_ids])
            photo_ids = [r[0] for r in self.env.cr.fetchall()]
        files, size = self._att_stats(photo_ids)
        img.update(cutoff=cutoff_date.strftime('%d/%m/%Y'), pending_lines=len(line_ids), pending_files=files, pending_size=size)
        cutoff_date, cutoff_utc = self._cutoff(pdf['value'], pdf['unit'])
        pdfs, pdf_size = self._att_stats(self._candidate_pdf_ids(cutoff_utc))
        pdf.update(cutoff=cutoff_date.strftime('%d/%m/%Y'), pending_pdfs=pdfs, pending_size=pdf_size)
        return {'img': img, 'pdf': pdf, 'batch': cfg['batch']}

    @api.model
    def get_settings(self):
        self._check_admin()
        try:
            last = json.loads(self.env['ir.config_parameter'].sudo().get_param(P_LAST) or '{}')
        except ValueError:
            last = {}
        cron = self.env.ref('store_checklist.cron_store_photo_purge', raise_if_not_found=False)
        return {
            **self._stats(self._config()),
            'last': last,
            'units': [{'id': k, 'name': v[0], 'max': v[1]} for k, v in UNITS.items()],
            'next_run': fields.Datetime.context_timestamp(self.with_context(tz='Asia/Ho_Chi_Minh'), cron.nextcall).strftime('%d/%m/%Y %H:%M')
            if cron and cron.nextcall and cron.active else '',
        }

    @api.model
    def preview(self, vals):
        """Xem trước mốc / số lượng khi đổi số hoặc đơn vị trên màn hình (chưa lưu)."""
        self._check_admin()
        return self._stats(self._clean(vals))

    @api.model
    def save_settings(self, vals):
        self._check_admin()
        cfg = self._clean(vals)
        ICP = self.env['ir.config_parameter'].sudo()
        for kind, (k_on, k_val, k_unit) in KEYS.items():
            ICP.set_param(PREFIX + k_on, '1' if cfg[kind]['enabled'] else '0')
            ICP.set_param(PREFIX + k_val, str(cfg[kind]['value']))
            ICP.set_param(PREFIX + k_unit, cfg[kind]['unit'])
        ICP.set_param(P_BATCH, str(cfg['batch']))
        _logger.info('store_checklist retention: cấu hình bởi %s -> ảnh %s, PDF %s, batch %s',
                     self.env.user.login, cfg['img'], cfg['pdf'], cfg['batch'])
        return self.get_settings()

    # ------------------------------------------------------------------ xóa cuốn chiếu
    @api.model
    def _unused(self, att_ids):
        """Lọc ra các ir.attachment không còn bảng nối nào trỏ tới."""
        keep = set()
        if att_ids:
            cr = self.env.cr
            for table, col in [('store_audit_line_attachment_rel', 'attachment_id')] + OTHER_RELS:
                cr.execute('SELECT to_regclass(%s)', [table])
                if cr.fetchone()[0]:
                    cr.execute('SELECT %s FROM %s WHERE %s = ANY(%%s)' % (col, table, col), [att_ids])
                    keep |= {r[0] for r in cr.fetchall()}
        return self.env['ir.attachment'].sudo().browse([a for a in att_ids if a not in keep]).exists()

    @api.model
    def _purge_batch(self, line_ids):
        """Gỡ ảnh khỏi một lô dòng (SQL trên bảng nối: không qua write() nên không vướng khóa chỉnh sửa phiếu cũ)
        rồi xóa các ir.attachment không còn nơi nào dùng. Trả (số liên kết gỡ, số file xóa, dung lượng)."""
        cr = self.env.cr
        cr.execute('SELECT DISTINCT attachment_id FROM store_audit_line_attachment_rel WHERE line_id = ANY(%s)', [line_ids])
        att_ids = [r[0] for r in cr.fetchall()]
        cr.execute('DELETE FROM store_audit_line_attachment_rel WHERE line_id = ANY(%s)', [line_ids])
        unlinked = cr.rowcount
        to_delete = self._unused(att_ids)
        size = sum(to_delete.mapped('file_size'))
        n_files = len(to_delete)
        to_delete.unlink()  # file trong filestore được Odoo dọn ở lần dọn rác filestore kế tiếp
        self.env['store.audit.line'].invalidate_model(['attachment_ids'])
        self.env['store.audit.action'].invalidate_model(['line_attachment_ids'])
        return unlinked, n_files, size

    @api.model
    def _purge_pdf_batch(self, pdf_ids):
        to_delete = self._unused(pdf_ids)
        size = sum(to_delete.mapped('file_size'))
        n = len(to_delete)
        to_delete.unlink()
        return n, size

    @api.model
    def run_purge(self, dry_run=False, manual=False, commit=True):
        """Chạy xóa cuốn chiếu (cron / Chạy ngay / Chạy thử). Mỗi phần chỉ chạy khi đang bật.
        dry_run=True: chỉ đếm, không xóa. Kết quả được lưu vào "Lần chạy gần nhất"."""
        if manual:
            self._check_admin()
        cfg = self._config()
        img_on, pdf_on = cfg['img']['enabled'], cfg['pdf']['enabled']
        if not img_on and not pdf_on:
            _logger.info('store_checklist retention: cả hình ảnh và PDF đang tắt, bỏ qua')
            res = {'time': datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S'), 'skipped': True,
                   'dry_run': bool(dry_run), 'manual': bool(manual)}
            if manual:
                self.env['ir.config_parameter'].sudo().set_param(P_LAST, json.dumps(res, ensure_ascii=False))
            return res
        stats = self._stats(cfg)
        start = datetime.now(VN_TZ)
        unit_txt = lambda p: '%s %s' % (p['value'], UNITS[p['unit']][0].lower())  # noqa: E731
        res = {'time': start.strftime('%d/%m/%Y %H:%M:%S'), 'dry_run': bool(dry_run), 'manual': bool(manual),
               'img_on': img_on, 'img_keep': unit_txt(cfg['img']), 'img_cutoff': stats['img']['cutoff'],
               'pdf_on': pdf_on, 'pdf_keep': unit_txt(cfg['pdf']), 'pdf_cutoff': stats['pdf']['cutoff'],
               'lines': 0, 'links': 0, 'files': 0, 'size': 0, 'pdfs': 0, 'pdf_size': 0, 'batches': 0, 'error': ''}
        _logger.info('store_checklist retention: BẮT ĐẦU ảnh=%s (giữ %s, mốc %s) PDF=%s (giữ %s, mốc %s) lô %s dry_run=%s manual=%s',
                     img_on, res['img_keep'], res['img_cutoff'], pdf_on, res['pdf_keep'], res['pdf_cutoff'],
                     cfg['batch'], dry_run, manual)
        try:
            if dry_run:
                if img_on:
                    res.update(lines=stats['img']['pending_lines'], files=stats['img']['pending_files'], size=stats['img']['pending_size'])
                if pdf_on:
                    res.update(pdfs=stats['pdf']['pending_pdfs'], pdf_size=stats['pdf']['pending_size'])
            else:
                _d, img_cut = self._cutoff(cfg['img']['value'], cfg['img']['unit'])
                while img_on:  # 1. ảnh cột Hình ảnh
                    batch = self._candidate_line_ids(img_cut, limit=cfg['batch'])
                    if not batch:
                        break
                    links, n_files, size = self._purge_batch(batch)
                    res.update(lines=res['lines'] + len(batch), links=res['links'] + links,
                               files=res['files'] + n_files, size=res['size'] + size, batches=res['batches'] + 1)
                    if commit:
                        self.env.cr.commit()  # mỗi lô một giao dịch nhỏ: không khóa bảng lâu
                    _logger.info('store_checklist retention: lô ảnh %s -> %s dòng, gỡ %s liên kết, xóa %s file (%s byte)',
                                 res['batches'], len(batch), links, n_files, size)
                _d, pdf_cut = self._cutoff(cfg['pdf']['value'], cfg['pdf']['unit'])
                while pdf_on:  # 2. PDF biên bản đã lưu
                    batch = self._candidate_pdf_ids(pdf_cut, limit=cfg['batch'])
                    if not batch:
                        break
                    n, size = self._purge_pdf_batch(batch)
                    res.update(pdfs=res['pdfs'] + n, pdf_size=res['pdf_size'] + size, batches=res['batches'] + 1)
                    if commit:
                        self.env.cr.commit()
                    _logger.info('store_checklist retention: lô PDF %s -> xóa %s file (%s byte)', res['batches'], n, size)
                    if not n:
                        break  # còn PDF nhưng đang được dùng ở nơi khác: dừng, tránh lặp vô hạn
        except Exception as e:
            res['error'] = str(e)[:300]
            _logger.exception('store_checklist retention: LỖI sau %s lô', res['batches'])
            if commit:
                self.env.cr.rollback()
        res['duration'] = round((datetime.now(VN_TZ) - start).total_seconds(), 1)
        self.env['ir.config_parameter'].sudo().set_param(P_LAST, json.dumps(res, ensure_ascii=False))
        if commit:
            self.env.cr.commit()
        _logger.info('store_checklist retention: KẾT THÚC %s', res)
        return res

    @api.model
    def _cron_purge_photos(self):
        self.run_purge()
