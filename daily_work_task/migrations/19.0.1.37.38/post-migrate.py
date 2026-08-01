# -*- coding: utf-8 -*-
"""Tạo model/table daily.work.note nếu chưa có + ACL."""


def migrate(cr, version):
    # ACL (an toàn nếu model đã có)
    cr.execute("SELECT id FROM ir_model WHERE model = 'daily.work.note' LIMIT 1")
    row = cr.fetchone()
    if not row:
        return
    model_id = row[0]
    cr.execute(
        """
        SELECT 1 FROM ir_model_access
         WHERE model_id = %s
         LIMIT 1
        """,
        (model_id,),
    )
    if not cr.fetchone():
        cr.execute(
            """
            INSERT INTO ir_model_access
                (name, model_id, group_id, perm_read, perm_write, perm_create, perm_unlink, active)
            VALUES
                ('daily.work.note all users', %s, NULL, true, true, true, true, true)
            """,
            (model_id,),
        )
