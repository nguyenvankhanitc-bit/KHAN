# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Phiếu EAM dùng VNĐ; đồng bộ ký hiệu tiền tệ."""
    cr.execute(
        """
        UPDATE res_currency
           SET symbol = 'VNĐ',
               position = 'after',
               active = true
         WHERE name = 'VND'
        """
    )
    cr.execute("SELECT id FROM res_currency WHERE name = 'VND' LIMIT 1")
    row = cr.fetchone()
    if not row:
        return
    vnd_id = row[0]
    cr.execute(
        """
        UPDATE eam_transaction
           SET currency_id = %s
         WHERE currency_id IS DISTINCT FROM %s
        """,
        (vnd_id, vnd_id),
    )
