# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class PhanHeItReminderConfig(models.Model):
    _name = "phan.he.it.reminder.config"
    _description = "Cấu hình nhắc hạn gia hạn IT"
    _order = "days_before"

    name = fields.Char(string="Tên mốc", required=True)
    days_before = fields.Integer(
        string="Số ngày trước hạn",
        required=True,
        help="0 = đúng ngày hết hạn; 30 = trước 30 ngày.",
    )
    active = fields.Boolean(default=True)
    notify_responsible = fields.Boolean(string="Nhắc người phụ trách", default=True)
    create_activity = fields.Boolean(string="Tạo hoạt động Odoo", default=True)

    _days_uniq = models.Constraint(
        "unique(days_before)",
        "Mỗi mốc số ngày chỉ cấu hình một lần.",
    )

    @api.model
    def cron_it_reminder(self):
        """Tạo activity cho khoản sắp hết hạn theo mốc — không trùng cùng ngày+cost+mốc."""
        today = fields.Date.context_today(self)
        configs = self.search([("active", "=", True)])
        Cost = self.env["phan.he.it.cost"].sudo()
        Activity = self.env["mail.activity"].sudo()
        act_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not act_type:
            return True
        for cfg in configs:
            target = today + relativedelta(days=int(cfg.days_before or 0))
            costs = Cost.search([
                ("active", "=", True),
                ("date_end", "=", target),
                ("renewal_state", "in", ("active", "expiring", "overdue")),
            ])
            for cost in costs:
                summary = "Nhắc gia hạn %s — còn %s ngày" % (
                    cost.asset_id.code or cost.code,
                    cfg.days_before,
                )
                domain = [
                    ("res_model", "=", "phan.he.it.cost"),
                    ("res_id", "=", cost.id),
                    ("summary", "=", summary),
                    ("date_deadline", "=", today),
                ]
                if Activity.search_count(domain):
                    continue
                user = self.env.user
                if cost.responsible_id and cost.responsible_id.user_id:
                    user = cost.responsible_id.user_id
                if cfg.create_activity:
                    Activity.create({
                        "activity_type_id": act_type.id,
                        "res_model_id": self.env["ir.model"]._get("phan.he.it.cost").id,
                        "res_id": cost.id,
                        "user_id": user.id,
                        "summary": summary,
                        "date_deadline": today,
                        "note": "Khoản %s hết hạn %s" % (cost.code, cost.date_end),
                    })
                if cost.renewal_state == "active" and cfg.days_before > 0:
                    cost.renewal_state = "expiring"
                elif cost.renewal_state in ("active", "expiring") and cfg.days_before == 0:
                    cost.renewal_state = "overdue"
        return True
