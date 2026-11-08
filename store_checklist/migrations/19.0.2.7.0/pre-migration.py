def migrate(cr, version):
    # store_id trỏ sang hr.store: đổi id store.store cũ thành id hr.store cùng mã (chưa có thì tạo)
    cr.execute("SELECT to_regclass('store_store')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT id, name, code FROM store_store")
    for old_id, name, code in cr.fetchall():
        cr.execute("SELECT id FROM hr_store WHERE code = %s ORDER BY id LIMIT 1", (code,))
        row = cr.fetchone()
        if row:
            new_id = row[0]
        else:
            cr.execute(
                "INSERT INTO hr_store (name, code, active, company_id) "
                "VALUES (jsonb_build_object('en_US', %s), %s, true, (SELECT id FROM res_company ORDER BY id LIMIT 1)) "
                "RETURNING id", (name, code))
            new_id = cr.fetchone()[0]
        cr.execute("ALTER TABLE store_audit DROP CONSTRAINT IF EXISTS store_audit_store_id_fkey")
        cr.execute("ALTER TABLE store_audit_line DROP CONSTRAINT IF EXISTS store_audit_line_store_id_fkey")
        cr.execute("ALTER TABLE store_audit_action DROP CONSTRAINT IF EXISTS store_audit_action_store_id_fkey")
        # ids cũ và mới có thể trùng nhau: dịch sang vùng âm tạm rồi đảo lại sau
        for t in ("store_audit", "store_audit_line", "store_audit_action"):
            cr.execute(f"UPDATE {t} SET store_id = -%s WHERE store_id = %s", (new_id, old_id))
    for t in ("store_audit", "store_audit_line", "store_audit_action"):
        cr.execute(f"UPDATE {t} SET store_id = -store_id WHERE store_id < 0")
