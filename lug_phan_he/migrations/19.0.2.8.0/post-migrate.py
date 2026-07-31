# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đánh lại STT tăng theo id; hiển thị list theo STT desc (lớn → nhỏ)."""
    cr.execute(
        """
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id ASC) AS rn
              FROM phan_he_service
        )
        UPDATE phan_he_service s
           SET stt = o.rn
          FROM ordered o
         WHERE s.id = o.id
        """
    )
