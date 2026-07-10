import os

from odoo import http
from odoo.http import content_disposition, request

_LEAVE_FORM_TEMPLATE_FILENAME = "Đơn xin nghỉ phép.docx"


class HrLeaveDashboardDepartmentController(http.Controller):
    @http.route(
        "/hr_leave/download_leave_form_template",
        type="http",
        auth="user",
        readonly=True,
    )
    def download_leave_form_template(self):
        module_root = os.path.dirname(os.path.dirname(__file__))
        template_path = os.path.join(
            module_root,
            "static",
            "download",
            "Don_xin_nghi_phep_mau.docx",
        )
        if not os.path.isfile(template_path):
            return request.not_found()
        with open(template_path, "rb") as template_file:
            payload = template_file.read()
        return request.make_response(
            payload,
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                (
                    "Content-Disposition",
                    content_disposition(_LEAVE_FORM_TEMPLATE_FILENAME),
                ),
            ],
        )
