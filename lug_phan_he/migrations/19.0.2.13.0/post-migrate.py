# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Đặt định dạng ngày tiếng Việt: dd/mm/yy."""
    cr.execute(
        "UPDATE res_lang SET date_format = %s WHERE code = %s",
        ("%d/%m/%y", "vi_VN"),
    )
