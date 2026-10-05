# -*- coding: utf-8 -*-
"""Link existing servers to the server-kind catalog."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE phan_he_service AS svc
           SET server_kind_id = kind.id
          FROM phan_he_server_kind AS kind
         WHERE svc.server_kind = kind.code
           AND svc.server_kind_id IS NULL
        """
    )
