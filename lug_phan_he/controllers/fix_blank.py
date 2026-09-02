# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PhanHeFixBlank(http.Controller):
    @http.route("/web/fix-blank", type="http", auth="public", csrf=False)
    def fix_blank(self, **kwargs):
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Xóa cache Odoo</title></head>
<body style="font-family:sans-serif;padding:40px">
<p>Đang xóa Service Worker và cache trình duyệt...</p>
<script>
(async () => {
  try {
    if (navigator.serviceWorker) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch (e) {}
  location.replace("/web/login");
})();
</script>
</body></html>
"""
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
