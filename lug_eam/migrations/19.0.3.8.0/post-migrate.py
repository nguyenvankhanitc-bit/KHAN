# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Đổi sequence xuất kho sang PX + padding 4."""
    cr.execute(
        """
        UPDATE ir_sequence
           SET prefix = 'PX',
               padding = 4,
               name = 'Phiếu xuất kho'
         WHERE code = 'eam.txn.out'
        """
    )
