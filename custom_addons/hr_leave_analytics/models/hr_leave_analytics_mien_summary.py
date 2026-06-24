# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class HrLeaveAnalyticsMienSummary(models.Model):
    _name = "hr.leave.analytics.mien.summary"
    _description = "Tổng hợp nghỉ phép theo miền"
    _auto = False
    _order = "leave_days desc"
    _rec_name = "employee_mien"

    employee_mien = fields.Selection(
        selection=[
            ("Nam", "Miền Nam"),
            ("Bắc", "Miền Bắc"),
            ("ĐTT", "Miền ĐTT"),
            ("VP", "VP"),
        ],
        string="Miền",
        readonly=True,
    )
    employee_count = fields.Integer(string="Tổng NV", readonly=True)
    leave_days = fields.Float(string="Ngày nghỉ", readonly=True)
    leave_rate = fields.Float(string="Tỷ lệ nghỉ phép (%)", readonly=True, digits=(16, 2))
    company_id = fields.Many2one("res.company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, "hr_leave_analytics_mien_summary")
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW hr_leave_analytics_mien_summary AS (
                WITH month_bounds AS (
                    SELECT
                        date_trunc('month', CURRENT_DATE)::date AS month_start,
                        (date_trunc('month', CURRENT_DATE) + interval '1 month' - interval '1 day')::date AS month_end
                ),
                business_days AS (
                    SELECT COUNT(*)::integer AS days
                    FROM generate_series(
                        (SELECT month_start FROM month_bounds),
                        (SELECT month_end FROM month_bounds),
                        interval '1 day'
                    ) AS day
                    WHERE EXTRACT(ISODOW FROM day) < 6
                ),
                regions AS (
                    SELECT unnest(ARRAY['VP', 'Nam', 'ĐTT', 'Bắc']::varchar[]) AS employee_mien
                ),
                region_companies AS (
                    SELECT r.employee_mien, c.id AS company_id
                    FROM regions r
                    CROSS JOIN res_company c
                ),
                employees AS (
                    SELECT
                        e.mien AS employee_mien,
                        e.company_id AS company_id,
                        COUNT(*) AS employee_count
                    FROM hr_employee e
                    WHERE e.active IS TRUE
                      AND e.mien IN ('Nam', 'Bắc', 'ĐTT', 'VP')
                    GROUP BY e.mien, e.company_id
                ),
                leaves AS (
                    SELECT
                        COALESCE(l.employee_leave_mien, e.mien) AS employee_mien,
                        l.employee_company_id AS company_id,
                        SUM(l.number_of_days) AS leave_days
                    FROM hr_leave l
                    INNER JOIN hr_employee e ON e.id = l.employee_id
                    CROSS JOIN month_bounds mb
                    WHERE e.active IS TRUE
                      AND l.state = 'validate'
                      AND l.request_date_from >= mb.month_start
                      AND l.request_date_from <= mb.month_end
                      AND COALESCE(l.employee_leave_mien, e.mien) IN ('Nam', 'Bắc', 'ĐTT', 'VP')
                    GROUP BY COALESCE(l.employee_leave_mien, e.mien), l.employee_company_id
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY
                            CASE rc.employee_mien
                                WHEN 'VP' THEN 1
                                WHEN 'Nam' THEN 2
                                WHEN 'ĐTT' THEN 3
                                WHEN 'Bắc' THEN 4
                                ELSE 5
                            END,
                            rc.company_id
                    ) AS id,
                    rc.employee_mien AS employee_mien,
                    COALESCE(emp.employee_count, 0) AS employee_count,
                    COALESCE(lv.leave_days, 0) AS leave_days,
                    CASE
                        WHEN COALESCE(emp.employee_count, 0) > 0 AND bd.days > 0 THEN
                            ROUND(
                                ((COALESCE(lv.leave_days, 0) / (emp.employee_count * bd.days)) * 100)::numeric,
                                2
                            )
                        ELSE 0
                    END AS leave_rate,
                    rc.company_id AS company_id
                FROM region_companies rc
                LEFT JOIN employees emp
                    ON emp.employee_mien = rc.employee_mien
                   AND emp.company_id = rc.company_id
                LEFT JOIN leaves lv
                    ON lv.employee_mien = rc.employee_mien
                   AND lv.company_id = rc.company_id
                CROSS JOIN business_days bd
            )
            """
        )
