# -*- coding: utf-8 -*-
"""Reset bảng phân quyền cũ + xóa client action OWL trước khi chuyển form kiểu lug.group."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'phan_he_module_access'
        """
    )
    if cr.fetchone():
        cr.execute("DELETE FROM phan_he_module_access_line")
        cr.execute("DELETE FROM phan_he_module_access")
        cr.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'phan_he_module_access_users_rel'
            """
        )
        if cr.fetchone():
            cr.execute("DELETE FROM phan_he_module_access_users_rel")

    # Xóa ir.actions.client cũ (xmlid action_phan_he_access_matrix)
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = 'lug_phan_he' AND name = 'action_phan_he_access_matrix'
          AND model = 'ir.actions.client'
        """
    )
    row = cr.fetchone()
    if row:
        cr.execute("DELETE FROM ir_act_client WHERE id = %s", (row[0],))
        cr.execute(
            """
            DELETE FROM ir_model_data
            WHERE module = 'lug_phan_he' AND name = 'action_phan_he_access_matrix'
            """
        )
