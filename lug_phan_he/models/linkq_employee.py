# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression


class LinkqEmployee(models.Model):
    _name = "linkq.employee"
    _description = "Nhân sự LinkQ ERP"
    _order = "stt, id"
    _inherit = ["mail.thread", "mail.activity.mixin", "lug.menu.access.mixin"]
    _linkq_menu_key = "hr_list"

    @api.model
    def _default_stt(self):
        last = self.search([], order="stt desc", limit=1)
        return (last.stt or 0) + 1 if last else 1

    stt = fields.Integer(string="STT", default=_default_stt)
    name = fields.Char(string="HỌ VÀ TÊN", required=True, tracking=True)
    job_position = fields.Selection(
        [
            ("cht", "CHT"),
            ("nt", "NT"),
            ("nvbh", "NVBH"),
            ("partime", "Partime"),
            ("asm", "ASM"),
        ],
        string="Chức vụ",
        required=True,
        default="nvbh",
        tracking=True,
    )
    employee_id_num = fields.Char(string="Mã ID", required=True)
    cccd = fields.Char(string="Số CCCD", size=12)
    phone = fields.Char(string="SĐT")
    joining_date = fields.Date(string="Ngày vào làm", default=fields.Date.today)
    state = fields.Selection(
        [
            ("working", "Đang công tác"),
            ("transferred", "Điều chuyển"),
            ("support", "Hỗ trợ"),
            ("resigned", "Nghỉ việc"),
        ],
        string="Trạng thái",
        default="working",
        required=True,
        tracking=True,
        index=True,
    )
    note = fields.Text(string="Ghi chú")
    store_id = fields.Many2one(
        "hr.store",
        string="Cửa hàng",
        index=True,
        ondelete="restrict",
        default=lambda self: self._default_store_id(),
    )
    store_group_label = fields.Char(
        string="Cửa hàng",
        compute="_compute_store_group_label",
        store=True,
        index=True,
    )
    stt_display = fields.Char(string="STT", compute="_compute_stt_display")

    @api.depends("stt")
    def _compute_stt_display(self):
        for rec in self:
            rec.stt_display = f"{int(rec.stt or 0):02d}"

    @api.depends(
        "store_id",
        "store_id.code",
        "store_id.name",
        "store_id.manager_id",
        "store_id.manager_id.name",
    )
    def _compute_store_group_label(self):
        for rec in self:
            rec.store_group_label = (
                rec.store_id._linkq_employee_group_label()
                if rec.store_id
                else "Chưa gán cửa hàng"
            )

    @api.model
    def _default_store_id(self):
        allowed = self.env.user._linkq_allowed_hr_store_ids()
        if allowed:
            return allowed[0]
        return False

    @api.model
    def _linkq_store_scope_domain(self):
        if self.env.su or self._linkq_bypass():
            return []
        store_ids = self.env.user._linkq_allowed_hr_store_ids()
        if not store_ids:
            return [("id", "=", False)]
        return [("store_id", "in", store_ids)]

    def _linkq_store_forbidden(self):
        domain = self._linkq_store_scope_domain()
        if not domain:
            return self.browse()
        allowed = set(self.env.user._linkq_allowed_hr_store_ids())
        return self.filtered(lambda rec: rec.store_id.id and rec.store_id.id not in allowed)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result is not None:
            return result
        if self.env.su or self._linkq_bypass() or not self:
            return None
        forbidden = self._linkq_store_forbidden()
        if forbidden:
            return forbidden, lambda: AccessError(
                "Bạn chỉ được xem nhân sự của cửa hàng mình phụ trách."
            )
        return None

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        extra = self._linkq_store_scope_domain()
        if extra and not kwargs.get("bypass_access"):
            domain = expression.AND([extra, domain or []])
        return super()._search(
            domain, offset=offset, limit=limit, order=order, **kwargs
        )

    def init(self):
        self.env.cr.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'linkq_employee'
                      AND column_name = 'employee_id_num'
                      AND data_type IN ('integer', 'bigint', 'numeric')
                ) THEN
                    ALTER TABLE linkq_employee
                    ALTER COLUMN employee_id_num TYPE varchar
                    USING TRIM(BOTH FROM employee_id_num::text);
                END IF;
            END $$;
            """
        )
        self.env.cr.execute("SELECT to_regclass('linkq_employee')")
        if self.env.cr.fetchone()[0]:
            self.env.cr.execute(
                """
                SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'linkq_employee' AND column_name = 'store_id'
                """
            )
            if self.env.cr.fetchone():
                self.env.cr.execute(
                    """
                    UPDATE linkq_employee e
                       SET store_id = sub.store_id
                    FROM (
                        SELECT DISTINCT ON (UPPER(TRIM(l.employee_name)))
                               UPPER(TRIM(l.employee_name)) AS nm,
                               r.store_id
                          FROM linkq_monthly_roster_line l
                          JOIN linkq_monthly_roster r ON r.id = l.roster_id
                         WHERE r.store_id IS NOT NULL
                           AND COALESCE(TRIM(l.employee_name), '') <> ''
                         ORDER BY UPPER(TRIM(l.employee_name)), r.id DESC
                    ) sub
                    WHERE e.store_id IS NULL
                      AND UPPER(TRIM(e.name)) = sub.nm
                    """
                )

    def _linkq_keys_for_model(self):
        return ["hr_list", "hr_add", "hr_group"]

    def _linkq_key_from_vals(self, vals):
        return False

    def _linkq_key_for_record(self, rec):
        return "hr_list"

    @staticmethod
    def _to_upper_name(value):
        if not value:
            return value
        return value.strip().upper()

    @api.onchange("name")
    def _onchange_name_uppercase(self):
        if self.name:
            self.name = self._to_upper_name(self.name)

    @api.model_create_multi
    def create(self, vals_list):
        next_stt = None
        allowed = self.env.user._linkq_allowed_hr_store_ids()
        scoped = bool(allowed and not self.env.su and not self._linkq_bypass())
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = self._to_upper_name(vals["name"])
            if scoped:
                store_id = vals.get("store_id")
                if store_id and store_id not in allowed:
                    raise AccessError("Bạn chỉ được thêm nhân sự cho cửa hàng mình phụ trách.")
                if not store_id:
                    vals["store_id"] = allowed[0]
            if not vals.get("stt"):
                if next_stt is None:
                    next_stt = self._default_stt()
                vals["stt"] = next_stt
                next_stt += 1
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = self._to_upper_name(vals["name"])
        allowed = self.env.user._linkq_allowed_hr_store_ids()
        if (
            allowed
            and not self.env.su
            and not self._linkq_bypass()
            and vals.get("store_id")
            and vals["store_id"] not in allowed
        ):
            raise AccessError("Bạn chỉ được sửa nhân sự của cửa hàng mình phụ trách.")
        return super().write(vals)

    @api.constrains("cccd")
    def _check_cccd_digits(self):
        for rec in self:
            value = (rec.cccd or "").strip()
            if value and (not value.isdigit() or len(value) > 12):
                raise ValidationError("Số CCCD chỉ được chứa chữ số và tối đa 12 ký tự.")

    def action_save_and_close(self):
        return {"type": "ir.actions.act_window_close"}

    def action_create_new_from_popup(self):
        view = self.env.ref("lug_phan_he.view_linkq_employee_popup_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Thêm mới nhân sự",
            "res_model": "linkq.employee",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {
                "form_view_initial_mode": "edit",
                "default_stt": self._default_stt(),
            },
        }

    def action_open_employee_edit(self):
        self.ensure_one()
        view = self.env.ref("lug_phan_he.view_linkq_employee_popup_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Thông tin nhân sự - %s" % (self.name or ""),
            "res_model": "linkq.employee",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {"form_view_initial_mode": "edit"},
        }

    def action_hard_delete_permanent(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("Chỉ Administrator mới được xóa vĩnh viễn nhân sự!")
        self.sudo().unlink()
        return True
