# -*- coding: utf-8 -*-

from odoo import fields, models, tools

_REQUIRED_EQUIPMENT_COLS = (
    "eam_state",
    "warehouse_id",
    "current_location_id",
    "eam_model_id",
    "eam_brand_id",
)


class EamAssetStockReport(models.Model):
    """Tồn kho TÀI SẢN — đếm số lượng theo mã riêng (mỗi dòng = 1 asset in_stock)."""

    _name = "eam.asset.stock.report"
    _description = "Tồn kho tài sản (theo mã)"
    _auto = False
    _order = "warehouse_id, category_id, eam_model_id"

    warehouse_id = fields.Many2one("eam.warehouse", string="Kho", readonly=True)
    current_location_id = fields.Many2one("eam.location", string="Vị trí", readonly=True)
    category_id = fields.Many2one(
        "maintenance.equipment.category", string="Nhóm", readonly=True
    )
    eam_model_id = fields.Many2one("eam.model", string="Model", readonly=True)
    eam_brand_id = fields.Many2one("eam.brand", string="Thương hiệu", readonly=True)
    company_id = fields.Many2one("res.company", string="Công ty", readonly=True)
    qty = fields.Integer(string="Số lượng TS", readonly=True)
    asset_value = fields.Float(string="Giá trị", readonly=True)

    def _equipment_cols_ready(self):
        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'maintenance_equipment'
               AND column_name = ANY(%s)
            """,
            [list(_REQUIRED_EQUIPMENT_COLS)],
        )
        found = {row[0] for row in self.env.cr.fetchall()}
        return set(_REQUIRED_EQUIPMENT_COLS).issubset(found)

    def init(self):
        """Tạo view an toàn: lúc upgrade cột eam_* có thể chưa có → stub rỗng, rồi tạo lại sau."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        if not self._equipment_cols_ready():
            self.env.cr.execute(
                """
                CREATE OR REPLACE VIEW %s AS (
                    SELECT
                        0::bigint AS id,
                        NULL::int AS warehouse_id,
                        NULL::int AS current_location_id,
                        NULL::int AS category_id,
                        NULL::int AS eam_model_id,
                        NULL::int AS eam_brand_id,
                        NULL::int AS company_id,
                        0::int AS qty,
                        0::float8 AS asset_value
                    WHERE FALSE
                )
                """
                % self._table
            )
            return
        self._create_real_view()

    def _create_real_view(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    e.warehouse_id AS warehouse_id,
                    e.current_location_id AS current_location_id,
                    e.category_id AS category_id,
                    e.eam_model_id AS eam_model_id,
                    e.eam_brand_id AS eam_brand_id,
                    e.company_id AS company_id,
                    COUNT(e.id)::int AS qty,
                    COALESCE(SUM(e.cost), 0) AS asset_value
                FROM maintenance_equipment e
                WHERE e.active = TRUE
                  AND e.eam_state = 'in_stock'
                  AND e.warehouse_id IS NOT NULL
                GROUP BY
                    e.warehouse_id,
                    e.current_location_id,
                    e.category_id,
                    e.eam_model_id,
                    e.eam_brand_id,
                    e.company_id
            )
            """
            % self._table
        )

    def _register_hook(self):
        super()._register_hook()
        # Sau khi mọi cột inherit đã có, dựng lại view thật.
        if self._equipment_cols_ready():
            self._create_real_view()
