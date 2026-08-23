# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = "project.task"

    lug_stage_id = fields.Many2one(
        "lug.project.stage",
        string="Giai đoạn",
        ondelete="cascade",
        index=True,
        copy=False,
        domain="[('project_id', '=', project_id)]",
    )
    lug_cost = fields.Float(string="Chi phí", default=0.0, digits=(16, 0))
    lug_phase = fields.Selection(
        [
            ("1", "Giai đoạn 1: CHUẨN BỊ & KHẢO SÁT"),
            ("2", "Giai đoạn 2: TRIỂN KHAI & BÁN HÀNG"),
            ("3", "Giai đoạn 3: LẮP ĐẶT & HOÀN THIỆN"),
            ("4", "Giai đoạn 4: NGHIỆM THU & BÀN GIAO"),
            ("5", "Giai đoạn 5: BẢO HÀNH & HỖ TRỢ"),
            ("6", "Giai đoạn 6: ĐÓNG DỰ ÁN"),
        ],
        string="Giai đoạn",
        index=True,
    )
    lug_pic_id = fields.Many2one(
        "res.users",
        string="Người phụ trách",
        domain="[('share', '=', False)]",
        index=True,
        tracking=True,
    )
    lug_supervisor_id = fields.Many2one(
        "res.users",
        string="Người giám sát",
        domain="[('share', '=', False)]",
        index=True,
        tracking=True,
    )
    lug_done_date = fields.Date(string="Ngày hoàn thành", copy=False)
    lug_result = fields.Char(string="Kết quả")
    lug_note = fields.Char(string="Ghi chú")
    lug_status = fields.Selection(
        [
            ("todo", "Chưa bắt đầu"),
            ("progress", "Đang thực hiện"),
            ("review", "Chờ duyệt"),
            ("done", "Hoàn thành"),
            ("cancel", "Hủy"),
        ],
        string="Trạng thái",
        default="todo",
        required=True,
        index=True,
        tracking=True,
    )
    lug_progress = fields.Integer(
        string="Tiến độ công việc",
        default=0,
        help="Phần trăm hoàn thành (0–100).",
    )
    lug_timeleft = fields.Char(
        string="Timeleft",
        compute="_compute_lug_timeleft",
    )
    lug_line_stt = fields.Char(
        string="STT",
        compute="_compute_lug_line_stt",
    )

    @api.depends(
        "project_id",
        "lug_stage_id",
        "lug_stage_id.code",
        "lug_stage_id.task_ids",
        "lug_stage_id.task_ids.sequence",
        "sequence",
    )
    def _compute_lug_line_stt(self):
        self.lug_line_stt = False
        staged = self.filtered("lug_stage_id")
        for stage in staged.mapped("lug_stage_id"):
            tasks = stage.task_ids.sorted(lambda task: (task.sequence or 0, task.id or 0))
            code = stage.code or "0"
            for index, task in enumerate(tasks, 1):
                if task in self:
                    task.lug_line_stt = "%s.%s" % (code, index)
        orphans = self - staged
        for project in orphans.mapped("project_id"):
            tasks = orphans.filtered(lambda task: task.project_id == project).sorted(
                lambda task: (task.sequence or 0, task.id or 0)
            )
            for index, task in enumerate(tasks, 1):
                task.lug_line_stt = str(index)

    @api.depends("date_deadline", "lug_done_date", "lug_status")
    def _compute_lug_timeleft(self):
        today = fields.Date.context_today(self)
        for rec in self:
            deadline = fields.Date.to_date(rec.date_deadline) if rec.date_deadline else False
            if not deadline:
                rec.lug_timeleft = "none|—"
                continue
            if rec.lug_status == "done" and rec.lug_done_date:
                delta = (rec.lug_done_date - deadline).days
                rec.lug_timeleft = "done|%s ngày" % delta
            elif rec.lug_status == "done":
                rec.lug_timeleft = "done|Hoàn thành"
            else:
                delta = (deadline - today).days
                if delta >= 0:
                    rec.lug_timeleft = "ok|%s ngày" % delta
                else:
                    rec.lug_timeleft = "late|%s ngày" % abs(delta)

    def _lug_apply_stage_defaults(self, vals):
        stage_id = vals.get("lug_stage_id")
        if not stage_id:
            return vals
        stage = self.env["lug.project.stage"].browse(stage_id)
        if not stage.exists():
            return vals
        if not vals.get("project_id") and stage.project_id:
            vals["project_id"] = stage.project_id.id
        codes = {key for key, _label in self._fields["lug_phase"].selection}
        if "lug_phase" not in vals and stage.code in codes:
            vals["lug_phase"] = stage.code
        return vals

    @api.onchange("lug_stage_id")
    def _onchange_lug_stage_id(self):
        if self.lug_stage_id:
            self.project_id = self.lug_stage_id.project_id
            codes = {key for key, _label in self._fields["lug_phase"].selection}
            if self.lug_stage_id.code in codes:
                self.lug_phase = self.lug_stage_id.code

    @api.onchange("lug_pic_id")
    def _onchange_lug_pic_id(self):
        if self.lug_pic_id:
            self.user_ids = self.lug_pic_id

    @api.onchange("lug_status")
    def _onchange_lug_status(self):
        if self.lug_status == "done" and not self.lug_done_date:
            self.lug_done_date = fields.Date.context_today(self)
        if self.lug_status == "progress" and not self.lug_result:
            self.lug_result = "Đang thực hiện"
        if self.lug_status == "done" and not self.lug_result:
            self.lug_result = "Hoàn thành"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals = self._lug_apply_stage_defaults(vals)
            if not (vals.get("name") or "").strip():
                vals["name"] = "Công việc mới"
            pic = vals.get("lug_pic_id")
            if pic and not vals.get("user_ids"):
                vals["user_ids"] = [(6, 0, [pic])]
            if vals.get("lug_status") == "done" and not vals.get("lug_done_date"):
                vals["lug_done_date"] = fields.Date.context_today(self)
        return super().create(vals_list)

    def write(self, vals):
        vals = self._lug_apply_stage_defaults(vals)
        pic = vals.get("lug_pic_id")
        if pic and "user_ids" not in vals:
            vals = dict(vals, user_ids=[(6, 0, [pic])])
        res = super().write(vals)
        if vals.get("lug_status") == "done":
            to_fill = self.filtered(lambda rec: not rec.lug_done_date)
            if to_fill:
                super(ProjectTask, to_fill).write(
                    {"lug_done_date": fields.Date.context_today(self)}
                )
        return res

    @api.constrains("lug_stage_id", "project_id")
    def _check_lug_stage_project(self):
        for rec in self:
            if rec.lug_stage_id and rec.project_id and rec.lug_stage_id.project_id != rec.project_id:
                raise ValidationError("Công việc phải cùng dự án với giai đoạn.")

    @api.constrains("lug_progress")
    def _check_lug_progress(self):
        for rec in self:
            if rec.lug_progress < 0 or rec.lug_progress > 100:
                raise ValidationError("Tiến độ công việc phải từ 0 đến 100.")
