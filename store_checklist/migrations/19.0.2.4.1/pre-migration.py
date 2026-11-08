def migrate(cr, version):
    # cột mới required: tạo sẵn và gán theo phân nhóm I-III = A, IV-V = B, VI = C
    cr.execute("ALTER TABLE store_audit_sub_group ADD COLUMN IF NOT EXISTS category varchar")
    cr.execute("""UPDATE store_audit_sub_group SET category = CASE
        WHEN name LIKE 'VI.%' THEN 'c' WHEN name LIKE 'IV.%' OR name LIKE 'V.%' THEN 'b' ELSE 'a' END""")
