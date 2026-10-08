# -*- coding: utf-8 -*-

import base64
import io
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_USER_DOMAIN = "[('share', '=', False), ('active', '=', True)]"

REGION_SELECTION = [
    ("south", "Miền Nam"),
    ("dtt", "Miền ĐTT"),
    ("north", "Miền Bắc"),
    ("vptt", "VPTT"),
    ("vpmb", "VPMB"),
]

STATE_SELECTION = [
    ("done", "Hoàn thành"),
    ("in_progress", "Đang thực hiện"),
    ("overdue", "Quá hạn"),
    ("not_started", "Chưa bắt đầu"),
]


class DailyTaskAssign(models.Model):
    """Phân công công việc — theo mẫu Danh sách phân công công việc."""

    _name = "daily.task.assign"
    _description = "Phân công công việc"
    _order = "stt, id"

    @api.model
    def _department_from_user(self, user=None):
        """Phòng ban trên hồ sơ hr.employee gắn với user."""
        user = user or self.env.user
        if not user:
            return False
        emp = getattr(user, "employee_id", False) or self.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)], limit=1
        )
        return emp.department_id if emp and emp.department_id else False

    @api.model
    def _default_department_from_user(self):
        return self._department_from_user()

    stt = fields.Integer(string="STT", default=0, index=True, copy=False)
    sequence = fields.Integer(string="Thứ tự", default=10)
    name = fields.Char(string="Nội dung công việc", required=False, index=True)
    work_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        required=False,
        index=True,
        ondelete="restrict",
    )
    # UI form: chọn Hạng mục (duy nhất) trước, rồi tick Tên công việc
    category_group_id = fields.Many2one(
        "daily.task.work.group",
        string="Hạng mục",
        ondelete="set null",
        index=True,
        help="Chọn nhóm hạng mục (Camera, Email…). Không phải dòng công việc con.",
    )
    category_name = fields.Char(
        string="Tên hạng mục",
        related="category_group_id.name",
        store=True,
        readonly=True,
    )
    work_group_ids = fields.Many2many(
        "daily.task.work.group",
        "daily_task_assign_work_group_sel_rel",
        "assign_id",
        "work_group_id",
        string="Tên công việc",
        help="Chọn một hoặc nhiều tên công việc (checkbox). Lưu sẽ tạo từng dòng phân công.",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        index=True,
        default=lambda self: self._default_department_from_user(),
        help="Tự lấy từ hồ sơ nhân viên của user (đăng nhập / người phụ trách).",
    )
    team_id = fields.Many2one(
        related="work_group_id.team_id",
        string="Team",
        store=True,
        readonly=True,
    )
    region = fields.Selection(
        REGION_SELECTION,
        string="Khu vực",
        required=False,
        index=True,
    )
    south_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_south_user_rel",
        "assign_id",
        "user_id",
        string="Miền Nam",
        domain=_USER_DOMAIN,
    )
    dtt_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_dtt_user_rel",
        "assign_id",
        "user_id",
        string="Miền ĐTT",
        domain=_USER_DOMAIN,
    )
    north_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_north_user_rel",
        "assign_id",
        "user_id",
        string="Miền Bắc",
        domain=_USER_DOMAIN,
    )
    office_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_office_user_rel",
        "assign_id",
        "user_id",
        string="Văn phòng",
        domain=_USER_DOMAIN,
    )
    # Giữ boolean cũ (ẩn) — tương thích cột DB đã tạo
    is_south = fields.Boolean(string="Miền Nam (cũ)", default=False)
    is_dtt = fields.Boolean(string="Miền ĐTT (cũ)", default=False)
    is_north = fields.Boolean(string="Miền Bắc (cũ)", default=False)
    is_office = fields.Boolean(string="Văn phòng (cũ)", default=False)
    # UI chính: M2M tags (giống cột miền). M2O giữ để search/group_by.
    assignee_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_assignee_user_rel",
        "assign_id",
        "user_id",
        string="Người phụ trách",
        domain=_USER_DOMAIN,
    )
    detail_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_detail_user_rel",
        "assign_id",
        "user_id",
        string="User chi tiết",
        domain=_USER_DOMAIN,
    )
    check_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_check_user_rel",
        "assign_id",
        "user_id",
        string="User kiểm tra",
        domain=_USER_DOMAIN,
    )
    coord_user_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_coord_user_rel",
        "assign_id",
        "user_id",
        string="User phối hợp",
        domain=_USER_DOMAIN,
    )
    assignee_user_id = fields.Many2one(
        "res.users",
        string="Người phụ trách (chính)",
        domain=_USER_DOMAIN,
        index=True,
        ondelete="set null",
    )
    detail_user_id = fields.Many2one(
        "res.users",
        string="User chi tiết (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    check_user_id = fields.Many2one(
        "res.users",
        string="User kiểm tra (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    coord_user_id = fields.Many2one(
        "res.users",
        string="User phối hợp (chính)",
        domain=_USER_DOMAIN,
        ondelete="set null",
    )
    participant_ids = fields.Many2many(
        "res.users",
        "daily_task_assign_participant_rel",
        "assign_id",
        "user_id",
        string="Người tham gia",
        domain=_USER_DOMAIN,
    )
    participant_label = fields.Char(
        string="Người tham gia",
        compute="_compute_participant_label",
    )
    date_start = fields.Date(string="Bắt đầu", default=fields.Date.context_today)
    deadline = fields.Date(string="Deadline")
    state = fields.Selection(
        STATE_SELECTION,
        string="Trạng thái",
        default="not_started",
        required=True,
        index=True,
    )
    note = fields.Char(string="Ghi chú")
    active = fields.Boolean(default=True)

    @api.depends("participant_ids")
    def _compute_participant_label(self):
        for rec in self:
            n = len(rec.participant_ids)
            rec.participant_label = ("%s người" % n) if n else "—"

    @staticmethod
    def _m2m_command_ids(commands):
        if not commands:
            return []
        # [(6, 0, ids)] phổ biến từ UI tags
        if isinstance(commands, (list, tuple)) and commands and commands[0][0] == 6:
            return list(commands[0][2] or [])
        return []

    def _sync_m2o_from_m2m_vals(self, vals):
        pairs = (
            ("assignee_user_ids", "assignee_user_id"),
            ("detail_user_ids", "detail_user_id"),
            ("check_user_ids", "check_user_id"),
            ("coord_user_ids", "coord_user_id"),
        )
        for m2m_name, m2o_name in pairs:
            if m2m_name in vals and m2o_name not in vals:
                ids = self._m2m_command_ids(vals.get(m2m_name))
                vals[m2o_name] = ids[0] if ids else False

    def _responsible_users(self):
        """User phụ trách chính (+ miền/VP nếu chưa chọn phụ trách)."""
        self.ensure_one()
        users = self.assignee_user_ids
        if users:
            return users
        return (
            self.south_user_ids
            | self.dtt_user_ids
            | self.north_user_ids
            | self.office_user_ids
        )

    def _sync_personal_daily_tasks(self):
        """Tạo/cập nhật công việc cá nhân từ dòng phân công → người phụ trách."""
        if self.env.context.get("skip_assign_personal_sync"):
            return
        Task = self.env["daily.task"].sudo().with_context(
            skip_work_group_user_check=True,
            from_daily_task_assign=True,
            mail_notrack=True,
            tracking_disable=True,
        )
        EmpBridge = self.env["daily.task.employee"].sudo()
        HrEmployee = self.env["hr.employee"].sudo()
        today = fields.Date.context_today(self)
        for rec in self:
            users = rec._responsible_users()
            existing = Task.search([("assign_line_id", "=", rec.id)])
            kept = Task.browse()
            for user in users:
                hr = HrEmployee.search([("user_id", "=", user.id)], limit=1)
                if not hr:
                    continue
                bridge = EmpBridge.get_or_create_from_hr(hr.id)
                # Ưu tiên phòng ban của hạng mục để khớp ràng buộc phòng ban
                wg = rec.work_group_id
                dept = (
                    wg.department_id.id
                    if wg and wg.department_id
                    else (
                        rec.department_id.id
                        if rec.department_id
                        else (hr.department_id.id if hr.department_id else False)
                    )
                )
                task_vals = {
                    "name": rec.name or (wg.task_name if wg else "") or "/",
                    "work_group_id": wg.id if wg else False,
                    "department_id": dept,
                    "assignee_id": bridge.id,
                    "assign_line_id": rec.id,
                    "assign_date": rec.date_start or today,
                    "deadline": rec.deadline or today,
                    "note": rec.note or "",
                    "assigned_by_id": self.env.uid,
                }
                task = existing.filtered(lambda t, b=bridge: t.assignee_id.id == b.id)[:1]
                if task:
                    task.with_context(
                        skip_work_group_user_check=True,
                        from_daily_task_assign=True,
                    ).write(task_vals)
                    kept |= task
                else:
                    kept |= Task.create(
                        {
                            **task_vals,
                            "state": "not_started",
                            "priority": "medium",
                        }
                    )
            # Không xóa việc cá nhân cũ — chỉ tạo/cập nhật theo người phụ trách hiện tại

    def _expand_vals_by_work_groups(self, vals_list):
        """Nhiều tên CV (checkbox) → nhiều dòng phân công (1 dòng / 1 công việc)."""
        if self.env.context.get("skip_assign_expand"):
            return [dict(v) for v in vals_list]
        expanded = []
        for vals in vals_list:
            vals = dict(vals)
            wg_ids = self._m2m_command_ids(vals.pop("work_group_ids", None))
            if not wg_ids and vals.get("work_group_id"):
                wg_ids = [vals["work_group_id"]]
            if not wg_ids:
                raise ValidationError(
                    "Vui lòng chọn Hạng mục và tích ít nhất một Tên công việc."
                )
            first_wg = self.env["daily.task.work.group"].browse(wg_ids[:1])
            for wg_id in wg_ids:
                line = dict(vals)
                line["work_group_id"] = wg_id
                line["work_group_ids"] = [(6, 0, [wg_id])]
                wg = self.env["daily.task.work.group"].browse(wg_id)
                if wg.task_name:
                    line["name"] = wg.task_name
                elif not line.get("name"):
                    line["name"] = wg.name or "/"
                line.update(self._linked_user_vals(line, wg, first_wg))
                # Tránh trùng STT khi tách nhiều dòng từ 1 form
                if "stt" in line and len(wg_ids) > 1:
                    line.pop("stt", None)
                expanded.append(line)
        return expanded

    @api.model
    def _assign_access_feature(self):
        """Context từ board: 'add' | 'list' — mặc định chấp nhận nếu có quyền ở một trong hai."""
        return self.env.context.get("daily_work_assign_feature") or False

    @api.model
    def _check_assign_access(self, action):
        Access = self.env["daily.task.assign.access"]
        feature = self._assign_access_feature()
        if feature in ("add", "list"):
            Access.check(feature, action)
            return
        if Access.can("add", action) or Access.can("list", action):
            return
        Access.check("add", action)

    @api.model_create_multi
    def create(self, vals_list):
        self._check_assign_access("create")
        vals_list = self._expand_vals_by_work_groups(vals_list)
        last = self.search([], order="stt desc", limit=1)
        next_stt = (last.stt or 0) + 1 if last else 1
        for vals in vals_list:
            if not vals.get("stt"):
                vals["stt"] = next_stt
                next_stt += 1
            # Lấy tên CV từ hạng mục cha nếu chưa nhập
            if not vals.get("name") and vals.get("work_group_id"):
                wg = self.env["daily.task.work.group"].browse(vals["work_group_id"])
                if wg.task_name:
                    vals["name"] = wg.task_name
            # Phòng ban: hồ sơ NV của người phụ trách → user tạo → hạng mục
            if not vals.get("department_id"):
                assignee_ids = self._m2m_command_ids(vals.get("assignee_user_ids"))
                if not assignee_ids and vals.get("assignee_user_id"):
                    assignee_ids = [vals["assignee_user_id"]]
                dept = False
                if assignee_ids:
                    dept = self._department_from_user(
                        self.env["res.users"].browse(assignee_ids[0])
                    )
                if not dept:
                    dept = self._department_from_user()
                if not dept and vals.get("work_group_id"):
                    wg = self.env["daily.task.work.group"].browse(vals["work_group_id"])
                    dept = wg.department_id
                if dept:
                    vals["department_id"] = dept.id
            self._sync_m2o_from_m2m_vals(vals)
            for m2m_name, m2o_name in (
                ("assignee_user_ids", "assignee_user_id"),
                ("detail_user_ids", "detail_user_id"),
                ("check_user_ids", "check_user_id"),
                ("coord_user_ids", "coord_user_id"),
            ):
                if m2m_name not in vals and vals.get(m2o_name):
                    vals[m2m_name] = [(6, 0, [vals[m2o_name]])]
        records = super().create(vals_list)
        # Giữ checkbox đã chọn khi mở lại form sửa — đúng 1 tên CV của dòng đó
        for rec in records:
            if rec.work_group_id:
                super(DailyTaskAssign, rec).write(
                    {"work_group_ids": [(6, 0, [rec.work_group_id.id])]}
                )
        records._sync_personal_daily_tasks()
        records._push_users_to_work_group()
        return records

    _USER_M2M_FIELDS = (
        "assignee_user_ids",
        "south_user_ids",
        "dtt_user_ids",
        "north_user_ids",
        "office_user_ids",
        "check_user_ids",
        "detail_user_ids",
        "coord_user_ids",
        "participant_ids",
    )

    def _merge_m2m_ids(self, existing_ids, commands):
        """Gộp id hiện có với lệnh M2M từ form (ưu tiên union)."""
        new_ids = self._m2m_command_ids(commands)
        if commands is None:
            return list(existing_ids)
        # [(6, 0, ids)] thay thế → vẫn union để không mất user khác trên dòng sẵn có
        return list({int(x) for x in (existing_ids or [])} | {int(x) for x in (new_ids or [])})

    def _apply_users_to_work_groups(self, wg_ids, user_vals):
        """Gắn user (Miền Nam / phụ trách…) lên từng tên CV đã tích — tìm dòng sẵn hoặc tạo mới."""
        self.ensure_one()
        touched = self.browse()
        first = True
        for wg_id in wg_ids:
            wg = self.env["daily.task.work.group"].browse(wg_id)
            if not wg.exists():
                continue
            if first:
                target = self
                first = False
            else:
                target = self.search(
                    [("work_group_id", "=", wg_id), ("active", "=", True)],
                    limit=1,
                )
            payload = {
                "work_group_id": wg_id,
                "name": wg.task_name or wg.name or "/",
                "work_group_ids": [(6, 0, [wg_id])],
            }
            if self.department_id:
                payload["department_id"] = self.department_id.id
            elif wg.department_id:
                payload["department_id"] = wg.department_id.id
            if self.category_group_id:
                payload["category_group_id"] = self.category_group_id.id
            for fname in self._USER_M2M_FIELDS:
                if fname in user_vals:
                    if target:
                        merged = self._merge_m2m_ids(target[fname].ids, user_vals[fname])
                    else:
                        merged = self._m2m_command_ids(user_vals[fname])
                    payload[fname] = [(6, 0, merged)]
            if target:
                super(DailyTaskAssign, target).write(payload)
                touched |= target
            else:
                create_vals = dict(payload)
                # stt để trống → create tự tăng
                create_vals.pop("stt", None)
                touched |= self.with_context(
                    skip_assign_expand=True,
                    skip_assign_personal_sync=True,
                ).create([create_vals])
        return touched

    def write(self, vals):
        self._check_assign_access("write")
        vals = dict(vals)
        self._sync_m2o_from_m2m_vals(vals)

        # Form tích nhiều tên CV → áp user lên từng dòng phân công tương ứng
        if "work_group_ids" in vals and len(self) == 1:
            wg_ids = self._m2m_command_ids(vals.get("work_group_ids"))
            if len(wg_ids) > 1 or (
                wg_ids
                and any(f in vals for f in self._USER_M2M_FIELDS)
            ):
                user_vals = {f: vals[f] for f in self._USER_M2M_FIELDS if f in vals}
                # Nếu form không gửi lại user fields, lấy từ record hiện tại
                for f in self._USER_M2M_FIELDS:
                    if f not in user_vals and self[f]:
                        user_vals[f] = [(6, 0, self[f].ids)]
                other_vals = {
                    k: v
                    for k, v in vals.items()
                    if k not in ("work_group_ids", "work_group_id")
                    and k not in self._USER_M2M_FIELDS
                }
                if other_vals:
                    super().write(other_vals)
                touched = self._apply_users_to_work_groups(wg_ids or self.work_group_id.ids, user_vals)
                touched._push_users_to_work_group()
                touched._sync_personal_daily_tasks()
                return True

        res = super().write(vals)
        if not self.env.context.get("skip_link_users") and set(vals) & {
            "assignee_user_ids",
            "check_user_ids",
            "south_user_ids",
            "dtt_user_ids",
            "north_user_ids",
            "work_group_id",
        }:
            self._push_users_to_work_group()
        sync_fields = {
            "name",
            "work_group_id",
            "work_group_ids",
            "assignee_user_ids",
            "south_user_ids",
            "dtt_user_ids",
            "north_user_ids",
            "office_user_ids",
            "date_start",
            "deadline",
            "note",
        }
        if sync_fields & set(vals):
            self._sync_personal_daily_tasks()
        return res

    _LINK_USER_FIELDS = (
        ("assignee_user_ids", "assignee_user_ids"),
        ("check_user_ids", "checker_user_ids"),
        ("south_user_ids", "south_user_ids"),
        ("dtt_user_ids", "dtt_user_ids"),
        ("north_user_ids", "north_user_ids"),
    )

    def _push_users_to_work_group(self):
        """User trên dòng phân công được gắn sang đúng hạng mục (không xóa user sẵn có)."""
        if self.env.context.get("skip_link_users"):
            return
        for rec in self:
            wg = rec.work_group_id
            if not wg:
                continue
            vals = {}
            for assign_field, wg_field in self._LINK_USER_FIELDS:
                missing = [
                    user_id
                    for user_id in rec[assign_field].ids
                    if user_id not in wg[wg_field].ids
                ]
                if missing:
                    vals[wg_field] = [(4, user_id) for user_id in missing]
            if vals:
                wg.sudo().with_context(skip_link_users=True).write(vals)

    def unlink(self):
        self._check_assign_access("unlink")
        return super().unlink()

    def _migrate_m2o_into_m2m(self):
        """Đổ user M2O cũ sang cột tags M2M (một lần khi upgrade)."""
        for rec in self:
            updates = {}
            if rec.assignee_user_id and not rec.assignee_user_ids:
                updates["assignee_user_ids"] = [(6, 0, rec.assignee_user_id.ids)]
            if rec.detail_user_id and not rec.detail_user_ids:
                updates["detail_user_ids"] = [(6, 0, rec.detail_user_id.ids)]
            if rec.check_user_id and not rec.check_user_ids:
                updates["check_user_ids"] = [(6, 0, rec.check_user_id.ids)]
            if rec.coord_user_id and not rec.coord_user_ids:
                updates["coord_user_ids"] = [(6, 0, rec.coord_user_id.ids)]
            if updates:
                super(DailyTaskAssign, rec).write(updates)

    @api.onchange("assignee_user_ids")
    def _onchange_assignee_user_ids(self):
        """Đồng bộ M2O + lấy Phòng ban từ hồ sơ NV của người phụ trách."""
        self.assignee_user_id = self.assignee_user_ids[:1]
        user = self.assignee_user_ids[:1]
        if user:
            dept = self._department_from_user(user)
            if dept:
                self.department_id = dept
                if (
                    self.work_group_id
                    and self.work_group_id.department_id
                    and self.work_group_id.department_id != dept
                ):
                    self.work_group_id = False

    def _work_group_task_domain(self):
        self.ensure_one()
        domain = [("active", "=", True)]
        if self.department_id:
            domain.append(("department_id", "=", self.department_id.id))
        cat_name = (self.category_name or "").strip()
        if not cat_name and self.category_group_id:
            cat_name = (self.category_group_id.name or "").strip()
        if cat_name:
            domain.append(("name", "=ilike", cat_name))
        else:
            domain.append(("id", "=", False))
        return domain

    @api.onchange("department_id")
    def _onchange_department_id(self):
        """Lọc hạng mục theo phòng ban hồ sơ NV."""
        if (
            self.category_group_id
            and self.department_id
            and self.category_group_id.department_id
            and self.category_group_id.department_id != self.department_id
        ):
            self.category_group_id = False
            self.work_group_ids = False
            self.work_group_id = False
            self.name = False
        return {
            "domain": {
                "category_group_id": (
                    [("department_id", "=", self.department_id.id)]
                    if self.department_id
                    else [("active", "=", True)]
                ),
                "work_group_ids": self._work_group_task_domain(),
            }
        }

    @api.onchange("category_group_id")
    def _onchange_category_group_id(self):
        """Chọn Hạng mục → hiện checkbox Tên công việc cùng nhóm."""
        self.work_group_ids = [(5, 0, 0)]
        self.work_group_id = False
        self.name = False
        return {"domain": {"work_group_ids": self._work_group_task_domain()}}

    @api.onchange("work_group_ids")
    def _onchange_work_group_ids(self):
        """Tick tên CV → đồng bộ work_group_id / name + gợi ý user."""
        groups = self.work_group_ids
        first = groups[:1]
        self.work_group_id = first
        if first:
            if not self.category_group_id:
                self.category_group_id = first
            if first.task_name:
                self.name = first.task_name
            return self._apply_work_group_user_defaults(first)
        self.name = False

    def _linked_user_vals(self, line, wg, first_wg):
        """Mỗi dòng phân công lấy user của đúng hạng mục, nếu form vẫn đang dùng gợi ý."""
        if not wg:
            return {}
        linked = {}

        def _keep_or_take(field, form_ids, default_ids, take_ids):
            form_ids = list(form_ids or [])
            default_ids = list(default_ids or [])
            take_ids = list(take_ids or [])
            if form_ids and set(form_ids) != set(default_ids):
                return
            if take_ids:
                linked[field] = [(6, 0, take_ids)]

        _keep_or_take(
            "assignee_user_ids",
            self._m2m_command_ids(line.get("assignee_user_ids")),
            first_wg.assignee_user_ids.ids,
            wg.assignee_user_ids.ids,
        )
        if linked.get("assignee_user_ids"):
            linked["assignee_user_id"] = wg.assignee_user_ids[:1].id
        _keep_or_take(
            "south_user_ids",
            self._m2m_command_ids(line.get("south_user_ids")),
            first_wg.south_user_ids.ids,
            wg.south_user_ids.ids,
        )
        _keep_or_take(
            "dtt_user_ids",
            self._m2m_command_ids(line.get("dtt_user_ids")),
            first_wg.dtt_user_ids.ids,
            wg.dtt_user_ids.ids,
        )
        _keep_or_take(
            "north_user_ids",
            self._m2m_command_ids(line.get("north_user_ids")),
            first_wg.north_user_ids.ids,
            wg.north_user_ids.ids,
        )
        office_take = (wg.vptt_user_ids | wg.vpmb_user_ids).ids
        office_default = (first_wg.vptt_user_ids | first_wg.vpmb_user_ids).ids
        _keep_or_take(
            "office_user_ids",
            self._m2m_command_ids(line.get("office_user_ids")),
            office_default,
            office_take,
        )
        check_take = wg.checker_user_ids.ids
        check_default = first_wg.checker_user_ids.ids
        _keep_or_take(
            "check_user_ids",
            self._m2m_command_ids(line.get("check_user_ids")),
            check_default,
            check_take,
        )
        if linked.get("check_user_ids"):
            linked["check_user_id"] = check_take[0]
        return linked

    def _apply_work_group_user_defaults(self, wg):
        """Gợi ý user từ hạng mục được chọn — Người phụ trách lấy từ User phụ trách."""
        if not wg:
            return
        if not self.department_id and wg.department_id:
            self.department_id = wg.department_id
        if not self.assignee_user_ids and wg.assignee_user_ids:
            self.assignee_user_ids = wg.assignee_user_ids
            self.assignee_user_id = wg.assignee_user_ids[:1]
        if not self.check_user_ids and wg.checker_user_ids:
            self.check_user_ids = wg.checker_user_ids
            self.check_user_id = wg.checker_user_ids[:1]
        if not self.coord_user_ids and wg.detail_check_user_ids and wg.total_user_ids:
            self.coord_user_ids = wg.total_user_ids[:1]
            self.coord_user_id = wg.total_user_ids[:1]
        if not self.south_user_ids and wg.south_user_ids:
            self.south_user_ids = wg.south_user_ids
        if not self.dtt_user_ids and wg.dtt_user_ids:
            self.dtt_user_ids = wg.dtt_user_ids
        if not self.north_user_ids and wg.north_user_ids:
            self.north_user_ids = wg.north_user_ids
        if not self.office_user_ids:
            office = wg.vptt_user_ids | wg.vpmb_user_ids
            if office:
                self.office_user_ids = office
        self._suggest_assignee_from_region()
        users = wg.applicable_users()
        domain = (
            [("id", "in", users.ids)]
            if users
            else [("share", "=", False), ("active", "=", True)]
        )
        return {
            "domain": {
                "assignee_user_ids": domain,
                "detail_user_ids": domain,
                "check_user_ids": domain,
                "coord_user_ids": domain,
                "participant_ids": domain,
                "south_user_ids": domain,
                "dtt_user_ids": domain,
                "north_user_ids": domain,
                "office_user_ids": domain,
            }
        }

    @api.onchange(
        "assignee_user_ids",
        "detail_user_ids",
        "check_user_ids",
        "coord_user_ids",
    )
    def _onchange_role_users_sync_m2o(self):
        """Đồng bộ M2O chính từ tags — hai cột phụ trách/chi tiết độc lập."""
        self.assignee_user_id = self.assignee_user_ids[:1]
        self.detail_user_id = self.detail_user_ids[:1]
        self.check_user_id = self.check_user_ids[:1]
        self.coord_user_id = self.coord_user_ids[:1]

    @api.onchange("work_group_id")
    def _onchange_work_group_id(self):
        """Chọn Tên công việc (dòng hạng mục) → điền nội dung + user."""
        wg = self.work_group_id
        if not wg:
            return
        if not self.category_group_id:
            self.category_group_id = wg
        # Ưu tiên phòng ban NV; nếu chưa có thì lấy từ hạng mục
        if not self.department_id and wg.department_id:
            self.department_id = wg.department_id
        if wg.task_name:
            self.name = wg.task_name
        return self._apply_work_group_user_defaults(wg)

    @api.onchange("region", "work_group_id")
    def _onchange_region(self):
        self._suggest_assignee_from_region()

    def _suggest_assignee_from_region(self):
        wg = self.work_group_id
        if not wg or not self.region:
            return
        field_map = {
            "south": "south_user_ids",
            "dtt": "dtt_user_ids",
            "north": "north_user_ids",
            "vptt": "vptt_user_ids",
            "vpmb": "vpmb_user_ids",
        }
        users = getattr(wg, field_map.get(self.region), self.env["res.users"])
        if users and not self.assignee_user_ids:
            self.assignee_user_ids = users[:1]
            self.assignee_user_id = users[:1]

    # ------------------------------------------------------------------
    # Bảng phân công team (client action — chỉ xem)
    # ------------------------------------------------------------------

    @api.model
    def _roman(self, n):
        vals = (
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        )
        out = []
        for value, numeral in vals:
            while n >= value:
                out.append(numeral)
                n -= value
        return "".join(out) or "I"

    @api.model
    def _users_payload(self, users):
        return [{"id": u.id, "name": u.name or ""} for u in users]

    @api.model
    def _assignees_for_row(self, rec):
        """Người phụ trách: dòng phân công cộng User phụ trách người dùng chọn trên hạng mục."""
        assignees = rec.assignee_user_ids
        if rec.assignee_user_id and rec.assignee_user_id not in assignees:
            assignees |= rec.assignee_user_id
        wg = rec.work_group_id
        if wg and wg.assignee_user_ids:
            assignees |= wg.assignee_user_ids
        return assignees

    @api.model
    def _checkers_for_row(self, rec):
        """User kiểm tra: cột trên dòng phân công cộng User kiểm tra trên hạng mục."""
        checkers = rec.check_user_ids
        if rec.check_user_id and rec.check_user_id not in checkers:
            checkers |= rec.check_user_id
        wg = rec.work_group_id
        if wg and wg.checker_user_ids:
            checkers |= wg.checker_user_ids
        return checkers

    @api.model
    def _assign_row_matches(self, rec, needle):
        if not needle:
            return True
        blobs = [
            rec.name or "",
            rec.note or "",
            rec.work_group_id.display_name or "",
            " ".join(rec.south_user_ids.mapped("name")),
            " ".join(rec.dtt_user_ids.mapped("name")),
            " ".join(rec.north_user_ids.mapped("name")),
            " ".join(rec.office_user_ids.mapped("name")),
            " ".join(rec.assignee_user_ids.mapped("name")),
            " ".join(rec.check_user_ids.mapped("name")),
            " ".join(rec.coord_user_ids.mapped("name")),
            " ".join(rec.participant_ids.mapped("name")),
        ]
        return needle in " ".join(blobs).lower()

    @api.model
    def get_assign_board_data(self, search=""):
        """Dữ liệu bảng phân công — nhóm theo hạng mục lớn (I. CAMERA → 1.1, 1.2…)."""
        needle = (search or "").strip().lower()
        WorkGroup = self.env["daily.task.work.group"]
        records = self.search([], order="stt, id")
        records.mapped("work_group_id").mapped("display_stt")
        # Sắp theo thứ tự hạng mục (sequence) rồi STT phân công
        records = records.sorted(
            key=lambda r: (
                int(r.work_group_id.sequence or 0) if r.work_group_id else 10**9,
                int(r.stt or 0),
                r.id,
            )
        )
        groups_map = {}
        group_order = []

        for rec in records:
            if not self._assign_row_matches(rec, needle):
                continue
            wg = rec.work_group_id
            cat = WorkGroup._norm_category_name(wg.name) if wg else "Khác"
            dept = wg.department_id.display_name if wg and wg.department_id else ""
            dept_id = wg.department_id.id if wg and wg.department_id else 0
            gkey = (dept_id, cat.casefold())
            if gkey not in groups_map:
                groups_map[gkey] = {
                    "id": "%s-%s" % (dept_id, cat.casefold()),
                    "name": cat,
                    "department": dept,
                    "tasks": [],
                }
                group_order.append(gkey)
            collab = rec.coord_user_ids | rec.participant_ids
            assignees = self._assignees_for_row(rec)
            checkers = self._checkers_for_row(rec)
            groups_map[gkey]["tasks"].append({
                "id": rec.id,
                "stt": rec.stt,
                "wg_stt": wg.display_stt if wg else "",
                "name": rec.name or "",
                "category": cat,
                "note": rec.note or "",
                "south": self._users_payload(rec.south_user_ids),
                "dtt": self._users_payload(rec.dtt_user_ids),
                "north": self._users_payload(rec.north_user_ids),
                "office": self._users_payload(rec.office_user_ids),
                "assignee": self._users_payload(assignees),
                "checker": self._users_payload(checkers),
                "collab": self._users_payload(collab),
            })

        sections = []
        for idx, gkey in enumerate(group_order, start=1):
            g = groups_map[gkey]
            title = "%s. %s" % (self._roman(idx), (g["name"] or "").upper())
            if g.get("department"):
                title = "%s (%s)" % (title, g["department"].upper())
            tasks = []
            for t_idx, task in enumerate(g["tasks"], start=1):
                tasks.append({
                    **task,
                    "display_stt": task.get("wg_stt") or "%s.%s" % (idx, t_idx),
                })
            sections.append({
                "id": g["id"],
                "code": self._roman(idx),
                "title": title,
                "tone": "alt" if idx % 3 == 0 else "default",
                "tasks": tasks,
            })

        today = fields.Date.context_today(self)
        Access = self.env["daily.task.assign.access"]
        feature = self._assign_access_feature() or "list"
        if feature not in ("add", "list"):
            feature = "list"
        Access.check(feature, "view")
        access = Access.get_access_map().get(feature) or {}
        return {
            "month": today.month,
            "year": today.year,
            "month_label": "Tháng %s / Năm %s" % (today.month, today.year),
            "readonly": True,
            "sections": sections,
            "task_count": sum(len(s["tasks"]) for s in sections),
            "access": {
                "view": bool(access.get("view")),
                "create": bool(access.get("create")),
                "write": bool(access.get("write")),
                "unlink": bool(access.get("unlink")),
            },
            "feature": feature,
        }

    @api.model
    def export_assign_board_excel(self, search=""):
        """Xuất Excel bảng phân công team."""
        try:
            import xlsxwriter
        except ImportError as err:
            raise UserError(
                "Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter"
            ) from err

        data = self.get_assign_board_data(search=search)
        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Phân công")

        title_fmt = wb.add_format({
            "bold": True, "font_size": 14, "font_color": "#0f172a",
        })
        sub_fmt = wb.add_format({"font_size": 11, "font_color": "#64748b"})
        head_fmt = wb.add_format({
            "bold": True, "font_color": "#ffffff", "bg_color": "#1c2d42",
            "align": "center", "valign": "vcenter", "border": 1,
        })
        section_fmt = wb.add_format({
            "bold": True, "bg_color": "#dbe4ee", "border": 1,
        })
        cell_fmt = wb.add_format({"border": 1, "valign": "vcenter"})
        center_fmt = wb.add_format({
            "border": 1, "align": "center", "valign": "vcenter",
        })

        headers = [
            "STT",
            "Tên công việc / Hạng mục",
            "Miền Nam",
            "Miền ĐTT",
            "Miền Bắc",
            "Văn phòng",
            "Người phụ trách",
            "User kiểm tra",
            "User tham gia / phối hợp",
            "Ghi chú",
        ]
        widths = [8, 48, 18, 18, 18, 16, 18, 18, 24, 16]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)

        ws.merge_range(0, 0, 0, 9, "BẢNG PHÂN CÔNG CÔNG VIỆC TEAM", title_fmt)
        ws.merge_range(1, 0, 1, 9, data.get("month_label") or "", sub_fmt)
        ws.merge_range(2, 0, 2, 9, "Chế độ: Chỉ xem", sub_fmt)

        row = 4
        for col, h in enumerate(headers):
            ws.write(row, col, h, head_fmt)
        row += 1

        def names(users):
            return ", ".join(u["name"] for u in (users or []) if u.get("name")) or "—"

        for section in data.get("sections") or []:
            ws.merge_range(row, 0, row, 9, section.get("title") or "", section_fmt)
            row += 1
            for task in section.get("tasks") or []:
                label = "%s — %s" % (task.get("category") or "", task.get("name") or "")
                ws.write(row, 0, task.get("display_stt") or "", center_fmt)
                ws.write(row, 1, label, cell_fmt)
                ws.write(row, 2, names(task.get("south")), cell_fmt)
                ws.write(row, 3, names(task.get("dtt")), cell_fmt)
                ws.write(row, 4, names(task.get("north")), cell_fmt)
                ws.write(row, 5, names(task.get("office")), cell_fmt)
                ws.write(row, 6, names(task.get("assignee")), cell_fmt)
                ws.write(row, 7, names(task.get("checker")), cell_fmt)
                ws.write(row, 8, names(task.get("collab")), cell_fmt)
                ws.write(row, 9, task.get("note") or "—", cell_fmt)
                row += 1

        wb.close()
        raw = buffer.getvalue()
        month = data.get("month") or 1
        year = data.get("year") or fields.Date.context_today(self).year
        filename = "Bang_Phan_Cong_Cong_Viec_Thang_%s_%s.xlsx" % (month, year)
        return {
            "file_base64": base64.b64encode(raw).decode("ascii"),
            "filename": filename,
        }

    @api.model
    def get_personnel_work_data(self):
        """Tách bảng phân công team thành công việc theo từng nhân sự (chỉ đọc).

        Không ghi dữ liệu mới. Người phụ trách / người kiểm tra mỗi người một dòng.
        """
        Access = self.env["daily.task.assign.access"]
        Access.check("personnel", "view")
        only_self = not Access._is_manager()
        current_uid = self.env.uid
        board = self.with_context(
            daily_work_assign_feature="list"
        ).get_assign_board_data(search="")
        task_ids = []
        for section in board.get("sections") or []:
            for task in section.get("tasks") or []:
                if task.get("id"):
                    task_ids.append(task["id"])
        records = {rec.id: rec for rec in self.browse(task_ids)}
        seen = set()
        people = {}
        people_order = []
        area_cols = (
            ("south", "Miền Nam"),
            ("dtt", "Miền ĐTT"),
            ("north", "Miền Bắc"),
            ("office", "Văn phòng"),
        )

        def _area(task, user_id, role_key):
            own = []
            for key, label in area_cols:
                people_in_col = task.get(key) or []
                if any(u.get("id") == user_id for u in people_in_col):
                    own.append(label)
            if own:
                return ", ".join(own)
            # User phụ trách / User kiểm tra lấy từ hạng mục, không gom mọi miền.
            if role_key in ("assignee", "checker"):
                return ""
            on_row = [
                label
                for key, label in area_cols
                if task.get(key)
            ]
            return ", ".join(on_row)

        def _push(user, role_key, role_label, section, task, rec):
            user_id = user.get("id") if isinstance(user, dict) else user.id
            user_name = user.get("name") if isinstance(user, dict) else user.name
            if not user_id:
                return
            if only_self and user_id != current_uid:
                return
            key = (user_id, rec.id, role_key)
            if key in seen:
                return
            seen.add(key)
            if user_id not in people:
                people[user_id] = {
                    "id": user_id,
                    "name": user_name or "",
                    "categories": {},
                    "category_order": [],
                }
                people_order.append(user_id)
            bucket = people[user_id]
            cat_id = section.get("id") or "0"
            if cat_id not in bucket["categories"]:
                cat_name = (task.get("category") or "Khác").upper()
                bucket["categories"][cat_id] = {
                    "id": cat_id,
                    "title": "HẠNG MỤC %s. %s" % (section.get("code") or "", cat_name),
                    "lines": [],
                }
                bucket["category_order"].append(cat_id)
            dept = rec.work_group_id.department_id or rec.department_id
            team = rec.team_id
            checker_names = ", ".join(
                u.get("name") for u in (task.get("checker") or []) if u.get("name")
            )
            bucket["categories"][cat_id]["lines"].append({
                "assign_id": rec.id,
                "code": task.get("display_stt") or "",
                "name": task.get("name") or "",
                "region": _area(task, user_id, role_key),
                "region_key": rec.region or "",
                "role": role_label,
                "role_key": role_key,
                "user_id": user_id,
                "user_name": user_name or "",
                "task_checker_name": checker_names,
                "category_id": cat_id,
                "category": task.get("category") or "",
                "department_id": dept.id if dept else 0,
                "department": dept.display_name if dept else "",
                "team_id": team.id if team else 0,
                "team": team.display_name if team else "",
            })

        for section in board.get("sections") or []:
            for task in section.get("tasks") or []:
                rec = records.get(task.get("id"))
                if not rec:
                    continue
                for user in task.get("assignee") or []:
                    _push(user, "assignee", "Người phụ trách", section, task, rec)
                for key, _label in area_cols:
                    for user in task.get(key) or []:
                        _push(user, "assignee", "Người phụ trách", section, task, rec)
                for user in task.get("checker") or []:
                    _push(user, "checker", "User kiểm tra", section, task, rec)

        people_order.sort(key=lambda uid: (people[uid]["name"] or "").casefold())
        payload_people = []
        departments = {}
        teams = {}
        categories = {}
        regions = {}
        users = []
        for uid in people_order:
            person = people[uid]
            cats = []
            total = 0
            for cat_id in person["category_order"]:
                cat = person["categories"][cat_id]
                total += len(cat["lines"])
                cats.append({
                    "id": cat["id"],
                    "title": cat["title"],
                    "count": len(cat["lines"]),
                    "lines": cat["lines"],
                })
                categories[cat_id] = cat["title"]
                for line in cat["lines"]:
                    if line["department_id"]:
                        departments[line["department_id"]] = line["department"]
                    if line["team_id"]:
                        teams[line["team_id"]] = line["team"]
                    if line["region"]:
                        regions[line["region"]] = line["region"]
            payload_people.append({
                "id": person["id"],
                "name": person["name"],
                "count": total,
                "categories": cats,
            })
            users.append({"id": person["id"], "name": person["name"]})

        def _opt(mapping):
            return [
                {"id": key, "name": mapping[key]}
                for key in sorted(mapping, key=lambda k: (mapping[k] or "").casefold())
            ]

        return {
            "people": payload_people,
            "filters": {
                "departments": _opt(departments),
                "teams": _opt(teams),
                "users": users,
                "categories": _opt(categories),
                "regions": _opt(regions),
                "roles": [
                    {"id": "assignee", "name": "Người phụ trách"},
                    {"id": "checker", "name": "User kiểm tra"},
                ],
            },
        }
