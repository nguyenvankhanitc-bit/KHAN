# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đảm bảo cột sắp xếp danh sách Internet tồn tại trên DB."""
    cr.execute(
        """
        ALTER TABLE phan_he_service
            ADD COLUMN IF NOT EXISTS store_mien_rank integer,
            ADD COLUMN IF NOT EXISTS store_name_sort varchar
        """
    )
    cr.execute(
        """
        UPDATE phan_he_service AS s
           SET store_name_sort = st.name
          FROM phan_he_store AS st
         WHERE s.store_id = st.id
           AND (s.store_name_sort IS DISTINCT FROM st.name)
        """
    )
    cr.execute(
        """
        UPDATE phan_he_service
           SET store_mien_rank = CASE store_mien
                WHEN 'Nam' THEN 1
                WHEN 'ĐTT' THEN 2
                WHEN 'Bắc' THEN 3
                WHEN 'VP' THEN 4
                ELSE 99
           END
         WHERE store_mien_rank IS NULL
            OR store_mien_rank <> CASE store_mien
                WHEN 'Nam' THEN 1
                WHEN 'ĐTT' THEN 2
                WHEN 'Bắc' THEN 3
                WHEN 'VP' THEN 4
                ELSE 99
           END
        """
    )
