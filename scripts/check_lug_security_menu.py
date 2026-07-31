# -*- coding: utf-8 -*-

import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, user="odoo", password="odoo", dbname="lap_odoo19"
)
cur = conn.cursor()
cur.execute(
    """
    SELECT u.login, d.module, d.name
    FROM res_users u
    JOIN res_groups_users_rel r ON r.uid = u.id
    JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = r.gid
    WHERE u.login = 'admin'
      AND d.module IN ('lug_security_audit', 'lug_permission')
    ORDER BY d.module, d.name
    """
)
print("admin groups:", cur.fetchall())

cur.execute(
    """
    SELECT m.id, m.name::text, m.parent_id, m.sequence, m.active,
           (SELECT name::text FROM ir_ui_menu p WHERE p.id = m.parent_id) AS parent_name
    FROM ir_ui_menu m
    JOIN ir_model_data d ON d.model = 'ir.ui.menu' AND d.res_id = m.id
    WHERE d.module = 'lug_security_audit' AND d.name = 'menu_lug_security_root'
    """
)
print("root menu:", cur.fetchone())
conn.close()
