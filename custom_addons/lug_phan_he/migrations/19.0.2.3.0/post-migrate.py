# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Chuyển tiền tệ hợp đồng / hóa đơn sang VNĐ."""
    cr.execute(
        """
        UPDATE phan_he_service s
           SET currency_id = c.id
          FROM res_currency c
         WHERE c.name = 'VND'
           AND (s.currency_id IS NULL OR s.currency_id <> c.id)
        """
    )
    cr.execute(
        """
        UPDATE phan_he_invoice i
           SET currency_id = c.id
          FROM res_currency c
         WHERE c.name = 'VND'
           AND (i.currency_id IS NULL OR i.currency_id <> c.id)
        """
    )
    cr.execute(
        """
        UPDATE phan_he_payment p
           SET currency_id = s.currency_id
          FROM phan_he_service s
         WHERE p.service_id = s.id
           AND s.currency_id IS NOT NULL
           AND (p.currency_id IS NULL OR p.currency_id <> s.currency_id)
        """
    )
