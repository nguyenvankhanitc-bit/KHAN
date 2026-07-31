# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

# Mã ngắn mặc định theo mã nhóm gốc.
_GROUP_TOKENS = {
    "GRP_HVAC": "HVAC",
    "GRP_IT": "IT",
    "GRP_ELEC": "ELEC",
    "GRP_WATER": "WATER",
    "GRP_CIVIL": "CIVIL",
    "GRP_OTHER": "OTHER",
}


def _ensure_asset_sequence(env):
    seq = env["ir.sequence"].sudo().search([("code", "=", "eam.asset")], limit=1)
    if seq and seq.prefix:
        seq.write({"prefix": False, "padding": 5})


def _ensure_category_tokens(env):
    Category = env["maintenance.equipment.category"].sudo()
    for code, token in _GROUP_TOKENS.items():
        cats = Category.search([("code", "=", code), ("code_token", "in", [False, ""])])
        if cats:
            cats.write({"code_token": token})


def post_init_hook(env):
    """Gán mã AS / barcode / QR cho equipment đã tồn tại (nếu thiếu)."""
    _ensure_asset_sequence(env)
    _ensure_category_tokens(env)

    # Đảm bảo SQL view tồn kho dùng cột eam_* vừa tạo.
    Report = env["eam.asset.stock.report"].sudo()
    if hasattr(Report, "_create_real_view") and Report._equipment_cols_ready():
        Report._create_real_view()

    Equipment = env["maintenance.equipment"].sudo()
    missing = Equipment.search([("asset_code", "=", False)])
    if not missing:
        return
    _logger.info("lug_eam: backfill asset_code for %s existing equipment", len(missing))
    for equipment in missing:
        vals = equipment._eam_prepare_identity_vals({})
        equipment.write(vals)
