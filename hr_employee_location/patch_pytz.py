# -*- coding: utf-8 -*-
import logging
import sys
import pytz

_logger = logging.getLogger(__name__)

_orig_pytz_timezone = pytz.timezone


def _safe_pytz_timezone(name):
    """
    Bản vá an toàn ngăn ngừa lỗi khi Odoo hoặc các addon gọi pytz.timezone(employee.tz)
    mà employee.tz là False, None hoặc rỗng, gây ra NotImplementedError trong pkg_resources:
    'Can\'t perform this operation for loaders without get_data()'.
    """
    if not name or name is False:
        try:
            return _orig_pytz_timezone("Asia/Ho_Chi_Minh")
        except Exception:
            return pytz.UTC
    try:
        return _orig_pytz_timezone(name)
    except Exception as e:
        _logger.warning("Không thể load múi giờ %r (%s), tự động fallback sang 'Asia/Ho_Chi_Minh'", name, e)
        try:
            return _orig_pytz_timezone("Asia/Ho_Chi_Minh")
        except Exception:
            return pytz.UTC


# Áp dụng bản vá an toàn lên pytz.timezone
pytz.timezone = _safe_pytz_timezone

# Đồng bộ lên các module đã import trực tiếp `from pytz import timezone`
for mod_name, mod in list(sys.modules.items()):
    if mod:
        if hasattr(mod, "pytz") and hasattr(mod.pytz, "timezone"):
            try:
                mod.pytz.timezone = _safe_pytz_timezone
            except Exception:
                pass
        if hasattr(mod, "timezone") and getattr(mod, "timezone", None) == _orig_pytz_timezone:
            try:
                mod.timezone = _safe_pytz_timezone
            except Exception:
                pass

_logger.info("Đã khởi tạo bản vá bảo vệ múi giờ _safe_pytz_timezone.")
