# Part of Odoo. See LICENSE file for full copyright and licensing details.



from odoo import api, fields, models, tools





class HrLeaveAnalyticsEmployeeWatch(models.Model):

    _name = "hr.leave.analytics.employee.watch"

    _inherit = ["hr.leave.analytics.job.title.mixin"]

    _description = "Top nhân viên cần chú ý"

    _auto = False

    _order = "leave_days desc, employee_name"

    _rec_name = "employee_name"



    employee_id = fields.Many2one("hr.employee", string="Nhân viên", readonly=True)

    employee_name = fields.Char(string="Nhân viên", readonly=True)

    store_name = fields.Char(string="Cửa hàng", readonly=True)

    job_title = fields.Char(string="Chức danh (mã)", readonly=True)

    job_title_display = fields.Char(

        string="Chức danh",

        compute="_compute_job_title_display",

        readonly=True,

    )

    employee_mien = fields.Selection(

        selection=[

            ("Bắc", "Miền Bắc"),

            ("Nam", "Miền Nam"),

            ("ĐTT", "Miền ĐTT"),

            ("VP", "VP"),

        ],

        string="Miền",

        readonly=True,

    )

    leave_days = fields.Float(string="Số ngày", readonly=True)

    company_id = fields.Many2one("res.company", readonly=True)



    @api.depends("job_title", "employee_id")

    def _compute_job_title_display(self):

        for row in self:

            row.job_title_display = self._job_title_label(row.job_title, employee=row.employee_id) or "—"



    def init(self):

        tools.drop_view_if_exists(self.env.cr, "hr_leave_analytics_employee_watch")

        self.env.cr.execute(

            """

            CREATE OR REPLACE VIEW hr_leave_analytics_employee_watch AS (

                WITH month_bounds AS (

                    SELECT

                        date_trunc('month', CURRENT_DATE)::date AS month_start,

                        (date_trunc('month', CURRENT_DATE) + interval '1 month' - interval '1 day')::date AS month_end

                )

                SELECT

                    ROW_NUMBER() OVER (

                        ORDER BY SUM(l.number_of_days) DESC, COALESCE(e.name, '')

                    ) AS id,

                    e.id AS employee_id,

                    COALESCE(e.name, '') AS employee_name,

                    COALESCE(NULLIF(TRIM(sc.code), ''), '') AS store_name,

                    COALESCE(v.job_title, '') AS job_title,

                    COALESCE(l.employee_leave_mien, e.mien) AS employee_mien,

                    SUM(l.number_of_days) AS leave_days,

                    l.employee_company_id AS company_id

                FROM hr_leave l

                INNER JOIN hr_employee e ON e.id = l.employee_id

                LEFT JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                LEFT JOIN hr_version v ON v.id = e.current_version_id

                CROSS JOIN month_bounds mb

                WHERE e.active IS TRUE

                  AND l.state = 'validate'

                  AND l.request_date_from >= mb.month_start

                  AND l.request_date_from <= mb.month_end

                GROUP BY

                    e.id,

                    e.name,

                    sc.code,

                    v.job_title,

                    COALESCE(l.employee_leave_mien, e.mien),

                    l.employee_company_id

                HAVING SUM(l.number_of_days) > 0

            )

            """

        )


