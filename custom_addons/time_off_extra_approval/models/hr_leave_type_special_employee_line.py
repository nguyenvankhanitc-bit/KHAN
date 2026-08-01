from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

_SKIP_SPECIAL_EMPLOYEE_RESEQUENCE = "skip_special_employee_line_resequence"

# Matches _ORG_CHART_STOP_JOB_POSITIONS / _ORG_CHART_STOP_JOB_POSITIONS_GIAM_SAT in responsible_approval.
_STOP_POSITION_SELECTION = [
    ("sale admin", "SALE ADMIN"),
    ("human resources manager", "Human Resources Manager"),
]

_LINE_KIND_OFFICE = "office"
_LINE_KIND_STORE = "store"


def _sequence_as_int(seq):
    if seq is False or seq is None:
        return 0
    return int(seq)


class HrLeaveTypeSpecialEmployeeLine(models.Model):
    _name = "hr.leave.type.special.employee.line"
    _description = "Time Off Type Special Employee Approval"
    _order = "line_kind, sequence, id"

    leave_type_id = fields.Many2one(
        comodel_name="hr.leave.type",
        string="Time Off Type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    line_kind = fields.Selection(
        selection=[
            (_LINE_KIND_OFFICE, "Office"),
            (_LINE_KIND_STORE, "Store"),
        ],
        string="Special employee kind",
        required=True,
        default=_LINE_KIND_OFFICE,
        index=True,
    )
    sequence = fields.Integer(string="STT", default=1)
    employee_hrm_id = fields.Char(
        string="Employee ID HRM",
        index=True,
        help="Store special employees: enter ID HRM; the employee is resolved automatically.",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
    )
    approval_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_leave_type_special_employee_approver_rel",
        column1="line_id",
        column2="employee_id",
        string="Approvals Employee",
        domain=[("user_id", "!=", False)],
        help="Store special employees: every selected employee must approve, in organization-chart order. "
        "Each employee must have an active internal user.",
    )
    readonly_notifier_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_leave_type_special_employee_notifier_rel",
        column1="line_id",
        column2="employee_id",
        string="Read only Notifier",
        domain=[("user_id", "!=", False)],
        help="Store special employees: receive a read-only Discuss DM when this employee submits a request.",
    )
    org_chart_stop_position = fields.Selection(
        selection=_STOP_POSITION_SELECTION,
        string="Stop at Job Position",
        help="Office special employees: org-chart walk stops (inclusive) at the first approver with this "
        "Job Position. Leave empty to use the default stop position for the employee's job title.",
    )

    _sql_constraints = [
        (
            "leave_type_employee_unique",
            "unique(leave_type_id, employee_id)",
            "Each employee can only appear once in the special list for this time off type.",
        ),
    ]

    @api.model
    def _employee_from_hrm_id(self, employee_hrm_id):
        employee_hrm_id = (employee_hrm_id or "").strip()
        if not employee_hrm_id:
            return self.env["hr.employee"]
        return (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([("id_hrm", "=", employee_hrm_id)], limit=1)
        )

    def _sibling_one2many_field(self):
        self.ensure_one()
        if self.line_kind == _LINE_KIND_STORE:
            return "special_store_employee_line_ids"
        return "special_director_employee_line_ids"

    @api.onchange("employee_hrm_id")
    def _onchange_employee_hrm_id(self):
        for line in self:
            if line.line_kind != _LINE_KIND_STORE:
                continue
            line.employee_hrm_id = (line.employee_hrm_id or "").strip()
            line.employee_id = line._employee_from_hrm_id(line.employee_hrm_id)
            if line.employee_hrm_id and not line.employee_id:
                return {
                    "warning": {
                        "title": _("ID HRM not found"),
                        "message": _("No employee was found with ID HRM %(id_hrm)s.")
                        % {"id_hrm": line.employee_hrm_id},
                    }
                }
        return None

    @api.onchange("employee_hrm_id", "employee_id", "line_kind")
    def _onchange_resequence_lines_realtime(self):
        """Keep STT 1..n while editing in the form (incl. popup), per kind."""
        for line in self:
            lt = line.leave_type_id
            if not lt:
                continue
            siblings = lt[line._sibling_one2many_field()]
            for idx, sibling in enumerate(siblings, start=1):
                sibling.sequence = idx

    @api.constrains("line_kind", "employee_hrm_id", "employee_id")
    def _check_employee_hrm_link(self):
        for line in self:
            if line.line_kind != _LINE_KIND_STORE:
                continue
            employee_hrm_id = (line.employee_hrm_id or "").strip()
            employee = line._employee_from_hrm_id(employee_hrm_id)
            if not employee:
                raise ValidationError(
                    _("No employee was found with ID HRM %(id_hrm)s.")
                    % {"id_hrm": employee_hrm_id or "—"}
                )
            if employee != line.employee_id:
                raise ValidationError(
                    _("ID HRM %(id_hrm)s does not match the linked employee.")
                    % {"id_hrm": employee_hrm_id}
                )

    @api.constrains("line_kind", "approval_employee_ids", "readonly_notifier_employee_ids")
    def _check_store_approvers_have_internal_users(self):
        for line in self:
            if line.line_kind != _LINE_KIND_STORE:
                continue
            if not line.approval_employee_ids:
                raise ValidationError(
                    _("Select at least one Approvals Employee.")
                )
            for employee in line.approval_employee_ids | line.readonly_notifier_employee_ids:
                if not employee.user_id or employee.user_id.share or not employee.user_id.active:
                    raise ValidationError(
                        _("%(employee)s must have an active internal user.")
                        % {"employee": employee.display_name}
                    )

    @api.model
    def _resequence_by_leave_type(self, leave_type_ids):
        """Pack STT to 1..n after create/write/unlink, separately per kind."""
        if not leave_type_ids:
            return
        for lt_id in set(leave_type_ids):
            for kind in (_LINE_KIND_OFFICE, _LINE_KIND_STORE):
                lines = self.search(
                    [("leave_type_id", "=", lt_id), ("line_kind", "=", kind)],
                    order="sequence,id",
                )
                for idx, rec in enumerate(lines, start=1):
                    if _sequence_as_int(rec.sequence) != idx:
                        rec.with_context(**{_SKIP_SPECIAL_EMPLOYEE_RESEQUENCE: True}).write(
                            {"sequence": idx}
                        )

    def _prepare_vals_employee_link(self, vals):
        """Resolve employee_id / employee_hrm_id according to line kind."""
        vals = dict(vals)
        kind = vals.get("line_kind") or self.env.context.get("default_line_kind") or _LINE_KIND_OFFICE
        if kind == _LINE_KIND_STORE or "employee_hrm_id" in vals:
            employee_hrm_id = (vals.get("employee_hrm_id") or "").strip()
            if employee_hrm_id:
                employee = self._employee_from_hrm_id(employee_hrm_id)
                if not employee:
                    raise ValidationError(
                        _("No employee was found with ID HRM %(id_hrm)s.")
                        % {"id_hrm": employee_hrm_id}
                    )
                vals["employee_hrm_id"] = employee_hrm_id
                vals["employee_id"] = employee.id
            elif vals.get("employee_id"):
                employee = self.env["hr.employee"].sudo().browse(vals["employee_id"])
                vals["employee_hrm_id"] = (employee.id_hrm or "").strip()
        elif vals.get("employee_id"):
            employee = self.env["hr.employee"].sudo().browse(vals["employee_id"])
            if employee.id_hrm and not vals.get("employee_hrm_id"):
                vals["employee_hrm_id"] = (employee.id_hrm or "").strip()
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env["hr.leave.type.special.employee.line"]
        prepared = []
        for vals in vals_list:
            vals = self._prepare_vals_employee_link(vals)
            if not vals.get("line_kind"):
                vals["line_kind"] = self.env.context.get("default_line_kind") or _LINE_KIND_OFFICE
            if "sequence" in vals and vals.get("sequence"):
                prepared.append(vals)
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
                siblings = Line.search(
                    [
                        ("leave_type_id", "=", ltid),
                        ("line_kind", "=", vals["line_kind"]),
                    ]
                )
                max_seq = max(
                    (_sequence_as_int(s) for s in siblings.mapped("sequence")),
                    default=0,
                )
                vals["sequence"] = max_seq + 1
            else:
                vals["sequence"] = 1
            prepared.append(vals)
        records = super().create(prepared)
        records._resequence_by_leave_type(records.mapped("leave_type_id").ids)
        return records

    def write(self, vals):
        if self.env.context.get(_SKIP_SPECIAL_EMPLOYEE_RESEQUENCE):
            return super().write(vals)
        vals = dict(vals)
        link_keys = {"employee_hrm_id", "employee_id"}
        if link_keys.intersection(vals) and len(self) == 1:
            kind = vals.get("line_kind") or self.line_kind
            if kind == _LINE_KIND_STORE or "employee_hrm_id" in vals:
                merged = dict(vals)
                merged.setdefault("line_kind", kind)
                resolved = self._prepare_vals_employee_link(merged)
                if "line_kind" not in vals:
                    resolved.pop("line_kind", None)
                vals = resolved
        old_lt = self.mapped("leave_type_id").ids
        res = super().write(vals)
        new_lt = self.mapped("leave_type_id").ids
        if "sequence" in vals or "leave_type_id" in vals or "line_kind" in vals:
            self._resequence_by_leave_type(old_lt + new_lt)
        return res

    def unlink(self):
        lt_ids = self.mapped("leave_type_id").ids
        res = super().unlink()
        self._resequence_by_leave_type(lt_ids)
        return res
