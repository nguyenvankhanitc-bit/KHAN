# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_LUG_DEFAULT_STAGES = [
    ("1", "CHUẨN BỊ & KHẢO SÁT", 10),
    ("2", "TRIỂN KHAI & BÁN HÀNG", 20),
    ("3", "LẮP ĐẶT & HOÀN THIỆN", 30),
    ("4", "NGHIỆM THU & BÀN GIAO", 40),
    ("5", "BẢO HÀNH & HỖ TRỢ", 50),
    ("6", "ĐÓNG DỰ ÁN", 60),
]


class LugProjectStage(models.Model):
    _name = "lug.project.stage"
    _description = "Giai đoạn dự án"
    _order = "sequence, id"

    project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        required=True,
        ondelete="cascade",
        index=True,
    )
    template_id = fields.Many2one(
        "lug.project.phase",
        string="Mẫu giai đoạn",
        ondelete="set null",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)
    code = fields.Char(string="STT", index=True)
    name = fields.Char(string="Tên giai đoạn", required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Phụ trách giai đoạn",
        domain="[('share', '=', False)]",
        index=True,
    )
    supervisor_id = fields.Many2one(
        "res.users",
        string="Giám sát",
        domain="[('share', '=', False)]",
        index=True,
    )
    date_start = fields.Date(string="Ngày bắt đầu")
    date_end = fields.Date(string="Ngày kết thúc")
    description = fields.Text(string="Mô tả giai đoạn")
    task_ids = fields.One2many(
        "project.task",
        "lug_stage_id",
        string="Danh sách công việc",
    )
    task_count = fields.Integer(
        string="Số lượng việc",
        compute="_compute_stage_metrics",
    )
    total_cost = fields.Float(
        string="Tổng chi phí giai đoạn",
        compute="_compute_stage_metrics",
        digits=(16, 0),
    )

    @api.depends("name", "code")
    def _compute_display_name(self):
        for rec in self:
            code = (rec.code or "").strip()
            name = rec.name or ""
            rec.display_name = ("GIAI ĐOẠN %s: %s" % (code, name)) if code else name

    @api.depends("task_ids", "task_ids.lug_cost")
    def _compute_stage_metrics(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)
            rec.total_cost = sum(rec.task_ids.mapped("lug_cost"))

    @api.constrains("date_start", "date_end")
    def _check_stage_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError("Ngày kết thúc giai đoạn phải sau hoặc bằng ngày bắt đầu.")

    @api.model
    def _lug_template_rows(self):
        templates = self.env["lug.project.phase"].search(
            [("active", "=", True)],
            order="sequence, code, id",
        )
        if templates:
            return [
                {
                    "template_id": template.id,
                    "code": template.code,
                    "name": template.name,
                    "sequence": template.sequence,
                }
                for template in templates
            ]
        return [
            {"code": code, "name": name, "sequence": seq}
            for code, name, seq in _LUG_DEFAULT_STAGES
        ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not (vals.get("name") or "").strip():
                vals["name"] = "Giai đoạn mới"
            if not vals.get("code") and vals.get("project_id"):
                siblings = self.search([("project_id", "=", vals["project_id"])])
                nums = [
                    int(code)
                    for code in siblings.mapped("code")
                    if code and str(code).isdigit()
                ]
                vals["code"] = str((max(nums) if nums else 0) + 1)
            if not vals.get("sequence"):
                code = vals.get("code") or "0"
                vals["sequence"] = int(code) * 10 if str(code).isdigit() else 10
        return super().create(vals_list)
