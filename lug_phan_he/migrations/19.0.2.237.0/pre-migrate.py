# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS phan_he_access_user_backup")
    cr.execute(
        """
        CREATE TABLE phan_he_access_user_backup AS
        SELECT access_id, user_id FROM phan_he_module_access_users_rel
        """
    )
