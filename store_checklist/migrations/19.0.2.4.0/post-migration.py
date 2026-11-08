def migrate(cr, version):
    # Phân nhóm từ chuỗi cũ sang bảng cấu hình: khớp theo tên
    cr.execute("""
        UPDATE store_audit_template_line l
           SET sub_group_id = g.id
          FROM store_audit_sub_group g
         WHERE l.sub_group_id IS NULL AND l.sub_category = g.name
    """)
