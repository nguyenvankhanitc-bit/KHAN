# -*- coding: utf-8 -*-
"""Đảm bảo ACL daily.work.note tồn tại (tránh lỗi AccessError trên lab)."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT id FROM ir_model WHERE model = 'daily.work.note' LIMIT 1
        """
    )
    row = cr.fetchone()
    if not row:
        return
    model_id = row[0]
    cr.execute(
        """
        SELECT id FROM ir_model_access
         WHERE name = 'daily.work.note all users'
            OR name = 'access_daily_work_note_all'
         LIMIT 1
        """
    )
    if cr.fetchone():
        return
    cr.execute(
        """
        INSERT INTO ir_model_access
            (name, model_id, group_id, perm_read, perm_write, perm_create, perm_unlink, active)
        VALUES
            ('daily.work.note all users', %s, NULL, true, true, true, true, true)
        """,
        (model_id,),
    )
