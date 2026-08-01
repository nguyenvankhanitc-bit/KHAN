import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import sql
from odoo.tools.translate import _
from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION

_logger = logging.getLogger(__name__)

# Allow self-service Time Off flows to flush stored computed fields on leave types
# (e.g. multi_step_approver_employee_*_id) without granting config write rights.
_ALLOW_WRITE_HR_LEAVE_TYPE = object()

_HANDOVER_ESCALATION_MIN_JOB_TITLE_KEY = "trưởng nhóm"
_HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION = []
_include = False
for _key, _label in JOB_TITLE_SELECTION:
    if _key == _HANDOVER_ESCALATION_MIN_JOB_TITLE_KEY:
        _include = True
    if _include:
        _HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION.append((_key, _label))
if not _HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION:
    _HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION = [
        ("trưởng bộ phận", "Trưởng bộ phận"),
        ("trưởng phòng", "Trưởng phòng"),
    ]


class HolidaysType(models.Model):
    _inherit = "hr.leave.type"

    def _check_access(self, operation):
        if (
            operation == "write"
            and self.env.context.get("_allow_write_hr_leave_type") is _ALLOW_WRITE_HR_LEAVE_TYPE
        ):
            return None
        return super()._check_access(operation)

    # Multi-step approval (demo) for Time Off requests.
    leave_validation_type = fields.Selection(
        selection_add=[
            ("multi_step_6", "6-step approval (Demo)"),
            ("employee_hr_responsibles", "Approve via employee HR responsibles"),
            ("vp_chain", "Store chain approval (by job title)"),
        ],
    )

    employee_responsible_approval_mode = fields.Selection(
        selection=[
            ("any", "Any responsible can approve"),
            ("all", "All responsibles must approve"),
            ("sequential", "Sequential approval (in order)"),
        ],
        string="Employee responsible approval mode",
        default="any",
        help="Applies when leave approval uses employee HR responsibles. "
        "In sequential mode, approvers are ordered by job title from team lead to director.",
    )

    employee_responsible_source = fields.Selection(
        selection=[
            ("manual", "HR responsibles on employee profile"),
            ("org_chart", "Organization chart (job title in management chain)"),
        ],
        string="Employee responsible source",
        default="manual",
        help="Manual: use HR responsibles configured on the employee. "
        "Org chart: walk up the manager chain and create one approval step per level with a linked internal user. "
        "In sequential mode, pre-director steps follow the org chart; final director step uses the employee department manager.",
    )

    employee_responsible_escalation_hours = fields.Float(
        string="Auto-escalate after (hours)",
        default=2.0,
        help="Sequential mode only: if the current approver does not act in time, request escalates to the next level.",
    )
    special_director_employee_line_ids = fields.One2many(
        comodel_name="hr.leave.type.special.employee.line",
        inverse_name="leave_type_id",
        string="Nhân viên đặc biệt văn phòng",
        domain=[("line_kind", "=", "office")],
        context={"default_line_kind": "office"},
        help="For listed office employees, approval remains sequential by org flow until Director level; "
        "then all internal users with Director title must approve (parallel or sequential).",
    )
    special_store_employee_line_ids = fields.One2many(
        comodel_name="hr.leave.type.special.employee.line",
        inverse_name="leave_type_id",
        string="Nhân viên đặc biệt cửa hàng",
        domain=[("line_kind", "=", "store")],
        context={"default_line_kind": "store"},
        help="Configure store special approval and read-only notification recipients by employee ID HRM.",
    )
    special_director_sequential_approval = fields.Boolean(
        string="Sequential director approval",
        default=False,
        help="For office special employees: when enabled, Director approval order follows the table below. "
        "When disabled, all Directors can approve in parallel.",
    )
    special_director_order_line_ids = fields.One2many(
        comodel_name="hr.leave.type.special.director.order.line",
        inverse_name="leave_type_id",
        string="Director approval order",
        help="Director list (Director title). Used only for office special employees when sequential "
        "director approval is enabled.",
    )
    handover_escalation_after_hours = fields.Float(
        string="Handover: escalate after (hours)",
        default=2.0,
        help="If nobody accepts handover within this period, escalation starts.",
    )
    handover_escalation_mode = fields.Selection(
        selection=[
            ("sequential", "Sequential"),
            ("direct", "Direct"),
        ],
        string="Handover: escalation progression",
        default="sequential",
        required=True,
        help="Sequential: escalate one management level at a time on the org chart. "
        "Direct: escalate immediately to the configured max job title on the requester's chain.",
    )
    handover_escalation_max_job_title = fields.Selection(
        selection=_HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION,
        string="Handover: max escalation job title",
        default="trưởng bộ phận",
        help="Maximum job title level used for handover escalation.",
    )
    handover_escalation_to_manager_hours = fields.Float(
        string="Handover: escalate to next level after (hours)",
        default=2.0,
        help="When max level is Department Manager: wait this many hours after Department Head before escalating further.",
    )
    handover_cancel_if_max_unresponsive = fields.Boolean(
        string="Handover: auto-cancel at max escalation level",
        default=False,
        help="If enabled, request auto-cancels when it reaches max escalation level and still has no assignee in time.",
    )
    handover_cancel_after_max_hours = fields.Float(
        string="Handover: cancel after timeout at max level (hours)",
        default=2.0,
        help="Used only when auto-cancel at max level is enabled.",
    )
    approval_escalation_after_hours = fields.Float(
        string="Approval: escalate after (hours)",
        default=2.0,
        help="If nobody approves within this period, escalation starts.",
    )
    approval_escalation_mode = fields.Selection(
        selection=[
            ("sequential", "Sequential"),
            ("direct", "Direct"),
        ],
        string="Approval: escalation progression",
        default="sequential",
        required=True,
        help="Sequential: escalate one management level at a time on the org chart. "
        "Direct: escalate immediately to the configured max job title on the requester's chain.",
    )
    approval_escalation_max_job_title = fields.Selection(
        selection=_HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION,
        string="Approval: max escalation job title",
        default="trưởng bộ phận",
        help="Maximum job title level used for approval escalation.",
    )
    approval_escalation_to_manager_hours = fields.Float(
        string="Approval: escalate to next level after (hours)",
        default=2.0,
        help="When max level is Department Manager: wait this many hours after Department Head before escalating further.",
    )
    approval_cancel_if_max_unresponsive = fields.Boolean(
        string="Approval: auto-cancel at max escalation level",
        default=False,
        help="If enabled, request auto-cancels when it reaches max escalation level and still has no approver action in time.",
    )
    approval_cancel_after_max_hours = fields.Float(
        string="Approval: cancel after timeout at max level (hours)",
        default=2.0,
        help="Used only when auto-cancel at max level is enabled.",
    )

    # Extend allocation (Time Off allocation requests) approval options.
    # Note: this selection is used by `hr.leave.allocation` validation_type.
    allocation_validation_type = fields.Selection(
        selection_add=[
            ("manager", "Approve by time off manager"),
            ("leader", "Approve by department head"),
            ("multi_step_6", "6-step approval (Demo)"),
        ]
    )

    multi_approval_step_ids = fields.One2many(
        comodel_name="hr.leave.type.approval.step",
        inverse_name="leave_type_id",
        string="Multi-step approval steps (Demo)",
        help="Underlying configuration rows for 6-step approval.",
    )

    # Kept for backwards compatibility: Studio / old inherited views may still reference this field.
    multi_step_approver_sync = fields.Char(
        compute="_compute_multi_step_approver_sync",
        string="Multi-step approver sync key",
    )

    # Pool for multi-step approvers: users must be employees in this department tree (default: name ilike HR).
    multi_step_hr_source_department_id = fields.Many2one(
        comodel_name="hr.department",
        string="Approver source (department)",
        default=lambda self: self._default_multi_step_hr_department(),
        help="Step approvers are limited to internal users linked to employees in this department tree.",
    )

    _MULTI_STEP_EMPLOYEE_DOMAIN = (
        "['&', ('user_id', '!=', False), "
        "('department_id', 'child_of', multi_step_hr_source_department_id)]"
    )

    # Form: pick hr.employee (HR department); stored approver remains res.users on the step line.
    multi_step_approver_employee_1_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 1",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )
    multi_step_approver_employee_2_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 2",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )
    multi_step_approver_employee_3_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 3",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )
    multi_step_approver_employee_4_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 4",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )
    multi_step_approver_employee_5_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 5",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )
    multi_step_approver_employee_6_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Step 6",
        compute="_compute_multi_step_approver_employees",
        inverse="_inverse_multi_step_approver_employees",
        store=True,
        domain=_MULTI_STEP_EMPLOYEE_DOMAIN,
    )

    @api.model
    def _default_multi_step_hr_department(self):
        return self.env["hr.department"].search([("name", "ilike", "HR")], limit=1)

    @api.constrains("leave_validation_type", "employee_responsible_source", "employee_responsible_approval_mode")
    def _check_org_chart_requires_sequential(self):
        for lt in self:
            if (
                lt.leave_validation_type == "employee_hr_responsibles"
                and lt.employee_responsible_source == "org_chart"
                and lt.employee_responsible_approval_mode != "sequential"
            ):
                raise ValidationError(
                    _("Organization-chart approval requires 'Sequential approval (in order)' mode.")
                )

    @api.onchange("employee_responsible_source")
    def _onchange_employee_responsible_source(self):
        for lt in self:
            if lt.employee_responsible_source == "org_chart":
                lt.employee_responsible_approval_mode = "sequential"

    @api.onchange("leave_validation_type", "allocation_validation_type")
    def _onchange_multi_step_ensure_hr_department(self):
        for lt in self:
            if lt.leave_validation_type == "multi_step_6" or lt.allocation_validation_type == "multi_step_6":
                if not lt.multi_step_hr_source_department_id:
                    lt.multi_step_hr_source_department_id = lt._default_multi_step_hr_department()

    @api.depends("multi_approval_step_ids.approver_user_id", "multi_approval_step_ids.sequence")
    def _compute_multi_step_approver_sync(self):
        for leave_type in self:
            steps = leave_type.multi_approval_step_ids.sorted(lambda s: (s.sequence, s.id))
            leave_type.multi_step_approver_sync = repr(
                [(s.sequence, s.approver_user_id.id if s.approver_user_id else 0) for s in steps]
            )

    def _employee_for_step_approver_user(self, user):
        """Map stored approver user -> employee in the configured department (for display/edit)."""
        self.ensure_one()
        if not user:
            return self.env["hr.employee"]
        domain = [("user_id", "=", user.id)]
        if self.multi_step_hr_source_department_id:
            domain.append(("department_id", "child_of", self.multi_step_hr_source_department_id.id))
        return self.env["hr.employee"].search(domain, limit=1)

    def _multi_step_dedupe_approver_employees_by_sequence(self):
        """Lowest sequence wins per linked user. Later duplicates become empty.

        Employees without ``user_id`` are left as-is (validated separately on save).
        """
        self.ensure_one()
        first_seq_by_user = {}
        out = {}
        Employee = self.env["hr.employee"]
        for seq in range(1, 7):
            emp = self[f"multi_step_approver_employee_{seq}_id"]
            if not emp:
                out[seq] = Employee
                continue
            if not emp.user_id:
                out[seq] = emp
                continue
            uid = emp.user_id.id
            if uid in first_seq_by_user:
                out[seq] = Employee
            else:
                first_seq_by_user[uid] = seq
                out[seq] = emp
        return out

    @api.depends(
        "multi_approval_step_ids.sequence",
        "multi_approval_step_ids.approver_user_id",
        "multi_step_hr_source_department_id",
    )
    def _compute_multi_step_approver_employees(self):
        for leave_type in self:
            by_seq = {s.sequence: s for s in leave_type.multi_approval_step_ids}
            for seq in range(1, 7):
                step = by_seq.get(seq)
                user = step.approver_user_id if step else False
                leave_type[f"multi_step_approver_employee_{seq}_id"] = leave_type._employee_for_step_approver_user(
                    user
                )

    def _inverse_multi_step_approver_employees(self):
        for leave_type in self:
            if not leave_type.id:
                continue
            deduped = leave_type._multi_step_dedupe_approver_employees_by_sequence()
            leave_type._ensure_multi_step_6_steps()
            for seq in range(1, 7):
                emp = deduped[seq]
                if emp and not emp.user_id:
                    raise ValidationError(
                        _("Step %(step)s: employee %(name)s has no linked user and cannot approve.")
                        % {"step": seq, "name": emp.display_name}
                    )
            # Clear all step approvers first. Writing step 1 before step 3 is cleared would
            # temporarily duplicate the same user on two lines and trip _check_unique_approver_per_leave_type.
            steps = leave_type.multi_approval_step_ids.filtered(lambda s: 1 <= s.sequence <= 6)
            steps.write({"approver_user_id": False})
            for seq in range(1, 7):
                emp = deduped[seq]
                step = steps.filtered(lambda s, sq=seq: s.sequence == sq)[:1]
                if not step:
                    continue
                step.write({"approver_user_id": emp.user_id.id if emp else False})

    @api.onchange(
        "multi_step_approver_employee_1_id",
        "multi_step_approver_employee_2_id",
        "multi_step_approver_employee_3_id",
        "multi_step_approver_employee_4_id",
        "multi_step_approver_employee_5_id",
        "multi_step_approver_employee_6_id",
    )
    def _onchange_multi_step_approver_employees_unique(self):
        """Clear duplicate step assignments on the form (lowest step wins) and warn."""
        value = {}
        cleared_steps = []
        for leave_type in self:
            if leave_type.leave_validation_type != "multi_step_6" and leave_type.allocation_validation_type != "multi_step_6":
                continue
            deduped = leave_type._multi_step_dedupe_approver_employees_by_sequence()
            for seq in range(1, 7):
                fname = f"multi_step_approver_employee_{seq}_id"
                cur = leave_type[fname]
                new_e = deduped[seq]
                cur_id = cur.id if cur else False
                new_id = new_e.id if new_e else False
                if cur_id != new_id:
                    value[fname] = new_id if new_id else False
                    if not new_id and cur_id:
                        cleared_steps.append(str(seq))
        if not value:
            return None
        msg = _(
            "Each approver can only be assigned to one step. "
            "Duplicate picks were removed at steps %(steps)s (lowest step kept)."
        ) % {"steps": ", ".join(cleared_steps)}
        return {
            "value": value,
            "warning": {
                "title": _("Duplicate approver"),
                "message": msg,
            },
        }

    @api.depends("employee_requests")
    def _compute_allocation_validation_type(self):
        """Keep user selection for manager/leader when employee_requests='no'.

        In base Odoo, employee_requests='no' forces allocation_validation_type='officer'.
        We relax that to allow manager/leader options.
        """
        for leave_type in self:
            if leave_type.employee_requests == "no" and leave_type.allocation_validation_type not in (
                "manager",
                "leader",
                "multi_step_6",
            ):
                leave_type.allocation_validation_type = "officer"

    def _ensure_multi_step_6_steps(self):
        """Ensure there are exactly 6 step records (sequence 1..6) for demo."""
        Step = self.env["hr.leave.type.approval.step"]
        for leave_type in self:
            if leave_type.leave_validation_type != "multi_step_6" and leave_type.allocation_validation_type != "multi_step_6":
                continue
            existing_seqs = {s.sequence for s in leave_type.multi_approval_step_ids}
            for seq in range(1, 7):
                if seq not in existing_seqs:
                    Step.create(
                        {
                            "leave_type_id": leave_type.id,
                            "sequence": seq,
                            "name": "Step %s" % seq,
                        }
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_multi_step_6_steps()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_multi_step_6_steps()
        return res

    # Demo fields:
    # - officers = additional users that can approve/refuse the "HR" validation step
    # - office/departments = members of departments that can also approve/refuse
    extra_responsible_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="hr_leave_type_extra_res_users_rel",
        column1="leave_type_id",
        column2="user_id",
        string="Approve by extra officers",
        domain=[("share", "=", False)],
        help="Extra officers/users who can approve or refuse this time off type "
             "(in addition to standard time off officers).",
    )

    extra_responsible_department_ids = fields.Many2many(
        comodel_name="hr.department",
        relation="hr_leave_type_extra_res_dept_rel",
        column1="leave_type_id",
        column2="department_id",
        string="Approve by extra departments",
        help="Members of these departments can also approve or refuse this time off type.",
    )

    def _register_hook(self):
        """If DB was not upgraded, add missing columns so the registry matches Python fields."""
        super()._register_hook()
        cr = self.env.cr
        if sql.table_exists(cr, "hr_leave_type"):
            if not sql.column_exists(cr, "hr_leave_type", "employee_responsible_source"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.employee_responsible_source; "
                    "upgrade module when convenient to sync metadata."
                )
                cr.execute("ALTER TABLE hr_leave_type ADD COLUMN employee_responsible_source VARCHAR")
                cr.execute(
                    "UPDATE hr_leave_type SET employee_responsible_source = %s WHERE employee_responsible_source IS NULL",
                    ("manual",),
                )
            if not sql.column_exists(cr, "hr_leave_type", "employee_responsible_escalation_hours"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.employee_responsible_escalation_hours"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN employee_responsible_escalation_hours DOUBLE PRECISION DEFAULT 2.0"
                )
            if not sql.column_exists(cr, "hr_leave_type", "handover_escalation_after_hours"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_escalation_after_hours"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_escalation_after_hours DOUBLE PRECISION DEFAULT 2.0"
                )
            if not sql.column_exists(cr, "hr_leave_type", "handover_escalation_mode"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_escalation_mode"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_escalation_mode VARCHAR DEFAULT 'sequential'"
                )
                cr.execute(
                    "UPDATE hr_leave_type SET handover_escalation_mode = %s "
                    "WHERE handover_escalation_mode IS NULL",
                    ("sequential",),
                )
            if not sql.column_exists(cr, "hr_leave_type", "handover_escalation_max_job_title"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_escalation_max_job_title"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_escalation_max_job_title VARCHAR"
                )
                cr.execute(
                    "UPDATE hr_leave_type SET handover_escalation_max_job_title = %s "
                    "WHERE handover_escalation_max_job_title IS NULL",
                    ("trưởng bộ phận",),
                )
            # Always normalize obsolete/invalid keys to a current selection value so that
            # any row pre-dating the JOB_TITLE_SELECTION rename ('trưởng BP' -> 'trưởng bộ phận',
            # etc.) does not break onchange/render with a Selection ValueError.
            valid_keys = tuple(k for k, _label in _HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION)
            cr.execute(
                """
                UPDATE hr_leave_type
                SET handover_escalation_max_job_title = CASE
                    WHEN handover_escalation_max_job_title = 'trưởng BP' THEN 'trưởng bộ phận'
                    WHEN handover_escalation_max_job_title = 'trưởng phòng HCNS' THEN 'trưởng phòng hcns'
                    ELSE %s
                END
                WHERE handover_escalation_max_job_title IS NOT NULL
                  AND handover_escalation_max_job_title NOT IN %s
                """,
                ("trưởng bộ phận", valid_keys),
            )
            if not sql.column_exists(cr, "hr_leave_type", "handover_escalation_to_manager_hours"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_escalation_to_manager_hours"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_escalation_to_manager_hours DOUBLE PRECISION DEFAULT 2.0"
                )
            if not sql.column_exists(cr, "hr_leave_type", "handover_cancel_if_max_unresponsive"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_cancel_if_max_unresponsive"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_cancel_if_max_unresponsive BOOLEAN DEFAULT FALSE"
                )
            if not sql.column_exists(cr, "hr_leave_type", "handover_cancel_after_max_hours"):
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.handover_cancel_after_max_hours"
                )
                cr.execute(
                    "ALTER TABLE hr_leave_type ADD COLUMN handover_cancel_after_max_hours DOUBLE PRECISION DEFAULT 2.0"
                )
            approval_columns = (
                ("approval_escalation_after_hours", "DOUBLE PRECISION DEFAULT 2.0"),
                ("approval_escalation_mode", "VARCHAR DEFAULT 'sequential'"),
                ("approval_escalation_max_job_title", "VARCHAR"),
                ("approval_escalation_to_manager_hours", "DOUBLE PRECISION DEFAULT 2.0"),
                ("approval_cancel_if_max_unresponsive", "BOOLEAN DEFAULT FALSE"),
                ("approval_cancel_after_max_hours", "DOUBLE PRECISION DEFAULT 2.0"),
            )
            for column_name, column_ddl in approval_columns:
                if sql.column_exists(cr, "hr_leave_type", column_name):
                    continue
                _logger.warning(
                    "time_off_extra_approval: creating missing column hr_leave_type.%s",
                    column_name,
                )
                cr.execute(
                    f"ALTER TABLE hr_leave_type ADD COLUMN {column_name} {column_ddl}"
                )
            if sql.column_exists(cr, "hr_leave_type", "approval_escalation_max_job_title"):
                cr.execute(
                    "UPDATE hr_leave_type SET approval_escalation_max_job_title = %s "
                    "WHERE approval_escalation_max_job_title IS NULL",
                    ("trưởng bộ phận",),
                )
            if sql.column_exists(cr, "hr_leave_type", "approval_escalation_mode"):
                cr.execute(
                    "UPDATE hr_leave_type SET approval_escalation_mode = %s "
                    "WHERE approval_escalation_mode IS NULL",
                    ("sequential",),
                )
        if sql.table_exists(cr, "hr_leave_responsible_approval") and not sql.column_exists(
            cr, "hr_leave_responsible_approval", "pending_since"
        ):
            _logger.warning(
                "time_off_extra_approval: creating missing column hr_leave_responsible_approval.pending_since"
            )
            cr.execute(
                "ALTER TABLE hr_leave_responsible_approval ADD COLUMN pending_since TIMESTAMP WITHOUT TIME ZONE"
            )
