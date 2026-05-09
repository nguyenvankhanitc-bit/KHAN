import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import sql
from odoo.tools.translate import _
from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION

_logger = logging.getLogger(__name__)

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
        ("trưởng BP", "Trưởng BP"),
        ("trưởng phòng", "Trưởng phòng"),
    ]


class HolidaysType(models.Model):
    _inherit = "hr.leave.type"

    # Multi-step approval (demo) for Time Off requests.
    leave_validation_type = fields.Selection(
        selection_add=[
            ("multi_step_6", "Duyệt 6 bước (Demo)"),
            ("employee_hr_responsibles", "Duyệt theo người phụ trách HR của nhân viên"),
        ],
    )

    employee_responsible_approval_mode = fields.Selection(
        selection=[
            ("any", "Chỉ cần một người phụ trách duyệt"),
            ("all", "Tất cả người phụ trách phải duyệt"),
            ("sequential", "Duyệt tuần tự (theo thứ tự)"),
        ],
        string="Chế độ duyệt của người phụ trách nhân viên",
        default="any",
        help="Áp dụng khi hình thức duyệt nghỉ phép là 'Duyệt theo người phụ trách HR của nhân viên'. "
        "Với chế độ tuần tự, người duyệt được sắp theo chức danh của từng người phụ trách "
        "(xem Chức danh trên hồ sơ nhân viên), từ Trưởng nhóm đến Giám đốc theo cấu hình công ty.",
    )

    employee_responsible_source = fields.Selection(
        selection=[
            ("manual", "Người phụ trách HR trên hồ sơ nhân viên"),
            ("org_chart", "Sơ đồ tổ chức (theo chức danh trên chuỗi quản lý)"),
        ],
        string="Nguồn người phụ trách nhân viên",
        default="manual",
        help="Thủ công: dùng người phụ trách HR cấu hình trên nhân viên. "
        "Sơ đồ tổ chức: đi ngược chuỗi quản lý (parent) và tạo một bước duyệt cho mỗi cấp có user nội bộ liên kết "
        "(theo từng tuyến báo cáo, không phải mỗi chức danh một ô).",
    )

    employee_responsible_escalation_hours = fields.Float(
        string="Tự động chuyển cấp sau (giờ)",
        default=2.0,
        help="Chỉ áp dụng cho luồng tuần tự: nếu người duyệt hiện tại không xử lý trong thời gian này, "
        "yêu cầu sẽ chuyển lên cấp tiếp theo.",
    )
    special_director_employee_line_ids = fields.One2many(
        comodel_name="hr.leave.type.special.employee.line",
        inverse_name="leave_type_id",
        string="Special employees (all directors must approve)",
        help="Nhân viên trong danh sách: luồng duyệt tuần tự theo sơ đồ/lan toán giữ nguyên cho tới khi tới cấp có "
        "chức danh Giám đốc; từ đó mỗi người có chức danh Giám đốc (có user nội bộ) trong công ty đều phải duyệt "
        "theo thứ tự trước khi hoàn tất.",
    )
    special_director_sequential_approval = fields.Boolean(
        string="Duyệt theo thứ tự Giám đốc",
        default=False,
        help="Áp dụng với nhân viên đặc biệt: khi bật, thứ tự duyệt giữa các Giám đốc lấy theo bảng bên dưới (STT 1 "
        "trước). Khi tắt, tất cả Giám đốc cùng một bước (nhận thông báo và có thể duyệt đồng thời cho tới khi tất cả "
        "đã duyệt).",
    )
    special_director_order_line_ids = fields.One2many(
        comodel_name="hr.leave.type.special.director.order.line",
        inverse_name="leave_type_id",
        string="Thứ tự duyệt Giám đốc",
        help="Danh sách Giám đốc (chức danh Giám đốc). Chỉ dùng khi bật 'Duyệt theo thứ tự Giám đốc'. Nếu bật nhưng "
        "bảng trống, hệ thống dùng tất cả Giám đốc trong công ty theo thứ tự mặc định.",
    )
    handover_escalation_after_hours = fields.Float(
        string="Bàn giao: Chuyển cấp sau (giờ)",
        default=2.0,
        help="Nếu không ai chấp nhận bàn giao trong khoảng thời gian này, hệ thống bắt đầu chuyển cấp.",
    )
    handover_escalation_max_job_title = fields.Selection(
        selection=_HANDOVER_MAX_ESCALATION_JOB_TITLE_SELECTION,
        string="Bàn giao: Chức danh tối đa để chuyển cấp",
        default="trưởng BP",
        help="Cấp chức danh tối đa khi chuyển cấp phân công bàn giao.",
    )
    handover_escalation_to_manager_hours = fields.Float(
        string="Bàn giao: Chuyển lên cấp kế tiếp sau (giờ)",
        default=2.0,
        help="Khi cấp tối đa là Trưởng phòng: chờ số giờ này sau khi đã chuyển lên Trưởng bộ phận "
        "rồi mới chuyển lên Trưởng phòng.",
    )
    handover_cancel_if_max_unresponsive = fields.Boolean(
        string="Bàn giao: Tự động hủy ở cấp chuyển tối đa",
        default=False,
        help="Nếu bật, đơn nghỉ sẽ tự hủy khi đã lên cấp tối đa nhưng chưa phân công được người nhận bàn giao "
        "trong thời gian cấu hình.",
    )
    handover_cancel_after_max_hours = fields.Float(
        string="Bàn giao: Hủy sau khi quá hạn ở cấp tối đa (giờ)",
        default=2.0,
        help="Chỉ dùng khi bật tùy chọn tự động hủy ở cấp chuyển tối đa.",
    )

    # Extend allocation (Time Off allocation requests) approval options.
    # Note: this selection is used by `hr.leave.allocation` validation_type.
    allocation_validation_type = fields.Selection(
        selection_add=[
            ("manager", "Duyệt bởi quản lý nghỉ phép"),
            ("leader", "Duyệt bởi trưởng bộ phận nghỉ phép"),
            ("multi_step_6", "Duyệt 6 bước (Demo)"),
        ]
    )

    multi_approval_step_ids = fields.One2many(
        comodel_name="hr.leave.type.approval.step",
        inverse_name="leave_type_id",
        string="Các bước duyệt nhiều cấp (Demo)",
        help="Các dòng cấu hình nền cho duyệt 6 bước (thiết lập qua trường Nhân viên bước 1-6 trên loại nghỉ).",
    )

    # Kept for backwards compatibility: Studio / old inherited views may still reference this field.
    multi_step_approver_sync = fields.Char(
        compute="_compute_multi_step_approver_sync",
        string="Mã đồng bộ người duyệt nhiều cấp",
    )

    # Pool for multi-step approvers: users must be employees in this department tree (default: name ilike HR).
    multi_step_hr_source_department_id = fields.Many2one(
        comodel_name="hr.department",
        string="Nguồn người duyệt (phòng ban)",
        default=lambda self: self._default_multi_step_hr_department(),
        help="Người duyệt theo bước bị giới hạn trong các user nội bộ liên kết với nhân viên thuộc phòng ban này "
        "(bao gồm phòng ban con). Đổi nếu đội HR dùng tên phòng ban khác.",
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
                    _("Duyệt theo sơ đồ tổ chức yêu cầu chế độ 'Duyệt tuần tự (theo thứ tự)'.")
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
                        _("Bước %(step)s: nhân viên %(name)s chưa liên kết user nên không thể duyệt.")
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
            "Mỗi người chỉ được gán cho một bước. "
            "Các lựa chọn trùng đã bị xóa ở bước %(steps)s (giữ lại bước có số nhỏ nhất cho mỗi người)."
        ) % {"steps": ", ".join(cleared_steps)}
        return {
            "value": value,
            "warning": {
                "title": _("Trùng người duyệt"),
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
        string="Duyệt bởi cán bộ bổ sung",
        domain=[("share", "=", False)],
        help="Cán bộ/người dùng bổ sung có thể duyệt/từ chối loại nghỉ phép này "
             "(ngoài các cán bộ nghỉ phép tiêu chuẩn).",
    )

    extra_responsible_department_ids = fields.Many2many(
        comodel_name="hr.department",
        relation="hr_leave_type_extra_res_dept_rel",
        column1="leave_type_id",
        column2="department_id",
        string="Duyệt bởi phòng ban bổ sung",
        help="Thành viên của các phòng ban này cũng có thể duyệt/từ chối loại nghỉ phép này.",
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
                    ("trưởng BP",),
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
        if sql.table_exists(cr, "hr_leave_responsible_approval") and not sql.column_exists(
            cr, "hr_leave_responsible_approval", "pending_since"
        ):
            _logger.warning(
                "time_off_extra_approval: creating missing column hr_leave_responsible_approval.pending_since"
            )
            cr.execute(
                "ALTER TABLE hr_leave_responsible_approval ADD COLUMN pending_since TIMESTAMP WITHOUT TIME ZONE"
            )
