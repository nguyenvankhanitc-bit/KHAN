# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đặt định dạng ngày tiếng Việt: dd/mm/yyyy (ví dụ 24/07/2026)."""
    cr.execute(
        "UPDATE res_lang SET date_format = %s WHERE code = %s",
        ("%d/%m/%Y", "vi_VN"),
    )
