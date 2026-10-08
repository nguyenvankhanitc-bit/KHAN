# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTaskAssignAccess(models.Model):
    """
    Phân quyền khối PHÂN CÔNG CÔNG VIỆC:
      - Thêm công việc (Thêm phân công)
      - Danh sách công việc (Danh sách phân công)
      - Hạng mục
      - Công việc theo nhân sự (mỗi user chỉ thấy việc và hạng mục của mình)
    Mỗi mục: Xem / Thêm / Chỉnh sửa / Xóa.
    """

    _name = "daily.task.assign.access"
    _description = "Phân quyền phân công công việc"
    _order = "employee_id"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="User được phân quyền",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('user_id', '!=', False)]",
    )
    department_id = fields.Many2one(
        related="employee_id.department_id",
        string="Bộ phận",
        store=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Tài khoản login",
        related="employee_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Ghi chú")

    # --- Thêm công việc (menu Thêm phân công) ---
    perm_add_view = fields.Boolean(string="Thêm CV: Xem", default=False)
    perm_add_create = fields.Boolean(string="Thêm CV: Thêm", default=False)
    perm_add_write = fields.Boolean(string="Thêm CV: Chỉnh sửa", default=False)
    perm_add_unlink = fields.Boolean(string="Thêm CV: Xóa", default=False)

    # --- Danh sách công việc (menu Danh sách phân công) ---
    perm_list_view = fields.Boolean(string="DS CV: Xem", default=False)
    perm_list_create = fields.Boolean(string="DS CV: Thêm", default=False)
    perm_list_write = fields.Boolean(string="DS CV: Chỉnh sửa", default=False)
    perm_list_unlink = fields.Boolean(string="DS CV: Xóa", default=False)

    # --- Hạng mục ---
    perm_category_view = fields.Boolean(string="Hạng mục: Xem", default=False)
    perm_category_create = fields.Boolean(string="Hạng mục: Thêm", default=False)
    perm_category_write = fields.Boolean(string="Hạng mục: Chỉnh sửa", default=False)
    perm_category_unlink = fields.Boolean(string="Hạng mục: Xóa", default=False)

    # --- Công việc theo nhân sự: chỉ việc và hạng mục của chính user ---
    perm_personnel_view = fields.Boolean(string="CV nhân sự: Xem", default=False)
    perm_personnel_create = fields.Boolean(string="CV nhân sự: Thêm", default=False)
    perm_personnel_write = fields.Boolean(string="CV nhân sự: Chỉnh sửa", default=False)
    perm_personnel_unlink = fields.Boolean(string="CV nhân sự: Xóa", default=False)

    _sql_constraints = [
        (
            "daily_task_assign_access_employee_uniq",
            "unique(employee_id)",
            "Đã có dòng phân quyền Phân công cho nhân viên này. Hãy sửa dòng hiện có.",
        )
    ]

    @api.depends(
        "employee_id",
        "perm_add_view",
        "perm_list_view",
        "perm_category_view",
        "perm_personnel_view",
    )
    def _compute_name(self):
        for rec in self:
            who = rec.employee_id.name or "?"
            parts = []
            if rec.perm_add_view or rec.perm_add_create or rec.perm_add_write or rec.perm_add_unlink:
                parts.append("Thêm CV")
            if rec.perm_list_view or rec.perm_list_create or rec.perm_list_write or rec.perm_list_unlink:
                parts.append("DS CV")
            if (
                rec.perm_category_view
                or rec.perm_category_create
                or rec.perm_category_write
                or rec.perm_category_unlink
            ):
                parts.append("Hạng mục")
            if (
                rec.perm_personnel_view
                or rec.perm_personnel_create
                or rec.perm_personnel_write
                or rec.perm_personnel_unlink
            ):
                parts.append("CV nhân sự")
            rec.name = "%s → [%s]" % (who, ", ".join(parts) or "chưa tick quyền")

    @api.onchange(
        "perm_add_create",
        "perm_add_write",
        "perm_add_unlink",
        "perm_list_create",
        "perm_list_write",
        "perm_list_unlink",
        "perm_category_create",
        "perm_category_write",
        "perm_category_unlink",
        "perm_personnel_create",
        "perm_personnel_write",
        "perm_personnel_unlink",
    )
    def _onchange_implies_view(self):
        if self.perm_add_create or self.perm_add_write or self.perm_add_unlink:
            self.perm_add_view = True
        if self.perm_list_create or self.perm_list_write or self.perm_list_unlink:
            self.perm_list_view = True
        if self.perm_category_create or self.perm_category_write or self.perm_category_unlink:
            self.perm_category_view = True
        if (
            self.perm_personnel_create
            or self.perm_personnel_write
            or self.perm_personnel_unlink
        ):
            self.perm_personnel_view = True

    @api.constrains("employee_id")
    def _check_employee_user(self):
        for rec in self:
            if not rec.employee_id.user_id:
                raise ValidationError(
                    "«%s» chưa gắn Related User — không đăng nhập được để dùng quyền."
                    % (rec.employee_id.name or "")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._vals_imply_view(vals)
        records = super().create(vals_list)
        self._invalidate_access_cache()
        return records

    def write(self, vals):
        self._vals_imply_view(vals)
        res = super().write(vals)
        self._invalidate_access_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self._invalidate_access_cache()
        return res

    def _invalidate_access_cache(self):
        """Xóa cache sau khi response đã trả — tránh cắt request Lưu trên trình duyệt."""
        registry = self.env.registry
        self.env.cr.postcommit.add(registry.clear_cache)

    @staticmethod
    def _vals_imply_view(vals):
        if vals.get("perm_add_create") or vals.get("perm_add_write") or vals.get("perm_add_unlink"):
            vals["perm_add_view"] = True
        if vals.get("perm_list_create") or vals.get("perm_list_write") or vals.get("perm_list_unlink"):
            vals["perm_list_view"] = True
        if (
            vals.get("perm_category_create")
            or vals.get("perm_category_write")
            or vals.get("perm_category_unlink")
        ):
            vals["perm_category_view"] = True
        if (
            vals.get("perm_personnel_create")
            or vals.get("perm_personnel_write")
            or vals.get("perm_personnel_unlink")
        ):
            vals["perm_personnel_view"] = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _is_manager(self, user=None):
        user = user or self.env.user
        return user.has_group("daily_work_task.group_daily_work_manager")

    @api.model
    def _line_for_user(self, user=None):
        user = user or self.env.user
        return self.sudo().search(
            [("active", "=", True), ("user_id", "=", user.id)],
            limit=1,
        )

    @api.model
    def get_access_map(self, user=None):
        """
        Trả về dict quyền cho UI / kiểm tra server.
        Manager → tất cả True.
        """
        user = user or self.env.user
        full = {
            "add": {"view": True, "create": True, "write": True, "unlink": True},
            "list": {"view": True, "create": True, "write": True, "unlink": True},
            "category": {"view": True, "create": True, "write": True, "unlink": True},
            "personnel": {"view": True, "create": True, "write": True, "unlink": True},
        }
        if self._is_manager(user):
            return full
        line = self._line_for_user(user)
        if not line:
            empty = {"view": False, "create": False, "write": False, "unlink": False}
            return {
                "add": dict(empty),
                "list": dict(empty),
                "category": dict(empty),
                "personnel": dict(empty),
            }
        return {
            "add": {
                "view": bool(line.perm_add_view),
                "create": bool(line.perm_add_create),
                "write": bool(line.perm_add_write),
                "unlink": bool(line.perm_add_unlink),
            },
            "list": {
                "view": bool(line.perm_list_view),
                "create": bool(line.perm_list_create),
                "write": bool(line.perm_list_write),
                "unlink": bool(line.perm_list_unlink),
            },
            "category": {
                "view": bool(line.perm_category_view),
                "create": bool(line.perm_category_create),
                "write": bool(line.perm_category_write),
                "unlink": bool(line.perm_category_unlink),
            },
            "personnel": {
                "view": bool(line.perm_personnel_view),
                "create": bool(line.perm_personnel_create),
                "write": bool(line.perm_personnel_write),
                "unlink": bool(line.perm_personnel_unlink),
            },
        }

    @api.model
    def can(self, feature, action="view", user=None):
        """
        feature: 'add' | 'list' | 'category'
        action:  'view' | 'create' | 'write' | 'unlink'
        """
        amap = self.get_access_map(user=user)
        feat = amap.get(feature) or {}
        return bool(feat.get(action))

    @api.model
    def check(self, feature, action="view", user=None):
        if self.env.su:
            return
        if not self.can(feature, action, user=user):
            labels = {
                "add": "Thêm công việc",
                "list": "Danh sách công việc",
                "category": "Hạng mục",
                "personnel": "Công việc theo nhân sự",
            }
            acts = {
                "view": "xem",
                "create": "thêm",
                "write": "chỉnh sửa",
                "unlink": "xóa",
            }
            raise AccessError(
                "Bạn không có quyền %s «%s»."
                % (acts.get(action, action), labels.get(feature, feature))
            )

    @api.model
    def can_any_assign_menu(self, user=None):
        amap = self.get_access_map(user=user)
        return bool(
            amap["add"]["view"]
            or amap["list"]["view"]
            or amap["category"]["view"]
            or amap["personnel"]["view"]
        )

    @api.model
    def get_assign_access_matrix(self):
        """Dữ liệu ma trận phân quyền (OWL)."""
        if not self._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền phân công.")
        Employee = self.env["hr.employee"].sudo()
        employees = Employee.search(
            [("user_id", "!=", False), ("active", "=", True)],
            order="name",
        )
        emp_payload = [
            {
                "id": e.id,
                "name": e.name or "",
                "department_id": e.department_id.id if e.department_id else 0,
                "department_name": e.department_id.display_name if e.department_id else "",
            }
            for e in employees
        ]
        lines = self.sudo().search([], order="department_id, employee_id")
        # Gộp user cùng phòng ban + cùng bộ quyền → 1 dòng UI (nhiều employee_ids)
        grouped = {}
        for line in lines:
            emp = line.employee_id
            if not emp:
                continue
            dept_id = line.department_id.id if line.department_id else 0
            add = {
                "view": bool(line.perm_add_view),
                "create": bool(line.perm_add_create),
                "write": bool(line.perm_add_write),
                "unlink": bool(line.perm_add_unlink),
            }
            lst = {
                "view": bool(line.perm_list_view),
                "create": bool(line.perm_list_create),
                "write": bool(line.perm_list_write),
                "unlink": bool(line.perm_list_unlink),
            }
            cat = {
                "view": bool(line.perm_category_view),
                "create": bool(line.perm_category_create),
                "write": bool(line.perm_category_write),
                "unlink": bool(line.perm_category_unlink),
            }
            personnel = {
                "view": bool(line.perm_personnel_view),
                "create": bool(line.perm_personnel_create),
                "write": bool(line.perm_personnel_write),
                "unlink": bool(line.perm_personnel_unlink),
            }

            def _sig(g):
                return tuple(bool(g.get(k)) for k in ("view", "create", "write", "unlink"))

            key = (dept_id, _sig(add), _sig(lst), _sig(cat), _sig(personnel))
            if key not in grouped:
                grouped[key] = {
                    "id": line.id,
                    "employee_id": emp.id,
                    "employee_ids": [],
                    "employee_names": [],
                    "record_ids": {},
                    "department_id": dept_id,
                    "department_name": line.department_id.display_name
                    if line.department_id
                    else "",
                    "add": add,
                    "list": lst,
                    "category": cat,
                    "personnel": personnel,
                }
            bucket = grouped[key]
            if emp.id not in bucket["employee_ids"]:
                bucket["employee_ids"].append(emp.id)
                bucket["employee_names"].append(emp.name or "")
            bucket["record_ids"][str(emp.id)] = line.id
        rows = list(grouped.values())
        return {"rows": rows, "employees": emp_payload}

    @api.model
    def save_assign_access_matrix(self, rows):
        """Lưu ma trận: tạo / cập nhật / xóa dòng không còn trong payload."""
        if not self._is_manager():
            raise AccessError("Chỉ Quản lý mới cấu hình phân quyền phân công.")
        rows = rows or []
        keep_ids = set()
        for row in rows:
            emp_id = int(row.get("employee_id") or 0)
            if not emp_id:
                continue
            vals = self._matrix_row_to_vals(row)
            # Luôn ghi theo nhân viên — id trên UI có thể là bản ghi của user khác trong cùng dòng
            existing = self.sudo().search([("employee_id", "=", emp_id)], limit=1)
            if existing:
                existing.write(vals)
                keep_ids.add(existing.id)
            else:
                vals["employee_id"] = emp_id
                created = self.sudo().create([vals])
                keep_ids.add(created.id)
        # Xóa dòng không còn trên ma trận
        if keep_ids:
            obsolete = self.search([("id", "not in", list(keep_ids))])
        else:
            obsolete = self.search([])
        if obsolete:
            obsolete.unlink()
        return True

    @api.model
    def _matrix_row_to_vals(self, row):
        add = row.get("add") or {}
        lst = row.get("list") or {}
        cat = row.get("category") or {}
        personnel = row.get("personnel") or {}

        def _norm(group):
            view = bool(group.get("view"))
            create = bool(group.get("create"))
            write = bool(group.get("write"))
            unlink = bool(group.get("unlink"))
            if create or write or unlink:
                view = True
            if not view:
                create = write = unlink = False
            return view, create, write, unlink

        av, ac, aw, au = _norm(add)
        lv, lc, lw, lu = _norm(lst)
        cv, cc, cw, cu = _norm(cat)
        pv, pc, pw, pu = _norm(personnel)
        return {
            "perm_add_view": av,
            "perm_add_create": ac,
            "perm_add_write": aw,
            "perm_add_unlink": au,
            "perm_list_view": lv,
            "perm_list_create": lc,
            "perm_list_write": lw,
            "perm_list_unlink": lu,
            "perm_category_view": cv,
            "perm_category_create": cc,
            "perm_category_write": cw,
            "perm_category_unlink": cu,
            "perm_personnel_view": pv,
            "perm_personnel_create": pc,
            "perm_personnel_write": pw,
            "perm_personnel_unlink": pu,
            "active": True,
        }
