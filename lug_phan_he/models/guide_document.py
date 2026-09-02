# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError


class LinkqGuideDocument(models.Model):
    _name = "linkq.guide.document"
    _description = "Tài liệu hướng dẫn LinkQ ERP"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    file = fields.Binary(string="File", attachment=True)
    file_name = fields.Char()
    file_kind = fields.Selection(
        [("pdf", "PDF"), ("xlsx", "XLSX"), ("other", "Khác")],
        default="pdf",
        required=True,
    )
    file_size_label = fields.Char()
    note = fields.Char()
    perm_view = fields.Boolean(string="User xem", default=True)
    perm_download = fields.Boolean(string="User tải về", default=True)

    def _size_label(self):
        self.ensure_one()
        if self.file_size_label:
            return self.file_size_label
        data = self.file
        if not data:
            return "—"
        raw = data if isinstance(data, (bytes, bytearray)) else False
        n = len(raw) if raw else 0
        if n > 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        if n > 1024:
            return f"{int(n / 1024)} KB"
        return f"{n} B"

    def _kind_meta(self):
        self.ensure_one()
        if self.file_kind == "xlsx":
            return "xlsx", "fa fa-file-excel-o text-success", "btn-success"
        return "pdf", "fa fa-file-pdf-o text-danger", "btn-primary"

    def _can_manage_docs(self):
        user = self.env.user
        return bool(
            self.env.su
            or user.has_group("base.group_system")
            or user.has_group("lug_phan_he.group_phan_he_admin")
        )

    def action_delete_guide_document(self):
        self.ensure_one()
        if not self._can_manage_docs():
            raise AccessError("Bạn không có quyền xóa tài liệu hướng dẫn.")
        name = self.name
        self.unlink()
        return {"ok": True, "name": name}

    @api.model
    def get_guide_documents(self):
        recs = self.search([])
        is_admin = self._can_manage_docs()
        docs = []
        for rec in recs:
            if not is_admin and not rec.perm_view:
                continue
            kind, icon, btn = rec._kind_meta()
            updated = rec.write_date and fields.Datetime.context_timestamp(
                rec, rec.write_date
            ).strftime("%d/%m/%Y")
            has_file = bool(rec.file)
            can_dl = is_admin or rec.perm_download
            docs.append(
                {
                    "key": f"doc-{rec.id}",
                    "id": rec.id,
                    "name": rec.name,
                    "kind": kind.upper(),
                    "icon": icon,
                    "btn": btn,
                    "size": rec._size_label(),
                    "updated": updated or "",
                    "has_file": has_file,
                    "can_delete": is_admin,
                    "can_download": can_dl,
                    "view_url": f"/web/content/linkq.guide.document/{rec.id}/file/{rec.file_name or rec.name}" if has_file else "",
                    "download_url": (
                        f"/web/content/linkq.guide.document/{rec.id}/file/{rec.file_name or rec.name}?download=true"
                        if has_file and can_dl
                        else ""
                    ),
                }
            )
        return docs

    @api.model
    def get_guide_manage_rows(self):
        if not self._can_manage_docs():
            raise AccessError("Bạn không có quyền quản lý tài liệu hướng dẫn.")
        rows = []
        for rec in self.search([]):
            kind, _icon, _btn = rec._kind_meta()
            rows.append(
                {
                    "id": rec.id,
                    "name": rec.name or "",
                    "file_name": rec.file_name or "",
                    "size": rec._size_label(),
                    "kind": kind,
                    "perm_view": bool(rec.perm_view),
                    "perm_download": bool(rec.perm_download),
                }
            )
        return rows

    @api.model
    def save_guide_rows(self, rows):
        if not self._can_manage_docs():
            raise AccessError("Bạn không có quyền quản lý tài liệu hướng dẫn.")
        keep_ids = []
        for idx, row in enumerate(rows or []):
            name = (row.get("name") or "").strip() or "Tài liệu mới"
            fname = (row.get("file_name") or "").strip()
            kind = "xlsx" if fname.lower().endswith((".xlsx", ".xls")) else "pdf"
            if fname.lower().endswith((".doc", ".docx", ".txt")):
                kind = "other"
            vals = {
                "name": name,
                "sequence": (idx + 1) * 10,
                "file_name": fname,
                "file_kind": kind,
                "file_size_label": row.get("size") or "",
                "perm_view": bool(row.get("perm_view")),
                "perm_download": bool(row.get("perm_download")),
            }
            raw = row.get("file_b64") or ""
            if raw:
                if "," in raw[:80]:
                    raw = raw.split(",", 1)[-1]
                vals["file"] = raw
            rid = int(row.get("id") or 0)
            rec = self.browse(rid) if rid else self.browse()
            if rec.exists():
                rec.write(vals)
            else:
                rec = self.create(vals)
            keep_ids.append(rec.id)
        extras = self.search([("id", "not in", keep_ids)]) if keep_ids else self.search([])
        extras.unlink()
        return {"ok": True, "count": len(keep_ids)}
