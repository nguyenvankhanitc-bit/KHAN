# -*- coding: utf-8 -*-
"""Đặt cron sinh việc lặp vào ~05:00 giờ Việt Nam (UTC+7)."""

import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


def _next_vn_5am_as_utc_naive():
    """Mốc 05:00 Asia/Ho_Chi_Minh kế tiếp, trả về datetime naive UTC (Odoo nextcall)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        # Fallback: giả định server UTC
        now = datetime.utcnow()
        today_2200 = now.replace(hour=22, minute=0, second=0, microsecond=0)
        return today_2200 if now < today_2200 else today_2200 + timedelta(days=1)

    vn = ZoneInfo("Asia/Ho_Chi_Minh")
    utc = ZoneInfo("UTC")
    now_vn = datetime.now(vn)
    target_vn = now_vn.replace(hour=5, minute=0, second=0, microsecond=0)
    if now_vn >= target_vn:
        target_vn = target_vn + timedelta(days=1)
    return target_vn.astimezone(utc).replace(tzinfo=None)


def migrate(cr, version):
    nextcall = _next_vn_5am_as_utc_naive()
    cr.execute(
        """
        UPDATE ir_cron
           SET active = TRUE,
               nextcall = %s,
               interval_number = 1,
               interval_type = 'days'
         WHERE id IN (
               SELECT res_id
                 FROM ir_model_data
                WHERE module = 'daily_work_task'
                  AND name = 'ir_cron_daily_work_generate_recurring'
                  AND model = 'ir.cron'
         )
        """,
        (nextcall,),
    )
    _logger.info(
        "daily_work_task: cron sinh việc lặp nextcall=%s (05:00 giờ VN)",
        nextcall,
    )
