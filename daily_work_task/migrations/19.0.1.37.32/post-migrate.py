# -*- coding: utf-8 -*-
"""Đặt cron nhắc việc sáng vào ~08:00 giờ Việt Nam (UTC+7)."""

import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


def _next_vn_8am_as_utc_naive():
    """Mốc 08:00 Asia/Ho_Chi_Minh kế tiếp → datetime naive UTC (Odoo nextcall)."""
    try:
        from zoneinfo import ZoneInfo

        vn = ZoneInfo("Asia/Ho_Chi_Minh")
        utc = ZoneInfo("UTC")
        now_vn = datetime.now(vn)
        target_vn = now_vn.replace(hour=8, minute=0, second=0, microsecond=0)
        if now_vn >= target_vn:
            target_vn = target_vn + timedelta(days=1)
        return target_vn.astimezone(utc).replace(tzinfo=None)
    except Exception:  # pragma: no cover
        # 08:00 VN = 01:00 UTC
        now = datetime.utcnow()
        today_0100 = now.replace(hour=1, minute=0, second=0, microsecond=0)
        return today_0100 if now < today_0100 else today_0100 + timedelta(days=1)


def migrate(cr, version):
    nextcall = _next_vn_8am_as_utc_naive()
    cr.execute(
        """
        UPDATE ir_cron
           SET active = TRUE,
               nextcall = %s,
               interval_number = 1,
               interval_type = 'days',
               code = 'model.cron_send_morning_reminders()'
         WHERE id IN (
               SELECT res_id
                 FROM ir_model_data
                WHERE module = 'daily_work_task'
                  AND name = 'ir_cron_daily_work_overdue_mail'
                  AND model = 'ir.cron'
         )
        """,
        (nextcall,),
    )
    _logger.info(
        "daily_work_task: cron nhắc việc sáng nextcall=%s (08:00 giờ VN)",
        nextcall,
    )
