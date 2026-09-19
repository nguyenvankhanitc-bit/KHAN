# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Gom ma trận menu Internet: bỏ Cảnh báo / Theo dõi → 4 mục thanh toán."""
    cr.execute(
        """
        UPDATE security_internet_menu_permission
           SET menu_code = 'payment_confirm'
         WHERE menu_code IN ('payment_tracking', 'payment_track')
           AND NOT EXISTS (
                SELECT 1 FROM security_internet_menu_permission t
                 WHERE t.role_id = security_internet_menu_permission.role_id
                   AND t.menu_code = 'payment_confirm'
           )
        """
    )
    cr.execute(
        """
        UPDATE security_internet_menu_permission AS src
           SET can_read = GREATEST(src.can_read::int, old.can_read::int)::bool,
               can_create = GREATEST(src.can_create::int, old.can_create::int)::bool,
               can_write = GREATEST(src.can_write::int, old.can_write::int)::bool,
               can_unlink = GREATEST(src.can_unlink::int, old.can_unlink::int)::bool,
               can_admin = GREATEST(src.can_admin::int, old.can_admin::int)::bool
          FROM security_internet_menu_permission AS old
         WHERE src.role_id = old.role_id
           AND src.menu_code = 'payment_confirm'
           AND old.menu_code IN ('payment_tracking', 'payment_track')
        """
    )
    cr.execute(
        """
        UPDATE security_internet_menu_permission
           SET menu_code = 'payment_overdue'
         WHERE menu_code IN ('alert_overdue', 'expired')
           AND NOT EXISTS (
                SELECT 1 FROM security_internet_menu_permission t
                 WHERE t.role_id = security_internet_menu_permission.role_id
                   AND t.menu_code = 'payment_overdue'
           )
        """
    )
    cr.execute(
        """
        UPDATE security_internet_menu_permission AS src
           SET can_read = GREATEST(src.can_read::int, old.can_read::int)::bool,
               can_create = GREATEST(src.can_create::int, old.can_create::int)::bool,
               can_write = GREATEST(src.can_write::int, old.can_write::int)::bool,
               can_unlink = GREATEST(src.can_unlink::int, old.can_unlink::int)::bool,
               can_admin = GREATEST(src.can_admin::int, old.can_admin::int)::bool
          FROM security_internet_menu_permission AS old
         WHERE src.role_id = old.role_id
           AND src.menu_code = 'payment_overdue'
           AND old.menu_code IN ('alert_overdue', 'expired')
        """
    )
    cr.execute(
        """
        UPDATE security_internet_menu_permission AS src
           SET can_read = GREATEST(src.can_read::int, old.can_read::int)::bool,
               can_create = GREATEST(src.can_create::int, old.can_create::int)::bool,
               can_write = GREATEST(src.can_write::int, old.can_write::int)::bool,
               can_unlink = GREATEST(src.can_unlink::int, old.can_unlink::int)::bool,
               can_admin = GREATEST(src.can_admin::int, old.can_admin::int)::bool
          FROM security_internet_menu_permission AS old
         WHERE src.role_id = old.role_id
           AND src.menu_code = 'payment_schedule'
           AND old.menu_code IN ('alert_due_soon', 'expire_soon')
        """
    )
    cr.execute(
        """
        DELETE FROM security_internet_menu_permission
         WHERE menu_code IN (
            'group_alerts', 'payment_tracking', 'payment_track',
            'alert_overdue', 'alert_due_soon', 'expire_soon', 'expired'
         )
        """
    )
    # Ẩn menu list Odoo cũ
    cr.execute(
        """
        UPDATE ir_ui_menu SET active = FALSE
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'lug_phan_he'
               AND name IN ('menu_phan_he_payment_file', 'menu_phan_he_payment_paid')
               AND model = 'ir.ui.menu'
         )
        """
    )
