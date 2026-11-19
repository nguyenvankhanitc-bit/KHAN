from odoo import http
from odoo.http import request


class StoreChecklistOpen(http.Controller):

    @http.route('/store_checklist/open/<int:check_id>', type='http', auth='user', website=False)
    def open_check(self, check_id, **kw):
        """Liên kết "Mở để đánh giá" trong tin nhắn OdooBot: ghi nhớ phiếu cần mở bằng cookie ngắn hạn rồi chuyển vào ứng dụng
        Checklist Audit (không phụ thuộc tham số trên URL vì thanh địa chỉ của Odoo có thể bỏ tham số lạ khi tải màn hình)."""
        resp = request.redirect('/odoo/action-store_checklist.action_store_shell?store_check=%s' % check_id)
        resp.set_cookie('store_check', str(check_id), max_age=180, path='/', samesite='Lax')
        return resp
