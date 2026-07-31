# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Trạng thái vận hành: expired cũ → active (quá hạn chỉ theo ngày kết thúc)."""
    cr.execute(
        """
        UPDATE phan_he_service
           SET state = 'active'
         WHERE state = 'expired'
        """
    )
