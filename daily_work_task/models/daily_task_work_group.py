# -*- coding: utf-8 -*-

import copy
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_USER_DOMAIN = "[('share', '=', False), ('active', '=', True)]"


class DailyTaskWorkGroup(models.Model):
    """Nhóm công việc theo phòng ban — gắn User chi tiết / Kiểm chi tiết / tổng."""

    _name = "daily.task.work.group"
    _description = "Nhóm công việc"
    _order = "department_id, sequence, name, id"
    _rec_names_search = ["name", "task_name"]

    sequence = fields.Integer(string="Thứ tự", default=10, index=True)
    display_stt = fields.Char(
        string="STT",
        compute="_compute_display_stt",
        store=False,
        help="Số thứ tự dạng 1.1, 1.2… theo nhóm hạng mục (giống bảng phân công).",
    )
    name = fields.Char(string="Hạng mục", required=True, index=True)
    task_name = fields.Char(
        string="Tên chi tiết hạng mục",
        index=True,
        help="Tên công việc mẫu của hạng mục. Phân công con sẽ lấy làm nội dung mặc định.",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        required=True,
        index=True,
        ondelete="restrict",
        default=lambda self: self.env["daily.task.assign"]._department_from_user(),
        help="Tự lấy theo phòng ban trên hồ sơ nhân viên của user đăng nhập.",
    )
    dept_locked = fields.Boolean(
        compute="_compute_dept_locked",
        help="Phòng ban tự lấy theo user đăng nhập — chỉ Quản lý được đổi.",
    )

    @api.depends_context("uid")
    def _compute_dept_locked(self):
        locked = not self.env["daily.task.assign.access"]._is_manager()
        for rec in self:
            rec.dept_locked = locked
    team_id = fields.Many2one(
        "daily.task.team",
        string="Team",
        index=True,
        ondelete="restrict",
        domain="[('department_id', '=', department_id), ('active', '=', True)]",
        default=lambda self: self._team_from_user(),
        help="Team thuộc phòng ban. Tự lấy theo user (quản lý Team, hoặc Team của các hạng mục user đang tham gia).",
    )
    assignee_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_assignee_user_rel",
        "group_id",
        "user_id",
        string="User phụ trách",
        domain=_USER_DOMAIN,
        help="Người phụ trách hạng mục. Tự chọn, không điền sẵn.",
    )
    # User quản lý cả Hạng mục (vd: I. Camera của team IT) — lưu giống nhau trên mọi dòng cùng hạng mục
    category_manager_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_cat_manager_rel",
        "group_id",
        "user_id",
        string="User quản lý hạng mục",
        domain=_USER_DOMAIN,
        help="Người quản lý cả hạng mục: được thêm/sửa việc chung, mặc định là Kiểm soát việc mới "
        "và được duyệt Plan của thành viên có việc trong hạng mục.",
    )
    checker_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_checker_user_rel",
        "group_id",
        "user_id",
        string="User kiểm tra",
        domain=_USER_DOMAIN,
        help="Người kiểm tra hạng mục. Tự chọn, không điền sẵn.",
    )
    detail_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_detail_user_rel",
        "group_id",
        "user_id",
        string="User chi tiết",
        domain=_USER_DOMAIN,
        help="User được áp dụng hạng mục này (chi tiết).",
    )
    detail_check_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_detail_check_user_rel",
        "group_id",
        "user_id",
        string="User Kiểm chi tiết",
        domain=_USER_DOMAIN,
        help="User kiểm chi tiết được áp dụng hạng mục này.",
    )
    total_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_total_user_rel",
        "group_id",
        "user_id",
        string="User tổng",
        domain=_USER_DOMAIN,
        help="User tổng được áp dụng hạng mục này.",
    )
    # Phân công theo miền / văn phòng
    south_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_south_user_rel",
        "group_id",
        "user_id",
        string="Miền Nam",
        domain=_USER_DOMAIN,
    )
    dtt_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_dtt_user_rel",
        "group_id",
        "user_id",
        string="Miền ĐTT",
        domain=_USER_DOMAIN,
    )
    north_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_north_user_rel",
        "group_id",
        "user_id",
        string="Miền Bắc",
        domain=_USER_DOMAIN,
    )
    vptt_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_vptt_user_rel",
        "group_id",
        "user_id",
        string="VPTT",
        domain=_USER_DOMAIN,
    )
    vpmb_user_ids = fields.Many2many(
        "res.users",
        "daily_task_work_group_vpmb_user_rel",
        "group_id",
        "user_id",
        string="VPMB",
        domain=_USER_DOMAIN,
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Ghi chú")
    task_count = fields.Integer(
        string="Số công việc",
        compute="_compute_task_count",
    )

    _sql_constraints = [
        (
            "daily_task_work_group_uniq",
            "unique(department_id, name, task_name)",
            "Hạng mục + Tên công việc này đã tồn tại trong phòng ban.",
        )
    ]

    # Form: chọn hạng mục đã có → điền sẵn tên / phòng ban / team / quản lý để thêm CV con
    pick_category_id = fields.Many2one(
        "daily.task.work.group",
        string="Chọn hạng mục có sẵn",
        compute="_compute_pick_category",
        readonly=False,
        store=False,
        help="Hạng mục đã có: chọn để thêm Tên công việc con vào hạng mục đó.",
    )
    last_saved_label = fields.Char(compute="_compute_last_saved_label")
    category_task_names = fields.Text(
        string="Công việc đã có trong hạng mục",
        compute="_compute_category_task_names",
    )

    category_head_id = fields.Many2one(
        "daily.task.work.group",
        string="Nhóm hạng mục",
        index=True,
        readonly=True,
        ondelete="set null",
        help="Dòng đại diện của hạng mục (cùng team + cùng tên) — dùng để group danh sách theo hạng mục.",
    )

    def init(self):
        super().init()
        # Bản cũ có ràng buộc unique(department_id, name) → không thêm được CV con cho hạng mục đã có.
        # Gỡ mọi ràng buộc / index UNIQUE còn sót trên (department_id, name).
        self.env.cr.execute(
            """
            SELECT conname FROM pg_constraint
             WHERE conrelid = 'daily_task_work_group'::regclass AND contype = 'u'
            """
        )
        for (conname,) in self.env.cr.fetchall():
            self.env.cr.execute('ALTER TABLE daily_task_work_group DROP CONSTRAINT IF EXISTS "%s"' % conname)
        self.env.cr.execute(
            """
            SELECT indexname FROM pg_indexes
             WHERE tablename = 'daily_task_work_group' AND indexdef ILIKE '%%unique%%'
               AND indexname <> 'daily_task_work_group_pkey'
            """
        )
        for (idx,) in self.env.cr.fetchall():
            self.env.cr.execute('DROP INDEX IF EXISTS "%s"' % idx)
        try:
            self.sudo()._refresh_category_heads()
        except Exception:  # noqa: BLE001 — chưa đủ cột lúc cài mới
            pass

    @api.model
    def _refresh_category_heads(self, team_ids=None):
        """Gán category_head_id = dòng nhỏ nhất (sequence, id) của mỗi hạng mục trong team."""
        domain = [("active", "=", True)]
        if team_ids is not None:
            team_ids = [t for t in team_ids if t]
            domain.append(("team_id", "in", team_ids) if team_ids else ("team_id", "=", False))
        rows = self.sudo().with_context(active_test=False).search(domain, order="sequence, id")
        heads = {}
        updates = {}
        for g in rows:
            key = (g.team_id.id, g.department_id.id if not g.team_id else 0,
                   self._norm_category_name(g.name).casefold())
            head = heads.setdefault(key, g.id)
            if g.category_head_id.id != head:
                updates.setdefault(head, []).append(g.id)
        for head, ids in updates.items():
            self.env.cr.execute(
                "UPDATE daily_task_work_group SET category_head_id = %s WHERE id IN %s",
                (head, tuple(ids)),
            )
        if updates:
            self.invalidate_model(["category_head_id"])

    @staticmethod
    def _norm_category_name(name):
        """Bỏ tiền tố số (1. / 2.) và số La Mã (III. / IV.) để nhóm hạng mục giống bảng phân công.

        «III. INTERNET» và «INTERNET» là cùng 1 hạng mục.
        """
        raw = " ".join((name or "").split())
        cleaned = re.sub(r"^(?:(?:\d+|[IVXLCDM]+)[.)]\s+)+", "", raw).strip()
        return cleaned or raw

    @api.depends("sequence", "name", "department_id", "team_id", "task_name", "active")
    def _compute_display_stt(self):
        """STT dạng 1.1, 1.2, 2.1… — đánh lại trong mỗi Team (chưa có Team: theo phòng ban).

        Thứ tự giống trang «Danh sách hạng mục»: hạng mục theo sequence nhỏ nhất rồi tên,
        công việc con theo sequence rồi tên.
        """
        depts = self.mapped("department_id")
        domain = [("active", "=", True)]
        if depts:
            domain.append(("department_id", "in", depts.ids))
        siblings = self.sudo().search(domain, order="department_id, sequence, id")
        by_scope = {}
        for g in siblings:
            scope = (g.department_id.id, g.team_id.id or 0)
            by_scope.setdefault(scope, []).append(g)

        computed = {}
        for rows in by_scope.values():
            cats = {}
            for g in rows:
                key = self._norm_category_name(g.name).casefold()
                cats.setdefault(key, []).append(g)
            ordered = sorted(
                cats.items(),
                key=lambda kv: (min(int(r.sequence or 0) for r in kv[1]), kv[0]),
            )
            for c_idx, (_key, items) in enumerate(ordered, start=1):
                items = sorted(items, key=lambda r: (int(r.sequence or 0), (r.task_name or "").casefold(), r.id))
                for t_idx, g in enumerate(items, start=1):
                    computed[g.id] = "%s.%s" % (c_idx, t_idx)

        for rec in self:
            rec.display_stt = computed.get(rec.id) or (
                str(rec.sequence) if rec.sequence else ""
            )

    @api.model
    def action_renumber_stt(self):
        """Đánh lại thứ tự từ nhỏ → lớn theo hạng mục rồi tên công việc."""
        groups = self.sudo().search(
            [("active", "=", True)],
            order="department_id, sequence, id",
        )
        by_dept = {}
        for g in groups:
            by_dept.setdefault(g.department_id.id, []).append(g)

        seq = 1
        for rows in by_dept.values():
            # Giữ thứ tự hạng mục theo sequence nhỏ nhất hiện có
            cat_first_seq = {}
            cat_rows = {}
            for g in rows:
                key = self._norm_category_name(g.name).casefold()
                cat_rows.setdefault(key, []).append(g)
                cat_first_seq[key] = min(
                    cat_first_seq.get(key, g.sequence or 10**9),
                    int(g.sequence or 10**9),
                )
            ordered_cats = sorted(cat_rows.keys(), key=lambda k: (cat_first_seq[k], k))
            for key in ordered_cats:
                items = sorted(
                    cat_rows[key],
                    key=lambda r: (int(r.sequence or 0), (r.task_name or "").casefold(), r.id),
                )
                clean_name = self._norm_category_name(items[0].name)
                for g in items:
                    vals = {"sequence": seq}
                    if self._norm_category_name(g.name) != clean_name or g.name != clean_name:
                        vals["name"] = clean_name
                    g.write(vals)
                    seq += 1
        return {"renumbered": seq - 1}

    @api.model
    def _roman(self, n):
        vals = (
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        )
        out = []
        num = int(n or 0)
        for value, numeral in vals:
            while num >= value:
                out.append(numeral)
                num -= value
        return "".join(out) or "I"

    @api.model
    def get_category_board_data(self, search=""):
        """Dữ liệu bảng hạng mục — nhớ trong 1 request (Plan tổng / báo cáo gọi lại nhiều lần)."""
        data = self.env["daily.task"]._req_cache(
            ("cat_board", self.env.uid, self.env.su, (search or "").strip().lower()),
            lambda: self._get_category_board_data_raw(search),
        )
        return copy.deepcopy(data)

    @api.model
    def _team_scope(self):
        """Phạm vi xem hạng mục — 1 luật chung cho mọi trang (Cài đặt → Bộ phận → Team).

        - User đã được gán Team (User quản lý team / User Group): CHỈ hạng mục của Team đó
          (kể cả Quản lý module; dòng chưa gán Team không hiện).
        - User chưa thuộc Team nào: Quản lý module → tất cả (None); người khác → theo phòng ban.
        Trả về None hoặc {"teams": set|None, "depts": set}.
        """
        if self.env.su:
            return None
        uid = self.env.uid
        teams = self.env["daily.task.team"].sudo().search(
            [("active", "=", True), "|", ("manager_ids", "in", uid), ("member_ids", "in", uid)]
        )
        depts = set(d for d in self.env["daily.task"].rule_team_department_ids() if d)
        if teams:
            return {"teams": set(teams.ids), "depts": depts | set(teams.mapped("department_id").ids)}
        if self.env["daily.task.assign.access"]._is_manager():
            return None
        return {"teams": None, "depts": depts}

    @api.model
    def _team_scope_domain(self):
        """Domain lọc hạng mục theo _team_scope (None = không lọc)."""
        scope = self._team_scope()
        if scope is None:
            return None
        if scope["teams"] is not None:
            return [("team_id", "in", list(scope["teams"]))]
        return [("department_id", "in", list(scope["depts"]) or [0])]

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        # Trang / ô chọn có context work_group_team_scope → chỉ hạng mục trong phạm vi Team của user
        if self.env.context.get("work_group_team_scope") and not self.env.su:
            extra = self._team_scope_domain()
            if extra:
                domain = list(domain or []) + extra
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def _in_team_scope(self, scope, team_id, dept_id):
        if scope is None:
            return True
        if scope["teams"] is None:
            return bool(dept_id) and dept_id in scope["depts"]
        # Đã được gán Team: chỉ hạng mục của Team mình (dòng chưa gán Team không hiện)
        return bool(team_id) and team_id in scope["teams"]

    @api.model
    def get_category_board_view(self, search=""):
        """Trang «Danh sách hạng mục công việc»: Quản lý thấy tất cả; người khác chỉ thấy
        Team của mình theo Cài đặt → Bộ phận → Team (+ dòng chưa gán Team của phòng ban mình)."""
        data = self.get_category_board_data(search)
        scope = self._team_scope()
        if scope is None:
            return data
        depts = []
        for d in data.get("departments") or []:
            try:
                dept_id = int(str(d.get("id") or "").replace("dept-", "") or 0)
            except ValueError:
                dept_id = 0
            teams = [t for t in d.get("teams") or [] if self._in_team_scope(scope, t.get("team_id"), dept_id)]
            if not teams:
                continue
            d["teams"] = teams
            d["team_count"] = len(teams)
            d["task_count"] = sum(t.get("task_count") or 0 for t in teams)
            depts.append(d)
        data["departments"] = depts
        data["task_count"] = sum(d["task_count"] for d in depts)
        return data
        user = self.env.user
        dept_ids = set(d for d in self.env["daily.task"].rule_team_department_ids() if d)
        teams = self.env["daily.task.team"].sudo().search(
            ["|", ("manager_ids", "in", user.id), ("member_ids", "in", user.id)]
        )
        dept_ids |= set(teams.mapped("department_id").ids)
        allowed = {"dept-%s" % i for i in dept_ids}
        depts = [d for d in data.get("departments") or [] if d.get("id") in allowed]
        data["departments"] = depts
        data["task_count"] = sum(
            len(c.get("tasks") or [])
            for d in depts for t in d.get("teams") or [] for c in t.get("categories") or []
        )
        return data

    @api.model
    def _get_category_board_data_raw(self, search=""):
        """Dữ liệu bảng hạng mục — group: Phòng ban → Team → Hạng mục → CV con."""
        needle = (search or "").strip().lower()
        assign_users = self._role_users_from_assigns()
        # Tần suất (Ngày / Tuần / Tháng) = ô đã tích trên Thêm phân công công việc của tên CV này
        freq_map = {}
        for line in self.env["daily.task.assign"].sudo().search(
            [("active", "=", True), ("work_group_id", "!=", False)], order="stt, id"
        ):
            key = line._frequency_key()
            if key:
                freq_map.setdefault(line.work_group_id.id, key)
        groups = self.search(
            [("active", "=", True)],
            order="department_id, sequence, id",
        )
        # dept_id -> {name, teams: team_key -> {...}}
        depts = {}
        dept_order = []

        for g in groups:
            cat = self._norm_category_name(g.name)
            dept_id = g.department_id.id if g.department_id else 0
            dept_name = (
                g.department_id.display_name
                if g.department_id
                else "Chưa có phòng ban"
            )
            team_id = g.team_id.id if g.team_id else 0
            team_name = g.team_id.name if g.team_id else "Chưa gán Team"
            team_seq = int(g.team_id.sequence or 0) if g.team_id else 10**9
            task_name = (g.task_name or "").strip()
            if needle:
                blob = " ".join([cat, task_name, dept_name, team_name]).lower()
                if needle not in blob:
                    continue

            if dept_id not in depts:
                depts[dept_id] = {
                    "id": "dept-%s" % dept_id,
                    "name": dept_name,
                    "teams": {},
                    "team_order": [],
                }
                dept_order.append(dept_id)

            dept = depts[dept_id]
            tkey = (team_id, team_name.casefold())
            if tkey not in dept["teams"]:
                dept["teams"][tkey] = {
                    "id": "dept-%s-team-%s" % (dept_id, team_id or "none"),
                    "name": team_name,
                    "title": "Team: %s" % team_name,
                    "sequence": team_seq,
                    "team_id": team_id or False,
                    "managers": g.team_id.manager_ids if g.team_id else self.env["res.users"],
                    "categories": {},
                    "cat_order": [],
                }
                dept["team_order"].append(tkey)

            team = dept["teams"][tkey]
            ckey = cat.casefold()
            if ckey not in team["categories"]:
                team["categories"][ckey] = {
                    "id": "dept-%s-team-%s-cat-%s"
                    % (dept_id, team_id or "none", ckey),
                    "name": cat,
                    "sequence": int(g.sequence or 0),
                    "tasks": [],
                    "group_id": g.id,
                    "managers": self.env["res.users"],
                }
                team["cat_order"].append(ckey)
            else:
                team["categories"][ckey]["sequence"] = min(
                    team["categories"][ckey]["sequence"],
                    int(g.sequence or 0),
                )
            team["categories"][ckey]["managers"] |= g.category_manager_ids

            linked = assign_users.get(g.id) or {}
            assignees = g.assignee_user_ids | linked.get(
                "assignees", self.env["res.users"]
            )
            checkers = g.checker_user_ids | linked.get(
                "checkers", self.env["res.users"]
            )
            team["categories"][ckey]["tasks"].append(
                {
                    "id": g.id,
                    "name": task_name or cat,
                    "sequence": int(g.sequence or 0),
                    "department": dept_name,
                    "team": team_name if team_id else "",
                    "team_id": team_id or False,
                    "freq": freq_map.get(g.id) or "",
                    "assignees": self._user_tags(assignees),
                    "checkers": self._user_tags(checkers),
                }
            )

        departments = []
        global_cat_idx = 0
        task_count = 0
        for dept_id in dept_order:
            dept = depts[dept_id]
            teams_out = []
            # Team theo sequence rồi tên
            ordered_teams = sorted(
                dept["team_order"],
                key=lambda k: (
                    dept["teams"][k]["sequence"],
                    dept["teams"][k]["name"].casefold(),
                ),
            )
            for tkey in ordered_teams:
                team = dept["teams"][tkey]
                cats_out = []
                global_cat_idx = 0  # mỗi team đánh lại I, II, III…
                ordered_cats = sorted(
                    team["cat_order"],
                    key=lambda k: (
                        team["categories"][k]["sequence"],
                        team["categories"][k]["name"].casefold(),
                    ),
                )
                for ckey in ordered_cats:
                    global_cat_idx += 1
                    cat = team["categories"][ckey]
                    tasks_sorted = sorted(
                        cat["tasks"],
                        key=lambda t: (t["sequence"], (t["name"] or "").casefold(), t["id"]),
                    )
                    tasks = []
                    for t_idx, task in enumerate(tasks_sorted, start=1):
                        tasks.append(
                            {
                                **task,
                                "display_stt": "%s.%s" % (global_cat_idx, t_idx),
                            }
                        )
                    task_count += len(tasks)
                    cats_out.append(
                        {
                            "id": cat["id"],
                            "name": cat["name"],
                            "code": self._roman(global_cat_idx),
                            "title": "Hạng mục: %s. %s"
                            % (self._roman(global_cat_idx), (cat["name"] or "").upper()),
                            "tone": "alt" if global_cat_idx % 3 == 0 else "default",
                            "task_count": len(tasks),
                            "tasks": tasks,
                            # User quản lý hạng mục
                            "group_id": cat["group_id"],
                            "managers": self._user_tags(cat["managers"]),
                        }
                    )
                teams_out.append(
                    {
                        "id": team["id"],
                        "name": team["name"],
                        "title": team["title"],
                        "team_id": team["team_id"],
                        "managers": self._user_tags(team["managers"]),
                        "category_count": len(cats_out),
                        "task_count": sum(c["task_count"] for c in cats_out),
                        "categories": cats_out,
                    }
                )
            departments.append(
                {
                    "id": dept["id"],
                    "name": dept["name"],
                    "title": (dept["name"] or "").upper(),
                    "team_count": len(teams_out),
                    "task_count": sum(t["task_count"] for t in teams_out),
                    "teams": teams_out,
                }
            )

        Access = self.env["daily.task.assign.access"]
        Access.check("category", "view")
        access = Access.get_access_map().get("category") or {}
        return {
            "departments": departments,
            "task_count": task_count,
            # giữ key cũ để tương thích tạm
            "sections": [],
            "access": {
                "view": bool(access.get("view")),
                "create": bool(access.get("create")),
                "write": bool(access.get("write")),
                "unlink": bool(access.get("unlink")),
                # Chọn User quản lý hạng mục: chỉ Quản lý module
                "set_manager": bool(Access._is_manager()),
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        self.env["daily.task"]._req_cache_clear()
        self.env["daily.task.assign.access"].check("category", "create")
        records = super().create(vals_list)
        self._refresh_category_heads(records.mapped("team_id").ids or None)
        for rec, vals in zip(records, vals_list):
            if "category_manager_ids" in vals:
                continue
            managers = (rec._category_siblings() - rec).mapped("category_manager_ids")
            if managers:
                rec.sudo().with_context(skip_cat_manager_sync=True, skip_link_users=True).write(
                    {"category_manager_ids": [(6, 0, managers.ids)]}
                )
        return records

    def write(self, vals):
        self.env["daily.task"]._req_cache_clear()
        self.env["daily.task.assign.access"].check("category", "write")
        if "category_manager_ids" in vals and not self.env.su \
                and not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới chọn được User quản lý hạng mục.")
        old_teams = self.mapped("team_id").ids
        res = super().write(vals)
        if {"name", "team_id", "active", "sequence", "department_id"} & set(vals):
            self._refresh_category_heads(list(set(old_teams + self.mapped("team_id").ids)) or None)
        if {"name", "task_name"} & set(vals) and not self.env.context.get("skip_detail_name_sync"):
            self._sync_detail_name_to_assign()
        if "category_manager_ids" in vals and not self.env.context.get("skip_cat_manager_sync"):
            # Quản lý áp dụng cho cả hạng mục (mọi dòng cùng team + cùng tên hạng mục)
            for rec in self:
                others = rec._category_siblings() - rec
                if others:
                    others.with_context(skip_cat_manager_sync=True, skip_link_users=True).write(
                        {"category_manager_ids": [(6, 0, rec.category_manager_ids.ids)]}
                    )
        if self.env.context.get("skip_link_users"):
            return res
        link = {
            "assignee_user_ids": "assignee_user_ids",
            "checker_user_ids": "check_user_ids",
            "south_user_ids": "south_user_ids",
            "dtt_user_ids": "dtt_user_ids",
            "north_user_ids": "north_user_ids",
        }
        if not any(field in vals for field in link):
            return res
        Assign = self.env["daily.task.assign"].sudo()
        for rec in self:
            assigns = Assign.search(
                [("active", "=", True), ("work_group_id", "=", rec.id)]
            )
            for assign in assigns:
                updates = {}
                for wg_field, assign_field in link.items():
                    if wg_field not in vals:
                        continue
                    missing = [
                        user_id
                        for user_id in rec[wg_field].ids
                        if user_id not in assign[assign_field].ids
                    ]
                    if missing:
                        updates[assign_field] = [(4, user_id) for user_id in missing]
                if updates:
                    assign.with_context(skip_link_users=True).write(updates)
        return res

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        """Nhập danh sách hạng mục (nhóm Phòng ban > Team): mở sẵn cả nhóm Team, không cần bấm từng nhóm."""
        groups = super().formatted_read_group(
            domain, groupby=groupby, aggregates=aggregates, having=having,
            offset=offset, limit=limit, order=order,
        )
        if self.env.context.get("dwg_unfold_all") and groupby:
            for group in groups:
                group.setdefault("__fold", False)
        return groups

    def _sync_detail_name_to_assign(self):
        """Tên chi tiết hạng mục đổi → dòng phân công đang dùng (và việc cá nhân của nó) đổi tên theo."""
        Assign = self.env["daily.task.assign"].sudo()
        for rec in self:
            detail = self._norm_category_name(rec.task_name) if (rec.task_name or "").strip() \
                else self._norm_category_name(rec.name)
            if not detail:
                continue
            lines = Assign.search([("work_group_id", "=", rec.id), ("active", "=", True)])
            if not lines:
                continue
            lines.filtered(lambda ln: ln.name != detail).write({"name": detail})
            # Mẫu việc lặp + việc chưa hoàn thành đổi theo; việc đã hoàn thành giữ tên cũ (lịch sử)
            Rec = self.env["daily.task.recurring"].sudo()
            Rec.search([("assign_line_id", "in", lines.ids), ("name", "!=", detail)]).write({"name": detail})
            self.env["daily.task"].sudo().with_context(from_daily_task_assign=True).search([
                ("assign_line_id", "in", lines.ids), ("state", "!=", "done"), ("name", "!=", detail),
            ]).write({"name": detail})

    def _used_ids(self):
        """Dòng hạng mục đang được công việc / phân công / việc lặp dùng (không xoá cứng được)."""
        if not self:
            return set()
        used = set()
        for model, field in (
            ("daily.task", "work_group_id"),
            ("daily.task.assign", "work_group_id"),
            ("daily.task.recurring", "work_group_id"),
        ):
            if model not in self.env:
                continue
            rows = self.env[model].sudo().with_context(active_test=False).search_read(
                [(field, "in", self.ids)], [field]
            )
            used |= {r[field][0] for r in rows if r[field]}
        return used

    def unlink(self):
        """Xoá hạng mục: dòng chưa dùng → xoá hẳn; dòng đã có công việc → lưu trữ (ẩn), giữ lịch sử."""
        self.env["daily.task"]._req_cache_clear()
        if not self.env.context.get("skip_category_unlink_check"):
            self.env["daily.task.assign.access"].check("category", "unlink")
        teams = self.mapped("team_id").ids
        used = self._used_ids()
        to_archive = self.filtered(lambda g: g.id in used)
        if to_archive:
            to_archive.sudo().with_context(skip_link_users=True).write({"active": False})
        res = super(DailyTaskWorkGroup, self - to_archive).unlink()
        self._refresh_category_heads(teams or None)
        return res

    @api.model
    def rename_category(self, group_ids, new_name):
        """Nút «Sửa» trên dòng hạng mục: đổi tên hạng mục cho mọi công việc chi tiết của nó.

        Chỉ user có quyền «Chỉnh sửa» ở dòng Hạng mục (Cài đặt → Phân quyền phân công công việc).
        """
        self.env["daily.task.assign.access"].check("category", "write")
        name = " ".join((new_name or "").split())
        if not name:
            raise UserError("Vui lòng nhập tên hạng mục.")
        rows = self.sudo().browse([int(i) for i in group_ids or []]).exists()
        if not rows:
            raise UserError("Không có hạng mục để sửa.")
        # Trùng tên với hạng mục khác cùng Team → dùng «Gộp vào…» thay vì đổi tên
        team_ids = set(rows.mapped("team_id").ids) or {False}
        clash = self.sudo().search([("id", "not in", rows.ids), ("active", "=", True)]).filtered(
            lambda g: (g.team_id.id or False) in team_ids
            and self._norm_category_name(g.name).casefold() == self._norm_category_name(name).casefold()
        )
        if clash:
            raise UserError(
                "Team đã có hạng mục «%s». Dùng nút «Gộp vào…» để dồn vào hạng mục đó." % clash[:1].name
            )
        rows.with_context(skip_link_users=True, skip_cat_manager_sync=True).write({"name": name})
        self.env["daily.task"]._req_cache_clear()
        return {"name": name, "count": len(rows)}

    @api.model
    def merge_category(self, source_ids, target_id=None, new_name=None):
        """Gộp hạng mục: dồn các dòng của hạng mục nguồn vào hạng mục đích (hoặc tên hạng mục mới).

        Dòng chưa có Tên công việc → lấy tên hạng mục cũ (bỏ số thứ tự) làm Tên công việc,
        để «6. CHECK CAMERA ĐỐI CHIẾU…» thành công việc con của «Camera».
        """
        self.env["daily.task.assign.access"].check("category", "write")
        rows = self.sudo().browse([int(i) for i in source_ids or []]).exists()
        if not rows:
            raise UserError("Không có dòng hạng mục để gộp.")
        target = self.sudo().browse(int(target_id)).exists() if target_id else self.sudo().browse()
        name = (target.name if target else (new_name or "")).strip()
        if not name:
            raise UserError("Vui lòng chọn hạng mục đích hoặc nhập tên hạng mục mới.")
        clean_target = self._norm_category_name(name).casefold()
        managers = target._category_siblings().mapped("category_manager_ids") if target else self.env["res.users"]
        moved = 0
        for row in rows:
            if target and row == target:
                continue
            vals = {"name": name}
            if target:
                vals["team_id"] = target.team_id.id or False
                if target.department_id:
                    vals["department_id"] = target.department_id.id
            old_cat = self._norm_category_name(row.name)
            task = (row.task_name or "").strip()
            if not task and old_cat.casefold() != clean_target:
                vals["task_name"] = old_cat
            elif task and self._norm_category_name(task) != task:
                vals["task_name"] = self._norm_category_name(task)  # bỏ số thứ tự «1. …»
            if managers:
                vals["category_manager_ids"] = [(6, 0, managers.ids)]
            row.with_context(skip_link_users=True, skip_cat_manager_sync=True).write(vals)
            moved += 1
        self.env["daily.task"]._req_cache_clear()
        return {"moved": moved, "name": name}

    @api.model
    def delete_category(self, group_ids):
        """Nút «Xoá» trên dòng hạng mục: xoá mọi công việc con của hạng mục."""
        rows = self.sudo().browse([int(i) for i in group_ids or []]).exists()
        # Theo Phân quyền phân công công việc → dòng «Hạng mục» → cột «Xóa»
        self.env["daily.task.assign.access"].check("category", "unlink")
        used = rows._used_ids()
        archived = len([r for r in rows if r.id in used])
        rows.with_context(skip_category_unlink_check=True).unlink()
        return {"deleted": len(rows) - archived, "archived": archived}

    def action_save_and_continue(self):
        """Popup Thêm hạng mục: Lưu xong mở lại form cùng hạng mục (CV vừa thêm hiện trong danh sách)."""
        self.ensure_one()
        ctx = {
            "default_name": self.name,
            "default_department_id": self.department_id.id,
            "default_team_id": self.team_id.id or False,
            "default_sequence": self.sequence,
            "dwg_last_saved": self.task_name or self.name,
        }
        if self.category_manager_ids:
            ctx["default_category_manager_ids"] = [(6, 0, self.category_manager_ids.ids)]
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm công việc con: %s" % (self.name or ""),
            "res_model": self._name,
            "views": [[False, "form"]],
            "target": "new",
            "context": ctx,
        }

    @api.model
    def action_import_from_assign_board(self):
        """Đổ Tên công việc từ bảng phân công → bảng hạng mục (1 dòng / 1 công việc)."""
        Assign = self.env["daily.task.assign"].sudo()
        assigns = Assign.search([("active", "=", True), ("work_group_id", "!=", False)])
        created = 0
        linked = 0
        for assign in assigns:
            src = assign.work_group_id
            task_name = (assign.name or "").strip()
            if not task_name or not src:
                continue
            dest = self.sudo().search(
                [
                    ("department_id", "=", src.department_id.id),
                    ("name", "=", src.name),
                    ("task_name", "=", task_name),
                ],
                limit=1,
            )
            if not dest:
                dest = src.sudo().copy(
                    {
                        "task_name": task_name,
                        "sequence": assign.stt or src.sequence,
                        "active": True,
                    }
                )
                created += 1
            if assign.work_group_id.id != dest.id:
                assign.sudo().with_context(skip_assign_personal_sync=True).write(
                    {"work_group_id": dest.id}
                )
                linked += 1
        used_ids = Assign.search([("active", "=", True)]).mapped("work_group_id").ids
        orphan_domain = [("task_name", "in", [False, ""])]
        if used_ids:
            orphan_domain.append(("id", "not in", used_ids))
        orphans = self.sudo().search(orphan_domain)
        if orphans:
            orphans.write({"active": False})
        renumbered = self.action_renumber_stt().get("renumbered", 0)
        return {
            "created": created,
            "linked": linked,
            "hidden": len(orphans),
            "renumbered": renumbered,
        }

    @api.model
    def _user_tags(self, users):
        return [{"id": u.id, "name": u.name or ""} for u in users]

    @api.model
    def search_role_users(self, search=""):
        """User nội bộ để chọn User phụ trách / User kiểm tra trên hạng mục."""
        domain = [("share", "=", False), ("active", "=", True)]
        needle = (search or "").strip()
        if needle:
            domain.append(("name", "ilike", needle))
        users = self.env["res.users"].search(domain, order="name", limit=40)
        return self._user_tags(users)

    # ------------------------------------------------------------------
    # User quản lý hạng mục
    # ------------------------------------------------------------------
    def _category_siblings(self):
        """Mọi dòng đang dùng của cùng hạng mục (cùng team + cùng tên hạng mục, bỏ tiền tố số)."""
        self.ensure_one()
        key = self._norm_category_name(self.name).casefold()
        rows = self.sudo().search([("active", "=", True), ("team_id", "=", self.team_id.id or False)])
        return rows.filtered(lambda g: self._norm_category_name(g.name).casefold() == key)

    def _category_managers(self):
        users = self.env["res.users"]
        for wg in self:
            users |= wg._category_siblings().mapped("category_manager_ids")
        return users

    @api.model
    def _is_category_manager(self, wg, user=None):
        """User quản lý hạng mục, hoặc User quản lý team chứa hạng mục."""
        user = user or self.env.user
        if not wg:
            return False
        return user in wg._category_managers() or user in wg.sudo().team_id.manager_ids

    def set_category_managers(self, user_ids):
        """Chọn User quản lý cho cả hạng mục (ghi lên mọi dòng cùng hạng mục). Chỉ Quản lý module."""
        self.ensure_one()
        if not self.env["daily.task.assign.access"]._is_manager():
            raise AccessError("Chỉ Quản lý mới chọn được User quản lý hạng mục.")
        ids = []
        for raw in user_ids or []:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        users = self.env["res.users"].sudo().search(
            [("id", "in", ids), ("share", "=", False), ("active", "=", True)]
        )
        self._category_siblings().with_context(
            skip_cat_manager_sync=True, skip_link_users=True
        ).write({"category_manager_ids": [(6, 0, users.ids)]})
        return self._user_tags(users)

    def set_role_users(self, role, user_ids):
        """Người dùng tự chọn user phụ trách hoặc user kiểm tra của một hạng mục."""
        self.ensure_one()
        self.env["daily.task.assign.access"].check("category", "write")
        role_key = (role or "").strip()
        if role_key not in ("assignee", "checker"):
            raise UserError("Vai trò không hợp lệ.")
        field_name = (
            "assignee_user_ids" if role_key == "assignee" else "checker_user_ids"
        )
        ids = []
        for raw in user_ids or []:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        users = self.env["res.users"].search(
            [("id", "in", ids), ("share", "=", False), ("active", "=", True)]
        )
        self.write({field_name: [(6, 0, users.ids)]})
        self._sync_role_users_to_assigns(role_key, users)
        return self._user_tags(users)

    def _sync_role_users_to_assigns(self, role_key, users):
        """Cùng user trên hạng mục phải nằm trên dòng phân công của công việc đó."""
        self.ensure_one()
        Assign = self.env["daily.task.assign"].sudo()
        assigns = Assign.search(
            [("active", "=", True), ("work_group_id", "=", self.id)]
        )
        if not assigns:
            return
        if role_key == "assignee":
            assigns.write(
                {
                    "assignee_user_ids": [(6, 0, users.ids)],
                    "assignee_user_id": users[:1].id or False,
                }
            )
        else:
            assigns.write(
                {
                    "check_user_ids": [(6, 0, users.ids)],
                    "check_user_id": users[:1].id or False,
                }
            )

    def _role_users_from_assigns(self):
        """User phụ trách / User kiểm tra đang lưu trên bảng phân công, theo hạng mục."""
        Assign = self.env["daily.task.assign"].sudo()
        assigns = Assign.search([("active", "=", True), ("work_group_id", "!=", False)])
        Users = self.env["res.users"]
        grouped = {}
        for rec in assigns:
            bucket = grouped.setdefault(
                rec.work_group_id.id,
                {"assignees": Users, "checkers": Users},
            )
            assignees = rec.assignee_user_ids
            if rec.assignee_user_id:
                assignees |= rec.assignee_user_id
            checkers = rec.check_user_ids
            if rec.check_user_id:
                checkers |= rec.check_user_id
            bucket["assignees"] |= assignees
            bucket["checkers"] |= checkers
        return grouped

    def applicable_users(self):
        """Union mọi danh sách user gắn trên hạng mục (chi tiết + miền/VP)."""
        self.ensure_one()
        return (
            self.assignee_user_ids
            | self.checker_user_ids
            | self.detail_user_ids
            | self.detail_check_user_ids
            | self.total_user_ids
            | self.south_user_ids
            | self.dtt_user_ids
            | self.north_user_ids
            | self.vptt_user_ids
            | self.vpmb_user_ids
        )

    def is_user_applicable(self, user):
        """True nếu user được dùng hạng mục.

        - Không gắn user nào trên hạng mục → cả phòng ban.
        - Có gắn user trên hạng mục → đúng các user đó.
        - Hoặc user đã được phân công trên bảng Phân công (Miền/Phụ trách…) → cũng được.
        """
        self.ensure_one()
        if not user:
            return False
        uid = user.id if hasattr(user, "id") else int(user or 0)
        if not uid:
            return False
        users = self.applicable_users()
        if not users:
            return True
        if uid in users.ids:
            return True
        return self._is_user_on_assign_line(uid)

    def _is_user_on_assign_line(self, uid):
        """User xuất hiện trên dòng phân công gắn hạng mục này."""
        self.ensure_one()
        Assign = self.env["daily.task.assign"].sudo()
        return bool(
            Assign.search_count(
                [
                    ("active", "=", True),
                    ("work_group_id", "=", self.id),
                    "|",
                    "|",
                    "|",
                    "|",
                    ("assignee_user_ids", "in", [uid]),
                    ("south_user_ids", "in", [uid]),
                    ("dtt_user_ids", "in", [uid]),
                    ("north_user_ids", "in", [uid]),
                    ("office_user_ids", "in", [uid]),
                ]
            )
        )

    @api.depends("name", "task_name", "department_id")
    @api.depends_context("work_group_short_name", "work_group_show_task_name", "work_group_category_label")
    def _compute_display_name(self):
        """
        - work_group_short_name: chỉ cột Hạng mục (Camera, Email…)
        - work_group_show_task_name: chỉ cột Tên công việc
        - work_group_category_label: nhãn nhóm "Hạng mục: I. CAMERA" (group danh sách)
        - mặc định: Hạng mục (Phòng ban)
        """
        short = bool(self.env.context.get("work_group_short_name"))
        show_task = bool(self.env.context.get("work_group_show_task_name"))
        if self.env.context.get("work_group_category_label"):
            for rec in self:
                heads = self.sudo().search([
                    ("active", "=", True),
                    ("team_id", "=", rec.team_id.id or False),
                ]).mapped("category_head_id")
                ordered = heads.sorted(lambda h: (h.sequence, (h.name or "").casefold(), h.id))
                idx = (ordered.ids.index(rec.id) + 1) if rec.id in ordered.ids else 0
                name = self._norm_category_name(rec.name).upper()
                rec.display_name = "Hạng mục: %s. %s" % (self._roman(idx), name) if idx else name
            return
        for rec in self:
            label = (rec.name or "").strip()
            task = (rec.task_name or "").strip()
            if show_task:
                rec.display_name = task or self._norm_category_name(label)
            elif short:
                rec.display_name = self._norm_category_name(label)
            else:
                dept = rec.department_id.display_name if rec.department_id else ""
                rec.display_name = (
                    "%s (%s)" % (label, dept) if dept and label else (label or dept or "")
                )

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        """Dropdown Hạng mục: mỗi tên hạng mục chỉ hiện 1 lần."""
        if self.env.context.get("work_group_unique_category"):
            search_domain = list(domain or [])
            if name:
                search_domain.append(("name", operator, name))
            rows = self.search(
                search_domain,
                order="department_id, sequence, id",
                limit=(limit or 80) * 8,
            )
            seen = set()
            result = []
            for rec in rows:
                clean = self._norm_category_name(rec.name)
                # «II. MÁY VI TÍNH» = «MÁY VI TÍNH» (cùng team) → 1 dòng, giống trang Hạng mục
                key = (clean.casefold(), rec.department_id.id, rec.team_id.id or 0)
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                head = rec.category_head_id or rec
                result.append((head.id, clean))
                if limit and len(result) >= limit:
                    break
            return result
        result = super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        if self.env.context.get("work_group_show_task_name") and result:
            # Tên chi tiết hạng mục: ẩn dòng «chỉ có tên hạng mục» (vd «II. MÁY VI TÍNH» không có tên chi tiết)
            # khi hạng mục đó đã có công việc chi tiết khác.
            recs = self.sudo().browse([r[0] for r in result])
            has_detail = {g.category_head_id.id for g in recs if (g.task_name or "").strip()}
            result = [
                r for r, g in zip(result, recs)
                if (g.task_name or "").strip() or g.category_head_id.id not in has_detail
            ]
        return result

    def _compute_task_count(self):
        Task = self.env["daily.task"]
        for rec in self:
            rec.task_count = Task.search_count([("work_group_id", "=", rec.id)])

    @api.constrains("name", "department_id", "task_name", "active")
    def _check_name(self):
        for rec in self:
            if not (rec.name or "").strip():
                raise ValidationError("Vui lòng nhập tên nhóm công việc.")
            # Chỉ chặn trùng ĐÚNG: cùng phòng ban + cùng hạng mục + cùng tên công việc con.
            # Cùng hạng mục nhưng tên CV con khác (vd Internet → Thanh toán cước / Di dời lắp đặt) là hợp lệ.
            if not rec.active:
                continue
            key_cat = " ".join(self._norm_category_name(rec.name).split()).casefold()
            key_task = " ".join((rec.task_name or "").split()).casefold()
            others = self.search([
                ("id", "!=", rec.id),
                ("department_id", "=", rec.department_id.id),
                ("active", "=", True),
            ])
            for o in others:
                if (" ".join(self._norm_category_name(o.name).split()).casefold() == key_cat
                        and " ".join((o.task_name or "").split()).casefold() == key_task):
                    raise ValidationError(
                        "Hạng mục «%s» đã có công việc «%s» trong phòng ban này."
                        % (rec.name, rec.task_name or "")
                    )

    @api.constrains("team_id", "department_id")
    def _check_team_department(self):
        for rec in self:
            if (
                rec.team_id
                and rec.department_id
                and rec.team_id.department_id
                and rec.team_id.department_id != rec.department_id
            ):
                raise ValidationError(
                    "Team «%s» không thuộc phòng ban của hạng mục."
                    % (rec.team_id.display_name,)
                )

    def _compute_last_saved_label(self):
        saved = self.env.context.get("dwg_last_saved")
        for rec in self:
            rec.last_saved_label = ("Đã lưu «%s». Nhập tiếp công việc con khác hoặc bấm Đóng." % saved) if saved and not rec.id else False

    def _compute_pick_category(self):
        for rec in self:
            rec.pick_category_id = False

    @api.depends("name", "department_id", "team_id")
    def _compute_category_task_names(self):
        for rec in self:
            key = self._norm_category_name(rec.name).casefold()
            if not key or not rec.department_id:
                rec.category_task_names = False
                continue
            rows = self.sudo().search(
                [("active", "=", True), ("department_id", "=", rec.department_id.id)],
                order="sequence, id",
            ).filtered(lambda g: self._norm_category_name(g.name).casefold() == key
                       and g.id != rec._origin.id)
            names = [(g.task_name or "").strip() for g in rows if (g.task_name or "").strip()]
            rec.category_task_names = "\n".join("• " + n for n in names) or False

    @api.onchange("pick_category_id")
    def _onchange_pick_category(self):
        """Chọn hạng mục có sẵn → điền tên, phòng ban, team, quản lý, thứ tự (để thêm CV con)."""
        cat = self.pick_category_id
        if not cat:
            return
        cat = cat._origin or cat
        self.name = cat.name
        if cat.department_id:
            self.department_id = cat.department_id
        self.team_id = cat.team_id
        siblings = cat.sudo()._category_siblings()
        if not self.category_manager_ids:
            managers = siblings.mapped("category_manager_ids")
            if managers:
                self.category_manager_ids = [(6, 0, managers.ids)]
        if siblings:
            self.sequence = max(siblings.mapped("sequence"))
        self.task_name = False

    @api.onchange("department_id")
    def _onchange_department_id(self):
        """Đổi phòng ban → xóa Team nếu không còn thuộc phòng ban đó."""
        if (
            self.team_id
            and self.department_id
            and self.team_id.department_id != self.department_id
        ):
            self.team_id = False

    _TEAM_USER_FIELDS = (
        "category_manager_ids", "assignee_user_ids", "checker_user_ids", "detail_user_ids",
        "detail_check_user_ids", "total_user_ids", "south_user_ids", "dtt_user_ids",
        "north_user_ids", "vptt_user_ids", "vpmb_user_ids",
    )

    @api.model
    def _team_from_user(self, user=None, department=None):
        """Team của user nếu có trong hệ thống: ưu tiên Team user làm quản lý, rồi Team có user
        trong User Group, sau đó Team xuất hiện nhiều nhất trong các hạng mục user đang tham gia. Không có → trống."""
        user = user or self.env.user
        if department is None:
            department = self.env["daily.task.assign"]._department_from_user(user)
        Team = self.env["daily.task.team"].sudo()
        dom = [("active", "=", True)]
        if department:
            dom.append(("department_id", "=", department.id))
        managed = Team.search(dom + [("manager_ids", "in", user.id)], limit=1)
        if managed:
            return managed
        member = Team.search(dom + [("member_ids", "in", user.id)], limit=1)
        if member:
            return member
        user_dom = ["|"] * (len(self._TEAM_USER_FIELDS) - 1) + [
            (f, "in", user.id) for f in self._TEAM_USER_FIELDS
        ]
        grp_dom = [("team_id", "!=", False), ("team_id.active", "=", True)] + user_dom
        if department:
            grp_dom.append(("team_id.department_id", "=", department.id))
        counts = {}
        for g in self.sudo().search(grp_dom):
            counts[g.team_id] = counts.get(g.team_id, 0) + 1
        if not counts:
            return Team
        return max(counts, key=lambda t: (counts[t], -t.id))

    @api.onchange("category_manager_ids")
    def _onchange_category_manager_team(self):
        """Chưa có Team → lấy Team theo User quản lý hạng mục (nếu có trong hệ thống)."""
        if self.team_id or not self.category_manager_ids:
            return
        for user in self.category_manager_ids:
            team = self._team_from_user(user._origin or user, self.department_id or None)
            if team:
                self.team_id = team
                return

    @api.onchange("team_id")
    def _onchange_team_id(self):
        """Chọn Team trước → tự điền Phòng ban của Team."""
        if self.team_id and self.team_id.department_id and not self.department_id:
            self.department_id = self.team_id.department_id

    @api.model
    def get_groups_for_assign(self):
        """Danh sách hạng mục cho màn Giao việc (kèm user_ids = union 3 loại)."""
        groups = self.sudo().search(
            [("active", "=", True)],
            order="sequence, name, id",
        )
        result = []
        for g in groups:
            result.append(
                {
                    "id": g.id,
                    "name": g.name or "",
                    # Ô chọn phân cấp: hạng mục cha → tên công việc con (giống Quản lý công việc)
                    "category": g.name or "",
                    "task_name": (g.task_name or g.name or "").strip(),
                    "sequence": int(g.sequence or 0),
                    "department_id": g.department_id.id if g.department_id else False,
                    "department": g.department_id.display_name if g.department_id else "",
                    "user_ids": g.applicable_users().ids,
                    "detail_user_ids": g.detail_user_ids.ids,
                    "checker_user_ids": g.checker_user_ids.ids,
                    "detail_check_user_ids": g.detail_check_user_ids.ids,
                    "total_user_ids": g.total_user_ids.ids,
                }
            )
        # Thứ tự + số hạng mục (I, II…) / STT (1.1, 1.2…) giống Bảng hạng mục
        return self._order_like_board(result)

    @api.model
    def get_groups_for_user(self, department_id=None, user_id=None, allow_all_for_manager=False):
        """Danh sách chọn trên Nhập công việc — ưu tiên từ bảng Phân công.

        Hiển thị = Tên công việc (phân công), value = work_group_id.
        - Có dòng phân công gắn user → chỉ các tên CV đó.
        - Không có phân công → fallback hạng mục user được áp dụng (label = task_name).
        """
        uid = int(user_id or self.env.uid)
        dept_id = int(department_id or 0)
        Assign = self.env["daily.task.assign"].sudo()
        assign_domain = [
            ("active", "=", True),
            "|",
            "|",
            "|",
            "|",
            "|",
            ("assignee_user_ids", "in", [uid]),
            ("check_user_ids", "in", [uid]),
            ("south_user_ids", "in", [uid]),
            ("dtt_user_ids", "in", [uid]),
            ("north_user_ids", "in", [uid]),
            ("office_user_ids", "in", [uid]),
        ]
        assigns = Assign.search(assign_domain, order="stt, id")
        result = []
        seen = set()
        for a in assigns:
            # Lấy cả work_group_id chính + các tên CV đã tích trên form (work_group_ids)
            group_set = a.work_group_id
            for g in group_set:
                if not g or not g.active or g.id in seen:
                    continue
                seen.add(g.id)
                task_label = (g.task_name or a.name or g.name or "").strip()
                result.append(
                    {
                        "id": g.id,
                        "name": task_label,
                        "category": g.name or "",
                        "task_name": g.task_name or a.name or "",
                        "sequence": int(g.sequence or a.stt or 0),
                        "department_id": g.department_id.id if g.department_id else False,
                        "department": g.department_id.display_name if g.department_id else "",
                        "assign_id": a.id,
                    }
                )
        owned = self.sudo().search(
            [
                ("active", "=", True),
                "|",
                ("assignee_user_ids", "in", [uid]),
                ("checker_user_ids", "in", [uid]),
            ],
            order="sequence, name, id",
        )
        for g in owned:
            if not g or g.id in seen:
                continue
            if dept_id and g.department_id.id != dept_id:
                continue
            seen.add(g.id)
            task_label = (g.task_name or g.name or "").strip()
            result.append(
                {
                    "id": g.id,
                    "name": task_label,
                    "category": g.name or "",
                    "task_name": g.task_name or "",
                    "sequence": int(g.sequence or 0),
                    "department_id": g.department_id.id if g.department_id else False,
                    "department": g.department_id.display_name if g.department_id else "",
                }
            )
        if result:
            return self._order_like_board(result)

        # Fallback: chưa có phân công → hạng mục theo cấu hình user
        domain = [("active", "=", True)]
        if dept_id:
            domain.append(("department_id", "=", dept_id))
        groups = self.sudo().search(domain, order="sequence, name, id")
        is_manager = False
        if allow_all_for_manager:
            is_manager = self.env["daily.task"]._is_manager()
        for g in groups:
            if not is_manager and not g.is_user_applicable(uid):
                continue
            task_label = (g.task_name or g.name or "").strip()
            result.append(
                {
                    "id": g.id,
                    "name": task_label,
                    "category": g.name or "",
                    "task_name": g.task_name or "",
                    "sequence": int(g.sequence or 0),
                    "department_id": g.department_id.id if g.department_id else False,
                    "department": g.department_id.display_name if g.department_id else "",
                }
            )
        return self._order_like_board(result)

    @api.model
    def _order_like_board(self, items):
        """Sắp xếp + đánh số giống Bảng hạng mục: hạng mục cha (I, II…) → công việc con (1.1, 1.2…)."""
        order = {}
        cat_index = 0
        for dept in self.sudo().get_category_board_data().get("departments") or []:
            for team in dept.get("teams") or []:
                for cat in team.get("categories") or []:
                    cat_index += 1
                    for t_idx, task in enumerate(cat.get("tasks") or [], start=1):
                        order[task["id"]] = {
                            "cat_index": cat_index,
                            "cat_key": cat["id"],
                            "cat_code": cat.get("code") or "",
                            "cat_name": cat.get("name") or "",
                            "task_index": t_idx,
                            "stt": task.get("display_stt") or "",
                        }
        out = []
        for item in items:
            meta = order.get(item["id"])
            if meta:
                item.update({
                    "cat_key": meta["cat_key"],
                    "cat_code": meta["cat_code"],
                    "cat_name": meta["cat_name"],
                    "stt": meta["stt"],
                    "_sort": (meta["cat_index"], meta["task_index"]),
                })
            else:
                name = self._norm_category_name(item.get("category"))
                item.update({
                    "cat_key": "other-%s" % name.casefold(),
                    "cat_code": "",
                    "cat_name": name or "Khác",
                    "stt": "",
                    "_sort": (10**6, int(item.get("sequence") or 0), item.get("name") or ""),
                })
            out.append(item)
        out.sort(key=lambda x: x.pop("_sort"))
        return out

    @api.model
    def get_groups_for_department(self, department_id):
        """Tương thích cũ — lọc theo phòng ban + user đang đăng nhập."""
        return self.get_groups_for_user(department_id=department_id, user_id=self.env.uid)
