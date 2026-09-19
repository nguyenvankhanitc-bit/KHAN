# -*- coding: utf-8 -*-
"""Convert payment menu actions act_window → ir.actions.client (same xmlid).

Odoo refuses updating xmlid when model changes; must remap before loading views.
"""


def _convert_action(cr, xmlid_name, client_name, open_nav, fallback_list_raw=False):
    cr.execute(
        """
        SELECT res_id, model FROM ir_model_data
        WHERE module = 'lug_phan_he' AND name = %s
        """,
        (xmlid_name,),
    )
    row = cr.fetchone()
    if not row:
        return
    old_id, model = row
    if model == "ir.actions.client":
        return

    ctx = (
        "{'phan_he_service_type_code': 'internet', "
        "'phan_he_app_title': 'Internet', "
        f"'phan_he_open_nav': '{open_nav}'}}"
    )
    cr.execute(
        """
        INSERT INTO ir_act_client
            (name, type, tag, context, target, binding_type, binding_view_types,
             create_uid, write_uid, create_date, write_date)
        VALUES
            (%s::jsonb, 'ir.actions.client', 'phan_he_dashboard', %s,
             'current', 'action', 'list,form', 1, 1, NOW(), NOW())
        RETURNING id
        """,
        (f'{{"en_US": "{client_name}"}}', ctx),
    )
    new_id = cr.fetchone()[0]
    cr.execute(
        """
        UPDATE ir_model_data
           SET model = 'ir.actions.client', res_id = %s, write_date = NOW()
         WHERE module = 'lug_phan_he' AND name = %s
        """,
        (new_id, xmlid_name),
    )
    cr.execute(
        """
        UPDATE ir_ui_menu
           SET action = %s
         WHERE action = %s
        """,
        (f"ir.actions.client,{new_id}", f"ir.actions.act_window,{old_id}"),
    )
    if fallback_list_raw:
        cr.execute(
            """
            SELECT 1 FROM ir_model_data
            WHERE module = 'lug_phan_he' AND name = 'action_phan_he_payment_list_raw'
            """
        )
        if not cr.fetchone():
            cr.execute(
                """
                INSERT INTO ir_model_data
                    (module, name, model, res_id, noupdate, create_date, write_date)
                VALUES
                    ('lug_phan_he', 'action_phan_he_payment_list_raw',
                     'ir.actions.act_window', %s, false, NOW(), NOW())
                """,
                (old_id,),
            )


def migrate(cr, version):
    _convert_action(
        cr,
        "action_phan_he_payment",
        "Lịch thanh toán",
        "payment_schedule",
        fallback_list_raw=True,
    )
    _convert_action(
        cr,
        "action_phan_he_payment_confirm",
        "Xác nhận TT",
        "payment_confirm",
    )
    _convert_action(
        cr,
        "action_phan_he_payment_overdue_board",
        "Quá hạn",
        "payment_overdue",
    )
    _convert_action(
        cr,
        "action_phan_he_payment_forecast",
        "Dự kiến thanh toán",
        "payment_forecast",
    )
