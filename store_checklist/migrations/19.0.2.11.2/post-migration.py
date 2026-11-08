def migrate(cr, version):
    # phiếu đã lưu từ popup (chưa có nút Gửi kết quả) mà đã chấm điểm thì chuyển sang Đã đánh giá
    cr.execute("""
        UPDATE store_audit a SET state = 'audited'
        WHERE a.state = 'draft'
          AND EXISTS (SELECT 1 FROM store_audit_line l WHERE l.audit_id = a.id AND l.is_scored)
    """)
