# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đồng bộ ops_status từ state (chỉ 3 giá trị vận hành)."""
    cr.execute(
        """
        UPDATE phan_he_service
           SET ops_status = CASE
                WHEN state = 'suspend' THEN 'suspend'
                WHEN state IN ('liquidated', 'expired', 'cancel') THEN 'liquidated'
                ELSE 'active'
           END
         WHERE ops_status IS NULL
            OR ops_status NOT IN ('active', 'suspend', 'liquidated')
        """
    )
