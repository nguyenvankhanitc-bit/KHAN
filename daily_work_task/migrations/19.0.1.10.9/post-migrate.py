# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Sửa Người giao = OdooBot khi create_uid là user thật (vd. Nguyễn Văn Khan)."""
    cr.execute(
        """
        UPDATE daily_task
           SET assigned_by_id = create_uid
         WHERE assigned_by_id = 1
           AND create_uid IS NOT NULL
           AND create_uid <> 1
        """
    )
