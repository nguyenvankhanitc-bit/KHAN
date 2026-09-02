# -*- coding: utf-8 -*-

from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.webmanifest import WebManifest as WebWebManifest
from odoo.http import request


class PhanHeHome(Home):
    def _login_redirect(self, uid, redirect=None):
        url = super()._login_redirect(uid, redirect=redirect)
        if not url or url in ("/odoo", "/web", "/"):
            return "/odoo?debug=1"
        return url


class PhanHeWebManifest(WebWebManifest):
    """Gỡ Service Worker đang cache trang /odoo trống (màn hình trắng)."""

    def _get_service_worker_content(self):
        return """
self.addEventListener("install", (event) => {
    self.skipWaiting();
});
self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
        await self.registration.unregister();
        const clients = await self.clients.matchAll({ type: "window" });
        for (const client of clients) {
            client.navigate(client.url);
        }
    })());
});
"""
