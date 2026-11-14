def migrate(cr, version):
    """Các việc khắc phục đã Hoàn thành từ trước cũng bị khóa, người phụ trách không sửa lại được."""
    cr.execute("UPDATE store_audit_action SET resp_locked = TRUE WHERE state = 'done'")
