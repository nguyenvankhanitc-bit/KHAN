# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class ProjectStageLine(models.Model):
    _name = "project.stage.line"
    _description = "Giai đoạn dự án"
    _order = "sequence, id"

    name = fields.Char(string="Nội dung giai đoạn", required=False)

    def init(self):
        self.env.cr.execute(
            'ALTER TABLE project_stage_line ALTER COLUMN name DROP NOT NULL'
        )
    sequence = fields.Integer(default=10, index=True)
    project_id = fields.Many2one(
        "project.project",
        string="Dự án",
        required=True,
        ondelete="cascade",
        index=True,
    )
    task_ids = fields.One2many(
        "project.stage.task",
        "stage_id",
        string="Công việc chi tiết",
    )
    task_count = fields.Integer(
        string="Số công việc",
        compute="_compute_stage_metrics",
    )
    total_cost = fields.Float(
        string="Tổng chi phí",
        compute="_compute_stage_metrics",
        digits=(16, 0),
    )

    @api.depends("name", "sequence")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or "Nhập nội dung"

    @api.depends("task_ids", "task_ids.cost")
    def _compute_stage_metrics(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)
            rec.total_cost = sum(rec.task_ids.mapped("cost"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") is not None and not str(vals.get("name") or "").strip():
                vals["name"] = False
            if not vals.get("sequence") and vals.get("project_id"):
                siblings = self.search([("project_id", "=", vals["project_id"])])
                vals["sequence"] = (max(siblings.mapped("sequence") or [0]) + 10)
        return super().create(vals_list)

    def action_add_task_popup(self):
        self.ensure_one()
        if not self.id:
            raise UserError("Vui lòng lưu dự án trước khi thêm công việc.")
        view = self.env.ref("lug_project.view_project_stage_task_popup_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm công việc",
            "res_model": "project.stage.task",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {
                "default_stage_id": self.id,
                "default_project_id": self.project_id.id,
                "default_user_ids": [(6, 0, [self.project_id.lug_pic_id.id])]
                if self.project_id.lug_pic_id
                else [],
                "default_state": "draft",
            },
        }
