# -*- coding: utf-8 -*-

import base64

from odoo import api, fields, models


class ShiftGuideDocument(models.Model):
    _name = "shift.guide.document"
    _description = "Tài liệu hướng dẫn LinkQ ERP"
    _order = "sequence asc, id asc"

    sequence = fields.Integer(string="STT", default=10)
    name = fields.Char(string="Nội dung / Tiêu đề", required=True)
    file_data = fields.Binary(string="File hướng dẫn", attachment=True)
    file_name = fields.Char(string="Tên file")
    file_type = fields.Selection(
        [
            ("pdf", "PDF"),
            ("xlsx", "Excel (XLSX)"),
            ("docx", "Word (DOCX)"),
            ("other", "Khác"),
        ],
        string="Loại file",
        compute="_compute_file_meta",
        store=True,
    )
    file_size_text = fields.Char(string="Dung lượng", compute="_compute_file_meta", store=True)
    allow_view = fields.Boolean(
        string="Xem",
        default=True,
        help="Cho phép User xem tài liệu",
    )
    allow_download = fields.Boolean(
        string="Tải về",
        default=True,
        help="Cho phép User tải file về",
    )
    active = fields.Boolean(default=True)

    @api.depends("file_data", "file_name")
    def _compute_file_meta(self):
        for rec in self:
            if not rec.file_data:
                rec.file_size_text = ""
                rec.file_type = "other"
                continue
            try:
                raw = rec.file_data
                if isinstance(raw, bytes):
                    file_bytes = base64.b64decode(raw) if raw[:1] not in (b"%", b"P") else raw
                else:
                    file_bytes = base64.b64decode(raw)
                size_kb = len(file_bytes) / 1024
                if size_kb >= 1024:
                    rec.file_size_text = f"{size_kb / 1024:.1f} MB"
                else:
                    rec.file_size_text = f"{int(size_kb)} KB"
            except Exception:
                rec.file_size_text = ""
            fname = (rec.file_name or "").lower()
            if fname.endswith(".pdf"):
                rec.file_type = "pdf"
            elif fname.endswith((".xlsx", ".xls")):
                rec.file_type = "xlsx"
            elif fname.endswith((".docx", ".doc")):
                rec.file_type = "docx"
            else:
                rec.file_type = "other"
