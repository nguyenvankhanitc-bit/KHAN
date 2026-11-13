def migrate(cr, version):
    # Trạng thái khắc phục rút còn 3 giá trị: Chưa làm / Đang làm / Hoàn thành
    cr.execute("UPDATE store_audit_action SET state = 'doing' WHERE state = 'wait'")
    cr.execute("UPDATE store_audit_action SET state = 'done' WHERE state = 'verified'")
