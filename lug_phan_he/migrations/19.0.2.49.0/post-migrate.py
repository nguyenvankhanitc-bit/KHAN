# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đảm bảo 6 loại dịch vụ app tồn tại (kể cả khi noupdate chặn XML)."""
    types = [
        ("CAMERA", "camera", 20),
        ("MÁY CHẤM CÔNG", "attendance", 30),
        ("LINKQ HRM", "linkq_hrm", 40),
        ("LINKQ NB", "linkq_nb", 50),
        ("MÁY CHỦ", "server", 60),
    ]
    for name, code, seq in types:
        cr.execute(
            """
            INSERT INTO phan_he_service_type (name, code, sequence, active, create_uid, write_uid, create_date, write_date)
            SELECT %s, %s, %s, TRUE, 1, 1, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
            WHERE NOT EXISTS (
                SELECT 1 FROM phan_he_service_type WHERE code = %s
            )
            """,
            (name, code, seq, code),
        )
