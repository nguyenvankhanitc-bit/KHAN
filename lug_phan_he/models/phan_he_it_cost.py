# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class PhanHeItCostCategory(models.Model):
    _name = "phan.he.it.cost.category"
    _description = "Hạng mục chi phí IT"
    _order = "sequence, name"

    name = fields.Char(string="Hạng mục", required=True)
    code = fields.Char(string="Mã", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("unique(code)", "Mã hạng mục phải duy nhất.")


class PhanHeItRenewalCycle(models.Model):
    _name = "phan.he.it.renewal.cycle"
    _description = "Chu kỳ gia hạn"
    _order = "months, name"

    name = fields.Char(string="Tên chu kỳ", required=True)
    code = fields.Char(string="Mã", required=True)
    months = fields.Integer(string="Số tháng", required=True, default=12)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("unique(code)", "Mã chu kỳ phải duy nhất.")


class PhanHeItCost(models.Model):
    _name = "phan.he.it.cost"
    _description = "Khoản chi phí / gia hạn tài sản IT"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end asc, code, id desc"
    _rec_names_search = ["code", "contract_ref"]

    code = fields.Char(
        string="Mã khoản chi phí",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("phan.he.it.cost") or "New",
        tracking=True,
    )
    asset_id = fields.Many2one(
        "phan.he.it.asset",
        string="Tài sản",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    category_id = fields.Many2one(
        "phan.he.it.cost.category",
        string="Hạng mục chi phí",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    provider_id = fields.Many2one("phan.he.provider", string="Nhà cung cấp", tracking=True)
    contract_ref = fields.Char(string="Số hợp đồng / mã tham chiếu", tracking=True)
    bandwidth = fields.Char(
        string="Băng thông",
        tracking=True,
        help="Dùng khi khoản chi phí gắn đường truyền / dịch vụ có băng thông.",
    )
    date_start = fields.Date(string="Ngày bắt đầu", tracking=True)
    date_end = fields.Date(string="Ngày kết thúc", tracking=True, index=True)
    cycle_id = fields.Many2one("phan.he.it.renewal.cycle", string="Chu kỳ gia hạn")
    reminder_date = fields.Date(
        string="Ngày nhắc gia hạn",
        compute="_compute_reminder_date",
        store=True,
    )
    amount_untaxed = fields.Monetary(
        string="Cước tháng",
        currency_field="currency_id",
        tracking=True,
        help="Chi phí trước thuế / cước định kỳ.",
    )
    tax_rate = fields.Float(string="Thuế suất (%)", default=10.0)
    amount_tax = fields.Monetary(
        string="Tiền thuế",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_total = fields.Monetary(
        string="Số tiền thanh toán",
        currency_field="currency_id",
        tracking=True,
        help="Nhập tay — độc lập với cước tháng.",
    )
    amount_untaxed_actual = fields.Monetary(
        string="Chi phí thực tế trước thuế",
        currency_field="currency_id",
        help="Phân biệt với chi phí dự kiến (amount_untaxed).",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Đồng tiền",
        default=lambda self: self.env.ref("base.VND", raise_if_not_found=False)
        or self.env.company.currency_id,
    )
    date_due = fields.Date(string="Ngày thanh toán dự kiến", tracking=True)
    date_paid = fields.Date(string="Ngày thanh toán thực tế", tracking=True)
    responsible_id = fields.Many2one("hr.employee", string="Người phụ trách", tracking=True)
    renewal_state = fields.Selection(
        [
            ("active", "Đang hiệu lực"),
            ("expiring", "Sắp hết hạn"),
            ("quote", "Chờ báo giá"),
            ("approval", "Chờ phê duyệt"),
            ("processing", "Đang xử lý gia hạn"),
            ("renewed", "Đã gia hạn"),
            ("overdue", "Quá hạn"),
            ("cancel", "Đã hủy"),
        ],
        string="Trạng thái gia hạn",
        default="active",
        required=True,
        tracking=True,
    )
    payment_state = fields.Selection(
        [
            ("not_due", "Chưa đến hạn thanh toán"),
            ("confirm", "Chờ xác nhận"),
            ("pending", "Chờ thanh toán"),
            ("paid", "Đã thanh toán"),
            ("overdue", "Quá hạn thanh toán"),
            ("cancel", "Đã hủy"),
        ],
        string="Trạng thái thanh toán",
        default="not_due",
        required=True,
        tracking=True,
    )
    note = fields.Text(string="Ghi chú")
    attachment = fields.Binary(string="Hóa đơn", attachment=True)
    attachment_name = fields.Char(string="Tên tệp hóa đơn")
    period_ids = fields.One2many("phan.he.it.cost.period", "cost_id", string="Lịch sử kỳ gia hạn")
    company_id = fields.Many2one(
        "res.company",
        related="asset_id.company_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)
    remaining_days = fields.Integer(compute="_compute_remaining_days", string="Số ngày còn lại")
    remaining_label = fields.Char(
        compute="_compute_remaining_days",
        string="Thời gian còn lại",
    )
    asset_name = fields.Char(
        related="asset_id.name",
        string="Tên thiết bị",
        store=True,
    )

    @api.depends("amount_untaxed", "tax_rate")
    def _compute_amounts(self):
        for rec in self:
            base = float(rec.amount_untaxed or 0.0)
            rec.amount_tax = base * float(rec.tax_rate or 0.0) / 100.0

    @api.depends("date_end", "cycle_id")
    def _compute_reminder_date(self):
        for rec in self:
            if not rec.date_end:
                rec.reminder_date = False
                continue
            # Mặc định nhắc trước 30 ngày (cấu hình chi tiết ở reminder.config)
            rec.reminder_date = rec.date_end - relativedelta(days=30)

    @api.depends("date_end")
    def _compute_remaining_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_end:
                rec.remaining_days = 0
                rec.remaining_label = "—"
                continue
            days = (rec.date_end - today).days
            rec.remaining_days = days
            if days > 0:
                rec.remaining_label = "Còn %s ngày" % days
            elif days == 0:
                rec.remaining_label = "Hết hạn hôm nay"
            else:
                rec.remaining_label = "Quá hạn %s ngày" % abs(days)

    def _allowed_renewal_transitions(self):
        return {
            "active": {"expiring", "quote", "overdue", "cancel"},
            "expiring": {"quote", "approval", "processing", "overdue", "cancel"},
            "quote": {"approval", "processing", "cancel"},
            "approval": {"processing", "quote", "cancel"},
            "processing": {"renewed", "cancel"},
            "renewed": {"active", "expiring"},
            "overdue": {"quote", "approval", "processing", "cancel"},
            "cancel": set(),
        }

    def action_set_renewal_state(self, new_state):
        allowed = self._allowed_renewal_transitions()
        for rec in self:
            if new_state not in allowed.get(rec.renewal_state, set()):
                raise UserError(
                    "Không thể chuyển trạng thái gia hạn từ «%s» sang «%s»."
                    % (rec.renewal_state, new_state)
                )
            rec.renewal_state = new_state
        return True

    def action_mark_expiring(self):
        return self.action_set_renewal_state("expiring")

    def action_request_quote(self):
        return self.action_set_renewal_state("quote")

    def action_submit_approval(self):
        return self.action_set_renewal_state("approval")

    def action_start_processing(self):
        return self.action_set_renewal_state("processing")

    def action_mark_payment_confirm(self):
        for rec in self:
            if rec.payment_state in ("cancel", "paid"):
                raise UserError("Không thể chuyển trạng thái thanh toán từ «%s»." % rec.payment_state)
            rec.payment_state = "confirm"
        return True

    def action_mark_paid(self):
        for rec in self:
            if rec.payment_state not in ("confirm", "pending", "overdue"):
                raise UserError("Chỉ xác nhận đã thanh toán khi đang chờ xác nhận/thanh toán.")
            rec.payment_state = "paid"
            if not rec.date_paid:
                rec.date_paid = fields.Date.context_today(self)
        return True

    def action_confirm_renewal(self, date_start=None, date_end=None, amount_untaxed=None, note=None):
        """Gia hạn: lưu kỳ cũ vào period, cập nhật hạn mới — không ghi đè lịch sử."""
        self.ensure_one()
        if self.renewal_state not in ("processing", "approval", "quote", "expiring", "overdue"):
            raise UserError("Chỉ xác nhận gia hạn khi khoản đang trong quy trình xử lý.")
        Period = self.env["phan.he.it.cost.period"]
        Period.create({
            "cost_id": self.id,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "amount_untaxed": self.amount_untaxed,
            "amount_tax": self.amount_tax,
            "amount_total": self.amount_total,
            "payment_state": self.payment_state,
            "date_paid": self.date_paid,
            "note": note or "Kỳ trước khi gia hạn",
        })
        vals = {
            "renewal_state": "renewed",
            "payment_state": "not_due",
            "date_paid": False,
        }
        if date_start:
            vals["date_start"] = date_start
        if date_end:
            vals["date_end"] = date_end
        elif self.cycle_id and self.date_end:
            vals["date_end"] = self.date_end + relativedelta(months=self.cycle_id.months or 12)
            vals["date_start"] = self.date_end + relativedelta(days=1)
        if amount_untaxed is not None:
            vals["amount_untaxed"] = amount_untaxed
        self.write(vals)
        self.renewal_state = "active"
        return True


class PhanHeItCostPeriod(models.Model):
    _name = "phan.he.it.cost.period"
    _description = "Lịch sử kỳ gia hạn chi phí IT"
    _order = "date_end desc, id desc"

    cost_id = fields.Many2one(
        "phan.he.it.cost",
        string="Khoản chi phí",
        required=True,
        ondelete="cascade",
        index=True,
    )
    asset_id = fields.Many2one(related="cost_id.asset_id", store=True, string="Tài sản")
    date_start = fields.Date(string="Từ ngày")
    date_end = fields.Date(string="Đến ngày")
    amount_untaxed = fields.Monetary(string="Trước thuế", currency_field="currency_id")
    amount_tax = fields.Monetary(string="Thuế", currency_field="currency_id")
    amount_total = fields.Monetary(string="Tổng", currency_field="currency_id")
    currency_id = fields.Many2one(related="cost_id.currency_id", store=True)
    payment_state = fields.Char(string="TT thanh toán (kỳ)")
    date_paid = fields.Date(string="Ngày thanh toán")
    note = fields.Char(string="Ghi chú")
