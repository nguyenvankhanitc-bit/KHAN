def migrate(cr, version):
    # Mới thêm báo nhóm Lark khi Checklist GS chấm xong: phiếu GS đã chấm từ trước coi như đã báo,
    # tránh gửi hàng loạt phiếu cũ vào nhóm khi có người mở/sửa lại phiếu cũ.
    if not version:
        return
    cr.execute("""
        UPDATE store_audit SET lark_sent = TRUE
         WHERE audit_type = 'gs' AND state != 'draft' AND lark_sent IS NOT TRUE
    """)
