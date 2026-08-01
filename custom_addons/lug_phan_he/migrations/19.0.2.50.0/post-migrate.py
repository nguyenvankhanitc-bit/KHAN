# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Gỡ icon app khỏi submenu và tắt lug.app phụ."""
    cr.execute(
        """
        UPDATE ir_ui_menu
           SET web_icon = NULL
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'lug_phan_he'
               AND model = 'ir.ui.menu'
               AND name IN (
                    'menu_phan_he_camera_root',
                    'menu_phan_he_attendance_root',
                    'menu_phan_he_linkq_hrm_root',
                    'menu_phan_he_linkq_nb_root',
                    'menu_phan_he_server_root'
               )
         )
        """
    )
    cr.execute(
        """
        UPDATE lug_app
           SET active = FALSE
         WHERE code IN (
            'phan_he_camera',
            'phan_he_attendance',
            'phan_he_linkq_hrm',
            'phan_he_linkq_nb',
            'phan_he_server'
         )
        """
    )
