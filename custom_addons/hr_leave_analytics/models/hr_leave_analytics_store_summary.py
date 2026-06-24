# Part of Odoo. See LICENSE file for full copyright and licensing details.



from odoo import api, fields, models, tools





class HrLeaveAnalyticsStoreSummary(models.Model):

    _name = "hr.leave.analytics.store.summary"

    _inherit = ["hr.leave.analytics.job.title.mixin"]

    _description = "Tổng hợp nghỉ phép theo cửa hàng"

    _auto = False

    _order = "leave_days desc, store_name"

    _rec_name = "store_name"



    store_id = fields.Many2one("hr.store", string="Cửa hàng (ref)", readonly=True)

    store_name = fields.Char(string="Cửa hàng", readonly=True)

    top_job_title = fields.Char(string="Chức danh nghỉ nhiều nhất (mã)", readonly=True)

    top_job_title_display = fields.Char(

        string="Chức danh",

        compute="_compute_top_job_title_display",

        readonly=True,

    )

    on_leave_job_titles = fields.Char(string="Chức danh đang nghỉ (mã)", readonly=True)

    on_leave_job_titles_display = fields.Char(

        string="Chức danh đang nghỉ",

        compute="_compute_on_leave_job_titles_display",

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

    employee_count = fields.Integer(string="Tổng NV", readonly=True)

    leave_days = fields.Float(string="Ngày nghỉ", readonly=True)

    on_leave_today = fields.Integer(string="Đang nghỉ", readonly=True)

    on_leave_rate = fields.Float(string="Tỷ lệ (%)", readonly=True, digits=(16, 2))

    company_id = fields.Many2one("res.company", readonly=True)



    @api.depends("top_job_title")

    def _compute_top_job_title_display(self):

        for row in self:

            row.top_job_title_display = self._job_title_label(row.top_job_title)



    @api.depends("on_leave_job_titles")

    def _compute_on_leave_job_titles_display(self):

        for row in self:

            row.on_leave_job_titles_display = self._job_titles_label(row.on_leave_job_titles)



    def init(self):

        tools.drop_view_if_exists(self.env.cr, "hr_leave_analytics_store_summary")

        self.env.cr.execute(

            """

            CREATE OR REPLACE VIEW hr_leave_analytics_store_summary AS (

                WITH month_bounds AS (

                    SELECT

                        date_trunc('month', CURRENT_DATE)::date AS month_start,

                        (date_trunc('month', CURRENT_DATE) + interval '1 month' - interval '1 day')::date AS month_end,

                        CURRENT_DATE AS today

                ),

                store_employees AS (

                    SELECT

                        sc.store_id AS store_id,

                        COALESCE(NULLIF(TRIM(sc.code), ''), 'CH-' || sc.store_id::text) AS store_name,

                        COALESCE(sc.mien, e.mien) AS employee_mien,

                        e.company_id AS company_id,

                        COUNT(DISTINCT e.id) AS employee_count

                    FROM hr_employee e

                    INNER JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                    WHERE e.active IS TRUE

                      AND sc.store_id IS NOT NULL

                    GROUP BY sc.store_id, sc.code, sc.mien, e.mien, e.company_id

                ),

                store_leaves AS (

                    SELECT

                        sc.store_id AS store_id,

                        e.company_id AS company_id,

                        SUM(l.number_of_days) AS leave_days

                    FROM hr_leave l

                    INNER JOIN hr_employee e ON e.id = l.employee_id

                    INNER JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                    CROSS JOIN month_bounds mb

                    WHERE e.active IS TRUE

                      AND l.state = 'validate'

                      AND sc.store_id IS NOT NULL

                      AND l.request_date_from >= mb.month_start

                      AND l.request_date_from <= mb.month_end

                    GROUP BY sc.store_id, e.company_id

                ),

                top_leave_employee AS (

                    SELECT store_id, company_id, job_title

                    FROM (

                        SELECT

                            sc.store_id AS store_id,

                            e.company_id AS company_id,

                            COALESCE(v.job_title, '') AS job_title,

                            ROW_NUMBER() OVER (

                                PARTITION BY sc.store_id, e.company_id

                                ORDER BY SUM(l.number_of_days) DESC, e.id

                            ) AS rn

                        FROM hr_leave l

                        INNER JOIN hr_employee e ON e.id = l.employee_id

                        INNER JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                        LEFT JOIN hr_version v ON v.id = e.current_version_id

                        CROSS JOIN month_bounds mb

                        WHERE e.active IS TRUE

                          AND l.state = 'validate'

                          AND sc.store_id IS NOT NULL

                          AND l.request_date_from >= mb.month_start

                          AND l.request_date_from <= mb.month_end

                        GROUP BY sc.store_id, e.company_id, v.job_title, e.id

                    ) ranked

                    WHERE rn = 1

                ),

                store_on_leave AS (

                    SELECT

                        sc.store_id AS store_id,

                        e.company_id AS company_id,

                        COUNT(DISTINCT l.employee_id) AS on_leave_today

                    FROM hr_leave l

                    INNER JOIN hr_employee e ON e.id = l.employee_id

                    INNER JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                    CROSS JOIN month_bounds mb

                    WHERE e.active IS TRUE

                      AND l.state = 'validate'

                      AND sc.store_id IS NOT NULL

                      AND l.request_date_from <= mb.today

                      AND l.request_date_to >= mb.today

                    GROUP BY sc.store_id, e.company_id

                ),

                on_leave_titles AS (

                    SELECT

                        sc.store_id AS store_id,

                        e.company_id AS company_id,

                        STRING_AGG(

                            DISTINCT COALESCE(v.job_title, ''),

                            ',' ORDER BY COALESCE(v.job_title, '')

                        ) AS on_leave_job_titles

                    FROM hr_leave l

                    INNER JOIN hr_employee e ON e.id = l.employee_id

                    INNER JOIN hr_store_code sc ON sc.id = e.ma_bo_phan_id

                    LEFT JOIN hr_version v ON v.id = e.current_version_id

                    CROSS JOIN month_bounds mb

                    WHERE e.active IS TRUE

                      AND l.state = 'validate'

                      AND sc.store_id IS NOT NULL

                      AND l.request_date_from <= mb.today

                      AND l.request_date_to >= mb.today

                    GROUP BY sc.store_id, e.company_id

                )

                SELECT

                    ROW_NUMBER() OVER (

                        ORDER BY COALESCE(sl.leave_days, 0) DESC, se.store_name

                    ) AS id,

                    se.store_id AS store_id,

                    se.store_name AS store_name,

                    COALESCE(tle.job_title, '') AS top_job_title,

                    COALESCE(olt.on_leave_job_titles, '') AS on_leave_job_titles,

                    se.employee_mien AS employee_mien,

                    se.employee_count AS employee_count,

                    COALESCE(sl.leave_days, 0) AS leave_days,

                    COALESCE(sol.on_leave_today, 0) AS on_leave_today,

                    CASE

                        WHEN se.employee_count > 0 THEN

                            ROUND(((COALESCE(sol.on_leave_today, 0)::numeric / se.employee_count) * 100)::numeric, 2)

                        ELSE 0

                    END AS on_leave_rate,

                    se.company_id AS company_id

                FROM store_employees se

                LEFT JOIN store_leaves sl

                    ON sl.store_id = se.store_id

                   AND sl.company_id = se.company_id

                LEFT JOIN top_leave_employee tle

                    ON tle.store_id = se.store_id

                   AND tle.company_id = se.company_id

                LEFT JOIN store_on_leave sol

                    ON sol.store_id = se.store_id

                   AND sol.company_id = se.company_id

                LEFT JOIN on_leave_titles olt

                    ON olt.store_id = se.store_id

                   AND olt.company_id = se.company_id

            )

            """

        )


