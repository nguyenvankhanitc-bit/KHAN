from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

_SKIP_RESEQ = "skip_special_director_order_line_resequence"
_DIRECTOR_KEY = "giám đốc"


def _seq_int(seq):
    if seq is False or seq is None:
        return 0
    return int(seq)


class HrLeaveTypeSpecialDirectorOrderLine(models.Model):
    _name = "hr.leave.type.special.director.order.line"
    _description = "Time Off Type — configurable director approval order"
    _order = "sequence, id"

    leave_type_id = fields.Many2one(
        comodel_name="hr.leave.type",
        string="Time Off Type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="STT", default=1)
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "leave_type_employee_director_unique",
            "unique(leave_type_id, employee_id)",
            "Each employee can only appear once in the director order list.",
        ),
    ]

    @api.constrains("employee_id")
    def _check_employee_director_job_title(self):
        for line in self:
            if not line.employee_id:
                continue
            title = line.employee_id.job_title or ""
            if title != _DIRECTOR_KEY:
                raise ValidationError(_("Chỉ được chọn nhân viên có chức danh Giám đốc."))

    @api.onchange("employee_id")
    def _onchange_resequence_lines_realtime(self):
        for line in self:
            lt = line.leave_type_id
            if not lt:
                continue
            for idx, sibling in enumerate(lt.special_director_order_line_ids, start=1):
                sibling.sequence = idx

    @api.model
    def _resequence_by_leave_type(self, leave_type_ids):
        if not leave_type_ids:
            return
        for lt_id in set(leave_type_ids):
            lines = self.search([("leave_type_id", "=", lt_id)], order="sequence,id")
            for idx, rec in enumerate(lines, start=1):
                if _seq_int(rec.sequence) != idx:
                    rec.with_context(**{_SKIP_RESEQ: True}).write({"sequence": idx})

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env["hr.leave.type.special.director.order.line"]
        for vals in vals_list:
            if "sequence" in vals and vals.get("sequence"):
                continue
            ltid = (
                vals.get("leave_type_id")
                or self.env.context.get("default_leave_type_id")
                or (
                    self.env.context.get("active_id")
                    if self.env.context.get("active_model") == "hr.leave.type"
                    else False
                )
            )
            if ltid:
                vals["leave_type_id"] = ltid
                sibs = Line.search([("leave_type_id", "=", ltid)])
                max_seq = max((_seq_int(s) for s in sibs.mapped("sequence")), default=0)
                vals["sequence"] = max_seq + 1
            else:
                vals["sequence"] = 1
        recs = super().create(vals_list)
        recs._resequence_by_leave_type(recs.mapped("leave_type_id").ids)
        return recs

    def write(self, vals):
        if self.env.context.get(_SKIP_RESEQ):
            return super().write(vals)
        old = self.mapped("leave_type_id").ids
        res = super().write(vals)
        new = self.mapped("leave_type_id").ids
        if "sequence" in vals or "leave_type_id" in vals:
            self._resequence_by_leave_type(old + new)
        return res

    def unlink(self):
        lt_ids = self.mapped("leave_type_id").ids
        res = super().unlink()
        self._resequence_by_leave_type(lt_ids)
        return res
