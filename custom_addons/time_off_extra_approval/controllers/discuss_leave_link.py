# Part of time_off_extra_approval — mobile-safe opens from Discuss (HTTP round-trip).

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class DiscussLeaveLink(http.Controller):
    @http.route(
        "/time_off_extra_approval/discuss_leave/<int:leave_id>/<string:token>",
        type="http",
        auth="user",
        methods=["GET"],
        readonly=True,
    )
    def discuss_open_leave(self, leave_id, token, **kw):
        """Verify token + session, then 303 to frontend path `/odoo/hr.leave/<id>` (or `/scoped_app/...`).

        Using the canonical pathname avoids legacy ``/web#id=&model=&view_type=`` handling that can
        mis-route phones after leaving the SPA (hash / `/web` round-trips behave inconsistently vs PC).
        """
        leave_admin = (
            request.env["hr.leave"]
            .sudo()
            .browse(int(leave_id))
            .exists()
            .filtered(lambda r: r._leave_discuss_link_verify_token(token))
        )
        if not leave_admin:
            raise NotFound()
        leave = leave_admin.with_user(request.env.user)
        try:
            leave.check_access("read")
        except AccessError:
            raise Forbidden() from None
        leave = leave[0]

        request.env["hr.leave"].action_discuss_mark_leave_notification_viewed(leave.id)

        ref = request.httprequest.headers.get("Referer") or ""
        base = "/scoped_app" if "/scoped_app/" in ref or ref.rstrip("/").endswith("/scoped_app") else "/odoo"
        location = f"{base}/hr.leave/{leave.id}"
        return request.redirect(location, code=303, local=True)
